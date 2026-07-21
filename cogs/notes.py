import asyncio
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

    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.lock = asyncio.Lock()

    def get_note(self, title: str):
        row = self.db.fetchone("SELECT content FROM notes WHERE title = ?", (title,))
        return row["content"] if row else None

    def set_note(self, title: str, content: str):
        self.db.execute(
            "INSERT INTO notes (title, content) VALUES (?, ?) "
            "ON CONFLICT(title) DO UPDATE SET content = excluded.content",
            (title, content),
        )

    def delete_note(self, title: str) -> bool:
        if self.get_note(title) is None:
            return False
        self.db.execute("DELETE FROM notes WHERE title = ?", (title,))
        return True

    def rename_note(self, old_title: str, new_title: str) -> bool:
        content = self.get_note(old_title)
        if content is None:
            return False
        self.set_note(new_title, content)
        self.db.execute("DELETE FROM notes WHERE title = ?", (old_title,))
        return True

    def list_notes(self) -> list:
        rows = self.db.fetchall("SELECT title FROM notes ORDER BY title")
        return [row["title"] for row in rows]

    @commands.command()
    async def addtag(self, ctx, title: str):
        """Ajoute une nouvelle note avec le titre et le contenu donnes."""
        await ctx.send("Enter the content for the tag: ")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        content = await self.bot.wait_for('message', check=check)
        async with self.lock:
            self.set_note(title, content.content)
        await ctx.send("Tag created.")

    @commands.command()
    async def removetag(self, ctx, title: str):
        """Supprime une note existante en utilisant son titre."""
        async with self.lock:
            if not self.delete_note(title):
                await ctx.send("Tag not found.")
                return
        await ctx.send("Tag removed.")

    @commands.command()
    async def tagedit(self, ctx, title: str):
        """Modifie le contenu d'une note existante en utilisant son titre."""
        if self.get_note(title) is None:
            await ctx.send("Tag not found.")
            return

        await ctx.send("Enter the new content for the tag: ")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        content = await self.bot.wait_for('message', check=check)
        async with self.lock:
            self.set_note(title, content.content)
        await ctx.send("Tag edited.")

    @commands.command()
    async def tagrename(self, ctx, old_title: str, new_title: str):
        """Modifie le nom d'une note."""
        async with self.lock:
            if not self.rename_note(old_title, new_title):
                await ctx.send("Tag not found.")
                return
        await ctx.send("Tag renamed.")

    @commands.command()
    async def tag(self, ctx, title: str):
        """Affiche le contenu d'une note avec un titre donne."""
        content = self.get_note(title)
        if content is not None:
            await ctx.send(content)
        else:
            await ctx.send(f"No tag found with the title '{title}'")

    @commands.command()
    async def taglist(self, ctx):
        """Affiche toutes les notes dans une liste organisee."""
        titles = self.list_notes()
        description = "\n".join(titles) if titles else "(aucune note)"
        embed = discord.Embed(title="Tag List", description=description, color=discord.Color.green())
        embed.set_thumbnail(url="https://i.imgur.com/zV874EI.png")
        await ctx.send(embed=embed)


def setup(bot, db):
    bot.add_cog(cmdnotes(bot, db))
