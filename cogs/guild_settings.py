import discord
from discord.ext import commands

from cogs.i18n import t


class cmdguildsettings(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    def get_settings(self, guild_id: int) -> dict:
        self.db.execute(
            "INSERT OR IGNORE INTO guild_settings "
            "(guild_id, welcome_enabled, welcome_channel_id, welcome_message, leave_enabled, leave_channel_id, leave_message) "
            "VALUES (?, 0, NULL, NULL, 0, NULL, NULL)",
            (guild_id,),
        )
        row = self.db.fetchone(
            "SELECT welcome_enabled, welcome_channel_id, welcome_message, "
            "leave_enabled, leave_channel_id, leave_message FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        return {
            "welcome_enabled": bool(row["welcome_enabled"]),
            "welcome_channel_id": row["welcome_channel_id"],
            "welcome_message": row["welcome_message"],
            "leave_enabled": bool(row["leave_enabled"]),
            "leave_channel_id": row["leave_channel_id"],
            "leave_message": row["leave_message"],
        }

    def save_settings(self, guild_id: int, **fields):
        self.get_settings(guild_id)
        assignments = []
        values = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(int(value) if isinstance(value, bool) else value)
        values.append(guild_id)
        self.db.execute(f"UPDATE guild_settings SET {', '.join(assignments)} WHERE guild_id = ?", values)

    def _render(self, template: str, member: discord.Member) -> str:
        try:
            guild = member.guild
        except AttributeError:
            guild = None
        server_name = guild.name if guild else "?"
        count = guild.member_count if guild else 0
        return (
            template.replace("{user}", member.mention)
            .replace("{server}", server_name)
            .replace("{count}", str(count))
        )

    # --- commandes ---

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setwelcome(self, ctx, channel: discord.TextChannel = None, *, message: str = None):
        """Configure le message de bienvenue : ,setwelcome #salon Texte {user} | ,setwelcome off"""
        if channel is None and (message is None or message.strip().lower() == "off"):
            self.save_settings(ctx.guild.id, welcome_enabled=False)
            await ctx.send(t(self.db, "welcome_disabled", ctx.guild.id, ctx.author.id))
            return
        if channel is None or not message:
            await ctx.send("Syntaxe : `,setwelcome #salon Votre message {user}` ou `,setwelcome off`")
            return
        self.save_settings(ctx.guild.id, welcome_enabled=True, welcome_channel_id=channel.id, welcome_message=message)
        await ctx.send(t(self.db, "welcome_set", ctx.guild.id, ctx.author.id) + f"\n{t(self.db, 'welcome_placeholders', ctx.guild.id, ctx.author.id)}")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setleave(self, ctx, channel: discord.TextChannel = None, *, message: str = None):
        """Configure le message de départ : ,setleave #salon Texte {user} | ,setleave off"""
        if channel is None and (message is None or message.strip().lower() == "off"):
            self.save_settings(ctx.guild.id, leave_enabled=False)
            await ctx.send(t(self.db, "leave_disabled", ctx.guild.id, ctx.author.id))
            return
        if channel is None or not message:
            await ctx.send("Syntaxe : `,setleave #salon Votre message {user}` ou `,setleave off`")
            return
        self.save_settings(ctx.guild.id, leave_enabled=True, leave_channel_id=channel.id, leave_message=message)
        await ctx.send(t(self.db, "leave_set", ctx.guild.id, ctx.author.id) + f"\n{t(self.db, 'welcome_placeholders', ctx.guild.id, ctx.author.id)}")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def welcomeconfig(self, ctx):
        """Affiche la configuration des messages de bienvenue/départ."""
        settings = self.get_settings(ctx.guild.id)
        embed = discord.Embed(
            title=t(self.db, "welcome_config_title", ctx.guild.id, ctx.author.id),
            color=discord.Color.blurple(),
        )
        for key, label_key in (("welcome", "welcome_config_welcome"), ("leave", "welcome_config_leave")):
            enabled = settings[f"{key}_enabled"]
            channel_id = settings[f"{key}_channel_id"]
            message = settings[f"{key}_message"] or "—"
            channel_label = f"<#{channel_id}>" if channel_id else t(self.db, "xp_config_none", ctx.guild.id, ctx.author.id)
            embed.add_field(
                name=f"{t(self.db, label_key, ctx.guild.id, ctx.author.id)} : {'✅' if enabled else '❌'}",
                value=f"{t(self.db, 'welcome_config_channel', ctx.guild.id, ctx.author.id)} : {channel_label}\n"
                      f"{t(self.db, 'welcome_config_message', ctx.guild.id, ctx.author.id)} : {message}",
                inline=False,
            )
        await ctx.send(embed=embed)

    # --- écouteurs ---

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot or member.guild is None:
            return
        settings = self.get_settings(member.guild.id)
        if not settings["welcome_enabled"] or not settings["welcome_channel_id"] or not settings["welcome_message"]:
            return
        channel = member.guild.get_channel(settings["welcome_channel_id"])
        if channel:
            try:
                await channel.send(self._render(settings["welcome_message"], member))
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if member.bot or member.guild is None:
            return
        settings = self.get_settings(member.guild.id)
        if not settings["leave_enabled"] or not settings["leave_channel_id"] or not settings["leave_message"]:
            return
        channel = member.guild.get_channel(settings["leave_channel_id"])
        if channel:
            try:
                await channel.send(self._render(settings["leave_message"], member))
            except (discord.Forbidden, discord.HTTPException):
                pass


def setup(bot, db):
    bot.add_cog(cmdguildsettings(bot, db))
