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

    # --- paliers de recompense ---

    def list_rewards(self, guild_id: int) -> list:
        rows = self.db.fetchall(
            "SELECT threshold, amount FROM invite_rewards WHERE guild_id = ? ORDER BY threshold",
            (guild_id,),
        )
        return [(row["threshold"], row["amount"]) for row in rows]

    def set_reward(self, guild_id: int, threshold: int, amount: float):
        self.db.execute(
            "INSERT INTO invite_rewards (guild_id, threshold, amount) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, threshold) DO UPDATE SET amount = excluded.amount",
            (guild_id, threshold, amount),
        )

    def remove_reward(self, guild_id: int, threshold: int) -> bool:
        cur = self.db.execute(
            "DELETE FROM invite_rewards WHERE guild_id = ? AND threshold = ?",
            (guild_id, threshold),
        )
        return bool(cur.rowcount)

    def pending_rewards(self, guild_id: int, user_id: int, invited: int) -> list:
        """Paliers atteints et pas encore verses a ce joueur."""
        claimed = {
            row["threshold"] for row in self.db.fetchall(
                "SELECT threshold FROM invite_reward_claims WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
        }
        return [
            (threshold, amount)
            for threshold, amount in self.list_rewards(guild_id)
            if invited >= threshold and threshold not in claimed
        ]

    def grant_invite_rewards(self, guild_id: int, user_id: int, invited: int) -> float:
        """Verse les paliers dus et renvoie le total credite."""
        total = 0.0
        for threshold, amount in self.pending_rewards(guild_id, user_id, invited):
            self.db.execute(
                "INSERT INTO balances (user_id, amount) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET amount = amount + excluded.amount",
                (user_id, amount),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO invite_reward_claims (guild_id, user_id, threshold) "
                "VALUES (?, ?, ?)",
                (guild_id, user_id, threshold),
            )
            self.db.log_transaction(
                guild_id, user_id, amount, "invite", f"palier {threshold} invitation(s)"
            )
            total += amount
        return total

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
                    await self._reward_inviter(guild, invite.inviter)
                return

    async def _reward_inviter(self, guild, inviter):
        stats = self.get_stats(guild.id, inviter.id)
        total = self.grant_invite_rewards(guild.id, inviter.id, stats["invited"])
        if not total:
            return
        channel = guild.system_channel
        if channel is not None:
            try:
                await channel.send(
                    f"🎉 {inviter.mention} atteint **{stats['invited']}** invitation(s) "
                    f"et reçoit **{total:.0f}** pièces !"
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.command()
    async def inviterewards(self, ctx, action: str = "list", threshold: int = None,
                            amount: float = None):
        """,inviterewards list | set <invitations> <montant> | remove <invitations>"""
        action = action.lower()
        if action == "set" and threshold is not None and amount is not None:
            self.set_reward(ctx.guild.id, threshold, amount)
            await ctx.send(f"✅ Palier **{threshold} invitation(s)** → **{amount:.0f}** pièces.")
            return
        if action == "remove" and threshold is not None:
            if self.remove_reward(ctx.guild.id, threshold):
                await ctx.send(f"✅ Palier **{threshold}** supprimé.")
            else:
                await ctx.send("❌ Ce palier n'existe pas.")
            return

        rewards = self.list_rewards(ctx.guild.id)
        if not rewards:
            await ctx.send(
                "Aucun palier configuré. Exemple : `,inviterewards set 5 500` "
                "(5 invitations → 500 pièces)."
            )
            return
        lines = "\n".join(f"↦ {t} = {a:.0f}" for t, a in rewards)
        await ctx.send(embed=discord.Embed(
            title="Récompenses d'invitation", description=lines,
            color=discord.Color.blurple(),
        ))

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
