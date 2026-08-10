import discord
from discord.ext import commands
from discord.ui import Button, Select, View

from versioning import bot_version


BOT_VERSION = bot_version()

CATEGORIES_PER_PAGE = 25
COMMANDS_PER_PAGE = 10
SELECT_LIMIT = 25


class HelpView(View):
    def __init__(self, categories: dict, prefix: str, author_id: int, initial_key: str = None):
        super().__init__(timeout=300)
        self.categories = categories
        self.keys = sorted(categories.keys())
        self.prefix = prefix
        self.author_id = author_id
        self.current = initial_key
        self.cat_page = 0
        self.cmd_page = 0
        self.message = None
        self.render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Seul l'auteur de la commande peut naviguer dans cette aide.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    def _select_options(self):
        start = self.cat_page * SELECT_LIMIT
        options = []
        for key in self.keys[start:start + SELECT_LIMIT]:
            cat = self.categories[key]
            label = f"{cat['emoji']} {cat['title']}".strip()
            desc = f"{len(cat['commands'])} commande(s)"
            options.append(discord.SelectOption(label=label[:100], value=key, description=desc))
        return options

    def render(self):
        self.clear_items()
        select = Select(
            placeholder="Choisissez une catégorie…",
            options=self._select_options(),
            row=0,
        )
        select.callback = self._on_select
        self.add_item(select)

        if len(self.keys) > SELECT_LIMIT:
            prev_cat = Button(label="◀", style=discord.ButtonStyle.secondary, row=1)
            prev_cat.callback = self._on_cat_prev
            prev_cat.disabled = self.cat_page == 0
            self.add_item(prev_cat)

            next_cat = Button(label="▶", style=discord.ButtonStyle.secondary, row=1)
            next_cat.callback = self._on_cat_next
            next_cat.disabled = (self.cat_page + 1) * SELECT_LIMIT >= len(self.keys)
            self.add_item(next_cat)

        if self.current is not None:
            home = Button(label="🏠 Vue d'ensemble", style=discord.ButtonStyle.primary, row=2)
            home.callback = self._on_home
            self.add_item(home)

            cmds = self.categories[self.current]["commands"]
            if len(cmds) > COMMANDS_PER_PAGE:
                prev_cmd = Button(label="◀", style=discord.ButtonStyle.secondary, row=2)
                prev_cmd.callback = self._on_cmd_prev
                prev_cmd.disabled = self.cmd_page == 0
                self.add_item(prev_cmd)

                next_cmd = Button(label="▶", style=discord.ButtonStyle.secondary, row=2)
                next_cmd.callback = self._on_cmd_next
                next_cmd.disabled = (self.cmd_page + 1) * COMMANDS_PER_PAGE >= len(cmds)
                self.add_item(next_cmd)

        close = Button(label="🗑 Fermer", style=discord.ButtonStyle.danger, row=3)
        close.callback = self._on_close
        self.add_item(close)

    def _overview_embed(self):
        start = self.cat_page * CATEGORIES_PER_PAGE
        page_keys = self.keys[start:start + CATEGORIES_PER_PAGE]
        embed = discord.Embed(
            title="📖 Aide de DDCBot",
            description=(
                f"Sélectionnez une catégorie ci-dessous pour découvrir ses commandes.\n"
                f"Préfixe : **`{self.prefix}`**"
            ),
            color=0x5865F2,
        )
        for key in page_keys:
            cat = self.categories[key]
            cmds = ", ".join(f"`{self.prefix}{s.split()[0].strip('`')}`" for s, _ in cat["commands"])
            embed.add_field(
                name=f"{cat['emoji']} {cat['title']}",
                value=cmds or "(aucune)",
                inline=True,
            )
        pages = (len(self.keys) + CATEGORIES_PER_PAGE - 1) // CATEGORIES_PER_PAGE
        if pages > 1:
            embed.set_footer(
                text=f"Page {self.cat_page + 1}/{pages} · {len(self.keys)} catégories · Commit {BOT_VERSION}"
            )
        else:
            embed.set_footer(text=f"{len(self.keys)} catégories · Commit {BOT_VERSION}")
        return embed

    def _category_embed(self, key: str):
        cat = self.categories[key]
        start = self.cmd_page * COMMANDS_PER_PAGE
        page_cmds = cat["commands"][start:start + COMMANDS_PER_PAGE]
        embed = discord.Embed(
            title=f"{cat['emoji']} {cat['title']}",
            description=f"Commandes de la catégorie **{cat['title']}** — préfixe `{self.prefix}`.",
            color=0x5865F2,
        )
        for syntax, desc in page_cmds:
            embed.add_field(name=f"`{self.prefix}{syntax}`", value=desc or "—", inline=False)
        total_pages = (len(cat["commands"]) + COMMANDS_PER_PAGE - 1) // COMMANDS_PER_PAGE
        if total_pages > 1:
            embed.set_footer(
                text=f"Page {self.cmd_page + 1}/{total_pages} · {len(cat['commands'])} commandes · Commit {BOT_VERSION}"
            )
        else:
            embed.set_footer(text=f"{len(cat['commands'])} commandes · Commit {BOT_VERSION}")
        return embed

    async def _refresh(self, interaction: discord.Interaction):
        self.render()
        if self.current is None:
            embed = self._overview_embed()
        else:
            embed = self._category_embed(self.current)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_select(self, interaction: discord.Interaction):
        key = interaction.data["values"][0]
        self.current = key
        self.cmd_page = 0
        await self._refresh(interaction)

    async def _on_cat_prev(self, interaction: discord.Interaction):
        self.cat_page = max(0, self.cat_page - 1)
        await self._refresh(interaction)

    async def _on_cat_next(self, interaction: discord.Interaction):
        if (self.cat_page + 1) * SELECT_LIMIT < len(self.keys):
            self.cat_page += 1
        await self._refresh(interaction)

    async def _on_home(self, interaction: discord.Interaction):
        self.current = None
        self.cmd_page = 0
        await self._refresh(interaction)

    async def _on_cmd_prev(self, interaction: discord.Interaction):
        self.cmd_page = max(0, self.cmd_page - 1)
        await self._refresh(interaction)

    async def _on_cmd_next(self, interaction: discord.Interaction):
        cmds = self.categories[self.current]["commands"]
        if (self.cmd_page + 1) * COMMANDS_PER_PAGE < len(cmds):
            self.cmd_page += 1
        await self._refresh(interaction)

    async def _on_close(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)


class cmdhelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _normalize(self, name: str) -> str:
        n = name.lower()
        return n[3:] if n.startswith('cmd') else n

    def _build_categories(self):
        META = {
                'moderation': {'emoji': '🔨', 'title': 'Modération'},
                'utility': {'emoji': '🛠️', 'title': 'Utilité'},
                'utilite': {'emoji': '🛠️', 'title': 'Utilité'},
                'economie': {'emoji': '💰', 'title': 'Économie'},
                'eco': {'emoji': '💶', 'title': 'Économie'},
                'travail': {'emoji': '💼', 'title': 'Travail'},
                'work': {'emoji': '💼', 'title': 'Travail'},
                'revenus': {'emoji': '📈', 'title': 'Revenus passifs'},
                'income': {'emoji': '📈', 'title': 'Revenus passifs'},
                'jeux': {'emoji': '🎮', 'title': 'Jeux'},
                'jeu': {'emoji': '🎮', 'title': 'Jeux'},
                'giveaway': {'emoji': '🎁', 'title': 'Giveaway'},
                'anim': {'emoji': '🎁', 'title': 'Giveaway'},
                'animations': {'emoji': '🎁', 'title': 'Giveaway'},
                'notifications': {'emoji': '📺', 'title': 'Notifications séries'},
                'rss': {'emoji': '📺', 'title': 'Notifications séries'},
                'notifrss': {'emoji': '📺', 'title': 'Notifications séries'},
                'ai': {'emoji': '🤖', 'title': 'Assistant IA'},
                'ai_assistant': {'emoji': '🤖', 'title': 'Assistant IA'},
                'ai_moderation': {'emoji': '🛡️', 'title': 'Modération IA'},
                'logs': {'emoji': '📝', 'title': 'Logs'},
                'logs_cmd': {'emoji': '📝', 'title': 'Logs'},
                'diagnostics': {'emoji': '🔍', 'title': 'Diagnostics'},
                'notes': {'emoji': '🗒️', 'title': 'Notes'},
                'changelog': {'emoji': '📰', 'title': 'Changelog'},
                'leveling': {'emoji': '⭐', 'title': 'Niveaux & XP'},
                'reactroles': {'emoji': '🎭', 'title': 'Rôles réactions'},
                'guild_settings': {'emoji': '⚙️', 'title': 'Paramètres du serveur'},
                'automod': {'emoji': '🚫', 'title': 'Anti-spam'},
                'translation': {'emoji': '🌍', 'title': 'Traduction'},
                'minecraft': {'emoji': '⛏️', 'title': 'Minecraft'},
                'invitations': {'emoji': '✉️', 'title': 'Invitations'},
                'steam': {'emoji': '🎮', 'title': 'Steam'},
                'tickets': {'emoji': '🎫', 'title': 'Tickets'},
                'webhooks': {'emoji': '🪝', 'title': 'Webhooks'},
                'lockdown': {'emoji': '🔒', 'title': 'Lockdown'},
                'plugins': {'emoji': '🧩', 'title': 'Plugins'},
                'plugins_cmd': {'emoji': '🧩', 'title': 'Plugins'},
                'autres': {'emoji': '📦', 'title': 'Autres'},
                'misc': {'emoji': '📦', 'title': 'Autres'},
            }

        categories = {}
        for cog_name, cog in self.bot.cogs.items():
            key = self._normalize(cog_name)
            if key == 'help':
                continue
            cmds = [
                cmd for cmd in self.bot.commands
                if (cmd.cog_name and self._normalize(cmd.cog_name) == key and not cmd.hidden)
            ]
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

        orphan_cmds = [cmd for cmd in self.bot.commands if not cmd.cog_name and not cmd.hidden]
        if orphan_cmds:
            cmds_list = [(f"{cmd.name} {cmd.signature}".strip(), cmd.help or "") for cmd in orphan_cmds]
            categories['autres'] = {'emoji': '📦', 'title': 'Autres', 'commands': cmds_list}

        return categories

    def _resolve_key(self, categorie: str) -> str | None:
        key = categorie.lower()
        if key in self.categories:
            return key
        for k in self.categories:
            if k.startswith(key):
                return k
        return None

    @commands.command(name="help")
    async def help_command(self, ctx, *, categorie: str = None):
        """Affiche la liste des commandes disponibles."""

        prefix = ","
        self.categories = self._build_categories()

        if categorie:
            key = self._resolve_key(categorie)
            if key is None:
                valid = ", ".join(f"`{k}`" for k in self.categories.keys())
                await ctx.send(f"❌ Catégorie inconnue. Catégories disponibles : {valid}")
                return
            view = HelpView(self.categories, prefix, ctx.author.id, initial_key=key)
            embed = view._category_embed(key)
            view.message = await ctx.send(embed=embed, view=view)
            return

        view = HelpView(self.categories, prefix, ctx.author.id)
        embed = view._overview_embed()
        view.message = await ctx.send(embed=embed, view=view)


def setup(bot):
    bot.add_cog(cmdhelp(bot))
