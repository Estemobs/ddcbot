import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest
from unittest.mock import MagicMock
from data.db import Database


def _make_cog():
    from cogs.notes import cmdnotes
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdnotes(bot, db)


class TestNotes(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_note_nonexistent(self):
        self.assertIsNone(self.cog.get_note("test"))

    def test_set_and_get(self):
        self.cog.set_note("test", "content")
        self.assertEqual(self.cog.get_note("test"), "content")

    def test_set_note_overwrites(self):
        self.cog.set_note("test", "v1")
        self.cog.set_note("test", "v2")
        self.assertEqual(self.cog.get_note("test"), "v2")

    def test_delete_note(self):
        self.cog.set_note("test", "content")
        self.assertTrue(self.cog.delete_note("test"))
        self.assertIsNone(self.cog.get_note("test"))

    def test_delete_nonexistent_returns_false(self):
        self.assertFalse(self.cog.delete_note("nope"))

    def test_rename_note(self):
        self.cog.set_note("old", "content")
        self.assertTrue(self.cog.rename_note("old", "new"))
        self.assertIsNone(self.cog.get_note("old"))
        self.assertEqual(self.cog.get_note("new"), "content")

    def test_list_notes(self):
        self.cog.set_note("b", "b content")
        self.cog.set_note("a", "a content")
        self.assertEqual(self.cog.list_notes(), ["a", "b"])
