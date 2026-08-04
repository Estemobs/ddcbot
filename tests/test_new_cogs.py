import unittest
import time
from unittest.mock import MagicMock, AsyncMock

from data.db import Database


def _make_db():
    return Database(path=":memory:")


def _make_bot():
    bot = MagicMock()
    bot.commands = []
    bot.cogs = {}
    bot.get_cog = MagicMock(return_value=None)
    return bot


class TestAIModeration(unittest.TestCase):
    def setUp(self):
        from cogs.ai_moderation import cmdaimoderation
        self.db = _make_db()
        self.bot = _make_bot()
        self.cog = cmdaimoderation(self.bot, self.db)

    def test_get_config_creates_default(self):
        cfg = self.cog.get_config(123456)
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["action"], "warn")
        self.assertEqual(cfg["threshold"], 0.7)
        self.assertEqual(cfg["cooldown_seconds"], 10)

    def test_save_config(self):
        self.cog.save_config(123456, enabled=True, threshold=0.5)
        cfg = self.cog.get_config(123456)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["threshold"], 0.5)

    def test_ignored_roles(self):
        self.cog.add_ignored_role(123456, 111)
        self.cog.add_ignored_role(123456, 222)
        roles = self.cog.get_ignored_roles(123456)
        self.assertIn(111, roles)
        self.assertIn(222, roles)
        self.cog.remove_ignored_role(123456, 111)
        roles = self.cog.get_ignored_roles(123456)
        self.assertNotIn(111, roles)
        self.assertIn(222, roles)

    def test_cooldown_prevents_duplicate_checks(self):
        self.cog._last_check[(123456, 777)] = time.time()
        self.assertIn((123456, 777), self.cog._last_check)


class TestTickets(unittest.TestCase):
    def setUp(self):
        from cogs.tickets import cmdtickets
        self.db = _make_db()
        self.bot = _make_bot()
        self.cog = cmdtickets(self.bot, self.db)

    def test_get_config_creates_default(self):
        cfg = self.cog.get_config(123456)
        self.assertFalse(cfg["enabled"])
        self.assertIsNone(cfg["category_id"])
        self.assertEqual(cfg["max_open_tickets"], 5)

    def test_save_config(self):
        self.cog.save_config(123456, enabled=True, max_open_tickets=3)
        cfg = self.cog.get_config(123456)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["max_open_tickets"], 3)

    def test_create_and_close_ticket(self):
        self.cog.create_ticket_record(123456, 777, 888)
        count = self.cog.get_open_count(123456, 777)
        self.assertEqual(count, 1)
        self.cog.close_ticket(888)
        count = self.cog.get_open_count(123456, 777)
        self.assertEqual(count, 0)

    def test_ticket_counter_increments(self):
        self.cog.create_ticket_record(123456, 777, 888)
        num = self.cog.get_ticket_number(123456)
        self.assertGreater(num, 0)


class TestWebhooks(unittest.TestCase):
    def setUp(self):
        from cogs.webhooks import cmdwebhooks
        self.db = _make_db()
        self.bot = _make_bot()
        self.cog = cmdwebhooks(self.bot, self.db)

    def test_get_config_creates_default(self):
        cfg = self.cog.get_config(123456)
        self.assertFalse(cfg["enabled"])
        self.assertIsNone(cfg["webhook_url"])
        self.assertIn("member_join", cfg["events"])

    def test_save_config(self):
        self.cog.save_config(123456, enabled=True, webhook_url="https://example.com/hook")
        cfg = self.cog.get_config(123456)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["webhook_url"], "https://example.com/hook")

    def test_events_toggle(self):
        cfg = self.cog.get_config(123456)
        self.assertTrue(cfg["events"]["member_join"])
        events = cfg["events"]
        events["member_join"] = False
        self.cog.save_config(123456, events_json=events)
        cfg2 = self.cog.get_config(123456)
        self.assertFalse(cfg2["events"]["member_join"])


class TestLockdown(unittest.TestCase):
    def setUp(self):
        from cogs.lockdown import cmdlockdown
        self.db = _make_db()
        self.bot = _make_bot()
        self.cog = cmdlockdown(self.bot, self.db)

    def test_get_config_creates_default(self):
        cfg = self.cog.get_config(123456)
        self.assertIsNone(cfg["lockdown_role_id"])
        self.assertIsNone(cfg["log_channel_id"])
        self.assertFalse(cfg["auto_lockon_mass_join"])
        self.assertEqual(cfg["mass_join_threshold"], 10)
        self.assertEqual(cfg["mass_join_window_seconds"], 60)

    def test_save_config(self):
        self.cog.save_config(123456, mass_join_threshold=20, auto_lockon_mass_join=True)
        cfg = self.cog.get_config(123456)
        self.assertEqual(cfg["mass_join_threshold"], 20)
        self.assertTrue(cfg["auto_lockon_mass_join"])

    def test_join_tracker(self):
        self.cog._join_tracker[123456] = [time.time() - 5, time.time() - 3, time.time()]
        self.assertEqual(len(self.cog._join_tracker[123456]), 3)


if __name__ == "__main__":
    unittest.main()
