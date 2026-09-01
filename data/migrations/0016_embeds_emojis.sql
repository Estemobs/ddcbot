-- Messages Embed enregistres, reutilisables et modifiables apres envoi.
-- channel_id/message_id retiennent le dernier envoi : c'est ce qui permet de
-- corriger une annonce en place au lieu d'en reposter une.
CREATE TABLE IF NOT EXISTS embeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '#5865F2',
    url TEXT NOT NULL DEFAULT '',
    author_name TEXT NOT NULL DEFAULT '',
    author_icon TEXT NOT NULL DEFAULT '',
    footer_text TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    thumbnail_url TEXT NOT NULL DEFAULT '',
    fields_json TEXT NOT NULL DEFAULT '[]',
    content TEXT NOT NULL DEFAULT '',      -- texte hors embed (mentions)
    channel_id INTEGER,
    message_id INTEGER,
    updated_at REAL NOT NULL DEFAULT (unixepoch()),
    UNIQUE (guild_id, name)
);

-- Miroir des emojis du serveur. Le dashboard n'a pas de connexion Discord :
-- sans ce miroir il ne peut rien afficher, comme pour guild_meta.
CREATE TABLE IF NOT EXISTS guild_emojis (
    emoji_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    animated INTEGER NOT NULL DEFAULT 0,
    url TEXT NOT NULL DEFAULT '',
    synced_at REAL NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_guild_emojis_guild ON guild_emojis(guild_id);
