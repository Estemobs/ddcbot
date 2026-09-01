"""Analyse des sources d'alertes sociales, sans cle d'API ni dependance externe.

Quatre sources, toutes accessibles publiquement :

- ``youtube``  flux Atom officiel ``/feeds/videos.xml?channel_id=UC...``
- ``reddit``   flux Atom ``/r/<sub>/new.rss`` (le ``.json`` de Reddit renvoie 403
               depuis un hebergeur, contrairement au flux RSS)
- ``rss``      n'importe quel flux RSS 2.0 ou Atom, ce qui couvre les podcasts
- ``kick``     ``kick.com/api/v2/channels/<slug>``, public et sans jeton

Le parsing vit ici, sans discord.py ni reseau : il se teste sur des flux figes.
Les appels HTTP et l'affichage restent dans le cog.
"""

import re
import xml.etree.ElementTree as ET

ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS = "http://www.youtube.com/xml/schemas/2015"
MEDIA_NS = "http://search.yahoo.com/mrss/"

KINDS = ("youtube", "reddit", "rss", "kick")

# Un identifiant de chaine YouTube commence toujours par UC et fait 24 caracteres.
YT_CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")

# Sur une page de chaine, plusieurs endroits contiennent un identifiant, mais un
# seul designe la chaine affichee. "channelId" apparait aussi dans les videos
# recommandees, et arrive souvent AVANT dans le document : s'y fier renvoie une
# chaine tierce. On lit donc en priorite le lien du flux RSS, puis externalId.
YT_CHANNEL_ID_PATTERNS = (
    re.compile(r"channel_id=(UC[\w-]{22})"),          # <link rel="alternate"> du flux
    re.compile(r'"externalId":"(UC[\w-]{22})"'),      # metadonnees de la chaine
    re.compile(r'"browseId":"(UC[\w-]{22})"'),
    re.compile(r"youtube\.com/channel/(UC[\w-]{22})"),
)


class FeedItem:
    """Element publie, normalise quelle que soit la source."""

    __slots__ = ("uid", "title", "url", "author", "published", "thumbnail")

    def __init__(self, uid, title="", url="", author="", published="", thumbnail=""):
        self.uid = str(uid)
        self.title = title or ""
        self.url = url or ""
        self.author = author or ""
        self.published = published or ""
        self.thumbnail = thumbnail or ""

    def __repr__(self):
        return f"FeedItem({self.uid!r}, {self.title!r})"

    def __eq__(self, other):
        return isinstance(other, FeedItem) and other.uid == self.uid


def _text(node, path, ns=None):
    found = node.find(path, ns or {})
    return (found.text or "").strip() if found is not None and found.text else ""


def feed_url(kind: str, target: str) -> str:
    """URL a interroger pour une source donnee."""
    target = (target or "").strip()
    if kind == "youtube":
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={target}"
    if kind == "reddit":
        sub = target.lstrip("/").removeprefix("r/")
        return f"https://www.reddit.com/r/{sub}/new.rss?limit=10"
    if kind == "kick":
        return f"https://kick.com/api/v2/channels/{target.lower()}"
    return target  # 'rss' : l'URL est fournie telle quelle


def extract_youtube_channel_id(text: str):
    """Identifiant de chaine, depuis un ID deja valide ou le HTML d'une page.

    YouTube n'expose pas de resolution @pseudo -> UC... sans cle ; en revanche
    la page publique de la chaine contient l'identifiant en clair.
    """
    text = (text or "").strip()
    if YT_CHANNEL_ID_RE.match(text):
        return text
    for pattern in YT_CHANNEL_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def parse_atom(body: str) -> list:
    """Flux Atom (YouTube, Reddit). Renvoie les elements du plus recent au plus ancien."""
    root = ET.fromstring(body)
    ns = {"a": ATOM_NS, "yt": YT_NS, "m": MEDIA_NS}
    items = []
    for entry in root.findall("a:entry", ns):
        video_id = _text(entry, "yt:videoId", ns)
        uid = video_id or _text(entry, "a:id", ns)
        if not uid:
            continue
        link = entry.find("a:link", ns)
        thumbnail = ""
        media = entry.find("m:group/m:thumbnail", ns)
        if media is not None:
            thumbnail = media.get("url") or ""
        items.append(FeedItem(
            uid=uid,
            title=_text(entry, "a:title", ns),
            url=(link.get("href") if link is not None else ""),
            author=_text(entry, "a:author/a:name", ns),
            published=_text(entry, "a:published", ns) or _text(entry, "a:updated", ns),
            thumbnail=thumbnail,
        ))
    return items


def parse_rss(body: str) -> list:
    """Flux RSS 2.0 (podcasts et la majorite des blogs)."""
    root = ET.fromstring(body)
    channel = root.find("channel")
    if channel is None:
        return []
    items = []
    for item in channel.findall("item"):
        uid = _text(item, "guid") or _text(item, "link") or _text(item, "title")
        if not uid:
            continue
        thumbnail = ""
        image = item.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
        if image is not None:
            thumbnail = image.get("href") or ""
        items.append(FeedItem(
            uid=uid,
            title=_text(item, "title"),
            url=_text(item, "link"),
            author=_text(item, "author") or _text(channel, "title"),
            published=_text(item, "pubDate"),
            thumbnail=thumbnail,
        ))
    return items


def parse_feed(body: str) -> list:
    """Detecte Atom ou RSS et delegue. Renvoie [] si le corps n'est pas un flux."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    tag = root.tag.rsplit("}", 1)[-1].lower()
    if tag == "feed":
        return parse_atom(body)
    if tag == "rss":
        return parse_rss(body)
    return []


def parse_kick(payload: dict):
    """Direct Kick en cours, ou None si la chaine est hors ligne ou inconnue."""
    if not isinstance(payload, dict):
        return None
    livestream = payload.get("livestream")
    if not livestream or not livestream.get("is_live"):
        return None
    slug = payload.get("slug") or ""
    user = payload.get("user") or {}
    thumbnail = ""
    raw_thumbnail = livestream.get("thumbnail")
    if isinstance(raw_thumbnail, dict):
        thumbnail = raw_thumbnail.get("url") or ""
    elif isinstance(raw_thumbnail, str):
        thumbnail = raw_thumbnail
    return FeedItem(
        uid=str(livestream.get("id") or slug),
        title=livestream.get("session_title") or "En direct",
        url=f"https://kick.com/{slug}",
        author=user.get("username") or slug,
        published=str(livestream.get("start_time") or ""),
        thumbnail=thumbnail,
    )


def new_items(items: list, last_uid, limit: int = 3) -> list:
    """Elements publies depuis `last_uid`, du plus ancien au plus recent.

    Sans repere connu on ne renvoie rien : au premier passage sur une source,
    annoncer tout l'historique inonderait le salon.
    """
    if not items:
        return []
    if last_uid is None:
        return []
    fresh = []
    for item in items:
        if item.uid == last_uid:
            break
        fresh.append(item)
    return list(reversed(fresh[:limit]))
