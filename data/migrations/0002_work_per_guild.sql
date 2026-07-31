-- La configuration du travail et l'etat par utilisateur deviennent par serveur.
-- (L'ancien singleton global id=1 ne peut pas etre attribue a un serveur : la
-- configuration est simplement reinitialisee, l'admin la reconfigure par serveur.)

DROP TABLE IF EXISTS work_settings;
CREATE TABLE work_settings (
    guild_id INTEGER PRIMARY KEY,
    min_amount REAL NOT NULL,
    max_amount REAL NOT NULL,
    reward_tiers INTEGER NOT NULL,
    cooldown INTEGER NOT NULL,
    rewards_json TEXT NOT NULL
);

DROP TABLE IF EXISTS work_state;
CREATE TABLE work_state (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    work_count INTEGER NOT NULL DEFAULT 0,
    last_worked REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);
