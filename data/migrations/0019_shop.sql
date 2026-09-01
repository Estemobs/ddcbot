-- Vraie boutique.
--
-- `,shop` listait les jeux sans rien vendre : le seul « achat » possible etait
-- de jouer. Un ticket ne s'obtenait que dans une box, donc un jeu reserve aux
-- tickets n'avait aucune porte d'entree payante, et un role comme VIP ne
-- pouvait pas s'acheter alors qu'il servait de lot.
--
-- Un article vend une des trois choses que le casino manipule deja :
--   ticket : une entree pour un jeu, deposee dans l'inventaire
--   role   : un grade attribue immediatement
--   item   : un objet decoratif dans l'inventaire
CREATE TABLE IF NOT EXISTS shop_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    slug TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'ticket',
    value TEXT NOT NULL DEFAULT '',        -- slug du jeu, id du role, ou nom de l'objet
    price REAL NOT NULL DEFAULT 0,
    stock INTEGER NOT NULL DEFAULT -1,     -- -1 = illimite
    per_user_limit INTEGER NOT NULL DEFAULT 0,  -- 0 = illimite
    required_role_id INTEGER,              -- achat reserve aux porteurs de ce role
    category TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL DEFAULT (unixepoch()),
    UNIQUE (guild_id, slug)
);

-- Journal des achats : sert aux limites par joueur et au suivi des ventes.
CREATE TABLE IF NOT EXISTS shop_purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    item_slug TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    total_price REAL NOT NULL DEFAULT 0,
    bought_at REAL NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_shop_purchases_user
    ON shop_purchases(guild_id, user_id, item_slug);
