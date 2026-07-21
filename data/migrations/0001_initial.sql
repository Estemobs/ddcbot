-- Schéma initial : remplace le stockage JSON plat par des tables SQLite.
-- Une table par responsabilité de cog ; voir CLAUDE.md pour le mapping cog -> table.

CREATE TABLE IF NOT EXISTS balances (
    user_id INTEGER PRIMARY KEY,
    amount REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS economy_config (
    guild_id INTEGER PRIMARY KEY,
    allow_transfers INTEGER NOT NULL DEFAULT 1,
    max_transfer REAL NOT NULL DEFAULT 10000,
    allow_negative_balances INTEGER NOT NULL DEFAULT 0,
    log_channel_id INTEGER
);

CREATE TABLE IF NOT EXISTS role_income (
    role_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    collect_interval INTEGER NOT NULL,
    last_collect REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS income_config (
    guild_id INTEGER PRIMARY KEY,
    collect_enabled INTEGER NOT NULL DEFAULT 1,
    default_amount REAL NOT NULL DEFAULT 100,
    default_interval_hours INTEGER NOT NULL DEFAULT 24,
    log_channel_id INTEGER
);

-- Singleton : configuration globale du travail, non liée à un serveur (comme workconfig.json aujourd'hui).
CREATE TABLE IF NOT EXISTS work_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    min_amount REAL NOT NULL,
    max_amount REAL NOT NULL,
    reward_tiers INTEGER NOT NULL,
    cooldown INTEGER NOT NULL,
    rewards_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_state (
    user_id INTEGER PRIMARY KEY,
    work_count INTEGER NOT NULL DEFAULT 0,
    last_worked REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS games (
    name TEXT PRIMARY KEY,
    num_lots INTEGER NOT NULL,
    lots_json TEXT NOT NULL,
    game_price REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS quests (
    name TEXT PRIMARY KEY,
    lot_count INTEGER NOT NULL,
    lot_json TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS inventory_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    item_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_panel_config (
    guild_id INTEGER PRIMARY KEY,
    openlot_enabled INTEGER NOT NULL DEFAULT 1,
    quests_enabled INTEGER NOT NULL DEFAULT 1,
    announce_win_public INTEGER NOT NULL DEFAULT 1,
    log_channel_id INTEGER
);

-- Objet imbriqué warn/actions/defaults/notifications conservé en blob JSON (peu de churn, admin uniquement).
CREATE TABLE IF NOT EXISTS moderation_config (
    guild_id INTEGER PRIMARY KEY,
    config_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS warn_counts (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS permission_config (
    guild_id INTEGER PRIMARY KEY,
    config_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs_config (
    guild_id INTEGER PRIMARY KEY,
    config_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    title TEXT PRIMARY KEY,
    content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    show_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    number INTEGER NOT NULL,
    airdate TEXT NOT NULL,
    user_id INTEGER NOT NULL
);
