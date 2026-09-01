"""Alertes Twitch, sans aucune cle d'API.

L'ancienne version demandait un client_id et un client_secret Twitch par serveur
(console developpeur, OAuth, rafraichissement de jeton). Le cog interroge
desormais le endpoint GraphQL public de twitch.tv, celui qu'utilise le site
lui-meme : aucun compte, aucune cle, rien a configurer cote utilisateur.

`TWITCH_WEB_CLIENT_ID` n'est pas une cle personnelle : c'est l'identifiant du
client web public de Twitch, le meme pour tout le monde et connu publiquement
(streamlink et yt-dlp s'en servent). Il est ici en dur, comme une URL.

Commandes :
  ,twitchconfig channel #salon   — ou annoncer les directs
  ,twitchconfig add <chaine>     — suivre une chaine
  ,twitchconfig remove <chaine>  — arreter de la suivre
  ,twitchconfig list             — chaines suivies
  ,twitchconfig enable|disable   — activer les alertes
  ,twitch status [chaine]        — etat des alertes, ou d'une chaine
"""

import asyncio

import aiohttp
import discord
from discord.ext import commands

TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
TWITCH_WEB_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
CHECK_INTERVAL_SECONDS = 300

_STREAM_QUERY = (
    '{user(login:"%s"){id displayName profileImageURL(width:150) '
    'stream{id title type viewersCount previewImageURL game{name}}}}'
)


def preview_url(stream: dict, width: int = 640, height: int = 360) -> str:
    """URL de l'apercu du direct.

    Twitch renvoie un gabarit contenant {width}/{height} : laisse tel quel,
    Discord refuse l'image.
    """
    raw = (stream or {}).get("previewImageURL") or ""
    return raw.replace("{width}", str(width)).replace("{height}", str(height))


class cmdtwitch(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._twitch_task = None
        self._session = None

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Client-Id": TWITCH_WEB_CLIENT_ID,
                         "Content-Type": "application/json"}
            )
        return self._session

    async def cog_unload(self):
        if self._twitch_task is not None:
            self._twitch_task.cancel()
        if self._session is not None and not self._session.closed:
            await self._session.close()

    # --- configuration ---

    def get_config(self, guild_id: int) -> dict:
        row = self.db.fetchone(
            "SELECT channel_id, enabled FROM twitch_config WHERE guild_id = ?", (guild_id,)
        )
        if row is None:
            return {"channel_id": None, "enabled": False}
        return {"channel_id": row["channel_id"], "enabled": bool(row["enabled"])}

    def set_config(self, guild_id: int, **fields):
        self.db.execute(
            "INSERT OR IGNORE INTO twitch_config (guild_id) VALUES (?)", (guild_id,)
        )
        allowed = {"channel_id", "enabled"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(
            f"UPDATE twitch_config SET {sets} WHERE guild_id = ?",
            list(fields.values()) + [guild_id],
        )

    def list_watched(self, guild_id: int) -> list:
        return [
            row["user_login"] for row in self.db.fetchall(
                "SELECT user_login FROM twitch_watch WHERE guild_id = ? ORDER BY user_login",
                (guild_id,),
            )
        ]

    def watch(self, guild_id: int, user_login: str, added_by: int = None):
        self.db.execute(
            "INSERT OR IGNORE INTO twitch_watch (guild_id, user_login, added_by) "
            "VALUES (?, ?, ?)",
            (guild_id, user_login.lower(), added_by),
        )

    def unwatch(self, guild_id: int, user_login: str) -> bool:
        cur = self.db.execute(
            "DELETE FROM twitch_watch WHERE guild_id = ? AND user_login = ?",
            (guild_id, user_login.lower()),
        )
        return bool(cur.rowcount)

    def already_announced(self, guild_id: int, stream_id: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM twitch_notifications WHERE guild_id = ? AND stream_id = ? LIMIT 1",
            (guild_id, stream_id),
        ) is not None

    def mark_announced(self, guild_id: int, user_login: str, stream_id: str,
                       title: str, url: str):
        self.db.execute(
            "INSERT INTO twitch_notifications (guild_id, user_id, user_login, "
            "stream_title, stream_url, stream_id) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, 0, user_login, title, url, stream_id),
        )

    # --- acces Twitch, sans cle ---

    async def fetch_channel(self, user_login: str):
        """Etat d'une chaine. None si elle n'existe pas, `stream` None si hors ligne."""
        session = await self._http()
        payload = {"query": _STREAM_QUERY % user_login.lower()}
        try:
            async with session.post(TWITCH_GQL_URL, json=payload, timeout=15) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, ValueError, asyncio.TimeoutError):
            return None
        if not isinstance(data, dict):
            return None
        return (data.get("data") or {}).get("user")

    async def is_live(self, user_login: str):
        """Renvoie le direct en cours, ou None."""
        user = await self.fetch_channel(user_login)
        if not user:
            return None
        stream = user.get("stream")
        if not stream or stream.get("type") != "live":
            return None
        return {"user": user, "stream": stream}

    def build_embed(self, user_login: str, live: dict) -> discord.Embed:
        user, stream = live["user"], live["stream"]
        name = user.get("displayName") or user_login
        url = f"https://www.twitch.tv/{user_login.lower()}"
        embed = discord.Embed(
            title=stream.get("title") or "En direct",
            url=url,
            description=f"🔴 **{name}** est en direct !",
            color=discord.Color.purple(),
        )
        game = (stream.get("game") or {}).get("name")
        if game:
            embed.add_field(name="Jeu", value=game, inline=True)
        if stream.get("viewersCount") is not None:
            embed.add_field(name="Spectateurs", value=str(stream["viewersCount"]), inline=True)
        if user.get("profileImageURL"):
            embed.set_thumbnail(url=user["profileImageURL"])
        preview = preview_url(stream)
        if preview:
            embed.set_image(url=preview)
        embed.set_footer(text="Twitch")
        return embed

    # --- boucle d'annonce ---

    async def check_streams(self):
        guilds = self.db.fetchall(
            "SELECT guild_id, channel_id FROM twitch_config WHERE enabled = 1 "
            "AND channel_id IS NOT NULL"
        )
        for row in guilds:
            guild_id, channel_id = row["guild_id"], row["channel_id"]
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                continue
            for user_login in self.list_watched(guild_id):
                live = await self.is_live(user_login)
                if live is None:
                    continue
                stream_id = str(live["stream"].get("id") or "")
                if not stream_id or self.already_announced(guild_id, stream_id):
                    continue
                url = f"https://www.twitch.tv/{user_login}"
                try:
                    await channel.send(embed=self.build_embed(user_login, live))
                except (discord.Forbidden, discord.HTTPException):
                    continue
                self.mark_announced(
                    guild_id, user_login, stream_id,
                    live["stream"].get("title") or "", url,
                )

    async def _twitch_check_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self.check_streams()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[DEBUG] Erreur boucle Twitch: {exc}")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    def setup_twitch_task(self):
        if self._twitch_task is None or self._twitch_task.done():
            self._twitch_task = asyncio.create_task(self._twitch_check_loop())

    @commands.Cog.listener()
    async def on_ready(self):
        self.setup_twitch_task()

    # --- commandes ---

    @commands.command()
    async def twitchconfig(self, ctx, action: str = None, *, value: str = None):
        cfg = self.get_config(ctx.guild.id)
        if action is None:
            channel = ctx.guild.get_channel(cfg["channel_id"]) if cfg["channel_id"] else None
            watched = self.list_watched(ctx.guild.id)
            embed = discord.Embed(title="Alertes Twitch", color=discord.Color.purple())
            embed.add_field(name="Etat",
                            value="Activees" if cfg["enabled"] else "Desactivees", inline=True)
            embed.add_field(name="Salon",
                            value=channel.mention if channel else "Non defini", inline=True)
            embed.add_field(name="Chaines suivies",
                            value=", ".join(watched) if watched else "Aucune", inline=False)
            embed.set_footer(text="Aucune cle d'API n'est necessaire.")
            await ctx.send(embed=embed)
            return

        action = action.lower()
        if action == "channel":
            channel = None
            if ctx.message.channel_mentions:
                channel = ctx.message.channel_mentions[0]
            elif value and value.strip().isdigit():
                channel = ctx.guild.get_channel(int(value.strip()))
            if channel is None:
                await ctx.send("Usage : `,twitchconfig channel #salon`")
                return
            self.set_config(ctx.guild.id, channel_id=channel.id)
            await ctx.send(f"✅ Les directs seront annonces dans {channel.mention}.")

        elif action == "add":
            if not value:
                await ctx.send("Usage : `,twitchconfig add <chaine>`")
                return
            login = value.strip().lower().rsplit("/", 1)[-1]
            user = await self.fetch_channel(login)
            if user is None:
                await ctx.send(f"❌ La chaine `{login}` est introuvable sur Twitch.")
                return
            self.watch(ctx.guild.id, login, ctx.author.id)
            await ctx.send(f"✅ **{user.get('displayName') or login}** est maintenant suivie.")

        elif action == "remove":
            if not value:
                await ctx.send("Usage : `,twitchconfig remove <chaine>`")
                return
            if self.unwatch(ctx.guild.id, value.strip()):
                await ctx.send(f"✅ `{value.strip()}` n'est plus suivie.")
            else:
                await ctx.send("❌ Cette chaine n'etait pas suivie.")

        elif action == "list":
            watched = self.list_watched(ctx.guild.id)
            await ctx.send("Chaines suivies : " + (", ".join(watched) if watched else "aucune"))

        elif action in ("enable", "disable"):
            self.set_config(ctx.guild.id, enabled=1 if action == "enable" else 0)
            await ctx.send("✅ Alertes Twitch " + ("activees." if action == "enable"
                                                   else "desactivees."))
        else:
            await ctx.send(
                "Actions : `channel #salon`, `add <chaine>`, `remove <chaine>`, "
                "`list`, `enable`, `disable`."
            )

    @commands.command()
    async def twitch(self, ctx, action: str = None, *, value: str = None):
        """,twitch status [chaine] — etat des alertes, ou d'une chaine."""
        if action is None or action.lower() != "status":
            await ctx.send("Usage : `,twitch status [chaine]`")
            return
        if value:
            login = value.strip().lower().rsplit("/", 1)[-1]
            live = await self.is_live(login)
            if live is None:
                await ctx.send(f"⚫ `{login}` n'est pas en direct.")
            else:
                await ctx.send(embed=self.build_embed(login, live))
            return
        cfg = self.get_config(ctx.guild.id)
        watched = self.list_watched(ctx.guild.id)
        await ctx.send(
            f"Alertes Twitch : {'activees' if cfg['enabled'] else 'desactivees'} · "
            f"{len(watched)} chaine(s) suivie(s)."
        )


def setup(bot, db):
    bot.add_cog(cmdtwitch(bot, db))
