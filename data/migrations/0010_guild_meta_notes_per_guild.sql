-- Metadonnees des serveurs (nom, icone, nb de membres).
-- Le dashboard web n'a pas de connexion Discord : c'est le bot qui alimente
-- cette table (on_ready / on_guild_join / on_guild_update), le dashboard la lit.
CREATE TABLE IF NOT EXISTS guild_meta (
    guild_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    icon_url TEXT,
    member_count INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT (unixepoch())
);

-- Notes desormais scopees par serveur (etaient globales : title seul en cle).
-- Les notes existantes sont conservees sous guild_id = 0 : elles restent
-- lisibles depuis n'importe quel serveur (repli dans cmdnotes.get_note), mais
-- toute nouvelle ecriture est rattachee au serveur courant.
CREATE TABLE IF NOT EXISTS notes_per_guild (
    guild_id INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (guild_id, title)
);

INSERT OR IGNORE INTO notes_per_guild (guild_id, title, content)
SELECT 0, title, content FROM notes;

DROP TABLE notes;
ALTER TABLE notes_per_guild RENAME TO notes;
