import discord
import json
import os
import asyncio
import time
from discord.ext import commands

class cmdincome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()
        self.role_income_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'income.json')
        self.role_income = {}
        self.tags_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'balances.json')

        # Charger les données depuis le fichier 'income.json'
        with open(self.role_income_path, 'r') as f:
            self.role_income = json.load(f)    

        # Charger les données depuis le fichier 'balances.json'
        with open(self.tags_path, 'r') as f:
            self.balances = json.load(f)

    @commands.command()
    @commands.has_role(591683595043602436)
    async def role_income_add(self, ctx, role_id: int, amount: float, collect_interval: str):
        role = discord.utils.get(ctx.guild.roles, id=role_id)
        # Vérifier si le rôle n'est pas déjà dans la liste des rôles avec gains associés
        if role.id in self.role_income:
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
        self.role_income[role.id] = {
            "name": role.name,
            "amount": amount,
            "collect_interval": collect_interval_sec,
            "last_collect": 0
        }
        with open(self.role_income_path, 'w') as f:
            json.dump(self.role_income, f, indent=4)

        await ctx.send(f"Le rôle {role_id} a été ajouté à la liste des rôles avec un gains de : {amount} collectable toute les {collect_interval} heures.")


    @commands.command()
    @commands.has_role(591683595043602436)
    async def role_income_remove(self, ctx, role_id: int):
        role = discord.utils.get(ctx.guild.roles, id=role_id)
        # Vérifier si le rôle est dans la liste des rôles avec gains associés
        if role.id not in self.role_income:
            await ctx.send(f"Le rôle {role_id} n'a pas de gain associé.")
            return
        
        # Supprimer le rôle de la liste
        del self.role_income[role.id]
        with open(self.role_income_path, 'w') as f:
            json.dump(self.role_income, f, indent=4)
        
        await ctx.send(f"Le rôle {role_id} a été supprimé de la liste des rôles avec gains associés.")

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
    @commands.has_role(591683595043602436)
    async def role_income_edit(self, ctx, role_id: int, amount: float, collect_interval: str):
        # Vérifier si le rôle existe dans la liste des rôles avec gains associés
        if role_id not in self.role_income:
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
        self.role_income[role_id]["amount"] = amount
        self.role_income[role_id]["collect_interval"] = collect_interval_sec
        with open(self.role_income_path, 'w') as f:
            json.dump(self.role_income, f, indent=4)

        await ctx.send(f"Le gain associé au rôle {role_id} a été modifié : {amount} par collecte toutes les {collect_interval} heures.")


    @commands.command()
    async def collect_income(self, ctx):
        # Récupérer l'utilisateur qui a lancé la commande
        member = ctx.author

        # Vérifier si l'utilisateur a un compte
        if str(member.id) not in self.balances:
            await ctx.send(f"{member.mention}, vous n'avez pas de compte. Utilisez la commande `,addmoney` pour en créer un.")
            return

        # Vérifier si suffisamment de temps s'est écoulé depuis la dernière collecte
        current_time = time.time()
        for role_id, role_data in self.role_income.items():
            if current_time - role_data["last_collect"] >= role_data["collect_interval"]:
                # Ajouter le gain associé au solde de l'utilisateur
                self.balances[str(member.id)] += role_data["amount"]
                role_data["last_collect"] = current_time

                # Enregistrer les données mises à jour dans les fichiers json
                with open(self.tags_path, 'w') as f:
                    json.dump(self.balances, f, indent=4)
                with open(self.role_income_path, 'w') as f:
                    json.dump(self.role_income, f, indent=4)

                await ctx.send(f"{member.mention}, vous avez collecté {role_data['amount']} grâce à votre rôle {role_data['name']}. Nouveau solde : {self.balances[str(member.id)]:.2f}.")
            else:
                # Calculer le temps restant avant la prochaine collecte
                time_left = role_data["collect_interval"] - (current_time - role_data["last_collect"])
                hours_left = int(time_left // 3600)
                minutes_left = int((time_left % 3600) // 60)

                await ctx.send(f"{member.mention}, vous devez attendre encore {hours_left} heures et {minutes_left} minutes avant de collecter de nouveau votre gain pour le rôle {role_data['name']}.")

def setup(bot):
    bot.add_cog(cmdincome(bot))

