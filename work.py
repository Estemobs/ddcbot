import discord
import json
import os
import time
import random
import asyncio
from discord.ext import commands


class cmdwork(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()
        # Charger les données depuis le fichier de configuration
        self.config_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'workconfig.json')
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)

        # Autres variables globales
        self.balances_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'balances.json')
        self.balances = {}

        # Charger les données depuis le fichier des balances
        with open(self.balances_path, 'r') as f:
            self.balances = json.load(f)

    @commands.command()
    @commands.has_role(591683595043602436) 
    async def config_work(self, ctx, min_amount: int, max_amount: int, reward_tiers: int, cooldown: int, *rewards: int):
        # Vérifiez si le nombre de récompenses correspond au nombre de paliers de récompenses
        if len(rewards) != reward_tiers:
            await ctx.send(f"Le nombre de récompenses doit être égal au nombre de paliers de récompenses ({reward_tiers})")
            return

        # Vérifiez si le montant minimum est inférieur au montant maximum
        if min_amount >= max_amount:
            await ctx.send("Le montant minimum doit être inférieur au montant maximum")
            return

        # Mettre à jour les données dans le fichier de configuration
        self.config['min_amount'] = min_amount
        self.config['max_amount'] = max_amount
        self.config['reward_tiers'] = reward_tiers
        self.config['cooldown'] = cooldown * 3600 # Multipliez la valeur du cooldown par 3600 pour la convertir en secondes
        self.config['rewards'] = rewards

        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

        await ctx.send(f"Commande configurée avec succès : montant minimum = {min_amount}, montant maximum = {max_amount}, nombre de paliers de récompenses = {reward_tiers}, cooldown = {cooldown} heures, récompenses = {rewards}")


    @commands.command()
    async def show_work_config(self, ctx):
        # Vérifiez si la commande configure_work a été exécutée auparavant
        if 'min_amount' not in self.config:
            await ctx.send("La commande configure_work doit être exécutée avant d'utiliser la commande show_work_config")
            return

        # Créez un embed pour afficher les données de configuration
        embed = discord.Embed(title="Configuration de la commande work", color=0x00ff00)
        embed.add_field(name="Montant minimum", value=self.config['min_amount'], inline=False)
        embed.add_field(name="Montant maximum", value=self.config['max_amount'], inline=False)
        embed.add_field(name="Nombre de paliers de récompenses", value=self.config['reward_tiers'], inline=False)
        embed.add_field(name="Cooldown (en heures)", value=self.config['cooldown'] // 3600, inline=False)
        embed.add_field(name="Récompenses bonus", value=', '.join(map(str, self.config['rewards'])), inline=False)

        await ctx.send(embed=embed)


    @commands.command()
    async def work(self, ctx):
        # Vérifiez si la commande configure_work a été exécutée auparavant
        if 'min_amount' not in self.config:
            await ctx.send("La commande configure_work doit être exécutée avant d'utiliser la commande work")
            return

        # Vérifiez si la commande est en cooldown pour l'utilisateur
        user_id = str(ctx.author.id)
        if 'last_worked' in self.config and user_id in self.config['last_worked']:
            time_since_last_worked = time.time() - self.config['last_worked'][user_id]
            if time_since_last_worked < self.config['cooldown']:
                remaining_cooldown = round((self.config['cooldown'] - time_since_last_worked) / 3600)
                await ctx.send(f"Vous devez attendre encore {remaining_cooldown} heures avant de pouvoir travailler à nouveau.")
                return

        # Générez un montant aléatoire entre le montant minimum et maximum
        amount = random.randint(self.config['min_amount'], self.config['max_amount'])

        # Déterminez la récompense bonus en fonction du nombre de fois que l'utilisateur a utilisé la commande work
        bonus_reward = 0
        if 'work_count' in self.config and user_id in self.config['work_count']:
            tier_size = self.config['reward_tiers']
            tier = min(self.config['work_count'][user_id] // tier_size, len(self.config['rewards']) - 1)
            bonus_reward = self.config['rewards'][tier]

        # Mettre à jour les données dans le fichier des balances
        if user_id not in self.balances:
            self.balances[user_id] = 0

        self.balances[user_id] += amount + bonus_reward

        with open(self.balances_path, 'w') as f:
            json.dump(self.balances, f, indent=4)

        # Mettre à jour les données dans le fichier de configuration
        if 'work_count' not in self.config:
            self.config['work_count'] = {}

        if user_id not in self.config['work_count']:
            self.config['work_count'][user_id] = 0

        if 'last_worked' not in self.config:
            self.config['last_worked'] = {}

        self.config['work_count'][user_id] += 1
        self.config['last_worked'][user_id] = time.time()

        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

        await ctx.send(f"Vous avez travaillé et gagné {amount}$! Vous avez également reçu une récompense bonus de {bonus_reward}. Votre solde actuel est de {self.balances[user_id]}.")



def setup(bot):
    bot.add_cog(cmdwork(bot))









