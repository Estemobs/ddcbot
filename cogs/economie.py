import discord
from discord.ext import commands


DEFAULT_ECO_CONFIG = {
    "allow_transfers": True,
    "max_transfer": 10000,
    "allow_negative_balances": False,
    "log_channel_id": None,
}


class EconomyPanelView(discord.ui.View):
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
        cfg = self.cog.get_eco_config(interaction.guild.id)
        embed = self.cog.build_eco_panel_embed(interaction.guild, cfg)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle transferts", style=discord.ButtonStyle.primary, row=0)
    async def toggle_transfers(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_eco_config(self.guild_id)
        self.cog.update_eco_config(self.guild_id, allow_transfers=not cfg["allow_transfers"])
        await self.refresh(interaction)

    @discord.ui.button(label="Max transfert +500", style=discord.ButtonStyle.secondary, row=0)
    async def max_plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_eco_config(self.guild_id)
        self.cog.update_eco_config(self.guild_id, max_transfer=cfg["max_transfer"] + 500)
        await self.refresh(interaction)

    @discord.ui.button(label="Max transfert -500", style=discord.ButtonStyle.secondary, row=0)
    async def max_minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_eco_config(self.guild_id)
        self.cog.update_eco_config(self.guild_id, max_transfer=max(1, cfg["max_transfer"] - 500))
        await self.refresh(interaction)

    @discord.ui.button(label="Toggle solde negatif", style=discord.ButtonStyle.primary, row=1)
    async def toggle_negative(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_eco_config(self.guild_id)
        self.cog.update_eco_config(self.guild_id, allow_negative_balances=not cfg["allow_negative_balances"])
        await self.refresh(interaction)

    @discord.ui.button(label="Canal logs = ici", style=discord.ButtonStyle.secondary, row=1)
    async def set_log_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.update_eco_config(self.guild_id, log_channel_id=interaction.channel_id)
        await self.refresh(interaction)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=1)
    async def reset_defaults(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.reset_eco_config(self.guild_id)
        await self.refresh(interaction)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, row=2)
    async def close_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        cfg = self.cog.get_eco_config(interaction.guild.id)
        embed = self.cog.build_eco_panel_embed(interaction.guild, cfg)
        embed.set_footer(text="Panneau ferme")
        await interaction.response.edit_message(embed=embed, view=self)


class cmdeco(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.intents = discord.Intents.all()

    # --- balances ---

    def has_account(self, user_id: int) -> bool:
        return self.db.fetchone("SELECT 1 FROM balances WHERE user_id = ?", (user_id,)) is not None

    def get_balance(self, user_id: int) -> float:
        row = self.db.fetchone("SELECT amount FROM balances WHERE user_id = ?", (user_id,))
        return row["amount"] if row else 0.0

    def create_account(self, user_id: int, amount: float = 0.0):
        self.db.execute("INSERT OR IGNORE INTO balances (user_id, amount) VALUES (?, ?)", (user_id, amount))

    def add_balance(self, user_id: int, delta: float):
        self.db.execute(
            "INSERT INTO balances (user_id, amount) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET amount = amount + excluded.amount",
            (user_id, delta),
        )

    def set_balance(self, user_id: int, amount: float):
        self.db.execute(
            "INSERT INTO balances (user_id, amount) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET amount = excluded.amount",
            (user_id, amount),
        )

    # --- config economie par serveur ---

    def get_eco_config(self, guild_id: int) -> dict:
        self.db.execute(
            "INSERT OR IGNORE INTO economy_config "
            "(guild_id, allow_transfers, max_transfer, allow_negative_balances, log_channel_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                guild_id,
                int(DEFAULT_ECO_CONFIG["allow_transfers"]),
                DEFAULT_ECO_CONFIG["max_transfer"],
                int(DEFAULT_ECO_CONFIG["allow_negative_balances"]),
                DEFAULT_ECO_CONFIG["log_channel_id"],
            ),
        )
        row = self.db.fetchone(
            "SELECT allow_transfers, max_transfer, allow_negative_balances, log_channel_id "
            "FROM economy_config WHERE guild_id = ?",
            (guild_id,),
        )
        return {
            "allow_transfers": bool(row["allow_transfers"]),
            "max_transfer": row["max_transfer"],
            "allow_negative_balances": bool(row["allow_negative_balances"]),
            "log_channel_id": row["log_channel_id"],
        }

    def update_eco_config(self, guild_id: int, **fields):
        self.get_eco_config(guild_id)
        assignments = []
        values = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(int(value) if isinstance(value, bool) else value)
        values.append(guild_id)
        self.db.execute(
            f"UPDATE economy_config SET {', '.join(assignments)} WHERE guild_id = ?",
            values,
        )

    def reset_eco_config(self, guild_id: int):
        self.db.execute(
            "INSERT INTO economy_config "
            "(guild_id, allow_transfers, max_transfer, allow_negative_balances, log_channel_id) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET allow_transfers=excluded.allow_transfers, "
            "max_transfer=excluded.max_transfer, allow_negative_balances=excluded.allow_negative_balances, "
            "log_channel_id=excluded.log_channel_id",
            (
                guild_id,
                int(DEFAULT_ECO_CONFIG["allow_transfers"]),
                DEFAULT_ECO_CONFIG["max_transfer"],
                int(DEFAULT_ECO_CONFIG["allow_negative_balances"]),
                DEFAULT_ECO_CONFIG["log_channel_id"],
            ),
        )

    async def send_eco_log(self, guild: discord.Guild, message: str):
        cfg = self.get_eco_config(guild.id)
        channel_id = cfg.get("log_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel:
            await channel.send(message)

    def build_eco_panel_embed(self, guild: discord.Guild, cfg: dict):
        channel_id = cfg.get("log_channel_id")
        log_channel = guild.get_channel(channel_id) if channel_id else None
        log_label = f"#{log_channel.name}" if log_channel else "Non defini"

        embed = discord.Embed(
            title="Panneau Economie",
            description="Configuration globale de l'economie du serveur.",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Transferts entre membres", value="Actif" if cfg["allow_transfers"] else "Desactive", inline=True)
        embed.add_field(name="Max transfert", value=str(cfg["max_transfer"]), inline=True)
        embed.add_field(name="Solde negatif", value="Autorise" if cfg["allow_negative_balances"] else "Interdit", inline=True)
        embed.add_field(name="Canal logs", value=log_label, inline=False)
        embed.set_footer(text=f"Serveur: {guild.name}")
        return embed

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def ecopanel(self, ctx):
        cfg = self.get_eco_config(ctx.guild.id)
        embed = self.build_eco_panel_embed(ctx.guild, cfg)
        view = EconomyPanelView(self, ctx.guild.id, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def mybalance(self, ctx):
        member = ctx.author
        if not self.has_account(member.id):
            self.create_account(member.id, 0)
            await ctx.send('Votre solde est de **0.00** pièces.')
        else:
            await ctx.send(f'Votre solde est de **{self.get_balance(member.id):.2f}** pièces.')

    @commands.command()
    async def balance(self, ctx, member: discord.Member):
        if not self.has_account(member.id):
            self.create_account(member.id, 0)
            await ctx.send(f'Un compte a été créé pour {member.mention} avec un solde de {self.get_balance(member.id):.2f}.')
        else:
            await ctx.send(f'{member.mention} a un solde de {self.get_balance(member.id):.2f}.')

    @commands.command()
    async def addmoney(self, ctx, member: discord.Member, amount: float):
        if amount <= 0:
            await ctx.send("Le montant doit etre superieur a 0.")
            return
        if not self.has_account(member.id):
            self.create_account(member.id, amount)
            await ctx.send(f'Un compte a été créé pour {member.mention} avec un solde de {amount:.2f}.')
        else:
            self.add_balance(member.id, amount)
            await ctx.send(f'{amount:.2f} a été ajouté au compte de {member.mention}. Nouveau solde : {self.get_balance(member.id):.2f}.')
        await self.send_eco_log(ctx.guild, f"[ECO] +{amount:.2f} pour {member.mention} par {ctx.author.mention}")

    @commands.command()
    async def removemoney(self, ctx, member: discord.Member, amount: float):
        if amount <= 0:
            await ctx.send("Le montant doit etre superieur a 0.")
            return
        if not self.has_account(member.id):
            await ctx.send(f"{member.mention} n'a pas de compte.")
            return
        cfg = self.get_eco_config(ctx.guild.id)
        current = self.get_balance(member.id)
        if cfg["allow_negative_balances"] or current >= amount:
            self.add_balance(member.id, -amount)
            await ctx.send(f'{amount:.2f} a été retiré du compte de {member.mention}. Nouveau solde : {self.get_balance(member.id):.2f}.')
            await self.send_eco_log(ctx.guild, f"[ECO] -{amount:.2f} pour {member.mention} par {ctx.author.mention}")
        else:
            await ctx.send(f"{member.mention} n'a pas suffisamment de fonds pour retirer {amount:.2f}. Solde actuel : {current:.2f}.")

    @commands.command()
    async def paye(self, ctx, member: discord.Member, amount: float):
        cfg = self.get_eco_config(ctx.guild.id)
        if not cfg["allow_transfers"]:
            await ctx.send("Les transferts entre membres sont desactives sur ce serveur.")
            return
        if amount <= 0:
            await ctx.send("Le montant doit etre superieur a 0.")
            return
        if amount > cfg["max_transfer"]:
            await ctx.send(f"Montant trop eleve. Maximum autorise: {cfg['max_transfer']}.")
            return
        if not self.has_account(ctx.author.id):
            await ctx.send("Vous n'avez pas de compte.")
            return
        if self.get_balance(ctx.author.id) < amount:
            await ctx.send("Vous n'avez pas suffisamment d'argent sur votre compte.")
            return
        self.add_balance(member.id, amount)
        self.add_balance(ctx.author.id, -amount)
        await ctx.send(f"{amount:.2f} a été donné à {member.mention}. Votre nouveau solde est : {self.get_balance(ctx.author.id):.2f}.")
        await self.send_eco_log(ctx.guild, f"[ECO] transfert {amount:.2f} de {ctx.author.mention} vers {member.mention}")

    @commands.command()
    async def leaderboard(self, ctx):
        rows = self.db.fetchall("SELECT user_id, amount FROM balances WHERE amount > 0 ORDER BY amount DESC LIMIT 10")
        embed = discord.Embed(title="Top 10 des utilisateurs les plus riches :", color=0xffd700)
        for i, row in enumerate(rows):
            member = ctx.guild.get_member(row["user_id"])
            if member:
                embed.add_field(name=f"{i+1}. {member.display_name}", value=f"{row['amount']:.2f}", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def clean_leaderboard(self, ctx):
        server_user_ids = {member.id for member in ctx.guild.members}
        rows = self.db.fetchall("SELECT user_id FROM balances")
        for row in rows:
            if row["user_id"] not in server_user_ids:
                self.db.execute("DELETE FROM balances WHERE user_id = ?", (row["user_id"],))
        await ctx.send("Le leaderboard a été nettoyé.")

    @commands.command()
    async def reset_money(self, ctx, member: discord.Member):
        if not self.has_account(member.id):
            await ctx.send(f"{member.mention} n'a pas de compte.")
        else:
            self.set_balance(member.id, 0.0)
            await ctx.send(f"Le solde de {member.mention} a été réinitialisé.")

    @commands.command()
    async def reset_economy(self, ctx):
        self.db.execute("UPDATE balances SET amount = 0.0")
        await ctx.send("Les comptes de tous les utilisateurs ont été remis à zéro.")


def setup(bot, db):
    bot.add_cog(cmdeco(bot, db))
