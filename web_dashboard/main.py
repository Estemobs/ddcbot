"""DDCBot Web Dashboard - FastAPI admin interface.

Dashboard web admin pour ddcbot. Lit/ecrit dans la meme base SQLite
que le bot Discord. Expose une interface web pour gerer toutes les
configurations par serveur.
"""

import json
import os
import sys

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.db import Database

app = FastAPI(title="DDCBot Dashboard", docs_url=None, redoc_url=None)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

DB_PATH = os.environ.get("DDC_DB_PATH", os.path.join(BASE_DIR, "..", "data", "ddcbot.sqlite3"))
db = Database(path=DB_PATH)


def get_guilds():
    tables_to_check = [
        ("economy_config", "guild_id"),
        ("income_config", "guild_id"),
        ("moderation_config", "guild_id"),
        ("permission_config", "guild_id"),
        ("logs_config", "guild_id"),
        ("xp_config", "guild_id"),
        ("guild_settings", "guild_id"),
        ("automod_config", "guild_id"),
        ("guild_lang", "guild_id"),
        ("work_settings", "guild_id"),
        ("game_panel_config", "guild_id"),
        ("minecraft_config", "guild_id"),
    ]
    guild_ids = set()
    for table, col in tables_to_check:
        try:
            rows = db.fetchall(f"SELECT {col} FROM {table}")
            for row in rows:
                guild_ids.add(row[col])
        except Exception:
            pass
    return sorted(guild_ids)


# ── Pages principales ──

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    guilds = get_guilds()
    stats = {
        "guilds": len(guilds),
        "balances": 0,
        "levels": 0,
        "transactions": 0,
        "warnings": 0,
    }
    try:
        row = db.fetchone("SELECT COUNT(*) as c FROM balances")
        stats["balances"] = row["c"]
    except Exception:
        pass
    try:
        row = db.fetchone("SELECT COUNT(*) as c FROM levels")
        stats["levels"] = row["c"]
    except Exception:
        pass
    try:
        row = db.fetchone("SELECT COUNT(*) as c FROM transactions")
        stats["transactions"] = row["c"]
    except Exception:
        pass
    try:
        row = db.fetchone("SELECT COALESCE(SUM(count), 0) as c FROM warn_counts")
        stats["warnings"] = row["c"]
    except Exception:
        pass
    return templates.TemplateResponse("index.html", {
        "request": request, "guilds": guilds, "stats": stats
    })


# ── Vue d\'ensemble d\'un serveur ──

@app.get("/guild/{guild_id}", response_class=HTMLResponse)
async def guild_overview(request: Request, guild_id: int):
    info = {}
    for table, col, label in [
        ("economy_config", "guild_id", "Economie"),
        ("moderation_config", "guild_id", "Moderation"),
        ("xp_config", "guild_id", "Leveling"),
        ("guild_settings", "guild_id", "Welcome/Leave"),
        ("automod_config", "guild_id", "AutoMod"),
        ("logs_config", "guild_id", "Logs"),
        ("minecraft_config", "guild_id", "Minecraft"),
        ("work_settings", "guild_id", "Travail"),
        ("game_panel_config", "guild_id", "Jeux"),
    ]:
        try:
            row = db.fetchone(f"SELECT COUNT(*) as c FROM {table} WHERE {col} = ?", (guild_id,))
            info[label] = row["c"] > 0
        except Exception:
            info[label] = False

    warn_row = db.fetchone(
        "SELECT COALESCE(SUM(count), 0) as c FROM warn_counts WHERE guild_id = ?", (guild_id,)
    ) if True else {"c": 0}
    eco_row = db.fetchone(
        "SELECT COUNT(*) as c FROM transactions WHERE guild_id = ?", (guild_id,)
    ) if True else {"c": 0}

    return templates.TemplateResponse("guild.html", {
        "request": request, "guild_id": guild_id, "info": info,
        "warnings": warn_row["c"], "transactions": eco_row["c"],
    })


# ── Economy ──

@app.get("/guild/{guild_id}/economy", response_class=HTMLResponse)
async def economy_page(request: Request, guild_id: int):
    cfg_row = db.fetchone("SELECT * FROM economy_config WHERE guild_id = ?", (guild_id,))
    config = None
    if cfg_row:
        config = dict(cfg_row)
    balances = db.fetchall(
        "SELECT user_id, amount FROM balances ORDER BY amount DESC LIMIT 50"
    )
    recent_tx = db.fetchall(
        "SELECT * FROM transactions WHERE guild_id = ? ORDER BY created_at DESC LIMIT 30",
        (guild_id,),
    )
    return templates.TemplateResponse("economy.html", {
        "request": request, "guild_id": guild_id,
        "config": config, "balances": balances, "transactions": recent_tx,
    })


@app.post("/guild/{guild_id}/economy/config")
async def economy_save_config(
    guild_id: int,
    allow_transfers: str = Form("0"),
    max_transfer: float = Form(10000),
    allow_negative: str = Form("0"),
):
    db.execute(
        "INSERT INTO economy_config (guild_id, allow_transfers, max_transfer, allow_negative_balances) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
        "allow_transfers=excluded.allow_transfers, max_transfer=excluded.max_transfer, "
        "allow_negative_balances=excluded.allow_negative_balances",
        (guild_id, int(allow_transfers), max_transfer, int(allow_negative)),
    )
    return RedirectResponse(f"/guild/{guild_id}/economy", status_code=303)


@app.post("/guild/{guild_id}/economy/addmoney")
async def economy_add_money(
    guild_id: int, user_id: int = Form(...), amount: float = Form(...)
):
    db.execute(
        "INSERT INTO balances (user_id, amount) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET amount = amount + excluded.amount",
        (user_id, amount),
    )
    db.execute(
        "INSERT INTO transactions (guild_id, user_id, amount, kind, detail) VALUES (?, ?, ?, ?, ?)",
        (guild_id, user_id, amount, "web_add", "Ajout via dashboard web"),
    )
    return RedirectResponse(f"/guild/{guild_id}/economy", status_code=303)


@app.post("/guild/{guild_id}/economy/removemoney")
async def economy_remove_money(
    guild_id: int, user_id: int = Form(...), amount: float = Form(...)
):
    db.execute(
        "INSERT INTO balances (user_id, amount) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET amount = amount - excluded.amount",
        (user_id, amount),
    )
    db.execute(
        "INSERT INTO transactions (guild_id, user_id, amount, kind, detail) VALUES (?, ?, ?, ?, ?)",
        (guild_id, user_id, -amount, "web_remove", "Retrait via dashboard web"),
    )
    return RedirectResponse(f"/guild/{guild_id}/economy", status_code=303)


# ── Moderation ──

@app.get("/guild/{guild_id}/moderation", response_class=HTMLResponse)
async def moderation_page(request: Request, guild_id: int):
    cfg_row = db.fetchone("SELECT config_json FROM moderation_config WHERE guild_id = ?", (guild_id,))
    config = {}
    if cfg_row:
        try:
            config = json.loads(cfg_row["config_json"])
        except json.JSONDecodeError:
            config = {}
    warns = db.fetchall(
        "SELECT user_id, count FROM warn_counts WHERE guild_id = ? AND count > 0 ORDER BY count DESC",
        (guild_id,),
    )
    return templates.TemplateResponse("moderation.html", {
        "request": request, "guild_id": guild_id,
        "config": config, "warns": warns,
    })


@app.post("/guild/{guild_id}/moderation/config")
async def moderation_save_config(
    guild_id: int,
    dm_user: str = Form("1"),
    announce_public: str = Form("1"),
    require_reason: str = Form("1"),
    auto_timeout: str = Form("0"),
    auto_timeout_warns: int = Form(3),
    auto_timeout_minutes: int = Form(30),
):
    cfg = {
        "warn": {
            "dm_user": dm_user == "1",
            "announce_public": announce_public == "1",
            "require_reason": require_reason == "1",
            "log_channel_id": None,
        },
        "actions": {
            "auto_timeout_enabled": auto_timeout == "1",
            "auto_timeout_after_warns": auto_timeout_warns,
            "auto_timeout_minutes": auto_timeout_minutes,
        },
        "defaults": {
            "clear_amount": 5,
            "timeout_minutes": 10,
        },
        "notifications": {
            "dm_on_kick": True,
            "dm_on_ban": True,
        },
    }
    db.execute(
        "INSERT INTO moderation_config (guild_id, config_json) VALUES (?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET config_json = excluded.config_json",
        (guild_id, json.dumps(cfg)),
    )
    return RedirectResponse(f"/guild/{guild_id}/moderation", status_code=303)


@app.post("/guild/{guild_id}/moderation/clearwarns")
async def moderation_clear_warns(guild_id: int, user_id: int = Form(...)):
    db.execute(
        "DELETE FROM warn_counts WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    return RedirectResponse(f"/guild/{guild_id}/moderation", status_code=303)


# ── Leveling ──

@app.get("/guild/{guild_id}/leveling", response_class=HTMLResponse)
async def leveling_page(request: Request, guild_id: int):
    cfg_row = db.fetchone(
        "SELECT enabled, xp_per_message, cooldown_seconds, announce_channel_id "
        "FROM xp_config WHERE guild_id = ?", (guild_id,)
    )
    config = None
    if cfg_row:
        config = {
            "enabled": bool(cfg_row["enabled"]),
            "xp_per_message": cfg_row["xp_per_message"],
            "cooldown_seconds": cfg_row["cooldown_seconds"],
            "announce_channel_id": cfg_row["announce_channel_id"],
        }
    top_levels = db.fetchall(
        "SELECT user_id, xp FROM levels ORDER BY xp DESC LIMIT 50"
    )
    return templates.TemplateResponse("leveling.html", {
        "request": request, "guild_id": guild_id,
        "config": config, "levels": top_levels,
    })


@app.post("/guild/{guild_id}/leveling/config")
async def leveling_save_config(
    guild_id: int,
    enabled: str = Form("1"),
    xp_per_message: int = Form(15),
    cooldown_seconds: int = Form(60),
):
    db.execute(
        "INSERT INTO xp_config (guild_id, enabled, xp_per_message, cooldown_seconds) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
        "enabled=excluded.enabled, xp_per_message=excluded.xp_per_message, "
        "cooldown_seconds=excluded.cooldown_seconds",
        (guild_id, int(enabled), xp_per_message, cooldown_seconds),
    )
    return RedirectResponse(f"/guild/{guild_id}/leveling", status_code=303)


@app.post("/guild/{guild_id}/leveling/reset")
async def leveling_reset(guild_id: int, user_id: int = Form(...)):
    db.execute("DELETE FROM levels WHERE user_id = ?", (user_id,))
    return RedirectResponse(f"/guild/{guild_id}/leveling", status_code=303)


# ── Welcome/Leave ──

@app.get("/guild/{guild_id}/welcome", response_class=HTMLResponse)
async def welcome_page(request: Request, guild_id: int):
    row = db.fetchone(
        "SELECT welcome_enabled, welcome_channel_id, welcome_message, "
        "leave_enabled, leave_channel_id, leave_message "
        "FROM guild_settings WHERE guild_id = ?", (guild_id,)
    )
    settings = None
    if row:
        settings = {
            "welcome_enabled": bool(row["welcome_enabled"]),
            "welcome_channel_id": row["welcome_channel_id"],
            "welcome_message": row["welcome_message"] or "",
            "leave_enabled": bool(row["leave_enabled"]),
            "leave_channel_id": row["leave_channel_id"],
            "leave_message": row["leave_message"] or "",
        }
    return templates.TemplateResponse("welcome.html", {
        "request": request, "guild_id": guild_id, "settings": settings,
    })


@app.post("/guild/{guild_id}/welcome/config")
async def welcome_save_config(
    guild_id: int,
    welcome_enabled: str = Form("0"),
    welcome_channel_id: int = Form(0),
    welcome_message: str = Form(""),
    leave_enabled: str = Form("0"),
    leave_channel_id: int = Form(0),
    leave_message: str = Form(""),
):
    db.execute(
        "INSERT INTO guild_settings "
        "(guild_id, welcome_enabled, welcome_channel_id, welcome_message, "
        "leave_enabled, leave_channel_id, leave_message) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET "
        "welcome_enabled=excluded.welcome_enabled, welcome_channel_id=excluded.welcome_channel_id, "
        "welcome_message=excluded.welcome_message, leave_enabled=excluded.leave_enabled, "
        "leave_channel_id=excluded.leave_channel_id, leave_message=excluded.leave_message",
        (
            guild_id,
            int(welcome_enabled), welcome_channel_id or None, welcome_message or None,
            int(leave_enabled), leave_channel_id or None, leave_message or None,
        ),
    )
    return RedirectResponse(f"/guild/{guild_id}/welcome", status_code=303)


# ── AutoMod ──

@app.get("/guild/{guild_id}/automod", response_class=HTMLResponse)
async def automod_page(request: Request, guild_id: int):
    cfg_row = db.fetchone(
        "SELECT enabled, warn_on_match, delete_on_match, log_channel_id "
        "FROM automod_config WHERE guild_id = ?", (guild_id,)
    )
    config = None
    if cfg_row:
        config = {
            "enabled": bool(cfg_row["enabled"]),
            "warn_on_match": bool(cfg_row["warn_on_match"]),
            "delete_on_match": bool(cfg_row["delete_on_match"]),
            "log_channel_id": cfg_row["log_channel_id"],
        }
    words = db.fetchall(
        "SELECT word FROM automod_words WHERE guild_id = ? ORDER BY word", (guild_id,)
    )
    return templates.TemplateResponse("automod.html", {
        "request": request, "guild_id": guild_id,
        "config": config, "words": [w["word"] for w in words],
    })


@app.post("/guild/{guild_id}/automod/config")
async def automod_save_config(
    guild_id: int,
    enabled: str = Form("0"),
    warn_on_match: str = Form("1"),
    delete_on_match: str = Form("1"),
):
    db.execute(
        "INSERT INTO automod_config (guild_id, enabled, warn_on_match, delete_on_match) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
        "enabled=excluded.enabled, warn_on_match=excluded.warn_on_match, "
        "delete_on_match=excluded.delete_on_match",
        (guild_id, int(enabled), int(warn_on_match), int(delete_on_match)),
    )
    return RedirectResponse(f"/guild/{guild_id}/automod", status_code=303)


@app.post("/guild/{guild_id}/automod/addword")
async def automod_add_word(guild_id: int, word: str = Form(...)):
    db.execute(
        "INSERT OR IGNORE INTO automod_words (guild_id, word) VALUES (?, ?)",
        (guild_id, word.lower().strip()),
    )
    return RedirectResponse(f"/guild/{guild_id}/automod", status_code=303)


@app.post("/guild/{guild_id}/automod/removeword")
async def automod_remove_word(guild_id: int, word: str = Form(...)):
    db.execute("DELETE FROM automod_words WHERE guild_id = ? AND word = ?", (guild_id, word))
    return RedirectResponse(f"/guild/{guild_id}/automod", status_code=303)


# ── Logs ──

@app.get("/guild/{guild_id}/logs", response_class=HTMLResponse)
async def logs_page(request: Request, guild_id: int):
    cfg_row = db.fetchone("SELECT config_json FROM logs_config WHERE guild_id = ?", (guild_id,))
    config = {}
    if cfg_row:
        try:
            config = json.loads(cfg_row["config_json"])
        except json.JSONDecodeError:
            config = {}
    return templates.TemplateResponse("logs.html", {
        "request": request, "guild_id": guild_id, "config": config,
    })


@app.post("/guild/{guild_id}/logs/config")
async def logs_save_config(
    guild_id: int,
    user_errors: str = Form("1"),
    unexpected_errors: str = Form("1"),
    log_channel_id: int = Form(0),
):
    cfg = {
        "channels": [log_channel_id] if log_channel_id else [],
        "categories": {
            "user_errors": user_errors == "1",
            "unexpected_errors": unexpected_errors == "1",
        },
    }
    db.execute(
        "INSERT INTO logs_config (guild_id, config_json) VALUES (?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET config_json = excluded.config_json",
        (guild_id, json.dumps(cfg)),
    )
    return RedirectResponse(f"/guild/{guild_id}/logs", status_code=303)


# ── Notes ──

@app.get("/notes", response_class=HTMLResponse)
async def notes_page(request: Request):
    notes = db.fetchall("SELECT title, content FROM notes ORDER BY title")
    return templates.TemplateResponse("notes.html", {
        "request": request, "notes": notes,
    })


@app.post("/notes/add")
async def notes_add(title: str = Form(...), content: str = Form(...)):
    db.execute(
        "INSERT INTO notes (title, content) VALUES (?, ?) "
        "ON CONFLICT(title) DO UPDATE SET content = excluded.content",
        (title.strip(), content),
    )
    return RedirectResponse("/notes", status_code=303)


@app.post("/notes/delete")
async def notes_delete(title: str = Form(...)):
    db.execute("DELETE FROM notes WHERE title = ?", (title,))
    return RedirectResponse("/notes", status_code=303)


# ── Transactions (historique global) ──

@app.get("/transactions", response_class=HTMLResponse)
async def transactions_page(request: Request, guild_id: int = 0):
    if guild_id:
        txs = db.fetchall(
            "SELECT * FROM transactions WHERE guild_id = ? ORDER BY created_at DESC LIMIT 100",
            (guild_id,),
        )
    else:
        txs = db.fetchall("SELECT * FROM transactions ORDER BY created_at DESC LIMIT 100")
    return templates.TemplateResponse("transactions.html", {
        "request": request, "transactions": txs, "selected_guild": guild_id,
    })


# ── Reminders ──

@app.get("/reminders", response_class=HTMLResponse)
async def reminders_page(request: Request):
    import time
    now = time.time()
    pending = db.fetchall(
        "SELECT * FROM reminders WHERE remind_at > ? ORDER BY remind_at LIMIT 100",
        (now,),
    )
    return templates.TemplateResponse("reminders.html", {
        "request": request, "reminders": pending,
    })


# ── Giveaways ──

@app.get("/giveaways", response_class=HTMLResponse)
async def giveaways_page(request: Request):
    active = db.fetchall(
        "SELECT * FROM giveaways WHERE ended = 0 ORDER BY ends_at"
    )
    ended = db.fetchall(
        "SELECT * FROM giveaways WHERE ended = 1 ORDER BY ends_at DESC LIMIT 30"
    )
    return templates.TemplateResponse("giveaways.html", {
        "request": request, "active": active, "ended": ended,
    })


# ── API JSON (pour usage externe / bots) ──

@app.get("/api/guilds")
async def api_guilds():
    return {"guilds": get_guilds()}


@app.get("/api/guild/{guild_id}/economy")
async def api_guild_economy(guild_id: int):
    cfg_row = db.fetchone("SELECT * FROM economy_config WHERE guild_id = ?", (guild_id,))
    balances = db.fetchall("SELECT user_id, amount FROM balances ORDER BY amount DESC LIMIT 50")
    return {
        "config": dict(cfg_row) if cfg_row else None,
        "balances": [dict(b) for b in balances],
    }


@app.get("/api/guild/{guild_id}/moderation")
async def api_guild_moderation(guild_id: int):
    cfg_row = db.fetchone("SELECT config_json FROM moderation_config WHERE guild_id = ?", (guild_id,))
    config = {}
    if cfg_row:
        try:
            config = json.loads(cfg_row["config_json"])
        except json.JSONDecodeError:
            pass
    warns = db.fetchall(
        "SELECT user_id, count FROM warn_counts WHERE guild_id = ? AND count > 0 ORDER BY count DESC",
        (guild_id,),
    )
    return {
        "config": config,
        "warns": [{"user_id": w["user_id"], "count": w["count"]} for w in warns],
    }


@app.get("/api/stats")
async def api_stats():
    stats = {}
    for table in ["balances", "levels", "transactions", "reminders", "giveaways", "notes"]:
        try:
            row = db.fetchone(f"SELECT COUNT(*) as c FROM {table}")
            stats[table] = row["c"]
        except Exception:
            stats[table] = 0
    try:
        row = db.fetchone("SELECT COALESCE(SUM(count), 0) as c FROM warn_counts")
        stats["warnings"] = row["c"]
    except Exception:
        stats["warnings"] = 0
    stats["guilds"] = len(get_guilds())
    return stats


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", "8080"))
    uvicorn.run(app, host=host, port=port)
