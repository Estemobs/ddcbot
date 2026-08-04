import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest
from unittest.mock import MagicMock
from data.db import Database


def _make_cog():
    from cogs.leveling import cmdleveling
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdleveling(bot, db)


class TestLevelingXp(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_xp_nonexistent(self):
        self.assertEqual(self.cog.get_xp(999), 0)

    def test_add_xp(self):
        new_xp = self.cog.add_xp(100, 50)
        self.assertEqual(new_xp, 50)
        self.assertEqual(self.cog.get_xp(100), 50)

    def test_add_xp_accumulates(self):
        self.cog.add_xp(100, 50)
        self.cog.add_xp(100, 30)
        self.assertEqual(self.cog.get_xp(100), 80)


class TestLevelingConfig(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_config_creates_default(self):
        cfg = self.cog.get_config(123)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["xp_per_message"], 15)
        self.assertEqual(cfg["cooldown_seconds"], 60)

    def test_set_config(self):
        self.cog.set_config(123, xp_per_message=25, cooldown_seconds=30)
        cfg = self.cog.get_config(123)
        self.assertEqual(cfg["xp_per_message"], 25)
        self.assertEqual(cfg["cooldown_seconds"], 30)

    def test_level_from_xp(self):
        from cogs.leveling import level_from_xp, xp_in_level
        self.assertEqual(level_from_xp(0), 1)
        self.assertEqual(level_from_xp(99), 1)
        self.assertEqual(level_from_xp(100), 2)
        self.assertEqual(level_from_xp(250), 3)
        self.assertEqual(xp_in_level(0), 0)
        self.assertEqual(xp_in_level(150), 50)
