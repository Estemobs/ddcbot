import time

import discord
from discord.ext import commands

from cogs.i18n import t

LEVEL_FACTOR = 100

DEFAULT_XP_CONFIG = {
    "enabled": True,
    "xp_per_message": 15,
    "cooldown_seconds": 60,
    "announce_channel_id": None,
}


def level_from_xp(xp: int) -> int:
    return xp // LEVEL_FACTOR + 1


def xp_in_level(xp: int) -> int:
    return xp % LEVEL_FACTOR


class cmdleveling(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._last_xp = {}
        self._cfg_initialized = set()

    def get_xp(self, user_id: int) -> int:
        row = self.db.fetchone("SELECT xp FROM levels WHERE user_id = ?", (user_id,))
        return row["xp"] if row else 0

    def add_xp(self, user_id: int, amount: int) -> int:
        self.db.execute(
            "INSERT INTO levels (user_id, xp) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET xp = xp + excluded.xp",
            (user_id, amount),
        )
        return self.get_xp(user_id)

    def get_config(self, guild_id: int) -> dict:
        if guild_id not in self._cfg_initialized:
            self._cfg_initialized.add(guild_id)
            self.db.execute(
                "INSERT OR IGNORE INTO xp_config "
                "(guild_id, enabled, xp_per_message, cooldown_seconds, announce_channel_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    guild_id,
                    int(DEFAULT_XP_CONFIG["enabled"]),
                    DEFAULT_XP_CONFIG["xp_per_message"],
                    DEFAULT_XP_CONFIG["cooldown_seconds"],
                    DEFAULT_XP_CONFIG["announce_channel_id"],
                ),
            )
        row = self.db.fetchone(
            "SELECT enabled, xp_per_message, cooldown_seconds, announce_channel_id "
            "FROM xp_config WHERE guild_id = ?",
            (guild_id,),
        )
        return {
            "enabled": bool(row["enabled"]),
            "xp_per_message": row["xp_per_message"],
            "cooldown_seconds": row["cooldown_seconds"],
            "announce_channel_id": row["announce_channel_id"],
        }

    def set_config(self, guild_id: int, **fields):
        self.get_config(guild_id)
        assignments = []
        values = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(int(value) if isinstance(value, bool) else value)
        values.append(guild_id)
        self.db.execute(f"UPDATE xp_config SET {', '.join(assignments)} WHERE guild_id = ?", values)

    # --- gain d'XP ---

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return
        if not message.content or message.content.startswith(","):
            return
        cfg = self.get_config(message.guild.id)
        if not cfg["enabled"]:
            return
        key = (message.guild.id, message.author.id)
        now = time.time()
        if now - self._last_xp.get(key, 0) < cfg["cooldown_seconds"]:
            return
        self._last_xp[key] = now
        old_xp = self.get_xp(message.author.id)
        new_xp = self.add_xp(message.author.id, cfg["xp_per_message"])
        if level_from_xp(new_xp) > level_from_xp(old_xp):
            target = self.bot.get_channel(cfg["announce_channel_id"]) if cfg["announce_channel_id"] else message.channel
            if target:
                await target.send(
                    t(
                        self.db,
                        "xp_leveled_up",
                        message.guild.id,
                        message.author.id,
                        mention=message.author.mention,
                        level=level_from_xp(new_xp),
                    )
                )

    # --- commandes ---

    @commands.command()
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        cfg = self.get_config(ctx.guild.id)
        xp = self.get_xp(member.id)
        level = level_from_xp(xp)
        in_level = xp_in_level(xp)

        server_rank = 0
        for guild_member in ctx.guild.members:
            if self.get_xp(guild_member.id) > xp:
                server_rank += 1
        server_rank += 1

        global_rank = 0
        rows = self.db.fetchall("SELECT user_id, xp FROM levels ORDER BY xp DESC")
        for i, row in enumerate(rows, start=1):
            if row["user_id"] == member.id:
                global_rank = i
                break

        embed = discord.Embed(
            title=t(self.db, "rank_title", ctx.guild.id, ctx.author.id, member=member.display_name),
            color=discord.Color.green(),
        )
        embed.add_field(name=t(self.db, "rank_field_level", ctx.guild.id, ctx.author.id), value=str(level), inline=True)
        embed.add_field(name=t(self.db, "rank_field_xp", ctx.guild.id, ctx.author.id), value=f"{in_level}/{LEVEL_FACTOR}", inline=True)
        embed.add_field(name=t(self.db, "rank_field_server_rank", ctx.guild.id, ctx.author.id), value=f"#{server_rank}", inline=True)
        embed.add_field(name=t(self.db, "rank_field_global_rank", ctx.guild.id, ctx.author.id), value=f"#{global_rank if global_rank else '—'}", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command()
    async def levels(self, ctx):
        cfg = self.get_config(ctx.guild.id)
        if not cfg["enabled"]:
            await ctx.send(t(self.db, "xp_not_enabled", ctx.guild.id, ctx.author.id))
            return
        rows = self.db.fetchall("SELECT user_id, xp FROM levels ORDER BY xp DESC LIMIT 10")
        embed = discord.Embed(title="🏆 Leaderboard XP", color=discord.Color.gold())
        if not rows:
            embed.description = "Aucune donnée XP."
        for i, row in enumerate(rows, start=1):
            member = ctx.guild.get_member(row["user_id"])
            if member:
                embed.add_field(
                    name=f"{i}. {member.display_name}",
                    value=f"Niveau {level_from_xp(row['xp'])} — {row['xp']} XP",
                    inline=False,
                )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def xptoggle(self, ctx):
        cfg = self.get_config(ctx.guild.id)
        self.set_config(ctx.guild.id, enabled=not cfg["enabled"])
        state = "on" if not cfg["enabled"] else "off"
        await ctx.send(t(self.db, "xp_config_saved", ctx.guild.id, ctx.author.id) + f" ({state})")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def xpconfig(self, ctx, xp_per_message: int = None, cooldown_seconds: int = None):
        """Configure l'XP par message et le cooldown (secondes). Sans argument : affiche la config."""
        if xp_per_message is not None and cooldown_seconds is not None:
            self.set_config(ctx.guild.id, xp_per_message=max(1, xp_per_message), cooldown_seconds=max(0, cooldown_seconds))
            await ctx.send(t(self.db, "xp_config_saved", ctx.guild.id, ctx.author.id))
            return
        cfg = self.get_config(ctx.guild.id)
        announce = self.bot.get_channel(cfg["announce_channel_id"]) if cfg["announce_channel_id"] else None
        embed = discord.Embed(
            title=t(self.db, "xp_config_title", ctx.guild.id, ctx.author.id),
            color=discord.Color.blurple(),
        )
        embed.add_field(name=t(self.db, "xp_config_enabled", ctx.guild.id, ctx.author.id), value="✅" if cfg["enabled"] else "❌", inline=True)
        embed.add_field(name=t(self.db, "xp_config_xp_per_message", ctx.guild.id, ctx.author.id), value=str(cfg["xp_per_message"]), inline=True)
        embed.add_field(name=t(self.db, "xp_config_cooldown", ctx.guild.id, ctx.author.id), value=f"{cfg['cooldown_seconds']}s", inline=True)
        announce_label = f"#{announce.name}" if announce else t(self.db, "xp_config_none", ctx.guild.id, ctx.author.id)
        embed.add_field(name=t(self.db, "xp_config_announce", ctx.guild.id, ctx.author.id), value=announce_label, inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def xpset(self, ctx, member: discord.Member, xp: int):
        """Définit l'XP d'un membre (admin)."""
        self.db.execute(
            "INSERT INTO levels (user_id, xp) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET xp = excluded.xp",
            (member.id, max(0, xp)),
        )
        await ctx.send(f"XP de {member.mention} défini sur **{max(0, xp)}**.")


def setup(bot, db):
    bot.add_cog(cmdleveling(bot, db))
