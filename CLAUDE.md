# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

DDCBot is a French-language, multi-purpose Discord bot built on `discord.py` (commands.Bot, prefix `,`). It provides server moderation, an economy/income/work system, mini-games, RSS notifications, an AI assistant, notes/tags, and self-diagnostics. All command modules are `discord.ext.commands.Cog` subclasses living in [cogs/](cogs/), wired together in [main.py](main.py) at the repo root. Runtime state lives in a SQLite database at `data/ddcbot.sqlite3` (see [data/db.py](data/db.py)).

## Commands

Setup:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Run the bot (`main.py:load_token()` reads the `DDC_TOKEN` env var first, falling back to a `secrets.json` at repo root with `{"ddc_token": "..."}`; neither is committed):
```bash
python main.py
```

One-time migration from the old flat-JSON storage (only needed once, when upgrading a pre-SQLite checkout that still has `data/*.json`):
```bash
python scripts/migrate_json_to_sqlite.py
```

Run via Docker (bot + self-updating watcher, see [docker-compose.yml](docker-compose.yml)):
```bash
cp .env.example .env   # set DDC_TOKEN and PROJECT_DIR (absolute host path)
docker compose up -d
```

Lint (matches CI):
```bash
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics   # blocking
flake8 . --count --exit-zero --statistics                            # full report, non-blocking
```

Syntax check:
```bash
python -m compileall -q .
```

Tests:
```bash
pytest -q                                # full suite
pytest -q tests/test_diagnostics.py      # single file
pytest -q tests/test_diagnostics.py::TestRunSelftest::test_basic_returns_all_keys   # single test
pytest -q tests/test_diagnostics_deep.py # deep diagnostic criteria, also run separately in CI
```

CI (`.github/workflows/tests.yml`) runs on Python 3.10/3.11/3.12: flake8 critical-error check, full flake8 report, `compileall`, `pytest`, then `test_diagnostics_deep.py` again explicitly.

## Architecture

**Entry point and cog wiring**: [main.py](main.py) creates the `commands.Bot`, instantiates a single module-level `db = Database()`, and registers every cog in `main()`. Each feature module lives in `cogs/` and exposes a `cmd<Name>` Cog class (e.g. `cmdeco`, `cmdincome`, `cmdjeu`, `cmdmoderation`) imported as `from cogs.<module> import cmd<Name>` and added with `bot.add_cog(...)`. Cogs that touch persistent state take `db` as a second constructor argument (`cmdeco(bot, db)`); cogs with no storage needs (e.g. `cmdutility`, `cmdanim`, `cmdhelp`, `cmdai`, `cmdchangelog`) keep the single-arg `(bot)` constructor. When adding a new feature, create a new cog module under `cogs/` and register it in `main.py`.

**Admin gate**: `main.py` defines a global `@bot.check` (`admin_role_gate`) that restricts a hardcoded `ADMIN_COMMANDS` set to guild admins/managers or roles configured per-guild in the `permission_config` table (queried fresh on every check via `load_permission_config(guild_id)`, not cached). Any new admin-only command must be added to `ADMIN_COMMANDS` in main.py.

**Centralized error handling**: `main.py`'s `on_command_error` distinguishes "expected" user errors (bad args, missing perms, cooldowns, etc.) from unexpected exceptions. Unexpected errors get a full traceback posted to a hardcoded Discord channel ID and printed to stdout; expected ones get a short notice to the same channel. Individual cogs can opt out by defining their own local `on_error` handler on a command.

**SQLite persistence, shared connection**: State lives in a single SQLite database, `data/ddcbot.sqlite3` (gitignored, created on first run). [data/db.py](data/db.py) defines `Database`, a thin `sqlite3` wrapper (WAL mode, `row_factory=sqlite3.Row`) that applies numbered SQL migrations from [data/migrations/](data/migrations/) on startup, tracked in a `schema_migrations` table. One `Database` instance is created once in `main.py` and injected into every storage-owning cog's constructor — there is no more per-cog file path or `_load_*`/`_save_*` pair. Each cog exposes small typed helper methods over its own tables instead (e.g. `cmdeco.get_balance`/`add_balance` over the shared `balances` table used by `cmdeco`, `cmdincome`, `cmdjeu`, and `cmdwork`). Mutations are targeted `INSERT ... ON CONFLICT DO UPDATE`/`UPDATE`/`DELETE` statements scoped to the affected row(s), not whole-table dumps — this is what eliminates the old flat-JSON failure modes (non-atomic writes that could corrupt a file on crash, and multiple cogs each holding a stale in-memory copy of the same file and clobbering each other's writes). Per-guild admin config that's a single nested object (`moderation_config`, `permission_config`, `logs_config`) is still stored as a JSON blob in a `config_json` column keyed by `guild_id`, since normalizing it into sub-tables wouldn't add correctness value for low-churn admin data. See [data/migrations/0001_initial.sql](data/migrations/0001_initial.sql) for the full schema. A one-time importer, [scripts/migrate_json_to_sqlite.py](scripts/migrate_json_to_sqlite.py), populates the database from any pre-existing `data/*.json` files (idempotent — skips a table that already has rows); those JSON files are no longer read by the bot and are kept only as a migration source/backup.

**Docker deployment**: [Dockerfile](Dockerfile) builds the bot image; [docker-compose.yml](docker-compose.yml) runs it alongside an `updater` service ([docker/updater](docker/updater)) that polls the git remote and rebuilds/restarts the `ddcbot` service on new commits via the mounted `docker.sock`. Requires `.env` (see `.env.example`) with `DDC_TOKEN` and `PROJECT_DIR` (absolute host path to the repo, needed because the updater bind-mounts volumes via the host daemon). The whole `PROJECT_DIR` is bind-mounted into the container, so `data/ddcbot.sqlite3` persists across restarts/rebuilds the same way the old JSON files did — no extra volume config needed. [changelog.py](changelog.py) posts a `git log` summary to `CHANGELOG_CHANNEL_ID` on the first ready event after a new commit is detected, and exposes `,changelog` on demand.

**Admin panels via persistent Views**: Economy, income, work-config, and game features expose `*panel` commands (`ecopanel`, `incomepanel`, `gamepanel`, etc.) backed by `discord.ui.View` subclasses (e.g. `EconomyPanelView`, `IncomePanelView`, `GamePanelView`) with an `interaction_check` restricting interaction to the command author and a 300s timeout. Follow this pattern for new configurable panels.

**Diagnostics/selftest** ([cogs/diagnostics.py](cogs/diagnostics.py)): maintains `EXPECTED_COMMANDS` — the full set of command names that should be registered across all cogs — plus `REQUIRED_MODULES` and `EXPECTED_TABLES` (checked against `sqlite_master` via the injected `db`; deep mode also runs `PRAGMA integrity_check`). The `,selftest [basic|deep]` command and `run_selftest()` cross-check the live bot's registered commands/cogs against these lists. **Any new user-facing command must be added to `EXPECTED_COMMANDS` in cogs/diagnostics.py**, or selftest/tests will report it missing.

**AI assistant** ([cogs/ai_assistant.py](cogs/ai_assistant.py)): uses `g4f` for LLM calls and lazily imports/initializes `easyocr` (heavy dependency, only loaded on first use via `_get_easyocr_reader`).

## Testing conventions

Tests live in `tests/` and use `unittest.TestCase` (run via pytest), with cogs instantiated directly against a `MagicMock()` bot and a real `Database(path=":memory:")` rather than a live Discord connection or the on-disk database (see `_make_cog()` helpers in `tests/test_diagnostics.py`). `tests/conftest.py` adds the repo root to `sys.path`, and cog modules are imported as `cogs.<module>` (e.g. `from cogs.diagnostics import cmddiagnostics`).
