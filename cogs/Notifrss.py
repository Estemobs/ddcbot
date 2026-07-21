import asyncio
import discord
import json
import requests
from datetime import datetime
from io import BytesIO
from discord.ext import commands


class cmdrss(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.intents = discord.Intents.all()
        self.notification_lock = asyncio.Lock()
        self._notification_task = None

    def list_notifications(self) -> list:
        rows = self.db.fetchall("SELECT id, show_name, season, number, airdate, user_id FROM notifications")
        return [
            {
                "id": row["id"],
                "show_name": row["show_name"],
                "season": row["season"],
                "number": row["number"],
                "airdate": row["airdate"],
                "user_id": row["user_id"],
            }
            for row in rows
        ]

    def add_notification(self, show_name, season, number, airdate, user_id):
        self.db.execute(
            "INSERT INTO notifications (show_name, season, number, airdate, user_id) VALUES (?, ?, ?, ?, ?)",
            (show_name, season, number, airdate, user_id),
        )

    def delete_notification(self, notification_id: int):
        self.db.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))

    def update_notification(self, notification_id: int, season, number, airdate):
        self.db.execute(
            "UPDATE notifications SET season = ?, number = ?, airdate = ? WHERE id = ?",
            (season, number, airdate, notification_id),
        )

    def delete_user_notifications_for_show(self, user_id: int, show_name: str):
        self.db.execute(
            "DELETE FROM notifications WHERE user_id = ? AND show_name = ?", (user_id, show_name)
        )

    def _compact_notifications(self, notifications):
        compacted = {}
        for notification in notifications:
            show_name = notification.get("show_name")
            user_id = notification.get("user_id")
            airdate_text = notification.get("airdate")
            if not show_name or user_id is None or not airdate_text:
                continue
            try:
                airdate = datetime.fromisoformat(airdate_text)
            except ValueError:
                continue
            key = (user_id, show_name)
            current = compacted.get(key)
            if current is None:
                compacted[key] = notification
                continue
            try:
                current_airdate = datetime.fromisoformat(current["airdate"])
            except ValueError:
                compacted[key] = notification
                continue
            if airdate < current_airdate:
                compacted[key] = notification
        return list(compacted.values())

    async def _get_next_episode(self, show_name, user_id, after_date=None):
        show_url = f'http://api.tvmaze.com/singlesearch/shows?q={show_name}&embed=episodes'
        try:
            show_response = requests.get(show_url)
            show_response.raise_for_status()
            show_data = show_response.json()
        except (requests.RequestException, ValueError):
            return None

        episodes = show_data.get('_embedded', {}).get('episodes', [])
        if after_date is None:
            cutoff_date = datetime.now().date()
            is_future_episode = lambda episode_date: episode_date >= cutoff_date
        else:
            cutoff_date = after_date
            is_future_episode = lambda episode_date: episode_date > cutoff_date

        future_episodes = []
        for episode in episodes:
            airdate_text = episode.get('airdate')
            if not airdate_text:
                continue
            try:
                airdate = datetime.strptime(airdate_text, '%Y-%m-%d').date()
            except ValueError:
                continue
            if is_future_episode(airdate):
                future_episodes.append((airdate, episode))

        if not future_episodes:
            return None

        airdate, episode = min(future_episodes, key=lambda item: item[0])
        return {
            'show_name': show_name,
            'season': episode['season'],
            'number': episode['number'],
            'airdate': airdate.isoformat(),
            'user_id': user_id
        }

    async def check_notifications(self):
        async with self.notification_lock:
            all_notifications = self.list_notifications()
            compacted = self._compact_notifications(all_notifications)
            keep_ids = {n["id"] for n in compacted}
            for n in all_notifications:
                if n["id"] not in keep_ids:
                    self.delete_notification(n["id"])

            notifications_to_send = {}

            for notification in compacted:
                show_name = notification["show_name"]
                season = notification["season"]
                number = notification["number"]

                try:
                    airdate = datetime.fromisoformat(notification["airdate"])
                except ValueError:
                    self.delete_notification(notification["id"])
                    continue

                now = datetime.now()
                if airdate <= now:
                    user_id = notification["user_id"]
                    if airdate.date() >= now.date():
                        message = f"Un nouvel épisode de {show_name} (S{season}E{number}) est maintenant disponible ! <@{user_id}>"
                        notifications_to_send.setdefault(user_id, []).append(message)

                    next_notification = await self._get_next_episode(show_name, user_id)
                    if next_notification:
                        self.update_notification(
                            notification["id"],
                            next_notification["season"],
                            next_notification["number"],
                            next_notification["airdate"],
                        )
                    else:
                        self.delete_notification(notification["id"])

            # Envoie les notifications par utilisateur pour éviter les doublons et le mélange des messages
            for user_id, messages in notifications_to_send.items():
                try:
                    user = await self.bot.fetch_user(user_id)
                    await user.send("\n".join(messages))
                except discord.DiscordException:
                    continue

    async def _notification_loop(self):
        while True:
            await self.check_notifications()
            await asyncio.sleep(3600)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._notification_task is None or self._notification_task.done():
            self._notification_task = asyncio.create_task(self._notification_loop())

    # commande pour créer un abonnement
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
        if not msg.content.isdigit():
            await ctx.send("Option invalide.")
            return
        choice = int(msg.content)
        if choice <= 0 or choice > len(options):
            await ctx.send("Option invalide.")
            return
        options = list(options)
        selected_option = options[choice-1]
        show_name = selected_option[0]

        # find show by name
        show_url = f'http://api.tvmaze.com/singlesearch/shows?q={show_name}&embed=episodes'
        show_response = requests.get(show_url)
        show_data = json.loads(show_response.text)

        # get future episode release dates
        episodes = show_data.get('_embedded', {}).get('episodes', [])
        future_episodes = []
        for episode in episodes:
            airdate_text = episode.get('airdate')
            if not airdate_text:
                continue
            try:
                airdate = datetime.strptime(airdate_text, '%Y-%m-%d')
            except ValueError:
                continue
            if airdate >= datetime.now():
                future_episodes.append((episode.get('season'), episode.get('number'), airdate))

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

        next_episode = await self._get_next_episode(show_name, ctx.author.id)
        async with self.notification_lock:
            self.delete_user_notifications_for_show(ctx.author.id, show_name)
            if next_episode:
                self.add_notification(
                    next_episode["show_name"], next_episode["season"], next_episode["number"],
                    next_episode["airdate"], next_episode["user_id"],
                )

        if next_episode:
            await ctx.send(f"Je vous notifierai en message privé lorsque les nouveaux épisodes de {show_name} sortiront.")
        else:
            await ctx.send("Aucun épisode à venir.")

    # commande pour voir la liste des notfications
    @commands.command()
    async def notifications(self, ctx):
        user_id = ctx.author.id
        all_notifications = self.list_notifications()

        found_notifications = []
        seen_show_names = set()
        for notification in all_notifications:
            show_name = notification.get('show_name')
            if notification.get('user_id') == user_id and show_name not in seen_show_names:
                seen_show_names.add(show_name)
                found_notifications.append(notification)

        if found_notifications:
            embed = discord.Embed(title="Liste des notifications")
            for notification in found_notifications:
                airdate = datetime.fromisoformat(notification["airdate"]).strftime('%d/%m/%Y')
                embed.colour = discord.Colour.green()
                embed.add_field(name=f"**{notification['show_name']}**", value=f"Saison {notification['season']}, épisode {notification['number']}\nDiffusion prévue le {airdate}", inline=False)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title="Liste des notifications", description="Vous n'avez pas de notifications enregistrées.")
            embed.colour = discord.Colour.red()
            await ctx.send(embed=embed)

    # commande pour suprimmer une notifications
    @commands.command()
    async def delnotif(self, ctx):
        user_id = ctx.author.id
        all_notifications = self.list_notifications()

        found_notifications = [n for n in all_notifications if n['user_id'] == user_id]

        if not found_notifications:
            embed = discord.Embed(title="Liste des notifications", description="Vous n'avez pas de notifications enregistrées.")
            embed.colour = discord.Colour.red()
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(title="Liste des notifications")
        for display_index, notification in enumerate(found_notifications, start=1):
            airdate = datetime.fromisoformat(notification["airdate"]).strftime('%d/%m/%Y')
            embed.colour = discord.Colour.green()
            embed.add_field(name=f"**[{display_index}] {notification['show_name']}**", value=f"Saison {notification['season']}, épisode {notification['number']}\nDiffusion prévue le {airdate}", inline=False)
        await ctx.send(embed=embed)

        # Suppression de la série en fonction du numéro saisi par l'utilisateur
        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            await ctx.send("**Veuillez entrer le numéro de la série que vous voulez supprimer.**")
            message = await self.bot.wait_for('message', timeout=30.0, check=check)
            selection = int(message.content.strip())
            if selection < 1 or selection > len(found_notifications):
                await ctx.send("Le numéro saisi est invalide.")
                return

            selected_show_name = found_notifications[selection - 1]['show_name']
            async with self.notification_lock:
                self.delete_user_notifications_for_show(user_id, selected_show_name)

            await ctx.send(f"Toutes les notifications de {selected_show_name} ont été supprimées avec succès.")
        except asyncio.TimeoutError:
            await ctx.send("Le temps imparti est écoulé. La commande a été annulée.")


def setup(bot, db):
    bot.add_cog(cmdrss(bot, db))
