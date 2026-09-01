"""Anniversaires : annonce automatique et role du jour.

Aucune dependance externe. La date est stockee sans annee obligatoire : beaucoup
de membres donnent leur jour et leur mois sans vouloir reveler leur age, et l'age
n'est affiche que s'ils ont fourni l'annee.

Commandes :
  ,birthday <JJ/MM[/AAAA]>      — enregistre son anniversaire
  ,birthday                     — affiche le sien
  ,birthdaydel                  — le supprime
  ,birthdays                 — les prochains anniversaires du serveur
  ,birthdayconfig               — configuration (admin)
"""

import asyncio
import datetime as dt
import re

import discord
from discord.ext import commands

DEFAULT_MESSAGE = "Joyeux anniversaire {user} ! 🎂"
CHECK_INTERVAL_SECONDS = 1800  # la boucle verifie l'heure d'annonce toutes les 30 min

DATE_RE = re.compile(r"^\s*(\d{1,2})\s*[/\-. ]\s*(\d{1,2})(?:\s*[/\-. ]\s*(\d{4}))?\s*$")

MONTHS_FR = [
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
]


def parse_birthday(text: str):
    """Analyse 'JJ/MM' ou 'JJ/MM/AAAA'. Renvoie (jour, mois, annee|None) ou None.

    Le 29 fevrier est accepte : c'est une date valide, simplement rare.
    """
    match = DATE_RE.match(text or "")
    if match is None:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    year = int(match.group(3)) if match.group(3) else None
    if not 1 <= month <= 12:
        return None
    # Annee bissextile de reference pour autoriser le 29 fevrier sans annee.
    try:
        dt.date(year or 2024, month, day)
    except ValueError:
        return None
    if year is not None and not 1900 <= year <= dt.date.today().year:
        return None
    return day, month, year


def format_birthday(day: int, month: int, year=None) -> str:
    label = f"{day} {MONTHS_FR[month - 1]}"
    return f"{label} {year}" if year else label


def age_on(day: int, month: int, year, today: dt.date) -> int | None:
    """Age atteint le jour de l'anniversaire, None si l'annee est inconnue."""
    if not year:
        return None
    return today.year - year


def days_until(day: int, month: int, today: dt.date) -> int:
    """Nombre de jours avant le prochain passage de cette date."""
    for candidate_year in (today.year, today.year + 1):
        try:
            date = dt.date(candidate_year, month, day)
        except ValueError:
            # 29 fevrier sur une annee non bissextile : on fete le 1er mars.
            date = dt.date(candidate_year, 3, 1)
        if date >= today:
            return (date - today).days
    return 0


class cmdbirthdays(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._task = None

    # --- configuration ---

    def get_config(self, guild_id: int) -> dict:
        self.db.execute("INSERT OR IGNORE INTO birthday_config (guild_id) VALUES (?)", (guild_id,))
        row = self.db.fetchone("SELECT * FROM birthday_config WHERE guild_id = ?", (guild_id,))
        return dict(row)

    def set_config(self, guild_id: int, **fields):
        self.get_config(guild_id)
        allowed = {"channel_id", "role_id", "message", "announce_hour", "enabled"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(
            f"UPDATE birthday_config SET {sets} WHERE guild_id = ?",
            list(fields.values()) + [guild_id],
        )

    # --- donnees ---

    def set_birthday(self, guild_id: int, user_id: int, day: int, month: int, year=None):
        self.db.execute(
            "INSERT INTO birthdays (guild_id, user_id, day, month, year) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET day=excluded.day, "
            "month=excluded.month, year=excluded.year",
            (guild_id, user_id, day, month, year),
        )

    def get_birthday(self, guild_id: int, user_id: int):
        row = self.db.fetchone(
            "SELECT day, month, year FROM birthdays WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return dict(row) if row else None

    def delete_birthday(self, guild_id: int, user_id: int) -> bool:
        cur = self.db.execute(
            "DELETE FROM birthdays WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        return bool(cur.rowcount)

    def birthdays_on(self, guild_id: int, day: int, month: int) -> list:
        return [dict(r) for r in self.db.fetchall(
            "SELECT user_id, day, month, year FROM birthdays "
            "WHERE guild_id = ? AND day = ? AND month = ?",
            (guild_id, day, month),
        )]

    def upcoming(self, guild_id: int, today: dt.date, limit: int = 15) -> list:
        rows = [dict(r) for r in self.db.fetchall(
            "SELECT user_id, day, month, year FROM birthdays WHERE guild_id = ?", (guild_id,)
        )]
        for row in rows:
            row["in_days"] = days_until(row["day"], row["month"], today)
        rows.sort(key=lambda r: r["in_days"])
        return rows[:limit]

    def already_announced(self, guild_id: int, user_id: int, on: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM birthday_announced WHERE guild_id = ? AND user_id = ? "
            "AND announced_on = ?",
            (guild_id, user_id, on),
        ) is not None

    def mark_announced(self, guild_id: int, user_id: int, on: str):
        self.db.execute(
            "INSERT OR IGNORE INTO birthday_announced (guild_id, user_id, announced_on) "
            "VALUES (?, ?, ?)",
            (guild_id, user_id, on),
        )

    def announced_before(self, guild_id: int, on: str) -> list:
        """Membres feted un autre jour que `on` : leur role du jour est a retirer."""
        return [r["user_id"] for r in self.db.fetchall(
            "SELECT DISTINCT user_id FROM birthday_announced "
            "WHERE guild_id = ? AND announced_on < ?",
            (guild_id, on),
        )]

    def clear_announced_before(self, guild_id: int, on: str):
        self.db.execute(
            "DELETE FROM birthday_announced WHERE guild_id = ? AND announced_on < ?",
            (guild_id, on),
        )

    # --- boucle d'annonce ---

    async def announce_for_guild(self, guild: discord.Guild, today: dt.date = None):
        today = today or dt.date.today()
        cfg = self.get_config(guild.id)
        if not cfg["enabled"] or not cfg["channel_id"]:
            return
        channel = guild.get_channel(cfg["channel_id"])
        if channel is None:
            return

        stamp = today.isoformat()
        role = guild.get_role(cfg["role_id"]) if cfg["role_id"] else None

        # Le role du jour precedent est retire avant de feter les nouveaux.
        if role is not None:
            for user_id in self.announced_before(guild.id, stamp):
                member = guild.get_member(user_id)
                if member is not None and role in member.roles:
                    try:
                        await member.remove_roles(role, reason="Anniversaire termine")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
        self.clear_announced_before(guild.id, stamp)

        celebrants = self.birthdays_on(guild.id, today.day, today.month)
        # Le 29 fevrier est fete le 1er mars les annees non bissextiles.
        if today.month == 3 and today.day == 1:
            try:
                dt.date(today.year, 2, 29)
            except ValueError:
                celebrants += self.birthdays_on(guild.id, 29, 2)

        for entry in celebrants:
            member = guild.get_member(entry["user_id"])
            if member is None or self.already_announced(guild.id, entry["user_id"], stamp):
                continue
            age = age_on(entry["day"], entry["month"], entry["year"], today)
            message = (cfg["message"] or DEFAULT_MESSAGE)
            message = message.replace("{user}", member.mention)
            message = message.replace("{name}", member.display_name)
            message = message.replace("{age}", str(age) if age is not None else "")
            message = message.replace("{server}", guild.name)
            try:
                await channel.send(message)
            except (discord.Forbidden, discord.HTTPException):
                continue
            if role is not None:
                try:
                    await member.add_roles(role, reason="Anniversaire")
                except (discord.Forbidden, discord.HTTPException):
                    pass
            self.mark_announced(guild.id, entry["user_id"], stamp)

    async def _loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                now = dt.datetime.now()
                for guild in self.bot.guilds:
                    cfg = self.get_config(guild.id)
                    if now.hour >= (cfg["announce_hour"] or 0):
                        await self.announce_for_guild(guild, now.date())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[DEBUG] Erreur boucle anniversaires: {exc}")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def cog_unload(self):
        if self._task is not None:
            self._task.cancel()

    # --- commandes ---

    @commands.command()
    async def birthday(self, ctx, *, date: str = None):
        """,birthday 24/12 ou ,birthday 24/12/2001 — sans argument, affiche le sien."""
        if date is None:
            entry = self.get_birthday(ctx.guild.id, ctx.author.id)
            if entry is None:
                await ctx.send(
                    "Vous n'avez pas enregistré d'anniversaire. "
                    "Utilisez `,birthday JJ/MM` (l'année est facultative)."
                )
                return
            await ctx.send(
                f"🎂 Votre anniversaire : **"
                f"{format_birthday(entry['day'], entry['month'], entry['year'])}**"
            )
            return

        parsed = parse_birthday(date)
        if parsed is None:
            await ctx.send("❌ Format attendu : `JJ/MM` ou `JJ/MM/AAAA`. Exemple : `,birthday 24/12`.")
            return
        day, month, year = parsed
        self.set_birthday(ctx.guild.id, ctx.author.id, day, month, year)
        await ctx.send(f"✅ Anniversaire enregistré : **{format_birthday(day, month, year)}**.")

    @commands.command()
    async def birthdaydel(self, ctx):
        """Supprime son anniversaire."""
        if self.delete_birthday(ctx.guild.id, ctx.author.id):
            await ctx.send("✅ Anniversaire supprimé.")
        else:
            await ctx.send("Vous n'aviez pas d'anniversaire enregistré.")

    @commands.command()
    async def birthdays(self, ctx):
        """Prochains anniversaires du serveur."""
        today = dt.date.today()
        entries = self.upcoming(ctx.guild.id, today)
        if not entries:
            await ctx.send("Aucun anniversaire enregistré sur ce serveur.")
            return
        lines = []
        for entry in entries:
            member = ctx.guild.get_member(entry["user_id"])
            name = member.display_name if member else f"<@{entry['user_id']}>"
            when = format_birthday(entry["day"], entry["month"])
            if entry["in_days"] == 0:
                lines.append(f"🎂 **{name}** — aujourd'hui !")
            else:
                lines.append(f"• **{name}** — {when} (dans {entry['in_days']} j)")
        await ctx.send(embed=discord.Embed(
            title="🎂 Prochains anniversaires",
            description="\n".join(lines),
            color=discord.Color.magenta(),
        ))

    @commands.command()
    async def birthdayconfig(self, ctx, action: str = None, *, value: str = None):
        """,birthdayconfig channel #salon | role @role | message <texte> | heure <0-23> | on | off"""
        cfg = self.get_config(ctx.guild.id)
        if action is None:
            channel = ctx.guild.get_channel(cfg["channel_id"]) if cfg["channel_id"] else None
            role = ctx.guild.get_role(cfg["role_id"]) if cfg["role_id"] else None
            embed = discord.Embed(title="Anniversaires", color=discord.Color.magenta())
            embed.add_field(name="Etat", value="Actifs" if cfg["enabled"] else "Desactives",
                            inline=True)
            embed.add_field(name="Salon", value=channel.mention if channel else "Non defini",
                            inline=True)
            embed.add_field(name="Role du jour", value=role.mention if role else "Aucun",
                            inline=True)
            embed.add_field(name="Heure d'annonce", value=f"{cfg['announce_hour']}h", inline=True)
            embed.add_field(name="Message", value=cfg["message"], inline=False)
            embed.set_footer(text="Variables : {user} {name} {age} {server}")
            await ctx.send(embed=embed)
            return

        action = action.lower()
        if action == "channel":
            channel = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None
            if channel is None and value and value.strip().isdigit():
                channel = ctx.guild.get_channel(int(value.strip()))
            if channel is None:
                await ctx.send("Usage : `,birthdayconfig channel #salon`")
                return
            self.set_config(ctx.guild.id, channel_id=channel.id)
            await ctx.send(f"✅ Annonces dans {channel.mention}.")
        elif action == "role":
            role = ctx.message.role_mentions[0] if ctx.message.role_mentions else None
            if role is None and value and value.strip().isdigit():
                role = ctx.guild.get_role(int(value.strip()))
            if role is None:
                await ctx.send("Usage : `,birthdayconfig role @role`")
                return
            self.set_config(ctx.guild.id, role_id=role.id)
            await ctx.send(f"✅ Le rôle **{role.name}** sera donné le jour J.")
        elif action == "message":
            if not value:
                await ctx.send("Usage : `,birthdayconfig message Joyeux anniversaire {user} !`")
                return
            self.set_config(ctx.guild.id, message=value)
            await ctx.send("✅ Message enregistré.")
        elif action in ("heure", "hour"):
            if not value or not value.strip().isdigit() or not 0 <= int(value.strip()) <= 23:
                await ctx.send("Usage : `,birthdayconfig heure 9` (0 à 23)")
                return
            self.set_config(ctx.guild.id, announce_hour=int(value.strip()))
            await ctx.send(f"✅ Annonce à partir de {int(value.strip())}h.")
        elif action in ("on", "off"):
            self.set_config(ctx.guild.id, enabled=1 if action == "on" else 0)
            await ctx.send("✅ Anniversaires " + ("activés." if action == "on" else "désactivés."))
        else:
            await ctx.send(
                "Actions : `channel #salon`, `role @role`, `message <texte>`, "
                "`heure <0-23>`, `on`, `off`."
            )


def setup(bot, db):
    bot.add_cog(cmdbirthdays(bot, db))
