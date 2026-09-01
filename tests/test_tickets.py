import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import asyncio
import re
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from data.db import Database
from cogs.tickets import (
    CLOSE_BUTTON_ID, OPEN_BUTTON_ID, TICKET_FIELDS, TICKET_FIELD_COLUMNS, cmdtickets,
)

GUILD = 111
MEMBER = 42


def _cog():
    return cmdtickets(MagicMock(), Database(path=":memory:"))


def _guild(category=None):
    guild = MagicMock()
    guild.id = GUILD
    guild.get_channel.return_value = category
    channel = MagicMock(id=900)
    channel.send = AsyncMock()
    guild.create_text_channel = AsyncMock(return_value=channel)
    return guild


class TestConfigParity(unittest.TestCase):
    """Tout ce que le dashboard regle doit l'etre en commande, et l'inverse."""

    def test_every_web_field_has_a_command_field(self):
        source = (Path(__file__).resolve().parent.parent
                  / "web_dashboard" / "main.py").read_text()
        block = source[source.index('post("/guild/{guild_id}/tickets/config")'):]
        block = block[:block.index("):")]
        web_fields = set(re.findall(r"(\w+):\s*[^=]+=\s*Form\(", block)) - {"guild_id"}
        self.assertEqual(web_fields - set(TICKET_FIELD_COLUMNS.values()), set())

    def test_enabling_tickets_is_reachable_from_discord(self):
        """`enabled` n'avait aucune commande : les tickets ne s'activaient que sur le web."""
        self.assertIn("enabled", TICKET_FIELD_COLUMNS.values())

    def test_close_message_is_reachable_from_discord(self):
        self.assertIn("close_message", TICKET_FIELD_COLUMNS.values())

    def test_fields_are_documented(self):
        for key, field in TICKET_FIELDS.items():
            with self.subTest(field=key):
                self.assertTrue(field.label)


class TestConfigRoundTrip(unittest.TestCase):
    def setUp(self):
        self.cog = _cog()

    def test_defaults(self):
        cfg = self.cog.get_config(GUILD)
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["max_open_tickets"], 5)

    def test_saving_each_field(self):
        self.cog.save_config(GUILD, enabled=1, category_id=7, log_channel_id=8,
                             max_open_tickets=2, welcome_message="Salut",
                             close_message="Bye")
        cfg = self.cog.get_config(GUILD)
        self.assertEqual(
            (cfg["enabled"], cfg["category_id"], cfg["log_channel_id"],
             cfg["max_open_tickets"], cfg["welcome_message"], cfg["close_message"]),
            (True, 7, 8, 2, "Salut", "Bye"),
        )

    def test_config_is_per_guild(self):
        self.cog.save_config(GUILD, enabled=1)
        self.assertFalse(self.cog.get_config(999)["enabled"])


class TestOpeningRefusals(unittest.TestCase):
    """open_ticket renvoie la raison du refus au lieu de lever une exception."""

    def setUp(self):
        self.cog = _cog()
        self.member = MagicMock(id=MEMBER)

    def _open(self, guild):
        return asyncio.run(self.cog.open_ticket(guild, self.member))

    def test_disabled_tickets(self):
        channel, problem = self._open(_guild())
        self.assertIsNone(channel)
        self.assertIn("désactivés", problem)

    def test_missing_category(self):
        self.cog.save_config(GUILD, enabled=1)
        channel, problem = self._open(_guild())
        self.assertIsNone(channel)
        self.assertIn("catégorie", problem)

    def test_category_that_no_longer_exists(self):
        self.cog.save_config(GUILD, enabled=1, category_id=555)
        guild = _guild(category=None)
        channel, problem = self._open(guild)
        self.assertIsNone(channel)
        self.assertIn("n'existe plus", problem)

    def test_too_many_open_tickets(self):
        self.cog.save_config(GUILD, enabled=1, category_id=555, max_open_tickets=1)
        self.cog.create_ticket_record(GUILD, MEMBER, 900)
        channel, problem = self._open(_guild(category=MagicMock()))
        self.assertIsNone(channel)
        self.assertIn("déjà", problem)

    def test_a_closed_ticket_frees_a_slot(self):
        self.cog.save_config(GUILD, enabled=1, category_id=555, max_open_tickets=1)
        self.cog.create_ticket_record(GUILD, MEMBER, 900)
        self.cog.close_ticket(900)
        self.assertEqual(self.cog.get_open_count(GUILD, MEMBER), 0)

    def test_the_limit_is_per_member(self):
        self.cog.save_config(GUILD, enabled=1, category_id=555, max_open_tickets=1)
        self.cog.create_ticket_record(GUILD, MEMBER, 900)
        self.assertEqual(self.cog.get_open_count(GUILD, 999), 0)


class TestOpeningSucceeds(unittest.TestCase):
    def setUp(self):
        self.cog = _cog()
        self.cog.save_config(GUILD, enabled=1, category_id=555)
        self.member = MagicMock(id=MEMBER)

    def test_channel_is_created_and_recorded(self):
        guild = _guild(category=MagicMock())
        channel, problem = asyncio.run(self.cog.open_ticket(guild, self.member))
        self.assertIsNone(problem)
        self.assertIsNotNone(channel)
        self.assertEqual(self.cog.get_open_count(GUILD, MEMBER), 1)

    def test_ticket_numbers_increment(self):
        guild = _guild(category=MagicMock())
        asyncio.run(self.cog.open_ticket(guild, self.member))
        self.assertEqual(self.cog.get_ticket_number(GUILD), 1)
        asyncio.run(self.cog.open_ticket(guild, self.member))
        self.assertEqual(self.cog.get_ticket_number(GUILD), 2)


class TestPersistentButtons(unittest.TestCase):
    """Les boutons doivent survivre a un redemarrage du bot."""

    def test_custom_ids_are_fixed(self):
        self.assertEqual(OPEN_BUTTON_ID, "ddcbot:ticket:open")
        self.assertEqual(CLOSE_BUTTON_ID, "ddcbot:ticket:close")

    def test_views_are_registered_on_ready(self):
        source = (Path(__file__).resolve().parent.parent / "cogs" / "tickets.py").read_text()
        self.assertIn("add_view(TicketPanelView", source)
        self.assertIn("add_view(TicketCloseView", source)

    def test_views_never_time_out(self):
        source = (Path(__file__).resolve().parent.parent / "cogs" / "tickets.py").read_text()
        self.assertEqual(source.count("super().__init__(timeout=None)"), 2)


class TestPanelIsNoLongerAConfigDump(unittest.TestCase):
    def test_the_dead_config_embed_is_gone(self):
        source = (Path(__file__).resolve().parent.parent / "cogs" / "tickets.py").read_text()
        self.assertNotIn("build_panel_embed", source)

    def test_both_commands_exist_and_are_gated(self):
        from admin import ADMIN_COMMANDS
        from cogs.diagnostics import EXPECTED_COMMANDS
        for name in ("ticketpanel", "ticketconfig"):
            with self.subTest(command=name):
                self.assertIn(name, EXPECTED_COMMANDS)
                self.assertIn(name, ADMIN_COMMANDS)

    def test_opening_a_ticket_stays_open_to_members(self):
        from admin import ADMIN_COMMANDS
        self.assertNotIn("ticket", ADMIN_COMMANDS)
        self.assertNotIn("closeticket", ADMIN_COMMANDS)


if __name__ == "__main__":
    unittest.main()
