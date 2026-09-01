import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import json
import time
import unittest
from unittest.mock import MagicMock

from data.db import Database
import achievements_engine as engine
from achievements_engine import (
    ACTION_KINDS, METRICS, matches, on_cooldown, parse_actions, progress,
    read_metric, render, validate_automation,
)
from cogs.achievements import cmdachievements

GUILD = 111
OTHER = 222
PLAYER = 42


def _cog():
    return cmdachievements(MagicMock(), Database(path=":memory:"))


class TestMetrics(unittest.TestCase):
    """Chaque compteur doit savoir se lire, meme quand le membre n'a rien fait."""

    def setUp(self):
        self.cog = _cog()

    def test_every_metric_reads_zero_by_default(self):
        for metric in METRICS:
            with self.subTest(metric=metric):
                self.assertEqual(read_metric(self.cog.db, metric, GUILD, PLAYER), 0)

    def test_unknown_metric_is_zero(self):
        self.assertEqual(read_metric(self.cog.db, "inexistant", GUILD, PLAYER), 0)

    def test_messages_are_counted(self):
        self.cog.touch(GUILD, PLAYER, messages=3)
        self.cog.touch(GUILD, PLAYER, messages=2)
        self.assertEqual(read_metric(self.cog.db, "messages", GUILD, PLAYER), 5)

    def test_voice_is_reported_in_minutes(self):
        self.cog.touch(GUILD, PLAYER, voice_seconds=185)
        self.assertEqual(read_metric(self.cog.db, "voice_minutes", GUILD, PLAYER), 3)

    def test_activity_is_per_guild(self):
        self.cog.touch(GUILD, PLAYER, messages=5)
        self.assertEqual(read_metric(self.cog.db, "messages", OTHER, PLAYER), 0)

    def test_invites_come_from_the_invites_table(self):
        self.cog.db.execute(
            "INSERT INTO invites (guild_id, user_id, invited, left) VALUES (?, ?, ?, ?)",
            (GUILD, PLAYER, 7, 1),
        )
        self.assertEqual(read_metric(self.cog.db, "invites", GUILD, PLAYER), 7)

    def test_balance_comes_from_the_economy(self):
        self.cog.db.execute("INSERT INTO balances (user_id, amount) VALUES (?, ?)",
                            (PLAYER, 1500.9))
        self.assertEqual(read_metric(self.cog.db, "balance", GUILD, PLAYER), 1500)

    def test_casino_plays_are_counted(self):
        for _ in range(4):
            self.cog.db.execute(
                "INSERT INTO casino_plays (guild_id, user_id, game_slug) VALUES (?, ?, ?)",
                (GUILD, PLAYER, "box"),
            )
        self.assertEqual(read_metric(self.cog.db, "casino_plays", GUILD, PLAYER), 4)


class TestAchievements(unittest.TestCase):
    def setUp(self):
        self.cog = _cog()
        self.cog.create_achievement(GUILD, "Bavard", "messages", 100, "money", "500")

    def test_progress_reports_value_goal_and_state(self):
        achievement = self.cog.list_achievements(GUILD)[0]
        self.assertEqual(progress(self.cog.db, achievement, GUILD, PLAYER), (0, 100, False))
        self.cog.touch(GUILD, PLAYER, messages=100)
        self.assertEqual(progress(self.cog.db, achievement, GUILD, PLAYER), (100, 100, True))

    def test_nothing_unlocks_before_the_goal(self):
        self.cog.touch(GUILD, PLAYER, messages=99)
        self.assertEqual(self.cog.newly_unlocked(GUILD, PLAYER), [])

    def test_unlock_is_reported_once(self):
        self.cog.touch(GUILD, PLAYER, messages=150)
        due = self.cog.newly_unlocked(GUILD, PLAYER)
        self.assertEqual(len(due), 1)
        self.cog.unlock(due[0]["id"], PLAYER)
        self.assertEqual(self.cog.newly_unlocked(GUILD, PLAYER), [])

    def test_unlocks_are_per_player(self):
        self.cog.touch(GUILD, PLAYER, messages=150)
        due = self.cog.newly_unlocked(GUILD, PLAYER)
        self.cog.unlock(due[0]["id"], PLAYER)
        self.assertFalse(self.cog.is_unlocked(due[0]["id"], 999))

    def test_unknown_metric_is_refused(self):
        with self.assertRaises(engine.AutomationError):
            self.cog.create_achievement(GUILD, "X", "nimportequoi", 1)

    def test_unknown_reward_is_refused(self):
        with self.assertRaises(engine.AutomationError):
            self.cog.create_achievement(GUILD, "X", "messages", 1, "licorne")

    def test_goal_is_at_least_one(self):
        self.cog.create_achievement(GUILD, "Zero", "messages", 0)
        stored = [a for a in self.cog.list_achievements(GUILD) if a["name"] == "Zero"][0]
        self.assertEqual(stored["goal"], 1)

    def test_achievements_are_per_guild(self):
        self.assertEqual(self.cog.list_achievements(OTHER), [])

    def test_delete_removes_unlocks_too(self):
        achievement = self.cog.list_achievements(GUILD)[0]
        self.cog.unlock(achievement["id"], PLAYER)
        self.assertTrue(self.cog.delete_achievement(GUILD, "bavard"))
        self.assertEqual(
            self.cog.db.fetchall("SELECT 1 FROM achievement_unlocks"), []
        )

    def test_disabled_achievements_are_hidden(self):
        self.cog.db.execute("UPDATE achievements SET enabled = 0")
        self.assertEqual(self.cog.list_achievements(GUILD), [])
        self.assertEqual(len(self.cog.list_achievements(GUILD, include_disabled=True)), 1)


class TestAutomationActions(unittest.TestCase):
    def test_valid_actions_are_kept(self):
        raw = json.dumps([{"kind": "send_message", "target": "1", "value": "hey"}])
        self.assertEqual(parse_actions(raw),
                         [{"kind": "send_message", "value": "hey", "target": "1"}])

    def test_unknown_action_kinds_are_dropped(self):
        raw = json.dumps([{"kind": "lancer_les_missiles"}, {"kind": "add_money", "value": "5"}])
        self.assertEqual([a["kind"] for a in parse_actions(raw)], ["add_money"])

    def test_broken_json_yields_nothing(self):
        for raw in ("{casse", "", None, "42", '"texte"'):
            with self.subTest(raw=raw):
                self.assertEqual(parse_actions(raw), [])

    def test_every_documented_kind_is_accepted(self):
        raw = [{"kind": kind} for kind in ACTION_KINDS]
        self.assertEqual(len(parse_actions(raw)), len(ACTION_KINDS))


class TestAutomationValidation(unittest.TestCase):
    def _rule(self, **overrides):
        rule = {"event": "member_join", "match_type": "any", "match_value": "",
                "actions_json": json.dumps([{"kind": "send_dm", "value": "salut"}])}
        rule.update(overrides)
        return rule

    def test_a_complete_rule_is_valid(self):
        self.assertEqual(validate_automation(self._rule()), [])

    def test_unknown_event_is_reported(self):
        self.assertTrue(validate_automation(self._rule(event="explosion")))

    def test_unknown_match_type_is_reported(self):
        self.assertTrue(validate_automation(self._rule(match_type="peut-etre")))

    def test_broken_regex_is_reported(self):
        problems = validate_automation(self._rule(match_type="regex", match_value="[a-"))
        self.assertTrue(any("reguliere" in p for p in problems))

    def test_a_rule_without_actions_is_reported(self):
        self.assertTrue(validate_automation(self._rule(actions_json="[]")))


class TestAutomationMatching(unittest.TestCase):
    def test_any_always_matches(self):
        self.assertTrue(matches({"match_type": "any"}, text="peu importe"))

    def test_contains_is_case_insensitive(self):
        rule = {"match_type": "contains", "match_value": "Bonjour"}
        self.assertTrue(matches(rule, text="eh bonjour toi"))
        self.assertFalse(matches(rule, text="salut"))

    def test_equals_ignores_surrounding_spaces(self):
        rule = {"match_type": "equals", "match_value": "ping"}
        self.assertTrue(matches(rule, text="  PING "))
        self.assertFalse(matches(rule, text="ping pong"))

    def test_regex(self):
        rule = {"match_type": "regex", "match_value": r"^\d+$"}
        self.assertTrue(matches(rule, text="12345"))
        self.assertFalse(matches(rule, text="12a"))

    def test_broken_regex_never_matches(self):
        self.assertFalse(matches({"match_type": "regex", "match_value": "[a-"}, text="a"))

    def test_role_condition(self):
        rule = {"match_type": "role", "match_value": "777"}
        self.assertTrue(matches(rule, role_ids=[1, 777]))
        self.assertFalse(matches(rule, role_ids=[1]))
        self.assertFalse(matches(rule, role_ids=None))

    def test_channel_condition(self):
        rule = {"match_type": "channel", "match_value": "555"}
        self.assertTrue(matches(rule, channel_id=555))
        self.assertFalse(matches(rule, channel_id=1))

    def test_an_empty_value_behaves_like_any(self):
        self.assertTrue(matches({"match_type": "contains", "match_value": ""}, text="x"))


class TestAutomationCooldown(unittest.TestCase):
    def test_no_cooldown_configured(self):
        self.assertFalse(on_cooldown({"cooldown_seconds": 0, "last_run": time.time()}))

    def test_within_the_delay(self):
        self.assertTrue(on_cooldown({"cooldown_seconds": 60, "last_run": time.time()}))

    def test_after_the_delay(self):
        self.assertFalse(on_cooldown({"cooldown_seconds": 60, "last_run": time.time() - 61}))

    def test_never_run_yet(self):
        self.assertFalse(on_cooldown({"cooldown_seconds": 60, "last_run": 0}))


class TestRender(unittest.TestCase):
    def test_variables_are_substituted(self):
        self.assertEqual(
            render("Salut {user}, bienvenue sur {server} !",
                   {"user": "<@7>", "server": "Chez moi"}),
            "Salut <@7>, bienvenue sur Chez moi !",
        )

    def test_unknown_variables_are_left_alone(self):
        self.assertEqual(render("{inconnu}", {"user": "x"}), "{inconnu}")

    def test_empty_template(self):
        self.assertEqual(render("", {}), "")
        self.assertEqual(render(None, None), "")


class TestAutomationStorage(unittest.TestCase):
    def setUp(self):
        self.cog = _cog()
        self.cog.db.execute(
            "INSERT INTO automations (guild_id, name, event, actions_json) VALUES (?, ?, ?, ?)",
            (GUILD, "Accueil", "member_join",
             json.dumps([{"kind": "send_dm", "value": "salut"}])),
        )

    def test_rules_are_filtered_by_event(self):
        self.assertEqual(len(self.cog.list_automations(GUILD, "member_join")), 1)
        self.assertEqual(self.cog.list_automations(GUILD, "message"), [])

    def test_rules_are_per_guild(self):
        self.assertEqual(self.cog.list_automations(OTHER), [])

    def test_runs_are_counted(self):
        rule = self.cog.list_automations(GUILD)[0]
        self.cog.mark_run(rule["id"])
        self.cog.mark_run(rule["id"])
        self.assertEqual(self.cog.list_automations(GUILD)[0]["runs"], 2)


class TestWelcomePanel(unittest.TestCase):
    def setUp(self):
        self.cog = _cog()

    def test_defaults(self):
        cfg = self.cog.get_welcome_panel(GUILD)
        self.assertFalse(cfg["enabled"])
        self.assertIn("{user}", cfg["greet_template"])

    def test_greeting_variables(self):
        cfg = self.cog.get_welcome_panel(GUILD)
        text = render(cfg["greet_template"],
                      {"user": "<@7>", "server": "Chez moi", "count": 42})
        self.assertIn("<@7>", text)
        self.assertIn("Chez moi", text)
        self.assertIn("42", text)


if __name__ == "__main__":
    unittest.main()
