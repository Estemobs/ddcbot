import os
import sys

# Ensure conftest's discord stub is loaded before any cog import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest
from unittest.mock import MagicMock
from data.db import Database


def _make_cog():
    from cogs.economie import cmdeco
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdeco(bot, db)


class TestEconomyBalance(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_balance_nonexistent_returns_zero(self):
        self.assertEqual(self.cog.get_balance(999), 0.0)

    def test_create_account(self):
        self.cog.create_account(100, 500.0)
        self.assertTrue(self.cog.has_account(100))
        self.assertEqual(self.cog.get_balance(100), 500.0)

    def test_add_balance(self):
        self.cog.create_account(100, 100.0)
        self.cog.add_balance(100, 50.0)
        self.assertEqual(self.cog.get_balance(100), 150.0)

    def test_add_balance_negative(self):
        self.cog.create_account(100, 100.0)
        self.cog.add_balance(100, -30.0)
        self.assertEqual(self.cog.get_balance(100), 70.0)

    def test_set_balance(self):
        self.cog.create_account(100, 100.0)
        self.cog.set_balance(100, 999.0)
        self.assertEqual(self.cog.get_balance(100), 999.0)

    def test_create_account_idempotent(self):
        self.cog.create_account(100, 100.0)
        self.cog.create_account(100, 500.0)
        self.assertEqual(self.cog.get_balance(100), 100.0)


class TestEconomyConfig(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_eco_config_creates_default(self):
        cfg = self.cog.get_eco_config(123)
        self.assertTrue(cfg["allow_transfers"])
        self.assertEqual(cfg["max_transfer"], 10000)
        self.assertFalse(cfg["allow_negative_balances"])

    def test_update_eco_config(self):
        self.cog.update_eco_config(123, max_transfer=5000, allow_transfers=False)
        cfg = self.cog.get_eco_config(123)
        self.assertEqual(cfg["max_transfer"], 5000)
        self.assertFalse(cfg["allow_transfers"])

    def test_reset_eco_config(self):
        self.cog.update_eco_config(123, max_transfer=999)
        self.cog.reset_eco_config(123)
        cfg = self.cog.get_eco_config(123)
        self.assertEqual(cfg["max_transfer"], 10000)
