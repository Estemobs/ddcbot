"""Systeme de tickets de support.

Permet aux membres de creer des tickets de support privees avec les admins.
"""

import time

import discord
from discord.ext import commands

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

    def build_panel_embed(self, guild, cfg):
        embed = discord.Embed(title="Configuration Tickets", color=discord.Color.blue())
        embed.add_field(name="Active", value="✅" if cfg["enabled"] else "❌", inline=True)
        embed.add_field(name="Categorie", value=f"<#{cfg['category_id']}>" if cfg["category_id"] else "—", inline=True)
        embed.add_field(name="Canal logs", value=f"<#{cfg['log_channel_id']}>" if cfg["log_channel_id"] else "—", inline=True)
        embed.add_field(name="Max ouverts", value=str(cfg["max_open_tickets"]), inline=True)
        return embed

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def ticketpanel(self, ctx):
        """Affiche le panneau de configuration des tickets."""
        cfg = self.get_config(ctx.guild.id)
        embed = self.build_panel_embed(ctx.guild, cfg)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def ticketcategory(self, ctx, category: discord.CategoryChannel = None):
        """Definit la categorie pour les tickets."""
        if category is None:
            await ctx.send("Usage: `,ticketcategory #categorie`")
            return
        self.save_config(ctx.guild.id, category_id=category.id)
        await ctx.send(f"✅ Categorie de tickets definie sur **{category.name}**.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def ticketwelcome(self, ctx, *, message: str = None):
        """Definit le message de bienvenue des tickets."""
        if message is None:
            await ctx.send("Usage: `,ticketwelcome Votre message`")
            return
        self.save_config(ctx.guild.id, welcome_message=message)
        await ctx.send(f"✅ Message de bienvenue mis a jour.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def ticketmax(self, ctx, max_tickets: int = None):
        """Definit le max de tickets ouverts par utilisateur."""
        if max_tickets is None or max_tickets < 1:
            await ctx.send("Usage: `,ticketmax 5`")
            return
        self.save_config(ctx.guild.id, max_open_tickets=max_tickets)
        await ctx.send(f"✅ Max tickets ouverts defini sur `{max_tickets}`.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
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
        cfg = self.get_config(ctx.guild.id)
        if not cfg["enabled"]:
            await ctx.send("❌ Les tickets sont desactives sur ce serveur.")
            return

        open_count = self.get_open_count(ctx.guild.id, ctx.author.id)
        if open_count >= cfg["max_open_tickets"]:
            await ctx.send(f"❌ Vous avez deja {open_count} ticket(s) ouvert(s).")
            return

        if not cfg["category_id"]:
            await ctx.send("❌ Les tickets ne sont pas configures (categorie manquante).")
            return

        category = ctx.guild.get_channel(cfg["category_id"])
        if not category:
            await ctx.send("❌ La categorie de tickets n'existe plus.")
            return

        ticket_number = self.get_ticket_number(ctx.guild.id) + 1
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            ctx.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        channel = await ctx.guild.create_text_channel(
            f"ticket-{ticket_number:04d}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket #{ticket_number} de {ctx.author}",
        )
        self.create_ticket_record(ctx.guild.id, ctx.author.id, channel.id)

        embed = discord.Embed(
            title=f"🎫 Ticket #{ticket_number:04d}",
            description=cfg["welcome_message"],
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"Ticket cree par {ctx.author}")
        await channel.send(content=ctx.author.mention, embed=embed)
        await ctx.send(f"✅ Ticket cree : {channel.mention}", delete_after=10)

    @commands.command()
    async def closeticket(self, ctx, *, reason: str = "Aucune raison"):
        """Ferme le ticket courant (utilisable dans le salon ticket)."""
        if not ctx.channel.name.startswith("ticket-"):
            await ctx.send("❌ Cette commande n'est utiliseable que dans un salon ticket.")
            return

        cfg = self.get_config(ctx.guild.id)
        self.close_ticket(ctx.channel.id)

        close_msg = cfg["close_message"] or "Ticket ferme."
        embed = discord.Embed(
            title="🔒 Ticket ferme",
            description=f"{close_msg}\n\nRaison: {reason}",
            color=discord.Color.red(),
        )
        embed.set_footer(text=f"Ferme par {ctx.author}")
        await ctx.send(embed=embed)

        log_channel = self.bot.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None
        if log_channel:
            log_embed = discord.Embed(
                title="🎫 Ticket ferme",
                description=f"Salon: {ctx.channel.name}\nFerme par: {ctx.author.mention}\nRaison: {reason}",
                color=discord.Color.orange(),
            )
            await log_channel.send(embed=log_embed)

        await ctx.channel.delete(reason=f"Ticket ferme par {ctx.author}")


def setup(bot, db):
    bot.add_cog(cmdtickets(bot, db))
