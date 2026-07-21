"""Importe les anciens fichiers data/*.json vers la base SQLite (data/ddcbot.sqlite3).

Usage: python scripts/migrate_json_to_sqlite.py

Idempotent : si une table cible contient deja des lignes, son import est saute
(pour ne pas dupliquer les donnees en cas de re-execution accidentelle).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.db import Database  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def table_has_rows(db, table_name):
    row = db.fetchone(f"SELECT 1 FROM {table_name} LIMIT 1")
    return row is not None


def migrate_balances(db):
    if table_has_rows(db, "balances"):
        print("balances: deja peuplee, ignore.")
        return
    data = load_json("balances.json") or {}
    for user_id, amount in data.items():
        db.execute("INSERT INTO balances (user_id, amount) VALUES (?, ?)", (int(user_id), amount))
    print(f"balances: {len(data)} ligne(s) importee(s).")


def migrate_economy_config(db):
    if table_has_rows(db, "economy_config"):
        print("economy_config: deja peuplee, ignore.")
        return
    data = load_json("economy_config.json") or {}
    for guild_id, cfg in data.items():
        db.execute(
            "INSERT INTO economy_config (guild_id, allow_transfers, max_transfer, allow_negative_balances, log_channel_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                int(guild_id),
                int(cfg.get("allow_transfers", True)),
                cfg.get("max_transfer", 10000),
                int(cfg.get("allow_negative_balances", False)),
                cfg.get("log_channel_id"),
            ),
        )
    print(f"economy_config: {len(data)} ligne(s) importee(s).")


def migrate_role_income(db):
    if table_has_rows(db, "role_income"):
        print("role_income: deja peuplee, ignore.")
        return
    data = load_json("income.json") or {}
    for role_id, role_data in data.items():
        db.execute(
            "INSERT INTO role_income (role_id, name, amount, collect_interval, last_collect) VALUES (?, ?, ?, ?, ?)",
            (
                int(role_id),
                role_data.get("name", ""),
                role_data.get("amount", 0),
                role_data.get("collect_interval", 0),
                role_data.get("last_collect", 0),
            ),
        )
    print(f"role_income: {len(data)} ligne(s) importee(s).")


def migrate_income_config(db):
    if table_has_rows(db, "income_config"):
        print("income_config: deja peuplee, ignore.")
        return
    data = load_json("income_config.json") or {}
    for guild_id, cfg in data.items():
        db.execute(
            "INSERT INTO income_config (guild_id, collect_enabled, default_amount, default_interval_hours, log_channel_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                int(guild_id),
                int(cfg.get("collect_enabled", True)),
                cfg.get("default_amount", 100.0),
                cfg.get("default_interval_hours", 24),
                cfg.get("log_channel_id"),
            ),
        )
    print(f"income_config: {len(data)} ligne(s) importee(s).")


def migrate_work(db):
    if table_has_rows(db, "work_settings"):
        print("work_settings: deja peuplee, ignore.")
    else:
        data = load_json("workconfig.json")
        if data and "min_amount" in data:
            db.execute(
                "INSERT INTO work_settings (id, min_amount, max_amount, reward_tiers, cooldown, rewards_json) "
                "VALUES (1, ?, ?, ?, ?, ?)",
                (
                    data.get("min_amount"),
                    data.get("max_amount"),
                    data.get("reward_tiers"),
                    data.get("cooldown"),
                    json.dumps(data.get("rewards", [])),
                ),
            )
            print("work_settings: 1 ligne importee.")
        else:
            print("work_settings: aucune configuration existante, ignore.")

    if table_has_rows(db, "work_state"):
        print("work_state: deja peuplee, ignore.")
        return
    data = load_json("workconfig.json") or {}
    work_count = data.get("work_count", {})
    last_worked = data.get("last_worked", {})
    user_ids = set(work_count.keys()) | set(last_worked.keys())
    for user_id in user_ids:
        db.execute(
            "INSERT INTO work_state (user_id, work_count, last_worked) VALUES (?, ?, ?)",
            (int(user_id), work_count.get(user_id, 0), last_worked.get(user_id, 0)),
        )
    print(f"work_state: {len(user_ids)} ligne(s) importee(s).")


def migrate_games(db):
    if table_has_rows(db, "games"):
        print("games: deja peuplee, ignore.")
        return
    data = load_json("gameconfig.json") or {}
    for name, game in data.items():
        db.execute(
            "INSERT INTO games (name, num_lots, lots_json, game_price) VALUES (?, ?, ?, ?)",
            (name, int(game.get("num_lots", 0)), json.dumps(game.get("lots", [])), int(game.get("game_price", 0))),
        )
    print(f"games: {len(data)} ligne(s) importee(s).")


def migrate_quests(db):
    if table_has_rows(db, "quests"):
        print("quests: deja peuplee, ignore.")
        return
    data = load_json("quete.json") or {}
    for name, quest in data.items():
        db.execute(
            "INSERT INTO quests (name, lot_count, lot_json, progress) VALUES (?, ?, ?, ?)",
            (name, quest.get("lot_count", 0), json.dumps(quest.get("lot", {})), quest.get("progress", 0)),
        )
    print(f"quests: {len(data)} ligne(s) importee(s).")


def migrate_inventory(db):
    if table_has_rows(db, "inventory_tickets"):
        print("inventory_tickets: deja peuplee, ignore.")
        return
    data = load_json("inventaire.json") or {}
    tickets = data.get("tickets", [])
    count = 0
    for ticket in tickets:
        for user_id, item_name in ticket.items():
            db.execute(
                "INSERT INTO inventory_tickets (user_id, item_name) VALUES (?, ?)",
                (int(user_id), item_name),
            )
            count += 1
    print(f"inventory_tickets: {count} ligne(s) importee(s).")


def migrate_game_panel_config(db):
    if table_has_rows(db, "game_panel_config"):
        print("game_panel_config: deja peuplee, ignore.")
        return
    data = load_json("game_panel_config.json") or {}
    for guild_id, cfg in data.items():
        db.execute(
            "INSERT INTO game_panel_config (guild_id, openlot_enabled, quests_enabled, announce_win_public, log_channel_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                int(guild_id),
                int(cfg.get("openlot_enabled", True)),
                int(cfg.get("quests_enabled", True)),
                int(cfg.get("announce_win_public", True)),
                cfg.get("log_channel_id"),
            ),
        )
    print(f"game_panel_config: {len(data)} ligne(s) importee(s).")


def migrate_moderation_config(db):
    if table_has_rows(db, "moderation_config"):
        print("moderation_config: deja peuplee, ignore.")
        return
    data = load_json("moderation_config.json") or {}
    for guild_id, cfg in data.items():
        db.execute(
            "INSERT INTO moderation_config (guild_id, config_json) VALUES (?, ?)",
            (int(guild_id), json.dumps(cfg)),
        )
    print(f"moderation_config: {len(data)} ligne(s) importee(s).")


def migrate_warn_counts(db):
    if table_has_rows(db, "warn_counts"):
        print("warn_counts: deja peuplee, ignore.")
        return
    data = load_json("warn_history.json") or {}
    count = 0
    for guild_id, users in data.items():
        for user_id, warn_count in users.items():
            db.execute(
                "INSERT INTO warn_counts (guild_id, user_id, count) VALUES (?, ?, ?)",
                (int(guild_id), int(user_id), int(warn_count)),
            )
            count += 1
    print(f"warn_counts: {count} ligne(s) importee(s).")


def migrate_permission_config(db):
    if table_has_rows(db, "permission_config"):
        print("permission_config: deja peuplee, ignore.")
        return
    data = load_json("permission_config.json") or {}
    for guild_id, cfg in data.items():
        db.execute(
            "INSERT INTO permission_config (guild_id, config_json) VALUES (?, ?)",
            (int(guild_id), json.dumps(cfg)),
        )
    print(f"permission_config: {len(data)} ligne(s) importee(s).")


def migrate_logs_config(db):
    if table_has_rows(db, "logs_config"):
        print("logs_config: deja peuplee, ignore.")
        return
    data = load_json("logs_config.json") or {}
    for guild_id, cfg in data.items():
        db.execute(
            "INSERT INTO logs_config (guild_id, config_json) VALUES (?, ?)",
            (int(guild_id), json.dumps(cfg)),
        )
    print(f"logs_config: {len(data)} ligne(s) importee(s).")


def migrate_notes(db):
    if table_has_rows(db, "notes"):
        print("notes: deja peuplee, ignore.")
        return
    data = load_json("notes.json") or {}
    for title, content in data.items():
        db.execute("INSERT INTO notes (title, content) VALUES (?, ?)", (title, content))
    print(f"notes: {len(data)} ligne(s) importee(s).")


def migrate_notifications(db):
    if table_has_rows(db, "notifications"):
        print("notifications: deja peuplee, ignore.")
        return
    data = load_json("notifications.json") or []
    for notification in data:
        db.execute(
            "INSERT INTO notifications (show_name, season, number, airdate, user_id) VALUES (?, ?, ?, ?, ?)",
            (
                notification.get("show_name"),
                notification.get("season"),
                notification.get("number"),
                notification.get("airdate"),
                notification.get("user_id"),
            ),
        )
    print(f"notifications: {len(data)} ligne(s) importee(s).")


def main():
    db = Database()
    migrate_balances(db)
    migrate_economy_config(db)
    migrate_role_income(db)
    migrate_income_config(db)
    migrate_work(db)
    migrate_games(db)
    migrate_quests(db)
    migrate_inventory(db)
    migrate_game_panel_config(db)
    migrate_moderation_config(db)
    migrate_warn_counts(db)
    migrate_permission_config(db)
    migrate_logs_config(db)
    migrate_notes(db)
    migrate_notifications(db)
    db.close()
    print("Migration terminee.")


if __name__ == "__main__":
    main()
