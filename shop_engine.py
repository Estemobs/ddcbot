"""Boutique : catalogue, regles d'achat et journal des ventes.

Sans discord.py, comme casino_engine : les regles se testent a sec et le
dashboard s'en sert pour valider un article avant enregistrement.

Un article vend une des trois choses que le casino manipule deja — une entree
de jeu (ticket), un grade (role) ou un objet — de sorte que la boutique se
branche sur l'inventaire existant au lieu d'introduire un stock parallele.
"""

ITEM_KINDS = ("ticket", "role", "item")

UNLIMITED_STOCK = -1


class ShopError(Exception):
    """Refus d'achat, message destine au joueur."""


class ShopEngine:
    def __init__(self, db):
        self.db = db

    # ── Catalogue ────────────────────────────────────────────────────────────

    def list_items(self, guild_id: int, include_disabled: bool = False) -> list:
        sql = "SELECT * FROM shop_items WHERE guild_id = ?"
        if not include_disabled:
            sql += " AND enabled = 1"
        sql += " ORDER BY position, price, slug"
        return [dict(r) for r in self.db.fetchall(sql, (guild_id,))]

    def get_item(self, guild_id: int, slug: str):
        row = self.db.fetchone(
            "SELECT * FROM shop_items WHERE guild_id = ? AND LOWER(slug) = LOWER(?)",
            (guild_id, slug),
        )
        return dict(row) if row else None

    def create_item(self, guild_id: int, slug: str, display_name: str, kind: str,
                    value: str, price: float, description: str = "",
                    stock: int = UNLIMITED_STOCK, per_user_limit: int = 0,
                    required_role_id=None, category: str = "") -> int:
        from casino_engine import normalize_slug
        slug = normalize_slug(slug)
        if not slug:
            raise ShopError("Le nom de l'article ne peut pas etre vide.")
        if kind not in ITEM_KINDS:
            raise ShopError(f"Type d'article inconnu : {kind}")
        if kind == "role" and not str(value).isdigit():
            raise ShopError("Un article de type role attend un identifiant de role.")
        if not str(value).strip():
            raise ShopError("Precisez ce que l'article donne.")
        if price < 0:
            raise ShopError("Le prix ne peut pas etre negatif.")
        cur = self.db.execute(
            "INSERT INTO shop_items (guild_id, slug, display_name, description, kind, "
            "value, price, stock, per_user_limit, required_role_id, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, slug) DO UPDATE SET display_name=excluded.display_name, "
            "description=excluded.description, kind=excluded.kind, value=excluded.value, "
            "price=excluded.price, stock=excluded.stock, "
            "per_user_limit=excluded.per_user_limit, "
            "required_role_id=excluded.required_role_id, category=excluded.category",
            (guild_id, slug, display_name or slug, description, kind, str(value),
             price, stock, max(0, per_user_limit), required_role_id, category),
        )
        return cur.lastrowid

    def update_item(self, item_id: int, **fields):
        allowed = {"display_name", "description", "kind", "value", "price", "stock",
                   "per_user_limit", "required_role_id", "category", "enabled", "position"}
        unknown = set(fields) - allowed
        if unknown:
            raise ShopError(f"Champs inconnus : {sorted(unknown)}")
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(
            f"UPDATE shop_items SET {sets} WHERE id = ?", list(fields.values()) + [item_id]
        )

    def delete_item(self, guild_id: int, slug: str) -> bool:
        cur = self.db.execute(
            "DELETE FROM shop_items WHERE guild_id = ? AND LOWER(slug) = LOWER(?)",
            (guild_id, slug),
        )
        return bool(cur.rowcount)

    # ── Achats ───────────────────────────────────────────────────────────────

    def bought_by(self, guild_id: int, user_id: int, slug: str) -> int:
        row = self.db.fetchone(
            "SELECT COALESCE(SUM(quantity), 0) AS n FROM shop_purchases "
            "WHERE guild_id = ? AND user_id = ? AND item_slug = ?",
            (guild_id, user_id, slug),
        )
        return row["n"] if row else 0

    def check_purchase(self, item: dict, guild_id: int, user_id: int, quantity: int,
                       *, balance: float, role_ids=None):
        """Refus d'achat eventuel, sous forme de message. None si l'achat est possible."""
        if quantity < 1:
            return "La quantite doit etre d'au moins 1."
        if not item["enabled"]:
            return f"**{item['display_name']}** n'est pas en vente."

        required = item["required_role_id"]
        if required and int(required) not in set(role_ids or []):
            return f"**{item['display_name']}** est reserve a un role que vous n'avez pas."

        stock = item["stock"]
        if stock != UNLIMITED_STOCK:
            if stock <= 0:
                return f"**{item['display_name']}** est en rupture de stock."
            if quantity > stock:
                return f"Il ne reste que {stock} exemplaire(s) de **{item['display_name']}**."

        limit = item["per_user_limit"]
        if limit:
            already = self.bought_by(guild_id, user_id, item["slug"])
            if already + quantity > limit:
                remaining = max(0, limit - already)
                if remaining == 0:
                    return f"Vous avez atteint la limite sur **{item['display_name']}**."
                return f"Vous ne pouvez en prendre que {remaining} de plus."

        total = float(item["price"]) * quantity
        if balance < total:
            return f"Il vous manque de quoi payer **{total:,.0f}**.".replace(",", " ")
        return None

    def record_purchase(self, guild_id: int, user_id: int, item: dict, quantity: int):
        """Enregistre la vente et decremente le stock limite."""
        total = float(item["price"]) * quantity
        self.db.execute(
            "INSERT INTO shop_purchases (guild_id, user_id, item_slug, quantity, total_price) "
            "VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, item["slug"], quantity, total),
        )
        if item["stock"] != UNLIMITED_STOCK:
            self.db.execute(
                "UPDATE shop_items SET stock = MAX(0, stock - ?) WHERE id = ?",
                (quantity, item["id"]),
            )
        return total

    def sales_stats(self, guild_id: int, slug: str = None) -> dict:
        sql = ("SELECT COALESCE(SUM(quantity), 0) AS units, "
               "COALESCE(SUM(total_price), 0) AS revenue, COUNT(*) AS orders "
               "FROM shop_purchases WHERE guild_id = ?")
        params = [guild_id]
        if slug:
            sql += " AND item_slug = ?"
            params.append(slug)
        row = self.db.fetchone(sql, params)
        return {"units": row["units"], "revenue": row["revenue"], "orders": row["orders"]}


def describe_item(item: dict, currency: str = "", role_names: dict = None) -> str:
    """Ce que l'article donne, en clair."""
    role_names = role_names or {}
    kind, value = item["kind"], item["value"]
    if kind == "ticket":
        return f"🎟️ une entrée pour **{value}**"
    if kind == "role":
        try:
            name = role_names.get(int(value), f"role {value}")
        except (TypeError, ValueError):
            name = f"role {value}"
        return f"🛡️ le rôle **{name}**"
    return f"📦 **{value}**"


def stock_label(item: dict) -> str:
    return "∞" if item["stock"] == UNLIMITED_STOCK else str(item["stock"])
