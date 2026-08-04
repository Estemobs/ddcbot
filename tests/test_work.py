import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest
from unittest.mock import MagicMock
from data.db import Database


def _make_cog():
    from cogs.work import cmdwork
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdwork(bot, db)


class TestWorkBalance(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_balance_nonexistent(self):
        self.assertEqual(self.cog.get_balance(999), 0.0)

    def test_add_balance(self):
        self.cog.add_balance(100, 200.0)
        self.assertEqual(self.cog.get_balance(100), 200.0)


class TestWorkSettings(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_work_settings_none(self):
        self.assertIsNone(self.cog.get_work_settings(123))

    def test_set_and_get(self):
        self.cog.set_work_settings(123, 10, 100, 3, 60, ["tier1", "tier2"])
        s = self.cog.get_work_settings(123)
        self.assertIsNotNone(s)
        self.assertEqual(s["min_amount"], 10)
        self.assertEqual(s["max_amount"], 100)
        self.assertEqual(s["reward_tiers"], 3)
        self.assertEqual(s["cooldown"], 60)
        self.assertEqual(s["rewards"], ["tier1", "tier2"])


class TestWorkState(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_work_state_none(self):
        self.assertIsNone(self.cog.get_work_state(123, 456))

    def test_record_work(self):
        self.cog.record_work(123, 456, 1000.0)
        s = self.cog.get_work_state(123, 456)
        self.assertIsNotNone(s)
        self.assertEqual(s["work_count"], 1)
        self.assertEqual(s["last_worked"], 1000.0)

    def test_record_work_accumulates(self):
        self.cog.record_work(123, 456, 1000.0)
        self.cog.record_work(123, 456, 2000.0)
        s = self.cog.get_work_state(123, 456)
        self.assertEqual(s["work_count"], 2)
        self.assertEqual(s["last_worked"], 2000.0)
