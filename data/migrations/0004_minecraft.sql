-- Pont Discord <-> Minecraft (remplace NerdMC) : configuration par serveur.
CREATE TABLE IF NOT EXISTS minecraft_config (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    log_path TEXT,
    method TEXT NOT NULL DEFAULT 'tmux',
    tmux_session TEXT,
    use_sudo INTEGER NOT NULL DEFAULT 0,
    rcon_host TEXT,
    rcon_port INTEGER,
    rcon_password TEXT,
    enabled INTEGER NOT NULL DEFAULT 0
);
