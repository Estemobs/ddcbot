import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from data.db import Database
from cogs.steam import cmdsteam, _clean_steam_username


def _make_cog():
    bot = MagicMock()
    db = Database(path=":memory:")
    return cmdsteam(bot, db)


class TestSteamConfigDB(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_api_key_none_when_unconfigured(self):
        self.assertIsNone(self.cog.get_api_key(123))

    def test_set_and_get_api_key(self):
        self.cog.set_api_key(123, "KEY123")
        self.assertEqual(self.cog.get_api_key(123), "KEY123")

    def test_api_key_is_per_guild(self):
        self.cog.set_api_key(123, "KEY123")
        self.assertIsNone(self.cog.get_api_key(456))

    def test_steam_config_table_exists(self):
        row = self.cog.db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'steam_config'"
        )
        self.assertIsNotNone(row)


def _make_session(response_data):
    response = MagicMock()
    response.status = 200
    response.json = AsyncMock(return_value=response_data)

    class _Ctx:
        async def __aenter__(self):
            return response

        async def __aexit__(self, *args):
            return None

    session = MagicMock()
    session.closed = False
    session.get = lambda *a, **k: _Ctx()
    return session


class TestSteamHelpers(unittest.TestCase):
    def test_clean_username_strips_slashes(self):
        self.assertEqual(_clean_steam_username("  /pseudo/  "), "pseudo")

    def test_clean_username_preserves_plain(self):
        self.assertEqual(_clean_steam_username("estemobs"), "estemobs")

    def test_resolve_vanity_returns_steamid(self):
        cog = _make_cog()
        cog._session = _make_session({"response": {"success": 1, "steamid": "76561198000000000"}})
        result = asyncio.run(cog.resolve_vanity("KEY", "pseudo"))
        self.assertEqual(result, "76561198000000000")

    def test_resolve_vanity_returns_none_on_failure(self):
        cog = _make_cog()
        cog._session = _make_session({"response": {"success": 42}})
        result = asyncio.run(cog.resolve_vanity("KEY", "pseudo"))
        self.assertIsNone(result)

    def test_fetch_inventory_parses_items(self):
        cog = _make_cog()
        cog._session = _make_session({"response": {"items": [{"item_id": "1"}, {"item_id": "2"}]}})
        items = asyncio.run(cog.fetch_inventory("KEY", "76561198000000000"))
        self.assertEqual(len(items), 2)


if __name__ == "__main__":
    unittest.main()
