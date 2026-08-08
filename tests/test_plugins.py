import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import plugin_loader  # noqa: E402
from cogs.plugins_cmd import cmdplugins  # noqa: E402
from data.db import Database  # noqa: E402

PLUGIN_PLUGIN = '''\
from discord.ext import commands


class ExamplePlugCog(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db


def setup(bot, db):
    bot.add_cog(ExamplePlugCog(bot, db))


def teardown(bot, db):
    bot.needs_cleanup = True
'''

PLUGIN_MANIFEST = '''\
{"name": "example", "version": "1.2.0", "description": "Plugin de test"}
'''

REPO_PLUGINS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins"
)


class FakeBot:
    def __init__(self):
        self.cogs = {}
        self.needs_cleanup = False

    def add_cog(self, cog):
        self.cogs[type(cog).__name__] = cog

    def get_cog(self, name):
        return self.cogs.get(name)

    async def remove_cog(self, name):
        self.cogs.pop(name, None)


def _write_plugin_dir(base, name="example", manifest=True):
    plugin_dir = os.path.join(base, name)
    os.makedirs(plugin_dir, exist_ok=True)
    with open(os.path.join(plugin_dir, "plugin.py"), "w") as f:
        f.write(PLUGIN_PLUGIN)
    if manifest:
        with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
            f.write(PLUGIN_MANIFEST)
    return plugin_dir


def _make_ctx():
    ctx = mock.MagicMock()
    ctx.send = mock.AsyncMock()
    return ctx


class TestPluginLoader(unittest.TestCase):
    def setUp(self):
        self.db = Database(path=":memory:")
        self.bot = FakeBot()
        self._old_dir = plugin_loader.PLUGINS_DIR
        self._tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._tmp)

    def tearDown(self):
        plugin_loader.PLUGINS_DIR = self._old_dir
        plugin_loader._loaded_cogs.clear()
        for key in [k for k in sys.modules if k.startswith("plugins.")]:
            del sys.modules[key]
        self.db.close()

    def test_discover_default_dir_is_empty(self):
        plugin_loader.PLUGINS_DIR = REPO_PLUGINS_DIR
        self.assertEqual(plugin_loader.discover_plugins(), [])

    def test_set_enabled_get_enabled(self):
        plugin_loader.set_enabled(self.db, "foo", True)
        plugin_loader.set_enabled(self.db, "bar", False)
        enabled = plugin_loader.get_enabled(self.db)
        self.assertTrue(enabled["foo"])
        self.assertFalse(enabled["bar"])
        self.assertTrue(plugin_loader.is_enabled(self.db, "unknown"))

    def test_metadata_from_manifest(self):
        _write_plugin_dir(self._tmp)
        plugin_loader.PLUGINS_DIR = self._tmp
        meta = plugin_loader.plugin_metadata("example")
        self.assertEqual(meta["version"], "1.2.0")
        self.assertEqual(meta["name"], "example")

    def test_load_and_unload(self):
        _write_plugin_dir(self._tmp)
        plugin_loader.PLUGINS_DIR = self._tmp

        async def run():
            return await plugin_loader.load_plugins(self.bot, self.db)

        loaded = asyncio.run(run())
        self.assertIn("example", loaded)
        self.assertIn("ExamplePlugCog", self.bot.cogs)

        async def unload():
            await plugin_loader.unload_plugins(self.bot, self.db, ["example"])

        asyncio.run(unload())
        self.assertNotIn("ExamplePlugCog", self.bot.cogs)
        self.assertTrue(self.bot.needs_cleanup)
        self.assertNotIn("plugins.example.plugin", sys.modules)

    def test_disabled_plugin_not_loaded(self):
        _write_plugin_dir(self._tmp)
        plugin_loader.PLUGINS_DIR = self._tmp
        plugin_loader.set_enabled(self.db, "example", False)

        async def run():
            return await plugin_loader.load_plugins(self.bot, self.db)

        loaded = asyncio.run(run())
        self.assertNotIn("example", loaded)
        self.assertNotIn("ExamplePlugCog", self.bot.cogs)


class TestPluginsCog(unittest.TestCase):
    def setUp(self):
        self.db = Database(path=":memory:")
        self.bot = FakeBot()
        self.cog = cmdplugins(self.bot, self.db)
        self._old_dir = plugin_loader.PLUGINS_DIR
        self._tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._tmp)

    def tearDown(self):
        plugin_loader.PLUGINS_DIR = self._old_dir
        plugin_loader._loaded_cogs.clear()
        for key in [k for k in sys.modules if k.startswith("plugins.")]:
            del sys.modules[key]
        self.db.close()

    def test_available_empty_default(self):
        plugin_loader.PLUGINS_DIR = REPO_PLUGINS_DIR
        self.assertEqual(self.cog._available(), set())

    def test_list_command_no_plugins(self):
        ctx = _make_ctx()
        plugin_loader.PLUGINS_DIR = REPO_PLUGINS_DIR
        asyncio.run(self.cog.plugins_list(ctx))
        ctx.send.assert_called_once()
        self.assertIn("Aucun plugin", ctx.send.call_args[0][0])

    def test_enable_and_disable(self):
        _write_plugin_dir(self._tmp)
        plugin_loader.PLUGINS_DIR = self._tmp
        ctx = _make_ctx()

        asyncio.run(self.cog.plugins_enable(ctx, "example"))
        self.assertIn("ExamplePlugCog", self.bot.cogs)
        self.assertTrue(plugin_loader.is_enabled(self.db, "example"))

        asyncio.run(self.cog.plugins_disable(ctx, "example"))
        self.assertNotIn("ExamplePlugCog", self.bot.cogs)
        self.assertFalse(plugin_loader.is_enabled(self.db, "example"))

    def test_enable_unknown_plugin(self):
        ctx = _make_ctx()
        asyncio.run(self.cog.plugins_enable(ctx, "nope"))
        ctx.send.assert_called()
        self.assertIn("inconnu", ctx.send.call_args[0][0])


if __name__ == "__main__":
    unittest.main()