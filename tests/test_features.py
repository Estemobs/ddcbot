import time
import unittest
from unittest.mock import MagicMock

from data.db import Database
from cogs.animations import cmdanim
from cogs.work import cmdwork
from cogs.i18n import resolve_lang, t
from cogs.leveling import cmdleveling, level_from_xp


def _make_cog(cog_cls, **kwargs):
    bot = MagicMock()
    db = Database(path=":memory:")
    return cog_cls(bot, db)


class TestGiveawaysDB(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog(cmdanim)

    def test_create_and_fetch_active(self):
        giveaway_id = self.cog.create_giveaway(1, 2, 3, "Nitro", time.time() + 1000, 9)
        active = self.cog.get_active_giveaway_by_guild(1)
        self.assertIsNotNone(active)
        self.assertEqual(active["prize"], "Nitro")
        self.assertEqual(active["id"], giveaway_id)

    def test_entries_dedupe(self):
        giveaway_id = self.cog.create_giveaway(1, 2, 3, "Nitro", time.time() + 1000, 9)
        self.cog.add_entry(giveaway_id, 100)
        self.cog.add_entry(giveaway_id, 100)
        self.cog.add_entry(giveaway_id, 200)
        self.assertEqual(sorted(self.cog.list_entries(giveaway_id)), [100, 200])

    def test_mark_ended_hides_giveaway(self):
        giveaway_id = self.cog.create_giveaway(1, 2, 3, "Nitro", time.time() + 1000, 9)
        self.cog.mark_ended(giveaway_id)
        self.assertIsNone(self.cog.get_active_giveaway_by_guild(1))

    def test_expired_list(self):
        self.cog.create_giveaway(1, 2, 3, "Nitro", time.time() - 10, 9)
        expired = self.cog.list_expired_giveaways(time.time())
        self.assertEqual(len(expired), 1)

    def test_no_giveaway_on_other_guild(self):
        self.cog.create_giveaway(1, 2, 3, "Nitro", time.time() + 1000, 9)
        self.assertIsNone(self.cog.get_active_giveaway_by_guild(2))


class TestWorkPerGuild(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog(cmdwork)

    def test_settings_are_per_guild(self):
        self.cog.set_work_settings(1, 10, 100, 3, 3600, [5, 10, 20])
        self.cog.set_work_settings(2, 1, 5, 1, 7200, [0])
        settings_1 = self.cog.get_work_settings(1)
        settings_2 = self.cog.get_work_settings(2)
        self.assertEqual(settings_1["min_amount"], 10)
        self.assertEqual(settings_2["min_amount"], 1)
        self.assertEqual(settings_1["cooldown"], 3600)
        self.assertEqual(settings_2["cooldown"], 7200)

    def test_work_state_is_per_guild_and_user(self):
        self.cog.record_work(1, 100, 123.0)
        self.cog.record_work(2, 100, 456.0)
        self.cog.record_work(1, 100, 789.0)
        state = self.cog.get_work_state(1, 100)
        self.assertEqual(state["work_count"], 2)
        state_other = self.cog.get_work_state(2, 100)
        self.assertEqual(state_other["work_count"], 1)


class TestI18n(unittest.TestCase):
    def setUp(self):
        self.db = Database(path=":memory:")

    def test_default_is_french(self):
        self.assertEqual(resolve_lang(self.db), "fr")

    def test_guild_lang_overrides_user_lang(self):
        self.db.execute("INSERT INTO guild_lang (guild_id, lang) VALUES (1, 'en')")
        self.db.execute("INSERT INTO user_lang (user_id, lang) VALUES (2, 'fr')")
        self.assertEqual(resolve_lang(self.db, guild_id=1, user_id=2), "en")

    def test_user_lang_fallback(self):
        self.db.execute("INSERT INTO user_lang (user_id, lang) VALUES (2, 'en')")
        self.assertEqual(resolve_lang(self.db, guild_id=5, user_id=2), "en")

    def test_translation_fr_en(self):
        self.assertEqual(t(self.db, "lang_changed", user_id=2, lang="en"), "Langue définie sur **en**.")
        self.db.execute("INSERT INTO user_lang (user_id, lang) VALUES (2, 'en')")
        self.assertEqual(t(self.db, "lang_changed", user_id=2, lang="en"), "Language set to **en**.")

    def test_unknown_key_falls_back_to_key(self):
        self.assertEqual(t(self.db, "cle_inconnue"), "cle_inconnue")


class TestLeveling(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog(cmdleveling)

    def test_level_formula(self):
        self.assertEqual(level_from_xp(0), 1)
        self.assertEqual(level_from_xp(99), 1)
        self.assertEqual(level_from_xp(100), 2)
        self.assertEqual(level_from_xp(250), 3)

    def test_add_xp_accumulates(self):
        self.cog.add_xp(42, 50)
        self.cog.add_xp(42, 50)
        self.assertEqual(self.cog.get_xp(42), 100)

    def test_config_defaults_created(self):
        cfg = self.cog.get_config(1)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["xp_per_message"], 15)


class TestTransactionLogging(unittest.TestCase):
    def test_log_transaction_stores_row(self):
        db = Database(path=":memory:")
        db.log_transaction(1, 42, 100.0, "work", "bonus=0")
        db.log_transaction(1, 42, -20.0, "transfer", "vers autre")
        rows = db.fetchall(
            "SELECT amount, kind, detail FROM transactions WHERE user_id = 42 ORDER BY id"
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["kind"], "work")
        self.assertEqual(rows[1]["amount"], -20.0)


if __name__ == "__main__":
    unittest.main()
