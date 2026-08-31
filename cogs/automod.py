import re

import discord
from discord.ext import commands

from cogs.i18n import t

WORD_RE = re.compile(r"[a-z0-9àâäéèêëîïôöùûüç'’-]+")


class cmdautomod(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._cfg_initialized = set()

    def get_config(self, guild_id: int) -> dict:
        if guild_id not in self._cfg_initialized:
            self._cfg_initialized.add(guild_id)
            self.db.execute(
                "INSERT OR IGNORE INTO automod_config (guild_id, enabled, warn_on_match, delete_on_match, log_channel_id) "
                "VALUES (?, 0, 1, 1, NULL)",
                (guild_id,),
            )
        row = self.db.fetchone(
            "SELECT enabled, warn_on_match, delete_on_match, log_channel_id FROM automod_config WHERE guild_id = ?",
            (guild_id,),
        )
        return {
            "enabled": bool(row["enabled"]),
            "warn_on_match": bool(row["warn_on_match"]),
            "delete_on_match": bool(row["delete_on_match"]),
            "log_channel_id": row["log_channel_id"],
        }

    def save_config(self, guild_id: int, **fields):
        self.get_config(guild_id)
        assignments = []
        values = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(int(value) if isinstance(value, bool) else value)
        values.append(guild_id)
        self.db.execute(f"UPDATE automod_config SET {', '.join(assignments)} WHERE guild_id = ?", values)

    def add_word(self, guild_id: int, word: str):
        self.db.execute(
            "INSERT OR IGNORE INTO automod_words (guild_id, word) VALUES (?, ?)",
            (guild_id, word),
        )

    def remove_word(self, guild_id: int, word: str) -> bool:
        cursor = self.db.execute(
            "DELETE FROM automod_words WHERE guild_id = ? AND word = ?", (guild_id, word)
        )
        return cursor.rowcount > 0

    def list_words(self, guild_id: int) -> list:
        rows = self.db.fetchall(
            "SELECT word FROM automod_words WHERE guild_id = ? ORDER BY word", (guild_id,)
        )
        return [row["word"] for row in rows]

    def _matches(self, content: str, words: list) -> bool:
        lowered = content.lower()
        tokens = set(WORD_RE.findall(lowered))
        return any(word.lower() in tokens for word in words)

    # --- commandes ---

    @commands.command()
    async def automod(self, ctx, state: str = None):
        """Active/désactive l'auto-mod (on/off) ou affiche la config."""
        if state is None:
            await ctx.invoke(self.bot.get_command("automodconfig"))
            return
        state = state.lower()
        if state not in ("on", "off"):
            await ctx.invoke(self.bot.get_command("automodconfig"))
            return
        self.save_config(ctx.guild.id, enabled=(state == "on"))
        if state == "on":
            await ctx.send(t(self.db, "automod_enabled", ctx.guild.id, ctx.author.id))
        else:
            await ctx.send(t(self.db, "automod_disabled", ctx.guild.id, ctx.author.id))

    @commands.command()
    async def automodconfig(self, ctx):
        """Affiche la configuration de l'auto-mod."""
        cfg = self.get_config(ctx.guild.id)
        log_channel = self.bot.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None
        embed = discord.Embed(
            title=t(self.db, "automod_config_title", ctx.guild.id, ctx.author.id),
            color=discord.Color.red(),
        )
        embed.add_field(name=t(self.db, "xp_config_enabled", ctx.guild.id, ctx.author.id), value="✅" if cfg["enabled"] else "❌", inline=True)
        embed.add_field(name=t(self.db, "automod_config_warn", ctx.guild.id, ctx.author.id), value="✅" if cfg["warn_on_match"] else "❌", inline=True)
        embed.add_field(name=t(self.db, "automod_config_delete", ctx.guild.id, ctx.author.id), value="✅" if cfg["delete_on_match"] else "❌", inline=True)
        log_label = f"#{log_channel.name}" if log_channel else t(self.db, "xp_config_none", ctx.guild.id, ctx.author.id)
        embed.add_field(name=t(self.db, "welcome_config_channel", ctx.guild.id, ctx.author.id), value=log_label, inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="badword")
    async def badword(self, ctx, action: str, *, word: str = None):
        """Gère les mots bannis : ,badword add <mot> / remove <mot> / list"""
        action = action.lower()
        if action == "list":
            words = self.list_words(ctx.guild.id)
            if not words:
                await ctx.send(t(self.db, "automod_list_empty", ctx.guild.id, ctx.author.id))
                return
            embed = discord.Embed(
                title=t(self.db, "automod_list_title", ctx.guild.id, ctx.author.id),
                description=", ".join(f"`{w}`" for w in words),
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return
        if not word:
            await ctx.send("Syntaxe : `,badword add <mot>` / `,badword remove <mot>` / `,badword list`")
            return
        word = word.strip().lower()
        if action == "add":
            self.add_word(ctx.guild.id, word)
            await ctx.send(t(self.db, "automod_word_added", ctx.guild.id, ctx.author.id, word=word))
        elif action == "remove":
            if self.remove_word(ctx.guild.id, word):
                await ctx.send(t(self.db, "automod_word_removed", ctx.guild.id, ctx.author.id, word=word))
            else:
                await ctx.send(t(self.db, "automod_word_not_found", ctx.guild.id, ctx.author.id))
        else:
            await ctx.send("Action invalide. Utilisez `add`, `remove` ou `list`.")

    # --- écouteur ---

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return
        cfg = self.get_config(message.guild.id)
        if not cfg["enabled"]:
            return
        words = self.list_words(message.guild.id)
        if not words:
            return
        if not self._matches(message.content, words):
            return
        if cfg["delete_on_match"]:
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
        if cfg["warn_on_match"]:
            await message.channel.send(
                f"{message.author.mention} {t(self.db, 'automod_warned', message.guild.id, message.author.id)}",
                delete_after=10,
            )
        if cfg["log_channel_id"]:
            channel = message.guild.get_channel(cfg["log_channel_id"])
            if channel:
                try:
                    await channel.send(
                        f"🚫 **Auto-mod** — {message.author.mention} ({message.author.id})\n"
                        f"Salon : {message.channel.mention}\nContenu : {message.content[:500]}"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass


def setup(bot, db):
    bot.add_cog(cmdautomod(bot, db))
