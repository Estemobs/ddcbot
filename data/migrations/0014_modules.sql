-- Trois modules serveur, tous sans dependance externe.

-- 1) Anniversaires. La date est stockee sans annee obligatoire : beaucoup de
-- membres donnent leur jour/mois sans vouloir reveler leur age.
CREATE TABLE IF NOT EXISTS birthday_config (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER,                       -- role donne le jour J, retire le lendemain
    message TEXT NOT NULL DEFAULT 'Joyeux anniversaire {user} ! 🎂',
    announce_hour INTEGER NOT NULL DEFAULT 9,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS birthdays (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    day INTEGER NOT NULL,
    month INTEGER NOT NULL,
    year INTEGER,
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_birthdays_date ON birthdays(guild_id, month, day);

-- Journal des annonces : evite de re-annoncer le meme anniversaire si la boucle
-- repasse dans la journee, et sert a retirer le role le lendemain.
CREATE TABLE IF NOT EXISTS birthday_announced (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    announced_on TEXT NOT NULL,            -- AAAA-MM-JJ
    PRIMARY KEY (guild_id, user_id, announced_on)
);

-- 2) Salons vocaux temporaires. Rejoindre le salon "hub" cree un vocal a soi,
-- supprime des qu'il se vide.
CREATE TABLE IF NOT EXISTS tempvoice_config (
    guild_id INTEGER PRIMARY KEY,
    hub_channel_id INTEGER,
    category_id INTEGER,
    name_template TEXT NOT NULL DEFAULT 'Salon de {user}',
    user_limit INTEGER NOT NULL DEFAULT 0, -- 0 = illimite
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tempvoice_channels (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    created_at REAL NOT NULL DEFAULT (unixepoch())
);

-- 3) Salons de statistiques : des salons dont le nom affiche un compteur.
-- Discord limite fortement le renommage de salon (2 par 10 min et par salon),
-- d'ou l'intervalle par defaut a 10 minutes.
CREATE TABLE IF NOT EXISTS stats_channels (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    kind TEXT NOT NULL,                    -- members | humans | bots | online | boosts | roles | channels | role
    template TEXT NOT NULL DEFAULT '{label} : {value}',
    role_id INTEGER,                       -- pour kind = 'role'
    last_value TEXT,
    last_update REAL NOT NULL DEFAULT 0
);
