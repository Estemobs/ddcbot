import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest
from unittest.mock import MagicMock
from data.db import Database


def _make_cog():
    from cogs.automod import cmdautomod
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdautomod(bot, db)


class TestAutomodConfig(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_config_creates_default(self):
        cfg = self.cog.get_config(123)
        self.assertFalse(cfg["enabled"])
        self.assertTrue(cfg["warn_on_match"])
        self.assertTrue(cfg["delete_on_match"])

    def test_save_config(self):
        self.cog.save_config(123, enabled=True, delete_on_match=False)
        cfg = self.cog.get_config(123)
        self.assertTrue(cfg["enabled"])
        self.assertFalse(cfg["delete_on_match"])


class TestAutomodWords(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_add_and_list_words(self):
        self.cog.add_word(123, "badword")
        self.cog.add_word(123, "other")
        words = self.cog.list_words(123)
        self.assertEqual(words, ["badword", "other"])

    def test_add_duplicate_ignored(self):
        self.cog.add_word(123, "badword")
        self.cog.add_word(123, "badword")
        self.assertEqual(len(self.cog.list_words(123)), 1)

    def test_remove_word(self):
        self.cog.add_word(123, "badword")
        self.assertTrue(self.cog.remove_word(123, "badword"))
        self.assertEqual(len(self.cog.list_words(123)), 0)

    def test_remove_nonexistent_returns_false(self):
        self.assertFalse(self.cog.remove_word(123, "nope"))

    def test_matches(self):
        words = ["spam", "test"]
        self.assertTrue(self.cog._matches("this is spam content", words))
        self.assertTrue(self.cog._matches("TEST message", words))
        self.assertFalse(self.cog._matches("hello world", words))
