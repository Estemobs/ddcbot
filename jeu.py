import discord
import json
import os
import random
import asyncio
from discord.ext import commands
from discord import Embed


DEFAULT_GAME_PANEL_CONFIG = {
    "openlot_enabled": True,
    "quests_enabled": True,
    "announce_win_public": True,
    "log_channel_id": None,
}


class GamePanelView(discord.ui.View):
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
        cfg = self.cog.get_game_panel_config(interaction.guild.id)
        embed = self.cog.build_game_panel_embed(interaction.guild, cfg)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle openlot", style=discord.ButtonStyle.primary, row=0)
    async def toggle_openlot(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_game_panel_config(self.guild_id)
        cfg["openlot_enabled"] = not cfg["openlot_enabled"]
        self.cog.save_game_panel_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Toggle quetes", style=discord.ButtonStyle.primary, row=0)
    async def toggle_quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_game_panel_config(self.guild_id)
        cfg["quests_enabled"] = not cfg["quests_enabled"]
        self.cog.save_game_panel_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Toggle annonce gains", style=discord.ButtonStyle.primary, row=0)
    async def toggle_public_announce(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_game_panel_config(self.guild_id)
        cfg["announce_win_public"] = not cfg["announce_win_public"]
        self.cog.save_game_panel_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Canal logs = ici", style=discord.ButtonStyle.secondary, row=1)
    async def set_log_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_game_panel_config(self.guild_id)
        cfg["log_channel_id"] = interaction.channel_id
        self.cog.save_game_panel_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=1)
    async def reset_defaults(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.game_panel_config[str(self.guild_id)] = dict(DEFAULT_GAME_PANEL_CONFIG)
        self.cog.save_game_panel_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, row=1)
    async def close_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        cfg = self.cog.get_game_panel_config(interaction.guild.id)
        embed = self.cog.build_game_panel_embed(interaction.guild, cfg)
        embed.set_footer(text="Panneau ferme")
        await interaction.response.edit_message(embed=embed, view=self)


class cmdjeu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()
        self.quete_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'quete.json')
        with open(self.quete_path, 'r') as f:
            self.quetes = json.load(f)

        self.config_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'gameconfig.json')
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)

        self.balances_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'balances.json')
        with open(self.balances_path, 'r') as f:
            self.balances = json.load(f)

        self.inventory_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'inventaire.json')
        self.game_panel_config_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'game_panel_config.json')
        self.game_panel_config = self.load_game_panel_config()

    def load_game_panel_config(self):
        if not os.path.exists(self.game_panel_config_path):
            return {}
        try:
            with open(self.game_panel_config_path, 'r') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def save_game_panel_config(self):
        with open(self.game_panel_config_path, 'w') as f:
            json.dump(self.game_panel_config, f, indent=4)

    def get_game_panel_config(self, guild_id: int):
        key = str(guild_id)
        if key not in self.game_panel_config or not isinstance(self.game_panel_config[key], dict):
            self.game_panel_config[key] = dict(DEFAULT_GAME_PANEL_CONFIG)
            self.save_game_panel_config()
        else:
            for cfg_key, cfg_default in DEFAULT_GAME_PANEL_CONFIG.items():
                if cfg_key not in self.game_panel_config[key]:
                    self.game_panel_config[key][cfg_key] = cfg_default
            self.save_game_panel_config()
        return self.game_panel_config[key]

    def build_game_panel_embed(self, guild: discord.Guild, cfg: dict):
        channel_id = cfg.get("log_channel_id")
        log_channel = guild.get_channel(channel_id) if channel_id else None
        log_label = f"#{log_channel.name}" if log_channel else "Non defini"

        embed = discord.Embed(
            title="Panneau Jeux / Lootbox",
            description="Configuration de la categorie jeux.",
            color=discord.Color.purple(),
        )
        embed.add_field(name="Ouverture des lots", value="Active" if cfg["openlot_enabled"] else "Desactivee", inline=True)
        embed.add_field(name="Systeme de quetes", value="Actif" if cfg["quests_enabled"] else "Desactive", inline=True)
        embed.add_field(name="Annonce publique des gains", value="Oui" if cfg["announce_win_public"] else "Non", inline=True)
        embed.add_field(name="Canal logs", value=log_label, inline=False)
        embed.set_footer(text=f"Serveur: {guild.name}")
        return embed

    async def send_game_log(self, guild: discord.Guild, message: str):
        cfg = self.get_game_panel_config(guild.id)
        channel_id = cfg.get("log_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel:
            await channel.send(message)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def gamepanel(self, ctx):
        cfg = self.get_game_panel_config(ctx.guild.id)
        embed = self.build_game_panel_embed(ctx.guild, cfg)
        view = GamePanelView(self, ctx.guild.id, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    # ─── Méthodes internes ───────────────────────────────────────────────────────

    async def _ask(self, ctx, timeout: float = 60.0):
        """Attend une réponse de l'auteur dans le même salon, avec timeout."""
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=timeout)
            return msg
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Temps écoulé. La commande a été annulée.")
            return None

    async def _award_prize(self, ctx, prize: dict, inventory: dict):
        """Attribue un prix à l'utilisateur selon le type (grade / ticket / argent)."""
        user_id = str(ctx.author.id)
        for prize_type, prize_value in prize.items():
            if prize_type == 'grade':
                role_id = int(prize_value)
                role = ctx.guild.get_role(role_id)
                if role is not None:
                    await ctx.author.add_roles(role)
                    await ctx.send(f"🎖️ Félicitations ! Vous avez reçu le rôle **{role.name}**.")
                else:
                    await ctx.send("⚠️ Désolé, je n'ai pas pu trouver le rôle correspondant à cet ID.")
            elif prize_type == 'ticket':
                if 'tickets' not in inventory:
                    inventory['tickets'] = []
                user_tickets = [
                    ticket for ticket in inventory['tickets']
                    if list(ticket.keys())[0] == user_id and list(ticket.values())[0] == prize_value
                ]
                if user_tickets:
                    for ticket in user_tickets:
                        ticket[user_id] = str(int(ticket[user_id]) + 1)
                else:
                    inventory['tickets'].append({user_id: prize_value})
                await ctx.send(f"🎟️ Vous avez gagné un ticket pour : **{prize_value}** !")
            elif prize_type == 'argent':
                if user_id not in self.balances:
                    self.balances[user_id] = 0
                self.balances[user_id] += int(prize_value)
                await ctx.send(f"💰 Vous avez gagné **{prize_value}** pièces !")

    # ─── Commandes ──────────────────────────────────────────────────────────────

    @commands.command()
    async def addgame(self, ctx):
        await ctx.send("Combien de lots voulez-vous ?")
        num_lots_msg = await self._ask(ctx)
        if num_lots_msg is None:
            return

        if not num_lots_msg.content.isdigit():
            await ctx.send("❌ Nombre de lots invalide.")
            return

        num_lots = int(num_lots_msg.content)
        lots = []

        for i in range(num_lots):
            valid_lot = False
            while not valid_lot:
                await ctx.send(f"Quel est le type du lot {i+1} ? (grade / ticket / argent)")
                lot_type = await self._ask(ctx)
                if lot_type is None:
                    return

                if lot_type.content == 'grade':
                    await ctx.send("Quel est l'ID du grade ?")
                    lot_value = await self._ask(ctx)
                    if lot_value is None:
                        return
                    while not lot_value.content.isdigit() or not ctx.guild.get_role(int(lot_value.content)):
                        await ctx.send("ID de grade invalide. Veuillez entrer un ID de grade valide.")
                        lot_value = await self._ask(ctx)
                        if lot_value is None:
                            return
                    valid_lot = True
                elif lot_type.content == 'ticket':
                    if not self.config:
                        await ctx.send("Impossible de créer un ticket car il n'y a aucun jeu. Veuillez choisir un autre type de lot.")
                    else:
                        await ctx.send("Veuillez choisir parmi les jeux suivants : " + ', '.join(self.config.keys()))
                        lot_value = await self._ask(ctx)
                        if lot_value is None:
                            return
                        while lot_value.content not in self.config:
                            await ctx.send("Nom de jeu invalide. Veuillez entrer un nom de jeu existant.")
                            lot_value = await self._ask(ctx)
                            if lot_value is None:
                                return
                        valid_lot = True
                elif lot_type.content == 'argent':
                    await ctx.send("Quel est le montant de l'argent ?")
                    lot_value = await self._ask(ctx)
                    if lot_value is None:
                        return
                    while not lot_value.content.isdigit():
                        await ctx.send("Montant d'argent invalide. Veuillez entrer un montant valide.")
                        lot_value = await self._ask(ctx)
                        if lot_value is None:
                            return
                    valid_lot = True
                else:
                    await ctx.send("Type invalide. Choisissez parmi : grade / ticket / argent")

            lots.append({lot_type.content: lot_value.content})

        await ctx.send("Quel est le prix du jeu ?")
        game_price = await self._ask(ctx)
        if game_price is None:
            return
        while not game_price.content.isdigit():
            await ctx.send("Prix du jeu invalide. Veuillez entrer un prix valide.")
            game_price = await self._ask(ctx)
            if game_price is None:
                return

        await ctx.send("Quel est le nom du jeu ?")
        command_name = await self._ask(ctx)
        if command_name is None:
            return
        while not command_name.content.isalpha():
            await ctx.send("Nom de jeu invalide. Veuillez entrer un nom composé uniquement de lettres.")
            command_name = await self._ask(ctx)
            if command_name is None:
                return

        self.config[command_name.content] = {
            "num_lots": str(num_lots),
            "lots": lots,
            "game_price": game_price.content
        }

        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

        await ctx.send(f"✅ Le jeu **{command_name.content}** a été enregistré avec succès.")


    @commands.command()
    async def openlot(self, ctx):
        panel_cfg = self.get_game_panel_config(ctx.guild.id)
        if not panel_cfg["openlot_enabled"]:
            await ctx.send("L'ouverture des lots est desactivee sur ce serveur.")
            return

        with open(self.config_path, 'r') as f:
            self.config = json.load(f)

        if not self.config:
            await ctx.send("Il n'y a actuellement aucun jeu enregistré. Consultez la boutique avec `,shop`.")
            return

        await ctx.send("Quel jeu voulez-vous ouvrir ? Jeux disponibles : " + ', '.join(self.config.keys()))
        lot_name_msg = await self._ask(ctx, timeout=30.0)
        if lot_name_msg is None:
            return

        lot_name = lot_name_msg.content
        if lot_name not in self.config:
            await ctx.send("❌ Ce jeu n'existe pas.")
            return

        with open(self.inventory_path, 'r') as f:
            inventory = json.load(f)
        with open(self.balances_path, 'r') as f:
            self.balances = json.load(f)

        user_id = str(ctx.author.id)
        game_price = int(self.config[lot_name]['game_price'])

        # Vérifier si l'utilisateur a un ticket pour ce jeu
        user_has_ticket = (
            'tickets' in inventory and
            any(
                ticket for ticket in inventory['tickets']
                if list(ticket.keys())[0] == user_id and list(ticket.values())[0] == lot_name
            )
        )

        if user_has_ticket:
            ticket_to_remove = next(
                ticket for ticket in inventory['tickets']
                if list(ticket.keys())[0] == user_id and list(ticket.values())[0] == lot_name
            )
            inventory['tickets'].remove(ticket_to_remove)
            await ctx.send("🎟️ Ouverture avec un ticket !")
        elif game_price > 0:
            if user_id not in self.balances or self.balances[user_id] < game_price:
                await ctx.send(f"❌ Vous n'avez pas assez d'argent pour ouvrir ce lot. Prix : **{game_price}** pièces.")
                return
            self.balances[user_id] -= game_price
        # Si game_price == 0, ouverture gratuite sans ticket

        # Tirage au sort parmi tous les lots
        prize = random.choice(self.config[lot_name]['lots'])

        # Progression des quêtes
        with open(self.quete_path, 'r') as f:
            self.quetes = json.load(f)

        if panel_cfg["quests_enabled"] and lot_name in self.quetes:
            quest = self.quetes[lot_name]
            quest['progress'] = quest.get('progress', 0) + 1

            if quest['progress'] >= quest['lot_count']:
                await self._award_prize(ctx, quest['lot'], inventory)
                quest['progress'] = 0
                await ctx.send(f"🏆 Quête **{lot_name}** complétée ! Vous avez reçu votre récompense de quête.")

            with open(self.quete_path, 'w') as f:
                json.dump(self.quetes, f, indent=4)

        # Attribuer le prix tiré au sort
        await self._award_prize(ctx, prize, inventory)

        if not panel_cfg["announce_win_public"]:
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

        await self.send_game_log(ctx.guild, f"[JEUX] {ctx.author.mention} a ouvert {lot_name} et a recu: {prize}")

        with open(self.inventory_path, 'w') as f:
            json.dump(inventory, f, indent=4, ensure_ascii=False)
        with open(self.balances_path, 'w') as f:
            json.dump(self.balances, f, indent=4)


    @commands.command()
    async def deletegame(self, ctx):
        await ctx.send("Quel est le nom du jeu que vous voulez supprimer ?")
        command_name = await self._ask(ctx, timeout=30.0)
        if command_name is None:
            return

        if command_name.content not in self.config:
            await ctx.send("❌ Ce jeu n'existe pas.")
            return

        del self.config[command_name.content]

        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

        await ctx.send(f"✅ Le jeu **{command_name.content}** a été supprimé avec succès.")


    @commands.command()
    async def shop(self, ctx):
        if not self.config:
            await ctx.send("Il n'y a actuellement aucun jeu enregistré.")
            return

        embed = Embed(title="🎰 Boutique des jeux", description="Voici la liste des jeux actuellement disponibles :", color=0x00ff00)

        for command_name, game_info in self.config.items():
            game_details = f"Nombre de lots : {game_info['num_lots']}\n"
            for i, lot in enumerate(game_info['lots'], start=1):
                for lot_type, lot_value in lot.items():
                    game_details += f"Lot {i} : {lot_type} — {lot_value}\n"
            price = game_info['game_price']
            game_details += f"Prix : {'Gratuit' if price == '0' else f'{price} pièces'}"
            embed.add_field(name=command_name, value=game_details, inline=False)

        await ctx.send(embed=embed)


    @commands.command()
    async def inventaire(self, ctx):
        with open(self.inventory_path, 'r') as f:
            inventory = json.load(f)

        user_id = str(ctx.author.id)

        if 'tickets' not in inventory:
            await ctx.send("Votre inventaire est vide.")
            return

        user_tickets = [ticket for ticket in inventory['tickets'] if list(ticket.keys())[0] == user_id]

        if not user_tickets:
            await ctx.send("Votre inventaire est vide.")
            return

        embed = discord.Embed(title="🎒 Votre inventaire", color=0x00ff00)
        ticket_counts = {}
        for ticket in user_tickets:
            game_name = list(ticket.values())[0]
            ticket_counts[game_name] = ticket_counts.get(game_name, 0) + 1

        for game_name, count in ticket_counts.items():
            embed.add_field(name=f"🎟️ {game_name}", value=f"Quantité : {count}", inline=False)

        await ctx.send(embed=embed)


    @commands.command()
    async def clearinventory(self, ctx, user: discord.User = None):
        if user is None:
            user = ctx.author

        with open(self.inventory_path, 'r') as f:
            inventory = json.load(f)

        if 'tickets' not in inventory:
            await ctx.send("L'inventaire est déjà vide.")
            return

        user_tickets = [ticket for ticket in inventory['tickets'] if list(ticket.keys())[0] == str(user.id)]
        if not user_tickets:
            await ctx.send("L'inventaire de cet utilisateur est déjà vide.")
            return

        inventory['tickets'] = [ticket for ticket in inventory['tickets'] if list(ticket.keys())[0] != str(user.id)]

        with open(self.inventory_path, 'w') as f:
            json.dump(inventory, f, indent=4, ensure_ascii=False)

        await ctx.send(f"✅ L'inventaire de **{user.name}** a été effacé.")


    @commands.command()
    async def addquest(self, ctx):
        if not self.config:
            await ctx.send("Il n'y a actuellement aucun lot enregistré.")
            return

        await ctx.send("La quête est associée à quel jeu ? Jeux disponibles : " + ', '.join(self.config.keys()))
        lot_name = await self._ask(ctx)
        if lot_name is None:
            return
        while lot_name.content not in self.config:
            await ctx.send("Nom de jeu invalide. Veuillez entrer un nom de jeu existant.")
            lot_name = await self._ask(ctx)
            if lot_name is None:
                return

        await ctx.send("Combien de lots doivent être ouverts pour débloquer la récompense ?")
        lot_count = await self._ask(ctx)
        if lot_count is None:
            return
        while not lot_count.content.isdigit():
            await ctx.send("Valeur invalide. Veuillez entrer un nombre entier.")
            lot_count = await self._ask(ctx)
            if lot_count is None:
                return

        valid_lot = False
        while not valid_lot:
            await ctx.send("Quel est le type de récompense pour la quête ? (grade / ticket / argent)")
            lot_type = await self._ask(ctx)
            if lot_type is None:
                return

            if lot_type.content == 'grade':
                await ctx.send("Quel est l'ID du grade ?")
                lot_value = await self._ask(ctx)
                if lot_value is None:
                    return
                while not lot_value.content.isdigit() or not ctx.guild.get_role(int(lot_value.content)):
                    await ctx.send("ID de grade invalide. Veuillez entrer un ID de grade valide.")
                    lot_value = await self._ask(ctx)
                    if lot_value is None:
                        return
                valid_lot = True
            elif lot_type.content == 'ticket':
                if not self.config:
                    await ctx.send("Impossible de créer un ticket car il n'y a aucun jeu. Veuillez choisir un autre type.")
                else:
                    await ctx.send("Veuillez choisir parmi les jeux suivants : " + ', '.join(self.config.keys()))
                    lot_value = await self._ask(ctx)
                    if lot_value is None:
                        return
                    while lot_value.content not in self.config:
                        await ctx.send("Nom de jeu invalide. Veuillez entrer un nom de jeu existant.")
                        lot_value = await self._ask(ctx)
                        if lot_value is None:
                            return
                    valid_lot = True
            elif lot_type.content == 'argent':
                await ctx.send("Quel est le montant de l'argent ?")
                lot_value = await self._ask(ctx)
                if lot_value is None:
                    return
                while not lot_value.content.isdigit():
                    await ctx.send("Montant invalide. Veuillez entrer un montant valide.")
                    lot_value = await self._ask(ctx)
                    if lot_value is None:
                        return
                valid_lot = True
            else:
                await ctx.send("Type invalide. Choisissez parmi : grade / ticket / argent")

        lot = {lot_type.content: lot_value.content}

        new_quest = {
            "name": lot_name.content,
            "lot_count": int(lot_count.content),
            "lot": lot,
            "progress": 0
        }

        with open(self.quete_path, 'r') as f:
            data = json.load(f)

        data[lot_name.content] = new_quest

        with open(self.quete_path, 'w') as f:
            json.dump(data, f, indent=4)

        self.quetes = data
        await ctx.send(f"✅ La quête pour le jeu **{lot_name.content}** a été ajoutée avec succès !")


    @commands.command()
    async def deletequete(self, ctx):
        await ctx.send("Quel est le nom de la quête que vous voulez supprimer ?")
        quest_name = await self._ask(ctx, timeout=30.0)
        if quest_name is None:
            return

        with open(self.quete_path, 'r') as f:
            quests = json.load(f)

        if quest_name.content not in quests:
            await ctx.send("❌ Cette quête n'existe pas.")
            return

        del quests[quest_name.content]

        with open(self.quete_path, 'w') as f:
            json.dump(quests, f, indent=4)

        self.quetes = quests
        await ctx.send(f"✅ La quête **{quest_name.content}** a été supprimée avec succès.")


    @commands.command()
    async def quest(self, ctx):
        with open(self.quete_path, 'r') as f:
            quests = json.load(f)

        if not quests:
            await ctx.send("Aucune quête n'est actuellement disponible.")
            return

        embed = discord.Embed(title="📋 Quêtes actives", color=0x00ff00)
        for quest_name, quest in quests.items():
            progress = quest.get('progress', 0)
            lot_count = quest['lot_count']
            reward = ', '.join([f"{lot_type} — {lot_value}" for lot_type, lot_value in quest['lot'].items()])
            quest_details = (
                f"Lots à ouvrir : {lot_count}\n"
                f"Progression globale : {progress}/{lot_count}\n"
                f"Récompense : {reward}"
            )
            embed.add_field(name=f"🗺️ {quest_name}", value=quest_details, inline=False)

        await ctx.send(embed=embed)


    @commands.command()
    async def config_quete(self, ctx):
        """Affiche la configuration complète de toutes les quêtes (admin)."""
        with open(self.quete_path, 'r') as f:
            quests = json.load(f)

        if not quests:
            await ctx.send("Aucune quête n'est configurée. Utilisez `,addquest` pour en créer une.")
            return

        embed = discord.Embed(
            title="⚙️ Configuration des quêtes",
            description="Voici le détail de toutes les quêtes configurées :",
            color=0xffa500
        )
        for quest_name, quest in quests.items():
            progress = quest.get('progress', 0)
            lot_count = quest['lot_count']
            reward = ', '.join([f"{lot_type} — {lot_value}" for lot_type, lot_value in quest['lot'].items()])
            details = (
                f"Lots requis : **{lot_count}**\n"
                f"Progression : **{progress}/{lot_count}**\n"
                f"Récompense : {reward}"
            )
            embed.add_field(name=f"🗺️ {quest_name}", value=details, inline=False)

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(cmdjeu(bot))
