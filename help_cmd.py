import discord
from discord.ext import commands


class cmdhelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx, *, categorie: str = None):
        """Affiche la liste des commandes disponibles."""

        categories = {
            "moderation": {
                "emoji": "🔨",
                "title": "Modération",
                "commands": [
                    ("`warn <membre> <raison>`", "Avertir un membre"),
                    ("`warnconfig`", "Ouvrir le panneau interactif de configuration des warns"),
                    ("`ban <membre> <raison>`", "Bannir un membre"),
                    ("`kick <membre> [raison]`", "Expulser un membre"),
                    ("`clear <nombre>`", "Supprimer N messages du salon"),
                    ("`unban <user_id> [raison]`", "Debannir un utilisateur"),
                    ("`timeout <membre> <minutes> [raison]`", "Timeout un membre"),
                    ("`untimeout <membre> [raison]`", "Retirer un timeout"),
                    ("`slowmode <secondes>`", "Definir le slowmode du salon"),
                    ("`lock`", "Verrouiller le salon"),
                    ("`unlock`", "Deverrouiller le salon"),
                ]
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
                ]
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
                ]
            },
            "travail": {
                "emoji": "💼",
                "title": "Travail",
                "commands": [
                    ("`work`", "Travailler pour gagner des pièces"),
                    ("`show_work_config`", "Voir la configuration du travail"),
                    ("`config_work <min> <max> <paliers> <cooldown_h> <récompenses...>`",
                     "Configurer la commande work *(admin)*"),
                ]
            },
            "revenus": {
                "emoji": "📈",
                "title": "Revenus passifs",
                "commands": [
                    ("`collect_income`", "Collecter ses revenus passifs"),
                    ("`role_income_list`", "Lister les rôles avec revenus"),
                    ("`role_income_add <id_rôle> <montant> <intervalle>`",
                     "Ajouter un revenu à un rôle *(admin)*"),
                    ("`role_income_remove <id_rôle>`", "Supprimer un revenu de rôle *(admin)*"),
                    ("`role_income_edit <id_rôle> <montant> <intervalle>`",
                     "Modifier un revenu de rôle *(admin)*"),
                ]
            },
            "jeux": {
                "emoji": "🎰",
                "title": "Jeux / Lootbox",
                "commands": [
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
                ]
            },
            "giveaway": {
                "emoji": "🎁",
                "title": "Giveaway",
                "commands": [
                    ("`gstart <durée_s> <prix>`", "Démarrer un giveaway *(admin)*"),
                    ("`gend`", "Terminer un giveaway et tirer un gagnant *(admin)*"),
                    ("`gcancel`", "Annuler un giveaway en cours *(admin)*"),
                ]
            },
            "notifications": {
                "emoji": "📺",
                "title": "Notifications séries",
                "commands": [
                    ("`subscribe`", "S'abonner aux notifications d'une série"),
                    ("`notifications`", "Voir ses abonnements actifs"),
                    ("`delnotif`", "Supprimer un abonnement"),
                ]
            },
        }

        prefix = ","

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
            embed.set_footer(text=f"Préfixe : {prefix}  •  ,help <catégorie> pour plus de détails")
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
        for key, cat in categories.items():
            cmd_list = ", ".join(f"`{prefix}{s.split()[0].strip('`')}`" for s, _ in cat["commands"])
            embed.add_field(
                name=f"{cat['emoji']} {cat['title']} — `{prefix}help {key}`",
                value=cmd_list,
                inline=False
            )
        embed.set_footer(text="*(admin)* = commande réservée aux administrateurs")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(cmdhelp(bot))
