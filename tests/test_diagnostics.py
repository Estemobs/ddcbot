import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from diagnostics import cmddiagnostics, EXPECTED_COMMANDS, REQUIRED_MODULES


def _make_cog():
    bot = MagicMock()
    bot.commands = []
    bot.cogs = {}
    return cmddiagnostics(bot)


class TestCheckJsonFile(unittest.TestCase):
    def setUp(self):
        self.cog = _make_cog()

    def test_missing_file_returns_absent(self):
        ok, msg = self.cog._check_json_file("__nonexistent_test__.json")
        self.assertFalse(ok)
        self.assertEqual(msg, "absent")

    def test_valid_json_returns_ok(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir=self.cog.base_dir, delete=False
        ) as f:
            json.dump({"key": "value"}, f)
            tmp_name = os.path.basename(f.name)
        try:
            ok, msg = self.cog._check_json_file(tmp_name)
            self.assertTrue(ok)
            self.assertEqual(msg, "ok")
        finally:
            os.unlink(os.path.join(self.cog.base_dir, tmp_name))

    def test_invalid_json_returns_error(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir=self.cog.base_dir, delete=False
        ) as f:
            f.write("{not valid json}")
            tmp_name = os.path.basename(f.name)
        try:
            ok, msg = self.cog._check_json_file(tmp_name)
            self.assertFalse(ok)
            self.assertIn("json invalide", msg)
        finally:
            os.unlink(os.path.join(self.cog.base_dir, tmp_name))


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


if __name__ == "__main__":
    unittest.main()
