import json
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

    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    def get_guild_config(self, guild_id: int) -> dict:
        row = self.db.fetchone("SELECT config_json FROM logs_config WHERE guild_id = ?", (guild_id,))
        if row is None:
            cfg = {"channels": [], "categories": dict(DEFAULT_CATEGORIES)}
            self.db.execute(
                "INSERT INTO logs_config (guild_id, config_json) VALUES (?, ?)",
                (guild_id, json.dumps(cfg)),
            )
            return cfg

        cfg = json.loads(row["config_json"])
        changed = False
        if "channels" not in cfg:
            cfg["channels"] = []
            changed = True
        categories = cfg.setdefault("categories", {})
        for key, default in DEFAULT_CATEGORIES.items():
            if key not in categories:
                categories[key] = default
                changed = True
        if changed:
            self.save_guild_config(guild_id, cfg)
        return cfg

    def save_guild_config(self, guild_id: int, cfg: dict):
        self.db.execute(
            "INSERT INTO logs_config (guild_id, config_json) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET config_json = excluded.config_json",
            (guild_id, json.dumps(cfg)),
        )

    def get_channels(self, guild, category: str):
        """Renvoie les salons configurés pour recevoir la catégorie de log donnée."""
        if guild is None or category not in LOG_CATEGORIES:
            return []
        guild_cfg = self.get_guild_config(guild.id)
        if not guild_cfg["categories"].get(category, True):
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
        guild_cfg = self.get_guild_config(ctx.guild.id)
        if channel.id in guild_cfg["channels"]:
            await ctx.send(f"Les logs sont déjà activés dans {channel.mention}.")
            return
        guild_cfg["channels"].append(channel.id)
        self.save_guild_config(ctx.guild.id, guild_cfg)
        await ctx.send(f"Logs activés dans {channel.mention}.")

    @commands.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def unsetlog(self, ctx, channel: discord.TextChannel = None):
        """Désactive les logs dans le canal spécifié (ou canal courant)."""
        channel = channel or ctx.channel
        guild_cfg = self.get_guild_config(ctx.guild.id)
        if channel.id not in guild_cfg["channels"]:
            await ctx.send(f"Les logs ne sont pas activés dans {channel.mention}.")
            return
        guild_cfg["channels"] = [cid for cid in guild_cfg["channels"] if cid != channel.id]
        self.save_guild_config(ctx.guild.id, guild_cfg)
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
            guild_cfg = self.cog.get_guild_config(self.guild_id)
            guild_cfg["categories"][key] = not guild_cfg["categories"].get(key, True)
            self.cog.save_guild_config(self.guild_id, guild_cfg)
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
        guild_cfg = self.cog.get_guild_config(self.guild_id)
        if interaction.channel_id not in guild_cfg["channels"]:
            guild_cfg["channels"].append(interaction.channel_id)
            self.cog.save_guild_config(self.guild_id, guild_cfg)
        await interaction.response.edit_message(embed=self.cog.build_panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, row=1)
    async def close_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)


def setup(bot, db):
    bot.add_cog(cmdlogs(bot, db))
