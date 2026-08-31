import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import time
import unittest
from unittest.mock import MagicMock

from data.db import Database

GUILD = 111
ROLE = 555
PLAYER = 42
OTHER_PLAYER = 99


def _income_cog():
    from cogs.income import cmdincome
    return cmdincome(MagicMock(), Database(path=":memory:"))


def _invites_cog():
    from cogs.invitations import cmdinvitations
    return cmdinvitations(MagicMock(), Database(path=":memory:"))


class TestRoleIncomeIsPerPlayer(unittest.TestCase):
    """Le cooldown vivait sur role_income.last_collect, donc partage par le role :
    le premier joueur a collecter bloquait tous les autres porteurs pendant 24h."""

    def setUp(self):
        self.cog = _income_cog()
        self.cog.db.execute(
            "INSERT INTO role_income (role_id, name, amount, collect_interval, last_collect) "
            "VALUES (?, ?, ?, ?, 0)",
            (ROLE, "VIP", 300, 86400),
        )

    def test_nobody_has_collected_initially(self):
        self.assertEqual(self.cog.get_user_last_collect(ROLE, PLAYER), 0)

    def test_one_player_collecting_does_not_block_the_others(self):
        now = time.time()
        self.cog.set_user_last_collect(ROLE, PLAYER, now)
        self.assertAlmostEqual(self.cog.get_user_last_collect(ROLE, PLAYER), now)
        self.assertEqual(self.cog.get_user_last_collect(ROLE, OTHER_PLAYER), 0)

    def test_state_is_per_role_too(self):
        now = time.time()
        self.cog.set_user_last_collect(ROLE, PLAYER, now)
        self.assertEqual(self.cog.get_user_last_collect(999, PLAYER), 0)

    def test_collect_updates_only_that_player(self):
        now = time.time()
        self.cog.set_user_last_collect(ROLE, PLAYER, now)
        self.cog.set_user_last_collect(ROLE, PLAYER, now + 10)
        self.assertAlmostEqual(self.cog.get_user_last_collect(ROLE, PLAYER), now + 10)

    def test_migrated_marker_applies_to_players_without_state(self):
        """La migration pose un repere (user_id 0) pour eviter un double versement."""
        self.cog.db.execute(
            "INSERT OR REPLACE INTO role_income_state (role_id, user_id, last_collect) "
            "VALUES (?, 0, ?)",
            (ROLE, 5000.0),
        )
        self.assertEqual(self.cog.get_user_last_collect(ROLE, PLAYER), 5000.0)


class TestInviteRewards(unittest.TestCase):
    def setUp(self):
        self.cog = _invites_cog()
        for threshold, amount in [(1, 100), (2, 200), (5, 500), (10, 1000)]:
            self.cog.set_reward(GUILD, threshold, amount)

    def _balance(self, user_id):
        row = self.cog.db.fetchone("SELECT amount FROM balances WHERE user_id = ?", (user_id,))
        return row["amount"] if row else 0

    def test_tiers_are_listed_in_order(self):
        self.assertEqual(
            self.cog.list_rewards(GUILD), [(1, 100), (2, 200), (5, 500), (10, 1000)]
        )

    def test_only_reached_tiers_are_due(self):
        due = self.cog.pending_rewards(GUILD, PLAYER, invited=2)
        self.assertEqual(due, [(1, 100), (2, 200)])

    def test_granting_credits_every_reached_tier_once(self):
        self.assertEqual(self.cog.grant_invite_rewards(GUILD, PLAYER, 5), 800)
        self.assertEqual(self._balance(PLAYER), 800)
        self.assertEqual(self.cog.grant_invite_rewards(GUILD, PLAYER, 5), 0)
        self.assertEqual(self._balance(PLAYER), 800)

    def test_new_tier_pays_the_difference_only(self):
        self.cog.grant_invite_rewards(GUILD, PLAYER, 5)
        self.assertEqual(self.cog.grant_invite_rewards(GUILD, PLAYER, 10), 1000)
        self.assertEqual(self._balance(PLAYER), 1800)

    def test_tiers_are_per_guild(self):
        self.assertEqual(self.cog.list_rewards(999), [])
        self.assertEqual(self.cog.grant_invite_rewards(999, PLAYER, 100), 0)

    def test_updating_a_tier_replaces_its_amount(self):
        self.cog.set_reward(GUILD, 5, 750)
        self.assertIn((5, 750), self.cog.list_rewards(GUILD))

    def test_removing_a_tier(self):
        self.assertTrue(self.cog.remove_reward(GUILD, 5))
        self.assertFalse(self.cog.remove_reward(GUILD, 5))
        self.assertNotIn(5, [t for t, _ in self.cog.list_rewards(GUILD)])

    def test_transaction_is_logged(self):
        self.cog.grant_invite_rewards(GUILD, PLAYER, 1)
        row = self.cog.db.fetchone(
            "SELECT kind, amount FROM transactions WHERE user_id = ?", (PLAYER,)
        )
        self.assertEqual(row["kind"], "invite")
        self.assertEqual(row["amount"], 100)


class TestStartingBalance(unittest.TestCase):
    def setUp(self):
        from cogs.economie import cmdeco
        self.cog = cmdeco(MagicMock(), Database(path=":memory:"))

    def test_defaults_to_disabled(self):
        self.assertEqual(self.cog.get_eco_config(GUILD)["starting_balance"], 0)

    def test_configured_amount_is_read_back(self):
        self.cog.get_eco_config(GUILD)
        self.cog.db.execute(
            "UPDATE economy_config SET starting_balance = ? WHERE guild_id = ?", (100, GUILD)
        )
        self.assertEqual(self.cog.get_eco_config(GUILD)["starting_balance"], 100)
