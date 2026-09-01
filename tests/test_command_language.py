import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import re
import unittest
from pathlib import Path

COGS_DIR = Path(__file__).resolve().parent.parent / "cogs"

# Fragments francais qui n'ont rien a faire dans un NOM de commande. Le francais
# reste dans les reponses du bot et dans l'interface web, pas dans ce que
# l'utilisateur tape.
FRENCH_FRAGMENTS = (
    "anniv", "vocal", "achet", "boutique", "succes", "quete", "accueil",
    "alerte", "inventaire", "paye", "devoir", "jeux", "aide", "langue",
    "argent", "travail", "supprim", "ajout", "parametre",
)

# Mots anglais dont un fragment francais est un sous-mot : faux positifs.
ALLOWED = {"games", "game", "gameaccess", "gamelots", "gamepanel", "addgame",
           "deletegame", "leaderboard", "clean_leaderboard"}

COMMAND_RE = re.compile(
    r"@commands\.(?:command|group|hybrid_command)\(([^)]*)\)\s*\n"
    r"(?:\s*@[^\n]*\n)*\s*async def (\w+)"
)


def declared_commands():
    """(fichier, nom effectif, alias) pour chaque commande du bot."""
    found = []
    for path in sorted(COGS_DIR.glob("*.py")):
        source = path.read_text()
        for match in COMMAND_RE.finditer(source):
            args, function = match.group(1), match.group(2)
            explicit = re.search(r"""name=["']([\w-]+)["']""", args)
            name = explicit.group(1) if explicit else function
            aliases = []
            alias_match = re.search(r"aliases=\[([^\]]*)\]", args)
            if alias_match:
                aliases = re.findall(r"""["']([\w-]+)["']""", alias_match.group(1))
            found.append((path.name, name, aliases))
    return found


class TestCommandNamesAreEnglish(unittest.TestCase):
    def setUp(self):
        self.commands = declared_commands()

    def test_the_bot_actually_declares_commands(self):
        """Garde-fou : si le parsing casse, les tests suivants passeraient a vide."""
        self.assertGreater(len(self.commands), 100)

    def test_no_command_name_is_french(self):
        offenders = []
        for filename, name, _ in self.commands:
            if name in ALLOWED:
                continue
            for fragment in FRENCH_FRAGMENTS:
                if fragment in name.lower():
                    offenders.append(f"{filename}: ,{name}")
                    break
        self.assertEqual(offenders, [], "noms de commandes en francais")

    def test_no_alias_is_french(self):
        offenders = []
        for filename, name, aliases in self.commands:
            for alias in aliases:
                if alias in ALLOWED:
                    continue
                for fragment in FRENCH_FRAGMENTS:
                    if fragment in alias.lower():
                        offenders.append(f"{filename}: ,{name} (alias {alias})")
                        break
        self.assertEqual(offenders, [], "alias de commandes en francais")

    def test_expected_commands_matches_what_is_declared(self):
        """EXPECTED_COMMANDS doit suivre les renommages, sinon selftest ment."""
        from cogs.diagnostics import EXPECTED_COMMANDS
        declared = {name for _, name, _ in self.commands}
        # Les sous-commandes de groupe portent un nom qualifie, hors de ce test.
        missing = declared - EXPECTED_COMMANDS - {"list", "enable", "disable", "reload"}
        self.assertEqual(missing, set(), "commandes declarees mais non attendues")

    def test_admin_commands_all_exist(self):
        from admin import ADMIN_COMMANDS
        from cogs.diagnostics import EXPECTED_COMMANDS
        unknown = {n for n in ADMIN_COMMANDS if " " not in n} - EXPECTED_COMMANDS
        self.assertEqual(unknown, set())


class TestFrenchStaysInTheOutput(unittest.TestCase):
    """Le francais doit rester dans ce que le bot repond, pas dans ce qu'on tape."""

    def test_replies_are_still_in_french(self):
        source = (COGS_DIR / "boutique.py").read_text()
        self.assertIn("Achat effectué", source)
        self.assertIn("quantité", source)

    def test_docstrings_still_document_in_french(self):
        source = (COGS_DIR / "birthdays.py").read_text()
        self.assertIn("anniversaire", source.lower())


if __name__ == "__main__":
    unittest.main()
