"""Systeme de tickets de support.

Permet aux membres d'ouvrir un salon prive avec le staff, depuis un bouton ou
la commande `,ticket`.

`,ticketpanel` publie le panneau que les membres cliquent ; `,ticketconfig`
regroupe les reglages, y compris l'activation et le message de fermeture, qui
n'etaient joignables que depuis le dashboard.
"""

import time

import discord
from discord.ext import commands

from settings_fields import Field, FieldError, apply_field, describe_fields

# Les identifiants sont fixes : c'est ce qui permet aux boutons de continuer a
# fonctionner apres un redemarrage du bot, sur des messages deja publies.
OPEN_BUTTON_ID = "ddcbot:ticket:open"
CLOSE_BUTTON_ID = "ddcbot:ticket:close"

TICKET_FIELDS = {
    "actif": Field("bool", "Tickets activés"),
    "categorie": Field("id", "Catégorie où créer les salons de ticket"),
    "salonlogs": Field("id", "Salon de journal des tickets"),
    "max": Field("int", "Tickets ouverts simultanément par membre", minimum=1, maximum=50),
    "bienvenue": Field("text", "Message affiché à l'ouverture d'un ticket"),
    "fermeture": Field("text", "Message affiché à la fermeture"),
}
TICKET_FIELD_COLUMNS = {
    "actif": "enabled", "categorie": "category_id", "salonlogs": "log_channel_id",
    "max": "max_open_tickets", "bienvenue": "welcome_message",
    "fermeture": "close_message",
}


class TicketPanelView(discord.ui.View):
    """Panneau permanent : un bouton qui ouvre un ticket.

    timeout=None et un custom_id fixe rendent la vue persistante : le bouton
    reste actif sur un message publie il y a des semaines, tant que le cog
    reenregistre la vue au demarrage.
    """

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Ouvrir un ticket", emoji="🎫",
                       style=discord.ButtonStyle.primary, custom_id=OPEN_BUTTON_ID)
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, problem = await self.cog.open_ticket(interaction.guild, interaction.user)
        if problem:
            await interaction.response.send_message(f"❌ {problem}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✅ Votre ticket : {channel.mention}", ephemeral=True
        )


class TicketCloseView(discord.ui.View):
    """Bouton de fermeture, publie dans le salon du ticket."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Fermer le ticket", emoji="🔒",
                       style=discord.ButtonStyle.danger, custom_id=CLOSE_BUTTON_ID)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Fermeture du ticket…")
        await self.cog.close_and_delete(
            interaction.channel, interaction.user, "Fermé depuis le bouton"
        )


DEFAULT_TICKET_CONFIG = {
    "enabled": False,
    "category_id": None,
    "log_channel_id": None,
    "welcome_message": "Bienvenue dans votre ticket. Decrivez votre probleme.",
    "close_message": "Ticket ferme. Merci.",
    "max_open_tickets": 5,
}


class cmdtickets(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._cfg_initialized = set()

    def get_config(self, guild_id: int) -> dict:
        if guild_id not in self._cfg_initialized:
            self._cfg_initialized.add(guild_id)
            self.db.execute(
                "INSERT OR IGNORE INTO ticket_config "
                "(guild_id, enabled, category_id, log_channel_id, welcome_message, close_message, max_open_tickets) "
                "VALUES (?, 0, NULL, NULL, ?, ?, 5)",
                (guild_id, DEFAULT_TICKET_CONFIG["welcome_message"], DEFAULT_TICKET_CONFIG["close_message"]),
            )
        row = self.db.fetchone(
            "SELECT enabled, category_id, log_channel_id, welcome_message, close_message, max_open_tickets "
            "FROM ticket_config WHERE guild_id = ?", (guild_id,),
        )
        return {
            "enabled": bool(row["enabled"]),
            "category_id": row["category_id"],
            "log_channel_id": row["log_channel_id"],
            "welcome_message": row["welcome_message"],
            "close_message": row["close_message"],
            "max_open_tickets": row["max_open_tickets"],
        }

    def save_config(self, guild_id: int, **fields):
        self.get_config(guild_id)
        assignments, values = [], []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(int(value) if isinstance(value, bool) else value)
        values.append(guild_id)
        self.db.execute(f"UPDATE ticket_config SET {', '.join(assignments)} WHERE guild_id = ?", values)

    def get_open_count(self, guild_id: int, user_id: int) -> int:
        row = self.db.fetchone(
            "SELECT COUNT(*) as c FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'",
            (guild_id, user_id),
        )
        return row["c"] if row else 0

    def create_ticket_record(self, guild_id: int, user_id: int, channel_id: int):
        self.db.execute(
            "INSERT INTO tickets (guild_id, user_id, channel_id, status, created_at) "
            "VALUES (?, ?, ?, 'open', ?)", (guild_id, user_id, channel_id, time.time()),
        )
        self.db.execute(
            "INSERT INTO ticket_counter (guild_id, counter) VALUES (?, 1) "
            "ON CONFLICT(guild_id) DO UPDATE SET counter = counter + 1", (guild_id,),
        )

    def close_ticket(self, channel_id: int):
        self.db.execute(
            "UPDATE tickets SET status = 'closed', closed_at = ? WHERE channel_id = ?",
            (time.time(), channel_id),
        )

    def get_ticket_number(self, guild_id: int) -> int:
        row = self.db.fetchone("SELECT counter FROM ticket_counter WHERE guild_id = ?", (guild_id,))
        return row["counter"] if row else 0

    async def open_ticket(self, guild, member):
        """Cree le salon de ticket. Renvoie (salon, None) ou (None, raison du refus)."""
        cfg = self.get_config(guild.id)
        if not cfg["enabled"]:
            return None, "Les tickets sont désactivés sur ce serveur."
        if self.get_open_count(guild.id, member.id) >= cfg["max_open_tickets"]:
            return None, f"Vous avez déjà {cfg['max_open_tickets']} ticket(s) ouvert(s)."
        if not cfg["category_id"]:
            return None, "Les tickets ne sont pas configurés (catégorie manquante)."
        category = guild.get_channel(cfg["category_id"])
        if category is None:
            return None, "La catégorie de tickets n'existe plus."

        number = self.get_ticket_number(guild.id) + 1
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }
        try:
            channel = await guild.create_text_channel(
                f"ticket-{number:04d}", category=category, overwrites=overwrites,
                topic=f"Ticket #{number} de {member}",
            )
        except discord.Forbidden:
            return None, "Le bot n'a pas la permission de créer le salon."
        except discord.HTTPException as exc:
            return None, f"Création impossible : {exc}"

        self.create_ticket_record(guild.id, member.id, channel.id)
        embed = discord.Embed(
            title=f"🎫 Ticket #{number:04d}",
            description=cfg["welcome_message"],
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"Ticket cree par {member}")
        await channel.send(content=member.mention, embed=embed, view=TicketCloseView(self))
        return channel, None

    async def close_and_delete(self, channel, author, reason: str):
        """Journalise la fermeture puis supprime le salon."""
        guild = channel.guild
        cfg = self.get_config(guild.id)
        self.close_ticket(channel.id)

        log_channel = self.bot.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None
        if log_channel is not None:
            log_embed = discord.Embed(
                title="🎫 Ticket ferme",
                description=f"Salon: {channel.name}\nFerme par: {author.mention}\n"
                            f"Raison: {reason}",
                color=discord.Color.orange(),
            )
            try:
                await log_channel.send(embed=log_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass
        try:
            await channel.delete(reason=f"Ticket ferme par {author}")
        except discord.NotFound:
            pass  # salon deja supprime : rien a signaler
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        # Reenregistre les vues pour que les boutons deja publies restent actifs.
        try:
            self.bot.add_view(TicketPanelView(self))
            self.bot.add_view(TicketCloseView(self))
        except Exception as exc:
            print(f"[DEBUG] Vues tickets non reenregistrees: {exc}")

    @commands.command()
    async def ticketpanel(self, ctx, channel: discord.TextChannel = None):
        """Publie le panneau que les membres cliquent pour ouvrir un ticket."""
        cfg = self.get_config(ctx.guild.id)
        target = channel or ctx.channel
        embed = discord.Embed(
            title="🎫 Besoin d'aide ?",
            description=cfg["welcome_message"],
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Cliquez sur le bouton pour ouvrir un ticket privé.")
        try:
            await target.send(embed=embed, view=TicketPanelView(self))
        except discord.Forbidden:
            await ctx.send("❌ Le bot ne peut pas écrire dans ce salon.")
            return
        if not cfg["enabled"]:
            await ctx.send(
                "⚠️ Panneau publié, mais les tickets sont désactivés : "
                "`,ticketconfig actif on`."
            )
        elif target.id != ctx.channel.id:
            await ctx.send(f"✅ Panneau publié dans {target.mention}.")

    @commands.command()
    async def ticketconfig(self, ctx, field: str = None, *, value: str = None):
        """,ticketconfig <champ> <valeur> — sans champ, affiche les réglages."""
        cfg = self.get_config(ctx.guild.id)
        if field is None:
            current = {key: cfg[column] for key, column in TICKET_FIELD_COLUMNS.items()}
            embed = discord.Embed(
                title="🎫 Réglages des tickets",
                description=describe_fields(TICKET_FIELDS, current),
                color=discord.Color.blue(),
            )
            embed.set_footer(text="Publier le panneau : ,ticketpanel [#salon]")
            await ctx.send(embed=embed)
            return
        try:
            key, parsed = apply_field(TICKET_FIELDS, field, value)
        except FieldError as exc:
            await ctx.send(f"❌ {exc}")
            return
        self.save_config(ctx.guild.id, **{TICKET_FIELD_COLUMNS[key]: parsed})
        await ctx.send(f"✅ `{key}` = **{parsed}**")

    @commands.command()
    async def ticketcategory(self, ctx, category: discord.CategoryChannel = None):
        """Definit la categorie pour les tickets."""
        if category is None:
            await ctx.send("Usage: `,ticketcategory #categorie`")
            return
        self.save_config(ctx.guild.id, category_id=category.id)
        await ctx.send(f"✅ Categorie de tickets definie sur **{category.name}**.")

    @commands.command()
    async def ticketwelcome(self, ctx, *, message: str = None):
        """Definit le message de bienvenue des tickets."""
        if message is None:
            await ctx.send("Usage: `,ticketwelcome Votre message`")
            return
        self.save_config(ctx.guild.id, welcome_message=message)
        await ctx.send("✅ Message de bienvenue mis a jour.")

    @commands.command()
    async def ticketmax(self, ctx, max_tickets: int = None):
        """Definit le max de tickets ouverts par utilisateur."""
        if max_tickets is None or max_tickets < 1:
            await ctx.send("Usage: `,ticketmax 5`")
            return
        self.save_config(ctx.guild.id, max_open_tickets=max_tickets)
        await ctx.send(f"✅ Max tickets ouverts defini sur `{max_tickets}`.")

    @commands.command()
    async def ticketlog(self, ctx, channel: discord.TextChannel = None):
        """Definit le canal de logs des tickets."""
        if channel is None:
            self.save_config(ctx.guild.id, log_channel_id=None)
            await ctx.send("Logs tickets desactivees.")
        else:
            self.save_config(ctx.guild.id, log_channel_id=channel.id)
            await ctx.send(f"✅ Canal de logs tickets defini sur {channel.mention}.")

    @commands.command()
    async def ticket(self, ctx):
        """Cree un ticket de support."""
        channel, problem = await self.open_ticket(ctx.guild, ctx.author)
        if problem:
            await ctx.send(f"❌ {problem}")
            return
        await ctx.send(f"✅ Ticket cree : {channel.mention}", delete_after=10)

    @commands.command()
    async def closeticket(self, ctx, *, reason: str = "Aucune raison"):
        """Ferme le ticket courant (utilisable dans le salon ticket)."""
        if not ctx.channel.name.startswith("ticket-"):
            await ctx.send("❌ Cette commande n'est utiliseable que dans un salon ticket.")
            return

        cfg = self.get_config(ctx.guild.id)
        embed = discord.Embed(
            title="🔒 Ticket ferme",
            description=f"{cfg['close_message'] or 'Ticket ferme.'}\n\nRaison: {reason}",
            color=discord.Color.red(),
        )
        embed.set_footer(text=f"Ferme par {ctx.author}")
        await ctx.send(embed=embed)
        await self.close_and_delete(ctx.channel, ctx.author, reason)


def setup(bot, db):
    bot.add_cog(cmdtickets(bot, db))
