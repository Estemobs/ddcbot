"""Systeme d'urgence / lockdown.

Permet de verrouiller rapidement tous les salons du serveur
(mode nuit / urgence) ou de selectionner les salons a verrouiller.
"""

import json

import discord
from discord.ext import commands


DEFAULT_LOCKDOWN_CONFIG = {
    "lockdown_role_id": None,
    "log_channel_id": None,
    "auto_lockon_mass_join": False,
    "mass_join_threshold": 10,
    "mass_join_window_seconds": 60,
}


class cmdlockdown(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._cfg_initialized = set()
        self._join_tracker = {}

    def get_config(self, guild_id: int) -> dict:
        if guild_id not in self._cfg_initialized:
            self._cfg_initialized.add(guild_id)
            self.db.execute(
                "INSERT OR IGNORE INTO lockdown_config "
                "(guild_id, lockdown_role_id, log_channel_id, auto_lockon_mass_join, mass_join_threshold, mass_join_window_seconds) "
                "VALUES (?, NULL, NULL, 0, 10, 60)", (guild_id,),
            )
        row = self.db.fetchone(
            "SELECT lockdown_role_id, log_channel_id, auto_lockon_mass_join, "
            "mass_join_threshold, mass_join_window_seconds "
            "FROM lockdown_config WHERE guild_id = ?", (guild_id,),
        )
        return {
            "lockdown_role_id": row["lockdown_role_id"],
            "log_channel_id": row["log_channel_id"],
            "auto_lockon_mass_join": bool(row["auto_lockon_mass_join"]),
            "mass_join_threshold": row["mass_join_threshold"],
            "mass_join_window_seconds": row["mass_join_window_seconds"],
        }

    def save_config(self, guild_id: int, **fields):
        self.get_config(guild_id)
        assignments, values = [], []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(int(value) if isinstance(value, bool) else value)
        values.append(guild_id)
        self.db.execute(f"UPDATE lockdown_config SET {', '.join(assignments)} WHERE guild_id = ?", values)

    async def _set_channel_lock(self, channel, locked: bool, reason: str):
        overwrites = channel.overwrites_for(channel.guild.default_role)
        overwrites.send_messages = not locked
        try:
            await channel.set_permissions(
                channel.guild.default_role,
                overwrite=overwrites,
                reason=reason,
            )
            return True
        except (discord.errors.Forbidden, discord.errors.HTTPException):
            return False

    async def _log_lockdown(self, guild, action: str, user: discord.Member = None, channel_count: int = 0):
        cfg = self.get_config(guild.id)
        if not cfg["log_channel_id"]:
            return
        log_channel = self.bot.get_channel(cfg["log_channel_id"])
        if not log_channel:
            return
        embed = discord.Embed(
            title=f"🔒 Lockdown: {action}",
            description=f"Execute par {user.mention if user else 'Systeme'}" if user else f"Action: {action}",
            color=discord.Color.red() if "Lock" in action else discord.Color.green(),
        )
        embed.add_field(name="Salons affectes", value=str(channel_count))
        try:
            await log_channel.send(embed=embed)
        except discord.errors.Forbidden:
            pass

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def lockdown(self, ctx, *, reason: str = "Urgence"):
        """Verrouille TOUS les salons textuels du serveur."""
        await ctx.send("🔒 Verrouillage en cours...")
        count = 0
        for channel in ctx.guild.text_channels:
            if await self._set_channel_lock(channel, True, f"Lockdown par {ctx.author}: {reason}"):
                count += 1
        await self._log_lockdown(ctx.guild, "Lockdown", ctx.author, count)
        await ctx.send(f"🔒 **{count}** salons verrouilles.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def unlockdown(self, ctx, *, reason: str = "Fin de l'urgence"):
        """Deverrouille TOUS les salons textuels du serveur."""
        await ctx.send("🔓 Deverrouillage en cours...")
        count = 0
        for channel in ctx.guild.text_channels:
            if await self._set_channel_lock(channel, False, f"Unlock par {ctx.author}: {reason}"):
                count += 1
        await self._log_lockdown(ctx.guild, "Unlockdown", ctx.author, count)
        await ctx.send(f"🔓 **{count}** salons deverrouilles.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def lockdownchannel(self, ctx, channel: discord.TextChannel = None, *, reason: str = "Urgence"):
        """Verrouille un salon specifique."""
        if channel is None:
            channel = ctx.channel
        await self._set_channel_lock(channel, True, f"Lockdown par {ctx.author}: {reason}")
        await self._log_lockdown(ctx.guild, f"Lock channel {channel.name}", ctx.author, 1)
        await ctx.send(f"🔒 Salon {channel.mention} verrouille.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def unlockdownchannel(self, ctx, channel: discord.TextChannel = None, *, reason: str = "Fin de l'urgence"):
        """Deverrouille un salon specifique."""
        if channel is None:
            channel = ctx.channel
        await self._set_channel_lock(channel, False, f"Unlock par {ctx.author}: {reason}")
        await self._log_lockdown(ctx.guild, f"Unlock channel {channel.name}", ctx.author, 1)
        await ctx.send(f"🔓 Salon {channel.mention} deverrouille.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def lockdownconfig(self, ctx):
        """Affiche la configuration du systeme de lockdown."""
        cfg = self.get_config(ctx.guild.id)
        embed = discord.Embed(title="Configuration Lockdown", color=discord.Color.orange())
        role = f"<@&{cfg['lockdown_role_id']}>" if cfg["lockdown_role_id"] else "—"
        embed.add_field(name="Role lockdown", value=role, inline=True)
        log_ch = f"<#{cfg['log_channel_id']}>" if cfg["log_channel_id"] else "—"
        embed.add_field(name="Canal logs", value=log_ch, inline=True)
        embed.add_field(name="Auto-lock mass-join", value="✅" if cfg["auto_lockon_mass_join"] else "❌", inline=True)
        embed.add_field(name="Seuil mass-join", value=str(cfg["mass_join_threshold"]), inline=True)
        embed.add_field(name="Fenetre (s)", value=str(cfg["mass_join_window_seconds"]), inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def lockdownrole(self, ctx, role: discord.Role = None):
        """Definit le role a assigner en mode lockdown."""
        if role is None:
            self.save_config(ctx.guild.id, lockdown_role_id=None)
            await ctx.send("Role lockdown retire.")
        else:
            self.save_config(ctx.guild.id, lockdown_role_id=role.id)
            await ctx.send(f"✅ Role lockdown defini sur {role.mention}.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def lockdownlog(self, ctx, channel: discord.TextChannel = None):
        """Definit le canal de logs du lockdown."""
        if channel is None:
            self.save_config(ctx.guild.id, log_channel_id=None)
            await ctx.send("Logs lockdown desactives.")
        else:
            self.save_config(ctx.guild.id, log_channel_id=channel.id)
            await ctx.send(f"✅ Canal de logs lockdown defini sur {channel.mention}.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def lockdownmassjoin(self, ctx, threshold: int = None, window: int = None):
        """Configure le lockdown automatique sur mass-join."""
        if threshold is not None:
            self.save_config(ctx.guild.id, mass_join_threshold=threshold)
        if window is not None:
            self.save_config(ctx.guild.id, mass_join_window_seconds=window)
        cfg = self.get_config(ctx.guild.id)
        await ctx.send(
            f"✅ Mass-join: {cfg['mass_join_threshold']} joins en {cfg['mass_join_window_seconds']}s"
        )

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def lockdownauto(self, ctx, state: str = None):
        """Active/desactive le lockdown automatique sur mass-join."""
        if state is None or state.lower() not in ("on", "off"):
            await ctx.send("Usage: `,lockdownauto on|off`")
            return
        self.save_config(ctx.guild.id, auto_lockon_mass_join=(state.lower() == "on"))
        await ctx.send(f"✅ Auto-lock mass-join {'active' if state.lower() == 'on' else 'desactive'}.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self.get_config(member.guild.id)
        if not cfg["auto_lockon_mass_join"]:
            return
        now = __import__("time").time()
        guild_id = member.guild.id
        if guild_id not in self._join_tracker:
            self._join_tracker[guild_id] = []
        self._join_tracker[guild_id].append(now)
        window = cfg["mass_join_window_seconds"]
        self._join_tracker[guild_id] = [
            t for t in self._join_tracker[guild_id] if now - t < window
        ]
        if len(self._join_tracker[guild_id]) >= cfg["mass_join_threshold"]:
            self._join_tracker[guild_id] = []
            for channel in member.guild.text_channels:
                overwrites = channel.overwrites_for(member.guild.default_role)
                overwrites.send_messages = False
                try:
                    await channel.set_permissions(
                        member.guild.default_role,
                        overwrite=overwrites,
                        reason=f"Lockdown auto: mass-join detecte ({cfg['mass_join_threshold']} joins en {window}s)",
                    )
                except (discord.errors.Forbidden, discord.errors.HTTPException):
                    pass
            log_channel = self.bot.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None
            if log_channel:
                embed = discord.Embed(
                    title="🔒 Lockdown auto-active",
                    description=f"Mass-join detecte : {cfg['mass_join_threshold']} joins en {window}s.\nTous les salons ont ete verrouilles.",
                    color=discord.Color.red(),
                )
                try:
                    await log_channel.send(embed=embed)
                except discord.errors.Forbidden:
                    pass


def setup(bot, db):
    bot.add_cog(cmdlockdown(bot, db))
