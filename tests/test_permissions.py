import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import re
import unittest
from pathlib import Path

from admin import ADMIN_COMMANDS

COGS_DIR = Path(__file__).resolve().parent.parent / "cogs"


class TestSinglePermissionMechanism(unittest.TestCase):
    """admin.py + le gate global sont l'unique autorite sur les commandes admin.

    Un `@commands.has_permissions(manage_guild=True)` en plus du gate est au
    mieux redondant (le gate accorde deja manage_guild), au pire il annule la
    delegation par role du panneau de permissions : un role autorise via
    ,permpanel passe le gate mais echoue sur le decorateur.
    """

    def test_no_redundant_manage_guild_decorator(self):
        offenders = []
        for path in sorted(COGS_DIR.glob("*.py")):
            for num, line in enumerate(path.read_text().splitlines(), 1):
                if re.search(r"has(_guild)?_permissions\(manage_guild=True\)", line):
                    offenders.append(f"{path.name}:{num}")
        self.assertEqual(offenders, [], "decorateurs manage_guild residuels")

    def test_admin_commands_are_all_known_commands(self):
        from cogs.diagnostics import EXPECTED_COMMANDS
        unknown = {
            name for name in ADMIN_COMMANDS
            if " " not in name and name not in EXPECTED_COMMANDS
        }
        self.assertEqual(unknown, set())

    def test_config_commands_are_gated(self):
        """Toute commande qui ecrit de la config serveur doit etre dans ADMIN_COMMANDS."""
        for name in ["setlog", "unsetlog", "twitchconfig", "cmdadd", "cmdedit",
                     "cmdrm", "starboardclear", "addtag", "removetag", "tagedit",
                     "tagrename"]:
            with self.subTest(command=name):
                self.assertIn(name, ADMIN_COMMANDS)


class TestSchemaComesFromMigrations(unittest.TestCase):
    """Le schema vit dans data/migrations/, pas dans les cogs."""

    def test_no_cog_creates_tables(self):
        offenders = []
        for path in sorted(COGS_DIR.glob("*.py")):
            if "CREATE TABLE" in path.read_text():
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_every_table_is_expected_by_selftest(self):
        from data.db import Database
        from cogs.diagnostics import EXPECTED_TABLES
        db = Database(path=":memory:")
        real = {
            row["name"]
            for row in db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
        } - {"schema_migrations", "sqlite_sequence"}
        self.assertEqual(real - set(EXPECTED_TABLES), set(), "tables non surveillees")
        self.assertEqual(set(EXPECTED_TABLES) - real, set(), "tables attendues inexistantes")


class TestMainIsImportable(unittest.TestCase):
    def test_main_has_entrypoint_guard(self):
        """Importer main.py ne doit pas demarrer le bot."""
        source = (Path(__file__).resolve().parent.parent / "main.py").read_text()
        self.assertIn('if __name__ == "__main__":', source)
        self.assertNotRegex(source, r"^asyncio\.run\(main\(\)\)", )
