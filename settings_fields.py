"""Reglages modifiables en commande, sur le modele `,<commande> <champ> <valeur>`.

Le dashboard expose des formulaires a dix ou quinze champs. Les transposer en
arguments positionnels donnerait des commandes intapables ; chaque module
declare donc ses champs ici, et une seule mecanique les lit, les valide et les
decrit. C'est aussi ce qui garantit que web et commandes acceptent les memes
valeurs.

Sans dependance a discord.py : testable a sec.
"""

import re

HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
# <#123>, <@&123> ou 123 : on accepte ce qu'un utilisateur colle depuis Discord.
MENTION_RE = re.compile(r"^<[#@][&!]?(\d+)>$|^(\d+)$")

TRUE_WORDS = {"1", "on", "oui", "yes", "true", "actif", "active", "activer"}
FALSE_WORDS = {"0", "off", "non", "no", "false", "inactif", "desactive", "desactiver"}


class FieldError(Exception):
    """Valeur refusee, message destine a l'utilisateur."""


class Field:
    """Un reglage : son type, sa description, et de quoi le valider."""

    __slots__ = ("kind", "label", "choices", "minimum", "maximum")

    def __init__(self, kind: str, label: str, choices=None, minimum=None, maximum=None):
        self.kind = kind
        self.label = label
        self.choices = tuple(choices) if choices else None
        self.minimum = minimum
        self.maximum = maximum

    def hint(self) -> str:
        if self.choices:
            return " | ".join(self.choices)
        if self.kind == "bool":
            return "on | off"
        if self.kind in ("int", "float"):
            bounds = []
            if self.minimum is not None:
                bounds.append(f"≥ {self.minimum:g}")
            if self.maximum is not None:
                bounds.append(f"≤ {self.maximum:g}")
            return ", ".join(bounds) or "nombre"
        if self.kind == "color":
            return "#RRGGBB"
        if self.kind == "id":
            return "mention ou identifiant"
        return "texte"


def parse_bool(raw: str) -> int:
    value = (raw or "").strip().lower()
    if value in TRUE_WORDS:
        return 1
    if value in FALSE_WORDS:
        return 0
    raise FieldError("Répondez par `on` ou `off`.")


def parse_id(raw: str):
    """Identifiant Discord depuis une mention, un identifiant, ou rien."""
    value = (raw or "").strip()
    if value in ("", "-", "aucun", "none"):
        return None
    match = MENTION_RE.match(value)
    if match is None:
        raise FieldError("Donnez une mention ou un identifiant numérique.")
    return int(match.group(1) or match.group(2))


def parse_color(raw: str) -> str:
    match = HEX_COLOR_RE.match((raw or "").strip())
    if match is None:
        raise FieldError("Donnez une couleur au format `#RRGGBB`.")
    return "#" + match.group(1).upper()


def parse_value(field: Field, raw: str):
    """Valeur convertie et validee, prete a etre stockee."""
    raw = "" if raw is None else str(raw)
    if field.kind == "bool":
        return parse_bool(raw)
    if field.kind == "id":
        return parse_id(raw)
    if field.kind == "color":
        return parse_color(raw)
    if field.kind in ("int", "float"):
        try:
            number = float(raw.replace(",", ".").strip())
        except ValueError:
            raise FieldError("Donnez un nombre.")
        if field.minimum is not None and number < field.minimum:
            raise FieldError(f"La valeur doit être ≥ {field.minimum:g}.")
        if field.maximum is not None and number > field.maximum:
            raise FieldError(f"La valeur doit être ≤ {field.maximum:g}.")
        return int(number) if field.kind == "int" else number
    if field.choices:
        value = raw.strip().lower()
        if value not in field.choices:
            raise FieldError("Valeurs possibles : " + ", ".join(f"`{c}`" for c in field.choices))
        return value
    return raw.strip()


def apply_field(fields: dict, name: str, raw: str):
    """(champ, valeur) prets pour la base. Leve FieldError si le champ est inconnu."""
    key = (name or "").strip().lower()
    field = fields.get(key)
    if field is None:
        raise FieldError(
            "Champ inconnu. Champs disponibles : " + ", ".join(f"`{k}`" for k in fields)
        )
    return key, parse_value(field, raw)


def describe_fields(fields: dict, current: dict = None) -> str:
    """Liste des champs, avec leur valeur actuelle si elle est fournie."""
    current = current or {}
    lines = []
    for key, field in fields.items():
        line = f"`{key}` — {field.label} ({field.hint()})"
        if key in current:
            value = current[key]
            shown = "—" if value in (None, "") else value
            line += f"\n　actuel : **{shown}**"
        lines.append(line)
    return "\n".join(lines)
