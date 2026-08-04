"""Notifications webhook.

Envoie des notifications automatiques vers des webhooks Discord
pour les evenements du bot (joins, bans, warns, etc.).
"""

import json

import aiohttp
import discord
from discord.ext import commands

DEFAULT_WEBHOOK_EVENTS = {
    "member_join": True,
    "member_leave": True,
    "member_ban": True,
    "member_unban": True,
    "member_warn": True,
    "member_kick": True,
    "message_delete": False,
    "message_edit": False,
    "channel_create": False,
    "channel_delete": False,
    "role_create": False,
    "role_delete": False,
}


class cmdwebhooks(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._cfg_initialized = set()

    def get_config(self, guild_id: int) -> dict:
        if guild_id not in self._cfg_initialized:
            self._cfg_initialized.add(guild_id)
            self.db.execute(
                "INSERT OR IGNORE INTO webhook_config (guild_id, webhook_url, enabled, events_json) "
                "VALUES (?, NULL, 0, ?)", (guild_id, json.dumps(DEFAULT_WEBHOOK_EVENTS)),
            )
        row = self.db.fetchone(
            "SELECT webhook_url, enabled, events_json FROM webhook_config WHERE guild_id = ?",
            (guild_id,),
        )
        events = DEFAULT_WEBHOOK_EVENTS.copy()
        if row["events_json"]:
            try:
                events.update(json.loads(row["events_json"]))
            except json.JSONDecodeError:
                pass
        return {"webhook_url": row["webhook_url"], "enabled": bool(row["enabled"]), "events": events}

    def save_config(self, guild_id: int, **fields):
        self.get_config(guild_id)
        assignments, values = [], []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            if isinstance(value, dict):
                values.append(json.dumps(value))
            else:
                values.append(int(value) if isinstance(value, bool) else value)
        values.append(guild_id)
        self.db.execute(f"UPDATE webhook_config SET {', '.join(assignments)} WHERE guild_id = ?", values)

    async def send_webhook(self, guild_id: int, embed: discord.Embed):
        cfg = self.get_config(guild_id)
        if not cfg["enabled"] or not cfg["webhook_url"]:
            return
        try:
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(cfg["webhook_url"], session=session)
                await webhook.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self.get_config(member.guild.id)
        if cfg["events"].get("member_join"):
            embed = discord.Embed(
                title="Membre rejoint",
                description=f"{member.mention} ({member}) a rejoint le serveur.",
                color=discord.Color.green(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="Membres", value=str(member.guild.member_count))
            await self.send_webhook(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = self.get_config(member.guild.id)
        if cfg["events"].get("member_leave"):
            embed = discord.Embed(
                title="Membre parti",
                description=f"**{member}** a quitte le serveur.",
                color=discord.Color.red(),
            )
            await self.send_webhook(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        cfg = self.get_config(guild.id)
        if cfg["events"].get("member_ban"):
            embed = discord.Embed(
                title="Membre banni",
                description=f"**{user}** a ete banni du serveur.",
                color=discord.Color.dark_red(),
            )
            await self.send_webhook(guild.id, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        cfg = self.get_config(guild.id)
        if cfg["events"].get("member_unban"):
            embed = discord.Embed(
                title="Membre debanni",
                description=f"**{user}** a ete debanni du serveur.",
                color=discord.Color.green(),
            )
            await self.send_webhook(guild.id, embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def webhookset(self, ctx, url: str = None):
        """Definit l'URL du webhook pour les notifications."""
        if url is None:
            await ctx.send("Usage: `,webhookset <URL webhook>`")
            return
        self.save_config(ctx.guild.id, webhook_url=url)
        await ctx.send("✅ Webhook configure.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def webhooktoggle(self, ctx, state: str = None):
        """Active/desactive les webhooks (on/off)."""
        if state is None or state.lower() not in ("on", "off"):
            await ctx.send("Usage: `,webhooktoggle on|off`")
            return
        self.save_config(ctx.guild.id, enabled=(state.lower() == "on"))
        await ctx.send(f"✅ Webhooks {'actives' if state.lower() == 'on' else 'desactives'}.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def webhookevent(self, ctx, event: str = None, state: str = None):
        """Active/desactive un evenement webhook (on/off)."""
        if event is None or event not in DEFAULT_WEBHOOK_EVENTS:
            await ctx.send(f"Evenements disponibles: {', '.join(DEFAULT_WEBHOOK_EVENTS.keys())}")
            return
        if state is None or state.lower() not in ("on", "off"):
            await ctx.send("Usage: `,webhookevent <event> on|off`")
            return
        cfg = self.get_config(ctx.guild.id)
        events = cfg["events"]
        events[event] = (state.lower() == "on")
        self.save_config(ctx.guild.id, events_json=events)
        await ctx.send(f"✅ Evenement `{event}` {'active' if state.lower() == 'on' else 'desactive'}.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def webhookconfig(self, ctx):
        """Affiche la configuration des webhooks."""
        cfg = self.get_config(ctx.guild.id)
        embed = discord.Embed(title="Configuration Webhooks", color=discord.Color.blue())
        embed.add_field(name="Active", value="✅" if cfg["enabled"] else "❌", inline=True)
        url_display = "Configure" if cfg["webhook_url"] else "Non configure"
        embed.add_field(name="URL", value=url_display, inline=True)
        events_text = "\n".join(
            f"{'✅' if v else '❌'} {k}" for k, v in cfg["events"].items()
        )
        embed.add_field(name="Evenements", value=events_text, inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def webhooksend(self, ctx, *, message: str = None):
        """Envoie un test au webhook."""
        if message is None:
            message = "Test webhook DDCBot"
        cfg = self.get_config(ctx.guild.id)
        if not cfg["webhook_url"]:
            await ctx.send("❌ Aucun webhook configure.")
            return
        embed = discord.Embed(title="Test Webhook", description=message, color=discord.Color.blue())
        await self.send_webhook(ctx.guild.id, embed)
        await ctx.send("✅ Message envoye au webhook.")


def setup(bot, db):
    bot.add_cog(cmdwebhooks(bot, db))
