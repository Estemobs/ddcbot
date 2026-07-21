import unittest
from unittest.mock import MagicMock

from data.db import Database
from cogs.diagnostics import cmddiagnostics, EXPECTED_COMMANDS, REQUIRED_MODULES, EXPECTED_TABLES


def _make_cog():
    bot = MagicMock()
    bot.commands = []
    bot.cogs = {}
    db = Database(path=":memory:")
    return cmddiagnostics(bot, db)


class TestTableExists(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_missing_table_returns_false(self):
        self.assertFalse(self.cog._table_exists("__nonexistent_table__"))

    def test_expected_tables_exist_after_migrations(self):
        for table_name in EXPECTED_TABLES:
            self.assertTrue(
                self.cog._table_exists(table_name),
                f"{table_name} devrait exister apres application des migrations",
            )


class TestRunSelftest(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_basic_returns_all_keys(self):
        result = self.cog.run_selftest(mode="basic")
        self.assertIn("checks_ok", result)
        self.assertIn("checks_total", result)
        self.assertIn("details", result)
        self.assertIn("missing_commands", result)
        self.assertIn("loaded_cogs", result)

    def test_checks_total_is_positive(self):
        result = self.cog.run_selftest(mode="basic")
        self.assertGreater(result["checks_total"], 0)

    def test_details_is_non_empty_list(self):
        result = self.cog.run_selftest(mode="basic")
        self.assertIsInstance(result["details"], list)
        self.assertGreater(len(result["details"]), 0)

    def test_tables_check_passes_on_fresh_database(self):
        result = self.cog.run_selftest(mode="basic")
        self.assertIn("[OK] Tables SQLite", result["details"])


class TestConstants(unittest.TestCase):
    def test_expected_commands_is_set(self):
        self.assertIsInstance(EXPECTED_COMMANDS, set)
        self.assertGreater(len(EXPECTED_COMMANDS), 0)

    def test_selftest_in_expected_commands(self):
        self.assertIn("selftest", EXPECTED_COMMANDS)

    def test_required_modules_is_list(self):
        self.assertIsInstance(REQUIRED_MODULES, list)
        self.assertGreater(len(REQUIRED_MODULES), 0)

    def test_discord_in_required_modules(self):
        self.assertIn("discord", REQUIRED_MODULES)

    def test_expected_tables_is_non_empty_list(self):
        self.assertIsInstance(EXPECTED_TABLES, list)
        self.assertGreater(len(EXPECTED_TABLES), 0)


if __name__ == "__main__":
    unittest.main()
