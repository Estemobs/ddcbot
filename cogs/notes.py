import asyncio
import json
import os
import discord
from discord.ext import commands


class cmdnotes(commands.Cog):
    """Gestion de notes/tags textuels par serveur.

    Commandes:
    - addtag [titre] : ajoute une nouvelle note
    - removetag [titre] : supprime une note existante
    - tagedit [titre] : modifie le contenu d'une note existante
    - tagrename [ancien_titre] [nouveau_titre] : renomme une note
    - tag [titre] : affiche le contenu d'une note
    - taglist : liste toutes les notes
    """

    def __init__(self, bot):
        self.bot = bot
        self.tags_path = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), 'data', 'notes.json')
        self.lock = asyncio.Lock()

    def _load_tags(self):
        try:
            with open(self.tags_path, 'r') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_tags(self, tags):
        with open(self.tags_path, 'w') as f:
            json.dump(tags, f, indent=2)

    @commands.command()
    async def addtag(self, ctx, title: str):
        """Ajoute une nouvelle note avec le titre et le contenu donnes."""
        await ctx.send("Enter the content for the tag: ")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        content = await self.bot.wait_for('message', check=check)
        async with self.lock:
            tags = self._load_tags()
            tags[title] = content.content
            self._save_tags(tags)
        await ctx.send("Tag created.")

    @commands.command()
    async def removetag(self, ctx, title: str):
        """Supprime une note existante en utilisant son titre."""
        async with self.lock:
            tags = self._load_tags()
            if title not in tags:
                await ctx.send("Tag not found.")
                return
            del tags[title]
            self._save_tags(tags)
        await ctx.send("Tag removed.")

    @commands.command()
    async def tagedit(self, ctx, title: str):
        """Modifie le contenu d'une note existante en utilisant son titre."""
        tags = self._load_tags()
        if title not in tags:
            await ctx.send("Tag not found.")
            return

        await ctx.send("Enter the new content for the tag: ")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        content = await self.bot.wait_for('message', check=check)
        async with self.lock:
            tags = self._load_tags()
            tags[title] = content.content
            self._save_tags(tags)
        await ctx.send("Tag edited.")

    @commands.command()
    async def tagrename(self, ctx, old_title: str, new_title: str):
        """Modifie le nom d'une note."""
        async with self.lock:
            tags = self._load_tags()
            if old_title not in tags:
                await ctx.send("Tag not found.")
                return
            tags[new_title] = tags[old_title]
            del tags[old_title]
            self._save_tags(tags)
        await ctx.send("Tag renamed.")

    @commands.command()
    async def tag(self, ctx, title: str):
        """Affiche le contenu d'une note avec un titre donne."""
        tags = self._load_tags()
        if title in tags:
            await ctx.send(tags[title])
        else:
            await ctx.send(f"No tag found with the title '{title}'")

    @commands.command()
    async def taglist(self, ctx):
        """Affiche toutes les notes dans une liste organisee."""
        tags = self._load_tags()
        description = "\n".join(tags.keys()) if tags else "(aucune note)"
        embed = discord.Embed(title="Tag List", description=description, color=discord.Color.green())
        embed.set_thumbnail(url="https://i.imgur.com/zV874EI.png")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(cmdnotes(bot))
