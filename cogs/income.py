import discord
import time
from discord.ext import commands


DEFAULT_INCOME_CONFIG = {
    "collect_enabled": True,
    "default_amount": 100.0,
    "default_interval_hours": 24,
    "log_channel_id": None,
}


class IncomePanelView(discord.ui.View):
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
        cfg = self.cog.get_income_config(interaction.guild.id)
        embed = self.cog.build_income_panel_embed(interaction.guild, cfg)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle collecte", style=discord.ButtonStyle.primary, row=0)
    async def toggle_collect(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_income_config(self.guild_id)
        self.cog.update_income_config(self.guild_id, collect_enabled=not cfg["collect_enabled"])
        await self.refresh(interaction)

    @discord.ui.button(label="Montant defaut +10", style=discord.ButtonStyle.secondary, row=0)
    async def amount_plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_income_config(self.guild_id)
        new_amount = round(float(cfg["default_amount"]) + 10.0, 2)
        self.cog.update_income_config(self.guild_id, default_amount=new_amount)
        await self.refresh(interaction)

    @discord.ui.button(label="Montant defaut -10", style=discord.ButtonStyle.secondary, row=0)
    async def amount_minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_income_config(self.guild_id)
        new_amount = max(1.0, round(float(cfg["default_amount"]) - 10.0, 2))
        self.cog.update_income_config(self.guild_id, default_amount=new_amount)
        await self.refresh(interaction)

    @discord.ui.button(label="Intervalle +1h", style=discord.ButtonStyle.secondary, row=1)
    async def interval_plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_income_config(self.guild_id)
        new_interval = int(cfg["default_interval_hours"]) + 1
        self.cog.update_income_config(self.guild_id, default_interval_hours=new_interval)
        await self.refresh(interaction)

    @discord.ui.button(label="Intervalle -1h", style=discord.ButtonStyle.secondary, row=1)
    async def interval_minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_income_config(self.guild_id)
        new_interval = max(1, int(cfg["default_interval_hours"]) - 1)
        self.cog.update_income_config(self.guild_id, default_interval_hours=new_interval)
        await self.refresh(interaction)

    @discord.ui.button(label="Canal logs = ici", style=discord.ButtonStyle.secondary, row=1)
    async def set_log_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.update_income_config(self.guild_id, log_channel_id=interaction.channel_id)
        await self.refresh(interaction)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=2)
    async def reset_defaults(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.reset_income_config(self.guild_id)
        await self.refresh(interaction)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, row=2)
    async def close_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        cfg = self.cog.get_income_config(interaction.guild.id)
        embed = self.cog.build_income_panel_embed(interaction.guild, cfg)
        embed.set_footer(text="Panneau ferme")
        await interaction.response.edit_message(embed=embed, view=self)


class cmdincome(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.intents = discord.Intents.all()

    # --- balances (table partagée avec economie.py/jeu.py/work.py) ---

    def has_account(self, user_id: int) -> bool:
        return self.db.fetchone("SELECT 1 FROM balances WHERE user_id = ?", (user_id,)) is not None

    def get_balance(self, user_id: int) -> float:
        row = self.db.fetchone("SELECT amount FROM balances WHERE user_id = ?", (user_id,))
        return row["amount"] if row else 0.0

    def add_balance(self, user_id: int, delta: float):
        self.db.execute(
            "INSERT INTO balances (user_id, amount) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET amount = amount + excluded.amount",
            (user_id, delta),
        )

    # --- role_income ---

    def list_role_income(self) -> dict:
        rows = self.db.fetchall("SELECT role_id, name, amount, collect_interval, last_collect FROM role_income")
        return {
            str(row["role_id"]): {
                "name": row["name"],
                "amount": row["amount"],
                "collect_interval": row["collect_interval"],
                "last_collect": row["last_collect"],
            }
            for row in rows
        }

    def get_role_income(self, role_id: int):
        row = self.db.fetchone(
            "SELECT name, amount, collect_interval, last_collect FROM role_income WHERE role_id = ?",
            (role_id,),
        )
        if row is None:
            return None
        return {
            "name": row["name"],
            "amount": row["amount"],
            "collect_interval": row["collect_interval"],
            "last_collect": row["last_collect"],
        }

    def add_role_income(self, role_id: int, name: str, amount: float, collect_interval: int):
        self.db.execute(
            "INSERT INTO role_income (role_id, name, amount, collect_interval, last_collect) VALUES (?, ?, ?, ?, 0)",
            (role_id, name, amount, collect_interval),
        )

    def remove_role_income(self, role_id: int):
        self.db.execute("DELETE FROM role_income WHERE role_id = ?", (role_id,))

    def update_role_income(self, role_id: int, amount: float, collect_interval: int):
        self.db.execute(
            "UPDATE role_income SET amount = ?, collect_interval = ? WHERE role_id = ?",
            (amount, collect_interval, role_id),
        )

    def set_role_income_last_collect(self, role_id: int, timestamp: float):
        self.db.execute("UPDATE role_income SET last_collect = ? WHERE role_id = ?", (timestamp, role_id))

    # --- config revenus passifs par serveur ---

    def get_income_config(self, guild_id: int) -> dict:
        self.db.execute(
            "INSERT OR IGNORE INTO income_config "
            "(guild_id, collect_enabled, default_amount, default_interval_hours, log_channel_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                guild_id,
                int(DEFAULT_INCOME_CONFIG["collect_enabled"]),
                DEFAULT_INCOME_CONFIG["default_amount"],
                DEFAULT_INCOME_CONFIG["default_interval_hours"],
                DEFAULT_INCOME_CONFIG["log_channel_id"],
            ),
        )
        row = self.db.fetchone(
            "SELECT collect_enabled, default_amount, default_interval_hours, log_channel_id "
            "FROM income_config WHERE guild_id = ?",
            (guild_id,),
        )
        return {
            "collect_enabled": bool(row["collect_enabled"]),
            "default_amount": row["default_amount"],
            "default_interval_hours": row["default_interval_hours"],
            "log_channel_id": row["log_channel_id"],
        }

    def update_income_config(self, guild_id: int, **fields):
        self.get_income_config(guild_id)
        assignments = []
        values = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(int(value) if isinstance(value, bool) else value)
        values.append(guild_id)
        self.db.execute(f"UPDATE income_config SET {', '.join(assignments)} WHERE guild_id = ?", values)

    def reset_income_config(self, guild_id: int):
        self.db.execute(
            "INSERT INTO income_config (guild_id, collect_enabled, default_amount, default_interval_hours, log_channel_id) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET collect_enabled=excluded.collect_enabled, "
            "default_amount=excluded.default_amount, default_interval_hours=excluded.default_interval_hours, "
            "log_channel_id=excluded.log_channel_id",
            (
                guild_id,
                int(DEFAULT_INCOME_CONFIG["collect_enabled"]),
                DEFAULT_INCOME_CONFIG["default_amount"],
                DEFAULT_INCOME_CONFIG["default_interval_hours"],
                DEFAULT_INCOME_CONFIG["log_channel_id"],
            ),
        )

    async def send_income_log(self, guild: discord.Guild, message: str):
        cfg = self.get_income_config(guild.id)
        channel_id = cfg.get("log_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel:
            await channel.send(message)

    def build_income_panel_embed(self, guild: discord.Guild, cfg: dict):
        channel_id = cfg.get("log_channel_id")
        log_channel = guild.get_channel(channel_id) if channel_id else None
        log_label = f"#{log_channel.name}" if log_channel else "Non defini"

        embed = discord.Embed(
            title="Panneau Revenus Passifs",
            description="Configuration des revenus passifs et de la collecte.",
            color=discord.Color.teal(),
        )
        embed.add_field(name="Collecte active", value="Oui" if cfg["collect_enabled"] else "Non", inline=True)
        embed.add_field(name="Montant defaut", value=f"{float(cfg['default_amount']):.2f}", inline=True)
        embed.add_field(name="Intervalle defaut", value=f"{int(cfg['default_interval_hours'])}h", inline=True)
        embed.add_field(name="Canal logs", value=log_label, inline=False)
        embed.set_footer(text=f"Serveur: {guild.name}")
        return embed

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def incomepanel(self, ctx):
        cfg = self.get_income_config(ctx.guild.id)
        embed = self.build_income_panel_embed(ctx.guild, cfg)
        view = IncomePanelView(self, ctx.guild.id, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def role_income_add(self, ctx, role_id: int, amount: float = None, collect_interval: str = None):
        cfg = self.get_income_config(ctx.guild.id)
        if amount is None:
            amount = float(cfg["default_amount"])
        if collect_interval is None:
            collect_interval = f"{int(cfg['default_interval_hours'])}h"
        role = discord.utils.get(ctx.guild.roles, id=role_id)
        if role is None:
            await ctx.send(f"Le rôle avec l'ID {role_id} n'existe pas sur ce serveur.")
            return
        if self.get_role_income(role.id) is not None:
            await ctx.send(f"Le rôle {role_id} a déjà un gain associé.")
            return

        try:
            hours = int(collect_interval.replace("h", ""))
            collect_interval_sec = hours * 3600
        except ValueError:
            await ctx.send("Le temps de collecte doit être un nombre entier suivi de la lettre 'h'. Exemple: 12h")
            return

        self.add_role_income(role.id, role.name, amount, collect_interval_sec)
        await ctx.send(f"Le rôle {role.name} a été ajouté à la liste des rôles avec un gain de : {amount} collectable toutes les {collect_interval} heures.")
        await self.send_income_log(ctx.guild, f"[INCOME] role_income_add role={role.name} amount={amount} interval={collect_interval} par {ctx.author.mention}")

    @commands.command()
    async def role_income_remove(self, ctx, role_id: int):
        if self.get_role_income(role_id) is None:
            await ctx.send(f"Le rôle {role_id} n'a pas de gain associé.")
            return

        self.remove_role_income(role_id)
        await ctx.send(f"Le rôle {role_id} a été supprimé de la liste des rôles avec gains associés.")
        await self.send_income_log(ctx.guild, f"[INCOME] role_income_remove role_id={role_id} par {ctx.author.mention}")

    @commands.command()
    async def role_income_list(self, ctx):
        role_income = self.list_role_income()
        if not role_income:
            await ctx.send("Il n'y a pas de rôle avec un gain associé.")
            return

        role_list = []
        for role_id, role_data in role_income.items():
            role_list.append(f"{role_data['name']} : {role_data['amount']} collectable toutes les {role_data['collect_interval']//3600} heures.")

        await ctx.send("Liste des rôles avec gains associés :\n" + "\n".join(role_list))

    @commands.command()
    async def role_income_edit(self, ctx, role_id: int, amount: float, collect_interval: str):
        if self.get_role_income(role_id) is None:
            await ctx.send(f"Le rôle {role_id} n'a pas de gain associé.")
            return

        try:
            hours = int(collect_interval.replace("h", ""))
            collect_interval_sec = hours * 3600
        except ValueError:
            await ctx.send("Le temps de collecte doit être un nombre entier suivi de la lettre 'h'. Exemple: 12h")
            return

        self.update_role_income(role_id, amount, collect_interval_sec)
        await ctx.send(f"Le gain associé au rôle {role_id} a été modifié : {amount} par collecte toutes les {collect_interval} heures.")
        await self.send_income_log(ctx.guild, f"[INCOME] role_income_edit role_id={role_id} amount={amount} interval={collect_interval} par {ctx.author.mention}")

    @commands.command()
    async def collect_income(self, ctx):
        cfg = self.get_income_config(ctx.guild.id)
        if not cfg["collect_enabled"]:
            await ctx.send("La collecte de revenus passifs est desactivee sur ce serveur.")
            return

        member = ctx.author
        if not self.has_account(member.id):
            await ctx.send(f"{member.mention}, vous n'avez pas de compte. Utilisez la commande `,addmoney` pour en créer un.")
            return

        current_time = time.time()
        collected_any = False

        for role_id_str, role_data in self.list_role_income().items():
            role_id = int(role_id_str)
            role = ctx.guild.get_role(role_id)
            if role is None or role not in member.roles:
                continue

            if current_time - role_data["last_collect"] >= role_data["collect_interval"]:
                self.add_balance(member.id, role_data["amount"])
                self.set_role_income_last_collect(role_id, current_time)
                new_balance = self.get_balance(member.id)
                await ctx.send(f"{member.mention}, vous avez collecté **{role_data['amount']:.2f}** pièces grâce à votre rôle **{role_data['name']}**. Nouveau solde : **{new_balance:.2f}** pièces.")
                collected_any = True
            else:
                time_left = role_data["collect_interval"] - (current_time - role_data["last_collect"])
                hours_left = int(time_left // 3600)
                minutes_left = int((time_left % 3600) // 60)
                await ctx.send(f"{member.mention}, vous devez attendre encore **{hours_left}h {minutes_left}min** avant de collecter votre gain pour le rôle **{role_data['name']}**.")
                collected_any = True

        if not collected_any:
            await ctx.send(f"{member.mention}, vous n'avez aucun rôle avec un gain passif associé.")


def setup(bot, db):
    bot.add_cog(cmdincome(bot, db))
