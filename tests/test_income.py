import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest
from unittest.mock import MagicMock
from data.db import Database


def _make_cog():
    from cogs.income import cmdincome
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdincome(bot, db)


class TestIncomeConfig(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_income_config_creates_default(self):
        cfg = self.cog.get_income_config(123)
        self.assertTrue(cfg["collect_enabled"])
        self.assertEqual(cfg["default_amount"], 100.0)
        self.assertEqual(cfg["default_interval_hours"], 24)

    def test_update_income_config(self):
        self.cog.update_income_config(123, default_amount=200.0)
        cfg = self.cog.get_income_config(123)
        self.assertEqual(cfg["default_amount"], 200.0)

    def test_reset_income_config(self):
        self.cog.update_income_config(123, default_amount=999)
        self.cog.reset_income_config(123)
        cfg = self.cog.get_income_config(123)
        self.assertEqual(cfg["default_amount"], 100.0)


class TestRoleIncome(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_add_and_get_role_income(self):
        self.cog.add_role_income(100, "VIP", 500.0, 12)
        ri = self.cog.get_role_income(100)
        self.assertIsNotNone(ri)
        self.assertEqual(ri["name"], "VIP")
        self.assertEqual(ri["amount"], 500.0)

    def test_list_role_income(self):
        self.cog.add_role_income(100, "VIP", 500.0, 12)
        self.cog.add_role_income(200, "Gold", 300.0, 6)
        incomes = self.cog.list_role_income()
        self.assertEqual(len(incomes), 2)

    def test_remove_role_income(self):
        self.cog.add_role_income(100, "VIP", 500.0, 12)
        self.cog.remove_role_income(100)
        self.assertIsNone(self.cog.get_role_income(100))

    def test_get_nonexistent_returns_none(self):
        self.assertIsNone(self.cog.get_role_income(999))
