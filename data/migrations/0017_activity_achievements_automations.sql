-- 1) Activite des membres : compteurs necessaires aux succes.
-- Rien n'existait : `levels` ne stocke que l'XP, sans nombre de messages ni
-- temps en vocal, et n'est meme pas scope par serveur.
CREATE TABLE IF NOT EXISTS member_activity (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    messages INTEGER NOT NULL DEFAULT 0,
    voice_seconds INTEGER NOT NULL DEFAULT 0,
    reactions INTEGER NOT NULL DEFAULT 0,
    first_seen REAL NOT NULL DEFAULT (unixepoch()),
    last_seen REAL NOT NULL DEFAULT (unixepoch()),
    PRIMARY KEY (guild_id, user_id)
);

-- 2) Succes : "atteindre N sur un compteur -> recompense", evalue par joueur.
CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '🏅',
    -- messages | voice_minutes | reactions | level | invites | balance |
    -- casino_plays | seniority_days
    metric TEXT NOT NULL DEFAULT 'messages',
    goal INTEGER NOT NULL DEFAULT 1,
    reward_kind TEXT NOT NULL DEFAULT 'none',   -- none | money | role
    reward_value TEXT NOT NULL DEFAULT '',
    announce INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    UNIQUE (guild_id, name)
);

CREATE TABLE IF NOT EXISTS achievement_unlocks (
    achievement_id INTEGER NOT NULL REFERENCES achievements(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    unlocked_at REAL NOT NULL DEFAULT (unixepoch()),
    PRIMARY KEY (achievement_id, user_id)
);

CREATE TABLE IF NOT EXISTS achievement_config (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1
);

-- 3) Automatisations : evenement -> condition -> actions.
-- Les actions sont une liste JSON parce que leur forme depend du type ; le
-- reste est normalise pour rester filtrable en SQL.
CREATE TABLE IF NOT EXISTS automations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    event TEXT NOT NULL,                    -- member_join | member_leave | message |
                                            -- reaction_add | boost | achievement
    match_type TEXT NOT NULL DEFAULT 'any', -- any | contains | equals | regex | role | channel
    match_value TEXT NOT NULL DEFAULT '',
    actions_json TEXT NOT NULL DEFAULT '[]',
    cooldown_seconds INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    runs INTEGER NOT NULL DEFAULT 0,
    last_run REAL NOT NULL DEFAULT 0,
    UNIQUE (guild_id, name)
);

-- 4) Salon d'accueil : un embed enregistre, maintenu en tete d'un salon, sous
-- lequel les nouveaux membres sont salues.
CREATE TABLE IF NOT EXISTS welcome_panel (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    embed_name TEXT NOT NULL DEFAULT '',
    greet_template TEXT NOT NULL DEFAULT 'Bienvenue {user} sur {server} ! Tu es le membre n°{count}.',
    message_id INTEGER,
    enabled INTEGER NOT NULL DEFAULT 0
);
