import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest
from unittest.mock import MagicMock
from data.db import Database


def _make_cog():
    from cogs.moderation import cmdmoderation
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdmoderation(bot, db)


class TestModerationConfig(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_guild_config_creates_default(self):
        cfg = self.cog.get_guild_config(123)
        self.assertTrue(cfg["warn"]["dm_user"])
        self.assertTrue(cfg["warn"]["announce_public"])
        self.assertFalse(cfg["actions"]["auto_timeout_enabled"])

    def test_save_guild_config(self):
        cfg = self.cog.get_guild_config(123)
        cfg["warn"]["dm_user"] = False
        cfg["actions"]["auto_timeout_enabled"] = True
        cfg["actions"]["auto_timeout_after_warns"] = 5
        self.cog.save_guild_config(123, cfg)
        loaded = self.cog.get_guild_config(123)
        self.assertFalse(loaded["warn"]["dm_user"])
        self.assertTrue(loaded["actions"]["auto_timeout_enabled"])
        self.assertEqual(loaded["actions"]["auto_timeout_after_warns"], 5)

    def test_missing_keys_get_backfilled(self):
        self.cog.save_guild_config(123, {"warn": {"dm_user": False}})
        cfg = self.cog.get_guild_config(123)
        self.assertFalse(cfg["warn"]["dm_user"])
        self.assertTrue(cfg["warn"]["announce_public"])


class TestModerationWarns(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_warn_count_nonexistent(self):
        self.assertEqual(self.cog.get_warn_count(123, 456), 0)

    def test_increment_warn(self):
        count = self.cog.increment_warn(123, 456)
        self.assertEqual(count, 1)
        count = self.cog.increment_warn(123, 456)
        self.assertEqual(count, 2)

    def test_clear_warns(self):
        self.cog.increment_warn(123, 456)
        self.cog.increment_warn(123, 456)
        self.cog.clear_warns(123, 456)
        self.assertEqual(self.cog.get_warn_count(123, 456), 0)
