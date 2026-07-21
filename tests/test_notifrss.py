import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock


def _install_discord_stubs():
    if "discord" in sys.modules:
        return

    discord_module = types.ModuleType("discord")

    class _FakeIntents:
        @staticmethod
        def all():
            return object()

    class _FakeColour:
        @staticmethod
        def green():
            return object()

        @staticmethod
        def red():
            return object()

    class _FakeEmbed:
        def __init__(self, *args, **kwargs):
            self.colour = None

        def add_field(self, *args, **kwargs):
            return None

    discord_module.Intents = _FakeIntents
    discord_module.Colour = _FakeColour
    discord_module.Embed = _FakeEmbed
    discord_module.File = object
    discord_module.DiscordException = Exception

    ext_module = types.ModuleType("discord.ext")
    commands_module = types.ModuleType("discord.ext.commands")

    class _FakeCog:
        @classmethod
        def listener(cls):
            def decorator(func):
                return func

            return decorator

    def _command(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    commands_module.Cog = _FakeCog
    commands_module.command = _command
    ext_module.commands = commands_module

    sys.modules["discord"] = discord_module
    sys.modules["discord.ext"] = ext_module
    sys.modules["discord.ext.commands"] = commands_module


_install_discord_stubs()

from data.db import Database  # noqa: E402
from cogs.Notifrss import cmdrss  # noqa: E402


def _make_cog():
    bot = MagicMock()
    bot.fetch_user = AsyncMock()
    db = Database(path=":memory:")
    return cmdrss(bot, db)


class TestNotifRssHelpers(unittest.TestCase):
    def test_delete_user_notifications_for_show_removes_every_matching_entry(self):
        cog = _make_cog()
        cog.add_notification("The Boys", 5, 1, "2026-05-20T00:00:00", 1)
        cog.add_notification("The Boys", 5, 2, "2026-05-27T00:00:00", 1)
        cog.add_notification("Another Show", 1, 1, "2026-05-20T00:00:00", 1)
        cog.add_notification("The Boys", 5, 1, "2026-05-20T00:00:00", 2)

        cog.delete_user_notifications_for_show(1, "The Boys")

        remaining = cog.list_notifications()
        self.assertEqual(len(remaining), 2)
        remaining_keys = sorted((n["show_name"], n["user_id"]) for n in remaining)
        self.assertEqual(remaining_keys, [("Another Show", 1), ("The Boys", 2)])


class TestNotifRssCheckNotifications(unittest.IsolatedAsyncioTestCase):
    async def test_check_notifications_advances_to_next_unreleased_episode(self):
        cog = _make_cog()
        cog.add_notification("The Boys", 5, 1, "2020-01-01T00:00:00", 123)
        cog._get_next_episode = AsyncMock(
            return_value={
                "show_name": "The Boys",
                "season": 5,
                "number": 9,
                "airdate": "2026-06-01",
                "user_id": 123,
            }
        )

        user = MagicMock()
        user.send = AsyncMock()
        cog.bot.fetch_user = AsyncMock(return_value=user)

        await cog.check_notifications()

        cog._get_next_episode.assert_awaited_once_with("The Boys", 123)
        remaining = cog.list_notifications()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["season"], 5)
        self.assertEqual(remaining[0]["number"], 9)
        self.assertEqual(remaining[0]["airdate"], "2026-06-01")
        user.send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
