import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest

from settings_fields import (
    Field, FieldError, apply_field, describe_fields, parse_bool, parse_color,
    parse_id, parse_value,
)


class TestBooleans(unittest.TestCase):
    """Les gens tapent `on`, `oui`, `1`… : tout doit passer."""

    def test_true_words(self):
        for word in ("1", "on", "oui", "yes", "true", "ACTIF", "Activer"):
            with self.subTest(word=word):
                self.assertEqual(parse_bool(word), 1)

    def test_false_words(self):
        for word in ("0", "off", "non", "no", "false", "Desactiver"):
            with self.subTest(word=word):
                self.assertEqual(parse_bool(word), 0)

    def test_anything_else_is_refused(self):
        for word in ("peut-etre", "", "2", None):
            with self.subTest(word=word):
                with self.assertRaises(FieldError):
                    parse_bool(word)


class TestDiscordIds(unittest.TestCase):
    """On accepte ce qu'un utilisateur colle depuis Discord."""

    def test_mentions_are_accepted(self):
        for raw in ("<@&123456>", "<#123456>", "<@123456>", "<@!123456>", "123456"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_id(raw), 123456)

    def test_emptiness_clears_the_field(self):
        for raw in ("", "  ", "-", "aucun", "none", None):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_id(raw))

    def test_garbage_is_refused(self):
        for raw in ("abc", "#salon", "12a"):
            with self.subTest(raw=raw):
                with self.assertRaises(FieldError):
                    parse_id(raw)


class TestColors(unittest.TestCase):
    def test_hash_is_optional_and_output_is_normalised(self):
        self.assertEqual(parse_color("00ff00"), "#00FF00")
        self.assertEqual(parse_color("#00FF00"), "#00FF00")

    def test_invalid_colors_are_refused(self):
        for raw in ("rouge", "#12345", "#GGGGGG", ""):
            with self.subTest(raw=raw):
                with self.assertRaises(FieldError):
                    parse_color(raw)


class TestNumbers(unittest.TestCase):
    def setUp(self):
        self.bounded = Field("int", "x", minimum=100, maximum=3000)

    def test_within_bounds(self):
        self.assertEqual(parse_value(self.bounded, "400"), 400)

    def test_below_minimum(self):
        with self.assertRaises(FieldError):
            parse_value(self.bounded, "10")

    def test_above_maximum(self):
        with self.assertRaises(FieldError):
            parse_value(self.bounded, "9999")

    def test_not_a_number(self):
        with self.assertRaises(FieldError):
            parse_value(self.bounded, "beaucoup")

    def test_comma_is_accepted_as_a_decimal_separator(self):
        self.assertEqual(parse_value(Field("float", "x"), "2,5"), 2.5)

    def test_float_truncates_to_int_for_int_fields(self):
        self.assertEqual(parse_value(Field("int", "x"), "7.9"), 7)


class TestChoices(unittest.TestCase):
    def setUp(self):
        self.field = Field("text", "x", choices=("open", "ticket"))

    def test_valid_choice_is_lowercased(self):
        self.assertEqual(parse_value(self.field, "TICKET"), "ticket")

    def test_invalid_choice_lists_the_options(self):
        with self.assertRaises(FieldError) as caught:
            parse_value(self.field, "licorne")
        self.assertIn("open", str(caught.exception))


class TestApplyField(unittest.TestCase):
    def setUp(self):
        self.fields = {"prix": Field("float", "Prix", minimum=0),
                       "actif": Field("bool", "Actif")}

    def test_field_name_is_case_insensitive(self):
        self.assertEqual(apply_field(self.fields, "PRIX", "250"), ("prix", 250.0))

    def test_unknown_field_lists_what_exists(self):
        with self.assertRaises(FieldError) as caught:
            apply_field(self.fields, "couleur", "x")
        self.assertIn("prix", str(caught.exception))
        self.assertIn("actif", str(caught.exception))


class TestDescription(unittest.TestCase):
    def test_hints_reflect_the_field_type(self):
        text = describe_fields({
            "actif": Field("bool", "Actif"),
            "prix": Field("float", "Prix", minimum=0),
            "couleur": Field("color", "Couleur"),
            "salon": Field("id", "Salon"),
        })
        self.assertIn("on | off", text)
        self.assertIn("≥ 0", text)
        self.assertIn("#RRGGBB", text)
        self.assertIn("mention", text)

    def test_current_values_are_shown_when_given(self):
        text = describe_fields({"prix": Field("float", "Prix")}, {"prix": 250})
        self.assertIn("250", text)

    def test_empty_values_are_shown_as_a_dash(self):
        text = describe_fields({"nom": Field("text", "Nom")}, {"nom": ""})
        self.assertIn("—", text)


class TestParityWithTheDashboard(unittest.TestCase):
    """Ce que le web configure doit l'etre aussi en commande."""

    def test_casino_effects_are_all_reachable_by_command(self):
        from cogs.jeu import STYLE_FIELD_COLUMNS
        # Colonnes editables de casino_config, hors identifiants techniques.
        from data.db import Database
        db = Database(path=":memory:")
        db.execute("INSERT OR IGNORE INTO casino_config (guild_id) VALUES (1)")
        columns = {row[1] for row in db.fetchall("PRAGMA table_info(casino_config)")}
        columns -= {"guild_id", "announce_channel_id"}
        self.assertEqual(columns - set(STYLE_FIELD_COLUMNS.values()), set())

    def test_game_settings_are_all_reachable_by_command(self):
        from cogs.jeu import GAME_FIELD_COLUMNS
        # Champs du formulaire d'edition du dashboard.
        web_fields = {"display_name", "category", "price", "cooldown_seconds",
                      "description", "enabled"}
        self.assertEqual(web_fields - set(GAME_FIELD_COLUMNS.values()), set())

    def test_shop_item_settings_are_all_reachable_by_command(self):
        from cogs.boutique import ITEM_FIELD_COLUMNS
        web_fields = {"display_name", "price", "stock", "per_user_limit", "enabled"}
        self.assertEqual(web_fields - set(ITEM_FIELD_COLUMNS.values()), set())


if __name__ == "__main__":
    unittest.main()
