import discord
import json
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
        self.cog.update_game_panel_config(self.guild_id, openlot_enabled=not cfg["openlot_enabled"])
        await self.refresh(interaction)

    @discord.ui.button(label="Toggle quetes", style=discord.ButtonStyle.primary, row=0)
    async def toggle_quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_game_panel_config(self.guild_id)
        self.cog.update_game_panel_config(self.guild_id, quests_enabled=not cfg["quests_enabled"])
        await self.refresh(interaction)

    @discord.ui.button(label="Toggle annonce gains", style=discord.ButtonStyle.primary, row=0)
    async def toggle_public_announce(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_game_panel_config(self.guild_id)
        self.cog.update_game_panel_config(self.guild_id, announce_win_public=not cfg["announce_win_public"])
        await self.refresh(interaction)

    @discord.ui.button(label="Canal logs = ici", style=discord.ButtonStyle.secondary, row=1)
    async def set_log_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.update_game_panel_config(self.guild_id, log_channel_id=interaction.channel_id)
        await self.refresh(interaction)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=1)
    async def reset_defaults(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.reset_game_panel_config(self.guild_id)
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
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.intents = discord.Intents.all()

    # --- balances (table partagee avec economie.py/income.py/work.py) ---

    def get_balance(self, user_id: int) -> float:
        row = self.db.fetchone("SELECT amount FROM balances WHERE user_id = ?", (user_id,))
        return row["amount"] if row else 0.0

    def add_balance(self, user_id: int, delta: float):
        self.db.execute(
            "INSERT INTO balances (user_id, amount) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET amount = amount + excluded.amount",
            (user_id, delta),
        )

    # --- jeux / lootbox ---

    def list_games(self) -> dict:
        rows = self.db.fetchall("SELECT name, num_lots, lots_json, game_price FROM games")
        return {
            row["name"]: {
                "num_lots": row["num_lots"],
                "lots": json.loads(row["lots_json"]),
                "game_price": row["game_price"],
            }
            for row in rows
        }

    def get_game(self, name: str):
        row = self.db.fetchone("SELECT num_lots, lots_json, game_price FROM games WHERE name = ?", (name,))
        if row is None:
            return None
        return {"num_lots": row["num_lots"], "lots": json.loads(row["lots_json"]), "game_price": row["game_price"]}

    def add_game(self, name: str, num_lots: int, lots: list, game_price: int):
        self.db.execute(
            "INSERT INTO games (name, num_lots, lots_json, game_price) VALUES (?, ?, ?, ?)",
            (name, num_lots, json.dumps(lots), game_price),
        )

    def remove_game(self, name: str):
        self.db.execute("DELETE FROM games WHERE name = ?", (name,))

    # --- quetes ---

    def list_quests(self) -> dict:
        rows = self.db.fetchall("SELECT name, lot_count, lot_json, progress FROM quests")
        return {
            row["name"]: {
                "name": row["name"],
                "lot_count": row["lot_count"],
                "lot": json.loads(row["lot_json"]),
                "progress": row["progress"],
            }
            for row in rows
        }

    def get_quest(self, name: str):
        row = self.db.fetchone("SELECT lot_count, lot_json, progress FROM quests WHERE name = ?", (name,))
        if row is None:
            return None
        return {"lot_count": row["lot_count"], "lot": json.loads(row["lot_json"]), "progress": row["progress"]}

    def add_quest(self, name: str, lot_count: int, lot: dict):
        self.db.execute(
            "INSERT INTO quests (name, lot_count, lot_json, progress) VALUES (?, ?, ?, 0) "
            "ON CONFLICT(name) DO UPDATE SET lot_count=excluded.lot_count, lot_json=excluded.lot_json, progress=0",
            (name, lot_count, json.dumps(lot)),
        )

    def remove_quest(self, name: str):
        self.db.execute("DELETE FROM quests WHERE name = ?", (name,))

    def increment_quest_progress(self, name: str) -> int:
        self.db.execute("UPDATE quests SET progress = progress + 1 WHERE name = ?", (name,))
        row = self.db.fetchone("SELECT progress FROM quests WHERE name = ?", (name,))
        return row["progress"]

    def reset_quest_progress(self, name: str):
        self.db.execute("UPDATE quests SET progress = 0 WHERE name = ?", (name,))

    # --- inventaire (tickets) ---

    def add_ticket(self, user_id: int, item_name: str):
        self.db.execute("INSERT INTO inventory_tickets (user_id, item_name) VALUES (?, ?)", (user_id, item_name))

    def pop_ticket(self, user_id: int, item_name: str) -> bool:
        row = self.db.fetchone(
            "SELECT id FROM inventory_tickets WHERE user_id = ? AND item_name = ? LIMIT 1",
            (user_id, item_name),
        )
        if row is None:
            return False
        self.db.execute("DELETE FROM inventory_tickets WHERE id = ?", (row["id"],))
        return True

    def has_ticket(self, user_id: int, item_name: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM inventory_tickets WHERE user_id = ? AND item_name = ? LIMIT 1",
            (user_id, item_name),
        ) is not None

    def user_ticket_counts(self, user_id: int) -> dict:
        rows = self.db.fetchall(
            "SELECT item_name, COUNT(*) as cnt FROM inventory_tickets WHERE user_id = ? GROUP BY item_name",
            (user_id,),
        )
        return {row["item_name"]: row["cnt"] for row in rows}

    def clear_user_tickets(self, user_id: int) -> bool:
        row = self.db.fetchone("SELECT 1 FROM inventory_tickets WHERE user_id = ? LIMIT 1", (user_id,))
        if row is None:
            return False
        self.db.execute("DELETE FROM inventory_tickets WHERE user_id = ?", (user_id,))
        return True

    # --- config panneau jeux par serveur ---

    def get_game_panel_config(self, guild_id: int) -> dict:
        self.db.execute(
            "INSERT OR IGNORE INTO game_panel_config "
            "(guild_id, openlot_enabled, quests_enabled, announce_win_public, log_channel_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                guild_id,
                int(DEFAULT_GAME_PANEL_CONFIG["openlot_enabled"]),
                int(DEFAULT_GAME_PANEL_CONFIG["quests_enabled"]),
                int(DEFAULT_GAME_PANEL_CONFIG["announce_win_public"]),
                DEFAULT_GAME_PANEL_CONFIG["log_channel_id"],
            ),
        )
        row = self.db.fetchone(
            "SELECT openlot_enabled, quests_enabled, announce_win_public, log_channel_id "
            "FROM game_panel_config WHERE guild_id = ?",
            (guild_id,),
        )
        return {
            "openlot_enabled": bool(row["openlot_enabled"]),
            "quests_enabled": bool(row["quests_enabled"]),
            "announce_win_public": bool(row["announce_win_public"]),
            "log_channel_id": row["log_channel_id"],
        }

    def update_game_panel_config(self, guild_id: int, **fields):
        self.get_game_panel_config(guild_id)
        assignments = []
        values = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(int(value) if isinstance(value, bool) else value)
        values.append(guild_id)
        self.db.execute(f"UPDATE game_panel_config SET {', '.join(assignments)} WHERE guild_id = ?", values)

    def reset_game_panel_config(self, guild_id: int):
        self.db.execute(
            "INSERT INTO game_panel_config (guild_id, openlot_enabled, quests_enabled, announce_win_public, log_channel_id) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET openlot_enabled=excluded.openlot_enabled, "
            "quests_enabled=excluded.quests_enabled, announce_win_public=excluded.announce_win_public, "
            "log_channel_id=excluded.log_channel_id",
            (
                guild_id,
                int(DEFAULT_GAME_PANEL_CONFIG["openlot_enabled"]),
                int(DEFAULT_GAME_PANEL_CONFIG["quests_enabled"]),
                int(DEFAULT_GAME_PANEL_CONFIG["announce_win_public"]),
                DEFAULT_GAME_PANEL_CONFIG["log_channel_id"],
            ),
        )

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

    async def _award_prize(self, ctx, prize: dict):
        """Attribue un prix à l'utilisateur selon le type (grade / ticket / argent)."""
        user_id = ctx.author.id
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
                self.add_ticket(user_id, prize_value)
                await ctx.send(f"🎟️ Vous avez gagné un ticket pour : **{prize_value}** !")
            elif prize_type == 'argent':
                self.add_balance(user_id, int(prize_value))
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
                    games = self.list_games()
                    if not games:
                        await ctx.send("Impossible de créer un ticket car il n'y a aucun jeu. Veuillez choisir un autre type de lot.")
                    else:
                        await ctx.send("Veuillez choisir parmi les jeux suivants : " + ', '.join(games.keys()))
                        lot_value = await self._ask(ctx)
                        if lot_value is None:
                            return
                        while lot_value.content not in self.list_games():
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

        self.add_game(command_name.content, num_lots, lots, int(game_price.content))

        await ctx.send(f"✅ Le jeu **{command_name.content}** a été enregistré avec succès.")

    @commands.command()
    async def openlot(self, ctx):
        panel_cfg = self.get_game_panel_config(ctx.guild.id)
        if not panel_cfg["openlot_enabled"]:
            await ctx.send("L'ouverture des lots est desactivee sur ce serveur.")
            return

        games = self.list_games()
        if not games:
            await ctx.send("Il n'y a actuellement aucun jeu enregistré. Consultez la boutique avec `,shop`.")
            return

        await ctx.send("Quel jeu voulez-vous ouvrir ? Jeux disponibles : " + ', '.join(games.keys()))
        lot_name_msg = await self._ask(ctx, timeout=30.0)
        if lot_name_msg is None:
            return

        lot_name = lot_name_msg.content
        game = self.get_game(lot_name)
        if game is None:
            await ctx.send("❌ Ce jeu n'existe pas.")
            return

        user_id = ctx.author.id
        game_price = int(game['game_price'])

        if self.has_ticket(user_id, lot_name):
            self.pop_ticket(user_id, lot_name)
            await ctx.send("🎟️ Ouverture avec un ticket !")
        elif game_price > 0:
            if self.get_balance(user_id) < game_price:
                await ctx.send(f"❌ Vous n'avez pas assez d'argent pour ouvrir ce lot. Prix : **{game_price}** pièces.")
                return
            self.add_balance(user_id, -game_price)
        # Si game_price == 0, ouverture gratuite sans ticket

        prize = random.choice(game['lots'])

        quest = self.get_quest(lot_name)
        if panel_cfg["quests_enabled"] and quest is not None:
            progress = self.increment_quest_progress(lot_name)
            if progress >= quest['lot_count']:
                await self._award_prize(ctx, quest['lot'])
                self.reset_quest_progress(lot_name)
                await ctx.send(f"🏆 Quête **{lot_name}** complétée ! Vous avez reçu votre récompense de quête.")

        await self._award_prize(ctx, prize)

        if not panel_cfg["announce_win_public"]:
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

        await self.send_game_log(ctx.guild, f"[JEUX] {ctx.author.mention} a ouvert {lot_name} et a recu: {prize}")

    @commands.command()
    async def deletegame(self, ctx):
        await ctx.send("Quel est le nom du jeu que vous voulez supprimer ?")
        command_name = await self._ask(ctx, timeout=30.0)
        if command_name is None:
            return

        if self.get_game(command_name.content) is None:
            await ctx.send("❌ Ce jeu n'existe pas.")
            return

        self.remove_game(command_name.content)

        await ctx.send(f"✅ Le jeu **{command_name.content}** a été supprimé avec succès.")

    @commands.command()
    async def shop(self, ctx):
        games = self.list_games()
        if not games:
            await ctx.send("Il n'y a actuellement aucun jeu enregistré.")
            return

        embed = Embed(title="🎰 Boutique des jeux", description="Voici la liste des jeux actuellement disponibles :", color=0x00ff00)

        for command_name, game_info in games.items():
            game_details = f"Nombre de lots : {game_info['num_lots']}\n"
            for i, lot in enumerate(game_info['lots'], start=1):
                for lot_type, lot_value in lot.items():
                    game_details += f"Lot {i} : {lot_type} — {lot_value}\n"
            price = game_info['game_price']
            game_details += f"Prix : {'Gratuit' if price == 0 else f'{price} pièces'}"
            embed.add_field(name=command_name, value=game_details, inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def inventaire(self, ctx):
        ticket_counts = self.user_ticket_counts(ctx.author.id)
        if not ticket_counts:
            await ctx.send("Votre inventaire est vide.")
            return

        embed = discord.Embed(title="🎒 Votre inventaire", color=0x00ff00)
        for game_name, count in ticket_counts.items():
            embed.add_field(name=f"🎟️ {game_name}", value=f"Quantité : {count}", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def clearinventory(self, ctx, user: discord.User = None):
        if user is None:
            user = ctx.author

        if not self.clear_user_tickets(user.id):
            await ctx.send("L'inventaire de cet utilisateur est déjà vide.")
            return

        await ctx.send(f"✅ L'inventaire de **{user.name}** a été effacé.")

    @commands.command()
    async def addquest(self, ctx):
        games = self.list_games()
        if not games:
            await ctx.send("Il n'y a actuellement aucun lot enregistré.")
            return

        await ctx.send("La quête est associée à quel jeu ? Jeux disponibles : " + ', '.join(games.keys()))
        lot_name = await self._ask(ctx)
        if lot_name is None:
            return
        while lot_name.content not in self.list_games():
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
                games = self.list_games()
                if not games:
                    await ctx.send("Impossible de créer un ticket car il n'y a aucun jeu. Veuillez choisir un autre type.")
                else:
                    await ctx.send("Veuillez choisir parmi les jeux suivants : " + ', '.join(games.keys()))
                    lot_value = await self._ask(ctx)
                    if lot_value is None:
                        return
                    while lot_value.content not in self.list_games():
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

        self.add_quest(lot_name.content, int(lot_count.content), lot)
        await ctx.send(f"✅ La quête pour le jeu **{lot_name.content}** a été ajoutée avec succès !")

    @commands.command()
    async def deletequete(self, ctx):
        await ctx.send("Quel est le nom de la quête que vous voulez supprimer ?")
        quest_name = await self._ask(ctx, timeout=30.0)
        if quest_name is None:
            return

        if self.get_quest(quest_name.content) is None:
            await ctx.send("❌ Cette quête n'existe pas.")
            return

        self.remove_quest(quest_name.content)
        await ctx.send(f"✅ La quête **{quest_name.content}** a été supprimée avec succès.")

    @commands.command()
    async def quest(self, ctx):
        quests = self.list_quests()
        if not quests:
            await ctx.send("Aucune quête n'est actuellement disponible.")
            return

        embed = discord.Embed(title="📋 Quêtes actives", color=0x00ff00)
        for quest_name, quest in quests.items():
            progress = quest['progress']
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
        quests = self.list_quests()
        if not quests:
            await ctx.send("Aucune quête n'est configurée. Utilisez `,addquest` pour en créer une.")
            return

        embed = discord.Embed(
            title="⚙️ Configuration des quêtes",
            description="Voici le détail de toutes les quêtes configurées :",
            color=0xffa500
        )
        for quest_name, quest in quests.items():
            progress = quest['progress']
            lot_count = quest['lot_count']
            reward = ', '.join([f"{lot_type} — {lot_value}" for lot_type, lot_value in quest['lot'].items()])
            details = (
                f"Lots requis : **{lot_count}**\n"
                f"Progression : **{progress}/{lot_count}**\n"
                f"Récompense : {reward}"
            )
            embed.add_field(name=f"🗺️ {quest_name}", value=details, inline=False)

        await ctx.send(embed=embed)


def setup(bot, db):
    bot.add_cog(cmdjeu(bot, db))
