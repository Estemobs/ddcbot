import asyncio
import discord
import json
import requests
import traceback
import os
import aiohttp
from datetime import datetime
from io import BytesIO
from discord.ext import commands

class cmdrss(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()
        self.notifications_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'notifications.json')
        self.notification_lock = asyncio.Lock()
       

    async def check_notifications(self):
        async with self.notification_lock:
            with open(self.notifications_path, "r") as f:
                data = json.load(f)

            notifications_to_send = []  # Liste pour stocker les notifications à envoyer

            for notification in data:
                show_name = notification["show_name"]
                season = notification["season"]
                number = notification["number"]
                airdate = datetime.strptime(notification["airdate"], '%Y-%m-%dT%H:%M:%S')

                # Check if airdate has passed
                now = datetime.now()
                print("now: ", now)
                if airdate <= now:
                    user_id = notification["user_id"]
                    user = await self.bot.fetch_user(user_id)
                    message = f"Un nouvel épisode de {show_name} (S{season}E{number}) est maintenant disponible ! {user.mention}"
                    notifications_to_send.append(message)  # Ajoutez le message à la liste

                    # Remove notification from file
                    data.remove(notification)
                    with open(self.notifications_path, "w") as f:
                        json.dump(data, f, indent=2)
                    print("Notification sent: ", show_name, season, number, airdate)

            # Envoie toutes les notifications en une seule fois
            if notifications_to_send:
                await user.send("\n".join(notifications_to_send))
        

    @commands.Cog.listener()
    async def on_ready(self):
         while True:
            await self.check_notifications()
            #await check_for_new_episodes()
            await asyncio.sleep(3600)
            
            
    #commande pour créer un abonnement 
    @commands.command()
    async def subscribe(self, ctx):
        # ask user for show name
        await ctx.send("Entrez le nom d'une série / film / anime:")
        msg = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
        show_name = msg.content
        
        # search for show
        search_url = f'http://api.tvmaze.com/search/shows?q={show_name}'
        search_response = requests.get(search_url)
        search_results = json.loads(search_response.text)

        # check if search found any shows
        if len(search_results) == 0:
            await ctx.send("Aucune série / film / anime trouvée.")
            return

    # display search results
        options = []
        for i, result in enumerate(search_results):
            name = result['show']['name']
            network = result['show']['network']['name'] if result['show']['network'] else 'N/A'
            image_url = result['show']['image']['original'] if result['show']['image'] else None
            message = f"{i+1}. {name} ({network})"
            if image_url:
                response = requests.get(image_url)
                file = BytesIO(response.content)
                image = discord.File(file, filename="image.png")
                await ctx.send(message, file=image)
            else:
                await ctx.send(message)
            option = (name, network, image_url)
            if option not in options:
                options.append(option)
            else:
                await ctx.send(f"Option {i+1} est un doublon et a été ignoré.")
                
        # ask user to select an option
        await ctx.send("Sélectionnez un numéro:")
        msg = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author)
        choice = int(msg.content)
        if choice <= 0 or choice > len(options):
            await ctx.send("Option invalide.")
            return
        options = list(options)
        selected_option = options[choice-1]
        show_name = selected_option[0]
        network = selected_option[1]

        
        # find show by name
        show_url = f'http://api.tvmaze.com/singlesearch/shows?q={show_name}&embed=episodes'
        show_response = requests.get(show_url)
        show_data = json.loads(show_response.text)

        # get future episode release dates
        episodes = show_data['_embedded']['episodes']
        future_episodes = []
        for episode in episodes:
            airdate = datetime.strptime(episode['airdate'], '%Y-%m-%d')
            if airdate >= datetime.now():
                future_episodes.append((episode['season'], episode['number'], airdate))

        # display future episodes
        await ctx.send(f"Prochains épisodes de {show_name}:")
        no_episodes = True
        for season, number, airdate in future_episodes:
            episode_str = ""
            if season:
                episode_str += f"Saison {season}"
            if number:
                episode_str += f", Épisode {number}"
            if airdate:
                episode_str += f": {airdate.strftime('%d/%m/%Y')}"
            if episode_str:
                await ctx.send(episode_str)
                no_episodes = False
        if no_episodes:
            await ctx.send("Aucun épisode à venir.")

    # Load the notifications from the JSON file
        if os.path.exists(self.notifications_path) and os.path.getsize(self.notifications_path) > 0:
        # Charger le contenu du fichier existant
            with open(self.notifications_path, 'r') as f:
                notifications = json.load(f)
        else:
        # Vérifier si le fichier est vide
            if os.path.exists(self.notifications_path) and os.path.getsize(self.notifications_path) == 0:
        # Remplir le fichier avec une liste vide
                with open(self.notifications_path, 'w') as f:
                    f.write("")
        # Initialiser une liste vide
                notifications = [] 

    # Create a list of dictionaries for future episodes
        future_episodes = []
        for episode in show_data['_embedded']['episodes']:
            airdate = datetime.strptime(episode['airdate'], '%Y-%m-%d')
            if airdate >= datetime.now():
                episode_data = {
                    'show_name': show_name,
                    'season': episode['season'],
                    'number': episode['number'],
                    'airdate': airdate.isoformat(),
                    'user_id': ctx.author.id
                }
                future_episodes.append(episode_data)

    # Add new episodes to the existing notifications
        for episode in future_episodes:
            if episode not in notifications:
                notifications.append(episode)

    # Save the notifications to the JSON file
        with open(self.notifications_path, 'w') as f:
            json.dump(notifications, f, indent=2)

    # Envoyer un message de confirmation
        if len(episode) > 0:
            await ctx.send(f"Je vous notifierai en message privé lorsque les nouveaux épisodes de {show_name} sortiront.")
            

    #commande pour voir la liste des notfications 
    @commands.command()
    async def notifications(self, ctx):
        user_id = ctx.author.id  # Récupère l'ID de l'utilisateur
        found = False  # Variable pour indiquer si l'ID a été trouvé dans le fichier JSON

        # Ouvre le fichier JSON
        with open(self.notifications_path) as f:
            notifications = json.load(f)

        # Recherche de l'ID dans la liste des notifications
        found_notifications = []
        for notification in notifications:
            if notification['user_id'] == user_id:
                found = True
                found_notifications.append(notification)

        # Envoie une réponse en fonction du résultat de la recherche
        last_message = None
        if found:
            embed = discord.Embed(title="Liste des notifications")
            for notification in found_notifications:
                airdate = datetime.fromisoformat(notification["airdate"]).strftime('%d/%m/%Y')
                embed.colour = discord.Colour.green()
                embed.add_field(name=f"**{notification['show_name']}**", value=f"Saison {notification['season']}, épisode {notification['number']}\nDiffusion prévue le {airdate}", inline=False)
            if last_message:
                await last_message.delete()
            last_message = await ctx.send(embed=embed)    
        else:
            embed = discord.Embed(title="Liste des notifications", description=f"Vous n'avez pas de notifications enregistrées.")
            embed.colour = discord.Colour.red()
            await ctx.send(embed=embed)

    #commande pour suprimmer une notifications
    @commands.command()
    async def delnotif(self, ctx):
        user_id = ctx.author.id  # Récupère l'ID de l'utilisateur
        found = False  # Variable pour indiquer si l'ID a été trouvé dans le fichier JSON

        # Ouvre le fichier JSON
        with open(self.notifications_path) as f:
            notifications = json.load(f)

        # Recherche de l'ID dans la liste des notifications
        found_notifications = []
        for notification_num, notification in enumerate(notifications):
            if notification['user_id'] == user_id:
                found = True
                found_notifications.append((notification_num, notification))

        # Envoie une réponse en fonction du résultat de la recherche
        last_message = None
        if found:
            embed = discord.Embed(title="Liste des notifications")
            for notification_num, notification in found_notifications:
                airdate = datetime.fromisoformat(notification["airdate"]).strftime('%d/%m/%Y')
                embed.colour = discord.Colour.green()
                embed.add_field(name=f"**[{notification_num}] {notification['show_name']}**", value=f"Saison {notification['season']}, épisode {notification['number']}\nDiffusion prévue le {airdate}", inline=False)
            if last_message:
                await last_message.delete()
            last_message = await ctx.send(embed=embed)
            
            # Suppression de la série en fonction du numéro saisi par l'utilisateur
            def check(message):
                return message.author == ctx.author and message.channel == ctx.channel
            
            try:
                await ctx.send("**Veuillez entrer le numéro de la série que vous voulez supprimer.**")
                message = await self.bot.wait_for('message', timeout=30.0, check=check)
                selection = int(message.content.strip())
                if selection < 0 or selection >= len(found_notifications):
                    await ctx.send("Le numéro saisi est invalide.")
                    return
                
                notifications.pop(found_notifications[selection][0])
                
                with open(self.notifications_path, 'w') as f:
                    json.dump(notifications, f, indent=2)
                
                await ctx.send("La série a été supprimée avec succès.")
            except asyncio.TimeoutError:
                await ctx.send("Le temps imparti est écoulé. La commande a été annulée.")
        else:
            embed = discord.Embed(title="Liste des notifications", description=f"Vous n'avez pas de notifications enregistrées.")
            embed.colour = discord.Colour.red()
            await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(cmdrss(bot))
