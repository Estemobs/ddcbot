import discord
import json
import os
import time
import random
import asyncio
from discord.ext import commands
from discord import Embed

class cmdjeu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()
        self.quete_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'quete.json')
        with open(self.quete_path, 'r') as f:
            self.quetes = json.load(f)

        # Charger les données depuis le fichier de configuration
        self.config_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'gameconfig.json')
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
    async def addgame(self, ctx):
        await ctx.send("Combien de lots voulez-vous ?")
        num_lots = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
        
        lots = []
        for i in range(int(num_lots.content)):
            valid_lot = False
            while not valid_lot:
                await ctx.send(f"Quel est le type du lot {i+1} ? (grade / ticket / argent)")
                lot_type = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                if lot_type.content == 'grade':
                    await ctx.send("Quel est l'ID du grade ?")
                    lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                    while not ctx.guild.get_role(int(lot_value.content)):
                        await ctx.send("ID de grade invalide. Veuillez entrer un ID de grade valide.")
                        lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                    valid_lot = True
                elif lot_type.content == 'ticket':
                    if not self.config:
                        await ctx.send("Impossible de créer un ticket car il n'y a aucun jeu. Veuillez choisir un autre type de lot.")
                    else:
                        await ctx.send("Veuillez choisir parmi les jeux suivants : " + ', '.join(self.config.keys()))
                        lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                        while lot_value.content not in self.config:
                            await ctx.send("Nom de jeu invalide. Veuillez entrer un nom de jeu existant.")
                            lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                        valid_lot = True
                elif lot_type.content == 'argent':
                    await ctx.send("Quel est le montant de l'argent ?")
                    lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                    while not lot_value.content.isdigit():
                        await ctx.send("Montant d'argent invalide. Veuillez entrer un montant d'argent valide.")
                        lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                    valid_lot = True
            lots.append({lot_type.content: lot_value.content})

       # Demander le prix du jeu et vérifier qu'il s'agit d'un entier
        await ctx.send("Quel est le prix du jeu ?")
        game_price = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
        while not game_price.content.isdigit():
            await ctx.send("Prix du jeu invalide. Veuillez entrer un prix du jeu valide.")
            game_price = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)

        # Demander le nom de la commande et vérifier qu'il est composé uniquement de lettres
        await ctx.send("Quel est le nom de la commande ?")
        command_name = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
        while not command_name.content.isalpha():
            await ctx.send("Nom de commande invalide. Veuillez entrer un nom de commande valide.")
            command_name = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)

        # Enregistrer les informations dans le fichier gameconfig.json
        self.config[command_name.content] = {
            "num_lots": num_lots.content,
            "lots": lots,
            "game_price": game_price.content
        }

        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

        await ctx.send("Les informations du jeu ont été enregistrées avec succès.")

    @commands.command()
    @commands.has_role(591683595043602436)
    async def openlot(self, ctx):
        await ctx.send("Quel est le nom du lot que vous voulez ouvrir ?")
        lot_name = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)

        if lot_name.content not in self.config:
            await ctx.send("Ce lot n'existe pas.")
            return

        # Charger les données depuis le fichier inventaire.json
        inventory_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'inventaire.json')
        with open(inventory_path, 'r') as f:
            inventory = json.load(f)
        
        with open(self.balances_path, 'r') as f:
            self.balances = json.load(f)
   
        if 'tickets' in inventory and any(ticket for ticket in inventory['tickets'] if list(ticket.values())[0] == lot_name.content):
        # Retirer le ticket de l'inventaire
            inventory['tickets'].remove(next(ticket for ticket in inventory['tickets'] if list(ticket.values())[0] == lot_name.content))
            await ctx.send("Ouverture avec un ticket")
            # Si l'utilisateur n'a pas de ticket, vérifier s'il a assez d'argent pour ouvrir le lot
            game_price = int(self.config[lot_name.content]['game_price'])
            if str(ctx.author.id) not in self.balances or self.balances[str(ctx.author.id)] < game_price:
                await ctx.send("Vous n'avez pas assez d'argent pour ouvrir ce lot.")
                return
            else:
                # Retirer le prix du jeu de la balance de l'utilisateur
                self.balances[str(ctx.author.id)] -= game_price

        # Faire un tirage au sort entre tous les lots
        prize = random.choice(self.config[lot_name.content]['lots'])


        # Incrémenter le compteur de la quête
        for quest in self.quetes:
            if quest['name'] == lot_name.content:
                # Si le champ 'progress' n'existe pas, le créer et le mettre à 1
                if 'progress' not in quest:
                    quest['progress'] = 1
                else:
                    # Sinon, incrémenter le compteur
                    quest['progress'] += 1

                # Vérifier si le compteur a atteint le nombre de lots requis pour la quête
                if quest['progress'] >= quest['lot_count']:
                    # Déclencher la récompense de la quête
                    for prize_type, prize_value in quest['lots'].items():
                        # Attribuer le prix à l'utilisateur en fonction du type de prix
                        if prize_type == 'grade':
                            # Récupérer l'ID du grade
                            role_id = int(prize_value)
                            # Récupérer l'objet Role correspondant à l'ID du grade
                            role = ctx.guild.get_role(role_id)
                            if role is not None:
                                # Ajouter le grade à l'utilisateur
                                await ctx.author.add_roles(role)
                                await ctx.send(f"Félicitations ! Vous avez reçu le grade {role.name}.")
                            else:
                                await ctx.send("Désolé, je n'ai pas pu trouver le grade correspondant à cet ID.")
                        elif prize_type == 'ticket':
                            if 'tickets' not in inventory:
                                # Si la clé 'tickets' n'existe pas, créer un nouvel inventaire pour l'utilisateur
                                inventory['tickets'] = []
                            user_tickets = [ticket for ticket in inventory['tickets'] if list(ticket.keys())[0] == str(ctx.author.id) and list(ticket.values())[0] == prize_value]
                            if user_tickets:
                                # Si l'utilisateur a déjà ce ticket, augmenter la quantité
                                for ticket in user_tickets:
                                    ticket[str(ctx.author.id)] = str(int(ticket[str(ctx.author.id)]) + 1)
                                    await ctx.send(f"Le ticket gagné est : {prize_value}")
                            else:
                                # Si l'utilisateur n'a pas ce ticket, l'ajouter à l'inventaire
                                inventory['tickets'].append({str(ctx.author.id): prize_value})
                                await ctx.send(f"Le ticket gagné est : {prize_value}")
                        elif prize_type == 'argent':
                            if ctx.author.id in self.balances:
                                self.balances[ctx.author.id] = 0
                                self.balances[ctx.author.id] += int(prize_value)
                                balance = self.balances[ctx.author.id]
                                await ctx.send(f"Vous venez de gagner : {balance}.")
                            else:
                                ancien_solde = self.balances[str(ctx.author.id)]
                                await ctx.send(f"Le solde avant l'ajout est : {ancien_solde}")
                                self.balances[str(ctx.author.id)] += int(prize_value)
                                nouveau_solde = self.balances[str(ctx.author.id)]
                                await ctx.send(f"Le solde après l'ajout est : {nouveau_solde}")

                    # Réinitialiser le compteur de la quête
                 
                        quest['progress'] = 0
                    # Sauvegarder les modifications apportées à self.quetes dans le fichier quete.json
                        with open(self.quete_path, 'w') as f:
                            json.dump(self.quetes, f, indent=4)

        # Attribuer le prix à l'utilisateur en fonction du type de prix
        for prize_type, prize_value in prize.items():
            if prize_type == 'grade':
                # Récupérer l'ID du grade
                role_id = int(prize_value)
                # Récupérer l'objet Role correspondant à l'ID du grade
                role = ctx.guild.get_role(role_id)
                if role is not None:
                    # Ajouter le grade à l'utilisateur
                    await ctx.author.add_roles(role)
                    await ctx.send(f"Félicitations ! Vous avez reçu le grade {role.name}.")
                else:
                    await ctx.send("Désolé, je n'ai pas pu trouver le grade correspondant à cet ID.")

                pass
            elif prize_type == 'ticket':
                if 'tickets' not in inventory:
                    # Si la clé 'tickets' n'existe pas, créer un nouvel inventaire pour l'utilisateur
                    inventory['tickets'] = []
                user_tickets = [ticket for ticket in inventory['tickets'] if list(ticket.keys())[0] == str(ctx.author.id) and list(ticket.values())[0] == prize_value]
                if user_tickets:
                    # Si l'utilisateur a déjà ce ticket, augmenter la quantité
                    for ticket in user_tickets:
                        ticket[str(ctx.author.id)] = str(int(ticket[str(ctx.author.id)]) + 1)
                        await ctx.send(f"Le ticket gagné est : {prize_value}")
                else:
                    # Si l'utilisateur n'a pas ce ticket, l'ajouter à l'inventaire
                    inventory['tickets'].append({str(ctx.author.id): prize_value})
                    await ctx.send(f"Le ticket gagné est : {prize_value}")
            elif prize_type == 'argent':
                if ctx.author.id in self.balances:
                    self.balances[ctx.author.id] = 0
                    self.balances[ctx.author.id] += int(prize_value)
                    balance = self.balances[ctx.author.id]
                    await ctx.send(f"Vous venez de gagner : {balance}.")
                else:
                    ancien_solde = self.balances[str(ctx.author.id)]
                    await ctx.send(f"Le solde avant l'ajout est : {ancien_solde}")
                    self.balances[str(ctx.author.id)] += int(prize_value)
                    nouveau_solde = self.balances[str(ctx.author.id)]
                    await ctx.send(f"Le solde après l'ajout est : {nouveau_solde}")

                    

        # Enregistrer les données dans les fichiers json
        with open(inventory_path, 'w') as f:
            json.dump(inventory, f, indent=4, ensure_ascii=False)
        
        with open(self.balances_path, 'w') as f:
            json.dump(self.balances, f, indent=4)



    @commands.command()
    @commands.has_role(591683595043602436)
    async def deletegame(self, ctx):
        await ctx.send("Quel est le nom du lot que vous voulez supprimer ?")
        command_name = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)

        if command_name.content not in self.config:
            await ctx.send("Ce lot n'existe pas.")
            return

        # Supprimer la commande du fichier gameconfig.json
        del self.config[command_name.content]

        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

        await ctx.send("Le lot a été supprimée avec succès.")




    @commands.command()
    async def shop(self, ctx):
        if not self.config:
            await ctx.send("Il n'y a actuellement aucun jeu enregistré.")
            return

        embed = Embed(title="Liste des jeux", description="Voici la liste des jeux actuellement enregistrés :", color=0x00ff00)

        for command_name, game_info in self.config.items():
            game_details = f"Nombre de lots : {game_info['num_lots']}\n"
            
            # Afficher le contenu des lots
            for i, lot in enumerate(game_info['lots'], start=1):
                for lot_type, lot_value in lot.items():
                    game_details += f"Lot {i} : Type - {lot_type}, Valeur - {lot_value}\n"
            
            game_details += f"Prix du jeu : {game_info['game_price']}"
            embed.add_field(name=command_name, value=game_details, inline=False)

        await ctx.send(embed=embed)

      
    @commands.command()
    async def inventaire(self, ctx):
        # Charger les données depuis le fichier inventaire.json
        inventory_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'inventaire.json')
        with open(inventory_path, 'r') as f:
            inventory = json.load(f)

        # Vérifier si la clé 'tickets' existe dans l'inventaire
        if 'tickets' not in inventory:
            await ctx.send("Votre inventaire est vide.")
            return

        # Si la clé 'tickets' existe, vérifier si l'ID de l'utilisateur est dans l'inventaire
        user_tickets = [ticket for ticket in inventory['tickets'] if list(ticket.keys())[0] == str(ctx.author.id)]

        if not user_tickets:
            await ctx.send("Votre inventaire est vide.")
            return

        # Si l'ID de l'utilisateur est dans l'inventaire et qu'il y a des éléments associés à l'ID, afficher le contenu de l'inventaire de l'utilisateur
        embed = discord.Embed(title="Votre inventaire", description="\n".join([f"{ticket[list(ticket.keys())[0]]}" for ticket in user_tickets]), color=0x00ff00)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_role(591683595043602436)  # Assurez-vous de remplacer ceci par l'ID du rôle approprié
    async def clearinventory(self, ctx, user: discord.User=None):
        if user is None:
            user = ctx.author

        # Charger les données depuis le fichier inventaire.json
        inventory_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'inventaire.json')
        with open(inventory_path, 'r') as f:
            inventory = json.load(f)

        # Vérifier si l'utilisateur a des tickets dans l'inventaire
        user_tickets = [ticket for ticket in inventory['tickets'] if list(ticket.keys())[0] == str(user.id)]
        if not user_tickets:
            await ctx.send("L'inventaire de l'utilisateur est déjà vide.")
            return

        # Supprimer tous les tickets de l'utilisateur
        inventory['tickets'] = [ticket for ticket in inventory['tickets'] if list(ticket.keys())[0] != str(user.id)]

        # Enregistrer les données dans le fichier inventaire.json
        with open(inventory_path, 'w') as f:
            json.dump(inventory, f, indent=4, ensure_ascii=False)

        await ctx.send(f"L'inventaire de {user.name} a été effacé.")

    @commands.command()
    @commands.has_role(591683595043602436)  # Assurez-vous de remplacer ceci par l'ID du rôle approprié
    async def addquest(self, ctx):
        if not self.config:
            await ctx.send("Il n'y a actuellement aucun lot enregistré.")
            return

        await ctx.send("La quête est associée à quel lot ? Veuillez choisir parmi les lots suivants : " + ', '.join(self.config.keys()))
        lot_name = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
        while lot_name.content not in self.config:
            await ctx.send("Nom de lot invalide. Veuillez entrer un nom de lot existant.")
            lot_name = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)

        await ctx.send("Combien de lots doivent être ouverts pour débloquer la récompense ?")
        lot_count = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)

        valid_lot = False
        while not valid_lot:
            await ctx.send("Quel est le type de récompense pour la quête ? (grade / ticket / argent)")
            lot_type = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
            if lot_type.content == 'grade':
                await ctx.send("Quel est l'ID du grade ?")
                lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                while not ctx.guild.get_role(int(lot_value.content)):
                    await ctx.send("ID de grade invalide. Veuillez entrer un ID de grade valide.")
                    lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                valid_lot = True
            elif lot_type.content == 'ticket':
                if not self.config:
                    await ctx.send("Impossible de créer un ticket car il n'y a aucun jeu. Veuillez choisir un autre type de lot.")
                else:
                    await ctx.send("Veuillez choisir parmi les jeux suivants : " + ', '.join(self.config.keys()))
                    lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                    while lot_value.content not in self.config:
                        await ctx.send("Nom de jeu invalide. Veuillez entrer un nom de jeu existant.")
                        lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                    valid_lot = True
            elif lot_type.content == 'argent':
                await ctx.send("Quel est le montant de l'argent ?")
                lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                while not lot_value.content.isdigit():
                    await ctx.send("Montant d'argent invalide. Veuillez entrer un montant d'argent valide.")
                    lot_value = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
                valid_lot = True
        lot = {lot_type.content: lot_value.content}

        # Enregistrement de la quête dans le fichier quete.json
        new_quest = {
            "name": lot_name.content,
            "lot_count": int(lot_count.content),
            "lot": lot
        }

        with open(self.quete_path, 'r') as f:
            data = json.load(f)

        data[lot_name.content] = new_quest

        with open(self.quete_path, 'w') as f:
            json.dump(data, f, indent=4)

        await ctx.send("La quête a été ajoutée avec succès !")

    @commands.command()
    @commands.has_role(591683595043602436)
    async def deletequete(self, ctx):
        await ctx.send("Quel est le nom de la quête que vous voulez supprimer ?")
        quest_name = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)

        # Charger les données depuis le fichier quete.json
        with open(self.quete_path, 'r') as f:
            quests = json.load(f)

        # Vérifier si la quête existe
        quest_exists = any(quest for quest in quests if quest['name'] == quest_name.content)
        if not quest_exists:
            await ctx.send("Cette quête n'existe pas.")
            return

        # Supprimer la quête
        quests = [quest for quest in quests if quest['name'] != quest_name.content]

        # Enregistrer les données dans le fichier quete.json
        with open(self.quete_path, 'w') as f:
            json.dump(quests, f, indent=4)

        await ctx.send("La quête a été supprimée avec succès.")

    @commands.command()
    async def quest(self, ctx):
        # Charger les données depuis le fichier quete.json
        with open(self.quete_path, 'r') as f:
            quests = json.load(f)

        # Vérifier si l'utilisateur a des quêtes en cours
        user_quests = [quest for quest_name, quest in quests.items() if quest_name in self.config]
        if not user_quests:
            await ctx.send("Vous n'avez pas de quêtes en cours.")
            return

        # Si l'utilisateur a des quêtes en cours, afficher la progression de chaque quête dans un embed
        embed = discord.Embed(title="Votre progression dans les quêtes", color=0x00ff00)
        for quest in user_quests:
            quest_details = f"Nombre de lots : {quest['lot_count']}\n"
            quest_details += f"Lot : {', '.join([f'{lot_type} - {lot_value}' for lot_type, lot_value in quest['lot'].items()])}"
            embed.add_field(name=quest['name'], value=quest_details, inline=False)

        await ctx.send(embed=embed)
        
def setup(bot):
    bot.add_cog(cmdjeu(bot))