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

    async def _prompt(self, ctx, text: str, timeout: float = 60.0):
        await ctx.send(text)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            return await self.bot.wait_for('message', check=check, timeout=timeout)
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Temps écoulé. La commande a été annulée.")
            return None

    @commands.command()
    async def addtag(self, ctx, title: str):
        """Ajoute une nouvelle note avec le titre et le contenu donnes."""
        content = await self._prompt(ctx, "Entrez le contenu de la note :")
        if content is None:
            return
        async with self.lock:
            self.set_note(title, content.content)
        await ctx.send("✅ Note créée.")

    @commands.command()
    async def removetag(self, ctx, title: str):
        """Supprime une note existante en utilisant son titre."""
        async with self.lock:
            if not self.delete_note(title):
                await ctx.send("❌ Note introuvable.")
                return
        await ctx.send("✅ Note supprimée.")

    @commands.command()
    async def tagedit(self, ctx, title: str):
        """Modifie le contenu d'une note existante en utilisant son titre."""
        if self.get_note(title) is None:
            await ctx.send("❌ Note introuvable.")
            return

        content = await self._prompt(ctx, "Entrez le nouveau contenu de la note :")
        if content is None:
            return
        async with self.lock:
            self.set_note(title, content.content)
        await ctx.send("✅ Note modifiée.")

    @commands.command()
    async def tagrename(self, ctx, old_title: str, new_title: str):
        """Modifie le nom d'une note."""
        async with self.lock:
            if not self.rename_note(old_title, new_title):
                await ctx.send("❌ Note introuvable.")
                return
        await ctx.send("✅ Note renommée.")

    @commands.command()
    async def tag(self, ctx, title: str):
        """Affiche le contenu d'une note avec un titre donne."""
        content = self.get_note(title)
        if content is not None:
            await ctx.send(content)
        else:
            await ctx.send(f"❌ Aucune note trouvée avec le titre '{title}'.")

    @commands.command()
    async def taglist(self, ctx):
        """Affiche toutes les notes dans une liste organisee."""
        titles = self.list_notes()
        description = "\n".join(titles) if titles else "(aucune note)"
        embed = discord.Embed(title="Liste des notes", description=description, color=discord.Color.green())
        await ctx.send(embed=embed)


def setup(bot, db):
    bot.add_cog(cmdnotes(bot, db))
