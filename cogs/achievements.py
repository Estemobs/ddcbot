"""Succes, automatisations et salon d'accueil.

Trois modules qui partagent la meme mecanique : observer ce que font les
membres, puis declencher quelque chose. Les regles vivent dans
achievements_engine, sans discord.py ; ce cog tient les compteurs a jour,
ecoute les evenements et applique les recompenses et actions.

Commandes :
  ,succes                       — ses succes et sa progression
  ,succesadd <nom> <compteur> <objectif> [recompense] [valeur]
  ,succesdel <nom>
  ,autos                        — automatisations configurees
  ,autotoggle <id>
  ,accueil                      — etat du salon d'accueil
"""

import asyncio
import time

import discord
from discord.ext import commands

import achievements_engine as engine
from achievements_engine import METRICS, progress

VOICE_FLUSH_SECONDS = 60


class cmdachievements(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        # Entrees en vocal en cours : (guild_id, user_id) -> horodatage d'arrivee.
        self._voice_since = {}

    # --- compteurs d'activite ---

    def touch(self, guild_id: int, user_id: int, **increments):
        """Cree la ligne d'activite si besoin et incremente des compteurs."""
        self.db.execute(
            "INSERT OR IGNORE INTO member_activity (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id),
        )
        allowed = {"messages", "voice_seconds", "reactions"}
        parts = [f"{k} = {k} + ?" for k in increments if k in allowed]
        values = [increments[k] for k in increments if k in allowed]
        parts.append("last_seen = unixepoch()")
        self.db.execute(
            f"UPDATE member_activity SET {', '.join(parts)} WHERE guild_id = ? AND user_id = ?",
            values + [guild_id, user_id],
        )

    def get_activity(self, guild_id: int, user_id: int) -> dict:
        row = self.db.fetchone(
            "SELECT * FROM member_activity WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return dict(row) if row else {}

    # --- succes ---

    def get_ach_config(self, guild_id: int) -> dict:
        self.db.execute(
            "INSERT OR IGNORE INTO achievement_config (guild_id) VALUES (?)", (guild_id,)
        )
        return dict(self.db.fetchone(
            "SELECT * FROM achievement_config WHERE guild_id = ?", (guild_id,)
        ))

    def list_achievements(self, guild_id: int, include_disabled: bool = False) -> list:
        sql = "SELECT * FROM achievements WHERE guild_id = ?"
        if not include_disabled:
            sql += " AND enabled = 1"
        sql += " ORDER BY metric, goal"
        return [dict(r) for r in self.db.fetchall(sql, (guild_id,))]

    def create_achievement(self, guild_id: int, name: str, metric: str, goal: int,
                           reward_kind: str = "none", reward_value: str = "",
                           description: str = "", icon: str = "🏅") -> int:
        if metric not in METRICS:
            raise engine.AutomationError(f"Compteur inconnu : {metric}")
        if reward_kind not in engine.REWARD_KINDS:
            raise engine.AutomationError(f"Recompense inconnue : {reward_kind}")
        cur = self.db.execute(
            "INSERT INTO achievements (guild_id, name, description, icon, metric, goal, "
            "reward_kind, reward_value) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, name) DO UPDATE SET description=excluded.description, "
            "icon=excluded.icon, metric=excluded.metric, goal=excluded.goal, "
            "reward_kind=excluded.reward_kind, reward_value=excluded.reward_value",
            (guild_id, name, description, icon, metric, max(1, goal),
             reward_kind, str(reward_value)),
        )
        return cur.lastrowid

    def delete_achievement(self, guild_id: int, name: str) -> bool:
        row = self.db.fetchone(
            "SELECT id FROM achievements WHERE guild_id = ? AND LOWER(name) = LOWER(?)",
            (guild_id, name),
        )
        if row is None:
            return False
        self.db.execute("DELETE FROM achievement_unlocks WHERE achievement_id = ?", (row["id"],))
        self.db.execute("DELETE FROM achievements WHERE id = ?", (row["id"],))
        return True

    def is_unlocked(self, achievement_id: int, user_id: int) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM achievement_unlocks WHERE achievement_id = ? AND user_id = ?",
            (achievement_id, user_id),
        ) is not None

    def unlock(self, achievement_id: int, user_id: int):
        self.db.execute(
            "INSERT OR IGNORE INTO achievement_unlocks (achievement_id, user_id) VALUES (?, ?)",
            (achievement_id, user_id),
        )

    def newly_unlocked(self, guild_id: int, user_id: int) -> list:
        """Succes atteints et pas encore debloques."""
        due = []
        for achievement in self.list_achievements(guild_id):
            if self.is_unlocked(achievement["id"], user_id):
                continue
            _, _, reached = progress(self.db, achievement, guild_id, user_id)
            if reached:
                due.append(achievement)
        return due

    async def grant_reward(self, guild, member, kind: str, value: str) -> str:
        if kind == "money":
            try:
                amount = float(value)
            except (TypeError, ValueError):
                return ""
            self.db.execute(
                "INSERT INTO balances (user_id, amount) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET amount = amount + excluded.amount",
                (member.id, amount),
            )
            self.db.log_transaction(guild.id, member.id, amount, "achievement", "succes")
            return f"{amount:.0f} pièces"
        if kind == "role":
            try:
                role = guild.get_role(int(value))
            except (TypeError, ValueError):
                role = None
            if role is None:
                return ""
            try:
                await member.add_roles(role, reason="Succes debloque")
            except (discord.Forbidden, discord.HTTPException):
                return ""
            return f"le rôle **{role.name}**"
        return ""

    async def check_achievements(self, guild, member):
        """Debloque, recompense et annonce les succes atteints par ce membre."""
        cfg = self.get_ach_config(guild.id)
        if not cfg["enabled"]:
            return
        for achievement in self.newly_unlocked(guild.id, member.id):
            self.unlock(achievement["id"], member.id)
            reward = await self.grant_reward(
                guild, member, achievement["reward_kind"], achievement["reward_value"]
            )
            if not achievement["announce"] or not cfg["channel_id"]:
                continue
            channel = guild.get_channel(cfg["channel_id"])
            if channel is None:
                continue
            embed = discord.Embed(
                title=f"{achievement['icon']} {achievement['name']}",
                description=achievement["description"] or None,
                color=discord.Color.gold(),
            )
            embed.set_author(name=str(member), icon_url=getattr(member.display_avatar, "url", None))
            if reward:
                embed.add_field(name="Récompense", value=reward, inline=True)
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

    # --- automatisations ---

    def list_automations(self, guild_id: int, event: str = None,
                         only_enabled: bool = False) -> list:
        sql = "SELECT * FROM automations WHERE guild_id = ?"
        params = [guild_id]
        if event:
            sql += " AND event = ?"
            params.append(event)
        if only_enabled:
            sql += " AND enabled = 1"
        sql += " ORDER BY id"
        return [dict(r) for r in self.db.fetchall(sql, params)]

    def mark_run(self, rule_id: int):
        self.db.execute(
            "UPDATE automations SET runs = runs + 1, last_run = ? WHERE id = ?",
            (time.time(), rule_id),
        )

    async def run_actions(self, rule: dict, guild, member=None, channel=None,
                          message=None, context: dict = None):
        """Applique les actions d'une regle. Chaque echec est isole."""
        context = context or {}
        for action in engine.parse_actions(rule["actions_json"]):
            kind = action["kind"]
            text = engine.render(action["value"], context)
            try:
                if kind == "send_message":
                    target = guild.get_channel(int(action["target"])) if action["target"] else channel
                    if target is not None:
                        await target.send(text)
                elif kind == "send_dm" and member is not None:
                    await member.send(text)
                elif kind in ("add_role", "remove_role") and member is not None:
                    role = guild.get_role(int(action["target"] or action["value"] or 0))
                    if role is not None:
                        if kind == "add_role":
                            await member.add_roles(role, reason=f"Automatisation {rule['name']}")
                        else:
                            await member.remove_roles(role, reason=f"Automatisation {rule['name']}")
                elif kind == "add_money" and member is not None:
                    amount = float(action["value"] or 0)
                    self.db.execute(
                        "INSERT INTO balances (user_id, amount) VALUES (?, ?) "
                        "ON CONFLICT(user_id) DO UPDATE SET amount = amount + excluded.amount",
                        (member.id, amount),
                    )
                    self.db.log_transaction(
                        guild.id, member.id, amount, "automation", rule["name"]
                    )
                elif kind == "react" and message is not None:
                    await message.add_reaction(action["value"])
            except (discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                continue
        self.mark_run(rule["id"])

    async def fire(self, event: str, guild, *, member=None, channel=None, message=None,
                   text="", role_ids=None, context=None):
        """Declenche les regles d'un evenement dont la condition est satisfaite."""
        if guild is None:
            return
        for rule in self.list_automations(guild.id, event, only_enabled=True):
            if engine.on_cooldown(rule):
                continue
            if not engine.matches(rule, text=text, role_ids=role_ids,
                                  channel_id=getattr(channel, "id", None)):
                continue
            await self.run_actions(rule, guild, member, channel, message, context)

    # --- salon d'accueil ---

    def get_welcome_panel(self, guild_id: int) -> dict:
        self.db.execute(
            "INSERT OR IGNORE INTO welcome_panel (guild_id) VALUES (?)", (guild_id,)
        )
        return dict(self.db.fetchone(
            "SELECT * FROM welcome_panel WHERE guild_id = ?", (guild_id,)
        ))

    async def refresh_welcome_panel(self, guild):
        """Republie ou met a jour l'embed d'accueil en tete du salon."""
        cfg = self.get_welcome_panel(guild.id)
        if not cfg["enabled"] or not cfg["channel_id"] or not cfg["embed_name"]:
            return
        channel = guild.get_channel(cfg["channel_id"])
        if channel is None:
            return
        stored = self.db.fetchone(
            "SELECT * FROM embeds WHERE guild_id = ? AND name = ?",
            (guild.id, cfg["embed_name"]),
        )
        if stored is None:
            return
        import embed_builder
        from cogs.embeds import build_discord_embed
        resolved = dict(stored)
        for key in ("title", "description", "footer_text", "author_name"):
            resolved[key] = embed_builder.render_variables(resolved.get(key), guild)
        built = build_discord_embed(embed_builder.to_payload(resolved))

        if cfg["message_id"]:
            try:
                message = await channel.fetch_message(cfg["message_id"])
                await message.edit(embed=built)
                return
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        try:
            message = await channel.send(embed=built)
        except (discord.Forbidden, discord.HTTPException):
            return
        self.db.execute(
            "UPDATE welcome_panel SET message_id = ? WHERE guild_id = ?",
            (message.id, guild.id),
        )

    async def greet(self, member):
        cfg = self.get_welcome_panel(member.guild.id)
        if not cfg["enabled"] or not cfg["channel_id"]:
            return
        channel = member.guild.get_channel(cfg["channel_id"])
        if channel is None:
            return
        text = engine.render(cfg["greet_template"], {
            "user": member.mention,
            "name": member.display_name,
            "server": member.guild.name,
            "count": member.guild.member_count or "",
        })
        try:
            await channel.send(text)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # --- evenements ---

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return
        self.touch(message.guild.id, message.author.id, messages=1)
        await self.check_achievements(message.guild, message.author)
        await self.fire(
            "message", message.guild, member=message.author, channel=message.channel,
            message=message, text=message.content,
            role_ids=[r.id for r in getattr(message.author, "roles", [])],
            context={"user": message.author.mention, "name": message.author.display_name,
                     "server": message.guild.name},
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.guild_id is None or payload.user_id == getattr(self.bot.user, "id", None):
            return
        self.touch(payload.guild_id, payload.user_id, reactions=1)
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        await self.fire(
            "reaction_add", guild, member=member,
            channel=guild.get_channel(payload.channel_id), text=str(payload.emoji),
            role_ids=[r.id for r in getattr(member, "roles", [])] if member else [],
            context={"user": member.mention if member else "", "server": guild.name},
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        key = (member.guild.id, member.id)
        now = time.time()
        if before.channel is None and after.channel is not None:
            self._voice_since[key] = now
        elif before.channel is not None and after.channel is None:
            started = self._voice_since.pop(key, None)
            if started is not None:
                seconds = int(now - started)
                if seconds >= VOICE_FLUSH_SECONDS:
                    self.touch(member.guild.id, member.id, voice_seconds=seconds)
                    await self.check_achievements(member.guild, member)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot:
            return
        self.touch(member.guild.id, member.id)
        await self.greet(member)
        await self.fire(
            "member_join", member.guild, member=member,
            context={"user": member.mention, "name": member.display_name,
                     "server": member.guild.name, "count": member.guild.member_count or ""},
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.fire(
            "member_leave", member.guild, member=member,
            context={"user": str(member), "name": member.display_name,
                     "server": member.guild.name, "count": member.guild.member_count or ""},
        )

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try:
                await self.refresh_welcome_panel(guild)
            except Exception as exc:
                print(f"[DEBUG] Salon d'accueil impossible pour {guild.id}: {exc}")
            await asyncio.sleep(0)

    # --- commandes ---

    @commands.command(aliases=["achievements"])
    async def succes(self, ctx, member: discord.Member = None):
        """Progression sur les succes du serveur."""
        member = member or ctx.author
        achievements = self.list_achievements(ctx.guild.id)
        if not achievements:
            await ctx.send(
                "Aucun succès configuré. Ajoutez-en avec `,succesadd` ou depuis le dashboard."
            )
            return
        embed = discord.Embed(
            title=f"🏅 Succès de {member.display_name}", color=discord.Color.gold()
        )
        unlocked = 0
        for achievement in achievements[:20]:
            value, goal, reached = progress(self.db, achievement, ctx.guild.id, member.id)
            done = self.is_unlocked(achievement["id"], member.id) or reached
            unlocked += 1 if done else 0
            filled = min(10, int(10 * value / goal)) if goal else 10
            bar = "▰" * filled + "▱" * (10 - filled)
            embed.add_field(
                name=f"{'✅' if done else achievement['icon']} {achievement['name']} "
                     f"({min(value, goal)}/{goal})",
                value=f"{bar}\n{engine.metric_label(achievement['metric'])}",
                inline=False,
            )
        embed.set_footer(text=f"{unlocked}/{len(achievements)} débloqué(s)")
        await ctx.send(embed=embed)

    @commands.command()
    async def succesadd(self, ctx, name: str, metric: str, goal: int,
                        reward_kind: str = "none", reward_value: str = ""):
        """,succesadd <nom> <compteur> <objectif> [none|money|role] [valeur]"""
        try:
            self.create_achievement(ctx.guild.id, name, metric.lower(), goal,
                                    reward_kind.lower(), reward_value)
        except engine.AutomationError as exc:
            await ctx.send(f"❌ {exc}\nCompteurs : " + ", ".join(f"`{m}`" for m in METRICS))
            return
        await ctx.send(f"✅ Succès **{name}** enregistré.")

    @commands.command()
    async def succesdel(self, ctx, *, name: str):
        if self.delete_achievement(ctx.guild.id, name):
            await ctx.send(f"✅ Succès **{name}** supprimé.")
        else:
            await ctx.send("❌ Ce succès n'existe pas.")

    @commands.command()
    async def autos(self, ctx):
        """Liste les automatisations du serveur."""
        rules = self.list_automations(ctx.guild.id)
        if not rules:
            await ctx.send(
                "Aucune automatisation. Elles se composent depuis le dashboard "
                "(événement → condition → actions)."
            )
            return
        lines = []
        for rule in rules:
            actions = engine.parse_actions(rule["actions_json"])
            state = "" if rule["enabled"] else " · ⏸"
            lines.append(
                f"`#{rule['id']}` **{rule['name']}** — {rule['event']} → "
                f"{len(actions)} action(s) · {rule['runs']} exéc.{state}"
            )
        await ctx.send(embed=discord.Embed(
            title="⚙️ Automatisations",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        ))

    @commands.command()
    async def autotoggle(self, ctx, rule_id: int):
        """Active ou met en pause une automatisation."""
        cur = self.db.execute(
            "UPDATE automations SET enabled = 1 - enabled WHERE id = ? AND guild_id = ?",
            (rule_id, ctx.guild.id),
        )
        if not cur.rowcount:
            await ctx.send("❌ Cette automatisation n'existe pas.")
            return
        row = self.db.fetchone("SELECT enabled FROM automations WHERE id = ?", (rule_id,))
        await ctx.send("✅ " + ("Activée." if row["enabled"] else "Mise en pause."))

    @commands.command()
    async def accueil(self, ctx):
        """Etat du salon d'accueil."""
        cfg = self.get_welcome_panel(ctx.guild.id)
        channel = ctx.guild.get_channel(cfg["channel_id"]) if cfg["channel_id"] else None
        embed = discord.Embed(title="👋 Salon d'accueil", color=discord.Color.blurple())
        embed.add_field(name="Etat", value="Actif" if cfg["enabled"] else "Desactive", inline=True)
        embed.add_field(name="Salon", value=channel.mention if channel else "Non defini",
                        inline=True)
        embed.add_field(name="Embed affiche", value=cfg["embed_name"] or "Aucun", inline=True)
        embed.add_field(name="Message d'accueil", value=cfg["greet_template"], inline=False)
        embed.set_footer(text="Configuration dans le dashboard")
        await ctx.send(embed=embed)


def setup(bot, db):
    bot.add_cog(cmdachievements(bot, db))
