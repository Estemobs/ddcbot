"""Messages Embed enregistres, et gestion des emojis du serveur.

Deux modules sans dependance externe. Les embeds se composent surtout depuis le
dashboard (avec apercu) ; les commandes servent a les envoyer et a les corriger
en place. Les regles et limites de Discord vivent dans embed_builder.

Commandes :
  ,embed list                  — embeds enregistres
  ,embed send <nom> [#salon]   — publie un embed
  ,embed edit <nom>            — met a jour le message deja publie
  ,embed delete <nom>
  ,emoji list                  — emojis du serveur
  ,emoji add <nom> <url|:emoji:>  — ajoute un emoji
  ,emoji remove <nom>
"""

import re

import discord
from discord.ext import commands

import embed_builder

EMOJI_MENTION_RE = re.compile(r"<(a?):(\w+):(\d+)>")


def build_discord_embed(payload: dict) -> discord.Embed:
    """Traduit la charge utile de embed_builder en discord.Embed."""
    embed = discord.Embed(
        title=payload["title"],
        description=payload["description"],
        url=payload["url"],
        color=payload["color"],
    )
    if payload["author_name"]:
        embed.set_author(name=payload["author_name"], icon_url=payload["author_icon"] or None)
    if payload["footer_text"]:
        embed.set_footer(text=payload["footer_text"])
    if payload["image_url"]:
        embed.set_image(url=payload["image_url"])
    if payload["thumbnail_url"]:
        embed.set_thumbnail(url=payload["thumbnail_url"])
    for field in payload["fields"]:
        embed.add_field(name=field["name"], value=field["value"], inline=field["inline"])
    return embed


class cmdembeds(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    # --- embeds enregistres ---

    def list_embeds(self, guild_id: int) -> list:
        return [dict(r) for r in self.db.fetchall(
            "SELECT * FROM embeds WHERE guild_id = ? ORDER BY name", (guild_id,)
        )]

    def get_embed(self, guild_id: int, name: str):
        row = self.db.fetchone(
            "SELECT * FROM embeds WHERE guild_id = ? AND LOWER(name) = LOWER(?)",
            (guild_id, name),
        )
        return dict(row) if row else None

    def delete_embed(self, guild_id: int, name: str) -> bool:
        cur = self.db.execute(
            "DELETE FROM embeds WHERE guild_id = ? AND LOWER(name) = LOWER(?)",
            (guild_id, name),
        )
        return bool(cur.rowcount)

    def remember_message(self, embed_id: int, channel_id: int, message_id: int):
        self.db.execute(
            "UPDATE embeds SET channel_id = ?, message_id = ? WHERE id = ?",
            (channel_id, message_id, embed_id),
        )

    def render(self, stored: dict, guild=None, member=None):
        """Embed pret a envoyer, plus le texte hors embed."""
        resolved = dict(stored)
        for key in ("title", "description", "footer_text", "author_name", "content"):
            resolved[key] = embed_builder.render_variables(resolved.get(key), guild, member)
        payload = embed_builder.to_payload(resolved)
        return build_discord_embed(payload), payload["content"]

    @commands.command()
    async def embed(self, ctx, action: str = None, name: str = None, *, rest: str = None):
        """,embed list | send <nom> [#salon] | edit <nom> | delete <nom>"""
        if action is None or action.lower() == "list":
            stored = self.list_embeds(ctx.guild.id)
            if not stored:
                await ctx.send(
                    "Aucun embed enregistré. Composez-en un depuis le dashboard, "
                    "puis publiez-le avec `,embed send <nom>`."
                )
                return
            lines = []
            for item in stored:
                where = ""
                if item["message_id"]:
                    where = f" · publié dans <#{item['channel_id']}>"
                lines.append(f"• **{item['name']}** — {item['title'] or '(sans titre)'}{where}")
            await ctx.send(embed=discord.Embed(
                title="🗒️ Embeds enregistrés",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            ))
            return

        action = action.lower()
        if not name:
            await ctx.send("Usage : `,embed send <nom> [#salon]`")
            return
        stored = self.get_embed(ctx.guild.id, name)
        if stored is None:
            await ctx.send(f"❌ Aucun embed nommé `{name}`.")
            return

        if action == "send":
            channel = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else ctx.channel
            problems = embed_builder.validate(stored)
            if problems:
                await ctx.send("❌ " + "\n".join(problems))
                return
            built, content = self.render(stored, ctx.guild, ctx.author)
            try:
                message = await channel.send(content=content, embed=built)
            except (discord.Forbidden, discord.HTTPException) as exc:
                await ctx.send(f"❌ Envoi impossible : {exc}")
                return
            self.remember_message(stored["id"], channel.id, message.id)
            if channel.id != ctx.channel.id:
                await ctx.send(f"✅ Publié dans {channel.mention}.")

        elif action == "edit":
            if not stored["message_id"]:
                await ctx.send("❌ Cet embed n'a pas encore été publié.")
                return
            channel = ctx.guild.get_channel(stored["channel_id"])
            if channel is None:
                await ctx.send("❌ Le salon de publication est introuvable.")
                return
            try:
                message = await channel.fetch_message(stored["message_id"])
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await ctx.send("❌ Le message publié est introuvable — republiez-le.")
                return
            built, content = self.render(stored, ctx.guild, ctx.author)
            await message.edit(content=content, embed=built)
            await ctx.send("✅ Message mis à jour.")

        elif action == "delete":
            self.delete_embed(ctx.guild.id, name)
            await ctx.send(f"✅ Embed `{name}` supprimé.")

        else:
            await ctx.send("Actions : `list`, `send`, `edit`, `delete`.")

    # --- emojis ---

    def sync_emojis(self, guild):
        """Recopie les emojis du serveur pour que le dashboard puisse les lire."""
        self.db.execute("DELETE FROM guild_emojis WHERE guild_id = ?", (guild.id,))
        for emoji in getattr(guild, "emojis", []) or []:
            self.db.execute(
                "INSERT OR REPLACE INTO guild_emojis (emoji_id, guild_id, name, animated, url) "
                "VALUES (?, ?, ?, ?, ?)",
                (emoji.id, guild.id, emoji.name, int(bool(emoji.animated)), str(emoji.url)),
            )

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try:
                self.sync_emojis(guild)
            except Exception as exc:
                print(f"[DEBUG] Synchronisation emojis impossible pour {guild.id}: {exc}")

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        self.sync_emojis(guild)

    async def _emoji_bytes(self, source: str):
        """Image d'un emoji, depuis une URL ou un emoji personnalise mentionne."""
        match = EMOJI_MENTION_RE.match(source.strip())
        if match:
            animated, _, emoji_id = match.groups()
            extension = "gif" if animated else "png"
            source = f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}"
        if not source.startswith("http"):
            return None
        from http_utils import get_bytes
        try:
            return await get_bytes(source, timeout=20)
        except Exception:
            return None

    @commands.command()
    async def emoji(self, ctx, action: str = None, name: str = None, *, source: str = None):
        """,emoji list | add <nom> <url|:emoji:> | remove <nom>"""
        if action is None or action.lower() == "list":
            emojis = ctx.guild.emojis
            if not emojis:
                await ctx.send("Ce serveur n'a aucun emoji personnalisé.")
                return
            self.sync_emojis(ctx.guild)
            shown = " ".join(str(e) for e in emojis[:60])
            await ctx.send(embed=discord.Embed(
                title=f"😀 Emojis ({len(emojis)})",
                description=shown,
                color=discord.Color.blurple(),
            ))
            return

        action = action.lower()
        if action == "add":
            if not name or not source:
                await ctx.send("Usage : `,emoji add <nom> <url ou :emoji:>`")
                return
            # Discord impose 2 a 32 caracteres alphanumeriques ou underscore.
            clean = re.sub(r"[^\w]", "_", name)[:32]
            if len(clean) < 2:
                await ctx.send("❌ Le nom doit faire au moins 2 caractères.")
                return
            data = await self._emoji_bytes(source)
            if data is None:
                await ctx.send("❌ Image introuvable. Donnez une URL directe ou un emoji.")
                return
            try:
                created = await ctx.guild.create_custom_emoji(
                    name=clean, image=data, reason=f"Ajoute par {ctx.author}"
                )
            except discord.Forbidden:
                await ctx.send("❌ Permission « Gérer les expressions » manquante.")
                return
            except discord.HTTPException as exc:
                await ctx.send(f"❌ Refus de Discord : {exc}")
                return
            self.sync_emojis(ctx.guild)
            await ctx.send(f"✅ Emoji {created} ajouté sous le nom `{clean}`.")

        elif action == "remove":
            if not name:
                await ctx.send("Usage : `,emoji remove <nom>`")
                return
            target = discord.utils.get(ctx.guild.emojis, name=name)
            if target is None:
                match = EMOJI_MENTION_RE.match(name)
                if match:
                    target = discord.utils.get(ctx.guild.emojis, id=int(match.group(3)))
            if target is None:
                await ctx.send(f"❌ Aucun emoji nommé `{name}`.")
                return
            try:
                await target.delete(reason=f"Supprime par {ctx.author}")
            except discord.Forbidden:
                await ctx.send("❌ Permission « Gérer les expressions » manquante.")
                return
            self.sync_emojis(ctx.guild)
            await ctx.send(f"✅ Emoji `{name}` supprimé.")

        else:
            await ctx.send("Actions : `list`, `add`, `remove`.")


def setup(bot, db):
    bot.add_cog(cmdembeds(bot, db))
