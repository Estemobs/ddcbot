import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest
from unittest.mock import MagicMock
from data.db import Database


def _make_cog():
    from cogs.guild_settings import cmdguildsettings
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdguildsettings(bot, db)


class TestGuildSettings(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_settings_creates_default(self):
        s = self.cog.get_settings(123)
        self.assertFalse(s["welcome_enabled"])
        self.assertFalse(s["leave_enabled"])
        self.assertIsNone(s["welcome_channel_id"])

    def test_save_settings(self):
        self.cog.save_settings(123, welcome_enabled=True, welcome_channel_id=456)
        s = self.cog.get_settings(123)
        self.assertTrue(s["welcome_enabled"])
        self.assertEqual(s["welcome_channel_id"], 456)

    def test_render(self):
        class FakeMember:
            display_name = "TestUser"
            mention = "@TestUser"
            guild = MagicMock()
            guild.member_count = 50
            guild.name = "TestServer"
        member = FakeMember()
        result = self.cog._render("Bienvenue {user} sur {server} ! ({count})", member)
        self.assertEqual(result, "Bienvenue @TestUser sur TestServer ! (50)")
