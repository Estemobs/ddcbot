import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest
from unittest.mock import MagicMock
from data.db import Database

GUILD = 111
OTHER_GUILD = 222


def _make_cog():
    from cogs.notes import cmdnotes
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdnotes(bot, db)


class TestNotes(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_get_note_nonexistent(self):
        self.assertIsNone(self.cog.get_note(GUILD, "test"))

    def test_set_and_get(self):
        self.cog.set_note(GUILD, "test", "content")
        self.assertEqual(self.cog.get_note(GUILD, "test"), "content")

    def test_set_note_overwrites(self):
        self.cog.set_note(GUILD, "test", "v1")
        self.cog.set_note(GUILD, "test", "v2")
        self.assertEqual(self.cog.get_note(GUILD, "test"), "v2")

    def test_delete_note(self):
        self.cog.set_note(GUILD, "test", "content")
        self.assertTrue(self.cog.delete_note(GUILD, "test"))
        self.assertIsNone(self.cog.get_note(GUILD, "test"))

    def test_delete_nonexistent_returns_false(self):
        self.assertFalse(self.cog.delete_note(GUILD, "nope"))

    def test_rename_note(self):
        self.cog.set_note(GUILD, "old", "content")
        self.assertTrue(self.cog.rename_note(GUILD, "old", "new"))
        self.assertIsNone(self.cog.get_note(GUILD, "old"))
        self.assertEqual(self.cog.get_note(GUILD, "new"), "content")

    def test_list_notes(self):
        self.cog.set_note(GUILD, "b", "b content")
        self.cog.set_note(GUILD, "a", "a content")
        self.assertEqual(self.cog.list_notes(GUILD), ["a", "b"])


class TestNotesAreScopedPerGuild(unittest.TestCase):
    """Les notes sont scopees par serveur depuis la migration 0010."""

    def setUp(self):
        self.cog = _make_cog()

    def test_note_invisible_from_another_guild(self):
        self.cog.set_note(GUILD, "regles", "contenu")
        self.assertIsNone(self.cog.get_note(OTHER_GUILD, "regles"))
        self.assertEqual(self.cog.list_notes(OTHER_GUILD), [])

    def test_same_title_holds_distinct_content_per_guild(self):
        self.cog.set_note(GUILD, "regles", "ici")
        self.cog.set_note(OTHER_GUILD, "regles", "la-bas")
        self.assertEqual(self.cog.get_note(GUILD, "regles"), "ici")
        self.assertEqual(self.cog.get_note(OTHER_GUILD, "regles"), "la-bas")

    def test_delete_only_affects_its_guild(self):
        self.cog.set_note(GUILD, "regles", "ici")
        self.cog.set_note(OTHER_GUILD, "regles", "la-bas")
        self.cog.delete_note(GUILD, "regles")
        self.assertEqual(self.cog.get_note(OTHER_GUILD, "regles"), "la-bas")


class TestLegacyGlobalNotes(unittest.TestCase):
    """Notes d'avant la migration (guild_id 0) : lisibles partout, en repli."""

    def setUp(self):
        self.cog = _make_cog()
        self.cog.db.execute(
            "INSERT INTO notes (guild_id, title, content) VALUES (0, 'ancienne', 'globale')"
        )

    def test_readable_from_any_guild(self):
        self.assertEqual(self.cog.get_note(GUILD, "ancienne"), "globale")
        self.assertEqual(self.cog.get_note(OTHER_GUILD, "ancienne"), "globale")

    def test_listed_alongside_guild_notes(self):
        self.cog.set_note(GUILD, "locale", "x")
        self.assertEqual(self.cog.list_notes(GUILD), ["ancienne", "locale"])

    def test_guild_note_shadows_legacy_one(self):
        self.cog.set_note(GUILD, "ancienne", "version du serveur")
        self.assertEqual(self.cog.get_note(GUILD, "ancienne"), "version du serveur")
        self.assertEqual(self.cog.get_note(OTHER_GUILD, "ancienne"), "globale")

    def test_deleting_shadow_falls_back_to_legacy(self):
        self.cog.set_note(GUILD, "ancienne", "version du serveur")
        self.assertTrue(self.cog.delete_note(GUILD, "ancienne"))
        self.assertEqual(self.cog.get_note(GUILD, "ancienne"), "globale")

    def test_legacy_note_can_be_deleted_without_a_shadow(self):
        self.assertTrue(self.cog.delete_note(GUILD, "ancienne"))
        self.assertIsNone(self.cog.get_note(OTHER_GUILD, "ancienne"))
