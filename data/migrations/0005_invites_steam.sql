-- Suivi des invitations (intègre ProjetsDivers/invitation.py) :
-- par utilisateur, par serveur. `invited` = total, `left` = départs,
-- `remained` = invités encore présents (calculé). Persistance SQLite.
CREATE TABLE IF NOT EXISTS invites (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    invited INTEGER NOT NULL DEFAULT 0,
    left INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

-- Configuration Steam (intègre ProjetsDivers/CSGO.py) : clé API par serveur.
CREATE TABLE IF NOT EXISTS steam_config (
    guild_id INTEGER PRIMARY KEY,
    api_key TEXT
);
