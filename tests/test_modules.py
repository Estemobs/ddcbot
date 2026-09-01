import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import datetime as dt
import unittest
from unittest.mock import MagicMock

from data.db import Database
from cogs.birthdays import (
    age_on, days_until, format_birthday, parse_birthday, cmdbirthdays,
)
from cogs.tempvoice import cmdtempvoice
from cogs.statschannels import cmdstatschannels, KINDS

GUILD = 111
OTHER = 222
PLAYER = 42


# ── Anniversaires ────────────────────────────────────────────────────────────

class TestParseBirthday(unittest.TestCase):
    def test_common_formats(self):
        for text in ("24/12", "24-12", "24.12", "4/2", "04/02"):
            with self.subTest(text=text):
                self.assertIsNotNone(parse_birthday(text))

    def test_day_month_year(self):
        self.assertEqual(parse_birthday("24/12/2001"), (24, 12, 2001))

    def test_year_is_optional(self):
        self.assertEqual(parse_birthday("24/12"), (24, 12, None))

    def test_29_february_is_accepted_without_a_year(self):
        """C'est une date valide, simplement rare : la refuser serait un bug."""
        self.assertEqual(parse_birthday("29/02"), (29, 2, None))

    def test_impossible_dates_are_refused(self):
        for text in ("32/01", "01/13", "31/02", "0/5", "", "demain", "12"):
            with self.subTest(text=text):
                self.assertIsNone(parse_birthday(text))

    def test_absurd_years_are_refused(self):
        self.assertIsNone(parse_birthday("24/12/1500"))
        self.assertIsNone(parse_birthday("24/12/3000"))


class TestBirthdayHelpers(unittest.TestCase):
    def test_format_with_and_without_year(self):
        self.assertEqual(format_birthday(24, 12), "24 decembre")
        self.assertEqual(format_birthday(1, 1, 2001), "1 janvier 2001")

    def test_age_is_none_without_a_year(self):
        self.assertIsNone(age_on(24, 12, None, dt.date(2026, 12, 24)))

    def test_age_on_the_day(self):
        self.assertEqual(age_on(24, 12, 2001, dt.date(2026, 12, 24)), 25)

    def test_days_until_today_is_zero(self):
        self.assertEqual(days_until(24, 12, dt.date(2026, 12, 24)), 0)

    def test_days_until_wraps_to_next_year(self):
        self.assertEqual(days_until(1, 1, dt.date(2026, 12, 31)), 1)

    def test_29_february_falls_back_to_march_first(self):
        """2027 n'est pas bissextile : l'anniversaire tombe le 1er mars."""
        self.assertEqual(days_until(29, 2, dt.date(2027, 3, 1)), 0)


class TestBirthdayStorage(unittest.TestCase):
    def setUp(self):
        self.cog = cmdbirthdays(MagicMock(), Database(path=":memory:"))

    def test_round_trip(self):
        self.cog.set_birthday(GUILD, PLAYER, 24, 12, 2001)
        self.assertEqual(self.cog.get_birthday(GUILD, PLAYER),
                         {"day": 24, "month": 12, "year": 2001})

    def test_registering_twice_updates(self):
        self.cog.set_birthday(GUILD, PLAYER, 24, 12)
        self.cog.set_birthday(GUILD, PLAYER, 1, 1, 1990)
        self.assertEqual(self.cog.get_birthday(GUILD, PLAYER),
                         {"day": 1, "month": 1, "year": 1990})

    def test_birthdays_are_per_guild(self):
        self.cog.set_birthday(GUILD, PLAYER, 24, 12)
        self.assertIsNone(self.cog.get_birthday(OTHER, PLAYER))

    def test_delete(self):
        self.cog.set_birthday(GUILD, PLAYER, 24, 12)
        self.assertTrue(self.cog.delete_birthday(GUILD, PLAYER))
        self.assertFalse(self.cog.delete_birthday(GUILD, PLAYER))

    def test_lookup_by_date(self):
        self.cog.set_birthday(GUILD, PLAYER, 24, 12)
        self.cog.set_birthday(GUILD, 43, 24, 12)
        self.cog.set_birthday(GUILD, 44, 25, 12)
        self.assertEqual({e["user_id"] for e in self.cog.birthdays_on(GUILD, 24, 12)},
                         {PLAYER, 43})

    def test_upcoming_is_sorted_by_proximity(self):
        today = dt.date(2026, 6, 15)
        self.cog.set_birthday(GUILD, 1, 20, 6)   # dans 5 jours
        self.cog.set_birthday(GUILD, 2, 15, 6)   # aujourd'hui
        self.cog.set_birthday(GUILD, 3, 1, 6)    # l'an prochain
        self.assertEqual([e["user_id"] for e in self.cog.upcoming(GUILD, today)], [2, 1, 3])

    def test_announcement_is_recorded_once_per_day(self):
        self.assertFalse(self.cog.already_announced(GUILD, PLAYER, "2026-12-24"))
        self.cog.mark_announced(GUILD, PLAYER, "2026-12-24")
        self.assertTrue(self.cog.already_announced(GUILD, PLAYER, "2026-12-24"))
        self.assertFalse(self.cog.already_announced(GUILD, PLAYER, "2026-12-25"))

    def test_previous_days_are_listed_for_role_removal(self):
        self.cog.mark_announced(GUILD, PLAYER, "2026-12-24")
        self.assertEqual(self.cog.announced_before(GUILD, "2026-12-25"), [PLAYER])
        self.cog.clear_announced_before(GUILD, "2026-12-25")
        self.assertEqual(self.cog.announced_before(GUILD, "2026-12-25"), [])


# ── Vocaux temporaires ───────────────────────────────────────────────────────

class TestTempVoice(unittest.TestCase):
    def setUp(self):
        self.cog = cmdtempvoice(MagicMock(), Database(path=":memory:"))

    def test_defaults(self):
        cfg = self.cog.get_config(GUILD)
        self.assertIsNone(cfg["hub_channel_id"])
        self.assertEqual(cfg["name_template"], "Salon de {user}")

    def test_config_round_trip(self):
        self.cog.set_config(GUILD, hub_channel_id=7, user_limit=5)
        cfg = self.cog.get_config(GUILD)
        self.assertEqual((cfg["hub_channel_id"], cfg["user_limit"]), (7, 5))

    def test_unknown_field_is_ignored(self):
        self.cog.set_config(GUILD, nimporte_quoi=1)
        self.assertIsNone(self.cog.get_config(GUILD)["hub_channel_id"])

    def test_channel_registry(self):
        self.cog.register(900, GUILD, PLAYER)
        self.assertTrue(self.cog.is_temp(900))
        self.assertEqual(self.cog.owner_of(900), PLAYER)
        self.cog.forget(900)
        self.assertFalse(self.cog.is_temp(900))

    def test_registry_is_per_guild(self):
        self.cog.register(900, GUILD, PLAYER)
        self.assertEqual(self.cog.list_channels(OTHER), [])

    def test_name_template_substitutes_variables(self):
        member = MagicMock()
        member.display_name = "estemobs"
        self.assertEqual(self.cog.render_name("Salon de {user}", member), "Salon de estemobs")
        self.assertEqual(self.cog.render_name("{user} ({count})", member, 3), "estemobs (3)")

    def test_name_is_truncated_to_discords_limit(self):
        member = MagicMock()
        member.display_name = "x" * 200
        self.assertEqual(len(self.cog.render_name("{user}", member)), 100)

    def test_empty_template_falls_back(self):
        member = MagicMock()
        member.display_name = "estemobs"
        self.assertEqual(self.cog.render_name("", member), "Salon de estemobs")


# ── Salons de statistiques ───────────────────────────────────────────────────

def _fake_guild(members=10, bots=2, roles=3, channels=5, boosts=1, name="Serveur"):
    guild = MagicMock()
    guild.name = name
    guild.member_count = members
    guild.premium_subscription_count = boosts
    guild.roles = list(range(roles))
    guild.channels = list(range(channels))
    people = []
    for i in range(members):
        member = MagicMock()
        member.bot = i < bots
        member.status = "online" if i % 2 == 0 else "offline"
        people.append(member)
    guild.members = people
    return guild


class TestStatsChannels(unittest.TestCase):
    def setUp(self):
        self.cog = cmdstatschannels(MagicMock(), Database(path=":memory:"))
        self.guild = _fake_guild()

    def test_every_kind_computes_a_number(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                entry = {"kind": kind, "template": "{label} : {value}", "role_id": None}
                value = self.cog.compute(self.guild, entry)
                self.assertIsInstance(value, int)

    def test_humans_excludes_bots(self):
        entry = {"kind": "humans", "template": "", "role_id": None}
        self.assertEqual(self.cog.compute(self.guild, entry), 8)

    def test_bots_are_counted(self):
        entry = {"kind": "bots", "template": "", "role_id": None}
        self.assertEqual(self.cog.compute(self.guild, entry), 2)

    def test_unknown_kind_yields_none(self):
        entry = {"kind": "inexistant", "template": "", "role_id": None}
        self.assertIsNone(self.cog.compute(self.guild, entry))

    def test_role_kind_without_role_counts_zero(self):
        self.guild.get_role.return_value = None
        entry = {"kind": "role", "template": "", "role_id": 5}
        self.assertEqual(self.cog.compute(self.guild, entry), 0)

    def test_render_substitutes_label_and_value(self):
        entry = {"kind": "members", "template": "{label} : {value}", "role_id": None}
        self.assertEqual(self.cog.render(self.guild, entry), "Membres : 10")

    def test_render_supports_a_free_template(self):
        entry = {"kind": "members", "template": "👥 {value} membres", "role_id": None}
        self.assertEqual(self.cog.render(self.guild, entry), "👥 10 membres")

    def test_render_truncates_to_discords_limit(self):
        entry = {"kind": "members", "template": "x" * 200, "role_id": None}
        self.assertEqual(len(self.cog.render(self.guild, entry)), 100)

    def test_registry_round_trip(self):
        self.cog.add_channel(GUILD, 900, "members")
        entries = self.cog.list_channels(GUILD)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["kind"], "members")
        self.assertTrue(self.cog.remove_channel(900))
        self.assertEqual(self.cog.list_channels(GUILD), [])

    def test_adding_the_same_channel_twice_updates_it(self):
        self.cog.add_channel(GUILD, 900, "members")
        self.cog.add_channel(GUILD, 900, "bots")
        entries = self.cog.list_channels(GUILD)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["kind"], "bots")

    def test_registry_is_per_guild(self):
        self.cog.add_channel(GUILD, 900, "members")
        self.assertEqual(self.cog.list_channels(OTHER), [])

    def test_last_value_is_remembered_to_avoid_useless_renames(self):
        """Discord limite a 2 renommages / 10 min : on n'ecrit que si ca change."""
        self.cog.add_channel(GUILD, 900, "members")
        self.cog.remember(900, "Membres : 10", 1234.0)
        self.assertEqual(self.cog.list_channels(GUILD)[0]["last_value"], "Membres : 10")


if __name__ == "__main__":
    unittest.main()
