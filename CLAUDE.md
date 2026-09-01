# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

DDCBot is a French-language, multi-purpose Discord bot built on `discord.py` (commands.Bot, prefix `,`). It provides server moderation, an economy/income/work system, mini-games, RSS notifications, an AI assistant, notes/tags, and self-diagnostics. All command modules are `discord.ext.commands.Cog` subclasses living in [cogs/](cogs/), wired together in [main.py](main.py) at the repo root. Runtime state lives in a SQLite database at `data/ddcbot.sqlite3` (see [data/db.py](data/db.py)).

## Commands

Setup:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# optionnel : dépendances du dashboard web (image dédiée sinon)
pip install -r requirements-dashboard.txt
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

**Entry point and cog wiring**: [main.py](main.py) creates the `commands.Bot`, instantiates a single module-level `db = Database()`, and registers every cog in `main()`. Each feature module lives in `cogs/` and exposes a `cmd<Name>` Cog class (e.g. `cmdeco`, `cmdincome`, `cmdjeu`, `cmdmoderation`) imported as `from cogs.<module> import cmd<Name>` and added with `bot.add_cog(...)`. Cogs that touch persistent state take `db` as a second constructor argument (`cmdeco(bot, db)`); cogs with no storage needs (e.g. `cmdhelp`, `cmdai`, `cmdchangelog`) keep the single-arg `(bot)` constructor. When adding a new feature, create a new cog module under `cogs/` and register it in `main.py`.

**Admin gate**: [admin.py](admin.py) is the **single source of truth** for `ADMIN_COMMANDS` (a `frozenset`). `main.py` defines a global `@bot.check` (`admin_role_gate`) that restricts those commands to guild admins/managers or roles configured per-guild in the `permission_config` table (queried fresh on every check via `load_permission_config(guild_id)`, not cached). The permission panel in `cogs/moderation.py` imports the same `ADMIN_COMMANDS` from `admin.py` to stay in sync. **Any new admin-only command must be added to `ADMIN_COMMANDS` in admin.py** (and its name to `EXPECTED_COMMANDS` in `cogs/diagnostics.py`).

**Centralized error handling**: `main.py`'s `on_command_error` distinguishes "expected" user errors (bad args, missing perms, cooldowns, etc.) from unexpected exceptions. Unexpected errors get a full traceback and expected ones a short notice, routed to the channels configured via `,setlog` (see `cmdlogs.get_channels`) and printed to stdout. Individual cogs can opt out by defining their own local `on_error` handler on a command.

**SQLite persistence, shared connection**: State lives in a single SQLite database, `data/ddcbot.sqlite3` (gitignored, created on first run). [data/db.py](data/db.py) defines `Database`, a thin `sqlite3` wrapper (WAL mode, `row_factory=sqlite3.Row`) that applies numbered SQL migrations from [data/migrations/](data/migrations/) on startup, tracked in a `schema_migrations` table. One `Database` instance is created once in `main.py` and injected into every storage-owning cog's constructor — there is no more per-cog file path or `_load_*`/`_save_*` pair. Each cog exposes small typed helper methods over its own tables instead (e.g. `cmdeco.get_balance`/`add_balance` over the shared `balances` table used by `cmdeco`, `cmdincome`, `cmdjeu`, and `cmdwork`). Mutations are targeted `INSERT ... ON CONFLICT DO UPDATE`/`UPDATE`/`DELETE` statements scoped to the affected row(s), not whole-table dumps — this is what eliminates the old flat-JSON failure modes (non-atomic writes that could corrupt a file on crash, and multiple cogs each holding a stale in-memory copy of the same file and clobbering each other's writes). Per-guild admin config that's a single nested object (`moderation_config`, `permission_config`, `logs_config`) is still stored as a JSON blob in a `config_json` column keyed by `guild_id`, since normalizing it into sub-tables wouldn't add correctness value for low-churn admin data. See [data/migrations/0001_initial.sql](data/migrations/0001_initial.sql) for the full schema.

**Docker deployment**: [Dockerfile](Dockerfile) builds the bot image; [docker-compose.yml](docker-compose.yml) runs it alongside an `updater` service ([docker/updater](docker/updater)) that polls the git remote and rebuilds/restarts the `ddcbot` service on new commits via the mounted `docker.sock`. Requires `.env` (see `.env.example`) with `DDC_TOKEN` and `PROJECT_DIR` (absolute host path to the repo, needed because the updater bind-mounts volumes via the host daemon). The whole `PROJECT_DIR` is bind-mounted into the container, so `data/ddcbot.sqlite3` persists across restarts/rebuilds the same way the old JSON files did — no extra volume config needed. [changelog.py](changelog.py) posts a `git log` summary to `CHANGELOG_CHANNEL_ID` on the first ready event after a new commit is detected, and exposes `,changelog` on demand. It also exposes `,version`, which reports the commit hash of the deployed branch (the only version identifier — see [versioning.py](versioning.py); there is no semver or `VERSION` file).

**Admin panels via persistent Views**: Economy, income, work-config, and game features expose `*panel` commands (`ecopanel`, `incomepanel`, `gamepanel`, etc.) backed by `discord.ui.View` subclasses (e.g. `EconomyPanelView`, `IncomePanelView`, `GamePanelView`) with an `interaction_check` restricting interaction to the command author and a 300s timeout. Follow this pattern for new configurable panels.

**Diagnostics/selftest** ([cogs/diagnostics.py](cogs/diagnostics.py)): maintains `EXPECTED_COMMANDS` — the full set of command names that should be registered across all cogs — plus `REQUIRED_MODULES` and `EXPECTED_TABLES` (checked against `sqlite_master` via the injected `db`; deep mode also runs `PRAGMA integrity_check`). The `,selftest [basic|deep]` command and `run_selftest()` cross-check the live bot's registered commands/cogs against these lists. **Any new user-facing command must be added to `EXPECTED_COMMANDS` in cogs/diagnostics.py**, or selftest/tests will report it missing.

**AI assistant** ([cogs/ai_assistant.py](cogs/ai_assistant.py)): uses `g4f` for LLM calls and lazily imports/initializes `easyocr` (heavy dependency, only loaded on first use via `_get_easyocr_reader`). Mention replies are rate-limited per user (10s).

**Languages/i18n** ([cogs/i18n.py](cogs/i18n.py)): the bot is French-first but supports per-guild (`guild_lang`) and per-user (`user_lang`) language selection (`fr`/`en`) via `,lang` / `,guildlang`. Message strings live in the `STRINGS` dict and are resolved through `t(db, key, guild_id, user_id, ...)`: server language wins over user language, which wins over French. Keys are fallbacks, so untranslated messages degrade to the key/French.

**Translation features** ([cogs/translation.py](cogs/translation.py)): free Google Translate endpoint (no API key) via `aiohttp`. `/translate <texte>` is a slash-only command that replies ephemerally in the same channel (only visible to the requester). `,lang`/`,guildlang` handle per-user/per-guild language selection (`fr`/`en`).

**Other modern features**: `cogs/leveling.py` (XP per message + `,rank`/`,levels`/`,xpconfig`), `cogs/reactroles.py` (reaction roles via message links), `cogs/guild_settings.py` (welcome/leave messages with `{user}`/`{server}`/`{count}` placeholders), `cogs/automod.py` (banned-word filter), persisted giveaways (`cogs/animations.py`, reaction-based entries in `giveaways`/`giveaway_entries`), persisted reminders (`cogs/utility.py` `,rmd`/`,reminders`/`,rmcancel`), and an economy audit trail (`transactions` table + `,transactions`). Work config/state is per-guild (`work_settings.guild_id`, `work_state(guild_id, user_id)`), not a global singleton.

**Command names are English, replies are French**: the bot is French-first in what it *says* — replies, embeds, docstrings, the web interface — but every command name and alias is English, so users type `,birthday`, `,shop`, `,inventory`, never `,anniv` or `,boutique`. `tests/test_command_language.py` fails the build if a French fragment reappears in a command name or alias, and cross-checks that `EXPECTED_COMMANDS` follows any rename.

**Ticket panel vs ticket config**: `,ticketpanel` publishes the button members click to open a ticket — a persistent `discord.ui.View` with fixed `custom_id`s (`ddcbot:ticket:open` / `ddcbot:ticket:close`) and `timeout=None`, re-registered with `bot.add_view` on every `on_ready` so buttons on weeks-old messages keep working. `,ticketconfig` holds the settings, including `enabled` and `close_message`, which previously had no command at all — tickets could only be switched on from the dashboard. Both `,ticket`/`,closeticket` and the buttons go through the same `open_ticket`/`close_and_delete` methods, so there is one code path per action; `open_ticket` returns `(channel, None)` or `(None, reason)` rather than raising, because the button answers ephemerally and the command answers in-channel.

**Web/command parity** ([settings_fields.py](settings_fields.py)): every setting the dashboard exposes must also be reachable from Discord. Transposing a fifteen-field web form into positional arguments would give unusable commands, so a module declares its settings as a `{name: Field}` dict and a single mechanism parses, validates and documents them — `,gameedit <jeu> <champ> <valeur>`, `,casinostyle`, `,shopedit`, `,achievementconfig`, `,welcomepanel`. Calling one without a field prints the fields with their current values. `Field` accepts what a user actually pastes from Discord (`<@&123>` as well as a raw id, `oui`/`on`/`1` for booleans, `#RRGGBB` with or without the hash). `tests/test_settings_fields.py` asserts the field maps still cover every editable column, so a new dashboard input cannot silently become web-only.

**No third-party API keys — ever**: the project's rule is that a feature either works through a keyless public endpoint or is not built. Nothing in the bot may ask the user for an API key, a client secret or a developer account. Existing examples of the pattern: `cogs/translation.py` (free Google Translate endpoint), `cogs/ai_assistant.py` (`g4f`), `cogs/Notifrss.py` (tvmaze, no key), `cogs/steam.py` (public `steamcommunity.com` profile XML and inventory JSON instead of `api.steampowered.com`), `cogs/twitch.py` (the public `gql.twitch.tv` endpoint with Twitch's own public web Client-ID — a shared public constant, not a user credential — instead of the Helix OAuth flow). Server credentials the user already owns are fine (Minecraft RCON password, the dashboard's own `DASHBOARD_TOKEN`/`API_KEY`); what is banned is a key obtained from a third-party developer console. When a requested feature has no keyless path (X/Twitter, Instagram, TikTok), say so and do not build it.

**Shop** ([shop_engine.py](shop_engine.py) + [cogs/boutique.py](cogs/boutique.py)): `,shop` used to list *games* and sell nothing — the only "purchase" was playing — so a ticket-only game had no paid way in and a rank like VIP could not be bought even though it was a box prize. `,shop` is now an alias of `,shop` and the game catalogue moved to `,games` (alias `,casino`). An item sells one of the three things the casino already handles — a game entry (`ticket`), a `role`, or an `item` — so the shop plugs into the existing inventory rather than adding a parallel stock. `check_purchase` returns a refusal *message* or None, keeping every rule (stock, per-player limit, required role, balance) in one testable place. `,buy` grants a role **before** debiting, since a missing permission must not cost the buyer. The shop is also the economy's main sink, which is why `shop_purchases` records revenue.

**Casino engine** ([casino_engine.py](casino_engine.py)): games are *data*, never code. A game is a `casino_games` row plus its `casino_lots`, created from the dashboard or `,addgame`; `kind` selects the draw (`weighted` for boxes/machines, `dice_sum` for lottery-style sum-of-dice payout tables, `dice_guess` for bet-on-a-die). `casino_engine` holds every rule and all randomness with no discord.py import, so it is testable dry and the dashboard imports it to compute the same RTP figures the bot uses; `cogs/jeu.py` only does Discord presentation, role granting and balance moves. **Lot weights matter**: a uniform draw makes most payout tables player-profitable (RTP > 100%), which mints currency indefinitely — `expected_value`/`theoretical_rtp` exist to catch that, and the dashboard flags any game above 100%. A game carries a *list* of access conditions (`casino_games.access_json`), any one of which admits the player: `free`, `price`, `ticket`, or `role` with an id. `resolve_access` walks them cheapest-first, so a role never burns a ticket and a ticket never charges money. An empty list means the historical behaviour — paid if a price is set, free otherwise — so games predating the feature are unchanged. This exists because a ticket used to be a mere payment waiver: a price-0 game reachable by ticket (lottery, lucky die) was in fact playable free and unlimited by anyone. `casino_plays` is the single journal behind cooldowns, per-player counters, quest progress and actual RTP. Quest progress and role-income cooldowns are **per player**: both were previously global counters (`quests.progress`, `role_income.last_collect`), so one member's play blocked or rewarded everyone else. Games, quests and inventory rows with `guild_id = 0` are the pre-migration global ones, visible from every guild and shadowed by a same-slug guild entry — same fallback rule as notes.

**Achievements, automations and welcome channel** ([achievements_engine.py](achievements_engine.py) + [cogs/achievements.py](cogs/achievements.py)): the rules live in the engine with no discord.py, the cog only listens to events and applies rewards. `METRICS` maps a counter name to the SQL that reads it for one member, which is what makes achievements data-driven — new counter, one entry. Counters come from tables other cogs already fill (`invites`, `balances`, `levels`, `casino_plays`) or from `member_activity`, which this cog maintains itself since nothing counted messages or voice time before (`levels` only holds XP, and isn't even per-guild). `balance` and `level` read global tables, so their SQL takes the guild id and ignores it — keeping one call signature. Automations are event → condition → actions, with actions stored as JSON because their shape varies; unknown action kinds and broken JSON are dropped at parse time rather than failing at run time. The welcome channel reuses a saved embed: the bot reposts or edits it on startup and greets newcomers underneath, which is what distinguishes it from `cogs/guild_settings.py` welcome messages.

**Social alerts** ([social_feeds.py](social_feeds.py) + [cogs/socialalerts.py](cogs/socialalerts.py)): YouTube, Reddit, podcasts/RSS and Kick, all keyless. Parsing lives in `social_feeds` with no discord.py and no network, so it is tested against frozen feeds; the cog only does HTTP, announcing and bookkeeping. Details that were found the hard way and must not be undone: Reddit's `.json` returns 403 from a server while `/new.rss` works, so the Reddit source is Atom; `youtube.com` serves its consent page to a plain request, so the session sends `Cookie: SOCS=CAI` or `@handle` resolution silently fails; and a channel page contains several `UC…` ids, where `"channelId"` is often a *recommended* channel — `channel_id=` from the feed link and `"externalId"` are the ones that identify the page. `social_feeds.last_uid` is NULL on creation and the first poll only records a marker, otherwise adding a source would replay its whole backlog into the channel.

**Server modules without external dependencies**: `cogs/birthdays.py` (`,birthday JJ/MM`, optional year, announcement loop plus a day-role removed the next morning; `birthday_announced` is the journal that makes both idempotent), `cogs/tempvoice.py` (joining a hub voice channel creates the member their own, deleted once empty; `tempvoice_channels` tracks ownership), `cogs/statschannels.py` (a counter rendered into a channel name — `KINDS` is the registry of computable counters, all derived from the guild cache with no network call). The stats loop runs every 10 minutes and only writes when the value changed, because Discord throttles channel renames to 2 per 10 minutes per channel.

**Notes are per-guild** (`notes(guild_id, title, content)`, composite PK): `cogs/notes.py` scopes every read/write to `ctx.guild.id`. Notes created before migration `0010` carry `guild_id = 0` and stay readable from every guild as a fallback in `get_note`; any write lands on the current guild and shadows the legacy note.

**Web dashboard** ([web_dashboard/](web_dashboard/)): a FastAPI app reading the same SQLite database as the bot (no Discord connection). `GUILD_MODULES` in [web_dashboard/main.py](web_dashboard/main.py) is the single source of truth for the per-server module list — the sidebar, the server-overview grid and the configured/not-configured status all derive from it, so a new dashboard page means one entry there plus its `module.<slug>` / `module.desc.<slug>` keys in [web_dashboard/i18n.py](web_dashboard/i18n.py). Everything is scoped under `/guild/{guild_id}/<slug>`; there are no global feature pages. Since the dashboard cannot talk to Discord, the bot mirrors server name/icon/member count into `guild_meta` (`sync_guild_meta` in [main.py](main.py), on `on_ready`/`on_guild_join`/`on_guild_update`); templates fall back to the numeric id when the bot hasn't run yet.

## Testing conventions

Tests live in `tests/` and use `unittest.TestCase` (run via pytest), with cogs instantiated directly against a `MagicMock()` bot and a real `Database(path=":memory:")` rather than a live Discord connection or the on-disk database (see `_make_cog()` helpers in `tests/test_diagnostics.py`). `tests/conftest.py` adds the repo root to `sys.path`, and cog modules are imported as `cogs.<module>` (e.g. `from cogs.diagnostics import cmddiagnostics`).
