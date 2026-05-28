import asyncio
import json
import os
import discord
from discord.ext import commands


class cmdlogs(commands.Cog):
    """Gestion simple des canaux de logs par serveur.

    Commandes:
    - setlog [#channel] : active les logs dans le canal (ou canal courant si absent)
    - unsetlog [#channel] : désactive les logs dans le canal (ou canal courant si absent)
    - listlogs : liste les canaux configurés pour les logs
    """

    def __init__(self, bot):
        self.bot = bot
        self.config_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'logs_config.json')
        self.lock = asyncio.Lock()

    def _load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_config(self, cfg):
        with open(self.config_path, 'w') as f:
            json.dump(cfg, f, indent=2)

    async def _ensure_guild(self, guild_id):
        async with self.lock:
            cfg = self._load_config()
            if str(guild_id) not in cfg:
                cfg[str(guild_id)] = []
                self._save_config(cfg)
            return cfg

    @commands.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def setlog(self, ctx, channel: discord.TextChannel = None):
        """Active les logs dans le canal spécifié (ou canal courant)."""
        channel = channel or ctx.channel
        cfg = self._load_config()
        guild_cfg = cfg.get(str(ctx.guild.id), [])
        if channel.id in guild_cfg:
            await ctx.send(f"Les logs sont déjà activés dans {channel.mention}.")
            return
        guild_cfg.append(channel.id)
        cfg[str(ctx.guild.id)] = guild_cfg
        self._save_config(cfg)
        await ctx.send(f"Logs activés dans {channel.mention}.")

    @commands.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def unsetlog(self, ctx, channel: discord.TextChannel = None):
        """Désactive les logs dans le canal spécifié (ou canal courant)."""
        channel = channel or ctx.channel
        cfg = self._load_config()
        guild_cfg = cfg.get(str(ctx.guild.id), [])
        if channel.id not in guild_cfg:
            await ctx.send(f"Les logs ne sont pas activés dans {channel.mention}.")
            return
        guild_cfg = [cid for cid in guild_cfg if cid != channel.id]
        cfg[str(ctx.guild.id)] = guild_cfg
        self._save_config(cfg)
        await ctx.send(f"Logs désactivés dans {channel.mention}.")

    @commands.command()
    async def listlogs(self, ctx):
        """Liste les canaux configurés pour les logs sur ce serveur."""
        cfg = self._load_config()
        guild_cfg = cfg.get(str(ctx.guild.id), [])
        if not guild_cfg:
            await ctx.send("Aucun canal de logs configuré pour ce serveur.")
            return
        mentions = []
        for cid in guild_cfg:
            channel = ctx.guild.get_channel(cid) if ctx.guild else None
            if channel:
                mentions.append(channel.mention)
            else:
                mentions.append(f"<#{cid}>")
        await ctx.send("Canaux de logs configurés: " + ", ".join(mentions))


def setup(bot):
    bot.add_cog(cmdlogs(bot))
