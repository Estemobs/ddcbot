import asyncio
import discord
from discord import app_commands
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

    @staticmethod
    def _gid(ctx_or_interaction) -> int:
        """Guild courante, 0 en MP (les notes 0 sont les notes heritees/globales)."""
        guild = getattr(ctx_or_interaction, "guild", None)
        return guild.id if guild else 0

    def get_note(self, guild_id: int, title: str):
        """Note du serveur, avec repli sur les notes globales heritees (guild_id 0)."""
        row = self.db.fetchone(
            "SELECT content FROM notes WHERE guild_id = ? AND title = ?", (guild_id, title)
        )
        if row is None and guild_id != 0:
            row = self.db.fetchone(
                "SELECT content FROM notes WHERE guild_id = 0 AND title = ?", (title,)
            )
        return row["content"] if row else None

    def set_note(self, guild_id: int, title: str, content: str):
        self.db.execute(
            "INSERT INTO notes (guild_id, title, content) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, title) DO UPDATE SET content = excluded.content",
            (guild_id, title, content),
        )

    def delete_note(self, guild_id: int, title: str) -> bool:
        """Supprime la note du serveur, sinon la note heritee du meme titre."""
        cur = self.db.execute(
            "DELETE FROM notes WHERE guild_id = ? AND title = ?", (guild_id, title)
        )
        if cur.rowcount:
            return True
        if guild_id == 0:
            return False
        cur = self.db.execute("DELETE FROM notes WHERE guild_id = 0 AND title = ?", (title,))
        return bool(cur.rowcount)

    def rename_note(self, guild_id: int, old_title: str, new_title: str) -> bool:
        content = self.get_note(guild_id, old_title)
        if content is None:
            return False
        self.set_note(guild_id, new_title, content)
        self.delete_note(guild_id, old_title)
        return True

    def list_notes(self, guild_id: int) -> list:
        rows = self.db.fetchall(
            "SELECT DISTINCT title FROM notes WHERE guild_id IN (?, 0) ORDER BY title",
            (guild_id,),
        )
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
            self.set_note(self._gid(ctx), title, content.content)
        await ctx.send("✅ Note créée.")

    @commands.command()
    async def removetag(self, ctx, title: str):
        """Supprime une note existante en utilisant son titre."""
        async with self.lock:
            if not self.delete_note(self._gid(ctx), title):
                await ctx.send("❌ Note introuvable.")
                return
        await ctx.send("✅ Note supprimée.")

    @commands.command()
    async def tagedit(self, ctx, title: str):
        """Modifie le contenu d'une note existante en utilisant son titre."""
        if self.get_note(self._gid(ctx), title) is None:
            await ctx.send("❌ Note introuvable.")
            return

        content = await self._prompt(ctx, "Entrez le nouveau contenu de la note :")
        if content is None:
            return
        async with self.lock:
            self.set_note(self._gid(ctx), title, content.content)
        await ctx.send("✅ Note modifiée.")

    @commands.command()
    async def tagrename(self, ctx, old_title: str, new_title: str):
        """Modifie le nom d'une note."""
        async with self.lock:
            if not self.rename_note(self._gid(ctx), old_title, new_title):
                await ctx.send("❌ Note introuvable.")
                return
        await ctx.send("✅ Note renommée.")

    @commands.command()
    async def tag(self, ctx, title: str):
        """Affiche le contenu d'une note avec un titre donne."""
        content = self.get_note(self._gid(ctx), title)
        if content is not None:
            await ctx.send(content)
        else:
            await ctx.send(f"❌ Aucune note trouvée avec le titre '{title}'.")

    @app_commands.command(name="tag")
    @app_commands.describe(title="Le titre de la note")
    async def tag_slash(self, interaction: discord.Interaction, title: str):
        """Affiche le contenu d'une note."""
        content = self.get_note(self._gid(interaction), title)
        if content is not None:
            await interaction.response.send_message(content)
        else:
            await interaction.response.send_message(f"❌ Aucune note trouvée avec le titre '{title}'.")

    @commands.command()
    async def taglist(self, ctx):
        """Affiche toutes les notes dans une liste organisee."""
        titles = self.list_notes(self._gid(ctx))
        description = "\n".join(titles) if titles else "(aucune note)"
        embed = discord.Embed(title="Liste des notes", description=description, color=discord.Color.green())
        await ctx.send(embed=embed)

    @app_commands.command(name="taglist")
    async def taglist_slash(self, interaction: discord.Interaction):
        """Affiche toutes les notes dans une liste organisee."""
        titles = self.list_notes(self._gid(interaction))
        description = "\n".join(titles) if titles else "(aucune note)"
        embed = discord.Embed(title="Liste des notes", description=description, color=discord.Color.green())
        await interaction.response.send_message(embed=embed)


def setup(bot, db):
    bot.add_cog(cmdnotes(bot, db))
