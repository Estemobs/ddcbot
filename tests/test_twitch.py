import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from data.db import Database
from cogs.twitch import cmdtwitch

GUILD = 111

LIVE_PAYLOAD = {
    "data": {"user": {
        "id": "1", "displayName": "OTPLOL_", "profileImageURL": "https://img/avatar.png",
        "stream": {"id": "317637106916", "title": "LCK - GEN vs KT", "type": "live",
                   "viewersCount": 6950, "previewImageURL":
                       "https://cdn/live_user-{width}x{height}.jpg",
                   "game": {"name": "League of Legends"}},
    }}
}
OFFLINE_PAYLOAD = {"data": {"user": {"id": "1", "displayName": "ZeratoR", "stream": None}}}
UNKNOWN_PAYLOAD = {"data": {"user": None}}


def _make_cog():
    return cmdtwitch(MagicMock(), Database(path=":memory:"))


def _make_session(payload, status=200):
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=payload)

    class _Ctx:
        async def __aenter__(self):
            return response

        async def __aexit__(self, *args):
            return None

    session = MagicMock()
    session.closed = False
    session.post = lambda *a, **k: _Ctx()
    return session


class TestNoApiKey(unittest.TestCase):
    """Twitch exigeait un client_id et un client_secret par serveur."""

    def test_no_oauth_endpoint_is_called(self):
        """Docstring exclue : elle rappelle volontairement l'ancien fonctionnement."""
        import ast

        tree = ast.parse((Path(__file__).resolve().parent.parent / "cogs" / "twitch.py").read_text())
        docstring = ast.get_docstring(tree, clean=False)
        literals = [
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node.value != docstring
        ]
        for forbidden in ("id.twitch.tv/oauth2", "api.twitch.tv/helix", "client_secret"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse([lit for lit in literals if forbidden in lit])

    def test_config_only_holds_a_channel_and_a_switch(self):
        cog = _make_cog()
        self.assertEqual(cog.get_config(GUILD), {"channel_id": None, "enabled": False})


class TestLiveDetection(unittest.TestCase):
    def test_live_channel_is_detected(self):
        cog = _make_cog()
        cog._session = _make_session(LIVE_PAYLOAD)
        live = asyncio.run(cog.is_live("otplol_"))
        self.assertIsNotNone(live)
        self.assertEqual(live["stream"]["title"], "LCK - GEN vs KT")

    def test_offline_channel_returns_none(self):
        cog = _make_cog()
        cog._session = _make_session(OFFLINE_PAYLOAD)
        self.assertIsNone(asyncio.run(cog.is_live("zerator")))

    def test_unknown_channel_returns_none(self):
        cog = _make_cog()
        cog._session = _make_session(UNKNOWN_PAYLOAD)
        self.assertIsNone(asyncio.run(cog.fetch_channel("nexistepas")))

    def test_http_error_is_swallowed(self):
        cog = _make_cog()
        cog._session = _make_session(None, status=503)
        self.assertIsNone(asyncio.run(cog.fetch_channel("otplol_")))

    def test_preview_template_is_resolved(self):
        """Laisses tels quels, les gabarits {width}/{height} font refuser l'image."""
        from cogs.twitch import preview_url
        url = preview_url(LIVE_PAYLOAD["data"]["user"]["stream"])
        self.assertEqual(url, "https://cdn/live_user-640x360.jpg")

    def test_preview_missing_is_empty(self):
        from cogs.twitch import preview_url
        self.assertEqual(preview_url({}), "")
        self.assertEqual(preview_url(None), "")


class TestWatchList(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_watching_is_case_insensitive_and_unique(self):
        self.cog.watch(GUILD, "ZeratoR")
        self.cog.watch(GUILD, "zerator")
        self.assertEqual(self.cog.list_watched(GUILD), ["zerator"])

    def test_watch_list_is_per_guild(self):
        self.cog.watch(GUILD, "zerator")
        self.assertEqual(self.cog.list_watched(999), [])

    def test_unwatch(self):
        self.cog.watch(GUILD, "zerator")
        self.assertTrue(self.cog.unwatch(GUILD, "ZeratoR"))
        self.assertFalse(self.cog.unwatch(GUILD, "zerator"))


class TestAnnounceOnce(unittest.TestCase):
    """Chaque direct ne doit etre annonce qu'une fois, pas a chaque tour de boucle."""

    def setUp(self):
        self.cog = _make_cog()

    def test_stream_is_announced_only_once(self):
        self.assertFalse(self.cog.already_announced(GUILD, "317637106916"))
        self.cog.mark_announced(GUILD, "otplol_", "317637106916", "LCK", "https://url")
        self.assertTrue(self.cog.already_announced(GUILD, "317637106916"))

    def test_a_new_stream_is_announced_again(self):
        self.cog.mark_announced(GUILD, "otplol_", "1", "LCK", "https://url")
        self.assertFalse(self.cog.already_announced(GUILD, "2"))

    def test_journal_is_per_guild(self):
        self.cog.mark_announced(GUILD, "otplol_", "1", "LCK", "https://url")
        self.assertFalse(self.cog.already_announced(999, "1"))


class TestConfig(unittest.TestCase):
    def test_channel_and_switch_round_trip(self):
        cog = _make_cog()
        cog.set_config(GUILD, channel_id=42, enabled=1)
        self.assertEqual(cog.get_config(GUILD), {"channel_id": 42, "enabled": True})

    def test_unknown_field_is_ignored(self):
        cog = _make_cog()
        cog.set_config(GUILD, client_secret="secret")
        self.assertEqual(cog.get_config(GUILD)["channel_id"], None)


class TestLegacyMigration(unittest.TestCase):
    def test_previously_followed_channels_are_carried_over(self):
        import shutil
        import tempfile
        from data.db import MIGRATIONS_DIR

        staging = tempfile.mkdtemp()
        for name in sorted(os.listdir(MIGRATIONS_DIR)):
            if not name.startswith("0013"):
                shutil.copy(os.path.join(MIGRATIONS_DIR, name), staging)
        path = os.path.join(tempfile.mkdtemp(), "legacy.sqlite3")

        old = Database(path=path, migrations_dir=staging)
        old.execute(
            "INSERT INTO twitch_notifications (guild_id, user_id, user_login) VALUES (?, ?, ?)",
            (GUILD, 7, "ZeratoR"),
        )
        old.close()

        cog = cmdtwitch(MagicMock(), Database(path=path))
        self.assertEqual(cog.list_watched(GUILD), ["zerator"])


if __name__ == "__main__":
    unittest.main()
