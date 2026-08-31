"""Intégration Steam (intègre ProjetsDivers/CSGO.py).

Affiche l'inventaire public d'un utilisateur Steam (par vanity URL ou SteamID64)
via l'API Steam Web officielle. La clé API est stockée par serveur dans la table
`steam_config` (commande `,steamconfig`), et n'est plus en dur comme dans le
prototype original (CSGO.py contenait une clé en clair).

Commandes :
  ,steamconfig <cle_api>  — enregistre la clé API Steam (admin)
  ,steaminv <pseudo|id>   — affiche l'inventaire CS:GO d'un utilisateur
  ,steamid <pseudo>       — résout un pseudo en SteamID64
"""

from __future__ import annotations

import asyncio
import re

import aiohttp
import discord
from discord.ext import commands

from cogs.i18n import t

STEAM_APP_CSGO = 730
STEAM_CONTEXT_2 = 2


def _clean_steam_username(name: str) -> str:
    return name.strip().strip("/")


class cmdsteam(commands.Cog):
    """Cog d'intégration Steam."""

    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._session: aiohttp.ClientSession | None = None

    # --- accès données ---

    def get_api_key(self, guild_id: int) -> str | None:
        row = self.db.fetchone("SELECT api_key FROM steam_config WHERE guild_id = ?", (guild_id,))
        if row is None or not row["api_key"]:
            return None
        return row["api_key"]

    def set_api_key(self, guild_id: int, api_key: str) -> None:
        self.db.execute(
            "INSERT INTO steam_config (guild_id, api_key) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET api_key=excluded.api_key",
            (guild_id, api_key),
        )

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def cog_unload(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def resolve_vanity(self, api_key: str, vanity: str) -> str | None:
        """Résout une vanity URL (pseudo) en SteamID64 via ResolveVanityURL."""
        session = await self._http()
        url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
        params = {"key": api_key, "vanityurl": vanity}
        async with session.get(url, params=params, timeout=10) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        body = data.get("response", {})
        if body.get("success") == 1:
            return body.get("steamid")
        return None

    async def fetch_inventory(self, api_key: str, steam_id: str) -> list[dict]:
        """Récupère l'inventaire CS:GO (app 730, contexte 2) via IInventoryService."""
        session = await self._http()
        url = "https://api.steampowered.com/IInventoryService/GetInventory/v1/"
        params = {
            "key": api_key,
            "steamid": steam_id,
            "appid": STEAM_APP_CSGO,
            "contextid": STEAM_CONTEXT_2,
            "count": 5000,
        }
        async with session.get(url, params=params, timeout=15) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
        items = data.get("response", {}).get("items", [])
        return items

    # --- commandes ---

    @commands.command()
    async def steamconfig(self, ctx, api_key: str):
        """Enregistre la clé API Steam pour ce serveur (admin)."""
        self.set_api_key(ctx.guild.id, api_key)
        await ctx.send(t(self.db, "steam_config_saved", ctx.guild.id, ctx.author.id))

    @commands.command()
    async def steaminv(self, ctx, *, username: str):
        """Affiche l'inventaire CS:GO d'un utilisateur Steam."""
        api_key = self.get_api_key(ctx.guild.id)
        if not api_key:
            await ctx.send(t(self.db, "steam_no_key", ctx.guild.id, ctx.author.id))
            return

        username = _clean_steam_username(username)
        steam_id = username if re.fullmatch(r"\d{17}", username) else None
        if steam_id is None:
            await ctx.send(t(self.db, "steam_resolving", ctx.guild.id, ctx.author.id))
            steam_id = await self.resolve_vanity(api_key, username)
            if steam_id is None:
                await ctx.send(t(self.db, "steam_not_found", ctx.guild.id, ctx.author.id, name=username))
                return

        await ctx.send(t(self.db, "steam_fetching", ctx.guild.id, ctx.author.id, steam_id=steam_id))
        items = await asyncio.wait_for(self.fetch_inventory(api_key, steam_id), timeout=20)

        if not items:
            await ctx.send(t(self.db, "steam_empty", ctx.guild.id, ctx.author.id, steam_id=steam_id))
            return

        by_name: dict[str, int] = {}
        for item in items:
            name = item.get("item_description", {}).get("market_hash_name") or item.get("item_id") or "?"
            by_name[name] = by_name.get(name, 0) + 1

        lines = [f"- {name} (x{count})" for name, count in sorted(by_name.items())]
        chunk_size = 15
        embeds = []
        for i in range(0, len(lines), chunk_size):
            embed = discord.Embed(
                title=t(self.db, "steam_inventory_title", ctx.guild.id, ctx.author.id, steam_id=steam_id),
                description="\n".join(lines[i:i + chunk_size]),
                color=discord.Color.blue(),
            )
            embeds.append(embed)
        for embed in embeds:
            await ctx.send(embed=embed)

    @commands.command()
    async def steamid(self, ctx, *, username: str):
        """Résout un pseudo Steam en SteamID64."""
        api_key = self.get_api_key(ctx.guild.id)
        if not api_key:
            await ctx.send(t(self.db, "steam_no_key", ctx.guild.id, ctx.author.id))
            return
        username = _clean_steam_username(username)
        steam_id = await self.resolve_vanity(api_key, username)
        if steam_id is None:
            await ctx.send(t(self.db, "steam_not_found", ctx.guild.id, ctx.author.id, name=username))
            return
        await ctx.send(t(self.db, "steam_id_result", ctx.guild.id, ctx.author.id, name=username, steam_id=steam_id))


def setup(bot, db):
    bot.add_cog(cmdsteam(bot, db))
