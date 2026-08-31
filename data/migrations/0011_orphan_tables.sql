-- Tables jusqu'ici creees a la main par les cogs (custom.py, poll.py, twitch.py)
-- au lieu de passer par les migrations : elles echappaient donc au suivi de
-- schema_migrations et a EXPECTED_TABLES du selftest. Definitions reprises a
-- l'identique (CREATE TABLE IF NOT EXISTS : aucun effet sur une base existante).

CREATE TABLE IF NOT EXISTS custom_commands (
    guild_id INTEGER,
    command_name TEXT,
    response TEXT,
    PRIMARY KEY (guild_id, command_name)
);
CREATE INDEX IF NOT EXISTS idx_custom_cmds_guild ON custom_commands(guild_id);

CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    message_id INTEGER,
    question TEXT,
    options_json TEXT,
    created_at REAL DEFAULT (unixepoch()),
    ended INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_polls_guild ON polls(guild_id);
CREATE INDEX IF NOT EXISTS idx_polls_message ON polls(message_id);

CREATE TABLE IF NOT EXISTS twitch_config (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    client_id TEXT,
    client_secret TEXT,
    access_token TEXT,
    refresh_token TEXT,
    expires_at REAL DEFAULT 0,
    enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS twitch_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    user_login TEXT,
    stream_title TEXT,
    stream_url TEXT,
    occurred_at REAL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_twitch_guild ON twitch_config(guild_id);
CREATE INDEX IF NOT EXISTS idx_twitch_notif_guild ON twitch_notifications(guild_id, user_id);
