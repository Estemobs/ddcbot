-- Historique des transactions economiques (audit).
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Rappels persistants (remplacent le asyncio.sleep en memoire).
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    guild_id INTEGER,
    channel_id INTEGER,
    message TEXT NOT NULL,
    remind_at REAL NOT NULL,
    created_at REAL NOT NULL DEFAULT (unixepoch())
);

-- Giveaways persistants avec participation par reaction.
CREATE TABLE IF NOT EXISTS giveaways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    prize TEXT NOT NULL,
    ends_at REAL NOT NULL,
    host_id INTEGER NOT NULL,
    ended INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS giveaway_entries (
    giveaway_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (giveaway_id, user_id)
);

-- Leveling / XP.
CREATE TABLE IF NOT EXISTS levels (
    user_id INTEGER PRIMARY KEY,
    xp INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS xp_config (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    xp_per_message INTEGER NOT NULL DEFAULT 15,
    cooldown_seconds INTEGER NOT NULL DEFAULT 60,
    announce_channel_id INTEGER
);

-- Reaction roles.
CREATE TABLE IF NOT EXISTS reaction_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    emoji TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    UNIQUE (guild_id, message_id, emoji)
);

-- Messages de bienvenue / depart.
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    welcome_enabled INTEGER NOT NULL DEFAULT 0,
    welcome_channel_id INTEGER,
    welcome_message TEXT,
    leave_enabled INTEGER NOT NULL DEFAULT 0,
    leave_channel_id INTEGER,
    leave_message TEXT
);

-- Auto-moderation : mots bannis et config.
CREATE TABLE IF NOT EXISTS automod_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    word TEXT NOT NULL,
    UNIQUE (guild_id, word)
);

CREATE TABLE IF NOT EXISTS automod_config (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    warn_on_match INTEGER NOT NULL DEFAULT 1,
    delete_on_match INTEGER NOT NULL DEFAULT 1,
    log_channel_id INTEGER
);

-- Langue par utilisateur / par serveur.
CREATE TABLE IF NOT EXISTS user_lang (
    user_id INTEGER PRIMARY KEY,
    lang TEXT NOT NULL DEFAULT 'fr'
);

CREATE TABLE IF NOT EXISTS guild_lang (
    guild_id INTEGER PRIMARY KEY,
    lang TEXT NOT NULL DEFAULT 'fr'
);

-- Abonnements a la traduction automatique par salon.
CREATE TABLE IF NOT EXISTS translation_subs (
    user_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    target_lang TEXT NOT NULL,
    PRIMARY KEY (user_id, channel_id)
);
