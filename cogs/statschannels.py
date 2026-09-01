"""Salons de statistiques : des salons dont le nom affiche un compteur vivant.

Aucune dependance externe, tout vient du cache de la guilde.

Discord limite le renommage d'un salon a 2 fois par 10 minutes ; au-dela la
requete est mise en attente et bloque la file. La boucle tourne donc toutes les
10 minutes et n'ecrit que si la valeur a change.

Commandes :
  ,statschannel add <id_salon> <type> [modele]  — suit un compteur
  ,statschannel remove <id_salon>
  ,statschannel list
  ,statschannel refresh                          — force une mise a jour
"""

import asyncio

import discord
from discord.ext import commands

UPDATE_INTERVAL_SECONDS = 600  # 2 renommages / 10 min par salon cote Discord

# Chaque type sait se calculer depuis la guilde, sans appel reseau.
KINDS = {
    "members": ("Membres", lambda g, role: g.member_count or len(g.members)),
    "humans": ("Humains", lambda g, role: sum(1 for m in g.members if not m.bot)),
    "bots": ("Bots", lambda g, role: sum(1 for m in g.members if m.bot)),
    "online": ("En ligne", lambda g, role: sum(
        1 for m in g.members if str(getattr(m, "status", "offline")) != "offline")),
    "boosts": ("Boosts", lambda g, role: g.premium_subscription_count or 0),
    "roles": ("Roles", lambda g, role: len(g.roles)),
    "channels": ("Salons", lambda g, role: len(g.channels)),
    "role": ("Role", lambda g, role: len(role.members) if role is not None else 0),
}


class cmdstatschannels(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._task = None

    # --- donnees ---

    def add_channel(self, guild_id: int, channel_id: int, kind: str,
                    template: str = "{label} : {value}", role_id: int = None):
        self.db.execute(
            "INSERT INTO stats_channels (channel_id, guild_id, kind, template, role_id) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(channel_id) DO UPDATE SET "
            "kind=excluded.kind, template=excluded.template, role_id=excluded.role_id",
            (channel_id, guild_id, kind, template, role_id),
        )

    def remove_channel(self, channel_id: int) -> bool:
        cur = self.db.execute("DELETE FROM stats_channels WHERE channel_id = ?", (channel_id,))
        return bool(cur.rowcount)

    def list_channels(self, guild_id: int) -> list:
        return [dict(r) for r in self.db.fetchall(
            "SELECT * FROM stats_channels WHERE guild_id = ? ORDER BY channel_id", (guild_id,)
        )]

    def remember(self, channel_id: int, value: str, when: float):
        self.db.execute(
            "UPDATE stats_channels SET last_value = ?, last_update = ? WHERE channel_id = ?",
            (value, when, channel_id),
        )

    # --- calcul ---

    def compute(self, guild, entry: dict):
        """Valeur du compteur, ou None si le type est inconnu."""
        spec = KINDS.get(entry["kind"])
        if spec is None:
            return None
        role = guild.get_role(entry["role_id"]) if entry.get("role_id") else None
        try:
            return spec[1](guild, role)
        except Exception:
            return None

    def render(self, guild, entry: dict):
        """Nom du salon a appliquer, ou None si le compteur n'est pas calculable."""
        value = self.compute(guild, entry)
        if value is None:
            return None
        spec = KINDS[entry["kind"]]
        label = spec[0]
        if entry["kind"] == "role" and entry.get("role_id"):
            role = guild.get_role(entry["role_id"])
            if role is not None:
                label = role.name
        name = (entry["template"] or "{label} : {value}")
        name = name.replace("{label}", label).replace("{value}", str(value))
        name = name.replace("{server}", guild.name)
        return name[:100]

    # --- boucle ---

    async def refresh_guild(self, guild) -> int:
        """Met a jour les salons dont la valeur a change. Renvoie le nombre d'ecritures."""
        import time
        updated = 0
        for entry in self.list_channels(guild.id):
            channel = guild.get_channel(entry["channel_id"])
            if channel is None:
                self.remove_channel(entry["channel_id"])
                continue
            name = self.render(guild, entry)
            if name is None or name == entry["last_value"]:
                continue
            try:
                await channel.edit(name=name, reason="Salon de statistiques")
            except (discord.Forbidden, discord.HTTPException):
                continue
            self.remember(entry["channel_id"], name, time.time())
            updated += 1
        return updated

    async def _loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                for guild in self.bot.guilds:
                    await self.refresh_guild(guild)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[DEBUG] Erreur boucle salons stats: {exc}")
            await asyncio.sleep(UPDATE_INTERVAL_SECONDS)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def cog_unload(self):
        if self._task is not None:
            self._task.cancel()

    # --- commandes ---

    @commands.command()
    async def statschannel(self, ctx, action: str = None, channel_id: str = None,
                           kind: str = None, *, template: str = None):
        """,statschannel add <id_salon> <type> [modèle] | remove <id> | list | refresh"""
        if action is None or action.lower() == "list":
            entries = self.list_channels(ctx.guild.id)
            if not entries:
                await ctx.send(
                    "Aucun salon de statistiques. Types disponibles : "
                    + ", ".join(f"`{k}`" for k in KINDS)
                )
                return
            lines = []
            for entry in entries:
                channel = ctx.guild.get_channel(entry["channel_id"])
                current = self.render(ctx.guild, entry) or "?"
                lines.append(
                    f"• `{entry['kind']}` — {channel.name if channel else entry['channel_id']} "
                    f"→ *{current}*"
                )
            await ctx.send(embed=discord.Embed(
                title="📊 Salons de statistiques",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            ))
            return

        action = action.lower()
        if action == "add":
            if not channel_id or not channel_id.isdigit() or not kind:
                await ctx.send(
                    "Usage : `,statschannel add <id_salon> <type> [modèle]`\n"
                    "Types : " + ", ".join(f"`{k}`" for k in KINDS)
                )
                return
            kind = kind.lower()
            if kind not in KINDS:
                await ctx.send("Types : " + ", ".join(f"`{k}`" for k in KINDS))
                return
            channel = ctx.guild.get_channel(int(channel_id))
            if channel is None:
                await ctx.send("❌ Salon introuvable sur ce serveur.")
                return
            role_id = ctx.message.role_mentions[0].id if ctx.message.role_mentions else None
            if kind == "role" and role_id is None:
                await ctx.send("Pour le type `role`, mentionnez le rôle à compter.")
                return
            self.add_channel(ctx.guild.id, channel.id, kind,
                             template or "{label} : {value}", role_id)
            await self.refresh_guild(ctx.guild)
            await ctx.send(f"✅ **{channel.name}** affiche désormais le compteur `{kind}`.")
        elif action == "remove":
            if not channel_id or not channel_id.isdigit():
                await ctx.send("Usage : `,statschannel remove <id_salon>`")
                return
            if self.remove_channel(int(channel_id)):
                await ctx.send("✅ Salon retiré des statistiques.")
            else:
                await ctx.send("❌ Ce salon n'était pas suivi.")
        elif action == "refresh":
            updated = await self.refresh_guild(ctx.guild)
            await ctx.send(f"✅ {updated} salon(s) mis à jour.")
        else:
            await ctx.send("Actions : `add`, `remove`, `list`, `refresh`.")


def setup(bot, db):
    bot.add_cog(cmdstatschannels(bot, db))
