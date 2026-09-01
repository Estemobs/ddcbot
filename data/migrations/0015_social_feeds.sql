-- Alertes sociales, toutes sans cle d'API.
--
-- kind :
--   youtube  flux Atom officiel /feeds/videos.xml?channel_id=UC...
--   reddit   flux Atom /r/<sub>/new.rss (le .json de Reddit renvoie 403 depuis
--            un hebergeur, le flux RSS non)
--   rss      flux RSS 2.0 ou Atom quelconque, ce qui couvre les podcasts
--   kick     kick.com/api/v2/channels/<slug>, public
--
-- last_uid porte le dernier element vu. Il vaut NULL a la creation : le premier
-- passage se contente de l'enregistrer, sinon toute la source serait annoncee
-- d'un coup.
CREATE TABLE IF NOT EXISTS social_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    target TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    channel_id INTEGER NOT NULL,
    mention TEXT NOT NULL DEFAULT '',      -- @everyone, un role, ou vide
    last_uid TEXT,
    last_check REAL NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL DEFAULT (unixepoch()),
    UNIQUE (guild_id, kind, target)
);
CREATE INDEX IF NOT EXISTS idx_social_feeds_guild ON social_feeds(guild_id);
