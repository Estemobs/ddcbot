import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from data.db import Database
from cogs.minecraft import cmdminecraft, RCONClient, RCONError, sanitize_minecraft_input


def _make_cog():
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdminecraft(bot, db)


class TestMinecraftConfig(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_config_returns_empty_when_unconfigured(self):
        self.assertEqual(self.cog.get_config(123), {})

    def test_save_and_get_config_roundtrip(self):
        self.cog.save_config(123, log_path="/tmp/latest.log", channel_id=456, method="rcon")
        cfg = self.cog.get_config(123)
        self.assertEqual(cfg["log_path"], "/tmp/latest.log")
        self.assertEqual(cfg["channel_id"], 456)
        self.assertEqual(cfg["method"], "rcon")
        self.assertFalse(cfg["enabled"])

    def test_save_config_merges_fields(self):
        self.cog.save_config(123, log_path="/tmp/latest.log")
        self.cog.save_config(123, tmux_session="mc")
        cfg = self.cog.get_config(123)
        self.assertEqual(cfg["log_path"], "/tmp/latest.log")
        self.assertEqual(cfg["tmux_session"], "mc")

    def test_minecraft_config_table_exists(self):
        row = self.cog.db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'minecraft_config'"
        )
        self.assertIsNotNone(row)


class TestSanitize(unittest.TestCase):
    def test_strips_newlines_and_nulls(self):
        self.assertEqual(sanitize_minecraft_input("salut\n\r\x00 le monde"), "salut le monde")

    def test_strips_mentions(self):
        self.assertEqual(sanitize_minecraft_input("<@123456> coucou"), "@<123456> coucou")

    def test_truncates_long_input(self):
        self.assertEqual(len(sanitize_minecraft_input("a" * 1000)), 500)


class TestRCONClient(unittest.TestCase):
    def test_sanitize_command_injection(self):
        # Les sauts de ligne ne doivent pas permettre d'injecter une 2e commande.
        cleaned = sanitize_minecraft_input("truc\nsay X")
        self.assertNotIn("\n", cleaned)

    def test_rcon_error_raises_when_not_connected(self):
        client = RCONClient("localhost", 25575, "pass")
        with self.assertRaises(RCONError):
            asyncio.run(client.command("list"))


if __name__ == "__main__":
    unittest.main()
