import aiohttp
import discord
from discord.ext import commands

from cogs.i18n import LANGUAGES, resolve_lang, t


async def translate_text(text: str, target_lang: str) -> str:
    """Traduit un texte via l'endpoint gratuit Google Translate (sans clef)."""
    url = "https://translate.googleapis.com/translate_a/single"
    params = {"client": "gtx", "sl": "auto", "tl": target_lang, "dt": "t", "q": text}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, params=params, timeout=aiohttp.ClientTimeout(total=15)
        ) as response:
            response.raise_for_status()
            data = await response.json(content_type=None)
    parts = [segment[0] for segment in data[0] if segment and segment[0]]
    return "".join(parts)


class cmdtranslation(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    def set_user_lang(self, user_id: int, lang: str):
        self.db.execute(
            "INSERT INTO user_lang (user_id, lang) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET lang = excluded.lang",
            (user_id, lang),
        )

    def set_guild_lang(self, guild_id: int, lang: str):
        self.db.execute(
            "INSERT INTO guild_lang (guild_id, lang) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET lang = excluded.lang",
            (guild_id, lang),
        )

    def add_subscription(self, user_id: int, channel_id: int, target_lang: str):
        self.db.execute(
            "INSERT INTO translation_subs (user_id, channel_id, target_lang) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, channel_id) DO UPDATE SET target_lang = excluded.target_lang",
            (user_id, channel_id, target_lang),
        )

    def remove_subscription(self, user_id: int, channel_id: int):
        self.db.execute(
            "DELETE FROM translation_subs WHERE user_id = ? AND channel_id = ?",
            (user_id, channel_id),
        )

    def list_subscriptions(self, user_id: int):
        return self.db.fetchall(
            "SELECT channel_id, target_lang FROM translation_subs WHERE user_id = ?",
            (user_id,),
        )

    def channel_subscribers(self, channel_id: int):
        return self.db.fetchall(
            "SELECT user_id, target_lang FROM translation_subs WHERE channel_id = ?",
            (channel_id,),
        )

    # --- commandes langue ---

    @commands.command()
    async def lang(self, ctx, lang: str):
        """Définit votre langue (fr ou en)."""
        lang = lang.lower().strip()
        if lang not in LANGUAGES:
            await ctx.send(t(self.db, "lang_invalid", ctx.guild.id if ctx.guild else None, ctx.author.id))
            return
        self.set_user_lang(ctx.author.id, lang)
        await ctx.send(t(self.db, "lang_changed", ctx.guild.id if ctx.guild else None, ctx.author.id, lang=lang))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def guildlang(self, ctx, lang: str):
        """Définit la langue par défaut du serveur (fr ou en)."""
        lang = lang.lower().strip()
        if lang not in LANGUAGES:
            await ctx.send(t(self.db, "lang_invalid", ctx.guild.id, ctx.author.id))
            return
        self.set_guild_lang(ctx.guild.id, lang)
        await ctx.send(t(self.db, "guild_lang_changed", ctx.guild.id, ctx.author.id, lang=lang))

    # --- abonnement traduction automatique ---

    @commands.command(name="translator")
    async def translator(self, ctx, state: str, lang: str = None):
        """Active/désactive la traduction automatique dans ce salon (,translator on en / off)."""
        if ctx.guild is None:
            await ctx.send(t(self.db, "translation_need_channel", None, ctx.author.id))
            return
        state = state.lower().strip()
        if state == "on":
            if lang is None or lang.lower() not in LANGUAGES:
                await ctx.send(t(self.db, "translation_invalid_lang", ctx.guild.id, ctx.author.id))
                return
            self.add_subscription(ctx.author.id, ctx.channel.id, lang.lower())
            await ctx.send(t(self.db, "translation_enabled", ctx.guild.id, ctx.author.id, lang=lang.lower()))
        elif state == "off":
            self.remove_subscription(ctx.author.id, ctx.channel.id)
            await ctx.send(t(self.db, "translation_disabled", ctx.guild.id, ctx.author.id))
        else:
            await ctx.send(t(self.db, "translation_invalid_lang", ctx.guild.id, ctx.author.id))

    @commands.command(name="translations")
    async def translations(self, ctx):
        """Liste vos abonnements à la traduction automatique."""
        rows = self.list_subscriptions(ctx.author.id)
        if not rows:
            await ctx.send(t(self.db, "translation_status_empty", ctx.guild.id if ctx.guild else None, ctx.author.id))
            return
        lines = []
        for row in rows:
            channel = self.bot.get_channel(row["channel_id"])
            label = f"<#{row['channel_id']}>" if channel is None else f"#{channel.name}"
            lines.append(f"- {label} → **{row['target_lang']}**")
        embed = discord.Embed(
            title=t(self.db, "translation_status_title", ctx.guild.id if ctx.guild else None, ctx.author.id),
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    # --- traduction a la demande (ephemere en slash) ---

    @commands.hybrid_command(name="translate", aliases=["traduire"])
    async def translate(self, ctx, *, text: str):
        """Traduit un texte (langue cible par défaut : celle du serveur ou fr)."""
        lang = None
        first_word = text.split(maxsplit=1)[0].lower() if text else ""
        if first_word in LANGUAGES:
            lang = first_word
            text = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
        if lang is None:
            lang = resolve_lang(self.db, ctx.guild.id if ctx.guild else None, ctx.author.id)
        try:
            translated = await translate_text(text, lang)
        except Exception:
            translated = None
        if not translated:
            await ctx.send(t(self.db, "translation_error", ctx.guild.id if ctx.guild else None, ctx.author.id))
            return
        embed = discord.Embed(
            title=f"🌐 → {lang}",
            description=translated,
            color=discord.Color.blue(),
        )
        if ctx.interaction:
            await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    # --- ecouteur : traduction automatique en DM ---

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return
        if not message.content or message.content.startswith(","):
            return
        subscribers = self.channel_subscribers(message.channel.id)
        if not subscribers:
            return
        for sub in subscribers:
            if sub["user_id"] == message.author.id:
                continue
            try:
                translated = await translate_text(message.content, sub["target_lang"])
            except Exception:
                continue
            if not translated or translated.strip() == message.content.strip():
                continue
            if len(translated) > 1900:
                translated = translated[:1900]
            user = self.bot.get_user(sub["user_id"])
            if user is None:
                continue
            try:
                await user.send(
                    f"{t(self.db, 'translation_dm_intro', None, sub['user_id'], channel=message.channel.name)}\n"
                    f"> {translated}"
                )
            except (discord.Forbidden, discord.HTTPException):
                continue


def setup(bot, db):
    bot.add_cog(cmdtranslation(bot, db))
