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

from Notifrss import cmdrss


def _make_cog():
    bot = MagicMock()
    bot.fetch_user = AsyncMock()
    return cmdrss(bot)


class TestNotifRssHelpers(unittest.TestCase):
    def test_remove_user_notifications_for_show_removes_every_matching_entry(self):
        cog = _make_cog()
        notifications = [
            {"show_name": "The Boys", "user_id": 1, "season": 5, "number": 1, "airdate": "2026-05-20T00:00:00"},
            {"show_name": "The Boys", "user_id": 1, "season": 5, "number": 2, "airdate": "2026-05-27T00:00:00"},
            {"show_name": "Another Show", "user_id": 1, "season": 1, "number": 1, "airdate": "2026-05-20T00:00:00"},
            {"show_name": "The Boys", "user_id": 2, "season": 5, "number": 1, "airdate": "2026-05-20T00:00:00"},
        ]

        filtered = cog._remove_user_notifications_for_show(notifications, 1, "The Boys")

        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]["show_name"], "Another Show")
        self.assertEqual(filtered[1]["user_id"], 2)


class TestNotifRssCheckNotifications(unittest.IsolatedAsyncioTestCase):
    async def test_check_notifications_advances_to_next_unreleased_episode(self):
        cog = _make_cog()
        cog._load_notifications = MagicMock(
            return_value=[
                {
                    "show_name": "The Boys",
                    "season": 5,
                    "number": 1,
                    "airdate": "2020-01-01T00:00:00",
                    "user_id": 123,
                }
            ]
        )
        cog._save_notifications = MagicMock()
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
        cog._save_notifications.assert_called_once()
        self.assertEqual(
            cog._save_notifications.call_args.args[0],
            [
                {
                    "show_name": "The Boys",
                    "season": 5,
                    "number": 9,
                    "airdate": "2026-06-01",
                    "user_id": 123,
                }
            ],
        )
        user.send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()