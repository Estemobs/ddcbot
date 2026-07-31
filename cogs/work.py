import discord
import json
import time
import random
from discord.ext import commands


class cmdwork(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    # --- balances (table partagée avec economie.py/income.py/jeu.py) ---

    def get_balance(self, user_id: int) -> float:
        row = self.db.fetchone("SELECT amount FROM balances WHERE user_id = ?", (user_id,))
        return row["amount"] if row else 0.0

    def add_balance(self, user_id: int, delta: float):
        self.db.execute(
            "INSERT INTO balances (user_id, amount) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET amount = amount + excluded.amount",
            (user_id, delta),
        )

    # --- configuration du travail par serveur ---

    def get_work_settings(self, guild_id: int):
        row = self.db.fetchone(
            "SELECT min_amount, max_amount, reward_tiers, cooldown, rewards_json "
            "FROM work_settings WHERE guild_id = ?",
            (guild_id,),
        )
        if row is None:
            return None
        return {
            "min_amount": row["min_amount"],
            "max_amount": row["max_amount"],
            "reward_tiers": row["reward_tiers"],
            "cooldown": row["cooldown"],
            "rewards": json.loads(row["rewards_json"]),
        }

    def set_work_settings(self, guild_id: int, min_amount, max_amount, reward_tiers, cooldown, rewards):
        self.db.execute(
            "INSERT INTO work_settings (guild_id, min_amount, max_amount, reward_tiers, cooldown, rewards_json) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET min_amount=excluded.min_amount, max_amount=excluded.max_amount, "
            "reward_tiers=excluded.reward_tiers, cooldown=excluded.cooldown, rewards_json=excluded.rewards_json",
            (guild_id, min_amount, max_amount, reward_tiers, cooldown, json.dumps(list(rewards))),
        )

    # --- etat par utilisateur (par serveur) ---

    def get_work_state(self, guild_id: int, user_id: int):
        row = self.db.fetchone(
            "SELECT work_count, last_worked FROM work_state WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        if row is None:
            return None
        return {"work_count": row["work_count"], "last_worked": row["last_worked"]}

    def record_work(self, guild_id: int, user_id: int, timestamp: float):
        self.db.execute(
            "INSERT INTO work_state (guild_id, user_id, work_count, last_worked) VALUES (?, ?, 1, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET work_count = work_count + 1, last_worked = excluded.last_worked",
            (guild_id, user_id, timestamp),
        )

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def config_work(self, ctx, min_amount: int, max_amount: int, reward_tiers: int, cooldown: int, *rewards: int):
        if len(rewards) != reward_tiers:
            await ctx.send(f"Le nombre de récompenses doit être égal au nombre de paliers de récompenses ({reward_tiers})")
            return

        if min_amount >= max_amount:
            await ctx.send("Le montant minimum doit être inférieur au montant maximum")
            return

        cooldown_sec = cooldown * 3600
        self.set_work_settings(ctx.guild.id, min_amount, max_amount, reward_tiers, cooldown_sec, rewards)

        await ctx.send(f"Commande configurée avec succès : montant minimum = {min_amount}, montant maximum = {max_amount}, nombre de paliers de récompenses = {reward_tiers}, cooldown = {cooldown} heures, récompenses = {rewards}")

    @commands.command()
    async def show_work_config(self, ctx):
        settings = self.get_work_settings(ctx.guild.id)
        if settings is None:
            await ctx.send("La commande config_work doit être exécutée avant d'utiliser la commande show_work_config")
            return

        embed = discord.Embed(title="Configuration de la commande work", color=0x00ff00)
        embed.add_field(name="Montant minimum", value=settings['min_amount'], inline=False)
        embed.add_field(name="Montant maximum", value=settings['max_amount'], inline=False)
        embed.add_field(name="Nombre de paliers de récompenses", value=settings['reward_tiers'], inline=False)
        embed.add_field(name="Cooldown (en heures)", value=settings['cooldown'] // 3600, inline=False)
        embed.add_field(name="Récompenses bonus", value=', '.join(map(str, settings['rewards'])), inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def work(self, ctx):
        settings = self.get_work_settings(ctx.guild.id)
        if settings is None:
            await ctx.send("La commande config_work doit être exécutée avant d'utiliser la commande work")
            return

        user_id = ctx.author.id
        guild_id = ctx.guild.id
        state = self.get_work_state(guild_id, user_id)
        if state is not None:
            time_since_last_worked = time.time() - state["last_worked"]
            if time_since_last_worked < settings["cooldown"]:
                remaining_cooldown = round((settings["cooldown"] - time_since_last_worked) / 3600)
                await ctx.send(f"Vous devez attendre encore {remaining_cooldown} heures avant de pouvoir travailler à nouveau.")
                return

        amount = random.randint(settings["min_amount"], settings["max_amount"])

        bonus_reward = 0
        if state is not None:
            tier_size = settings["reward_tiers"]
            tier = min(state["work_count"] // tier_size, len(settings["rewards"]) - 1)
            bonus_reward = settings["rewards"][tier]

        self.add_balance(user_id, amount + bonus_reward)
        self.record_work(guild_id, user_id, time.time())
        self.db.log_transaction(guild_id, user_id, amount + bonus_reward, "work", f"bonus={bonus_reward}")
        new_balance = self.get_balance(user_id)

        await ctx.send(f"Vous avez travaillé et gagné {amount}$! Vous avez également reçu une récompense bonus de {bonus_reward}. Votre solde actuel est de {new_balance}.")


def setup(bot, db):
    bot.add_cog(cmdwork(bot, db))
