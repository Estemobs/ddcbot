-- Moteur de jeux configurable.
--
-- Une box, une machine, un loto et un de de la chance sont le meme objet :
-- une mise, un tirage, une recompense. Seule la facon de tirer change, d'ou
-- la colonne `kind`. Le game master cree autant de jeux qu'il veut de chaque
-- type sans toucher au code : tout (prix, lots, poids, cooldown) vit ici.

CREATE TABLE IF NOT EXISTS casino_games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL DEFAULT 0,
    slug TEXT NOT NULL,                        -- nom court tape par les joueurs
    display_name TEXT NOT NULL,
    -- 'weighted'   : tirage pondere dans casino_lots (box, machine)
    -- 'dice_sum'   : somme de N des, gain indexe sur la somme (loto or)
    -- 'dice_guess' : le joueur parie une valeur, gain si le de tombe dessus
    kind TEXT NOT NULL DEFAULT 'weighted',
    category TEXT NOT NULL DEFAULT '',         -- libre : 'box', 'machine'... sert aux quetes
    price REAL NOT NULL DEFAULT 0,
    cooldown_seconds INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    description TEXT NOT NULL DEFAULT '',
    config_json TEXT NOT NULL DEFAULT '{}',    -- parametres propres au kind
    created_at REAL NOT NULL DEFAULT (unixepoch()),
    UNIQUE (guild_id, slug)
);

-- Lots d'un jeu. `weight` porte la rarete (un tirage uniforme rend la plupart
-- des grilles de gains rentables pour le joueur, donc ruineuses pour le serveur).
-- `outcome` n'est utilise que par 'dice_sum' : la somme de des concernee.
CREATE TABLE IF NOT EXISTS casino_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES casino_games(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    reward_kind TEXT NOT NULL DEFAULT 'money', -- 'money' | 'role' | 'ticket' | 'item' | 'nothing'
    reward_value TEXT NOT NULL DEFAULT '0',
    label TEXT NOT NULL DEFAULT '',
    weight REAL NOT NULL DEFAULT 1,
    outcome INTEGER
);
CREATE INDEX IF NOT EXISTS idx_casino_lots_game ON casino_lots(game_id);

-- Journal des parties. Source unique des cooldowns, des compteurs par joueur,
-- de la progression des quetes et du RTP reel.
CREATE TABLE IF NOT EXISTS casino_plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    game_slug TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    cost REAL NOT NULL DEFAULT 0,
    payout REAL NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '',
    played_at REAL NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_casino_plays_user ON casino_plays(guild_id, user_id, game_slug);
CREATE INDEX IF NOT EXISTS idx_casino_plays_time ON casino_plays(guild_id, played_at);

-- Inventaire : tickets d'ouverture gratuite et objets purement decoratifs.
CREATE TABLE IF NOT EXISTS casino_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL DEFAULT 0,
    user_id INTEGER NOT NULL,
    item_kind TEXT NOT NULL DEFAULT 'ticket',  -- 'ticket' (vers un slug de jeu) | 'item'
    item_name TEXT NOT NULL,
    acquired_at REAL NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_casino_inv_user ON casino_inventory(guild_id, user_id);

-- Quetes et paliers : "faire N fois X -> recompense", evalue PAR JOUEUR.
CREATE TABLE IF NOT EXISTS casino_quests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    -- 'game' : un slug precis | 'category' : 'box', 'machine'... | 'any' : tout jeu
    target_kind TEXT NOT NULL DEFAULT 'any',
    target_value TEXT NOT NULL DEFAULT '',
    goal INTEGER NOT NULL DEFAULT 1,
    reward_kind TEXT NOT NULL DEFAULT 'money',
    reward_value TEXT NOT NULL DEFAULT '0',
    repeatable INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    UNIQUE (guild_id, name)
);

CREATE TABLE IF NOT EXISTS casino_quest_claims (
    quest_id INTEGER NOT NULL REFERENCES casino_quests(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    claimed_count INTEGER NOT NULL DEFAULT 0,
    last_claim_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (quest_id, user_id)
);

-- Revenu par role : le cooldown etait stocke sur role_income.last_collect, donc
-- partage par tous les porteurs du role — le premier a collecter bloquait les
-- autres. L'etat devient (role, joueur).
CREATE TABLE IF NOT EXISTS role_income_state (
    role_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    last_collect REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (role_id, user_id)
);

-- Paliers de recompense a l'invitation, entierement configurables.
CREATE TABLE IF NOT EXISTS invite_rewards (
    guild_id INTEGER NOT NULL,
    threshold INTEGER NOT NULL,
    amount REAL NOT NULL,
    PRIMARY KEY (guild_id, threshold)
);

CREATE TABLE IF NOT EXISTS invite_reward_claims (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    threshold INTEGER NOT NULL,
    claimed_at REAL NOT NULL DEFAULT (unixepoch()),
    PRIMARY KEY (guild_id, user_id, threshold)
);

-- Presentation et effets d'animation du casino, par serveur. Le cog fait
-- defiler des symboles en editant son message avant de reveler le resultat ;
-- tout est parametrable, y compris la desactivation complete.
CREATE TABLE IF NOT EXISTS casino_config (
    guild_id INTEGER PRIMARY KEY,
    animations_enabled INTEGER NOT NULL DEFAULT 1,
    frame_count INTEGER NOT NULL DEFAULT 4,
    frame_delay_ms INTEGER NOT NULL DEFAULT 650,
    reel_symbols TEXT NOT NULL DEFAULT '🍒,🍋,🍇,🔔,💎,7️⃣',
    reel_width INTEGER NOT NULL DEFAULT 3,
    suspense_text TEXT NOT NULL DEFAULT 'Tirage en cours…',
    win_emoji TEXT NOT NULL DEFAULT '🎉',
    lose_emoji TEXT NOT NULL DEFAULT '💸',
    win_color TEXT NOT NULL DEFAULT '#57F287',
    lose_color TEXT NOT NULL DEFAULT '#ED4245',
    jackpot_threshold REAL NOT NULL DEFAULT 0,
    jackpot_text TEXT NOT NULL DEFAULT '💥 JACKPOT 💥',
    announce_channel_id INTEGER,
    currency_symbol TEXT NOT NULL DEFAULT '$'
);

-- Solde credite a l'arrivee sur le serveur (0 = desactive).
ALTER TABLE economy_config ADD COLUMN starting_balance REAL NOT NULL DEFAULT 0;

-- Reprise de l'existant. games/quests/inventory_tickets etaient globaux (pas de
-- guild_id) : ils atterrissent sous guild_id = 0, que le moteur traite comme
-- "tous serveurs", comme pour les notes heritees.
INSERT INTO casino_games (guild_id, slug, display_name, kind, category, price, description)
SELECT 0, name, name, 'weighted', 'box', game_price, 'Repris de l''ancien systeme'
FROM games
WHERE NOT EXISTS (SELECT 1 FROM casino_games c WHERE c.guild_id = 0 AND c.slug = games.name);

-- Les lots vivaient dans un blob JSON [{"argent": "150"}, {"grade": "42"}] :
-- json_each l'aplatit en lignes. Poids uniformes au depart, comme le tirage
-- d'origine — c'est au game master de les ajuster ensuite.
INSERT INTO casino_lots (game_id, position, reward_kind, reward_value, weight)
SELECT c.id, l.key,
       CASE k.key
           WHEN 'argent' THEN 'money'
           WHEN 'grade'  THEN 'role'
           WHEN 'ticket' THEN 'ticket'
           ELSE k.key
       END,
       k.value, 1
FROM games g
JOIN casino_games c ON c.guild_id = 0 AND c.slug = g.name
JOIN json_each(g.lots_json) l
JOIN json_each(l.value) k
WHERE NOT EXISTS (SELECT 1 FROM casino_lots cl WHERE cl.game_id = c.id);

INSERT INTO casino_inventory (guild_id, user_id, item_kind, item_name)
SELECT 0, user_id, 'ticket', item_name FROM inventory_tickets;

INSERT INTO casino_quests (guild_id, name, description, target_kind, target_value, goal, reward_kind, reward_value, repeatable)
SELECT 0, name, 'Repris de l''ancien systeme', 'game', name, lot_count, 'money', '0', 1
FROM quests
WHERE NOT EXISTS (SELECT 1 FROM casino_quests q WHERE q.guild_id = 0 AND q.name = quests.name);

-- Recompense des quetes reprises (lot_json = {"argent": "1000"}).
UPDATE casino_quests SET
    reward_kind = COALESCE((
        SELECT CASE k.key WHEN 'argent' THEN 'money' WHEN 'grade' THEN 'role'
                          WHEN 'ticket' THEN 'ticket' ELSE k.key END
        FROM quests q, json_each(q.lot_json) k
        WHERE q.name = casino_quests.name LIMIT 1), reward_kind),
    reward_value = COALESCE((
        SELECT k.value FROM quests q, json_each(q.lot_json) k
        WHERE q.name = casino_quests.name LIMIT 1), reward_value)
WHERE guild_id = 0 AND EXISTS (SELECT 1 FROM quests q WHERE q.name = casino_quests.name);

-- Reprise des derniers collects : chaque porteur repart du timestamp du role,
-- ce qui evite un versement immediat en double juste apres la migration.
INSERT OR IGNORE INTO role_income_state (role_id, user_id, last_collect)
SELECT role_id, 0, last_collect FROM role_income;
