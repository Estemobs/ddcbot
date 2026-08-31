"""Casino : boxes, machines, loto et des, entierement configurables.

Aucun jeu n'est code en dur. Un jeu est une ligne de `casino_games` avec ses
lots, cree depuis le dashboard web ou avec ,addgame. Les regles et le hasard
vivent dans casino_engine ; ce cog ne fait que l'affichage Discord,
l'attribution des roles et le debit/credit du solde.
"""

import asyncio
import discord
from discord.ext import commands
from discord import Embed

from casino_engine import (
    CasinoEngine, CasinoError, Reward, format_duration, normalize_slug,
)

DEFAULT_GAME_PANEL_CONFIG = {
    "openlot_enabled": True,
    "quests_enabled": True,
    "announce_win_public": True,
    "log_channel_id": None,
}

# Alias acceptes cote commandes Discord, pour rester proche du vocabulaire du jeu.
REWARD_ALIASES = {
    "argent": "money", "money": "money",
    "grade": "role", "role": "role", "rôle": "role",
    "ticket": "ticket",
    "objet": "item", "item": "item",
    "rien": "nothing", "nothing": "nothing",
}

KIND_ALIASES = {
    "box": "weighted", "machine": "weighted", "pondere": "weighted",
    "pondéré": "weighted", "weighted": "weighted",
    "loto": "dice_sum", "des": "dice_sum", "dés": "dice_sum", "dice_sum": "dice_sum",
    "de": "dice_guess", "dé": "dice_guess", "pari": "dice_guess", "dice_guess": "dice_guess",
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
                "Seul l'auteur de la commande peut modifier ce panneau.", ephemeral=True
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
        self.cog.update_game_panel_config(
            self.guild_id, announce_win_public=not cfg["announce_win_public"]
        )
        await self.refresh(interaction)

    @discord.ui.button(label="Toggle animations", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_animations(self, interaction: discord.Interaction, button: discord.ui.Button):
        style = self.cog.engine.get_style(self.guild_id)
        self.cog.engine.update_style(
            self.guild_id, animations_enabled=0 if style["animations_enabled"] else 1
        )
        await self.refresh(interaction)

    @discord.ui.button(label="Canal logs = ici", style=discord.ButtonStyle.secondary, row=1)
    async def set_log_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.update_game_panel_config(self.guild_id, log_channel_id=interaction.channel_id)
        await self.refresh(interaction)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=1)
    async def reset_defaults(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.reset_game_panel_config(self.guild_id)
        await self.refresh(interaction)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, row=2)
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
        self.engine = CasinoEngine(db)
        self._locks = {}

    def _user_lock(self, user_id: int) -> asyncio.Lock:
        """Une partie a la fois par joueur : evite le double-debit sur spam."""
        lock = self._locks.get(user_id)
        if lock is None:
            lock = self._locks[user_id] = asyncio.Lock()
        return lock

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
        self.db.execute(
            f"UPDATE game_panel_config SET {', '.join(assignments)} WHERE guild_id = ?", values
        )

    def reset_game_panel_config(self, guild_id: int):
        self.db.execute(
            "INSERT INTO game_panel_config (guild_id, openlot_enabled, quests_enabled, "
            "announce_win_public, log_channel_id) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET openlot_enabled=excluded.openlot_enabled, "
            "quests_enabled=excluded.quests_enabled, "
            "announce_win_public=excluded.announce_win_public, "
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
        style = self.engine.get_style(guild.id)

        embed = discord.Embed(
            title="Panneau Casino",
            description="Jeux, lots et effets se configurent dans le dashboard web.",
            color=discord.Color.purple(),
        )
        embed.add_field(name="Ouverture des lots",
                        value="Active" if cfg["openlot_enabled"] else "Desactivee", inline=True)
        embed.add_field(name="Systeme de quetes",
                        value="Actif" if cfg["quests_enabled"] else "Desactive", inline=True)
        embed.add_field(name="Annonce publique des gains",
                        value="Oui" if cfg["announce_win_public"] else "Non", inline=True)
        embed.add_field(name="Animations",
                        value="Activees" if style["animations_enabled"] else "Desactivees",
                        inline=True)
        embed.add_field(name="Jeux configures",
                        value=str(len(self.engine.list_games(guild.id, include_disabled=True))),
                        inline=True)
        embed.add_field(name="Canal logs",
                        value=f"#{log_channel.name}" if log_channel else "Non defini", inline=False)
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

    # --- deroulement d'une partie ---

    async def _ask(self, ctx, timeout: float = 60.0):
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        try:
            return await self.bot.wait_for('message', check=check, timeout=timeout)
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Temps écoulé. La commande a été annulée.")
            return None

    def money(self, style: dict, amount: float) -> str:
        return f"{amount:,.0f}".replace(",", " ") + style["currency_symbol"]

    async def _grant(self, ctx, reward, style: dict) -> str:
        """Applique une recompense et renvoie sa description lisible."""
        if reward.kind == "money":
            amount = reward.money
            self.add_balance(ctx.author.id, amount)
            self.db.log_transaction(
                ctx.guild.id, ctx.author.id, amount, "casino",
                "gain" if amount >= 0 else "perte",
            )
            return self.money(style, amount)
        if reward.kind == "role":
            try:
                role = ctx.guild.get_role(int(reward.value))
            except (TypeError, ValueError):
                role = None
            if role is None:
                return "un rôle introuvable ⚠️"
            try:
                await ctx.author.add_roles(role)
            except discord.Forbidden:
                return f"le rôle **{role.name}** (permissions manquantes ⚠️)"
            return f"le rôle **{role.name}**"
        if reward.kind == "ticket":
            self.engine.add_item(ctx.guild.id, ctx.author.id, reward.value, "ticket")
            return f"un ticket **{reward.value}**"
        if reward.kind == "item":
            self.engine.add_item(ctx.guild.id, ctx.author.id, reward.value, "item")
            return f"**{reward.value}**"
        return "rien du tout"

    async def _animate(self, ctx, game: dict, style: dict):
        """Fait defiler les symboles dans un seul message, puis le renvoie.

        On edite un message unique plutot que d'en envoyer plusieurs : l'effet
        de rouleaux qui tournent, sans inonder le salon.
        """
        if not style["animations_enabled"] or not style["frame_count"]:
            return None
        frames = self.engine.animation_frames(style)
        if not frames:
            return None
        delay = max(0, int(style["frame_delay_ms"])) / 1000
        embed = Embed(
            title=game["display_name"],
            description=f"{style['suspense_text']}\n\n**{frames[0]}**",
            color=discord.Color.blurple(),
        )
        message = await ctx.send(embed=embed)
        for frame in frames[1:]:
            await asyncio.sleep(delay)
            embed.description = f"{style['suspense_text']}\n\n**{frame}**"
            try:
                await message.edit(embed=embed)
            except discord.HTTPException:
                break
        if delay:
            await asyncio.sleep(delay)
        return message

    async def play_game(self, ctx, game: dict, guess=None):
        """Cycle complet : cooldown, mise, tirage, effets, quetes."""
        panel = self.get_game_panel_config(ctx.guild.id)
        if not panel["openlot_enabled"]:
            await ctx.send("Les jeux sont désactivés sur ce serveur.")
            return
        if not game["enabled"]:
            await ctx.send(f"**{game['display_name']}** est désactivé.")
            return

        style = self.engine.get_style(ctx.guild.id)
        user_id = ctx.author.id

        async with self._user_lock(user_id):
            remaining = self.engine.cooldown_remaining(ctx.guild.id, user_id, game)
            if remaining > 0:
                await ctx.send(
                    f"⏳ **{game['display_name']}** sera de nouveau disponible dans "
                    f"**{format_duration(remaining)}**."
                )
                return

            price = float(game["price"] or 0)
            paid_with_ticket = self.engine.take_ticket(ctx.guild.id, user_id, game["slug"])
            if paid_with_ticket:
                price = 0.0
            elif price > 0:
                if self.get_balance(user_id) < price:
                    await ctx.send(
                        f"❌ Il vous faut **{self.money(style, price)}** pour jouer à "
                        f"**{game['display_name']}**."
                    )
                    return
                self.add_balance(user_id, -price)
                self.db.log_transaction(
                    ctx.guild.id, user_id, -price, "casino", f"mise {game['slug']}"
                )

            try:
                outcome = self.engine.draw(game, guess=guess)
            except CasinoError as exc:
                # La partie n'a pas eu lieu : on rend la mise.
                if price > 0:
                    self.add_balance(user_id, price)
                    self.db.log_transaction(
                        ctx.guild.id, user_id, price, "casino", f"remboursement {game['slug']}"
                    )
                if paid_with_ticket:
                    self.engine.add_item(ctx.guild.id, user_id, game["slug"], "ticket")
                await ctx.send(f"❌ {exc}")
                return

            message = await self._animate(ctx, game, style)
            granted = await self._grant(ctx, outcome.reward, style)
            payout = outcome.reward.money if outcome.reward.kind == "money" else 0.0
            self.engine.record_play(
                ctx.guild.id, user_id, game, price, payout, outcome.reward.describe()
            )

            won = payout > 0 or outcome.reward.kind in ("role", "ticket", "item")
            color = discord.Color.from_str(style["win_color"] if won else style["lose_color"])
            emoji = style["win_emoji"] if won else style["lose_emoji"]
            title = game["display_name"]
            if self.engine.is_jackpot(style, payout):
                title = f"{style['jackpot_text']} — {title}"
                color = discord.Color.gold()

            embed = Embed(title=title, color=color)
            embed.description = f"{emoji} Vous obtenez **{granted}**"
            if outcome.detail:
                embed.add_field(name="Tirage", value=outcome.detail, inline=True)
            if paid_with_ticket:
                embed.add_field(name="Mise", value="Ticket 🎟️", inline=True)
            elif price:
                embed.add_field(name="Mise", value=self.money(style, price), inline=True)
            embed.add_field(name="Solde", value=self.money(style, self.get_balance(user_id)),
                            inline=True)
            plays = self.engine.play_count(ctx.guild.id, user_id, slug=game["slug"])
            embed.set_footer(text=f"{plays} partie(s) sur ce jeu")

            if message is not None:
                await message.edit(embed=embed)
            else:
                await ctx.send(embed=embed)

            if panel["quests_enabled"]:
                await self._settle_quests(ctx, style)

            if not panel["announce_win_public"]:
                try:
                    await ctx.message.delete()
                except (discord.Forbidden, discord.HTTPException, AttributeError):
                    pass

            await self.send_game_log(
                ctx.guild,
                f"[CASINO] {ctx.author.mention} — {game['display_name']} → "
                f"{outcome.reward.describe()}",
            )

    async def _settle_quests(self, ctx, style: dict):
        """Verse les quetes dues. La progression est comptee par joueur."""
        role_ids = [role.id for role in getattr(ctx.author, "roles", [])]
        for quest, times, progress in self.engine.claimable_quests(
            ctx.guild.id, ctx.author.id, role_ids
        ):
            for _ in range(times):
                granted = await self._grant(
                    ctx, Reward(quest["reward_kind"], quest["reward_value"]), style
                )
                await ctx.send(
                    f"🏆 Quête **{quest['name']}** accomplie ({progress}/{quest['goal']}) — "
                    f"vous recevez {granted} !"
                )
            self.engine.mark_claimed(quest["id"], ctx.author.id, times)

    # --- commandes joueur ---

    @commands.command()
    async def gamepanel(self, ctx):
        cfg = self.get_game_panel_config(ctx.guild.id)
        embed = self.build_game_panel_embed(ctx.guild, cfg)
        await ctx.send(embed=embed, view=GamePanelView(self, ctx.guild.id, ctx.author.id))

    @commands.command(aliases=["jeux", "casino"])
    async def shop(self, ctx):
        """Catalogue des jeux disponibles."""
        games = self.engine.list_games(ctx.guild.id)
        if not games:
            await ctx.send(
                "Aucun jeu n'est configuré. Ajoutez-en avec `,addgame` ou depuis le dashboard."
            )
            return

        style = self.engine.get_style(ctx.guild.id)
        by_category = {}
        for game in games:
            by_category.setdefault(game["category"] or "Jeux", []).append(game)

        embed = Embed(title="🎰 Casino", color=discord.Color.blurple())
        for category, entries in by_category.items():
            lines = []
            for game in entries:
                price = "Gratuit" if not game["price"] else self.money(style, game["price"])
                line = f"`,{game['slug']}` — **{game['display_name']}** · {price}"
                if game["cooldown_seconds"]:
                    line += f" · 1× / {format_duration(game['cooldown_seconds'])}"
                lines.append(line)
            embed.add_field(name=str(category).capitalize(), value="\n".join(lines), inline=False)
        embed.set_footer(text="Jouez avec ,<nom du jeu> — détails avec ,jeu <nom>")
        await ctx.send(embed=embed)

    @commands.command(name="jeu")
    async def game_details(self, ctx, *, name: str):
        """Fiche d'un jeu : lots, chances reelles et cooldown."""
        game = self.engine.get_game(ctx.guild.id, normalize_slug(name))
        if game is None:
            await ctx.send("❌ Ce jeu n'existe pas.")
            return
        style = self.engine.get_style(ctx.guild.id)
        lots = self.engine.list_lots(game["id"])
        embed = Embed(
            title=game["display_name"],
            description=game["description"] or None,
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Prix",
                        value="Gratuit" if not game["price"] else self.money(style, game["price"]),
                        inline=True)
        if game["cooldown_seconds"]:
            embed.add_field(name="Disponible",
                            value=f"1× / {format_duration(game['cooldown_seconds'])}", inline=True)

        total_weight = sum(lot["weight"] for lot in lots) or 1
        lines = []
        for lot in lots:
            label = Reward(lot["reward_kind"], lot["reward_value"], lot["label"]).describe()
            if game["kind"] == "dice_sum":
                lines.append(f"`{lot['outcome']}` → {label}")
            else:
                lines.append(f"{label} — {lot['weight'] / total_weight * 100:.1f} %")
        if lines:
            embed.add_field(name="Lots", value="\n".join(lines[:20]), inline=False)

        remaining = self.engine.cooldown_remaining(ctx.guild.id, ctx.author.id, game)
        if remaining:
            embed.set_footer(text=f"Disponible dans {format_duration(remaining)}")
        await ctx.send(embed=embed)

    @commands.command()
    async def openlot(self, ctx, *, name: str = None):
        """Joue a un jeu. Sans argument, demande lequel."""
        if name is None:
            games = self.engine.list_games(ctx.guild.id)
            if not games:
                await ctx.send("Aucun jeu n'est configuré. Consultez `,shop`.")
                return
            await ctx.send("Quel jeu ? " + ", ".join(g["slug"] for g in games))
            answer = await self._ask(ctx, timeout=30.0)
            if answer is None:
                return
            name = answer.content

        game = self.engine.get_game(ctx.guild.id, normalize_slug(name))
        if game is None:
            await ctx.send("❌ Ce jeu n'existe pas.")
            return
        await self.play_game(ctx, game)

    @commands.command()
    async def inventaire(self, ctx, member: discord.Member = None):
        """Tickets, objets et nombre de parties par jeu."""
        member = member or ctx.author
        style = self.engine.get_style(ctx.guild.id)
        items = self.engine.inventory(ctx.guild.id, member.id)
        counts = self.engine.play_counts_by_game(ctx.guild.id, member.id)

        embed = Embed(title=f"🎒 Inventaire de {member.display_name}",
                      color=discord.Color.blurple())
        tickets = [f"🎟️ **{name}** × {n}" for (kind, name), n in items.items() if kind == "ticket"]
        objects = [f"📦 **{name}** × {n}" for (kind, name), n in items.items() if kind != "ticket"]
        embed.add_field(name="Tickets", value="\n".join(tickets) or "Aucun", inline=False)
        if objects:
            embed.add_field(name="Objets", value="\n".join(objects), inline=False)
        if counts:
            top = "\n".join(f"**{slug}** × {n}" for slug, n in list(counts.items())[:10])
            embed.add_field(name="Parties jouées", value=top, inline=False)
            embed.set_footer(text=f"{sum(counts.values())} partie(s) au total")
        embed.add_field(name="Solde", value=self.money(style, self.get_balance(member.id)),
                        inline=False)
        await ctx.send(embed=embed)

    @commands.command(aliases=["quetes"])
    async def quest(self, ctx):
        """Progression du joueur sur les quetes, comptee individuellement."""
        quests = self.engine.list_quests(ctx.guild.id)
        if not quests:
            await ctx.send("Aucune quête n'est configurée.")
            return
        role_ids = [role.id for role in getattr(ctx.author, "roles", [])]
        embed = Embed(title="📜 Quêtes", color=discord.Color.green())
        for quest in quests:
            progress = self.engine.quest_progress(ctx.guild.id, ctx.author.id, quest, role_ids)
            done = min(progress, quest["goal"])
            filled = int(10 * done / quest["goal"]) if quest["goal"] else 10
            bar = "▰" * filled + "▱" * (10 - filled)
            reward = Reward(quest["reward_kind"], quest["reward_value"]).describe()
            embed.add_field(
                name=f"{quest['name']} ({done}/{quest['goal']})",
                value=f"{bar}\n{quest['description'] or ''}\nRécompense : {reward}".strip(),
                inline=False,
            )
        await ctx.send(embed=embed)

    # --- commandes d'administration ---

    @commands.command()
    async def addgame(self, ctx, slug: str = None, price: float = None,
                      category: str = "box", kind: str = "box"):
        """,addgame <nom> <prix> [categorie] [type] — puis ,addlot pour les lots."""
        if slug is None:
            await ctx.send(
                "Usage : `,addgame <nom> <prix> [catégorie] [type]`\n"
                "Types : `box` (tirage pondéré), `loto` (somme de dés), `de` (pari sur un dé).\n"
                "Exemple : `,addgame \"Machine Bois\" 250 machine box`"
            )
            return
        try:
            game_id = self.engine.create_game(
                ctx.guild.id, slug,
                display_name=slug,
                kind=KIND_ALIASES.get(kind.lower(), "weighted"),
                category=category.lower(),
                price=price or 0,
            )
        except CasinoError as exc:
            await ctx.send(f"❌ {exc}")
            return
        row = self.db.fetchone("SELECT slug FROM casino_games WHERE id = ?", (game_id,))
        await ctx.send(
            f"✅ Jeu **{row['slug']}** créé. Ajoutez ses lots avec "
            f"`,addlot {row['slug']} argent 450 3` (type, valeur, poids)."
        )

    @commands.command()
    async def addlot(self, ctx, slug: str, reward_kind: str, value: str,
                     weight: float = 1.0, outcome: int = None):
        """,addlot <jeu> <argent|grade|ticket|objet> <valeur> [poids] [somme]"""
        game = self.engine.get_game(ctx.guild.id, normalize_slug(slug))
        if game is None:
            await ctx.send("❌ Ce jeu n'existe pas.")
            return
        kind = REWARD_ALIASES.get(reward_kind.lower())
        if kind is None:
            await ctx.send("❌ Types de lot : argent, grade, ticket, objet, rien.")
            return
        try:
            self.engine.add_lot(game["id"], kind, value, weight=weight, outcome=outcome)
        except CasinoError as exc:
            await ctx.send(f"❌ {exc}")
            return
        total = len(self.engine.list_lots(game["id"]))
        await ctx.send(f"✅ Lot ajouté à **{game['display_name']}** ({total} lot(s)).")

    @commands.command()
    async def rmlot(self, ctx, lot_id: int):
        """Supprime un lot par son identifiant (visible dans ,gamelots)."""
        self.engine.delete_lot(lot_id)
        await ctx.send("✅ Lot supprimé.")

    @commands.command()
    async def gamelots(self, ctx, *, slug: str):
        """Lots d'un jeu, avec identifiant et probabilite reelle."""
        game = self.engine.get_game(ctx.guild.id, normalize_slug(slug))
        if game is None:
            await ctx.send("❌ Ce jeu n'existe pas.")
            return
        lots = self.engine.list_lots(game["id"])
        if not lots:
            await ctx.send("Ce jeu n'a aucun lot.")
            return
        total = sum(lot["weight"] for lot in lots) or 1
        lines = [
            f"`#{lot['id']}` {lot['reward_kind']} {lot['reward_value']} — "
            f"poids {lot['weight']:g} ({lot['weight'] / total * 100:.1f} %)"
            + (f" · somme {lot['outcome']}" if lot["outcome"] is not None else "")
            for lot in lots
        ]
        await ctx.send(embed=Embed(title=f"Lots — {game['display_name']}",
                                   description="\n".join(lines[:25]),
                                   color=discord.Color.blurple()))

    @commands.command()
    async def deletegame(self, ctx, *, slug: str):
        game = self.engine.get_game(ctx.guild.id, normalize_slug(slug))
        if game is None:
            await ctx.send("❌ Ce jeu n'existe pas.")
            return
        self.engine.delete_game(game["id"])
        await ctx.send(f"✅ **{game['display_name']}** supprimé.")

    @commands.command()
    async def addquest(self, ctx, name: str, goal: int, reward_kind: str, value: str,
                       target_kind: str = "any", target_value: str = ""):
        """,addquest <nom> <objectif> <argent|grade|ticket> <valeur> [any|game|category|role] [cible]"""
        kind = REWARD_ALIASES.get(reward_kind.lower())
        if kind is None:
            await ctx.send("❌ Récompenses : argent, grade, ticket, objet.")
            return
        try:
            self.engine.create_quest(
                ctx.guild.id, name, goal, kind, value,
                target_kind=target_kind.lower(), target_value=target_value,
            )
        except CasinoError as exc:
            await ctx.send(f"❌ {exc}")
            return
        await ctx.send(f"✅ Quête **{name}** enregistrée.")

    @commands.command()
    async def deletequete(self, ctx, *, name: str):
        for quest in self.engine.list_quests(ctx.guild.id, include_disabled=True):
            if quest["name"].lower() == name.lower():
                self.engine.delete_quest(quest["id"])
                await ctx.send(f"✅ Quête **{quest['name']}** supprimée.")
                return
        await ctx.send("❌ Cette quête n'existe pas.")

    @commands.command()
    async def config_quete(self, ctx):
        """Rappelle ou se configurent les quetes."""
        quests = self.engine.list_quests(ctx.guild.id, include_disabled=True)
        await ctx.send(
            f"{len(quests)} quête(s) configurée(s). Ajout : `,addquest <nom> <objectif> "
            "<récompense> <valeur> [cible]`, suppression : `,deletequete <nom>`. "
            "Édition complète depuis le dashboard web."
        )

    @commands.command()
    async def clearinventory(self, ctx, user: discord.User = None):
        user = user or ctx.author
        removed = self.engine.clear_inventory(ctx.guild.id, user.id)
        if not removed:
            await ctx.send("L'inventaire de cet utilisateur est déjà vide.")
            return
        await ctx.send(f"✅ Inventaire de **{user.name}** vidé ({removed} objet(s)).")

    @commands.command()
    async def casinostats(self, ctx, *, slug: str = None):
        """Ce que le casino encaisse reellement, compare a la theorie."""
        style = self.engine.get_style(ctx.guild.id)
        if slug:
            game = self.engine.get_game(ctx.guild.id, normalize_slug(slug))
            if game is None:
                await ctx.send("❌ Ce jeu n'existe pas.")
                return
            games = [game]
        else:
            games = self.engine.list_games(ctx.guild.id, include_disabled=True)

        embed = Embed(title="📊 Santé du casino", color=discord.Color.gold())
        overall = self.engine.actual_stats(ctx.guild.id)
        embed.description = (
            f"**{overall['plays']}** partie(s) · misé {self.money(style, overall['cost'])} · "
            f"versé {self.money(style, overall['payout'])} · "
            f"**bilan {self.money(style, overall['net'])}**"
        )
        for game in games[:15]:
            stats = self.engine.actual_stats(ctx.guild.id, game["slug"])
            theoretical = self.engine.theoretical_rtp(game)
            parts = [f"gain moyen {self.money(style, self.engine.expected_value(game))}"]
            if theoretical is not None:
                flag = " ⚠️" if theoretical > 1 else ""
                parts.append(f"RTP théorique {theoretical * 100:.0f} %{flag}")
            if stats["rtp"] is not None:
                parts.append(f"réel {stats['rtp'] * 100:.0f} % sur {stats['plays']}")
            embed.add_field(name=game["display_name"], value=" · ".join(parts), inline=False)
        embed.set_footer(text="Un RTP théorique > 100 % signifie que le jeu crée de la monnaie.")
        await ctx.send(embed=embed)

    # --- invocation directe ,<slug> ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Permet `,b-gratuite` sans declarer une commande par jeu.

        Les jeux etant des donnees, leurs noms ne peuvent pas etre des commandes
        enregistrees : on rattrape donc les messages qui ne correspondent a
        aucune commande connue mais au slug d'un jeu.
        """
        if message.author.bot or not message.guild:
            return
        prefix = getattr(self.bot, "command_prefix", ",")
        if not isinstance(prefix, str) or not message.content.startswith(prefix):
            return
        parts = message.content[len(prefix):].strip().split()
        if not parts:
            return
        if self.bot.get_command(parts[0]) is not None:
            return
        slug = normalize_slug(parts[0])
        if not slug:
            return
        game = self.engine.get_game(message.guild.id, slug)
        if game is None:
            return
        ctx = await self.bot.get_context(message)
        if ctx.author is None:
            return
        await self.play_game(ctx, game, guess=parts[1] if len(parts) > 1 else None)


def setup(bot, db):
    bot.add_cog(cmdjeu(bot, db))
