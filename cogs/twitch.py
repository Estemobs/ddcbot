import asyncio
import json
import re
import time

import aiohttp
import discord
from datetime import datetime
from discord.ext import commands

from http_utils import get_json


class cmdtwitch(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._twitch_task = None
        self._api_task = None
        self.streams = {}

    def _ensure_twitch_tables(self):
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS twitch_config ("
            "guild_id INTEGER PRIMARY KEY,"
            "channel_id INTEGER,"
            "client_id TEXT,"
            "client_secret TEXT,"
            "access_token TEXT,"
            "refresh_token TEXT,"
            "expires_at REAL DEFAULT 0,"
            "enabled INTEGER DEFAULT 1)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS twitch_notifications ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "guild_id INTEGER,"
            "user_id INTEGER,"
            "user_login TEXT,"
            "stream_title TEXT,"
            "stream_url TEXT,"
            "occurred_at REAL DEFAULT (unixepoch()))"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_twitch_guild ON twitch_config(guild_id)"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_twitch_notif_guild ON twitch_notifications(guild_id, user_id)"
        )

    # --- Configuration ---

    def set_twitch_config(
        self, guild_id: int, channel_id: int = None,
        client_id: str = None, client_secret: str = None,
        access_token: str = None, refresh_token: str = None,
        expires_at: float = None, enabled: int = 1,
    ):
        self.db.execute(
            "INSERT INTO twitch_config (guild_id, channel_id, client_id, client_secret, "
            "access_token, refresh_token, expires_at, enabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET "
            "channel_id=excluded.channel_id, client_id=excluded.client_id, "
            "client_secret=excluded.client_secret, access_token=excluded.access_token, "
            "refresh_token=excluded.refresh_token, expires_at=excluded.expires_at, "
            "enabled=excluded.enabled",
            (guild_id, channel_id, client_id, client_secret, access_token, refresh_token,
             expires_at or 0, enabled),
        )

    def get_twitch_config(self, guild_id: int):
        row = self.db.fetchone("SELECT * FROM twitch_config WHERE guild_id = ?", (guild_id,))
        if row:
            return dict(row)
        return None

    def set_twitch_enabled(self, guild_id: int, enabled: int):
        self.set_twitch_config(guild_id, enabled=enabled)

    def is_twitch_enabled(self, guild_id: int) -> bool:
        cfg = self.get_twitch_config(guild_id)
        return cfg is not None and cfg.get("enabled", 0) == 1

    # --- OAuth helper ---

    async def _refresh_twitch_token(self, cfg: dict) -> dict:
        """Refresh the Twitch OAuth token."""
        if not cfg.get("refresh_token"):
            return cfg

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://id.twitch.tv/oauth2/token",
                params={
                    "client_id": cfg.get("client_id"),
                    "client_secret": cfg.get("client_secret"),
                    "grant_type": "refresh_token",
                    "refresh_token": cfg.get("refresh_token"),
                },
            ) as resp:
                if resp.status != 200:
                    return cfg
                data = await resp.json()
        cfg["access_token"] = data.get("access_token", cfg.get("access_token"))
        cfg["refresh_token"] = data.get("refresh_token", cfg.get("refresh_token"))
        cfg["expires_at"] = time.time() + data.get("expires_in", 0)
        return cfg

    async def _get_auth_headers(self, cfg: dict) -> dict:
        """Get auth headers for Twitch API."""
        if time.time() > cfg.get("expires_at", 0) - 300:
            cfg = await self._refresh_twitch_token(cfg)
        return {"Client-Id": cfg.get("client_id"), "Authorization": f"Bearer {cfg.get('access_token')}"}

    # --- Stream checking ---

    async def _get_user_login(self, cfg: dict, user_login: str) -> dict:
        """Get Twitch user info by login name."""
        headers = await self._get_auth_headers(cfg)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.twitch.tv/helix/users?login={user_login}",
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                users = data.get("data", [])
                return users[0] if users else None

    async def _get_live_streams(self, user_login: str, cfg: dict) -> list:
        """Check if a user is live on Twitch."""
        user_info = await self._get_user_login(cfg, user_login)
        if not user_info:
            return []

        user_login_lower = user_info["login"].lower()
        user_id = user_info["id"]

        headers = await self._get_auth_headers(cfg)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.twitch.tv/helix/streams?user_login={user_login_lower}",
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("data", [])

    # --- Notification system ---

    async def check_twitch_streams(self):
        """Check for live streams and send notifications."""
        cfg = self.get_twitch_config(None)
        if not cfg:
            return

        if not self.is_twitch_enabled(None):
            return

        rows = self.db.fetchall(
            "SELECT user_id, user_login FROM twitch_notifications WHERE guild_id = ?",
            (cfg["guild_id"],),
        )

        for row in rows:
            user_login = row["user_login"]
            is_live = await self._get_live_streams(user_login, cfg)
            if is_live:
                stream = is_live[0]
                stream_title = stream.get("title", "En direct")
                stream_url = stream.get("url", "")
                stream_game = stream.get("game_name", "")

                self.db.execute(
                    "INSERT INTO twitch_notifications (guild_id, user_id, user_login, stream_title, stream_url) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (cfg["guild_id"], row["user_id"], user_login, stream_title, stream_url),
                )

                try:
                    user = await self.bot.fetch_user(int(row["user_id"]))
                    message = (
                        f"🔴 **{user_login}** est en direct !\n",
                        f"**{stream_title}**\n",
                        f"{stream_game + " - " if stream_game else ""}"\n",
                    )
                        f"📺 [Regarder sur Twitch]({stream_url})"
                    )
                    await user.send(message)
                except (discord.NotFound, discord.HTTPException):
                    continue

    async def _twitch_check_loop(self):
        """Background task to check Twitch streams."""
        await self.bot.wait_until_ready()
        while True:
            try:
                await self.check_twitch_streams()
            except Exception as e:
                print(f"Erreur Twitch check: {e}")
            await asyncio.sleep(300)

    # --- Commandes ---

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def twitchconfig(self, ctx, action: str = None, *args):
        if action is None:
            cfg = self.get_twitch_config(ctx.guild.id)
            if cfg is None:
                return await ctx.send("Twitch non configure.")
            is_enabled = cfg.get("enabled", 0) == 1
            await ctx.send(f"Twitch : {'Activé' if is_enabled else 'Désactivé'}")
            return

        action = action.lower()
        if action == "setup":
            if len(args) < 2:
                return await ctx.send("Usage: ,twitchconfig setup <client_id> <client_secret>")
            client_id, client_secret = args[0], args[1]
            self.set_twitch_config(ctx.guild.id, client_id=client_id, client_secret=client_secret)
            await ctx.send("Configuration Twitch initialisee !")

        if action == "adduser":
            if len(args) < 1:
                return await ctx.send("Usage: ,twitchconfig adduser <pseudo_twitch>")
            user_login = args[0]
            self.db.execute(
                "INSERT OR IGNORE INTO twitch_notifications (guild_id, user_id, user_login) VALUES (?, ?, ?)",
                (ctx.guild.id, ctx.author.id, user_login),
            )
            await ctx.send(f"Vous serez notifie quand {user_login} sera en direct !")

        if action == "removeuser":
            if len(args) < 1:
                return await ctx.send("Usage: ,twitchconfig removeuser <pseudo_twitch>")
            user_login = args[0]
            self.db.execute(
                "DELETE FROM twitch_notifications WHERE guild_id = ? AND user_login = ?",
                (ctx.guild.id, user_login),
            )
            await ctx.send(f"Plus de notifications pour {user_login}")

        if action == "enable":
            self.set_twitch_config(ctx.guild.id, enabled=1)
            await ctx.send("Alertes Twitch activées.")

        if action == "disable":
            self.set_twitch_config(ctx.guild.id, enabled=0)
            await ctx.send("Alertes Twitch desactivees.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def twitch(self, ctx, action: str = None, *args):
        if action is None:
            await ctx.send("Utilisez ,twitchconfig pour configurer.")
            return
        action = action.lower()
        if action == "status":
            cfg = self.get_twitch_config(ctx.guild.id)
            if cfg is None:
                return await ctx.send("Twitch non configure.")
            is_enabled = cfg.get("enabled", 0) == 1
            await ctx.send(f"Twitch : {'Activé' if is_enabled else 'Désactivé'}")

    def setup_twitch_task(self):
        if self._twitch_task is None or self._twitch_task.done():
            self._twitch_task = asyncio.create_task(self._twitch_check_loop())


def setup(bot, db):
    cog = cmdtwitch(bot, db)
    cog._ensure_twitch_tables()
    bot.add_cog(cog)
