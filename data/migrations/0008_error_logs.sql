-- Journalisation des erreurs du bot
CREATE TABLE IF NOT EXISTS error_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    command TEXT,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    traceback TEXT,
    occurred_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_error_logs_guild ON error_logs(guild_id);
CREATE INDEX IF NOT EXISTS idx_error_logs_command ON error_logs(command);
CREATE INDEX IF NOT EXISTS idx_error_logs_occurred ON error_logs(occurred_at DESC);
