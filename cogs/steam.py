"""Integration Steam, sans aucune cle d'API.

Steam expose deux points d'acces publics qui suffisent, et qui ne demandent
ni cle ni compte developpeur :

- ``https://steamcommunity.com/id/<pseudo>?xml=1`` renvoie le profil en XML,
  dont le SteamID64 ;
- ``https://steamcommunity.com/inventory/<steamid>/<appid>/<contextid>``
  renvoie l'inventaire en JSON, tant que le profil est public.

L'ancienne version passait par api.steampowered.com, qui exige une cle Steam Web
stockee par serveur. La colonne `steam_config.api_key` reste en base pour ne
rien casser, mais plus rien ne la lit.

Commandes :
  ,steaminv <pseudo|id>   — affiche l'inventaire CS2/CS:GO d'un utilisateur
  ,steamid <pseudo>       — resout un pseudo en SteamID64
  ,steamconfig            — rappelle qu'aucune configuration n'est necessaire
"""

from __future__ import annotations

import re

import aiohttp
import discord
from discord.ext import commands

from cogs.i18n import t

STEAM_APP_CSGO = 730
STEAM_CONTEXT_2 = 2
STEAM_ID_RE = re.compile(r"\d{17}")
# Le profil XML expose le SteamID64 sans authentification.
STEAM_ID64_RE = re.compile(r"<steamID64>(\d{17})</steamID64>")

# steamcommunity refuse les requetes sans navigateur identifiable.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr,en;q=0.8",
}


def _clean_steam_username(name: str) -> str:
    """Accepte un pseudo, une URL de profil complete ou un SteamID64."""
    name = name.strip().strip("/")
    for prefix in ("https://steamcommunity.com/id/", "https://steamcommunity.com/profiles/",
                   "steamcommunity.com/id/", "steamcommunity.com/profiles/"):
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
            break
    return name.strip("/")


class cmdsteam(commands.Cog):
    """Cog d'integration Steam (sans cle d'API)."""

    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._session: aiohttp.ClientSession | None = None

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=BROWSER_HEADERS)
        return self._session

    async def cog_unload(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()

    # --- acces Steam, endpoints publics ---

    async def resolve_vanity(self, vanity: str) -> str | None:
        """Resout un pseudo en SteamID64 via le profil XML public."""
        if STEAM_ID_RE.fullmatch(vanity):
            return vanity
        session = await self._http()
        url = f"https://steamcommunity.com/id/{vanity}"
        try:
            async with session.get(url, params={"xml": 1}, timeout=10) as resp:
                if resp.status != 200:
                    return None
                body = await resp.text()
        except aiohttp.ClientError:
            return None
        match = STEAM_ID64_RE.search(body)
        return match.group(1) if match else None

    async def fetch_inventory(self, steam_id: str, appid: int = STEAM_APP_CSGO,
                              contextid: int = STEAM_CONTEXT_2) -> list[dict]:
        """Inventaire public d'un joueur. Liste vide si le profil est prive."""
        session = await self._http()
        url = f"https://steamcommunity.com/inventory/{steam_id}/{appid}/{contextid}"
        try:
            async with session.get(url, params={"l": "french", "count": 500},
                                   timeout=15) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, ValueError):
            return []
        if not isinstance(data, dict):
            return []

        # `assets` porte les quantites, `descriptions` les noms lisibles ; la
        # jointure se fait sur (classid, instanceid).
        descriptions = {
            (d.get("classid"), d.get("instanceid")): d
            for d in data.get("descriptions") or []
        }
        items = []
        for asset in data.get("assets") or []:
            description = descriptions.get((asset.get("classid"), asset.get("instanceid")), {})
            items.append({
                "name": description.get("market_hash_name") or description.get("name") or "?",
                "amount": int(asset.get("amount") or 1),
            })
        return items

    # --- commandes ---

    @commands.command()
    async def steamconfig(self, ctx):
        """Steam ne demande plus aucune configuration."""
        await ctx.send(t(self.db, "steam_no_config_needed", ctx.guild.id, ctx.author.id))

    @commands.command()
    async def steaminv(self, ctx, *, username: str):
        """Affiche l'inventaire CS2/CS:GO d'un utilisateur Steam."""
        username = _clean_steam_username(username)

        await ctx.send(t(self.db, "steam_resolving", ctx.guild.id, ctx.author.id))
        steam_id = await self.resolve_vanity(username)
        if steam_id is None:
            await ctx.send(t(self.db, "steam_not_found", ctx.guild.id, ctx.author.id, name=username))
            return

        await ctx.send(t(self.db, "steam_fetching", ctx.guild.id, ctx.author.id, steam_id=steam_id))
        items = await self.fetch_inventory(steam_id)

        if not items:
            await ctx.send(t(self.db, "steam_empty", ctx.guild.id, ctx.author.id, steam_id=steam_id))
            return

        by_name: dict[str, int] = {}
        for item in items:
            by_name[item["name"]] = by_name.get(item["name"], 0) + item["amount"]

        lines = [f"- {name} (x{count})" for name, count in sorted(by_name.items())]
        chunk_size = 15
        for i in range(0, len(lines), chunk_size):
            await ctx.send(embed=discord.Embed(
                title=t(self.db, "steam_inventory_title", ctx.guild.id, ctx.author.id,
                        steam_id=steam_id),
                description="\n".join(lines[i:i + chunk_size]),
                color=discord.Color.blue(),
            ))

    @commands.command()
    async def steamid(self, ctx, *, username: str):
        """Resout un pseudo Steam en SteamID64."""
        username = _clean_steam_username(username)
        steam_id = await self.resolve_vanity(username)
        if steam_id is None:
            await ctx.send(t(self.db, "steam_not_found", ctx.guild.id, ctx.author.id, name=username))
            return
        await ctx.send(t(self.db, "steam_id_result", ctx.guild.id, ctx.author.id,
                         name=username, steam_id=steam_id))


def setup(bot, db):
    bot.add_cog(cmdsteam(bot, db))
