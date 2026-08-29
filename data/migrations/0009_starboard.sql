-- Systeme Starboard
CREATE TABLE IF NOT EXISTS starboard_config (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    emoji TEXT DEFAULT '🌟',
    min_stars INTEGER DEFAULT 5,
    include_bot_messages INTEGER DEFAULT 0,
    exclude_pinned INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS starboard_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    message_id INTEGER,
    source_message_id INTEGER,
    stars INTEGER DEFAULT 0,
    forwarded_message_id INTEGER,
    UNIQUE(guild_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_starboard_guild ON starboard_config(guild_id);
CREATE INDEX IF NOT EXISTS idx_starboard_entries_guild ON starboard_entries(guild_id);