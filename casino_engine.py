"""Moteur de jeux du casino : catalogue, tirages, inventaire, quetes, stats.

Volontairement sans dependance a discord.py : tout ce qui touche au hasard et
aux regles est ici, testable a sec, et le cog ne garde que l'affichage et
l'attribution des roles. Le dashboard web importe le meme module pour calculer
les RTP sans dupliquer les formules.

Rien n'est code en dur : un jeu est une ligne de `casino_games` plus ses lots.
Trois facons de tirer, qui couvrent box, machines, loto et de :

- ``weighted``   tirage pondere parmi les lots (box, machines)
- ``dice_sum``   somme de N des, le gain est indexe sur la somme (loto or)
- ``dice_guess`` le joueur parie une valeur, gain si le de tombe dessus

Les jeux, quetes et objets portes par ``guild_id = 0`` sont ceux repris de
l'ancien systeme, qui etait global : ils restent visibles depuis tous les
serveurs, et un jeu du serveur portant le meme slug les masque.
"""

import json
import random
import time

# Types de recompense qu'un lot ou une quete peut donner.
REWARD_KINDS = ("money", "role", "ticket", "item", "nothing")
GAME_KINDS = ("weighted", "dice_sum", "dice_guess")

LEGACY_GUILD = 0


class CasinoError(Exception):
    """Erreur de regle du jeu, destinee a etre montree au joueur."""


class Reward:
    """Recompense tiree, avant application (l'attribution de role est au cog)."""

    __slots__ = ("kind", "value", "label")

    def __init__(self, kind: str, value: str, label: str = ""):
        self.kind = kind
        self.value = value
        self.label = label

    @property
    def money(self) -> float:
        """Montant en pieces, 0 si la recompense n'est pas de l'argent."""
        if self.kind != "money":
            return 0.0
        try:
            return float(self.value)
        except (TypeError, ValueError):
            return 0.0

    def describe(self) -> str:
        if self.label:
            return self.label
        if self.kind == "money":
            return f"{self.money:,.0f} pieces".replace(",", " ")
        if self.kind == "role":
            return f"role {self.value}"
        if self.kind == "ticket":
            return f"ticket {self.value}"
        if self.kind == "item":
            return str(self.value)
        return "rien"

    def __repr__(self):
        return f"Reward({self.kind!r}, {self.value!r})"


class Outcome:
    """Resultat complet d'une partie."""

    __slots__ = ("reward", "detail", "roll")

    def __init__(self, reward: Reward, detail: str = "", roll=None):
        self.reward = reward
        self.detail = detail
        self.roll = roll


class CasinoEngine:
    def __init__(self, db, rng=None):
        self.db = db
        self.rng = rng or random

    # ── Catalogue ────────────────────────────────────────────────────────────

    def list_games(self, guild_id: int, include_disabled: bool = False) -> list:
        """Jeux du serveur, plus les jeux herites non masques par un slug local."""
        sql = (
            "SELECT * FROM casino_games WHERE guild_id IN (?, ?) "
            + ("" if include_disabled else "AND enabled = 1 ")
            + "ORDER BY guild_id DESC, price, slug"
        )
        rows = self.db.fetchall(sql, (guild_id, LEGACY_GUILD))
        seen = set()
        games = []
        for row in rows:
            game = dict(row)
            if game["slug"] in seen:
                continue  # un jeu du serveur masque l'herite de meme slug
            seen.add(game["slug"])
            game["config"] = _load_json(game["config_json"])
            games.append(game)
        return games

    def get_game(self, guild_id: int, slug: str):
        row = self.db.fetchone(
            "SELECT * FROM casino_games WHERE guild_id IN (?, ?) AND slug = ? "
            "ORDER BY guild_id DESC LIMIT 1",
            (guild_id, LEGACY_GUILD, slug),
        )
        if row is None:
            return None
        game = dict(row)
        game["config"] = _load_json(game["config_json"])
        return game

    def create_game(self, guild_id: int, slug: str, display_name: str = "",
                    kind: str = "weighted", category: str = "", price: float = 0,
                    cooldown_seconds: int = 0, description: str = "",
                    config: dict = None) -> int:
        if kind not in GAME_KINDS:
            raise CasinoError(f"Type de jeu inconnu : {kind}")
        slug = normalize_slug(slug)
        if not slug:
            raise CasinoError("Le nom du jeu ne peut pas etre vide.")
        cur = self.db.execute(
            "INSERT INTO casino_games (guild_id, slug, display_name, kind, category, "
            "price, cooldown_seconds, description, config_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, slug) DO UPDATE SET "
            "display_name=excluded.display_name, kind=excluded.kind, "
            "category=excluded.category, price=excluded.price, "
            "cooldown_seconds=excluded.cooldown_seconds, "
            "description=excluded.description, config_json=excluded.config_json",
            (guild_id, slug, display_name or slug, kind, category, price,
             cooldown_seconds, description, json.dumps(config or {})),
        )
        if cur.lastrowid:
            return cur.lastrowid
        return self.get_game(guild_id, slug)["id"]

    def update_game(self, game_id: int, **fields):
        if "config" in fields:
            fields["config_json"] = json.dumps(fields.pop("config"))
        if not fields:
            return
        allowed = {"display_name", "kind", "category", "price", "cooldown_seconds",
                   "enabled", "description", "config_json", "slug"}
        unknown = set(fields) - allowed
        if unknown:
            raise CasinoError(f"Champs inconnus : {sorted(unknown)}")
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(
            f"UPDATE casino_games SET {sets} WHERE id = ?",
            list(fields.values()) + [game_id],
        )

    def delete_game(self, game_id: int):
        self.db.execute("DELETE FROM casino_lots WHERE game_id = ?", (game_id,))
        self.db.execute("DELETE FROM casino_games WHERE id = ?", (game_id,))

    # ── Lots ─────────────────────────────────────────────────────────────────

    def list_lots(self, game_id: int) -> list:
        return [dict(r) for r in self.db.fetchall(
            "SELECT * FROM casino_lots WHERE game_id = ? ORDER BY position, id", (game_id,)
        )]

    def add_lot(self, game_id: int, reward_kind: str, reward_value, label: str = "",
                weight: float = 1, outcome=None, position=None) -> int:
        if reward_kind not in REWARD_KINDS:
            raise CasinoError(f"Type de lot inconnu : {reward_kind}")
        if weight < 0:
            raise CasinoError("Un poids ne peut pas etre negatif.")
        if position is None:
            row = self.db.fetchone(
                "SELECT COALESCE(MAX(position), -1) + 1 AS p FROM casino_lots WHERE game_id = ?",
                (game_id,),
            )
            position = row["p"]
        cur = self.db.execute(
            "INSERT INTO casino_lots (game_id, position, reward_kind, reward_value, "
            "label, weight, outcome) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (game_id, position, reward_kind, str(reward_value), label, weight, outcome),
        )
        return cur.lastrowid

    def update_lot(self, lot_id: int, **fields):
        allowed = {"reward_kind", "reward_value", "label", "weight", "outcome", "position"}
        unknown = set(fields) - allowed
        if unknown:
            raise CasinoError(f"Champs inconnus : {sorted(unknown)}")
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(
            f"UPDATE casino_lots SET {sets} WHERE id = ?", list(fields.values()) + [lot_id]
        )

    def delete_lot(self, lot_id: int):
        self.db.execute("DELETE FROM casino_lots WHERE id = ?", (lot_id,))

    # ── Cooldowns et compteurs ───────────────────────────────────────────────

    def last_play_at(self, guild_id: int, user_id: int, slug: str) -> float:
        row = self.db.fetchone(
            "SELECT MAX(played_at) AS t FROM casino_plays "
            "WHERE guild_id = ? AND user_id = ? AND game_slug = ?",
            (guild_id, user_id, slug),
        )
        return row["t"] or 0.0

    def cooldown_remaining(self, guild_id: int, user_id: int, game: dict, now=None) -> float:
        """Secondes restantes avant que le joueur puisse rejouer (0 si dispo)."""
        cooldown = game.get("cooldown_seconds") or 0
        if cooldown <= 0:
            return 0.0
        now = time.time() if now is None else now
        elapsed = now - self.last_play_at(guild_id, user_id, game["slug"])
        return max(0.0, cooldown - elapsed)

    def play_count(self, guild_id: int, user_id: int, slug: str = None,
                   category: str = None) -> int:
        """Nombre de parties d'un joueur, filtrable par jeu ou par categorie."""
        sql = "SELECT COUNT(*) AS c FROM casino_plays WHERE guild_id = ? AND user_id = ?"
        params = [guild_id, user_id]
        if slug:
            sql += " AND game_slug = ?"
            params.append(slug)
        if category:
            sql += " AND category = ?"
            params.append(category)
        return self.db.fetchone(sql, params)["c"]

    def play_counts_by_game(self, guild_id: int, user_id: int) -> dict:
        rows = self.db.fetchall(
            "SELECT game_slug, COUNT(*) AS c FROM casino_plays "
            "WHERE guild_id = ? AND user_id = ? GROUP BY game_slug ORDER BY c DESC",
            (guild_id, user_id),
        )
        return {r["game_slug"]: r["c"] for r in rows}

    def record_play(self, guild_id: int, user_id: int, game: dict,
                    cost: float, payout: float, detail: str = ""):
        self.db.execute(
            "INSERT INTO casino_plays (guild_id, user_id, game_slug, category, "
            "cost, payout, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, game["slug"], game.get("category") or "",
             cost, payout, detail),
        )

    # ── Tirages ──────────────────────────────────────────────────────────────

    def draw(self, game: dict, guess=None) -> Outcome:
        """Joue un tour et renvoie le resultat, sans toucher au solde."""
        kind = game.get("kind") or "weighted"
        if kind == "weighted":
            return self._draw_weighted(game)
        if kind == "dice_sum":
            return self._draw_dice_sum(game)
        if kind == "dice_guess":
            return self._draw_dice_guess(game, guess)
        raise CasinoError(f"Type de jeu inconnu : {kind}")

    def _draw_weighted(self, game: dict) -> Outcome:
        lots = [lot for lot in self.list_lots(game["id"]) if lot["weight"] > 0]
        if not lots:
            raise CasinoError("Ce jeu n'a aucun lot configure.")
        weights = [lot["weight"] for lot in lots]
        lot = self.rng.choices(lots, weights=weights, k=1)[0]
        return Outcome(_lot_reward(lot), detail=lot["label"] or "")

    def _draw_dice_sum(self, game: dict) -> Outcome:
        config = game.get("config") or {}
        dice = int(config.get("dice", 2))
        faces = int(config.get("faces", 6))
        if dice < 1 or faces < 2:
            raise CasinoError("Configuration de des invalide.")
        rolls = [self.rng.randint(1, faces) for _ in range(dice)]
        total = sum(rolls)
        lots = {lot["outcome"]: lot for lot in self.list_lots(game["id"])}
        lot = lots.get(total)
        detail = " + ".join(str(r) for r in rolls) + f" = {total}"
        if lot is None:
            return Outcome(Reward("nothing", "0"), detail=detail, roll=rolls)
        return Outcome(_lot_reward(lot), detail=detail, roll=rolls)

    def _draw_dice_guess(self, game: dict, guess) -> Outcome:
        config = game.get("config") or {}
        faces = int(config.get("faces", 6))
        win = float(config.get("win_amount", 0))
        lose = float(config.get("lose_amount", 0))
        if guess is None:
            raise CasinoError(f"Choisissez un chiffre entre 1 et {faces}.")
        try:
            guess = int(guess)
        except (TypeError, ValueError):
            raise CasinoError(f"Choisissez un chiffre entre 1 et {faces}.")
        if not 1 <= guess <= faces:
            raise CasinoError(f"Choisissez un chiffre entre 1 et {faces}.")
        roll = self.rng.randint(1, faces)
        if roll == guess:
            return Outcome(Reward("money", str(win)), detail=f"de : {roll} (gagne)", roll=roll)
        return Outcome(Reward("money", str(-lose)), detail=f"de : {roll} (perdu)", roll=roll)

    # ── Inventaire ───────────────────────────────────────────────────────────

    def add_item(self, guild_id: int, user_id: int, item_name: str,
                 item_kind: str = "ticket"):
        self.db.execute(
            "INSERT INTO casino_inventory (guild_id, user_id, item_kind, item_name) "
            "VALUES (?, ?, ?, ?)",
            (guild_id, user_id, item_kind, item_name),
        )

    def has_ticket(self, guild_id: int, user_id: int, slug: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM casino_inventory WHERE guild_id IN (?, ?) AND user_id = ? "
            "AND item_kind = 'ticket' AND item_name = ? LIMIT 1",
            (guild_id, LEGACY_GUILD, user_id, slug),
        ) is not None

    def take_ticket(self, guild_id: int, user_id: int, slug: str) -> bool:
        """Consomme un ticket d'ouverture. Les tickets herites passent en dernier."""
        row = self.db.fetchone(
            "SELECT id FROM casino_inventory WHERE guild_id IN (?, ?) AND user_id = ? "
            "AND item_kind = 'ticket' AND item_name = ? ORDER BY guild_id DESC LIMIT 1",
            (guild_id, LEGACY_GUILD, user_id, slug),
        )
        if row is None:
            return False
        self.db.execute("DELETE FROM casino_inventory WHERE id = ?", (row["id"],))
        return True

    def inventory(self, guild_id: int, user_id: int) -> dict:
        rows = self.db.fetchall(
            "SELECT item_kind, item_name, COUNT(*) AS c FROM casino_inventory "
            "WHERE guild_id IN (?, ?) AND user_id = ? GROUP BY item_kind, item_name "
            "ORDER BY item_kind, item_name",
            (guild_id, LEGACY_GUILD, user_id),
        )
        return {(r["item_kind"], r["item_name"]): r["c"] for r in rows}

    def clear_inventory(self, guild_id: int, user_id: int) -> int:
        cur = self.db.execute(
            "DELETE FROM casino_inventory WHERE guild_id IN (?, ?) AND user_id = ?",
            (guild_id, LEGACY_GUILD, user_id),
        )
        return cur.rowcount

    # ── Quetes et paliers ────────────────────────────────────────────────────

    def list_quests(self, guild_id: int, include_disabled: bool = False) -> list:
        sql = (
            "SELECT * FROM casino_quests WHERE guild_id IN (?, ?) "
            + ("" if include_disabled else "AND enabled = 1 ")
            + "ORDER BY guild_id DESC, goal"
        )
        return [dict(r) for r in self.db.fetchall(sql, (guild_id, LEGACY_GUILD))]

    def create_quest(self, guild_id: int, name: str, goal: int, reward_kind: str,
                     reward_value, target_kind: str = "any", target_value: str = "",
                     description: str = "", repeatable: bool = False) -> int:
        if reward_kind not in REWARD_KINDS:
            raise CasinoError(f"Type de recompense inconnu : {reward_kind}")
        if target_kind not in ("any", "game", "category", "role"):
            raise CasinoError(f"Cible de quete inconnue : {target_kind}")
        if goal < 1:
            raise CasinoError("L'objectif doit valoir au moins 1.")
        cur = self.db.execute(
            "INSERT INTO casino_quests (guild_id, name, description, target_kind, "
            "target_value, goal, reward_kind, reward_value, repeatable) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, name) DO UPDATE SET description=excluded.description, "
            "target_kind=excluded.target_kind, target_value=excluded.target_value, "
            "goal=excluded.goal, reward_kind=excluded.reward_kind, "
            "reward_value=excluded.reward_value, repeatable=excluded.repeatable",
            (guild_id, name, description, target_kind, target_value, goal,
             reward_kind, str(reward_value), int(repeatable)),
        )
        return cur.lastrowid

    def delete_quest(self, quest_id: int):
        self.db.execute("DELETE FROM casino_quest_claims WHERE quest_id = ?", (quest_id,))
        self.db.execute("DELETE FROM casino_quests WHERE id = ?", (quest_id,))

    def quest_progress(self, guild_id: int, user_id: int, quest: dict,
                       role_ids=None) -> int:
        """Avancement du joueur sur une quete, compte PAR JOUEUR."""
        target = quest["target_kind"]
        if target == "game":
            return self.play_count(guild_id, user_id, slug=quest["target_value"])
        if target == "category":
            return self.play_count(guild_id, user_id, category=quest["target_value"])
        if target == "role":
            if role_ids is None:
                return 0
            try:
                wanted = int(quest["target_value"])
            except (TypeError, ValueError):
                return 0
            return 1 if wanted in set(role_ids) else 0
        return self.play_count(guild_id, user_id)

    def claimed_count(self, quest_id: int, user_id: int) -> int:
        row = self.db.fetchone(
            "SELECT claimed_count FROM casino_quest_claims WHERE quest_id = ? AND user_id = ?",
            (quest_id, user_id),
        )
        return row["claimed_count"] if row else 0

    def claimable_quests(self, guild_id: int, user_id: int, role_ids=None) -> list:
        """Quetes dont la recompense est due au joueur et pas encore versee."""
        due = []
        for quest in self.list_quests(guild_id):
            progress = self.quest_progress(guild_id, user_id, quest, role_ids)
            already = self.claimed_count(quest["id"], user_id)
            if quest["repeatable"]:
                earned = progress // quest["goal"]
            else:
                earned = 1 if progress >= quest["goal"] else 0
            if earned > already:
                due.append((quest, earned - already, progress))
        return due

    def mark_claimed(self, quest_id: int, user_id: int, count: int):
        self.db.execute(
            "INSERT INTO casino_quest_claims (quest_id, user_id, claimed_count, last_claim_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(quest_id, user_id) DO UPDATE SET "
            "claimed_count = claimed_count + excluded.claimed_count, "
            "last_claim_at = excluded.last_claim_at",
            (quest_id, user_id, count, time.time()),
        )

    # ── Presentation et effets ───────────────────────────────────────────────

    def get_style(self, guild_id: int) -> dict:
        """Reglages d'affichage/animation du serveur, defauts si jamais configures."""
        self.db.execute(
            "INSERT OR IGNORE INTO casino_config (guild_id) VALUES (?)", (guild_id,)
        )
        row = self.db.fetchone("SELECT * FROM casino_config WHERE guild_id = ?", (guild_id,))
        style = dict(row)
        style["reels"] = [s for s in (style["reel_symbols"] or "").split(",") if s.strip()]
        return style

    def update_style(self, guild_id: int, **fields):
        self.get_style(guild_id)
        allowed = {
            "animations_enabled", "frame_count", "frame_delay_ms", "reel_symbols",
            "reel_width", "suspense_text", "win_emoji", "lose_emoji", "win_color",
            "lose_color", "jackpot_threshold", "jackpot_text", "announce_channel_id",
            "currency_symbol",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise CasinoError(f"Champs inconnus : {sorted(unknown)}")
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(
            f"UPDATE casino_config SET {sets} WHERE guild_id = ?",
            list(fields.values()) + [guild_id],
        )

    def animation_frames(self, style: dict, final: str = None) -> list:
        """Images successives du defilement, la derniere etant le resultat.

        Le cog edite un seul message avec ces images : c'est ce qui donne
        l'effet de rouleaux qui tournent sans spammer le salon.
        """
        reels = style.get("reels") or ["🎰"]
        width = max(1, int(style.get("reel_width") or 3))
        count = max(0, int(style.get("frame_count") or 0))
        frames = []
        for _ in range(count):
            frames.append(" ".join(self.rng.choice(reels) for _ in range(width)))
        if final is not None:
            frames.append(final)
        return frames

    def is_jackpot(self, style: dict, amount: float) -> bool:
        threshold = style.get("jackpot_threshold") or 0
        return threshold > 0 and amount >= threshold

    # ── Statistiques ─────────────────────────────────────────────────────────

    def expected_value(self, game: dict) -> float:
        """Gain moyen theorique d'une partie, en pieces.

        Sert au game master a voir si un jeu est rentable pour la maison : un
        gain moyen superieur au prix signifie que le jeu cree de la monnaie.
        """
        kind = game.get("kind") or "weighted"
        if kind == "dice_guess":
            config = game.get("config") or {}
            faces = max(2, int(config.get("faces", 6)))
            win = float(config.get("win_amount", 0))
            lose = float(config.get("lose_amount", 0))
            return win / faces - lose * (faces - 1) / faces

        lots = self.list_lots(game["id"])
        if not lots:
            return 0.0

        if kind == "dice_sum":
            config = game.get("config") or {}
            dice = int(config.get("dice", 2))
            faces = int(config.get("faces", 6))
            distribution = dice_sum_distribution(dice, faces)
            by_outcome = {lot["outcome"]: lot for lot in lots}
            total = 0.0
            for outcome, probability in distribution.items():
                lot = by_outcome.get(outcome)
                if lot is not None:
                    total += probability * _lot_reward(lot).money
            return total

        weights = sum(lot["weight"] for lot in lots)
        if weights <= 0:
            return 0.0
        return sum(lot["weight"] * _lot_reward(lot).money for lot in lots) / weights

    def theoretical_rtp(self, game: dict):
        """Part de la mise revenant au joueur en moyenne. None si le jeu est gratuit."""
        price = game.get("price") or 0
        if price <= 0:
            return None
        return self.expected_value(game) / price

    def actual_stats(self, guild_id: int, slug: str = None) -> dict:
        """Ce que le casino a reellement encaisse et verse."""
        sql = ("SELECT COUNT(*) AS plays, COALESCE(SUM(cost), 0) AS cost, "
               "COALESCE(SUM(payout), 0) AS payout FROM casino_plays WHERE guild_id = ?")
        params = [guild_id]
        if slug:
            sql += " AND game_slug = ?"
            params.append(slug)
        row = self.db.fetchone(sql, params)
        cost = row["cost"] or 0.0
        payout = row["payout"] or 0.0
        return {
            "plays": row["plays"],
            "cost": cost,
            "payout": payout,
            "net": cost - payout,
            "rtp": (payout / cost) if cost else None,
        }


# ── Utilitaires ──────────────────────────────────────────────────────────────

def _load_json(raw):
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _lot_reward(lot: dict) -> Reward:
    return Reward(lot["reward_kind"], lot["reward_value"], lot.get("label") or "")


def normalize_slug(name: str) -> str:
    """Slug utilisable en commande : minuscules, espaces en tirets.

    L'ancien systeme imposait `isalpha()`, ce qui interdisait chiffres, espaces
    et tirets — donc « Box bois » ou « machine-saison-1 » etaient refuses.
    """
    slug = (name or "").strip().lower().replace(" ", "-").replace("_", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def dice_sum_distribution(dice: int, faces: int) -> dict:
    """Probabilite de chaque somme pour `dice` des a `faces` faces.

    La somme de plusieurs des n'est pas uniforme : c'est ce qui rend une grille
    de gains type loto equilibree sans avoir a poser de poids a la main.
    """
    distribution = {0: 1.0}
    for _ in range(max(1, dice)):
        rolled = {}
        for total, probability in distribution.items():
            for face in range(1, faces + 1):
                rolled[total + face] = rolled.get(total + face, 0.0) + probability / faces
        distribution = rolled
    return distribution


def format_duration(seconds: float) -> str:
    """Duree lisible, pour les messages de cooldown."""
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}min" + (f" {seconds}s" if seconds else "")
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h" + (f" {minutes}min" if minutes else "")
    days, hours = divmod(hours, 24)
    return f"{days}j" + (f" {hours}h" if hours else "")
