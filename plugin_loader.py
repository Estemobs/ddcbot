"""Chargeur de plugins/extensions pour DDCBot.

Un plugin est un dossier sous `plugins/<nom>/` contenant un module
`plugin.py` exposant `setup(bot, db)` (obligatoire) et optionnellement
`teardown(bot, db)`. Des metadonnees (name, version) peuvent etre fournies
via `manifest.json` dans le dossier du plugin.

Les plugins actives/inactives sont suivis dans la table `plugins`.
Par defaut, un plugin non reference est considere comme actif.
"""

import importlib
import importlib.util
import inspect
import json
import os
import sys

PLUGINS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")

_loaded_cogs = {}


def discover_plugins():
    """Liste les noms des plugins disponibles dans le dossier plugins/."""
    if not os.path.isdir(PLUGINS_DIR):
        return []
    return sorted(
        name for name in os.listdir(PLUGINS_DIR)
        if os.path.isdir(os.path.join(PLUGINS_DIR, name))
        and not name.startswith("_")
        and not name.startswith(".")
    )


def _plugin_dir(name):
    return os.path.join(PLUGINS_DIR, name)


def plugin_metadata(name):
    """Retourne les metadonnees d'un plugin (manifest.json + defauts)."""
    metadata = {"name": name, "version": "0.0.0"}
    manifest = os.path.join(_plugin_dir(name), "manifest.json")
    if os.path.exists(manifest):
        try:
            with open(manifest) as f:
                data = json.load(f)
            if isinstance(data, dict):
                metadata.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return metadata


def get_enabled(db):
    """Retourne {nom_plugin: bool} depuis la table plugins ({} si absente)."""
    try:
        rows = db.fetchall("SELECT name, enabled FROM plugins")
        return {row["name"]: bool(row["enabled"]) for row in rows}
    except Exception:
        return {}


def is_enabled(db, name):
    """Un plugin non reference est considere actif par defaut."""
    return get_enabled(db).get(name, True)


def set_enabled(db, name, enabled):
    """Active/desactive un plugin dans la table plugins."""
    db.execute(
        "INSERT INTO plugins (name, enabled, installed_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(name) DO UPDATE SET enabled = excluded.enabled",
        (name, int(bool(enabled))),
    )


async def load_plugins(bot, db):
    """Charge les plugins actifs. Retourne la liste des plugins charges."""
    loaded = []
    for name in discover_plugins():
        if not is_enabled(db, name):
            continue
        module_name = f"plugins.{name}.plugin"
        if module_name in sys.modules:
            loaded.append(name)
            continue
        plugin_file = os.path.join(_plugin_dir(name), "plugin.py")
        if not os.path.exists(plugin_file):
            continue
        try:
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            setup = getattr(module, "setup", None)
            if not callable(setup):
                continue
            before = set(bot.cogs.keys())
            result = setup(bot, db)
            if inspect.isawaitable(result):
                await result
            _loaded_cogs[name] = set(bot.cogs.keys()) - before
            loaded.append(name)
            print(f"[PLUGINS] Plugin charge: {name}")
        except Exception as exc:
            print(f"[PLUGINS] Echec du chargement de '{name}': {exc}")
    return loaded


async def unload_plugins(bot, db, names=None):
    """Decharge les plugins (par defaut tous ceux actuellement charges)."""
    for name in names or list(_loaded_cogs):
        module = sys.modules.get(f"plugins.{name}.plugin")
        if module is None:
            _loaded_cogs.pop(name, None)
            continue
        teardown = getattr(module, "teardown", None)
        try:
            if callable(teardown):
                result = teardown(bot, db)
                if inspect.isawaitable(result):
                    await result
            for cog_name in _loaded_cogs.get(name, ()):
                if bot.get_cog(cog_name) is not None:
                    await bot.remove_cog(cog_name)
            del sys.modules[f"plugins.{name}.plugin"]
        except Exception as exc:
            print(f"[PLUGINS] Echec du dechargement de '{name}': {exc}")
        _loaded_cogs.pop(name, None)
        print(f"[PLUGINS] Plugin decharge: {name}")


async def reload_plugins(bot, db, names=None):
    """Recharge les plugins donnes (ou tous si names est None)."""
    targets = names or list(_loaded_cogs)
    await unload_plugins(bot, db, targets)
    return await load_plugins(bot, db)
