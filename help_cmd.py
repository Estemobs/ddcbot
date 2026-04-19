import discord
from discord.ext import commands


def get_categories(prefix: str = ",") -> dict:
    return {
        "moderation": {
            "emoji": "🔨",
            "title": "Modération",
            "commands": [
                ("`warn <membre> <raison>`", "Avertir un membre"),
                ("`modpanel`", "Ouvrir le panneau complet de configuration moderation"),
                ("`warnconfig`", "Alias de `modpanel`"),
                ("`permpanel`", "Configurer les roles autorises pour chaque commande admin"),
                ("`warns [membre]`", "Voir le nombre de warns"),
                ("`clearwarns <membre>`", "Reinitialiser les warns d'un membre"),
                ("`ban <membre> <raison>`", "Bannir un membre"),
                ("`kick <membre> [raison]`", "Expulser un membre"),
                ("`clear [nombre]`", "Supprimer N messages (ou valeur par defaut)"),
                ("`unban <user_id> [raison]`", "Debannir un utilisateur"),
                ("`timeout <membre> [minutes] [raison]`", "Timeout un membre"),
                ("`untimeout <membre> [raison]`", "Retirer un timeout"),
                ("`slowmode <secondes>`", "Definir le slowmode du salon"),
                ("`lock`", "Verrouiller le salon"),
                ("`unlock`", "Deverrouiller le salon"),
            ],
        },
        "utilite": {
            "emoji": "🛠️",
            "title": "Utilité",
            "commands": [
                ("`role_id <nom_rôle>`", "Obtenir l'ID d'un rôle"),
                ("`role_name <id_rôle>`", "Obtenir le nom d'un rôle"),
                ("`rmd <durée> <message>`", "Créer un rappel (ex: `,rmd 30m réveil`)"),
                ("`avatar <membre>`", "Afficher l'avatar d'un membre"),
                ("`serverpicture`", "Afficher l'icône du serveur"),
                ("`devoir`", "OCR + reponse IA depuis une image"),
                ("`selftest [deep]`", "Diagnostic global du bot (mode standard ou approfondi) *(admin)*"),
            ],
        },
        "economie": {
            "emoji": "💰",
            "title": "Économie",
            "commands": [
                ("`mybalance`", "Voir son propre solde"),
                ("`balance <membre>`", "Voir le solde d'un membre"),
                ("`paye <membre> <montant>`", "Payer un autre membre"),
                ("`leaderboard`", "Top 10 des membres les plus riches"),
                ("`addmoney <membre> <montant>`", "Ajouter de l'argent *(admin)*"),
                ("`removemoney <membre> <montant>`", "Retirer de l'argent *(admin)*"),
                ("`reset_money <membre>`", "Réinitialiser le solde d'un membre *(admin)*"),
                ("`reset_economy`", "Réinitialiser toute l'économie *(admin)*"),
                ("`clean_leaderboard`", "Nettoyer le leaderboard des membres partis"),
                ("`ecopanel`", "Configurer la partie economie (transferts, limites, logs)"),
            ],
        },
        "travail": {
            "emoji": "💼",
            "title": "Travail",
            "commands": [
                ("`work`", "Travailler pour gagner des pièces"),
                ("`show_work_config`", "Voir la configuration du travail"),
                (
                    "`config_work <min> <max> <paliers> <cooldown_h> <récompenses...>`",
                    "Configurer la commande work *(admin)*",
                ),
            ],
        },
        "revenus": {
            "emoji": "📈",
            "title": "Revenus passifs",
            "commands": [
                ("`incomepanel`", "Panneau de configuration des revenus passifs *(admin)*"),
                ("`collect_income`", "Collecter ses revenus passifs"),
                ("`role_income_list`", "Lister les rôles avec revenus"),
                ("`role_income_add <id_rôle> <montant> <intervalle>`", "Ajouter un revenu à un rôle *(admin)*"),
                ("`role_income_remove <id_rôle>`", "Supprimer un revenu de rôle *(admin)*"),
                ("`role_income_edit <id_rôle> <montant> <intervalle>`", "Modifier un revenu de rôle *(admin)*"),
            ],
        },
        "jeux": {
            "emoji": "🎰",
            "title": "Jeux / Lootbox",
            "commands": [
                ("`gamepanel`", "Panneau de configuration des jeux / lootbox *(admin)*"),
                ("`shop`", "Voir les jeux disponibles"),
                ("`openlot`", "Ouvrir un lot (ticket ou pièces)"),
                ("`inventaire`", "Voir ses tickets"),
                ("`quest`", "Voir les quêtes actives et leur progression"),
                ("`addgame`", "Créer un nouveau jeu *(admin)*"),
                ("`deletegame`", "Supprimer un jeu *(admin)*"),
                ("`addquest`", "Ajouter une quête à un jeu *(admin)*"),
                ("`deletequete`", "Supprimer une quête *(admin)*"),
                ("`config_quete`", "Voir la configuration complète des quêtes *(admin)*"),
                ("`clearinventory [membre]`", "Vider l'inventaire d'un membre *(admin)*"),
            ],
        },
        "musique": {
            "emoji": "🎵",
            "title": "Musique",
            "commands": [
                ("`musicpanel`", "Panneau interactif de contrôle de la musique"),
                ("`join`", "Connecter le bot à votre salon vocal"),
                ("`play <url/source>`", "Ajouter et lire une piste"),
                ("`queue`", "Afficher la file d'attente"),
                ("`nowplaying`", "Afficher la piste en cours"),
                ("`pause`", "Mettre en pause la lecture"),
                ("`resume`", "Reprendre la lecture"),
                ("`skip`", "Passer à la piste suivante"),
                ("`stop`", "Stopper la lecture et vider la file"),
                ("`leave`", "Déconnecter le bot du vocal"),
            ],
        },
        "giveaway": {
            "emoji": "🎁",
            "title": "Giveaway",
            "commands": [
                ("`gstart <durée_s> <prix>`", "Démarrer un giveaway *(admin)*"),
                ("`gend`", "Terminer un giveaway et tirer un gagnant *(admin)*"),
                ("`gcancel`", "Annuler un giveaway en cours *(admin)*"),
            ],
        },
        "notifications": {
            "emoji": "📺",
            "title": "Notifications séries",
            "commands": [
                ("`subscribe`", "S'abonner aux notifications d'une série"),
                ("`notifications`", "Voir ses abonnements actifs"),
                ("`delnotif`", "Supprimer un abonnement"),
            ],
        },
    }


def build_home_embed(prefix: str, categories: dict) -> discord.Embed:
    embed = discord.Embed(
        title="📖 Centre de commandes",
        description=f"Choisissez une catégorie dans le menu ci-dessous.\nPréfixe actuel: `{prefix}`",
        color=0x7289DA,
    )
    for key, cat in categories.items():
        first_cmd = cat["commands"][0][0].split()[0].strip("`")
        embed.add_field(
            name=f"{cat['emoji']} {cat['title']}",
            value=f"Catégorie: `{key}` • Exemple: `{prefix}{first_cmd}`",
            inline=False,
        )
    embed.set_footer(text="Version moderne interactive")
    return embed


def build_category_embed(prefix: str, key: str, cat: dict) -> discord.Embed:
    embed = discord.Embed(title=f"{cat['emoji']} {cat['title']}", color=0x7289DA)
    for cmd_syntax, description in cat["commands"]:
        embed.add_field(name=f"{prefix}{cmd_syntax}", value=description, inline=False)
    embed.set_footer(text=f"Catégorie: {key}")
    return embed


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, prefix: str, categories: dict):
        options = [
            discord.SelectOption(label=cat["title"], value=key, emoji=cat["emoji"])
            for key, cat in categories.items()
        ]
        super().__init__(placeholder="Sélectionnez une catégorie", min_values=1, max_values=1, options=options)
        self.prefix = prefix
        self.categories = categories

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        cat = self.categories[key]
        embed = build_category_embed(self.prefix, key, cat)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpMenuView(discord.ui.View):
    def __init__(self, author_id: int, prefix: str, categories: dict):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.prefix = prefix
        self.categories = categories
        self.add_item(HelpCategorySelect(prefix, categories))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Seul l'auteur peut utiliser ce menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accueil", style=discord.ButtonStyle.secondary, emoji="🏠")
    async def back_home(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_home_embed(self.prefix, self.categories)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, emoji="✖️")
    async def close_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else None
        if embed:
            embed.set_footer(text="Menu fermé")
        await interaction.response.edit_message(embed=embed, view=self)


class cmdhelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx, *, categorie: str = None):
        """Affiche la liste des commandes disponibles."""
        prefix = ","
        categories = get_categories(prefix)

        if categorie:
            key = categorie.lower()
            if key not in categories:
                valid = ", ".join(f"`{k}`" for k in categories.keys())
                await ctx.send(f"❌ Catégorie inconnue. Catégories disponibles : {valid}")
                return
            await ctx.send(embed=build_category_embed(prefix, key, categories[key]))
            return

        embed = build_home_embed(prefix, categories)
        view = HelpMenuView(ctx.author.id, prefix, categories)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="menu")
    async def menu_command(self, ctx):
        await self.help_command(ctx)


def setup(bot):
    bot.add_cog(cmdhelp(bot))
