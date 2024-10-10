import discord
import json
import os
from discord.ext import commands

class cmdeco(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()

        self.tags_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'balances.json')

        # Charger les données depuis le fichier 'balances.json'
        with open(self.tags_path, 'r') as f:
            self.balances = json.load(f)



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
    @commands.has_role(591683595043602436) # ID du rôle autorisé
    async def addmoney(self, ctx, member: discord.Member, amount: float):
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


    @commands.command()
    @commands.has_role(591683595043602436) # ID du rôle autorisé
    async def removemoney(self, ctx, member: discord.Member, amount: float):
        # Vérifier si l'utilisateur a un compte
        if str(member.id) not in self.balances:
            await ctx.send(f"{member.mention} n'a pas de compte.")
        else:
            # Vérifier si l'utilisateur a suffisamment de fonds pour retirer le montant spécifié
            if self.balances[str(member.id)] >= amount:
                # Retirer le montant spécifié du solde actuel de l'utilisateur
                self.balances[str(member.id)] -= amount
                with open(self.tags_path, 'w') as f:
                    json.dump(self.balances, f, indent=4)
                await ctx.send(f'{amount:.2f} a été retiré du compte de {member.mention}. Nouveau solde : {self.balances[str(member.id)]:.2f}.')
            else:
                await ctx.send(f"{member.mention} n'a pas suffisamment de fonds pour retirer {amount:.2f}. Solde actuel : {self.balances[str(member.id)]:.2f}.")

    @commands.command()
    async def paye(self, ctx, member: discord.Member, amount: float):
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
    @commands.has_role(591683595043602436)
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
    @commands.has_role(591683595043602436)
    async def reset_economy(self, ctx):
        global balances # Utilisez la variable globale définie dans le code précédent
        for user_id in self.balances:
            self.balances[user_id] = 0.0
        with open(self.tags_path, 'w') as f:
            json.dump(self.balances, f, indent=4)
        await ctx.send("Les comptes de tous les utilisateurs ont été remis à zéro.")

def setup(bot):
    bot.add_cog(cmdeco(bot))