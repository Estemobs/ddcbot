import asyncio
import random
import time

import discord
from discord.ext import commands


GIVEAWAY_EMOJI = "🎉"
END_CHECK_INTERVAL = 30


class cmdanim(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._end_task = None

    # --- persistance ---

    def create_giveaway(self, guild_id, channel_id, message_id, prize, ends_at, host_id) -> int:
        self.db.execute(
            "INSERT INTO giveaways (guild_id, channel_id, message_id, prize, ends_at, host_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, channel_id, message_id, prize, ends_at, host_id),
        )
        row = self.db.fetchone(
            "SELECT id FROM giveaways WHERE message_id = ?", (message_id,)
        )
        return row["id"]

    def get_active_giveaway_by_guild(self, guild_id: int):
        row = self.db.fetchone(
            "SELECT id, channel_id, message_id, prize, ends_at, host_id "
            "FROM giveaways WHERE guild_id = ? AND ended = 0 LIMIT 1",
            (guild_id,),
        )
        return self._row_to_giveaway(row)

    def get_active_giveaway_by_message(self, message_id: int):
        row = self.db.fetchone(
            "SELECT id, guild_id, channel_id, message_id, prize, ends_at, host_id "
            "FROM giveaways WHERE message_id = ? AND ended = 0 LIMIT 1",
            (message_id,),
        )
        return self._row_to_giveaway(row)

    def list_expired_giveaways(self, now: float):
        rows = self.db.fetchall(
            "SELECT id, guild_id, channel_id, message_id, prize, ends_at, host_id "
            "FROM giveaways WHERE ended = 0 AND ends_at <= ?",
            (now,),
        )
        return [self._row_to_giveaway(row) for row in rows]

    def _row_to_giveaway(self, row):
        if row is None:
            return None
        return dict(row)

    def add_entry(self, giveaway_id: int, user_id: int):
        self.db.execute(
            "INSERT OR IGNORE INTO giveaway_entries (giveaway_id, user_id) VALUES (?, ?)",
            (giveaway_id, user_id),
        )

    def list_entries(self, giveaway_id: int) -> list:
        rows = self.db.fetchall(
            "SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?", (giveaway_id,)
        )
        return [row["user_id"] for row in rows]

    def mark_ended(self, giveaway_id: int):
        self.db.execute("UPDATE giveaways SET ended = 1 WHERE id = ?", (giveaway_id,))

    # --- boucle de fin automatique ---

    @commands.Cog.listener()
    async def on_ready(self):
        if self._end_task is None or self._end_task.done():
            self._end_task = asyncio.create_task(self._end_loop())

    async def _end_loop(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                await self._finish_expired()
            except Exception:
                pass
            await asyncio.sleep(END_CHECK_INTERVAL)

    async def _finish_expired(self):
        now = time.time()
        for giveaway in self.list_expired_giveaways(now):
            await self._finish_giveaway(giveaway)

    async def _finish_giveaway(self, giveaway: dict):
        self.mark_ended(giveaway["id"])
        channel = self.bot.get_channel(giveaway["channel_id"])
        if channel is None:
            return
        entries = self.list_entries(giveaway["id"])
        if not entries:
            await channel.send(
                f"{GIVEAWAY_EMOJI} Giveaway **{giveaway['prize']}** terminé sans participant."
            )
            return
        winner_id = random.choice(entries)
        try:
            winner = await self.bot.fetch_user(winner_id)
            winner_label = winner.mention
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            winner_label = f"<@{winner_id}>"
        await channel.send(
            f"{GIVEAWAY_EMOJI} Giveaway **{giveaway['prize']}** terminé ! "
            f"Félicitations **{winner_label}** !"
        )

    # --- commandes ---

    @commands.command()
    async def gstart(self, ctx, duration: int, *, prize: str):
        if self.get_active_giveaway_by_guild(ctx.guild.id) is not None:
            return await ctx.send("Il y a déjà un giveaway en cours sur ce serveur.")
        if duration <= 0:
            return await ctx.send("La durée doit être supérieure à 0 secondes.")

        ends_at = time.time() + duration
        embed = discord.Embed(
            title=f"{GIVEAWAY_EMOJI} Giveaway : {prize}",
            description=f"Réagissez avec {GIVEAWAY_EMOJI} pour participer !",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Fin du giveaway",
            value=f"<t:{int(ends_at)}:R>",
            inline=False,
        )
        embed.set_footer(text=f"Organisé par {ctx.author.display_name}")

        message = await ctx.send(embed=embed)
        await message.add_reaction(GIVEAWAY_EMOJI)
        self.create_giveaway(ctx.guild.id, ctx.channel.id, message.id, prize, ends_at, ctx.author.id)
        await ctx.send(f"Giveaway démarré pour {duration} secondes ! Prix : {prize}")

    @commands.command()
    async def gend(self, ctx):
        giveaway = self.get_active_giveaway_by_guild(ctx.guild.id)
        if giveaway is None:
            return await ctx.send("Il n'y a pas de giveaway en cours sur ce serveur.")
        await self._finish_giveaway(giveaway)

    @commands.command()
    async def gcancel(self, ctx):
        giveaway = self.get_active_giveaway_by_guild(ctx.guild.id)
        if giveaway is None:
            return await ctx.send("Il n'y a pas de giveaway en cours sur ce serveur.")
        self.mark_ended(giveaway["id"])
        await ctx.send(f"Giveaway annulé ! Le prix était {giveaway['prize']}.")

    # --- participation par réaction ---

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        if getattr(payload.emoji, "name", None) != GIVEAWAY_EMOJI:
            return
        giveaway = self.get_active_giveaway_by_message(payload.message_id)
        if giveaway is None:
            return
        self.add_entry(giveaway["id"], payload.user_id)


def setup(bot, db):
    bot.add_cog(cmdanim(bot, db))
