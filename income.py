import discord
import json
import os
import asyncio
import time
from discord.ext import commands


DEFAULT_INCOME_CONFIG = {
    "collect_enabled": True,
    "default_amount": 100.0,
    "default_interval_hours": 24,
    "log_channel_id": None,
}


class IncomePanelView(discord.ui.View):
    def __init__(self, cog, guild_id: int, author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Seul l'auteur de la commande peut modifier ce panneau.",
                ephemeral=True,
            )
            return False
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Permission manquante: Manage Server.",
                ephemeral=True,
            )
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        cfg = self.cog.get_income_config(interaction.guild.id)
        embed = self.cog.build_income_panel_embed(interaction.guild, cfg)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle collecte", style=discord.ButtonStyle.primary, row=0)
    async def toggle_collect(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_income_config(self.guild_id)
        cfg["collect_enabled"] = not cfg["collect_enabled"]
        self.cog.save_income_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Montant defaut +10", style=discord.ButtonStyle.secondary, row=0)
    async def amount_plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_income_config(self.guild_id)
        cfg["default_amount"] = round(float(cfg["default_amount"]) + 10.0, 2)
        self.cog.save_income_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Montant defaut -10", style=discord.ButtonStyle.secondary, row=0)
    async def amount_minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_income_config(self.guild_id)
        cfg["default_amount"] = max(1.0, round(float(cfg["default_amount"]) - 10.0, 2))
        self.cog.save_income_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Intervalle +1h", style=discord.ButtonStyle.secondary, row=1)
    async def interval_plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_income_config(self.guild_id)
        cfg["default_interval_hours"] = int(cfg["default_interval_hours"]) + 1
        self.cog.save_income_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Intervalle -1h", style=discord.ButtonStyle.secondary, row=1)
    async def interval_minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_income_config(self.guild_id)
        cfg["default_interval_hours"] = max(1, int(cfg["default_interval_hours"]) - 1)
        self.cog.save_income_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Canal logs = ici", style=discord.ButtonStyle.secondary, row=1)
    async def set_log_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_income_config(self.guild_id)
        cfg["log_channel_id"] = interaction.channel_id
        self.cog.save_income_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=2)
    async def reset_defaults(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.income_config[str(self.guild_id)] = dict(DEFAULT_INCOME_CONFIG)
        self.cog.save_income_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, row=2)
    async def close_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        cfg = self.cog.get_income_config(interaction.guild.id)
        embed = self.cog.build_income_panel_embed(interaction.guild, cfg)
        embed.set_footer(text="Panneau ferme")
        await interaction.response.edit_message(embed=embed, view=self)

class cmdincome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()
        self.role_income_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'income.json')
        self.role_income = {}
        self.tags_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'balances.json')
        self.income_config_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'income_config.json')

        # Charger les données depuis le fichier 'income.json'
        with open(self.role_income_path, 'r') as f:
            self.role_income = json.load(f)    

        # Charger les données depuis le fichier 'balances.json'
        with open(self.tags_path, 'r') as f:
            self.balances = json.load(f)

        self.income_config = self.load_income_config()

    def load_income_config(self):
        if not os.path.exists(self.income_config_path):
            return {}
        try:
            with open(self.income_config_path, 'r') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def save_income_config(self):
        with open(self.income_config_path, 'w') as f:
            json.dump(self.income_config, f, indent=4)

    def get_income_config(self, guild_id: int):
        key = str(guild_id)
        if key not in self.income_config or not isinstance(self.income_config[key], dict):
            self.income_config[key] = dict(DEFAULT_INCOME_CONFIG)
            self.save_income_config()
        else:
            for cfg_key, cfg_default in DEFAULT_INCOME_CONFIG.items():
                if cfg_key not in self.income_config[key]:
                    self.income_config[key][cfg_key] = cfg_default
            self.save_income_config()
        return self.income_config[key]

    async def send_income_log(self, guild: discord.Guild, message: str):
        cfg = self.get_income_config(guild.id)
        channel_id = cfg.get("log_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel:
            await channel.send(message)

    def build_income_panel_embed(self, guild: discord.Guild, cfg: dict):
        channel_id = cfg.get("log_channel_id")
        log_channel = guild.get_channel(channel_id) if channel_id else None
        log_label = f"#{log_channel.name}" if log_channel else "Non defini"

        embed = discord.Embed(
            title="Panneau Revenus Passifs",
            description="Configuration des revenus passifs et de la collecte.",
            color=discord.Color.teal(),
        )
        embed.add_field(name="Collecte active", value="Oui" if cfg["collect_enabled"] else "Non", inline=True)
        embed.add_field(name="Montant defaut", value=f"{float(cfg['default_amount']):.2f}", inline=True)
        embed.add_field(name="Intervalle defaut", value=f"{int(cfg['default_interval_hours'])}h", inline=True)
        embed.add_field(name="Canal logs", value=log_label, inline=False)
        embed.set_footer(text=f"Serveur: {guild.name}")
        return embed

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def incomepanel(self, ctx):
        cfg = self.get_income_config(ctx.guild.id)
        embed = self.build_income_panel_embed(ctx.guild, cfg)
        view = IncomePanelView(self, ctx.guild.id, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def role_income_add(self, ctx, role_id: int, amount: float = None, collect_interval: str = None):
        cfg = self.get_income_config(ctx.guild.id)
        if amount is None:
            amount = float(cfg["default_amount"])
        if collect_interval is None:
            collect_interval = f"{int(cfg['default_interval_hours'])}h"
        role = discord.utils.get(ctx.guild.roles, id=role_id)
        if role is None:
            await ctx.send(f"Le rôle avec l'ID {role_id} n'existe pas sur ce serveur.")
            return
        # Vérifier si le rôle n'est pas déjà dans la liste des rôles avec gains associés
        if str(role.id) in self.role_income:
            await ctx.send(f"Le rôle {role_id} a déjà un gain associé.")
            return

        # Extraire le nombre d'heures de collect_interval et le convertir en secondes
        try:
            hours = int(collect_interval.replace("h", ""))
            collect_interval_sec = hours * 3600
        except ValueError:
            await ctx.send("Le temps de collecte doit être un nombre entier suivi de la lettre 'h'. Exemple: 12h")
            return

        # Ajouter le rôle et le gain associé à la liste
        self.role_income[str(role.id)] = {
            "name": role.name,
            "amount": amount,
            "collect_interval": collect_interval_sec,
            "last_collect": 0
        }
        with open(self.role_income_path, 'w') as f:
            json.dump(self.role_income, f, indent=4)

        await ctx.send(f"Le rôle {role.name} a été ajouté à la liste des rôles avec un gain de : {amount} collectable toutes les {collect_interval} heures.")
        await self.send_income_log(ctx.guild, f"[INCOME] role_income_add role={role.name} amount={amount} interval={collect_interval} par {ctx.author.mention}")


    @commands.command()
    async def role_income_remove(self, ctx, role_id: int):
        # Vérifier si le rôle est dans la liste des rôles avec gains associés
        if str(role_id) not in self.role_income:
            await ctx.send(f"Le rôle {role_id} n'a pas de gain associé.")
            return
        
        # Supprimer le rôle de la liste
        del self.role_income[str(role_id)]
        with open(self.role_income_path, 'w') as f:
            json.dump(self.role_income, f, indent=4)
        
        await ctx.send(f"Le rôle {role_id} a été supprimé de la liste des rôles avec gains associés.")
        await self.send_income_log(ctx.guild, f"[INCOME] role_income_remove role_id={role_id} par {ctx.author.mention}")

    @commands.command()
    async def role_income_list(self, ctx):
        # Vérifier s'il y a des rôles avec gains associés
        if not self.role_income:
            await ctx.send("Il n'y a pas de rôle avec un gain associé.")
            return
        
        # Construire une liste de chaînes de caractères pour chaque rôle avec son gain associé
        role_list = []
        for role_id, role_data in self.role_income.items():
            role_list.append(f"{role_data['name']} : {role_data['amount']} collectable toutes les {role_data['collect_interval']//3600} heures.")
        
        # Envoyer la liste des rôles avec gains associés
        await ctx.send("Liste des rôles avec gains associés :\n" + "\n".join(role_list))

    @commands.command()
    async def role_income_edit(self, ctx, role_id: int, amount: float, collect_interval: str):
        # Vérifier si le rôle existe dans la liste des rôles avec gains associés
        if str(role_id) not in self.role_income:
            await ctx.send(f"Le rôle {role_id} n'a pas de gain associé.")
            return

        # Extraire le nombre d'heures de collect_interval et le convertir en secondes
        try:
            hours = int(collect_interval.replace("h", ""))
            collect_interval_sec = hours * 3600
        except ValueError:
            await ctx.send("Le temps de collecte doit être un nombre entier suivi de la lettre 'h'. Exemple: 12h")
            return

        # Modifier le rôle et le gain associé dans la liste
        self.role_income[str(role_id)]["amount"] = amount
        self.role_income[str(role_id)]["collect_interval"] = collect_interval_sec
        with open(self.role_income_path, 'w') as f:
            json.dump(self.role_income, f, indent=4)

        await ctx.send(f"Le gain associé au rôle {role_id} a été modifié : {amount} par collecte toutes les {collect_interval} heures.")
        await self.send_income_log(ctx.guild, f"[INCOME] role_income_edit role_id={role_id} amount={amount} interval={collect_interval} par {ctx.author.mention}")


    @commands.command()
    async def collect_income(self, ctx):
        cfg = self.get_income_config(ctx.guild.id)
        if not cfg["collect_enabled"]:
            await ctx.send("La collecte de revenus passifs est desactivee sur ce serveur.")
            return
        # Récupérer l'utilisateur qui a lancé la commande
        member = ctx.author

        # Vérifier si l'utilisateur a un compte
        if str(member.id) not in self.balances:
            await ctx.send(f"{member.mention}, vous n'avez pas de compte. Utilisez la commande `,addmoney` pour en créer un.")
            return

        # Recharger les données depuis le fichier 'balances.json'
        with open(self.tags_path, 'r') as f:
            self.balances = json.load(f)

        current_time = time.time()
        collected_any = False

        for role_id, role_data in self.role_income.items():
            # Vérifier si l'utilisateur possède ce rôle
            role = ctx.guild.get_role(int(role_id))
            if role is None or role not in member.roles:
                continue

            if current_time - role_data["last_collect"] >= role_data["collect_interval"]:
                # Ajouter le gain associé au solde de l'utilisateur
                self.balances[str(member.id)] += role_data["amount"]
                role_data["last_collect"] = current_time

                # Enregistrer les données mises à jour dans les fichiers json
                with open(self.tags_path, 'w') as f:
                    json.dump(self.balances, f, indent=4)
                with open(self.role_income_path, 'w') as f:
                    json.dump(self.role_income, f, indent=4)

                await ctx.send(f"{member.mention}, vous avez collecté **{role_data['amount']:.2f}** pièces grâce à votre rôle **{role_data['name']}**. Nouveau solde : **{self.balances[str(member.id)]:.2f}** pièces.")
                collected_any = True
            else:
                time_left = role_data["collect_interval"] - (current_time - role_data["last_collect"])
                hours_left = int(time_left // 3600)
                minutes_left = int((time_left % 3600) // 60)
                await ctx.send(f"{member.mention}, vous devez attendre encore **{hours_left}h {minutes_left}min** avant de collecter votre gain pour le rôle **{role_data['name']}**.")
                collected_any = True

        if not collected_any:
            await ctx.send(f"{member.mention}, vous n'avez aucun rôle avec un gain passif associé.")

def setup(bot):
    bot.add_cog(cmdincome(bot))

