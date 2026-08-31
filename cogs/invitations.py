"""Suivi des invitations Discord (intègre ProjetsDivers/invitation.py).

Compte les membres qui rejoignent/partent et associe chaque arrivée à
l'invitation utilisée (via la comparaison des `guild.invites`). La persistance
se fait en SQLite (table `invites`, par serveur et par utilisateur) : les
compteurs ne sont plus volatils comme dans le prototype original.

Commandes :
  ,invitations [membre] — nombre d'invitations d'un membre (ou total serveur)
  ,topinvitations [n]   — classement des meilleurs invitateurs
  ,invleft <membre>     — marque un invité comme ayant quitté le serveur
"""

from __future__ import annotations

import discord
from discord.ext import commands

from cogs.i18n import t


class cmdinvitations(commands.Cog):
    """Cog de suivi des invitations."""

    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._invite_cache: dict[int, dict[str, int]] = {}

    # --- accès données ---

    def get_stats(self, guild_id: int, user_id: int) -> dict:
        row = self.db.fetchone(
            "SELECT invited, left FROM invites WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        if row is None:
            return {"invited": 0, "left": 0}
        return {"invited": row["invited"], "left": row["left"]}

    def set_stats(self, guild_id: int, user_id: int, invited: int, left: int) -> None:
        self.db.execute(
            "INSERT INTO invites (guild_id, user_id, invited, left) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
            " invited=excluded.invited, left=excluded.left",
            (guild_id, user_id, invited, left),
        )

    def add_invite(self, guild_id: int, user_id: int, delta: int = 1) -> None:
        stats = self.get_stats(guild_id, user_id)
        self.set_stats(guild_id, user_id, max(0, stats["invited"] + delta), stats["left"])

    def add_left(self, guild_id: int, user_id: int, delta: int = 1) -> None:
        stats = self.get_stats(guild_id, user_id)
        self.set_stats(guild_id, user_id, stats["invited"], max(0, stats["left"] + delta))

    def top_inviters(self, guild_id: int, limit: int = 5) -> list[tuple[int, dict]]:
        rows = self.db.fetchall(
            "SELECT user_id, invited, left FROM invites "
            "WHERE guild_id = ? AND invited > 0 ORDER BY invited DESC LIMIT ?",
            (guild_id, limit),
        )
        return [(row["user_id"], {"invited": row["invited"], "left": row["left"]}) for row in rows]

    # --- événements ---

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try:
                self._invite_cache[guild.id] = {
                    invite.code: invite.uses for invite in await guild.invites()
                }
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        cached = self._invite_cache.get(guild.id)
        if cached is None:
            return
        try:
            invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return
        current = {invite.code: invite.uses for invite in invites}
        self._invite_cache[guild.id] = current
        for invite in invites:
            if invite.uses > cached.get(invite.code, 0):
                if invite.inviter is not None and not invite.inviter.bot:
                    self.add_invite(guild.id, invite.inviter.id)
                return

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild:
            cache = self._invite_cache.setdefault(invite.guild.id, {})
            cache[invite.code] = invite.uses

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild:
            self._invite_cache.get(invite.guild.id, {}).pop(invite.code, None)

    # --- commandes ---

    @commands.command()
    async def invitations(self, ctx, member: discord.Member = None):
        """Affiche le nombre d'invitations d'un membre (ou le total du serveur)."""
        if member is None:
            rows = self.db.fetchall(
                "SELECT COALESCE(SUM(invited), 0) AS total, COALESCE(SUM(left), 0) AS lefts "
                "FROM invites WHERE guild_id = ?",
                (ctx.guild.id,),
            )
            row = rows[0] if rows else None
            total = row["total"] if row else 0
            lefts = row["lefts"] if row else 0
            embed = discord.Embed(
                title=t(self.db, "inv_total_title", ctx.guild.id, ctx.author.id),
                color=discord.Color.green(),
            )
            embed.add_field(
                name=t(self.db, "inv_total", ctx.guild.id, ctx.author.id),
                value=str(total),
                inline=True,
            )
            embed.add_field(
                name=t(self.db, "inv_left", ctx.guild.id, ctx.author.id),
                value=str(lefts),
                inline=True,
            )
            await ctx.send(embed=embed)
            return

        stats = self.get_stats(ctx.guild.id, member.id)
        remained = stats["invited"] - stats["left"]
        embed = discord.Embed(
            title=t(self.db, "inv_member_title", ctx.guild.id, ctx.author.id),
            color=discord.Color.green(),
        )
        embed.add_field(
            name=t(self.db, "inv_member", ctx.guild.id, ctx.author.id),
            value=member.display_name,
            inline=True,
        )
        embed.add_field(
            name=t(self.db, "inv_invited", ctx.guild.id, ctx.author.id),
            value=str(stats["invited"]),
            inline=True,
        )
        embed.add_field(
            name=t(self.db, "inv_remained", ctx.guild.id, ctx.author.id),
            value=str(max(0, remained)),
            inline=True,
        )
        embed.add_field(
            name=t(self.db, "inv_left", ctx.guild.id, ctx.author.id),
            value=str(stats["left"]),
            inline=True,
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def topinvitations(self, ctx, n: int = 5):
        """Classement des meilleurs invitateurs du serveur."""
        n = max(1, min(n, 20))
        top = self.top_inviters(ctx.guild.id, n)
        if not top:
            await ctx.send(t(self.db, "inv_no_data", ctx.guild.id, ctx.author.id))
            return
        lines = []
        for i, (user_id, stats) in enumerate(top, start=1):
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"<@{user_id}>"
            lines.append(f"{i}. {name} — {stats['invited']}")
        embed = discord.Embed(
            title=t(self.db, "inv_top_title", ctx.guild.id, ctx.author.id),
            description="\n".join(lines),
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def invleft(self, ctx, member: discord.Member):
        """Marque un invité comme ayant quitté le serveur (admin)."""
        self.add_left(ctx.guild.id, member.id)
        await ctx.send(
            t(self.db, "inv_marked_left", ctx.guild.id, ctx.author.id, member=member.mention)
        )


def setup(bot, db):
    bot.add_cog(cmdinvitations(bot, db))
