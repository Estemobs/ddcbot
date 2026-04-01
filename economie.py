import discord
import json
import os
from discord.ext import commands


DEFAULT_ECO_CONFIG = {
    "allow_transfers": True,
    "max_transfer": 10000,
    "allow_negative_balances": False,
    "log_channel_id": None,
}


class EconomyPanelView(discord.ui.View):
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
        cfg = self.cog.get_eco_config(interaction.guild.id)
        embed = self.cog.build_eco_panel_embed(interaction.guild, cfg)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle transferts", style=discord.ButtonStyle.primary, row=0)
    async def toggle_transfers(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_eco_config(self.guild_id)
        cfg["allow_transfers"] = not cfg["allow_transfers"]
        self.cog.save_eco_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Max transfert +500", style=discord.ButtonStyle.secondary, row=0)
    async def max_plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_eco_config(self.guild_id)
        cfg["max_transfer"] += 500
        self.cog.save_eco_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Max transfert -500", style=discord.ButtonStyle.secondary, row=0)
    async def max_minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_eco_config(self.guild_id)
        cfg["max_transfer"] = max(1, cfg["max_transfer"] - 500)
        self.cog.save_eco_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Toggle solde negatif", style=discord.ButtonStyle.primary, row=1)
    async def toggle_negative(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_eco_config(self.guild_id)
        cfg["allow_negative_balances"] = not cfg["allow_negative_balances"]
        self.cog.save_eco_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Canal logs = ici", style=discord.ButtonStyle.secondary, row=1)
    async def set_log_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_eco_config(self.guild_id)
        cfg["log_channel_id"] = interaction.channel_id
        self.cog.save_eco_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=1)
    async def reset_defaults(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.eco_config[str(self.guild_id)] = dict(DEFAULT_ECO_CONFIG)
        self.cog.save_eco_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, row=2)
    async def close_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        cfg = self.cog.get_eco_config(interaction.guild.id)
        embed = self.cog.build_eco_panel_embed(interaction.guild, cfg)
        embed.set_footer(text="Panneau ferme")
        await interaction.response.edit_message(embed=embed, view=self)

class cmdeco(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()

        self.tags_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'balances.json')
        self.eco_config_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'economy_config.json')

        # Charger les données depuis le fichier 'balances.json'
        with open(self.tags_path, 'r') as f:
            self.balances = json.load(f)

        self.eco_config = self.load_eco_config()

    def load_eco_config(self):
        if not os.path.exists(self.eco_config_path):
            return {}
        try:
            with open(self.eco_config_path, 'r') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def save_eco_config(self):
        with open(self.eco_config_path, 'w') as f:
            json.dump(self.eco_config, f, indent=4)

    def get_eco_config(self, guild_id: int):
        key = str(guild_id)
        if key not in self.eco_config or not isinstance(self.eco_config[key], dict):
            self.eco_config[key] = dict(DEFAULT_ECO_CONFIG)
            self.save_eco_config()
        else:
            for cfg_key, cfg_default in DEFAULT_ECO_CONFIG.items():
                if cfg_key not in self.eco_config[key]:
                    self.eco_config[key][cfg_key] = cfg_default
            self.save_eco_config()
        return self.eco_config[key]

    async def send_eco_log(self, guild: discord.Guild, message: str):
        cfg = self.get_eco_config(guild.id)
        channel_id = cfg.get("log_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel:
            await channel.send(message)

    def build_eco_panel_embed(self, guild: discord.Guild, cfg: dict):
        channel_id = cfg.get("log_channel_id")
        log_channel = guild.get_channel(channel_id) if channel_id else None
        log_label = f"#{log_channel.name}" if log_channel else "Non defini"

        embed = discord.Embed(
            title="Panneau Economie",
            description="Configuration globale de l'economie du serveur.",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Transferts entre membres", value="Actif" if cfg["allow_transfers"] else "Desactive", inline=True)
        embed.add_field(name="Max transfert", value=str(cfg["max_transfer"]), inline=True)
        embed.add_field(name="Solde negatif", value="Autorise" if cfg["allow_negative_balances"] else "Interdit", inline=True)
        embed.add_field(name="Canal logs", value=log_label, inline=False)
        embed.set_footer(text=f"Serveur: {guild.name}")
        return embed

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def ecopanel(self, ctx):
        cfg = self.get_eco_config(ctx.guild.id)
        embed = self.build_eco_panel_embed(ctx.guild, cfg)
        view = EconomyPanelView(self, ctx.guild.id, ctx.author.id)
        await ctx.send(embed=embed, view=view)



    @commands.command()
    async def mybalance(self, ctx):
        member = ctx.author
        if str(member.id) not in self.balances:
            self.balances[str(member.id)] = 0
            with open(self.tags_path, 'w') as f:
                json.dump(self.balances, f, indent=4)
            await ctx.send(f'Votre solde est de **0.00** pièces.')
        else:
            await ctx.send(f'Votre solde est de **{self.balances[str(member.id)]:.2f}** pièces.')

    @commands.command()
    async def balance(self, ctx, member: discord.Member):
            # Vérifier si l'utilisateur a déjà un compte
            if str(member.id) not in self.balances:
                # Créer un compte pour l'utilisateur avec un solde de 0
                self.balances[str(member.id)] = 0
                with open(self.tags_path, 'w') as f:
                    json.dump(self.balances, f, indent=4)
                await ctx.send(f'Un compte a été créé pour {member.mention} avec un solde de {self.balances[str(member.id)]:.2f}.')
            else:
                # Afficher le solde de l'utilisateur
                await ctx.send(f'{member.mention} a un solde de {self.balances[str(member.id)]:.2f}.')


    @commands.command()
    async def addmoney(self, ctx, member: discord.Member, amount: float):
        if amount <= 0:
            await ctx.send("Le montant doit etre superieur a 0.")
            return
        # Récupérer le solde actuel de l'utilisateur
        if str(member.id) not in self.balances:
            # Si l'utilisateur n'a pas de compte, créer un compte avec le montant spécifié
            self.balances[str(member.id)] = amount
            with open(self.tags_path, 'w') as f:
                json.dump(self.balances, f, indent=4)
            await ctx.send(f'Un compte a été créé pour {member.mention} avec un solde de {amount:.2f}.')
        else:
            # Ajouter le montant spécifié au solde actuel de l'utilisateur
            self.balances[str(member.id)] += amount
            with open(self.tags_path, 'w') as f:
                json.dump(self.balances, f, indent=4)
            await ctx.send(f'{amount:.2f} a été ajouté au compte de {member.mention}. Nouveau solde : {self.balances[str(member.id)]:.2f}.')
        await self.send_eco_log(ctx.guild, f"[ECO] +{amount:.2f} pour {member.mention} par {ctx.author.mention}")


    @commands.command()
    async def removemoney(self, ctx, member: discord.Member, amount: float):
        if amount <= 0:
            await ctx.send("Le montant doit etre superieur a 0.")
            return
        # Vérifier si l'utilisateur a un compte
        if str(member.id) not in self.balances:
            await ctx.send(f"{member.mention} n'a pas de compte.")
        else:
            cfg = self.get_eco_config(ctx.guild.id)
            # Vérifier si l'utilisateur a suffisamment de fonds pour retirer le montant spécifié
            if cfg["allow_negative_balances"] or self.balances[str(member.id)] >= amount:
                # Retirer le montant spécifié du solde actuel de l'utilisateur
                self.balances[str(member.id)] -= amount
                with open(self.tags_path, 'w') as f:
                    json.dump(self.balances, f, indent=4)
                await ctx.send(f'{amount:.2f} a été retiré du compte de {member.mention}. Nouveau solde : {self.balances[str(member.id)]:.2f}.')
                await self.send_eco_log(ctx.guild, f"[ECO] -{amount:.2f} pour {member.mention} par {ctx.author.mention}")
            else:
                await ctx.send(f"{member.mention} n'a pas suffisamment de fonds pour retirer {amount:.2f}. Solde actuel : {self.balances[str(member.id)]:.2f}.")

    @commands.command()
    async def paye(self, ctx, member: discord.Member, amount: float):
        cfg = self.get_eco_config(ctx.guild.id)
        if not cfg["allow_transfers"]:
            await ctx.send("Les transferts entre membres sont desactives sur ce serveur.")
            return
        if amount <= 0:
            await ctx.send("Le montant doit etre superieur a 0.")
            return
        if amount > cfg["max_transfer"]:
            await ctx.send(f"Montant trop eleve. Maximum autorise: {cfg['max_transfer']}.")
            return
        # Vérifier si l'utilisateur a un compte
        if str(ctx.author.id) not in self.balances:
            await ctx.send(f"Vous n'avez pas de compte.")
        else:
            # Vérifier si l'utilisateur a suffisamment d'argent pour donner le montant spécifié
            if self.balances[str(ctx.author.id)] < amount:
                await ctx.send(f"Vous n'avez pas suffisamment d'argent sur votre compte.")
            else:
                # Ajouter le montant spécifié au compte de l'utilisateur cible
                if str(member.id) not in self.balances:
                    self.balances[str(member.id)] = amount
                else:
                    self.balances[str(member.id)] += amount
                # Retirer le montant spécifié du compte de l'utilisateur source
                self.balances[str(ctx.author.id)] -= amount
                with open(self.tags_path, 'w') as f:
                    json.dump(self.balances, f, indent=4)
                await ctx.send(f"{amount:.2f} a été donné à {member.mention}. Votre nouveau solde est : {self.balances[str(ctx.author.id)]:.2f}.")
                await self.send_eco_log(ctx.guild, f"[ECO] transfert {amount:.2f} de {ctx.author.mention} vers {member.mention}")


    @commands.command()
    async def leaderboard(self, ctx):
        # Récupérer les soldes de tous les utilisateurs ayant un compte
        filtered_balances = {k: v for k, v in self.balances.items() if k.isdigit() and v > 0}
        sorted_balances = sorted(filtered_balances.items(), key=lambda x: x[1], reverse=True)[:10] # Prendre les 10 premiers résultats
        # Créer l'embed
        embed = discord.Embed(title="Top 10 des utilisateurs les plus riches :", color=0xffd700)
        for i, (user_id, balance) in enumerate(sorted_balances):
            member = ctx.guild.get_member(int(user_id))
            if member:
                embed.add_field(name=f"{i+1}. {member.display_name}", value=f"{balance:.2f}", inline=False)
        await ctx.send(embed=embed)


    @commands.command()
    async def clean_leaderboard(self, ctx):
        # Récupérer la liste des utilisateurs actuels du serveur
        server_users = [member.id for member in ctx.guild.members]
        
        # Récupérer le leaderboard actuel
        with open(self.tags_path, 'r') as f:
            self.balances = json.load(f)
            
        # Créer une copie du leaderboard pour itérer sans danger de modification
        for user_id in list(self.balances.keys()):
            # Vérifier si l'utilisateur n'est plus sur le serveur
            if int(user_id) not in server_users:
                # Retirer l'utilisateur du leaderboard
                del self.balances[user_id]
                
        # Enregistrer les modifications au fichier
        with open(self.tags_path, 'w') as f:
            json.dump(self.balances, f, indent=4)
            
        await ctx.send("Le leaderboard a été nettoyé.")

    @commands.command()
    async def reset_money(self, ctx, member: discord.Member):
        # Vérifier si l'utilisateur a un compte
        if str(member.id) not in self.balances:
            await ctx.send(f"{member.mention} n'a pas de compte.")
        else:
            # Réinitialiser le solde de l'utilisateur
            self.balances[str(member.id)] = 0.0
            with open(self.tags_path, 'w') as f:
                json.dump(self.balances, f, indent=4)
            await ctx.send(f"Le solde de {member.mention} a été réinitialisé.")

    @commands.command()
    async def reset_economy(self, ctx):
        for user_id in self.balances:
            self.balances[user_id] = 0.0
        with open(self.tags_path, 'w') as f:
            json.dump(self.balances, f, indent=4)
        await ctx.send("Les comptes de tous les utilisateurs ont été remis à zéro.")

def setup(bot):
    bot.add_cog(cmdeco(bot))