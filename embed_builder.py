"""Construction des messages Embed a partir des donnees stockees.

Sans discord.py : les regles et les limites de Discord sont ici, testables a
sec, et le dashboard s'en sert pour valider un embed avant enregistrement.

Les limites viennent de l'API Discord : depassees, l'envoi est refuse avec une
erreur peu lisible, d'ou la validation en amont.
"""

import json
import re

LIMITS = {
    "title": 256,
    "description": 4096,
    "author_name": 256,
    "footer_text": 2048,
    "field_name": 256,
    "field_value": 1024,
    "fields": 25,
    "content": 2000,
    "total": 6000,
}

HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
DEFAULT_COLOR = 0x5865F2


def parse_color(value) -> int:
    """Couleur en entier. Retombe sur le bleu Discord si la valeur est invalide."""
    if isinstance(value, int):
        return value & 0xFFFFFF
    match = HEX_COLOR_RE.match(str(value or "").strip())
    return int(match.group(1), 16) if match else DEFAULT_COLOR


def parse_fields(raw) -> list:
    """Champs de l'embed : [{name, value, inline}]. Tolere un JSON casse."""
    if isinstance(raw, list):
        candidate = raw
    else:
        try:
            candidate = json.loads(raw or "[]")
        except (TypeError, ValueError):
            return []
    if not isinstance(candidate, list):
        return []
    fields = []
    for entry in candidate:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        value = str(entry.get("value") or "").strip()
        if not name or not value:
            continue  # Discord refuse un champ dont un cote est vide
        fields.append({
            "name": name[:LIMITS["field_name"]],
            "value": value[:LIMITS["field_value"]],
            "inline": bool(entry.get("inline")),
        })
    return fields[:LIMITS["fields"]]


def total_length(embed: dict) -> int:
    """Longueur cumulee, telle que Discord la compte pour sa limite de 6000."""
    total = sum(len(str(embed.get(key) or "")) for key in
                ("title", "description", "author_name", "footer_text"))
    for field in parse_fields(embed.get("fields_json")):
        total += len(field["name"]) + len(field["value"])
    return total


def is_empty(embed: dict) -> bool:
    """Un embed sans titre, description, champ ni image est refuse par Discord."""
    if any(str(embed.get(key) or "").strip() for key in
           ("title", "description", "author_name", "footer_text",
            "image_url", "thumbnail_url")):
        return False
    return not parse_fields(embed.get("fields_json"))


def validate(embed: dict) -> list:
    """Liste des problemes bloquants. Vide si l'embed est envoyable."""
    problems = []
    if is_empty(embed) and not str(embed.get("content") or "").strip():
        problems.append("L'embed est vide : donnez au moins un titre ou une description.")
    for key in ("title", "description", "author_name", "footer_text", "content"):
        limit = LIMITS.get(key)
        if limit and len(str(embed.get(key) or "")) > limit:
            problems.append(f"Le champ « {key} » depasse {limit} caracteres.")
    if total_length(embed) > LIMITS["total"]:
        problems.append(f"L'embed total depasse {LIMITS['total']} caracteres.")
    return problems


def to_payload(embed: dict) -> dict:
    """Donnees pretes a devenir un discord.Embed, tronquees aux limites."""
    return {
        "title": str(embed.get("title") or "")[:LIMITS["title"]] or None,
        "description": str(embed.get("description") or "")[:LIMITS["description"]] or None,
        "url": str(embed.get("url") or "") or None,
        "color": parse_color(embed.get("color")),
        "author_name": str(embed.get("author_name") or "")[:LIMITS["author_name"]] or None,
        "author_icon": str(embed.get("author_icon") or "") or None,
        "footer_text": str(embed.get("footer_text") or "")[:LIMITS["footer_text"]] or None,
        "image_url": str(embed.get("image_url") or "") or None,
        "thumbnail_url": str(embed.get("thumbnail_url") or "") or None,
        "fields": parse_fields(embed.get("fields_json")),
        "content": str(embed.get("content") or "")[:LIMITS["content"]] or None,
    }


def render_variables(text: str, guild=None, member=None) -> str:
    """Remplace {server}, {count}, {user} — memes variables que les messages de bienvenue."""
    if not text:
        return ""
    if guild is not None:
        text = text.replace("{server}", getattr(guild, "name", ""))
        text = text.replace("{count}", str(getattr(guild, "member_count", "") or ""))
    if member is not None:
        text = text.replace("{user}", getattr(member, "mention", ""))
        text = text.replace("{name}", getattr(member, "display_name", ""))
    return text
