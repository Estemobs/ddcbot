-- AI-Moderation
CREATE TABLE IF NOT EXISTS ai_moderation_config (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    action TEXT NOT NULL DEFAULT 'warn',
    log_channel_id INTEGER,
    threshold REAL NOT NULL DEFAULT 0.7,
    cooldown_seconds INTEGER NOT NULL DEFAULT 10
);

CREATE TABLE IF NOT EXISTS ai_moderation_ignored_roles (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);

-- Tickets
CREATE TABLE IF NOT EXISTS ticket_config (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    category_id INTEGER,
    log_channel_id INTEGER,
    welcome_message TEXT NOT NULL DEFAULT 'Bienvenue dans votre ticket.',
    close_message TEXT NOT NULL DEFAULT 'Ticket ferme.',
    max_open_tickets INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at REAL NOT NULL,
    closed_at REAL
);

CREATE TABLE IF NOT EXISTS ticket_counter (
    guild_id INTEGER PRIMARY KEY,
    counter INTEGER NOT NULL DEFAULT 0
);

-- Webhooks
CREATE TABLE IF NOT EXISTS webhook_config (
    guild_id INTEGER PRIMARY KEY,
    webhook_url TEXT,
    enabled INTEGER NOT NULL DEFAULT 0,
    events_json TEXT
);

-- Lockdown
CREATE TABLE IF NOT EXISTS lockdown_config (
    guild_id INTEGER PRIMARY KEY,
    lockdown_role_id INTEGER,
    log_channel_id INTEGER,
    auto_lockon_mass_join INTEGER NOT NULL DEFAULT 0,
    mass_join_threshold INTEGER NOT NULL DEFAULT 10,
    mass_join_window_seconds INTEGER NOT NULL DEFAULT 60
);
