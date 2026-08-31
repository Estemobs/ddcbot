import aiohttp
import discord
from discord import app_commands
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
    async def guildlang(self, ctx, lang: str):
        """Définit la langue par défaut du serveur (fr ou en)."""
        lang = lang.lower().strip()
        if lang not in LANGUAGES:
            await ctx.send(t(self.db, "lang_invalid", ctx.guild.id, ctx.author.id))
            return
        self.set_guild_lang(ctx.guild.id, lang)
        await ctx.send(t(self.db, "guild_lang_changed", ctx.guild.id, ctx.author.id, lang=lang))

    # --- traduction a la demande (ephemere, slash uniquement) ---

    @app_commands.command(name="translate")
    @app_commands.describe(text="Le texte à traduire (optionnel : langue cible en premier mot, ex. `en Bonjour`)")
    async def translate(self, interaction: discord.Interaction, text: str):
        """Traduit un texte (langue cible par défaut : celle du serveur ou fr)."""
        lang = None
        parts = text.split(maxsplit=1)
        first_word = parts[0].lower() if parts else ""
        if first_word in LANGUAGES:
            lang = first_word
            text = parts[1] if len(parts) > 1 else ""
        if lang is None:
            lang = resolve_lang(self.db, interaction.guild.id if interaction.guild else None, interaction.user.id)
        try:
            translated = await translate_text(text, lang)
        except Exception:
            translated = None
        if not translated:
            await interaction.response.send_message(
                t(self.db, "translation_error", interaction.guild.id if interaction.guild else None, interaction.user.id),
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title=f"🌐 → {lang}",
            description=translated,
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


def setup(bot, db):
    bot.add_cog(cmdtranslation(bot, db))
