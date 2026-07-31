import re

import discord
from discord.ext import commands

from cogs.i18n import t

MESSAGE_LINK_RE = re.compile(r"channels/(\d+)/(\d+)/(\d+)")


def parse_message_link(link: str):
    match = MESSAGE_LINK_RE.search(link)
    if not match:
        return None
    return int(match.group(2)), int(match.group(3))


class cmdreactroles(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    def add_binding(self, guild_id, channel_id, message_id, emoji, role_id):
        self.db.execute(
            "INSERT INTO reaction_roles (guild_id, channel_id, message_id, emoji, role_id) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, message_id, emoji) DO UPDATE SET role_id = excluded.role_id, channel_id = excluded.channel_id",
            (guild_id, channel_id, message_id, emoji, role_id),
        )

    def remove_binding(self, guild_id, message_id, emoji) -> bool:
        cursor = self.db.execute(
            "DELETE FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
            (guild_id, message_id, emoji),
        )
        return cursor.rowcount > 0

    def get_binding(self, guild_id, message_id, emoji):
        row = self.db.fetchone(
            "SELECT role_id, channel_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
            (guild_id, message_id, emoji),
        )
        return dict(row) if row else None

    def list_bindings(self, guild_id):
        return self.db.fetchall(
            "SELECT channel_id, message_id, emoji, role_id FROM reaction_roles WHERE guild_id = ? ORDER BY message_id",
            (guild_id,),
        )

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def reactrole(self, ctx, message_link: str, emoji: str, role: discord.Role):
        """Lie une réaction à un rôle sur un message. Lien du message + emoji + rôle."""
        parsed = parse_message_link(message_link)
        if parsed is None:
            await ctx.send(t(self.db, "reactrole_invalid_message", ctx.guild.id, ctx.author.id))
            return
        channel_id, message_id = parsed
        channel = ctx.guild.get_channel(channel_id)
        if channel is None:
            await ctx.send(t(self.db, "reactrole_invalid_message", ctx.guild.id, ctx.author.id))
            return
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send(t(self.db, "reactrole_invalid_message", ctx.guild.id, ctx.author.id))
            return
        await message.add_reaction(emoji)
        self.add_binding(ctx.guild.id, channel_id, message_id, emoji, role.id)
        await ctx.send(
            t(
                self.db,
                "reactrole_added",
                ctx.guild.id,
                ctx.author.id,
                emoji=emoji,
                role=role.mention,
                link=f"[message]({message.jump_url})",
            )
        )

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def reactrolerm(self, ctx, message_link: str, emoji: str):
        """Retire une liaison réaction-rôle sur un message."""
        parsed = parse_message_link(message_link)
        if parsed is None:
            await ctx.send(t(self.db, "reactrole_invalid_message", ctx.guild.id, ctx.author.id))
            return
        _, message_id = parsed
        if self.remove_binding(ctx.guild.id, message_id, emoji):
            await ctx.send(t(self.db, "reactrole_removed", ctx.guild.id, ctx.author.id))
        else:
            await ctx.send(t(self.db, "reactrole_not_found", ctx.guild.id, ctx.author.id))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def reactroles(self, ctx):
        """Liste les reaction roles du serveur."""
        bindings = self.list_bindings(ctx.guild.id)
        if not bindings:
            await ctx.send(t(self.db, "reactrole_list_empty", ctx.guild.id, ctx.author.id))
            return
        embed = discord.Embed(
            title=t(self.db, "reactrole_list_title", ctx.guild.id, ctx.author.id),
            color=discord.Color.dark_purple(),
        )
        seen_messages = {}
        for binding in bindings:
            role = ctx.guild.get_role(binding["role_id"])
            role_label = role.mention if role else f"<@&{binding['role_id']}>"
            seen_messages.setdefault(binding["message_id"], []).append(f"{binding['emoji']} → {role_label}")
        for message_id, lines in seen_messages.items():
            embed.add_field(name=f"Message {message_id}", value="\n".join(lines), inline=False)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        emoji_str = str(payload.emoji)
        binding = self.get_binding(payload.guild_id, payload.message_id, emoji_str)
        if binding is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        if member is None:
            return
        role = guild.get_role(binding["role_id"])
        if role is not None and role not in member.roles:
            try:
                await member.add_roles(role)
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        emoji_str = str(payload.emoji)
        binding = self.get_binding(payload.guild_id, payload.message_id, emoji_str)
        if binding is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        if member is None:
            return
        role = guild.get_role(binding["role_id"])
        if role is not None and role in member.roles:
            try:
                await member.remove_roles(role)
            except (discord.Forbidden, discord.HTTPException):
                pass


def setup(bot, db):
    bot.add_cog(cmdreactroles(bot, db))
