import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from data.db import Database
from cogs.steam import cmdsteam, _clean_steam_username

PROFILE_XML = """<?xml version="1.0"?>
<profile><steamID64>76561198000000000</steamID64><steamID>estemobs</steamID></profile>
"""


def _make_cog():
    return cmdsteam(MagicMock(), Database(path=":memory:"))


def _make_session(*, text=None, json_data=None, status=200):
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value=text or "")
    response.json = AsyncMock(return_value=json_data)

    class _Ctx:
        async def __aenter__(self):
            return response

        async def __aexit__(self, *args):
            return None

    session = MagicMock()
    session.closed = False
    session.get = lambda *a, **k: _Ctx()
    return session


class TestNoApiKey(unittest.TestCase):
    """Steam passe par les pages publiques : plus aucune cle n'est lue."""

    def test_cog_never_reads_an_api_key(self):
        """Le code (docstring exclue, qui rappelle l'historique) n'appelle plus l'API a cle."""
        import ast
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "cogs" / "steam.py"
        tree = ast.parse(path.read_text())
        literals = [
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        docstring = ast.get_docstring(tree, clean=False)
        code_literals = [lit for lit in literals if lit != docstring]
        self.assertFalse([lit for lit in code_literals if "api.steampowered.com" in lit])
        self.assertNotIn("key", code_literals)

    def test_no_key_accessors_remain(self):
        cog = _make_cog()
        self.assertFalse(hasattr(cog, "get_api_key"))
        self.assertFalse(hasattr(cog, "set_api_key"))

    def test_steam_config_table_still_exists(self):
        """La colonne est conservee pour ne pas casser les bases existantes."""
        row = _make_cog().db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'steam_config'"
        )
        self.assertIsNotNone(row)


class TestCleanUsername(unittest.TestCase):
    def test_strips_slashes(self):
        self.assertEqual(_clean_steam_username("  /pseudo/  "), "pseudo")

    def test_preserves_plain(self):
        self.assertEqual(_clean_steam_username("estemobs"), "estemobs")

    def test_accepts_a_full_profile_url(self):
        self.assertEqual(
            _clean_steam_username("https://steamcommunity.com/id/estemobs/"), "estemobs"
        )
        self.assertEqual(
            _clean_steam_username("steamcommunity.com/profiles/76561198000000000"),
            "76561198000000000",
        )


class TestResolveVanity(unittest.TestCase):
    def test_reads_steamid64_from_the_public_profile(self):
        cog = _make_cog()
        cog._session = _make_session(text=PROFILE_XML)
        self.assertEqual(asyncio.run(cog.resolve_vanity("estemobs")), "76561198000000000")

    def test_a_steamid64_is_returned_as_is_without_any_request(self):
        cog = _make_cog()
        cog._session = _make_session(text="", status=500)
        self.assertEqual(
            asyncio.run(cog.resolve_vanity("76561198000000000")), "76561198000000000"
        )

    def test_returns_none_when_the_profile_is_missing(self):
        cog = _make_cog()
        cog._session = _make_session(text="<profile></profile>")
        self.assertIsNone(asyncio.run(cog.resolve_vanity("inconnu")))

    def test_returns_none_on_http_error(self):
        cog = _make_cog()
        cog._session = _make_session(text="", status=404)
        self.assertIsNone(asyncio.run(cog.resolve_vanity("inconnu")))


class TestFetchInventory(unittest.TestCase):
    """L'inventaire public joint `assets` (quantites) et `descriptions` (noms)."""

    PAYLOAD = {
        "assets": [
            {"classid": "1", "instanceid": "0", "amount": "2"},
            {"classid": "2", "instanceid": "0", "amount": "1"},
        ],
        "descriptions": [
            {"classid": "1", "instanceid": "0", "market_hash_name": "AK-47 | Redline"},
            {"classid": "2", "instanceid": "0", "market_hash_name": "Glock-18 | Fade"},
        ],
    }

    def test_joins_assets_with_their_descriptions(self):
        cog = _make_cog()
        cog._session = _make_session(json_data=self.PAYLOAD)
        items = asyncio.run(cog.fetch_inventory("76561198000000000"))
        self.assertEqual(
            sorted((i["name"], i["amount"]) for i in items),
            [("AK-47 | Redline", 2), ("Glock-18 | Fade", 1)],
        )

    def test_private_profile_yields_an_empty_inventory(self):
        cog = _make_cog()
        cog._session = _make_session(json_data=None, status=403)
        self.assertEqual(asyncio.run(cog.fetch_inventory("76561198000000000")), [])

    def test_asset_without_description_is_kept_with_a_placeholder(self):
        cog = _make_cog()
        cog._session = _make_session(
            json_data={"assets": [{"classid": "9", "instanceid": "0", "amount": "1"}],
                       "descriptions": []}
        )
        items = asyncio.run(cog.fetch_inventory("76561198000000000"))
        self.assertEqual(items, [{"name": "?", "amount": 1}])


if __name__ == "__main__":
    unittest.main()
