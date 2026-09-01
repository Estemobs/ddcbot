import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import json
import unittest
from unittest.mock import MagicMock

from data.db import Database
from embed_builder import (
    DEFAULT_COLOR, LIMITS, is_empty, parse_color, parse_fields, render_variables,
    to_payload, total_length, validate,
)
from cogs.embeds import cmdembeds

GUILD = 111


class TestColor(unittest.TestCase):
    def test_hex_with_and_without_hash(self):
        self.assertEqual(parse_color("#FF0000"), 0xFF0000)
        self.assertEqual(parse_color("00ff00"), 0x00FF00)

    def test_integer_is_masked(self):
        self.assertEqual(parse_color(0xFFFFFF + 1), 0)

    def test_invalid_falls_back_to_discord_blue(self):
        for value in ("rouge", "#GGG", "", None, "#12345"):
            with self.subTest(value=value):
                self.assertEqual(parse_color(value), DEFAULT_COLOR)


class TestFields(unittest.TestCase):
    def test_valid_fields_are_kept(self):
        raw = json.dumps([{"name": "A", "value": "B", "inline": True}])
        self.assertEqual(parse_fields(raw),
                         [{"name": "A", "value": "B", "inline": True}])

    def test_a_field_missing_a_side_is_dropped(self):
        """Discord refuse un champ dont le nom ou la valeur est vide."""
        raw = json.dumps([{"name": "A", "value": ""}, {"name": "", "value": "B"},
                          {"name": "C", "value": "D"}])
        self.assertEqual([f["name"] for f in parse_fields(raw)], ["C"])

    def test_broken_json_yields_no_fields(self):
        for raw in ("{pas du json", "", None, '"une chaine"', "42"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_fields(raw), [])

    def test_a_list_is_accepted_directly(self):
        self.assertEqual(len(parse_fields([{"name": "A", "value": "B"}])), 1)

    def test_field_count_is_capped(self):
        raw = [{"name": str(i), "value": "x"} for i in range(40)]
        self.assertEqual(len(parse_fields(raw)), LIMITS["fields"])

    def test_long_field_text_is_truncated(self):
        raw = [{"name": "n" * 500, "value": "v" * 2000}]
        field = parse_fields(raw)[0]
        self.assertEqual(len(field["name"]), LIMITS["field_name"])
        self.assertEqual(len(field["value"]), LIMITS["field_value"])

    def test_non_dict_entries_are_ignored(self):
        self.assertEqual(parse_fields(["texte", 42, {"name": "A", "value": "B"}]),
                         [{"name": "A", "value": "B", "inline": False}])


class TestValidation(unittest.TestCase):
    def test_empty_embed_is_refused(self):
        self.assertTrue(is_empty({}))
        self.assertTrue(validate({}))

    def test_a_description_alone_is_enough(self):
        embed = {"description": "Bonjour"}
        self.assertFalse(is_empty(embed))
        self.assertEqual(validate(embed), [])

    def test_an_image_alone_is_enough(self):
        self.assertFalse(is_empty({"image_url": "https://x/y.png"}))

    def test_fields_alone_are_enough(self):
        embed = {"fields_json": json.dumps([{"name": "A", "value": "B"}])}
        self.assertFalse(is_empty(embed))

    def test_plain_content_without_embed_is_allowed(self):
        self.assertEqual(validate({"content": "coucou"}), [])

    def test_overlong_title_is_reported(self):
        problems = validate({"title": "x" * 300})
        self.assertTrue(any("title" in p for p in problems))

    def test_global_limit_is_reported(self):
        embed = {"title": "t", "description": "d" * 4000,
                 "fields_json": json.dumps(
                     [{"name": "n" * 200, "value": "v" * 1000} for _ in range(5)])}
        self.assertTrue(any(str(LIMITS["total"]) in p for p in validate(embed)))

    def test_total_length_counts_fields(self):
        embed = {"title": "abc",
                 "fields_json": json.dumps([{"name": "de", "value": "fghi"}])}
        self.assertEqual(total_length(embed), 3 + 2 + 4)


class TestPayload(unittest.TestCase):
    def test_empty_strings_become_none(self):
        payload = to_payload({"title": "", "description": ""})
        self.assertIsNone(payload["title"])
        self.assertIsNone(payload["description"])

    def test_values_are_truncated_to_limits(self):
        payload = to_payload({"title": "x" * 500, "description": "y" * 5000})
        self.assertEqual(len(payload["title"]), LIMITS["title"])
        self.assertEqual(len(payload["description"]), LIMITS["description"])

    def test_color_is_resolved(self):
        self.assertEqual(to_payload({"color": "#FF0000"})["color"], 0xFF0000)


class TestVariables(unittest.TestCase):
    def setUp(self):
        self.guild = MagicMock()
        self.guild.name = "Mon Serveur"
        self.guild.member_count = 42
        self.member = MagicMock()
        self.member.mention = "<@7>"
        self.member.display_name = "estemobs"

    def test_server_variables(self):
        self.assertEqual(
            render_variables("Bienvenue sur {server} ({count})", self.guild),
            "Bienvenue sur Mon Serveur (42)",
        )

    def test_member_variables(self):
        self.assertEqual(
            render_variables("Salut {user} alias {name}", self.guild, self.member),
            "Salut <@7> alias estemobs",
        )

    def test_missing_context_leaves_text_alone(self):
        self.assertEqual(render_variables("{server}"), "{server}")

    def test_empty_text(self):
        self.assertEqual(render_variables(""), "")
        self.assertEqual(render_variables(None), "")


class TestEmbedStorage(unittest.TestCase):
    def setUp(self):
        self.cog = cmdembeds(MagicMock(), Database(path=":memory:"))
        self.cog.db.execute(
            "INSERT INTO embeds (guild_id, name, title) VALUES (?, ?, ?)",
            (GUILD, "reglement", "Règles"),
        )

    def test_lookup_is_case_insensitive(self):
        self.assertIsNotNone(self.cog.get_embed(GUILD, "REGLEMENT"))

    def test_embeds_are_per_guild(self):
        self.assertIsNone(self.cog.get_embed(999, "reglement"))

    def test_delete(self):
        self.assertTrue(self.cog.delete_embed(GUILD, "reglement"))
        self.assertFalse(self.cog.delete_embed(GUILD, "reglement"))

    def test_published_message_is_remembered(self):
        stored = self.cog.get_embed(GUILD, "reglement")
        self.cog.remember_message(stored["id"], 555, 777)
        stored = self.cog.get_embed(GUILD, "reglement")
        self.assertEqual((stored["channel_id"], stored["message_id"]), (555, 777))


class TestEmojiMirror(unittest.TestCase):
    """Le dashboard n'a pas de connexion Discord : le bot recopie les emojis."""

    def setUp(self):
        self.cog = cmdembeds(MagicMock(), Database(path=":memory:"))

    def _guild(self, emojis):
        guild = MagicMock()
        guild.id = GUILD
        guild.emojis = emojis
        return guild

    def _emoji(self, emoji_id, name, animated=False):
        emoji = MagicMock()
        emoji.id = emoji_id
        emoji.name = name
        emoji.animated = animated
        emoji.url = f"https://cdn/{name}.png"
        return emoji

    def test_sync_copies_emojis(self):
        self.cog.sync_emojis(self._guild([self._emoji(1, "pepe"),
                                          self._emoji(2, "dance", True)]))
        rows = self.cog.db.fetchall("SELECT name, animated FROM guild_emojis ORDER BY name")
        self.assertEqual([(r["name"], r["animated"]) for r in rows],
                         [("dance", 1), ("pepe", 0)])

    def test_sync_replaces_the_previous_state(self):
        self.cog.sync_emojis(self._guild([self._emoji(1, "pepe")]))
        self.cog.sync_emojis(self._guild([self._emoji(2, "autre")]))
        rows = self.cog.db.fetchall("SELECT name FROM guild_emojis")
        self.assertEqual([r["name"] for r in rows], ["autre"])

    def test_sync_on_an_empty_guild(self):
        self.cog.sync_emojis(self._guild([]))
        self.assertEqual(self.cog.db.fetchall("SELECT 1 FROM guild_emojis"), [])


if __name__ == "__main__":
    unittest.main()
