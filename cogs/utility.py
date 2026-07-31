import asyncio
import time

import discord
from discord.ext import commands


class cmdutility(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._reminder_task = None

    # --- rappels persistants ---

    def add_reminder(self, user_id, guild_id, channel_id, message, remind_at) -> int:
        self.db.execute(
            "INSERT INTO reminders (user_id, guild_id, channel_id, message, remind_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, guild_id, channel_id, message, remind_at),
        )
        row = self.db.fetchone(
            "SELECT id FROM reminders WHERE user_id = ? AND remind_at = ? ORDER BY id DESC LIMIT 1",
            (user_id, remind_at),
        )
        return row["id"] if row else 0

    def list_user_reminders(self, user_id: int):
        return self.db.fetchall(
            "SELECT id, channel_id, message, remind_at FROM reminders "
            "WHERE user_id = ? AND remind_at > ? ORDER BY remind_at",
            (user_id, time.time()),
        )

    def delete_reminder(self, reminder_id: int) -> bool:
        cursor = self.db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        return cursor.rowcount > 0

    def list_due_reminders(self, now: float, limit: int = 50):
        return self.db.fetchall(
            "SELECT id, user_id, guild_id, channel_id, message, remind_at "
            "FROM reminders WHERE remind_at <= ? ORDER BY remind_at LIMIT ?",
            (now, limit),
        )

    @commands.Cog.listener()
    async def on_ready(self):
        if self._reminder_task is None or self._reminder_task.done():
            self._reminder_task = asyncio.create_task(self._reminder_loop())

    async def _reminder_loop(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                await self._fire_due_reminders()
            except Exception:
                pass
            await asyncio.sleep(15)

    async def _fire_due_reminders(self):
        now = time.time()
        for reminder in self.list_due_reminders(now):
            self.delete_reminder(reminder["id"])
            message = reminder["message"]
            if reminder["guild_id"] and reminder["channel_id"]:
                guild = self.bot.get_guild(reminder["guild_id"])
                channel = guild.get_channel(reminder["channel_id"]) if guild else None
                if channel:
                    try:
                        await channel.send(f"<@{reminder['user_id']}> ⏰ **Rappel:** {message}")
                        continue
                    except (discord.Forbidden, discord.HTTPException):
                        pass
            user = self.bot.get_user(reminder["user_id"])
            if user:
                try:
                    await user.send(f"⏰ **Rappel:** {message}")
                except (discord.Forbidden, discord.HTTPException):
                    pass

    @commands.command()
    async def rmd(self, ctx, duree: str, *, message: str):
        temps = duree[:-1]
        unite = duree[-1]
        if not temps.isnumeric():
            await ctx.send("Format du rappel incorrect, veuillez utiliser les unités de temps telles que `d, h, m, s` pour votre rappel. Exemple : `,rmd 30m je vais dormir.`")
            return
        temps = int(temps)
        unites = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        if unite not in unites:
            await ctx.send("Format du rappel incorrect, veuillez utiliser les unités de temps telles que `d, h, m, s` pour votre rappel. Exemple : `,rmd 30m je vais dormir.`")
            return
        retard = temps * unites[unite]
        remind_at = time.time() + retard
        self.add_reminder(ctx.author.id, ctx.guild.id if ctx.guild else None, ctx.channel.id, message, remind_at)
        await ctx.send(f"Rappel enregistré, je vous enverrai **{message}** dans **{temps}{unite}.**")

    @commands.command()
    async def reminders(self, ctx):
        rows = self.list_user_reminders(ctx.author.id)
        if not rows:
            await ctx.send("Vous n'avez aucun rappel en attente.")
            return
        lines = []
        for row in rows:
            remaining = int(row["remind_at"] - time.time())
            minutes, seconds = divmod(remaining, 60)
            hours, minutes = divmod(minutes, 60)
            if hours:
                delay = f"{hours}h{minutes}m"
            else:
                delay = f"{minutes}m{seconds}s"
            lines.append(f"**[{row['id']}]** dans {delay} : {row['message']}")
        embed = discord.Embed(
            title="Rappels en attente",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def rmcancel(self, ctx, reminder_id: int):
        row = self.db.fetchone(
            "SELECT id FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, ctx.author.id)
        )
        if row is None:
            await ctx.send("Aucun rappel avec cet ID pour vous.")
            return
        self.delete_reminder(reminder_id)
        await ctx.send(f"Rappel [{reminder_id}] annulé.")

    # --- autres utilitaires ---

    @commands.command()
    async def role_id(self, ctx, *, role_name):
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if role is not None:
            await ctx.send(f"L'ID du rôle {role_name} est : {role.id}")
        else:
            await ctx.send(f"Le rôle {role_name} n'existe pas sur ce serveur.")

    @commands.command()
    async def role_name(self, ctx, role_id: int):
        role = discord.utils.get(ctx.guild.roles, id=role_id)
        if role is not None:
            await ctx.send(f"Le nom du rôle avec l'ID {role_id} est : {role.name}")
        else:
            await ctx.send(f"Aucun rôle n'a l'ID {role_id} sur ce serveur.")

    @commands.command()
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        em = discord.Embed(description=f'● Voici la photo de profil de {member}', color=0x04ff00)
        em.set_image(url=member.display_avatar.url)
        await ctx.send(embed=em)

    @commands.command()
    async def serverpicture(self, ctx):
        embed = discord.Embed(title="Server Icon", color=discord.Color.green())
        if ctx.guild.icon:
            embed.set_image(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)


def setup(bot, db):
    bot.add_cog(cmdutility(bot, db))
