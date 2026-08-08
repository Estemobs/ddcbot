"""Cog de gestion des plugins/extensions.

Commandes (admin) : ,plugins list / enable / disable / reload
"""

import discord
from discord.ext import commands

import plugin_loader


class cmdplugins(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    def _available(self):
        return set(plugin_loader.discover_plugins())

    @commands.group(name="plugins", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def plugins(self, ctx):
        """Gestion des plugins: ,plugins list | enable | disable | reload"""
        await ctx.send(
            "Gestion des plugins.\n"
            "` ,plugins list` - liste les plugins\n"
            "` ,plugins enable <nom>` - active un plugin\n"
            "` ,plugins disable <nom>` - desactive un plugin\n"
            "` ,plugins reload [nom]` - recharge les plugins"
        )

    @plugins.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def plugins_list(self, ctx):
        """Liste les plugins disponibles et leur statut."""
        available = self._available()
        if not available:
            await ctx.send("Aucun plugin disponible dans le dossier `plugins/`.")
            return
        enabled = plugin_loader.get_enabled(self.db)
        lines = []
        for name in sorted(available):
            meta = plugin_loader.plugin_metadata(name)
            status = "actif" if enabled.get(name, True) else "inactif"
            lines.append(f"- **{name}** v{meta.get('version', '?')} ({status})")
        embed = discord.Embed(
            title="Plugins",
            description="\n".join(lines) or "Aucun plugin.",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @plugins.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def plugins_enable(self, ctx, name: str):
        """Active un plugin et le charge."""
        if name not in self._available():
            await ctx.send(f"Plugin inconnu: `{name}`.")
            return
        plugin_loader.set_enabled(self.db, name, True)
        await ctx.send(f"Plugin `{name}` active. Chargement en cours...")
        await plugin_loader.reload_plugins(self.bot, self.db, [name])

    @plugins.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def plugins_disable(self, ctx, name: str):
        """Desactive un plugin et le decharge."""
        if name not in self._available():
            await ctx.send(f"Plugin inconnu: `{name}`.")
            return
        await plugin_loader.unload_plugins(self.bot, self.db, [name])
        plugin_loader.set_enabled(self.db, name, False)
        await ctx.send(f"Plugin `{name}` desactive.")

    @plugins.command(name="reload")
    @commands.has_permissions(manage_guild=True)
    async def plugins_reload(self, ctx, name: str = None):
        """Recharge tous les plugins (ou un seul)."""
        if name is not None and name not in self._available():
            await ctx.send(f"Plugin inconnu: `{name}`.")
            return
        targets = [name] if name else None
        loaded = await plugin_loader.reload_plugins(self.bot, self.db, targets)
        if name:
            await ctx.send(f"Plugin `{name}` recharge.")
        else:
            await ctx.send(f"Plugins recharges: {', '.join(loaded) if loaded else 'aucun'}.")


def setup(bot, db):
    bot.add_cog(cmdplugins(bot, db))
