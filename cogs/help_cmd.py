import discord
from discord.ext import commands

from versioning import bot_version


BOT_VERSION = bot_version()


class cmdhelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _normalize(self, name: str) -> str:
        n = name.lower()
        return n[3:] if n.startswith('cmd') else n

    def _build_categories(self):
        # Meta par défaut pour certaines catégories connues
        META = {
                'moderation': {'emoji': '🔨', 'title': 'Modération'},
                'utility': {'emoji': '🛠️', 'title': 'Utility'},
                'utilite': {'emoji': '🛠️', 'title': 'Utilité'},
                'economie': {'emoji': '💰', 'title': 'Économie'},
                'eco': {'emoji': '💶', 'title': 'Eco'},
                'travail': {'emoji': '💼', 'title': 'Travail'},
                'revenus': {'emoji': '📈', 'title': 'Revenus passifs'},
                'jeux': {'emoji': '🎰', 'title': 'Jeux / Lootbox'},
                'jeu': {'emoji': '🎮', 'title': 'Jeu'},
                'giveaway': {'emoji': '🎁', 'title': 'Giveaway'},
                'notifications': {'emoji': '📺', 'title': 'Notifications séries'},
                'rss': {'emoji': '📡', 'title': 'Rss'},
                'anim': {'emoji': '🎞️', 'title': 'Anim'},
                'animations': {'emoji': '🎞️', 'title': 'Anim'},
                'income': {'emoji': '📥', 'title': 'Income'},
                'work': {'emoji': '💼', 'title': 'Work'},
                'ai': {'emoji': '🤖', 'title': 'Ai'},
                'logs': {'emoji': '📝', 'title': 'Logs'},
                'diagnostics': {'emoji': '🔍', 'title': 'Diagnostics'},
                'notes': {'emoji': '🗒️', 'title': 'Notes'},
                'autres': {'emoji': '📦', 'title': 'Autres'},
            }

        categories = {}
        for cog_name, cog in self.bot.cogs.items():
            key = self._normalize(cog_name)
            if key == 'help':
                continue
            cmds = [cmd for cmd in self.bot.commands if (cmd.cog_name and self._normalize(cmd.cog_name) == key and not cmd.hidden)]
            if not cmds:
                continue
            cmds_list = []
            for cmd in cmds:
                sig = cmd.signature.strip()
                usage = f"{cmd.name} {sig}".strip()
                desc = cmd.help or ""
                cmds_list.append((usage, desc))
            meta = META.get(key, {})
            categories[key] = {
                'emoji': meta.get('emoji', ''),
                'title': meta.get('title', key.capitalize()),
                'commands': cmds_list,
            }

        # Commandes orphelines (sans cog)
        orphan_cmds = [cmd for cmd in self.bot.commands if not cmd.cog_name and not cmd.hidden]
        if orphan_cmds:
            cmds_list = [(f"{cmd.name} {cmd.signature}".strip(), cmd.help or "") for cmd in orphan_cmds]
            categories['autres'] = {'emoji': '📦', 'title': 'Autres', 'commands': cmds_list}

        return categories

    @commands.command(name="help")
    async def help_command(self, ctx, *, categorie: str = None):
        """Affiche la liste des commandes disponibles."""

        prefix = ","
        categories = self._build_categories()

        if categorie:
            key = categorie.lower()
            if key not in categories:
                valid = ", ".join(f"`{k}`" for k in categories.keys())
                await ctx.send(f"❌ Catégorie inconnue. Catégories disponibles : {valid}")
                return

            cat = categories[key]
            embed = discord.Embed(
                title=f"{cat['emoji']} {cat['title']}",
                color=0x7289DA
            )
            for cmd_syntax, description in cat["commands"]:
                embed.add_field(
                    name=f"{prefix}{cmd_syntax}",
                    value=description,
                    inline=False
                )
            embed.set_footer(text=f"Préfixe : {prefix}  •  Commit {BOT_VERSION}  •  ,help <catégorie> pour plus de détails")
            await ctx.send(embed=embed)
            return

        # Vue générale
        embed = discord.Embed(
            title="📖 Liste des commandes",
            description=(
                f"Utilisez **`{prefix}help <catégorie>`** pour voir le détail d'une catégorie.\n"
                f"Exemple : `{prefix}help jeux`"
            ),
            color=0x7289DA
        )
        # Trier les catégories pour affichage stable
        for key in sorted(categories.keys()):
            cat = categories[key]
            # formate chaque commande comme `,commande`
            cmd_list = ", ".join(f"`{prefix}{s.split()[0].strip('`')}`" for s, _ in cat["commands"]) if cat["commands"] else "(aucune)"
            embed.add_field(
                name=f"{cat['emoji']} {cat['title']} — `{prefix}help {key}`",
                value=cmd_list,
                inline=False
            )
        embed.set_footer(text=f"Commit {BOT_VERSION}")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(cmdhelp(bot))
