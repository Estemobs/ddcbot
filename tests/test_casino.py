import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import random
import unittest
from collections import Counter

from data.db import Database
from casino_engine import (
    CasinoEngine, CasinoError, dice_sum_distribution, format_duration, normalize_slug,
)

GUILD = 111
OTHER = 222
PLAYER = 42
OTHER_PLAYER = 99


def _engine(seed=1):
    return CasinoEngine(Database(path=":memory:"), rng=random.Random(seed))


class TestSlugs(unittest.TestCase):
    """L'ancien systeme imposait isalpha() : ni chiffre, ni espace, ni tiret."""

    def test_spaces_digits_and_dashes_are_accepted(self):
        self.assertEqual(normalize_slug("Machine Saison 1"), "machine-saison-1")
        self.assertEqual(normalize_slug("b-gratuite"), "b-gratuite")
        self.assertEqual(normalize_slug("Box  bois "), "box-bois")

    def test_empty_slug_is_refused(self):
        engine = _engine()
        with self.assertRaises(CasinoError):
            engine.create_game(GUILD, "   ")


class TestWeightedDraw(unittest.TestCase):
    """Le tirage suit les poids : c'est ce qui rend le RTP pilotable."""

    def setUp(self):
        self.engine = _engine(seed=12345)
        game_id = self.engine.create_game(GUILD, "machine", price=250)
        for value, weight in [(450, 1), (300, 2), (280, 3), (150, 5), (100, 8)]:
            self.engine.add_lot(game_id, "money", value, weight=weight)
        self.game = self.engine.get_game(GUILD, "machine")

    def test_frequencies_follow_weights(self):
        rolls = 40000
        draws = Counter(self.engine.draw(self.game).reward.money for _ in range(rolls))
        total = sum([1, 2, 3, 5, 8])
        # Tolerance a ~4 ecarts-types : le tirage reste aleatoire malgre la graine fixe.
        for value, weight in [(450, 1), (300, 2), (280, 3), (150, 5), (100, 8)]:
            with self.subTest(value=value):
                self.assertAlmostEqual(draws[value] / rolls, weight / total, delta=0.01)

    def test_zero_weight_lot_never_drawn(self):
        self.engine.add_lot(self.game["id"], "money", 999999, weight=0)
        drawn = {self.engine.draw(self.game).reward.money for _ in range(2000)}
        self.assertNotIn(999999, drawn)

    def test_expected_value_uses_weights(self):
        # 1*450 + 2*300 + 3*280 + 5*150 + 8*100 = 3440, sur un poids total de 19
        self.assertAlmostEqual(self.engine.expected_value(self.game), 3440 / 19, places=6)
        self.assertAlmostEqual(self.engine.theoretical_rtp(self.game), 3440 / 19 / 250, places=6)

    def test_uniform_weights_can_exceed_the_price(self):
        """Le probleme d'origine : sans poids, plusieurs machines etaient rentables."""
        game_id = self.engine.create_game(GUILD, "dieu", price=50000)
        for value in (100000, 35000):
            self.engine.add_lot(game_id, "money", value)
        game = self.engine.get_game(GUILD, "dieu")
        self.assertGreater(self.engine.theoretical_rtp(game), 1.0)

    def test_game_without_lots_is_refused(self):
        self.engine.create_game(GUILD, "vide")
        with self.assertRaises(CasinoError):
            self.engine.draw(self.engine.get_game(GUILD, "vide"))


class TestDiceGames(unittest.TestCase):
    def setUp(self):
        self.engine = _engine(seed=7)

    def test_dice_sum_distribution_is_not_uniform(self):
        distribution = dice_sum_distribution(2, 6)
        self.assertAlmostEqual(distribution[7], 6 / 36)
        self.assertAlmostEqual(distribution[2], 1 / 36)
        self.assertAlmostEqual(sum(distribution.values()), 1.0)

    def test_loto_expected_value_weights_rare_sums_correctly(self):
        payouts = {2: 7000, 3: 4350, 4: 4550, 5: 4000, 6: 3580, 7: 3200,
                   8: 3500, 9: 3000, 10: 4800, 11: 5500, 12: 7000}
        game_id = self.engine.create_game(
            GUILD, "loto-or", kind="dice_sum", config={"dice": 2, "faces": 6}
        )
        for outcome, value in payouts.items():
            self.engine.add_lot(game_id, "money", value, outcome=outcome)
        game = self.engine.get_game(GUILD, "loto-or")
        ways = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
        expected = sum(ways[s] / 36 * payouts[s] for s in payouts)
        self.assertAlmostEqual(self.engine.expected_value(game), expected, places=6)

    def test_dice_sum_only_pays_configured_outcomes(self):
        game_id = self.engine.create_game(
            GUILD, "partiel", kind="dice_sum", config={"dice": 2, "faces": 6}
        )
        self.engine.add_lot(game_id, "money", 100, outcome=2)
        game = self.engine.get_game(GUILD, "partiel")
        results = {self.engine.draw(game).reward.kind for _ in range(300)}
        self.assertIn("nothing", results)

    def test_dice_guess_requires_a_valid_guess(self):
        self.engine.create_game(
            GUILD, "de", kind="dice_guess",
            config={"faces": 6, "win_amount": 3000, "lose_amount": 300},
        )
        game = self.engine.get_game(GUILD, "de")
        for bad in (None, "abc", 0, 7):
            with self.subTest(guess=bad):
                with self.assertRaises(CasinoError):
                    self.engine.draw(game, guess=bad)

    def test_dice_guess_expected_value(self):
        self.engine.create_game(
            GUILD, "de", kind="dice_guess",
            config={"faces": 6, "win_amount": 3000, "lose_amount": 300},
        )
        game = self.engine.get_game(GUILD, "de")
        self.assertAlmostEqual(self.engine.expected_value(game), 3000 / 6 - 300 * 5 / 6)

    def test_dice_guess_pays_win_or_loss(self):
        self.engine.create_game(
            GUILD, "de", kind="dice_guess",
            config={"faces": 6, "win_amount": 3000, "lose_amount": 300},
        )
        game = self.engine.get_game(GUILD, "de")
        amounts = {self.engine.draw(game, guess=3).reward.money for _ in range(200)}
        self.assertEqual(amounts, {3000.0, -300.0})


class TestCooldowns(unittest.TestCase):
    """Les boxes gratuites etaient ouvrables en boucle : aucun cooldown n'existait."""

    def setUp(self):
        self.engine = _engine()
        self.engine.create_game(GUILD, "b-gratuite", price=0, cooldown_seconds=86400)
        self.game = self.engine.get_game(GUILD, "b-gratuite")

    def test_no_cooldown_before_first_play(self):
        self.assertEqual(self.engine.cooldown_remaining(GUILD, PLAYER, self.game), 0)

    def test_cooldown_applies_after_playing(self):
        self.engine.record_play(GUILD, PLAYER, self.game, 0, 10)
        remaining = self.engine.cooldown_remaining(GUILD, PLAYER, self.game)
        self.assertGreater(remaining, 86000)

    def test_cooldown_is_per_player(self):
        self.engine.record_play(GUILD, PLAYER, self.game, 0, 10)
        self.assertEqual(self.engine.cooldown_remaining(GUILD, OTHER_PLAYER, self.game), 0)

    def test_cooldown_expires(self):
        self.engine.record_play(GUILD, PLAYER, self.game, 0, 10)
        future = self.engine.last_play_at(GUILD, PLAYER, "b-gratuite") + 86401
        self.assertEqual(
            self.engine.cooldown_remaining(GUILD, PLAYER, self.game, now=future), 0
        )

    def test_format_duration_is_readable(self):
        self.assertEqual(format_duration(30), "30s")
        self.assertEqual(format_duration(3600), "1h")
        self.assertEqual(format_duration(86400), "1j")


class TestQuestsArePerPlayer(unittest.TestCase):
    """L'ancien compteur de quete etait global : le 20e ouvreur raflait le lot."""

    def setUp(self):
        self.engine = _engine()
        game_id = self.engine.create_game(GUILD, "box", category="box")
        self.engine.add_lot(game_id, "money", 10)
        self.game = self.engine.get_game(GUILD, "box")
        self.engine.create_quest(
            GUILD, "Ouvreur", 20, "role", "111",
            target_kind="category", target_value="box",
        )

    def _play(self, user_id, times):
        for _ in range(times):
            self.engine.record_play(GUILD, user_id, self.game, 0, 10)

    def test_progress_counts_only_the_players_own_plays(self):
        self._play(PLAYER, 19)
        self._play(OTHER_PLAYER, 19)
        self.assertEqual(self.engine.claimable_quests(GUILD, PLAYER), [])
        self.assertEqual(self.engine.claimable_quests(GUILD, OTHER_PLAYER), [])

    def test_each_player_earns_the_reward_independently(self):
        self._play(PLAYER, 20)
        self.assertEqual(len(self.engine.claimable_quests(GUILD, PLAYER)), 1)
        self.assertEqual(self.engine.claimable_quests(GUILD, OTHER_PLAYER), [])
        self._play(OTHER_PLAYER, 20)
        self.assertEqual(len(self.engine.claimable_quests(GUILD, OTHER_PLAYER)), 1)

    def test_reward_is_paid_once(self):
        self._play(PLAYER, 25)
        quest, times, _ = self.engine.claimable_quests(GUILD, PLAYER)[0]
        self.engine.mark_claimed(quest["id"], PLAYER, times)
        self._play(PLAYER, 5)
        self.assertEqual(self.engine.claimable_quests(GUILD, PLAYER), [])

    def test_repeatable_quest_pays_every_tier(self):
        self.engine.create_quest(
            GUILD, "Palier", 5, "money", "100",
            target_kind="category", target_value="box", repeatable=True,
        )
        self._play(PLAYER, 21)
        due = {q["name"]: n for q, n, _ in self.engine.claimable_quests(GUILD, PLAYER)}
        self.assertEqual(due["Palier"], 4)

    def test_role_quest_depends_on_the_player_roles(self):
        self.engine.create_quest(
            GUILD, "Saison 1", 1, "money", "2000", target_kind="role", target_value="777"
        )
        holders = [q["name"] for q, _, _ in self.engine.claimable_quests(GUILD, PLAYER, [777])]
        others = [q["name"] for q, _, _ in self.engine.claimable_quests(GUILD, PLAYER, [1])]
        self.assertIn("Saison 1", holders)
        self.assertNotIn("Saison 1", others)


class TestInventory(unittest.TestCase):
    def setUp(self):
        self.engine = _engine()

    def test_ticket_is_consumed_once(self):
        self.engine.add_item(GUILD, PLAYER, "b-bois", "ticket")
        self.assertTrue(self.engine.has_ticket(GUILD, PLAYER, "b-bois"))
        self.assertTrue(self.engine.take_ticket(GUILD, PLAYER, "b-bois"))
        self.assertFalse(self.engine.has_ticket(GUILD, PLAYER, "b-bois"))

    def test_taking_a_missing_ticket_fails(self):
        self.assertFalse(self.engine.take_ticket(GUILD, PLAYER, "inconnu"))

    def test_inventory_groups_by_item(self):
        for _ in range(3):
            self.engine.add_item(GUILD, PLAYER, "Ticket de Loto", "item")
        self.assertEqual(self.engine.inventory(GUILD, PLAYER)[("item", "Ticket de Loto")], 3)

    def test_inventory_is_scoped_to_the_guild(self):
        self.engine.add_item(GUILD, PLAYER, "x", "item")
        self.assertEqual(self.engine.inventory(OTHER, PLAYER), {})


class TestGuildScoping(unittest.TestCase):
    def setUp(self):
        self.engine = _engine()

    def test_games_are_per_guild(self):
        self.engine.create_game(GUILD, "box")
        self.assertIsNone(self.engine.get_game(OTHER, "box"))

    def test_legacy_games_are_visible_everywhere(self):
        self.engine.create_game(0, "ancienne")
        self.assertIsNotNone(self.engine.get_game(GUILD, "ancienne"))
        self.assertIsNotNone(self.engine.get_game(OTHER, "ancienne"))

    def test_guild_game_shadows_the_legacy_one(self):
        self.engine.create_game(0, "box", display_name="Héritée")
        self.engine.create_game(GUILD, "box", display_name="Du serveur")
        self.assertEqual(self.engine.get_game(GUILD, "box")["display_name"], "Du serveur")
        self.assertEqual(self.engine.get_game(OTHER, "box")["display_name"], "Héritée")
        slugs = [g["slug"] for g in self.engine.list_games(GUILD)]
        self.assertEqual(slugs.count("box"), 1)

    def test_disabled_games_are_hidden_from_players(self):
        game_id = self.engine.create_game(GUILD, "box")
        self.engine.update_game(game_id, enabled=0)
        self.assertEqual(self.engine.list_games(GUILD), [])
        self.assertEqual(len(self.engine.list_games(GUILD, include_disabled=True)), 1)


class TestStats(unittest.TestCase):
    def test_actual_stats_track_the_house_balance(self):
        engine = _engine()
        game_id = engine.create_game(GUILD, "machine", price=100)
        engine.add_lot(game_id, "money", 50)
        game = engine.get_game(GUILD, "machine")
        for _ in range(10):
            engine.record_play(GUILD, PLAYER, game, 100, 50)
        stats = engine.actual_stats(GUILD)
        self.assertEqual(stats["plays"], 10)
        self.assertEqual(stats["cost"], 1000)
        self.assertEqual(stats["payout"], 500)
        self.assertEqual(stats["net"], 500)
        self.assertAlmostEqual(stats["rtp"], 0.5)

    def test_stats_are_empty_without_plays(self):
        self.assertIsNone(_engine().actual_stats(GUILD)["rtp"])


class TestStyle(unittest.TestCase):
    def test_defaults_exist_without_configuration(self):
        style = _engine().get_style(GUILD)
        self.assertTrue(style["animations_enabled"])
        self.assertTrue(style["reels"])

    def test_frames_end_on_the_result(self):
        engine = _engine()
        engine.update_style(GUILD, frame_count=3, reel_width=2)
        frames = engine.animation_frames(engine.get_style(GUILD), final="GAGNE")
        self.assertEqual(len(frames), 4)
        self.assertEqual(frames[-1], "GAGNE")
        self.assertEqual(len(frames[0].split(" ")), 2)

    def test_animations_can_be_disabled(self):
        engine = _engine()
        engine.update_style(GUILD, frame_count=0)
        self.assertEqual(engine.animation_frames(engine.get_style(GUILD)), [])

    def test_jackpot_threshold(self):
        engine = _engine()
        engine.update_style(GUILD, jackpot_threshold=1000)
        style = engine.get_style(GUILD)
        self.assertTrue(engine.is_jackpot(style, 1000))
        self.assertFalse(engine.is_jackpot(style, 999))

    def test_zero_threshold_disables_jackpots(self):
        engine = _engine()
        self.assertFalse(engine.is_jackpot(engine.get_style(GUILD), 10 ** 9))

    def test_unknown_style_field_is_refused(self):
        with self.assertRaises(CasinoError):
            _engine().update_style(GUILD, couleur="rouge")


class TestLegacyMigration(unittest.TestCase):
    """La migration 0012 reprend games/quests/inventory_tickets de l'ancien systeme."""

    def test_existing_games_lots_and_tickets_are_carried_over(self):
        import json
        import shutil
        import tempfile
        from data.db import MIGRATIONS_DIR

        staging = tempfile.mkdtemp()
        for name in sorted(os.listdir(MIGRATIONS_DIR)):
            if not name.startswith("0012"):
                shutil.copy(os.path.join(MIGRATIONS_DIR, name), staging)
        path = os.path.join(tempfile.mkdtemp(), "legacy.sqlite3")

        old = Database(path=path, migrations_dir=staging)
        old.execute(
            "INSERT INTO games (name, num_lots, lots_json, game_price) VALUES (?, ?, ?, ?)",
            ("bois", 3, json.dumps(
                [{"argent": "1500"}, {"grade": "42"}, {"ticket": "or"}]), 1050),
        )
        old.execute("INSERT INTO inventory_tickets (user_id, item_name) VALUES (?, ?)",
                    (PLAYER, "or"))
        old.execute("INSERT INTO quests (name, lot_count, lot_json, progress) VALUES (?, ?, ?, ?)",
                    ("bois", 20, json.dumps({"argent": "2000"}), 13))
        old.close()

        engine = CasinoEngine(Database(path=path))
        game = engine.get_game(GUILD, "bois")
        self.assertIsNotNone(game)
        self.assertEqual(game["price"], 1050)
        kinds = {lot["reward_kind"] for lot in engine.list_lots(game["id"])}
        self.assertEqual(kinds, {"money", "role", "ticket"})
        self.assertTrue(engine.has_ticket(GUILD, PLAYER, "or"))
        quest = engine.list_quests(GUILD)[0]
        self.assertEqual(quest["goal"], 20)
        self.assertEqual(quest["reward_kind"], "money")
        self.assertEqual(quest["reward_value"], "2000")
