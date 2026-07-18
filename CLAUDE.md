# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

DDCBot is a French-language, multi-purpose Discord bot built on `discord.py` (commands.Bot, prefix `,`). It provides server moderation, an economy/income/work system, mini-games, RSS notifications, an AI assistant, notes/tags, and self-diagnostics. All command modules are `discord.ext.commands.Cog` subclasses wired together in [main.py](main.py).

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

**Entry point and cog wiring**: [main.py](main.py) creates the `commands.Bot` and registers every cog in `main()`. Each feature module exposes a `cmd<Name>` Cog class (e.g. `cmdeco`, `cmdincome`, `cmdjeu`, `cmdmoderation`) that is added with `bot.add_cog(...)`. When adding a new feature, create a new cog module and register it in `main.py`.

**Admin gate**: `main.py` defines a global `@bot.check` (`admin_role_gate`) that restricts a hardcoded `ADMIN_COMMANDS` set to guild admins/managers or roles configured per-guild in `permission_config.json` (loaded fresh on every check, not cached). Any new admin-only command must be added to `ADMIN_COMMANDS` in main.py.

**Centralized error handling**: `main.py`'s `on_command_error` distinguishes "expected" user errors (bad args, missing perms, cooldowns, etc.) from unexpected exceptions. Unexpected errors get a full traceback posted to a hardcoded Discord channel ID and printed to stdout; expected ones get a short notice to the same channel. Individual cogs can opt out by defining their own local `on_error` handler on a command.

**Per-guild JSON persistence, no database**: State is stored in flat JSON files at the repo root (`balances.json`, `income.json`, `inventaire.json`, `quete.json`, `notifications.json`, `gameconfig.json`, `workconfig.json`, `notes.json`, plus optional `*_config.json` files like `moderation_config.json`, `economy_config.json`, `income_config.json`, `game_panel_config.json`, `permission_config.json`). Each cog resolves its own JSON path via `os.path.dirname(__file__)` and implements its own `_load_*`/`_save_*` pair (naming isn't fully consistent across cogs: some use `_load_config`/`_save_config`, others `_load_json`/`_save_json`, or feature-specific names like `_load_tags`/`_load_notifications`). Configs are commonly keyed by guild ID with a `DEFAULT_*_CONFIG` dict merged in for missing keys (see `economie.py`, `income.py`, `jeu.py`, `moderation.py`). Runtime/production data files (`balances.json`, `income.json`, `inventaire.json`, `quete.json`, `notifications.json`, `workconfig.json`, `notes.json`) are gitignored and untracked — each owning cog creates the file with sane defaults on first run if it's absent (see `cmdwork.__init__` in `work.py` for the pattern); never re-add these to git, since a `git reset`/`git pull` would otherwise clobber live production data.

**Docker deployment**: [Dockerfile](Dockerfile) builds the bot image; [docker-compose.yml](docker-compose.yml) runs it alongside an `updater` service ([docker/updater](docker/updater)) that polls the git remote and rebuilds/restarts the `ddcbot` service on new commits via the mounted `docker.sock`. Requires `.env` (see `.env.example`) with `DDC_TOKEN` and `PROJECT_DIR` (absolute host path to the repo, needed because the updater bind-mounts volumes via the host daemon). [changelog.py](changelog.py) posts a `git log` summary to `CHANGELOG_CHANNEL_ID` on the first ready event after a new commit is detected, and exposes `,changelog` on demand.

**Admin panels via persistent Views**: Economy, income, work-config, and game features expose `*panel` commands (`ecopanel`, `incomepanel`, `gamepanel`, etc.) backed by `discord.ui.View` subclasses (e.g. `EconomyPanelView`, `IncomePanelView`, `GamePanelView`) with an `interaction_check` restricting interaction to the command author and a 300s timeout. Follow this pattern for new configurable panels.

**Diagnostics/selftest** ([diagnostics.py](diagnostics.py)): maintains `EXPECTED_COMMANDS` — the full set of command names that should be registered across all cogs — plus `REQUIRED_MODULES` and required/optional JSON file lists. The `,selftest [basic|deep]` command and `run_selftest()` cross-check the live bot's registered commands/cogs against these lists. **Any new user-facing command must be added to `EXPECTED_COMMANDS` in diagnostics.py**, or selftest/tests will report it missing.

**AI assistant** ([ai_assistant.py](ai_assistant.py)): uses `g4f` for LLM calls and lazily imports/initializes `easyocr` (heavy dependency, only loaded on first use via `_get_easyocr_reader`).

## Testing conventions

Tests live in `tests/` and use `unittest.TestCase` (run via pytest), with cogs instantiated directly against a `MagicMock()` bot rather than a real Discord connection (see `_make_cog()` helpers in `tests/test_diagnostics.py`). `tests/conftest.py` adds the repo root to `sys.path` so modules import without packaging.
