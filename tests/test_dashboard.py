import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest

# Pointe la base du dashboard vers une base en memoire AVANT l'import du module.
os.environ["DDC_DB_PATH"] = ":memory:"

from fastapi.testclient import TestClient  # noqa: E402
import web_dashboard.main as dashboard  # noqa: E402

from data.db import Database  # noqa: E402

GUILD = 12345


def _fresh_db():
    return Database(path=":memory:")


def _seed_six_pages(db):
    db.execute(
        "INSERT INTO invites (guild_id, user_id, invited, left) VALUES (?, ?, ?, ?)",
        (GUILD, 111, 5, 1),
    )
    db.execute(
        "INSERT INTO work_settings (guild_id, min_amount, max_amount, reward_tiers, cooldown, rewards_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (GUILD, 10, 100, 3, 4, "[]"),
    )
    db.execute(
        "INSERT INTO income_config (guild_id, collect_enabled, default_amount, default_interval_hours) "
        "VALUES (?, ?, ?, ?)",
        (GUILD, 1, 50, 24),
    )
    db.execute(
        "INSERT INTO minecraft_config (guild_id, channel_id, method, tmux_session, use_sudo, enabled) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (GUILD, 999, "tmux", "mc", 0, 1),
    )
    db.execute(
        "INSERT INTO steam_config (guild_id, api_key) VALUES (?, ?)",
        (GUILD, "STEAM_KEY_TEST"),
    )
    db.execute(
        "INSERT INTO notifications (show_name, season, number, airdate, user_id) VALUES (?, ?, ?, ?, ?)",
        ("Ma Serie", 1, 2, "2026-08-08", 111),
    )
    db.execute(
        "INSERT INTO guild_lang (guild_id, lang) VALUES (?, ?)",
        (GUILD, "fr"),
    )


class TestDashboardSixNewPages(unittest.TestCase):
    def setUp(self):
        self._old_db = dashboard.db
        dashboard.db = _fresh_db()
        _seed_six_pages(dashboard.db)
        self.client = TestClient(dashboard.app)

    def tearDown(self):
        dashboard.db = self._old_db

    def test_invitations_page(self):
        resp = self.client.get(f"/guild/{GUILD}/invitations")
        self.assertEqual(resp.status_code, 200)
        body = resp.text
        self.assertIn("111", body)
        self.assertIn("Invitations", body)

    def test_minecraft_page(self):
        resp = self.client.get(f"/guild/{GUILD}/minecraft")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("tmux", resp.text)

    def test_steam_page_advertises_no_api_key(self):
        resp = self.client.get(f"/guild/{GUILD}/steam")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Sans cle d&#39;API", resp.text)
        self.assertNotIn('name="api_key"', resp.text)

    def test_work_income_page(self):
        resp = self.client.get(f"/guild/{GUILD}/work")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Travail", resp.text)
        self.assertIn("10", resp.text)

    def test_rss_page(self):
        resp = self.client.get(f"/guild/{GUILD}/rss")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Ma Serie", resp.text)

    def test_lang_page(self):
        resp = self.client.get(f"/guild/{GUILD}/lang")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Francais", resp.text)

    def test_all_pages_return_200(self):
        for path in [
            "/",
            f"/guild/{GUILD}", f"/guild/{GUILD}/economy",
            f"/guild/{GUILD}/moderation", f"/guild/{GUILD}/leveling",
            f"/guild/{GUILD}/welcome", f"/guild/{GUILD}/automod",
            f"/guild/{GUILD}/logs", f"/guild/{GUILD}/aimod",
            f"/guild/{GUILD}/tickets", f"/guild/{GUILD}/webhooks",
            f"/guild/{GUILD}/lockdown", f"/guild/{GUILD}/invitations",
            f"/guild/{GUILD}/minecraft", f"/guild/{GUILD}/steam",
            f"/guild/{GUILD}/work", f"/guild/{GUILD}/rss",
            f"/guild/{GUILD}/lang", f"/guild/{GUILD}/notes",
            f"/guild/{GUILD}/transactions", f"/guild/{GUILD}/reminders",
            f"/guild/{GUILD}/giveaways", f"/guild/{GUILD}/casino",
            f"/guild/{GUILD}/twitch", f"/guild/{GUILD}/birthdays",
            f"/guild/{GUILD}/tempvoice", f"/guild/{GUILD}/statschannels",
        ]:
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 200, path)


class TestDashboardAPI(unittest.TestCase):
    def setUp(self):
        self._old_db = dashboard.db
        dashboard.db = _fresh_db()
        _seed_six_pages(dashboard.db)
        self.client = TestClient(dashboard.app)

    def tearDown(self):
        dashboard.db = self._old_db

    def test_api_guilds(self):
        resp = self.client.get("/api/guilds")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(GUILD, resp.json()["guilds"])

    def test_api_stats(self):
        resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("guilds", data)
        self.assertEqual(data["guilds"], 1)

    def test_api_invitations(self):
        resp = self.client.get(f"/api/guild/{GUILD}/invitations")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_invited"], 5)
        self.assertEqual(data["total_active"], 4)

    def test_api_minecraft(self):
        resp = self.client.get(f"/api/guild/{GUILD}/minecraft")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["config"]["method"], "tmux")

    def test_api_steam(self):
        resp = self.client.get(f"/api/guild/{GUILD}/steam")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["config"]["api_key"], "STEAM_KEY_TEST")

    def test_api_work(self):
        resp = self.client.get(f"/api/guild/{GUILD}/work")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["config"]["min_amount"], 10)

    def test_api_income(self):
        resp = self.client.get(f"/api/guild/{GUILD}/income")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["config"]["default_amount"], 50)

    def test_api_rss(self):
        resp = self.client.get(f"/api/guild/{GUILD}/rss")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["notifications"][0]["show_name"], "Ma Serie")

    def test_api_lang(self):
        resp = self.client.get(f"/api/guild/{GUILD}/lang")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["config"]["lang"], "fr")

    def test_api_unknown_guild_empty(self):
        resp = self.client.get("/api/guild/999999/leveling")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["config"])
        self.assertEqual(resp.json()["levels"], [])

    def test_api_global_endpoints(self):
        for path in ["/api/transactions", "/api/reminders", "/api/giveaways", "/api/notes"]:
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 200)


class TestDashboardConfigPosts(unittest.TestCase):
    def setUp(self):
        self._old_db = dashboard.db
        dashboard.db = _fresh_db()
        self.client = TestClient(dashboard.app, follow_redirects=False)

    def tearDown(self):
        dashboard.db = self._old_db

    def test_economy_config_upsert(self):
        resp = self.client.post(
            f"/guild/{GUILD}/economy/config",
            data={"allow_transfers": "1", "max_transfer": "5000", "allow_negative": "0"},
        )
        self.assertEqual(resp.status_code, 303)
        row = dashboard.db.fetchone(
            "SELECT * FROM economy_config WHERE guild_id = ?", (GUILD,)
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["max_transfer"], 5000)

    def test_work_config_upsert(self):
        resp = self.client.post(
            f"/guild/{GUILD}/work/config",
            data={"min_amount": "20", "max_amount": "200", "reward_tiers": "5", "cooldown": "2"},
        )
        self.assertEqual(resp.status_code, 303)
        row = dashboard.db.fetchone(
            "SELECT * FROM work_settings WHERE guild_id = ?", (GUILD,)
        )
        self.assertEqual(row["max_amount"], 200)

    def test_notes_add_delete(self):
        resp = self.client.post(
            f"/guild/{GUILD}/notes/add", data={"title": "TitreTest", "content": "Contenu"}
        )
        self.assertEqual(resp.status_code, 303)
        row = dashboard.db.fetchone(
            "SELECT * FROM notes WHERE guild_id = ? AND title = 'TitreTest'", (GUILD,)
        )
        self.assertIsNotNone(row)
        resp = self.client.post(
            f"/guild/{GUILD}/notes/delete", data={"title": "TitreTest", "scope": str(GUILD)}
        )
        self.assertEqual(resp.status_code, 303)
        row = dashboard.db.fetchone(
            "SELECT * FROM notes WHERE guild_id = ? AND title = 'TitreTest'", (GUILD,)
        )
        self.assertIsNone(row)


class TestGuildIdentity(unittest.TestCase):
    """Nom et logo des serveurs, alimentes par le bot dans guild_meta."""

    def setUp(self):
        self._old_db = dashboard.db
        dashboard.db = _fresh_db()
        dashboard.db.execute(
            "INSERT INTO economy_config (guild_id) VALUES (?)", (GUILD,)
        )
        self.client = TestClient(dashboard.app, follow_redirects=False)

    def tearDown(self):
        dashboard.db = self._old_db

    def _set_meta(self, name, icon_url, members):
        dashboard.db.execute(
            "INSERT INTO guild_meta (guild_id, name, icon_url, member_count) VALUES (?, ?, ?, ?)",
            (GUILD, name, icon_url, members),
        )

    def test_falls_back_to_id_without_meta(self):
        resp = self.client.get(f"/guild/{GUILD}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(str(GUILD), resp.text)

    def test_shows_name_icon_and_member_count(self):
        self._set_meta("Mon Serveur", "https://cdn.example/icon.png", 42)
        resp = self.client.get(f"/guild/{GUILD}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Mon Serveur", resp.text)
        self.assertIn("https://cdn.example/icon.png", resp.text)
        self.assertIn("42 membres", resp.text)

    def test_name_shown_on_home_page(self):
        self._set_meta("Mon Serveur", None, 0)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Mon Serveur", resp.text)

    def test_guild_known_from_meta_alone(self):
        dashboard.db.execute(
            "INSERT INTO guild_meta (guild_id, name) VALUES (?, ?)", (777, "Sans Config")
        )
        self.assertIn(777, dashboard.get_guilds())


class TestPerGuildNotes(unittest.TestCase):
    """Les notes heritees (guild_id 0) restent visibles depuis chaque serveur."""

    def setUp(self):
        self._old_db = dashboard.db
        dashboard.db = _fresh_db()
        dashboard.db.execute("INSERT INTO economy_config (guild_id) VALUES (?)", (GUILD,))
        dashboard.db.execute(
            "INSERT INTO notes (guild_id, title, content) VALUES (0, 'ancienne', 'globale')"
        )
        dashboard.db.execute(
            "INSERT INTO notes (guild_id, title, content) VALUES (?, 'locale', 'du serveur')",
            (GUILD,),
        )
        self.client = TestClient(dashboard.app, follow_redirects=False)

    def tearDown(self):
        dashboard.db = self._old_db

    def test_page_lists_guild_and_legacy_notes(self):
        resp = self.client.get(f"/guild/{GUILD}/notes")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("locale", resp.text)
        self.assertIn("ancienne", resp.text)

    def test_delete_targets_the_requested_scope(self):
        resp = self.client.post(
            f"/guild/{GUILD}/notes/delete", data={"title": "locale", "scope": str(GUILD)}
        )
        self.assertEqual(resp.status_code, 303)
        self.assertIsNotNone(
            dashboard.db.fetchone("SELECT 1 FROM notes WHERE guild_id = 0 AND title = 'ancienne'")
        )
        self.assertIsNone(
            dashboard.db.fetchone(
                "SELECT 1 FROM notes WHERE guild_id = ? AND title = 'locale'", (GUILD,)
            )
        )


class TestCasinoDashboard(unittest.TestCase):
    """L'editeur de jeux : c'est la que le game master configure tout."""

    def setUp(self):
        self._old_db = dashboard.db
        self._old_engine_db = dashboard.casino.db
        dashboard.db = _fresh_db()
        dashboard.casino.db = dashboard.db
        dashboard.db.execute("INSERT INTO economy_config (guild_id) VALUES (?)", (GUILD,))
        self.client = TestClient(dashboard.app, follow_redirects=False)

    def tearDown(self):
        dashboard.db = self._old_db
        dashboard.casino.db = self._old_engine_db

    def test_create_game_normalises_the_name(self):
        resp = self.client.post(f"/guild/{GUILD}/casino/game/add", data={
            "display_name": "Machine Saison 1", "kind": "weighted", "category": "machine",
            "price": "3500", "cooldown_seconds": "0", "description": "",
            "dice": "2", "faces": "6", "win_amount": "0", "lose_amount": "0",
        })
        self.assertEqual(resp.status_code, 303)
        game = dashboard.casino.get_game(GUILD, "machine-saison-1")
        self.assertIsNotNone(game)
        self.assertEqual(game["display_name"], "Machine Saison 1")
        self.assertEqual(game["price"], 3500)

    def test_lot_weight_round_trip(self):
        game_id = dashboard.casino.create_game(GUILD, "machine", price=250)
        self.client.post(f"/guild/{GUILD}/casino/game/{game_id}/lot/add", data={
            "reward_kind": "money", "reward_value": "450", "label": "",
            "weight": "3", "outcome": "",
        })
        lots = dashboard.casino.list_lots(game_id)
        self.assertEqual(len(lots), 1)
        self.assertEqual(lots[0]["weight"], 3)

        self.client.post(f"/guild/{GUILD}/casino/lot/{lots[0]['id']}/edit", data={
            "reward_value": "500", "weight": "9", "game_id": str(game_id),
        })
        self.assertEqual(dashboard.casino.list_lots(game_id)[0]["weight"], 9)

        self.client.post(f"/guild/{GUILD}/casino/lot/{lots[0]['id']}/delete",
                         data={"game_id": str(game_id)})
        self.assertEqual(dashboard.casino.list_lots(game_id), [])

    def test_page_warns_about_games_that_mint_money(self):
        game_id = dashboard.casino.create_game(GUILD, "dieu", display_name="Machine de DIEU",
                                               price=50000)
        for value in (100000, 35000):
            dashboard.casino.add_lot(game_id, "money", value)
        body = self.client.get(f"/guild/{GUILD}/casino").text
        self.assertIn("Machine de DIEU", body)
        self.assertIn("RTP 135", body)

    def test_effects_are_configurable(self):
        resp = self.client.post(f"/guild/{GUILD}/casino/style", data={
            "animations_enabled": "1", "frame_count": "6", "frame_delay_ms": "400",
            "reel_symbols": "🍀,💰,🎲", "reel_width": "4", "suspense_text": "Ça tourne",
            "win_emoji": "🤑", "lose_emoji": "😭", "win_color": "#00FF00",
            "lose_color": "#FF0000", "jackpot_threshold": "50000",
            "jackpot_text": "GROS LOT", "currency_symbol": "$",
        })
        self.assertEqual(resp.status_code, 303)
        style = dashboard.casino.get_style(GUILD)
        self.assertEqual(style["frame_count"], 6)
        self.assertEqual(style["reels"], ["🍀", "💰", "🎲"])
        self.assertEqual(style["jackpot_text"], "GROS LOT")

    def test_quest_creation_and_deletion(self):
        self.client.post(f"/guild/{GUILD}/casino/quest/add", data={
            "name": "Ouvreur de boxs", "goal": "20", "reward_kind": "role",
            "reward_value": "111", "target_kind": "category", "target_value": "box",
            "description": "", "repeatable": "0",
        })
        quests = dashboard.casino.list_quests(GUILD)
        self.assertEqual([q["name"] for q in quests], ["Ouvreur de boxs"])
        self.client.post(f"/guild/{GUILD}/casino/quest/{quests[0]['id']}/delete")
        self.assertEqual(dashboard.casino.list_quests(GUILD), [])

    def test_invite_tiers_round_trip(self):
        self.client.post(f"/guild/{GUILD}/invitations/reward",
                         data={"threshold": "5", "amount": "500"})
        rows = dashboard.db.fetchall(
            "SELECT threshold, amount FROM invite_rewards WHERE guild_id = ?", (GUILD,)
        )
        self.assertEqual([(r["threshold"], r["amount"]) for r in rows], [(5, 500)])
        self.client.post(f"/guild/{GUILD}/invitations/reward/delete", data={"threshold": "5"})
        self.assertEqual(
            dashboard.db.fetchall("SELECT 1 FROM invite_rewards WHERE guild_id = ?", (GUILD,)), []
        )

    def test_starting_balance_is_saved(self):
        self.client.post(f"/guild/{GUILD}/economy/config", data={
            "allow_transfers": "1", "max_transfer": "10000",
            "allow_negative": "0", "starting_balance": "100",
        })
        row = dashboard.db.fetchone(
            "SELECT starting_balance FROM economy_config WHERE guild_id = ?", (GUILD,)
        )
        self.assertEqual(row["starting_balance"], 100)


class TestNewModulePages(unittest.TestCase):
    def setUp(self):
        self._old_db = dashboard.db
        dashboard.db = _fresh_db()
        dashboard.db.execute("INSERT INTO economy_config (guild_id) VALUES (?)", (GUILD,))
        self.client = TestClient(dashboard.app, follow_redirects=False)

    def tearDown(self):
        dashboard.db = self._old_db

    def test_birthday_config_round_trip(self):
        resp = self.client.post(f"/guild/{GUILD}/birthdays/config", data={
            "channel_id": "555", "role_id": "666", "message": "Joyeux anniv {user}",
            "announce_hour": "10", "enabled": "1",
        })
        self.assertEqual(resp.status_code, 303)
        row = dashboard.db.fetchone(
            "SELECT * FROM birthday_config WHERE guild_id = ?", (GUILD,)
        )
        self.assertEqual((row["channel_id"], row["role_id"], row["announce_hour"]),
                         (555, 666, 10))

    def test_birthday_hour_is_clamped(self):
        self.client.post(f"/guild/{GUILD}/birthdays/config", data={
            "channel_id": "", "role_id": "", "message": "x",
            "announce_hour": "99", "enabled": "1",
        })
        row = dashboard.db.fetchone(
            "SELECT announce_hour FROM birthday_config WHERE guild_id = ?", (GUILD,)
        )
        self.assertEqual(row["announce_hour"], 23)

    def test_birthday_delete(self):
        dashboard.db.execute(
            "INSERT INTO birthdays (guild_id, user_id, day, month) VALUES (?, ?, ?, ?)",
            (GUILD, 42, 24, 12),
        )
        self.client.post(f"/guild/{GUILD}/birthdays/delete", data={"user_id": "42"})
        self.assertEqual(
            dashboard.db.fetchall("SELECT 1 FROM birthdays WHERE guild_id = ?", (GUILD,)), []
        )

    def test_tempvoice_config_round_trip(self):
        self.client.post(f"/guild/{GUILD}/tempvoice/config", data={
            "hub_channel_id": "777", "category_id": "888",
            "name_template": "Vocal de {user}", "user_limit": "5", "enabled": "1",
        })
        row = dashboard.db.fetchone(
            "SELECT * FROM tempvoice_config WHERE guild_id = ?", (GUILD,)
        )
        self.assertEqual((row["hub_channel_id"], row["user_limit"]), (777, 5))

    def test_stats_channel_add_and_delete(self):
        self.client.post(f"/guild/{GUILD}/statschannels/add", data={
            "channel_id": "999", "kind": "members",
            "template": "{label} : {value}", "role_id": "",
        })
        rows = dashboard.db.fetchall("SELECT * FROM stats_channels WHERE guild_id = ?", (GUILD,))
        self.assertEqual(len(rows), 1)
        self.client.post(f"/guild/{GUILD}/statschannels/delete", data={"channel_id": "999"})
        self.assertEqual(
            dashboard.db.fetchall("SELECT 1 FROM stats_channels WHERE guild_id = ?", (GUILD,)), []
        )

    def test_unknown_stats_kind_is_rejected(self):
        self.client.post(f"/guild/{GUILD}/statschannels/add", data={
            "channel_id": "999", "kind": "nimportequoi", "template": "x", "role_id": "",
        })
        self.assertEqual(
            dashboard.db.fetchall("SELECT 1 FROM stats_channels WHERE guild_id = ?", (GUILD,)), []
        )


class TestDashboardAuth(unittest.TestCase):
    def setUp(self):
        self._old_db = dashboard.db
        self._old_token = dashboard.DASHBOARD_TOKEN
        self._old_api_key = dashboard.API_KEY
        self._old_sessions = dashboard._sessions
        dashboard.db = _fresh_db()
        dashboard.DASHBOARD_TOKEN = "secret-token"
        dashboard.API_KEY = "api-key-1"
        dashboard._sessions = {}
        dashboard._login_attempts.clear()
        self.client = TestClient(dashboard.app, follow_redirects=False)

    def tearDown(self):
        dashboard.db = self._old_db
        dashboard.DASHBOARD_TOKEN = self._old_token
        dashboard.API_KEY = self._old_api_key
        dashboard._sessions = self._old_sessions
        dashboard._login_attempts.clear()

    def test_page_requires_login(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Token", resp.text)

    def test_api_returns_401_without_auth(self):
        resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 401)

    def test_api_key_header_allows_access(self):
        resp = self.client.get("/api/stats", headers={"X-API-Key": "api-key-1"})
        self.assertEqual(resp.status_code, 200)

    def test_login_success_sets_session(self):
        resp = self.client.post("/login", data={"token": "secret-token"})
        self.assertEqual(resp.status_code, 303)
        self.assertIsNotNone(resp.cookies.get("ddc_session"))
        resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)

    def test_login_wrong_token(self):
        resp = self.client.post("/login", data={"token": "bad"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Token invalide", resp.text)

    def test_login_rate_limit(self):
        for i in range(6):
            self.client.post("/login", data={"token": "bad"})
        resp = self.client.post("/login", data={"token": "bad"})
        self.assertIn("Trop de tentatives", resp.text)


class TestDashboardI18n(unittest.TestCase):
    def setUp(self):
        self._old_db = dashboard.db
        dashboard.db = _fresh_db()
        self.client = TestClient(dashboard.app)

    def tearDown(self):
        dashboard.db = self._old_db

    def test_french_by_default(self):
        resp = self.client.get("/")
        self.assertIn("Accueil", resp.text)

    def test_english_via_query_param(self):
        resp = self.client.get("/?lang=en")
        self.assertIn("Home", resp.text)
        self.assertNotIn("Accueil", resp.text)

    def test_english_via_cookie(self):
        self.client.cookies.set("dash_lang", "en")
        resp = self.client.get("/")
        self.assertIn("Home", resp.text)

    def test_guild_page_translation(self):
        resp = self.client.get(f"/guild/{GUILD}/economy?lang=en")
        self.assertIn("Economy", resp.text)
        self.assertIn("Save", resp.text)


class TestDashboardDarkMode(unittest.TestCase):
    def setUp(self):
        self._old_db = dashboard.db
        dashboard.db = _fresh_db()
        self.client = TestClient(dashboard.app)

    def tearDown(self):
        dashboard.db = self._old_db

    def test_base_has_theme_script(self):
        resp = self.client.get("/")
        self.assertIn("data-theme", resp.text)
        self.assertIn("toggleTheme", resp.text)

    def test_css_has_light_theme(self):
        resp = self.client.get("/static/css/style.css")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('html[data-theme="light"]', resp.text)


if __name__ == "__main__":
    unittest.main()
