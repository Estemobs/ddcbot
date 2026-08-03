import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from data.db import Database
from cogs.invitations import cmdinvitations


def _make_cog():
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdinvitations(bot, db)


class TestInvitationsDB(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_stats_default_to_zero(self):
        self.assertEqual(self.cog.get_stats(1, 100), {"invited": 0, "left": 0})

    def test_add_invite_roundtrip(self):
        self.cog.add_invite(1, 100)
        self.cog.add_invite(1, 100)
        self.assertEqual(self.cog.get_stats(1, 100)["invited"], 2)

    def test_stats_are_per_guild(self):
        self.cog.add_invite(1, 100)
        self.assertEqual(self.cog.get_stats(2, 100)["invited"], 0)

    def test_add_left(self):
        self.cog.add_invite(1, 100, delta=3)
        self.cog.add_left(1, 100)
        self.assertEqual(self.cog.get_stats(1, 100)["left"], 1)

    def test_top_inviters_sorted(self):
        self.cog.add_invite(1, 100)
        self.cog.add_invite(1, 200, delta=5)
        self.cog.add_invite(1, 300, delta=2)
        top = self.cog.top_inviters(1, 3)
        self.assertEqual([uid for uid, _ in top], [200, 300, 100])

    def test_top_inviters_limited(self):
        self.cog.add_invite(1, 100)
        self.cog.add_invite(1, 200)
        self.assertEqual(len(self.cog.top_inviters(1, 1)), 1)

    def test_invites_table_exists(self):
        row = self.cog.db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'invites'"
        )
        self.assertIsNotNone(row)


class TestInvitationsEvents(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_on_member_join_credits_inviter(self):
        inviter = MagicMock()
        inviter.bot = False
        inviter.id = 100
        invite = MagicMock()
        invite.code = "abc"
        invite.uses = 2
        invite.inviter = inviter

        guild = MagicMock()
        guild.id = 1
        guild.invites = AsyncMock(return_value=[invite])

        member = MagicMock()
        member.guild = guild

        self.cog._invite_cache[1] = {"abc": 1}
        asyncio.run(self.cog.on_member_join(member))
        self.assertEqual(self.cog.get_stats(1, 100)["invited"], 1)

    def test_on_member_join_ignores_bot_inviter(self):
        inviter = MagicMock()
        inviter.bot = True
        inviter.id = 100
        invite = MagicMock()
        invite.code = "abc"
        invite.uses = 2
        invite.inviter = inviter

        guild = MagicMock()
        guild.id = 1
        guild.invites = AsyncMock(return_value=[invite])

        member = MagicMock()
        member.guild = guild

        self.cog._invite_cache[1] = {"abc": 1}
        asyncio.run(self.cog.on_member_join(member))
        self.assertEqual(self.cog.get_stats(1, 100)["invited"], 0)

    def test_on_member_join_without_cache(self):
        member = MagicMock()
        member.guild = MagicMock()
        self.cog._invite_cache = {}
        asyncio.run(self.cog.on_member_join(member))
        self.assertEqual(self.cog.get_stats(1, 100)["invited"], 0)


if __name__ == "__main__":
    unittest.main()
