-- Twitch sans cle d'API.
--
-- L'ancienne version exigeait un client_id et un client_secret Twitch par
-- serveur (api.twitch.tv + id.twitch.tv/oauth2). Le cog passe desormais par le
-- endpoint GraphQL public du site twitch.tv, qui ne demande ni compte ni cle.
-- Les colonnes client_id / client_secret / access_token / refresh_token restent
-- en base pour ne pas casser les installations existantes, mais ne sont plus lues.

-- Chaines suivies. twitch_notifications melangeait la liste des chaines et le
-- journal des annonces, ce qui recreait une ligne a chaque passage de boucle.
CREATE TABLE IF NOT EXISTS twitch_watch (
    guild_id INTEGER NOT NULL,
    user_login TEXT NOT NULL,
    added_by INTEGER,
    added_at REAL NOT NULL DEFAULT (unixepoch()),
    PRIMARY KEY (guild_id, user_login)
);

-- Reprise des chaines deja suivies.
INSERT OR IGNORE INTO twitch_watch (guild_id, user_login, added_by)
SELECT DISTINCT guild_id, LOWER(user_login), user_id FROM twitch_notifications
WHERE user_login IS NOT NULL AND user_login <> '';

-- Identifiant du direct deja annonce : evite de re-annoncer le meme stream a
-- chaque tour de boucle.
ALTER TABLE twitch_notifications ADD COLUMN stream_id TEXT;
