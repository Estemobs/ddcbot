"""Alertes sociales : YouTube, Reddit, podcasts/RSS et Kick.

Aucune cle d'API. Chaque source expose un acces public : flux Atom officiel pour
YouTube et Reddit, RSS pour les podcasts, endpoint public pour Kick. L'analyse
des flux vit dans social_feeds ; ce cog fait les requetes, l'annonce Discord et
le suivi de ce qui a deja ete publie.

Commandes :
  ,alerts                                   — sources suivies
  ,alerts add <type> <cible> [#salon]       — suivre une source
  ,alerts remove <id>                       — arreter de la suivre
  ,alerts test <id>                         — annonce le dernier element
  ,alerts mention <id> <@role|everyone|->   — mention a l'annonce
"""

import asyncio
import time

import aiohttp
import discord
from discord.ext import commands

import social_feeds
from social_feeds import KINDS, feed_url, parse_feed, parse_kick, new_items

CHECK_INTERVAL_SECONDS = 900  # Reddit limite fortement : 15 min est un bon compromis
MAX_FAILURES = 20             # au-dela, la source est desactivee automatiquement

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr,en;q=0.8",
    # Sans ce cookie, youtube.com sert sa page de consentement au lieu de la
    # page de la chaine, et la resolution d'un @pseudo echoue silencieusement.
    # Il n'identifie personne : il signale juste que la banniere est traitee.
    "Cookie": "SOCS=CAI",
}

KIND_STYLE = {
    "youtube": ("📺", discord.Color.red, "YouTube"),
    "reddit": ("👽", discord.Color.orange, "Reddit"),
    "rss": ("📰", discord.Color.blurple, "RSS"),
    "kick": ("🟢", discord.Color.green, "Kick"),
}


class cmdsocialalerts(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._task = None
        self._session = None

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=BROWSER_HEADERS)
        return self._session

    async def cog_unload(self):
        if self._task is not None:
            self._task.cancel()
        if self._session is not None and not self._session.closed:
            await self._session.close()

    # --- donnees ---

    def list_feeds(self, guild_id: int = None, only_enabled: bool = False) -> list:
        sql = "SELECT * FROM social_feeds"
        clauses, params = [], []
        if guild_id is not None:
            clauses.append("guild_id = ?")
            params.append(guild_id)
        if only_enabled:
            clauses.append("enabled = 1")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id"
        return [dict(r) for r in self.db.fetchall(sql, params)]

    def get_feed(self, feed_id: int, guild_id: int = None):
        sql = "SELECT * FROM social_feeds WHERE id = ?"
        params = [feed_id]
        if guild_id is not None:
            sql += " AND guild_id = ?"
            params.append(guild_id)
        row = self.db.fetchone(sql, params)
        return dict(row) if row else None

    def add_feed(self, guild_id: int, kind: str, target: str, channel_id: int,
                 label: str = "", mention: str = "") -> int:
        cur = self.db.execute(
            "INSERT INTO social_feeds (guild_id, kind, target, label, channel_id, mention) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, kind, target) DO UPDATE SET "
            "channel_id=excluded.channel_id, label=excluded.label, enabled=1",
            (guild_id, kind, target, label, channel_id, mention),
        )
        return cur.lastrowid

    def remove_feed(self, feed_id: int, guild_id: int) -> bool:
        cur = self.db.execute(
            "DELETE FROM social_feeds WHERE id = ? AND guild_id = ?", (feed_id, guild_id)
        )
        return bool(cur.rowcount)

    def update_feed(self, feed_id: int, **fields):
        allowed = {"last_uid", "last_check", "failures", "enabled", "mention",
                   "channel_id", "label"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(
            f"UPDATE social_feeds SET {sets} WHERE id = ?", list(fields.values()) + [feed_id]
        )

    # --- recuperation ---

    async def fetch_items(self, feed: dict) -> list:
        """Elements de la source, du plus recent au plus ancien. [] si echec."""
        session = await self._http()
        url = feed_url(feed["kind"], feed["target"])
        try:
            async with session.get(url, timeout=20) as resp:
                if resp.status != 200:
                    return []
                if feed["kind"] == "kick":
                    payload = await resp.json(content_type=None)
                    item = parse_kick(payload)
                    return [item] if item else []
                body = await resp.text()
        except (aiohttp.ClientError, ValueError, asyncio.TimeoutError, UnicodeDecodeError):
            return []
        return parse_feed(body)

    async def resolve_youtube(self, target: str):
        """Identifiant de chaine YouTube depuis un ID, une URL ou un @pseudo."""
        direct = social_feeds.extract_youtube_channel_id(target)
        if direct:
            return direct
        handle = target.strip().rstrip("/").rsplit("/", 1)[-1]
        if not handle.startswith("@"):
            handle = "@" + handle
        session = await self._http()
        try:
            async with session.get(f"https://www.youtube.com/{handle}", timeout=20) as resp:
                if resp.status != 200:
                    return None
                body = await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError):
            return None
        return social_feeds.extract_youtube_channel_id(body)

    # --- annonce ---

    def build_embed(self, feed: dict, item) -> discord.Embed:
        emoji, color, source = KIND_STYLE.get(feed["kind"], ("🔔", discord.Color.blurple, "Flux"))
        title = item.title or "Nouvelle publication"
        embed = discord.Embed(title=title[:256], url=item.url or None, color=color())
        name = feed["label"] or item.author or feed["target"]
        embed.description = f"{emoji} **{name}** — {source}"
        if item.thumbnail:
            embed.set_image(url=item.thumbnail)
        if item.published:
            embed.set_footer(text=item.published)
        return embed

    async def announce(self, feed: dict, item) -> bool:
        channel = self.bot.get_channel(feed["channel_id"])
        if channel is None:
            return False
        content = feed["mention"] or None
        try:
            await channel.send(content=content, embed=self.build_embed(feed, item))
        except (discord.Forbidden, discord.HTTPException):
            return False
        return True

    async def poll_feed(self, feed: dict) -> int:
        """Verifie une source et annonce les nouveautes. Renvoie le nombre d'annonces."""
        items = await self.fetch_items(feed)
        now = time.time()
        if not items:
            failures = feed["failures"] + 1
            # Une source durablement injoignable (chaine supprimee, flux mort)
            # est mise en veille plutot que reessayee indefiniment.
            self.update_feed(
                feed["id"], failures=failures, last_check=now,
                enabled=0 if failures >= MAX_FAILURES else feed["enabled"],
            )
            return 0

        latest = items[0]
        # Premier passage : on pose le repere sans rien annoncer.
        if feed["last_uid"] is None:
            self.update_feed(feed["id"], last_uid=latest.uid, last_check=now, failures=0)
            return 0

        fresh = new_items(items, feed["last_uid"])
        sent = 0
        for item in fresh:
            if await self.announce(feed, item):
                sent += 1
        self.update_feed(feed["id"], last_uid=latest.uid, last_check=now, failures=0)
        return sent

    async def _loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                for feed in self.list_feeds(only_enabled=True):
                    await self.poll_feed(feed)
                    await asyncio.sleep(2)  # etale les requetes, Reddit limite vite
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[DEBUG] Erreur boucle alertes sociales: {exc}")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    # --- commandes ---

    @commands.command(aliases=["alertes"])
    async def alerts(self, ctx, action: str = None, kind: str = None, *, rest: str = None):
        """,alerts add <youtube|reddit|rss|kick> <cible> [#salon]"""
        if action is None or action.lower() == "list":
            feeds = self.list_feeds(ctx.guild.id)
            if not feeds:
                await ctx.send(
                    "Aucune alerte configurée. Types : " + ", ".join(f"`{k}`" for k in KINDS)
                    + "\nExemple : `,alerts add youtube @MrBeast #annonces`"
                )
                return
            lines = []
            for feed in feeds:
                channel = ctx.guild.get_channel(feed["channel_id"])
                state = "" if feed["enabled"] else " · ⏸ en veille"
                lines.append(
                    f"`#{feed['id']}` **{feed['kind']}** · {feed['label'] or feed['target']} "
                    f"→ {channel.mention if channel else feed['channel_id']}{state}"
                )
            await ctx.send(embed=discord.Embed(
                title="🔔 Alertes sociales",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            ))
            return

        action = action.lower()

        if action == "add":
            if not kind or kind.lower() not in KINDS or not rest:
                await ctx.send(
                    "Usage : `,alerts add <type> <cible> [#salon]`\n"
                    "Types : " + ", ".join(f"`{k}`" for k in KINDS)
                )
                return
            kind = kind.lower()
            channel = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else ctx.channel
            target = rest
            for mention in ctx.message.channel_mentions:
                target = target.replace(f"<#{mention.id}>", "")
            target = target.strip()
            if not target:
                await ctx.send("❌ Précisez la cible à suivre.")
                return

            label = target
            if kind == "youtube":
                resolved = await self.resolve_youtube(target)
                if resolved is None:
                    await ctx.send(
                        "❌ Chaîne YouTube introuvable. Donnez son identifiant `UC...`, "
                        "son `@pseudo` ou l'URL de la chaîne."
                    )
                    return
                target = resolved
            elif kind == "reddit":
                target = target.lstrip("/").removeprefix("r/")
                label = f"r/{target}"
            elif kind == "kick":
                target = target.lower().rstrip("/").rsplit("/", 1)[-1]

            feed_id = self.add_feed(ctx.guild.id, kind, target, channel.id, label)
            feed = self.get_feed(feed_id) or self.db.fetchone(
                "SELECT * FROM social_feeds WHERE guild_id = ? AND kind = ? AND target = ?",
                (ctx.guild.id, kind, target),
            )
            items = await self.fetch_items(dict(feed))
            if not items:
                await ctx.send(
                    f"⚠️ Source ajoutée (`#{feed['id']}`) mais rien n'a pu être lu pour le "
                    f"moment. Elle sera réessayée automatiquement."
                )
                return
            self.update_feed(feed["id"], last_uid=items[0].uid, last_check=time.time())
            await ctx.send(
                f"✅ `#{feed['id']}` **{label}** suivie dans {channel.mention}. "
                f"Dernier élément repéré : *{items[0].title[:80]}*"
            )

        elif action == "remove":
            if not kind or not kind.isdigit():
                await ctx.send("Usage : `,alerts remove <id>`")
                return
            if self.remove_feed(int(kind), ctx.guild.id):
                await ctx.send("✅ Alerte supprimée.")
            else:
                await ctx.send("❌ Cette alerte n'existe pas.")

        elif action == "test":
            if not kind or not kind.isdigit():
                await ctx.send("Usage : `,alerts test <id>`")
                return
            feed = self.get_feed(int(kind), ctx.guild.id)
            if feed is None:
                await ctx.send("❌ Cette alerte n'existe pas.")
                return
            items = await self.fetch_items(feed)
            if not items:
                await ctx.send("❌ Rien n'a pu être lu depuis cette source.")
                return
            await ctx.send(embed=self.build_embed(feed, items[0]))

        elif action == "mention":
            if not kind or not kind.isdigit() or not rest:
                await ctx.send("Usage : `,alerts mention <id> <@role|everyone|->`")
                return
            feed = self.get_feed(int(kind), ctx.guild.id)
            if feed is None:
                await ctx.send("❌ Cette alerte n'existe pas.")
                return
            value = rest.strip()
            if value == "-":
                mention = ""
            elif value.lower() == "everyone":
                mention = "@everyone"
            elif ctx.message.role_mentions:
                mention = ctx.message.role_mentions[0].mention
            else:
                await ctx.send("Usage : `,alerts mention <id> <@role|everyone|->`")
                return
            self.update_feed(feed["id"], mention=mention)
            await ctx.send("✅ Mention enregistrée." if mention else "✅ Mention retirée.")

        else:
            await ctx.send("Actions : `list`, `add`, `remove`, `test`, `mention`.")


def setup(bot, db):
    bot.add_cog(cmdsocialalerts(bot, db))
