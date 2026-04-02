import unittest
from unittest.mock import MagicMock

from diagnostics import cmddiagnostics, EXPECTED_COMMANDS


def _make_cog():
    bot = MagicMock()
    bot.commands = []
    bot.cogs = {}
    return cmddiagnostics(bot)


class TestRunSelftestDeep(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_deep_returns_all_keys(self):
        result = self.cog.run_selftest(mode="deep")
        self.assertIn("checks_ok", result)
        self.assertIn("checks_total", result)
        self.assertIn("details", result)
        self.assertIn("missing_commands", result)
        self.assertIn("loaded_cogs", result)

    def test_deep_has_more_checks_than_basic(self):
        basic = self.cog.run_selftest(mode="basic")
        deep = self.cog.run_selftest(mode="deep")
        self.assertGreater(deep["checks_total"], basic["checks_total"])

    def test_deep_details_is_non_empty_list(self):
        result = self.cog.run_selftest(mode="deep")
        self.assertIsInstance(result["details"], list)
        self.assertGreater(len(result["details"]), 0)

    def test_deep_missing_commands_contains_all_expected(self):
        # With no commands registered the bot reports all commands as missing
        result = self.cog.run_selftest(mode="deep")
        missing = set(result["missing_commands"])
        self.assertTrue(missing.issubset(EXPECTED_COMMANDS))


if __name__ == "__main__":
    unittest.main()
