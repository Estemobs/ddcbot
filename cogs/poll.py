import asyncio
import json
import re
import time

import discord
from discord.ext import commands


class cmdpoll(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._active_polls = {}

    def _ensure_poll_tables(self):
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS polls ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "guild_id INTEGER,"
            "message_id INTEGER,"
            "question TEXT,"
            "options_json TEXT,"
            "created_at REAL DEFAULT (unixepoch()),"
            "ended INTEGER DEFAULT 0)"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_polls_guild ON polls(guild_id)"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_polls_message ON polls(message_id)"
        )

    # --- Configuration ---

    def create_poll(self, guild_id: int, message_id: int, question: str, options: list):
        options_json = json.dumps(options)
        self.db.execute(
            "INSERT INTO polls (guild_id, message_id, question, options_json) "
            "VALUES (?, ?, ?, ?)",
            (guild_id, message_id, question, options_json),
        )

    def get_active_polls(self, guild_id: int) -> list:
        rows = self.db.fetchall(
            "SELECT id, message_id, question, options_json FROM polls WHERE guild_id = ? AND ended = 0",
            (guild_id,),
        )
        polls = []
        for row in rows:
            try:
                options = json.loads(row["options_json"])
                polls.append({
                    "id": row["id"],
                    "message_id": row["message_id"],
                    "question": row["question"],
                    "options": options,
                })
            except (json.JSONDecodeError, Exception):
                pass
        return polls

    def end_poll(self, poll_id: int):
        self.db.execute("UPDATE polls SET ended = 1 WHERE id = ?", (poll_id,))

    # --- Commandes ---

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def poll(self, ctx, *, poll_data: str = None):
        """Créer un sondage.
        Usage: ,poll \"Question\" option1 | option2 | option3
        """
        if poll_data is None:
            return await ctx.send(
                "Usage: `,poll \"Question\" option1 | option2 | option3`"
            )

        # Parse: "Question" option1 | option2 | option3
        match = re.match(r'^"(.+)"\s+(.+)$', poll_data)
        if not match:
            return await ctx.send(
                "Format invalide. Utilisez: `,poll \"Question\" option1 | option2 | option3`"
            )

        question = match.group(1)
        options_str = match.group(2)
        options = [opt.strip() for opt in options_str.split("|") if opt.strip()]

        if len(options) < 2:
            return await ctx.send("Un sondage doit avoir au moins 2 options.")

        if len(options) > 10:
            return await ctx.send("Un sondage ne peut pas avoir plus de 10 options.")

        # Send the poll embed
        embed = discord.Embed(
            title="📊 Sondage",
            description=question,
            color=discord.Color.blurple(),
            timestamp=ctx.message.created_at,
        )
        embed.set_footer(text=f"Sondage créé par {ctx.author.display_name}")

        # Add reactions for each option (using numbers or letters)
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        message = await ctx.send(embed=embed)
        
        for i, option in enumerate(options):
            if i < len(emojis):
                await message.add_reaction(emojis[i])
                option += f" {emojis[i]}"

        # Store the poll in database
        self.create_poll(ctx.guild.id, message.id, question, options)

        # Store message ID for timeout
        self._active_polls[message.id] = {
            "guild_id": ctx.guild.id,
            "question": question,
            "options": options,
            "end_time": time.time() + 86400,  # 24h max
        }

        # Auto-end after 24h or when all voted
        asyncio.create_task(self._poll_timeout(message.id))

    async def _poll_timeout(self, message_id: int):
        await asyncio.sleep(86400)  # 24 hours
        # End the poll
        rows = self.db.fetchall("SELECT guild_id, message_id FROM polls WHERE message_id = ?", (message_id,))
        for row in rows:
            self.end_poll(row["id"])
        # Remove from active
        self._active_polls.pop(message_id, None)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def pollresults(self, ctx, message_id: int = None):
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        """Voir les résultats d'un sondage."""
        if message_id is None:
            # Try to find the latest poll in this channel
            messages = ctx.message.channel.history(limit=5)
            async for msg in messages:
                if hasattr(msg, 'embeds') and msg.embeds:
                    # Check if this is a poll embed
                    embed = msg.embeds[0]
                    if embed.title == "📊 Sondage":
                        message_id = msg.id
                        break

            if message_id is None:
                return await ctx.send("Aucun sondage trouvé dans ce canal. Utilisez `,pollresults <message_id>`.")

        # Get poll from database
        row = self.db.fetchone(
            "SELECT question, options_json FROM polls WHERE message_id = ? AND ended = 0",
            (message_id,),
        )
        if row is None:
            # Check ended polls
            row = self.db.fetchone(
                "SELECT question, options_json FROM polls WHERE message_id = ?",
                (message_id,),
            )
            if row is None:
                return await ctx.send("Sondage introuvable.")
            # Show ended poll results
            ended = True
        else:
            ended = False

        try:
            options = json.loads(row["options_json"])
        except (json.JSONDecodeError, Exception):
            return await ctx.send("Erreur lecture du sondage.")

        # Count reactions from the message
        try:
            msg = await ctx.fetch_message(message_id)
            reactions = msg.reactions
        except (discord.NotFound, discord.HTTPException):
            reactions = []

        # Build results
        results = []
        for i, option in enumerate(options):
            votes = 0
            for reaction in reactions:
                if str(reaction.emoji) in ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]:
                    # Check if this emoji matches option i+1
                    if reaction.emoji == emojis[i] if i < len(emojis) else False:
                        votes = reaction.count
            results.append({"option": option, "votes": votes, "percent": 0})

        # Calculate percentages
        total_votes = sum(r["votes"] for r in results)
        if total_votes > 0:
            for r in results:
                r["percent"] = round(r["votes"] / total_votes * 100, 1)

        # Build response
        status = "Terminé" if ended else "En cours"
        embed = discord.Embed(
            title=f"📊 Sondage - {status}",
            description=row["question"],
            color=discord.Color.gold() if ended else discord.Color.blurple(),
        )
        embed.set_footer(text=f"Total votes: {total_votes}")

        lines = []
        for r in results:
            bar = "▓" * int(r["percent"]) + "░" * (10 - int(r["percent"]))
            lines.append(f"{r['option']}: {r['votes']} vote(s) ({r['percent']}%) |[{bar}]|")

        embed.add_field(name="Résultats", value="\n".join(lines) or "Aucun vote", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def pollclose(self, ctx, message_id: int = None):
        """Clôturer un sondage prématurément."""
        if message_id is None:
            # Try to find in channel
            messages = ctx.message.channel.history(limit=5)
            async for msg in messages:
                if hasattr(msg, 'embeds') and msg.embeds:
                    embed = msg.embeds[0]
                    if embed.title == "📊 Sondage":
                        message_id = msg.id
                        break

        if message_id is None:
            return await ctx.send("Usage: `,pollclose <message_id>`")

        self.end_poll(message_id)
        # Remove from active
        self._active_pops.get(message_id, None)
        await ctx.send(f"✅ Sondage {message_id} clôturé.")

    def setup_active_poll(self, message_id: int, poll_data: dict):
        """Enregistrer un poll actif depuis l'extérieur."""
        self._active_polls[message_id] = poll_data


def setup(bot, db):
    cog = cmdpoll(bot, db)
    cog._ensure_poll_tables()
    bot.add_cog(cog)