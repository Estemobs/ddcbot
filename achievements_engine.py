"""Regles des succes et des automatisations, sans discord.py.

Comme casino_engine : le calcul et les decisions vivent ici, testables a sec,
et le cog ne garde que l'ecoute des evenements Discord et l'application des
recompenses.

Un succes est « atteindre N sur un compteur ». Les compteurs viennent de tables
deja alimentees ailleurs (invitations, economie, casino) ou de member_activity,
que le cog des succes tient a jour lui-meme.
"""

import json
import re
import time

# Chaque compteur sait se lire en SQL. La requete renvoie une seule valeur.
METRICS = {
    "messages": (
        "Messages envoyes",
        "SELECT COALESCE(messages, 0) AS v FROM member_activity "
        "WHERE guild_id = ? AND user_id = ?",
    ),
    "voice_minutes": (
        "Minutes en vocal",
        "SELECT COALESCE(voice_seconds, 0) / 60 AS v FROM member_activity "
        "WHERE guild_id = ? AND user_id = ?",
    ),
    "reactions": (
        "Reactions ajoutees",
        "SELECT COALESCE(reactions, 0) AS v FROM member_activity "
        "WHERE guild_id = ? AND user_id = ?",
    ),
    "seniority_days": (
        "Jours sur le serveur",
        "SELECT CAST((unixepoch() - first_seen) / 86400 AS INTEGER) AS v "
        "FROM member_activity WHERE guild_id = ? AND user_id = ?",
    ),
    "invites": (
        "Invitations",
        "SELECT COALESCE(invited, 0) AS v FROM invites WHERE guild_id = ? AND user_id = ?",
    ),
    "casino_plays": (
        "Parties de casino",
        "SELECT COUNT(*) AS v FROM casino_plays WHERE guild_id = ? AND user_id = ?",
    ),
    # `balances` et `levels` ne sont pas scopes par serveur : le guild_id est
    # accepte puis ignore, pour garder une signature unique.
    "balance": (
        "Solde",
        "SELECT CAST(COALESCE(amount, 0) AS INTEGER) AS v FROM balances "
        "WHERE ? IS NOT NULL AND user_id = ?",
    ),
    "level": (
        "Experience",
        "SELECT COALESCE(xp, 0) AS v FROM levels WHERE ? IS NOT NULL AND user_id = ?",
    ),
}

REWARD_KINDS = ("none", "money", "role")

EVENTS = ("member_join", "member_leave", "message", "reaction_add", "boost", "achievement")
MATCH_TYPES = ("any", "contains", "equals", "regex", "role", "channel")
ACTION_KINDS = ("send_message", "send_dm", "add_role", "remove_role", "add_money", "react")


class AutomationError(Exception):
    """Regle invalide, message destine a l'utilisateur."""


def metric_label(metric: str) -> str:
    spec = METRICS.get(metric)
    return spec[0] if spec else metric


def read_metric(db, metric: str, guild_id: int, user_id: int) -> int:
    """Valeur d'un compteur pour un membre. 0 si inconnu ou absent."""
    spec = METRICS.get(metric)
    if spec is None:
        return 0
    row = db.fetchone(spec[1], (guild_id, user_id))
    if row is None:
        return 0
    try:
        return int(row["v"] or 0)
    except (TypeError, ValueError):
        return 0


def progress(db, achievement: dict, guild_id: int, user_id: int) -> tuple:
    """(valeur actuelle, objectif, atteint ?)."""
    value = read_metric(db, achievement["metric"], guild_id, user_id)
    goal = max(1, int(achievement["goal"] or 1))
    return value, goal, value >= goal


def parse_actions(raw) -> list:
    """Actions d'une automatisation : [{kind, ...}]. Ignore ce qui est invalide."""
    if isinstance(raw, list):
        candidate = raw
    else:
        try:
            candidate = json.loads(raw or "[]")
        except (TypeError, ValueError):
            return []
    if not isinstance(candidate, list):
        return []
    actions = []
    for entry in candidate:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "").strip()
        if kind not in ACTION_KINDS:
            continue
        actions.append({
            "kind": kind,
            "value": str(entry.get("value") or ""),
            "target": str(entry.get("target") or ""),
        })
    return actions


def validate_automation(rule: dict) -> list:
    """Problemes bloquants d'une regle. Vide si elle est utilisable."""
    problems = []
    if rule.get("event") not in EVENTS:
        problems.append(f"Evenement inconnu : {rule.get('event')}")
    if rule.get("match_type") not in MATCH_TYPES:
        problems.append(f"Condition inconnue : {rule.get('match_type')}")
    if rule.get("match_type") == "regex":
        try:
            re.compile(rule.get("match_value") or "")
        except re.error as exc:
            problems.append(f"Expression reguliere invalide : {exc}")
    if not parse_actions(rule.get("actions_json")):
        problems.append("La regle n'a aucune action valide.")
    return problems


def matches(rule: dict, *, text: str = "", role_ids=None, channel_id=None) -> bool:
    """La condition de la regle est-elle satisfaite par ce contexte ?"""
    match_type = rule.get("match_type") or "any"
    value = (rule.get("match_value") or "").strip()

    if match_type == "any" or not value:
        return True
    if match_type == "contains":
        return value.lower() in (text or "").lower()
    if match_type == "equals":
        return (text or "").strip().lower() == value.lower()
    if match_type == "regex":
        try:
            return re.search(value, text or "", re.IGNORECASE) is not None
        except re.error:
            return False
    if match_type == "role":
        try:
            return int(value) in set(role_ids or [])
        except (TypeError, ValueError):
            return False
    if match_type == "channel":
        try:
            return int(value) == channel_id
        except (TypeError, ValueError):
            return False
    return False


def on_cooldown(rule: dict, now: float = None) -> bool:
    """Une regle a cooldown ne se redeclenche pas avant la fin du delai."""
    cooldown = rule.get("cooldown_seconds") or 0
    if cooldown <= 0:
        return False
    now = time.time() if now is None else now
    return (now - (rule.get("last_run") or 0)) < cooldown


def render(template: str, context: dict) -> str:
    """Remplace {user}, {server}, {count}, {value}, {name} dans un texte d'action."""
    text = template or ""
    for key, value in (context or {}).items():
        text = text.replace("{" + key + "}", str(value))
    return text
