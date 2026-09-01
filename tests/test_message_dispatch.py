import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import re
import unittest
from pathlib import Path

COGS_DIR = Path(__file__).resolve().parent.parent / "cogs"
ROOT = Path(__file__).resolve().parent.parent


class TestNoDoubleCommandDispatch(unittest.TestCase):
    """Un listener de Cog s'ajoute au on_message par defaut, il ne le remplace pas.

    Appeler bot.process_commands depuis un @commands.Cog.listener() relance donc
    le dispatch : chaque commande du bot s'executait deux fois. Symptomes
    observes : logs en double, double debit, et 404 Unknown Channel sur
    ,closeticket dont la seconde execution retrouvait le salon deja supprime.
    """

    def test_no_cog_calls_process_commands(self):
        offenders = []
        for path in sorted(COGS_DIR.glob("*.py")):
            for num, line in enumerate(path.read_text().splitlines(), 1):
                if "process_commands" in line and not line.strip().startswith("#"):
                    offenders.append(f"{path.name}:{num}")
        self.assertEqual(offenders, [], "process_commands relance le dispatch")

    def test_main_does_not_override_on_message(self):
        """Un @bot.event on_message remplacerait le defaut et couperait les commandes."""
        source = (ROOT / "main.py").read_text()
        self.assertNotRegex(source, r"@bot\.event\s*\n\s*async def on_message")

    def test_cog_on_message_listeners_are_listeners(self):
        """Tout on_message dans un cog doit etre declare via @commands.Cog.listener()."""
        for path in sorted(COGS_DIR.glob("*.py")):
            lines = path.read_text().splitlines()
            for num, line in enumerate(lines):
                if re.match(r"\s*async def on_message\(", line):
                    with self.subTest(cog=path.name, line=num + 1):
                        preceding = "\n".join(lines[max(0, num - 3):num])
                        self.assertIn("Cog.listener", preceding)
