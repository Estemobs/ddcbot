import json
import re

import discord
from discord.ext import commands


class cmdcustom(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    # --- Configuration ---

    def set_custom_command(self, guild_id: int, command_name: str, response: str):
        self.db.execute(
            "INSERT INTO custom_commands (guild_id, command_name, response) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, command_name) DO UPDATE SET "
            "response=excluded.response",
            (guild_id, command_name.lower(), response),
        )

    def get_custom_command(self, guild_id: int, command_name: str):
        row = self.db.fetchone(
            "SELECT response FROM custom_commands WHERE guild_id = ? AND command_name = ?",
            (guild_id, command_name.lower()),
        )
        return row["response"] if row else None

    def list_custom_commands(self, guild_id: int) -> list:
        rows = self.db.fetchall(
            "SELECT command_name, response FROM custom_commands WHERE guild_id = ?",
            (guild_id,),
        )
        return [{"name": row["command_name"], "response": row["response"]} for row in rows]

    def delete_custom_command(self, guild_id: int, command_name: str):
        self.db.execute(
            "DELETE FROM custom_commands WHERE guild_id = ? AND command_name = ?",
            (guild_id, command_name.lower()),
        )

    # --- Command processing ---

    async def process_custom_commands(self, message: discord.Message) -> bool:
        """Process custom commands in messages. Returns True if a custom command was matched."""
        if message.author.bot:
            return False
        if not message.guild:
            return False

        guild_id = message.guild.id
        cmd_name = message.content.strip().lower()

        # Check if the message is just the command (optionally with prefix)
        # Custom commands are triggered by ,commandname
        if not cmd_name.startswith(","):
            return False

        cmd_name = cmd_name[1:]  # Remove the comma
        response = self.get_custom_command(guild_id, cmd_name)
        if response is None:
            return False

        # Send the response
        # Check if the response contains placeholders
        if "{user}" in response:
            response = response.replace("{user}", message.author.mention)
        if "{server}" in response:
            response = response.replace("{server}", message.guild.name)
        if "{count}" in response:
            member_count = message.guild.member_count
            response = response.replace("{count}", str(member_count))

        # Send as embed or message
        if response.startswith("{") and response.endswith("}"):
            # Try to parse as JSON embed
            try:
                embed_data = json.loads(response)
                embed = discord.Embed.from_dict(embed_data)
                await message.channel.send(embed=embed)
                return True
            except (json.JSONDecodeError, Exception):
                pass

        await message.channel.send(response)
        return True

    # --- Commandes ---

    @commands.command()
    async def cmdadd(self, ctx, *, command_and_response: str = None):
        """Ajouter une commande personnalisée.
        Usage: ,cmdadd nom_commande = réponse
        ou: ,cmdadd nom_commande -> réponse
        """
        if command_and_response is None:
            return await ctx.send(
                "Usage: `,cmdadd nom_commande = réponse`\n"
                "Ou: `,cmdadd nom_commande -> réponse`"
            )

        # Parse the command and response
        if "=" in command_and_response:
            parts = command_and_response.split("=", 1)
            cmd_name = parts[0].strip()
            response = parts[1].strip()
        elif "->" in command_and_response:
            parts = command_and_response.split("->", 1)
            cmd_name = parts[0].strip()
            response = parts[1].strip()
        else:
            return await ctx.send(
                "Format invalide. Utilisez `=` ou `->` pour séparer la commande de la réponse."
            )

        if not cmd_name:
            return await ctx.send("Le nom de la commande ne peut pas être vide.")

        self.set_custom_command(ctx.guild.id, cmd_name, response)
        await ctx.send(
            f"✅ Commande personnalisée **`{cmd_name}`** enregistrée !"
        )

    @commands.command()
    async def cmdlist(self, ctx):
        """Lister toutes les commandes personnalisées."""
        commands_list = self.list_custom_commands(ctx.guild.id)
        if not commands_list:
            return await ctx.send("Aucune commande personnalisée configurée pour ce serveur.")

        # Build the response
        lines = []
        for cmd in commands_list:
            # Truncate long responses for display
            resp = cmd["response"]
            if len(resp) > 100:
                resp = resp[:97] + "..."
            lines.append(f"**{cmd['name']}** : {resp}")

        await ctx.send(
            "Commandes personnalisées :\n" + "\n".join(lines[:10])
            + (f"\n...\nTotal: {len(commands_list)} commandes" if len(commands_list) > 10 else "")
        )

    @commands.command()
    async def cmdrm(self, ctx, *, command_name: str = None):
        """Supprimer une commande personnalisée."""
        if command_name is None:
            return await ctx.send("Usage: `,cmdrm nom_commande`")

        self.delete_custom_command(ctx.guild.id, command_name)
        await ctx.send(
            f"✅ Commande **`{command_name}`** supprimée !"
        )

    @commands.command()
    async def cmdedit(self, ctx, cmd_name: str = None, *, new_response: str = None):
        """Modifier une commande personnalisée."""
        if cmd_name is None:
            return await ctx.send("Usage: `,cmdedit nom_commande -> nouvelle_réponse`")
        if new_response is None:
            return await ctx.send("Usage: `,cmdedit nom_commande -> nouvelle_réponse`")

        self.set_custom_command(ctx.guild.id, cmd_name, new_response)
        await ctx.send(
            f"✅ Commande **`{cmd_name}`** modifiée !"
        )

    # --- Message processing ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ne PAS appeler bot.process_commands ici : un listener de Cog s'ajoute
        # au on_message par defaut de commands.Bot, il ne le remplace pas. Le
        # dispatch a donc deja lieu, et un second appel executait chaque
        # commande du bot une deuxieme fois (double debit, doublons de logs,
        # et 404 sur les commandes qui suppriment leur propre salon).
        await self.process_custom_commands(message)


def setup(bot, db):
    cog = cmdcustom(bot, db)
    bot.add_cog(cog)