import asyncio
import json
import os
import discord
from discord.ext import commands


LOG_CATEGORIES = {
    "user_errors": "Erreurs utilisateur (argument invalide, permission, cooldown...)",
    "unexpected_errors": "Erreurs inattendues (bugs, exceptions)",
}

DEFAULT_CATEGORIES = {key: True for key in LOG_CATEGORIES}


class cmdlogs(commands.Cog):
    """Gestion des canaux et catégories de logs par serveur.

    Commandes:
    - setlog [#channel] : active les logs dans le canal (ou canal courant si absent)
    - unsetlog [#channel] : désactive les logs dans le canal (ou canal courant si absent)
    - listlogs : liste les canaux et catégories configurés pour les logs
    - logspanel : panneau interactif pour choisir les catégories envoyées dans les logs
    """

    def __init__(self, bot):
        self.bot = bot
        self.config_path = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), 'data', 'logs_config.json')
        self.lock = asyncio.Lock()

    def _load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            data = data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        changed = False
        for guild_id, guild_cfg in list(data.items()):
            if isinstance(guild_cfg, list):
                data[guild_id] = {"channels": guild_cfg, "categories": dict(DEFAULT_CATEGORIES)}
                changed = True
            elif isinstance(guild_cfg, dict):
                guild_cfg.setdefault("channels", [])
                categories = guild_cfg.setdefault("categories", {})
                for key, default in DEFAULT_CATEGORIES.items():
                    categories.setdefault(key, default)
        if changed:
            self._save_config(data)
        return data

    def _save_config(self, cfg):
        with open(self.config_path, 'w') as f:
            json.dump(cfg, f, indent=2)

    def get_guild_config(self, guild_id):
        cfg = self._load_config()
        return cfg.setdefault(str(guild_id), {"channels": [], "categories": dict(DEFAULT_CATEGORIES)})

    def get_channels(self, guild, category: str):
        """Renvoie les salons configurés pour recevoir la catégorie de log donnée."""
        if guild is None or category not in LOG_CATEGORIES:
            return []
        cfg = self._load_config()
        guild_cfg = cfg.get(str(guild.id))
        if not guild_cfg or not guild_cfg["categories"].get(category, True):
            return []
        channels = []
        for cid in guild_cfg["channels"]:
            channel = guild.get_channel(cid)
            if channel:
                channels.append(channel)
        return channels

    @commands.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def setlog(self, ctx, channel: discord.TextChannel = None):
        """Active les logs dans le canal spécifié (ou canal courant)."""
        channel = channel or ctx.channel
        cfg = self._load_config()
        guild_cfg = cfg.setdefault(str(ctx.guild.id), {"channels": [], "categories": dict(DEFAULT_CATEGORIES)})
        if channel.id in guild_cfg["channels"]:
            await ctx.send(f"Les logs sont déjà activés dans {channel.mention}.")
            return
        guild_cfg["channels"].append(channel.id)
        self._save_config(cfg)
        await ctx.send(f"Logs activés dans {channel.mention}.")

    @commands.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def unsetlog(self, ctx, channel: discord.TextChannel = None):
        """Désactive les logs dans le canal spécifié (ou canal courant)."""
        channel = channel or ctx.channel
        cfg = self._load_config()
        guild_cfg = cfg.setdefault(str(ctx.guild.id), {"channels": [], "categories": dict(DEFAULT_CATEGORIES)})
        if channel.id not in guild_cfg["channels"]:
            await ctx.send(f"Les logs ne sont pas activés dans {channel.mention}.")
            return
        guild_cfg["channels"] = [cid for cid in guild_cfg["channels"] if cid != channel.id]
        self._save_config(cfg)
        await ctx.send(f"Logs désactivés dans {channel.mention}.")

    @commands.command()
    async def listlogs(self, ctx):
        """Liste les canaux et catégories configurés pour les logs sur ce serveur."""
        guild_cfg = self.get_guild_config(ctx.guild.id)
        if not guild_cfg["channels"]:
            await ctx.send("Aucun canal de logs configuré pour ce serveur.")
            return
        mentions = []
        for cid in guild_cfg["channels"]:
            channel = ctx.guild.get_channel(cid) if ctx.guild else None
            mentions.append(channel.mention if channel else f"<#{cid}>")
        categories = ", ".join(
            f"{label.split(' (')[0]}: {'on' if guild_cfg['categories'].get(key, True) else 'off'}"
            for key, label in LOG_CATEGORIES.items()
        )
        await ctx.send(
            "Canaux de logs configurés: " + ", ".join(mentions) + "\nCatégories: " + categories
        )

    def build_panel_embed(self, guild):
        guild_cfg = self.get_guild_config(guild.id)
        embed = discord.Embed(title="Panneau des logs", color=discord.Color.blurple())
        if guild_cfg["channels"]:
            mentions = []
            for cid in guild_cfg["channels"]:
                channel = guild.get_channel(cid)
                mentions.append(channel.mention if channel else f"<#{cid}>")
            embed.add_field(name="Canaux", value=", ".join(mentions), inline=False)
        else:
            embed.add_field(name="Canaux", value="Aucun (utilisez `,setlog`)", inline=False)

        for key, label in LOG_CATEGORIES.items():
            state = "✅ activé" if guild_cfg["categories"].get(key, True) else "❌ désactivé"
            embed.add_field(name=label, value=state, inline=False)
        return embed

    @commands.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def logspanel(self, ctx):
        """Ouvre un panneau interactif pour choisir les catégories envoyées dans les logs."""
        view = LogsPanelView(self, ctx.guild.id, ctx.author.id)
        await ctx.send(embed=self.build_panel_embed(ctx.guild), view=view)


class LogsPanelView(discord.ui.View):
    def __init__(self, cog: cmdlogs, guild_id: int, author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.author_id = author_id
        for key, label in LOG_CATEGORIES.items():
            self.add_item(self._make_toggle_button(key, label))

    def _make_toggle_button(self, key: str, label: str):
        short_label = f"Toggle {label.split(' (')[0]}"
        button = discord.ui.Button(label=short_label, style=discord.ButtonStyle.primary, row=0)

        async def callback(interaction: discord.Interaction):
            cfg = self.cog._load_config()
            guild_cfg = cfg.setdefault(str(self.guild_id), {"channels": [], "categories": dict(DEFAULT_CATEGORIES)})
            guild_cfg["categories"][key] = not guild_cfg["categories"].get(key, True)
            self.cog._save_config(cfg)
            await interaction.response.edit_message(embed=self.cog.build_panel_embed(interaction.guild), view=self)

        button.callback = callback
        return button

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Seul l'auteur de la commande peut modifier ce panneau.",
                ephemeral=True,
            )
            return False
        permissions = interaction.user.guild_permissions
        if not permissions.manage_guild:
            await interaction.response.send_message(
                "Permission manquante: Manage Server.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Canal logs = ici", style=discord.ButtonStyle.secondary, row=1)
    async def set_log_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog._load_config()
        guild_cfg = cfg.setdefault(str(self.guild_id), {"channels": [], "categories": dict(DEFAULT_CATEGORIES)})
        if interaction.channel_id not in guild_cfg["channels"]:
            guild_cfg["channels"].append(interaction.channel_id)
            self.cog._save_config(cfg)
        await interaction.response.edit_message(embed=self.cog.build_panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, row=1)
    async def close_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)


def setup(bot):
    bot.add_cog(cmdlogs(bot))
