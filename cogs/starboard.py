import asyncio
import json
import time

import discord
from discord.ext import commands

STARBOARD_EMOJI = "🌟"


class cmdstarboard(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._reaction_task = None
        self._process_task = None

    def _ensure_starboard_tables(self):
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS starboard_config ("
            "guild_id INTEGER PRIMARY KEY,"
            "channel_id INTEGER,"
            "emoji TEXT DEFAULT '🌟',"
            "min_stars INTEGER DEFAULT 5,"
            "include_bot_messages INTEGER DEFAULT 0,"
            "exclude_pinned INTEGER DEFAULT 1"
            ")"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS starboard_entries ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "guild_id INTEGER,"
            "message_id INTEGER,"
            "source_message_id INTEGER,"
            "stars INTEGER DEFAULT 0,"
            "forwarded_message_id INTEGER,"
            "UNIQUE(guild_id, message_id))"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_starboard_guild ON starboard_config(guild_id)"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_starboard_entries_guild ON starboard_entries(guild_id)"
        )

    def set_starboard_channel(self, guild_id: int, channel_id: int, emoji: str = "🌟", min_stars: int = 5):
        self.db.execute(
            "INSERT INTO starboard_config (guild_id, channel_id, emoji, min_stars) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET "
            "channel_id=excluded.channel_id, emoji=excluded.emoji, min_stars=excluded.min_stars",
            (guild_id, channel_id, emoji, min_stars),
        )

    def get_starboard_config(self, guild_id: int):
        row = self.db.fetchone(
            "SELECT * FROM starboard_config WHERE guild_id = ?", (guild_id,)
        )
        if row:
            return dict(row)
        return None

    def set_starboard_settings(
        self,
        guild_id: int,
        emoji: str = "🌟",
        min_stars: int = 5,
        include_bot_messages: int = 0,
        exclude_pinned: int = 1,
    ):
        self.db.execute(
            "INSERT INTO starboard_config (guild_id, emoji, min_stars, include_bot_messages, exclude_pinned) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET "
            "emoji=excluded.emoji, min_stars=excluded.min_stars, "
            "include_bot_messages=excluded.include_bot_messages, "
            "exclude_pinned=excluded.exclude_pinned",
            (guild_id, emoji, min_stars, include_bot_messages, exclude_pinned),
        )

    def is_starboard_message(self, message: discord.Message) -> bool:
        if message.guild is None:
            return False
        cfg = self.get_starboard_message_config(message.guild.id, message.id)
        return cfg is not None

    def get_starboard_message_config(self, guild_id: int, message_id: int):
        row = self.db.fetchone(
            "SELECT * FROM starboard_entries WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        )
        return row

    def add_star_to_message(self, guild_id: int, message_id: int, user_id: int):
        existing = self.db.fetchone(
            "SELECT stars FROM starboard_entries WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        )
        if existing is None:
            self.db.execute(
                "INSERT INTO starboard_entries (guild_id, message_id, stars) VALUES (?, ?, 1)",
                (guild_id, message_id),
            )
            new_stars = 1
        else:
            new_stars = existing["stars"] + 1
            self.db.execute(
                "UPDATE starboard_entries SET stars = ? WHERE guild_id = ? AND message_id = ?",
                (new_stars, guild_id, message_id),
            )
        return new_stars

    def remove_star_from_message(self, guild_id: int, message_id: int):
        self.db.execute(
            "DELETE FROM starboard_entries WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        )

    def get_message_stars(self, guild_id: int, message_id: int) -> int:
        row = self.db.fetchone(
            "SELECT stars FROM starboard_entries WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        )
        return row["stars"] if row else 0

    async def forward_to_starboard(self, message: discord.Message, stars: int):
        guild_id = message.guild.id
        cfg = self.get_starboard_config(guild_id)
        if cfg is None:
            return

        channel = message.guild.get_channel(cfg["channel_id"])
        if channel is None:
            self.set_starboard_channel(guild_id, 0)
            return

        emoji = cfg["emoji"]
        min_stars = cfg["min_stars"]
        include_bot = cfg["include_bot_messages"]
        exclude_pinned = cfg["exclude_pinned"]

        if not include_bot and message.author.bot:
            return
        if exclude_pinned and message.pinned:
            return
        if stars < min_stars:
            return

        existing = self.get_starboard_message_config(guild_id, message.id)
        if existing and existing["forwarded_message_id"]:
            try:
                forwarded = await message.guild.get_channel(
                    int(existing["forwarded_message_id"])
                ).fetch_message(int(existing["forwarded_message_id"]))
                if forwarded is None:
                    await self._create_starboard_entry(message, channel, stars)
            except (discord.NotFound, discord.HTTPException):
                await self._create_starboard_entry(message, channel, stars)
            return

        await self._create_starboard_entry(message, channel, stars)

    async def _create_starboard_entry(self, message: discord.Message, channel: discord.TextChannel, stars: int):
        existing = self.get_starboard_message_config(message.guild.id, message.id)
        if existing and existing["forwarded_message_id"]:
            try:
                old_msg = await channel.fetch_message(int(existing["forwarded_message_id"]))
                if old_msg:
                    await old_msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
            self.db.execute(
                "DELETE FROM starboard_entries WHERE guild_id = ? AND message_id = ?",
                (message.guild.id, message.id),
            )

        embed = discord.Embed(
            title=f"{STARBOARD_EMOJI} Starboard",
            description=f"Message de {message.author.mention}",
            color=discord.Color.gold(),
            timestamp=message.created_at,
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        if message.content:
            embed.description += f"> {message.content[:1000]}"
        if message.attachments:
            for att in message.attachments[:1]:
                embed.set_image(url=att.proxy_url)
        embed.set_footer(text=f"{stars}★ · {message.guild.name}")

        try:
            await message.add_reaction(STARBOARD_EMOJI)
        except (discord.Forbidden, discord.HTTPException):
            pass

        forwarded = await channel.send(embed=embed)
        self.db.execute(
            "INSERT INTO starboard_entries (guild_id, message_id, source_message_id, stars, forwarded_message_id) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, message_id) DO UPDATE SET "
            "stars=excluded.stars, forwarded_message_id=excluded.forwarded_message_id",
            (message.guild.id, message.id, message.id, stars, forwarded.id),
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        if str(payload.emoji) != STARBOARD_EMOJI:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        message = await payload.message.channel.fetch_message(payload.message_id)
        if message is None:
            return

        stars = self.add_star_to_message(guild.id, payload.message_id, payload.user_id)
        await self.forward_to_starboard(message, stars)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if str(payload.emoji) != STARBOARD_EMOJI:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        self.remove_star_from_message(guild.id, payload.message_id)

        message = await guild.get_channel(payload.channel_id).fetch_message(payload.message_id)
        if message is None:
            return

        stars = self.get_message_stars(guild.id, payload.message_id)
        cfg = self.get_starboard_config(guild.id)
        if cfg is None:
            return

        if stars < cfg["min_stars"]:
            existing = self.get_starboard_message_config(guild.id, payload.message_id)
            if existing and existing["forwarded_message_id"]:
                try:
                    channel = guild.get_channel(cfg["channel_id"])
                    if channel:
                        old_msg = await channel.fetch_message(int(existing["forwarded_message_id"]))
                        if old_msg:
                            await old_msg.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass
                self.db.execute(
                    "DELETE FROM starboard_entries WHERE guild_id = ? AND message_id = ?",
                    (guild.id, payload.message_id),
                )
        else:
            existing = self.get_starboard_message_config(guild.id, payload.message_id)
            if existing and existing["forwarded_message_id"]:
                try:
                    channel = guild.get_channel(cfg["channel_id"])
                    if channel:
                        old_msg = await channel.fetch_message(int(existing["forwarded_message_id"]))
                        if old_msg:
                            old_footer = old_msg.embeds[0].footer.text if old_msg.embeds else ""
                            new_embed = discord.Embed(
                                title=f"{STARBOARD_EMOJI} Starboard",
                                description=f"Message de {message.author.mention}",
                                color=discord.Color.gold(),
                                timestamp=message.created_at,
                            )
                            new_embed.set_author(
                                name=message.author.display_name,
                                icon_url=message.author.display_avatar.url,
                            )
                            if message.content:
                                new_embed.description += f"> {message.content[:1000]}"
                            new_embed.set_footer(text=f"{stars}★ · {message.guild.name}")
                            await old_msg.edit(embed=new_embed)
                except (discord.NotFound, discord.HTTPException):
                    pass

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def starboard(self, ctx, *, arg: str = None):
        if arg is None:
            cfg = self.get_starboard_config(ctx.guild.id)
            if cfg is None:
                return await ctx.send(
                    "Aucune configuration starboard pour ce serveur. Utilisez `,starboard #channel` pour en définir un."
                )
            return await ctx.send(
                f"Configuration starboard :
"
                f"- Canal : <#{cfg['channel_id']}>
"
                f"- Emoji : {cfg['emoji']}
"
                f"- Seuil : {cfg['min_stars']}★
"
                f"- Inclure messages bots : {'Oui' if cfg['include_bot_messages'] else 'Non'}
"
                f"- Exclure messages épinglés : {'Oui' if cfg['exclude_pinned'] else 'Non'}"
            )

        args = arg.split()
        if args[0] == "#" or args[0].startswith("<#"):
            channel = None
            for channel in ctx.guild.channels:
                if f"<#{channel.id}>" == args[0] or channel.mention == args[0]:
                    break
            if channel is None:
                return await ctx.send("Canal introuvable.")
            self.set_starboard_channel(ctx.guild.id, channel.id)
            return await ctx.send(f"✅ Salon de starboard défini sur {channel.mention}")

        if args[0] == "emoji" and len(args) >= 2:
            emoji = args[1]
            self.set_starboard_channel(ctx.guild.id, cfg["channel_id"] if cfg else 0, emoji=emoji)
            return await ctx.send(f"✅ Emoji starboard défini sur {emoji}")

        if args[0] == "seuil" and len(args) >= 2:
            try:
                min_stars = int(args[1])
            except ValueError:
                return await ctx.send("Le seuil doit être un nombre.")
            self.set_starboard_channel(
                ctx.guild.id, cfg["channel_id"] if cfg else 0, min_stars=min_stars
            )
            return await ctx.send(f"✅ Seuil starboard défini sur {min_stars}★")

        if args[0] == "bots":
            include = args[1].lower() == "on" if len(args) >= 2 else True
            self.set_starboard_channel(
                ctx.guild.id,
                cfg["channel_id"] if cfg else 0,
                include_bot_messages=1 if include else 0,
            )
            status = "activé" if include else "désactivé"
            return await ctx.send(f"✅ Inclusion des messages bots {status}")

        if args[0] == "epingles":
            exclude = args[1].lower() == "on" if len(args) >= 2 else True
            self.set_starboard_channel(
                ctx.guild.id,
                cfg["channel_id"] if cfg else 0,
                exclude_pinned=1 if exclude else 0,
            )
            status = "activé" if exclude else "désactivé"
            return await ctx.send(f"✅ Exclusion des messages épinglés {status}")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def starboardclear(self, ctx):
        self.db.execute("DELETE FROM starboard_entries WHERE guild_id = ?", (ctx.guild.id,))
        self.db.execute("DELETE FROM starboard_config WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send("✅ Configuration starboard réinitialisée.")

    async def _process_loop(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                await self._process_starboard_queue()
            except Exception:
                pass
            await asyncio.sleep(15)

    async def _process_starboard_queue(self):
        rows = self.db.fetchall("SELECT id, guild_id, message_id FROM starboard_entries")
        for row in rows:
            try:
                guild = self.bot.get_guild(row["guild_id"])
                if guild is None:
                    self.db.execute("DELETE FROM starboard_entries WHERE id = ?", (row["id"],))
                    continue
                msg = await guild.fetch_message(row["message_id"])
                if msg is None:
                    self.db.execute("DELETE FROM starboard_entries WHERE id = ?", (row["id"],))
            except (discord.NotFound, discord.HTTPException):
                self.db.execute("DELETE FROM starboard_entries WHERE id = ?", (row["id"],))

    def setup_process_task(self):
        if self._process_task is None or self._process_task.done():
            self._process_task = asyncio.create_task(self._process_loop())


def setup(bot, db):
    cog = cmdstarboard(bot, db)
    cog._ensure_starboard_tables()
    cog.setup_process_task()
    bot.add_cog(cog)
