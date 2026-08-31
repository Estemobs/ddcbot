"""DDCBot Web Dashboard - FastAPI admin interface.

Dashboard web admin pour ddcbot. Lit/ecrit dans la meme base SQLite
que le bot Discord. Expose une interface web pour gerer toutes les
configurations par serveur.
"""

import hashlib
import json
import os
import re
import secrets
import sys
import time
from collections import defaultdict

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.db import Database
from casino_engine import CasinoEngine, CasinoError
from web_dashboard.i18n import tr, resolve_lang, get_text

app = FastAPI(title="DDCBot Dashboard", docs_url=None, redoc_url=None)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

templates.env.globals["t"] = pass_context(tr)


@pass_context
def current_lang(ctx):
    return resolve_lang(ctx.get("request"))


templates.env.globals["current_lang"] = current_lang


@pass_context
def nav_guilds(ctx):
    return get_guilds()


templates.env.globals["nav_guilds"] = nav_guilds

# Modules configurables par serveur. Source de verite unique : la nav laterale,
# la grille de la page serveur et le calcul des statuts s'en servent tous.
GUILD_MODULES = [
    {"slug": "economy", "key": "module.economy", "icon": "coins", "table": "economy_config"},
    {"slug": "work", "key": "module.work", "icon": "briefcase", "table": "work_settings"},
    {"slug": "leveling", "key": "module.leveling", "icon": "chart", "table": "xp_config"},
    {"slug": "moderation", "key": "module.moderation", "icon": "shield", "table": "moderation_config"},
    {"slug": "automod", "key": "module.automod", "icon": "filter", "table": "automod_config"},
    {"slug": "aimod", "key": "module.aimod", "icon": "sparkles", "table": "ai_moderation_config"},
    {"slug": "lockdown", "key": "module.lockdown", "icon": "lock", "table": "lockdown_config"},
    {"slug": "welcome", "key": "module.welcome", "icon": "wave", "table": "guild_settings"},
    {"slug": "invitations", "key": "module.invitations", "icon": "users", "table": "invites"},
    {"slug": "tickets", "key": "module.tickets", "icon": "ticket", "table": "ticket_config"},
    {"slug": "logs", "key": "module.logs", "icon": "list", "table": "logs_config"},
    {"slug": "webhooks", "key": "module.webhooks", "icon": "link", "table": "webhook_config"},
    {"slug": "rss", "key": "module.rss", "icon": "tv", "table": None},
    {"slug": "minecraft", "key": "module.minecraft", "icon": "cube", "table": "minecraft_config"},
    {"slug": "steam", "key": "module.steam", "icon": "gamepad", "table": "steam_config"},
    {"slug": "lang", "key": "module.lang", "icon": "globe", "table": "guild_lang"},
    {"slug": "casino", "key": "module.casino", "icon": "dice", "table": "casino_games"},
    {"slug": "notes", "key": "module.notes", "icon": "note", "table": "notes"},
    {"slug": "transactions", "key": "module.transactions", "icon": "swap", "table": "transactions"},
    {"slug": "reminders", "key": "module.reminders", "icon": "clock", "table": "reminders"},
    {"slug": "giveaways", "key": "module.giveaways", "icon": "gift", "table": "giveaways"},
]

templates.env.globals["guild_modules"] = GUILD_MODULES

_GUILD_PATH_RE = re.compile(r"^/guild/(\d+)")


@pass_context
def current_guild(ctx):
    """Guild id de la page courante (nav contextuelle), ou None."""
    request = ctx.get("request")
    if request is None:
        return None
    match = _GUILD_PATH_RE.match(request.url.path)
    return int(match.group(1)) if match else None


templates.env.globals["current_guild"] = current_guild


@pass_context
def auth_enabled(ctx):
    return bool(DASHBOARD_TOKEN)


templates.env.globals["auth_enabled"] = auth_enabled

DB_PATH = os.environ.get("DDC_DB_PATH", os.path.join(BASE_DIR, "..", "data", "ddcbot.sqlite3"))
db = Database(path=DB_PATH)
casino = CasinoEngine(db)

DASHBOARD_TOKEN = os.environ.get("DASHBOARD_TOKEN", "")
API_KEY = os.environ.get("DASHBOARD_API_KEY", "")
_sessions = {}

# ── Rate limiting ──
_login_attempts = defaultdict(list)
RATE_LIMIT_MAX = int(os.environ.get("DASHBOARD_RATE_LIMIT_MAX", "5"))
RATE_LIMIT_WINDOW = int(os.environ.get("DASHBOARD_RATE_LIMIT_WINDOW", "300"))


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
    return len(_login_attempts[ip]) >= RATE_LIMIT_MAX


def _record_login_attempt(ip: str):
    _login_attempts[ip].append(time.time())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_auth(request: Request) -> bool:
    if not DASHBOARD_TOKEN:
        return True
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header and api_key_header in (API_KEY, DASHBOARD_TOKEN):
        return True
    session_id = request.cookies.get("ddc_session")
    if session_id and session_id in _sessions:
        if _sessions[session_id] > time.time():
            return True
        del _sessions[session_id]
    return False


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path == "/login" or path == "/api/login":
        return await call_next(request)
    if not require_auth(request):
        lang = resolve_lang(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": get_text("api.unauthorized", lang)}, status_code=401)
        return templates.TemplateResponse(request, "login.html", {
            "request": request, "error": None
        })
    return await call_next(request)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if not DASHBOARD_TOKEN:
        return RedirectResponse("/", status_code=303)
    if require_auth(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None})


@app.post("/login")
async def login_submit(request: Request, token: str = Form(...)):
    if not DASHBOARD_TOKEN:
        return RedirectResponse("/", status_code=303)

    client_ip = request.client.host if request.client else "unknown"
    lang = resolve_lang(request)
    if _check_rate_limit(client_ip):
        return templates.TemplateResponse(request, "login.html", {
            "request": request,
            "error": get_text("login.too_many", lang, seconds=RATE_LIMIT_WINDOW),
        })

    if token == DASHBOARD_TOKEN:
        _login_attempts[client_ip] = []
        session_id = secrets.token_urlsafe(32)
        _sessions[session_id] = time.time() + 86400
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("ddc_session", session_id, httponly=True, max_age=86400)
        return response

    _record_login_attempt(client_ip)
    remaining = RATE_LIMIT_MAX - len(_login_attempts[client_ip])
    return templates.TemplateResponse(request, "login.html", {
        "request": request,
        "error": get_text("login.invalid", lang, remaining=remaining),
    })


@app.get("/logout")
async def logout(request: Request):
    session_id = request.cookies.get("ddc_session")
    if session_id:
        _sessions.pop(session_id, None)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("ddc_session")
    return response


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
        ("ai_moderation_config", "guild_id"),
        ("ticket_config", "guild_id"),
        ("webhook_config", "guild_id"),
        ("lockdown_config", "guild_id"),
        ("invites", "guild_id"),
        ("steam_config", "guild_id"),
        ("guild_meta", "guild_id"),
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


def guild_info(guild_id):
    """Nom/icone d'un serveur depuis guild_meta, avec repli sur l'identifiant.

    Le bot alimente guild_meta (voir main.py sync_guild_meta) ; tant qu'il n'a
    pas tourne depuis la migration, `name` reste None et les gabarits affichent
    l'identifiant numerique.
    """
    row = None
    try:
        row = db.fetchone(
            "SELECT name, icon_url, member_count FROM guild_meta WHERE guild_id = ?",
            (guild_id,),
        )
    except Exception:
        pass
    return {
        "id": guild_id,
        "name": (row["name"] or None) if row else None,
        "icon_url": row["icon_url"] if row else None,
        "member_count": row["member_count"] if row else 0,
    }


templates.env.globals["guild_info"] = guild_info


# ── Pages principales ──

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    guilds = get_guilds()
    # Ancien lien ?guild_id=... : renvoie vers la page du serveur.
    selected_guild = request.query_params.get("guild_id")
    if selected_guild and selected_guild.isdigit() and int(selected_guild) in guilds:
        return RedirectResponse(f"/guild/{int(selected_guild)}", status_code=303)

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

    return templates.TemplateResponse(request, "index.html", {
        "request": request, "guilds": guilds, "stats": stats
    })


# ── Vue d'ensemble d'un serveur ──

def _module_is_configured(table: str, guild_id: int) -> bool:
    if not table:
        return False
    try:
        row = db.fetchone(f"SELECT COUNT(*) as c FROM {table} WHERE guild_id = ?", (guild_id,))
        return row["c"] > 0
    except Exception:
        return False


def _count(query: str, params=()) -> int:
    try:
        row = db.fetchone(query, params)
        return row["c"] if row else 0
    except Exception:
        return 0


@app.get("/guild/{guild_id}", response_class=HTMLResponse)
async def guild_overview(request: Request, guild_id: int):
    modules = [
        dict(mod, active=_module_is_configured(mod["table"], guild_id))
        for mod in GUILD_MODULES
    ]
    stats = {
        "active_modules": sum(1 for mod in modules if mod["active"]),
        "total_modules": len(modules),
        "warnings": _count(
            "SELECT COALESCE(SUM(count), 0) as c FROM warn_counts WHERE guild_id = ?", (guild_id,)
        ),
        "transactions": _count(
            "SELECT COUNT(*) as c FROM transactions WHERE guild_id = ?", (guild_id,)
        ),
    }

    return templates.TemplateResponse(request, "guild.html", {
        "request": request, "guild_id": guild_id, "modules": modules, "stats": stats,
        "warnings": stats["warnings"], "transactions": stats["transactions"],
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
    return templates.TemplateResponse(request, "economy.html", {
        "request": request, "guild_id": guild_id,
        "config": config, "balances": balances, "transactions": recent_tx,
    })


@app.post("/guild/{guild_id}/economy/config")
async def economy_save_config(
    guild_id: int,
    allow_transfers: str = Form("0"),
    max_transfer: float = Form(10000),
    allow_negative: str = Form("0"),
    starting_balance: float = Form(0),
):
    db.execute(
        "INSERT INTO economy_config (guild_id, allow_transfers, max_transfer, "
        "allow_negative_balances, starting_balance) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
        "allow_transfers=excluded.allow_transfers, max_transfer=excluded.max_transfer, "
        "allow_negative_balances=excluded.allow_negative_balances, "
        "starting_balance=excluded.starting_balance",
        (guild_id, int(allow_transfers), max_transfer, int(allow_negative), starting_balance),
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
    return templates.TemplateResponse(request, "moderation.html", {
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
    return templates.TemplateResponse(request, "leveling.html", {
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
    return templates.TemplateResponse(request, "welcome.html", {
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
    return templates.TemplateResponse(request, "automod.html", {
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
    return templates.TemplateResponse(request, "logs.html", {
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


# ── AI-Moderation ──

@app.get("/guild/{guild_id}/aimod", response_class=HTMLResponse)
async def aimod_page(request: Request, guild_id: int):
    cfg_row = db.fetchone(
        "SELECT enabled, action, log_channel_id, threshold, cooldown_seconds "
        "FROM ai_moderation_config WHERE guild_id = ?", (guild_id,)
    )
    config = None
    if cfg_row:
        config = {
            "enabled": bool(cfg_row["enabled"]),
            "action": cfg_row["action"],
            "log_channel_id": cfg_row["log_channel_id"],
            "threshold": cfg_row["threshold"],
            "cooldown_seconds": cfg_row["cooldown_seconds"],
        }
    ignored = db.fetchall(
        "SELECT role_id FROM ai_moderation_ignored_roles WHERE guild_id = ?", (guild_id,)
    )
    return templates.TemplateResponse(request, "aimod.html", {
        "request": request, "guild_id": guild_id,
        "config": config, "ignored_roles": [r["role_id"] for r in ignored],
    })


@app.post("/guild/{guild_id}/aimod/config")
async def aimod_save_config(
    guild_id: int,
    enabled: str = Form("0"),
    action: str = Form("warn"),
    threshold: float = Form(0.7),
    cooldown_seconds: int = Form(10),
    log_channel_id: int = Form(0),
):
    db.execute(
        "INSERT INTO ai_moderation_config "
        "(guild_id, enabled, action, log_channel_id, threshold, cooldown_seconds) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
        "enabled=excluded.enabled, action=excluded.action, log_channel_id=excluded.log_channel_id, "
        "threshold=excluded.threshold, cooldown_seconds=excluded.cooldown_seconds",
        (guild_id, int(enabled), action, log_channel_id or None, threshold, cooldown_seconds),
    )
    return RedirectResponse(f"/guild/{guild_id}/aimod", status_code=303)


# ── Tickets ──

@app.get("/guild/{guild_id}/tickets", response_class=HTMLResponse)
async def tickets_page(request: Request, guild_id: int):
    cfg_row = db.fetchone(
        "SELECT enabled, category_id, log_channel_id, welcome_message, close_message, max_open_tickets "
        "FROM ticket_config WHERE guild_id = ?", (guild_id,)
    )
    config = None
    if cfg_row:
        config = {
            "enabled": bool(cfg_row["enabled"]),
            "category_id": cfg_row["category_id"],
            "log_channel_id": cfg_row["log_channel_id"],
            "welcome_message": cfg_row["welcome_message"],
            "close_message": cfg_row["close_message"],
            "max_open_tickets": cfg_row["max_open_tickets"],
        }
    open_tickets = db.fetchall(
        "SELECT id, user_id, channel_id, created_at FROM tickets "
        "WHERE guild_id = ? AND status = 'open' ORDER BY created_at DESC", (guild_id,)
    )
    closed_tickets = db.fetchall(
        "SELECT id, user_id, channel_id, created_at, closed_at FROM tickets "
        "WHERE guild_id = ? AND status = 'closed' ORDER BY closed_at DESC LIMIT 30", (guild_id,)
    )
    return templates.TemplateResponse(request, "tickets.html", {
        "request": request, "guild_id": guild_id,
        "config": config, "open_tickets": open_tickets, "closed_tickets": closed_tickets,
    })


@app.post("/guild/{guild_id}/tickets/config")
async def tickets_save_config(
    guild_id: int,
    enabled: str = Form("0"),
    category_id: int = Form(0),
    max_open_tickets: int = Form(5),
    welcome_message: str = Form(""),
    close_message: str = Form(""),
    log_channel_id: int = Form(0),
):
    db.execute(
        "INSERT INTO ticket_config "
        "(guild_id, enabled, category_id, log_channel_id, welcome_message, close_message, max_open_tickets) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
        "enabled=excluded.enabled, category_id=excluded.category_id, log_channel_id=excluded.log_channel_id, "
        "welcome_message=excluded.welcome_message, close_message=excluded.close_message, "
        "max_open_tickets=excluded.max_open_tickets",
        (guild_id, int(enabled), category_id or None, log_channel_id or None,
         welcome_message or None, close_message or None, max_open_tickets),
    )
    return RedirectResponse(f"/guild/{guild_id}/tickets", status_code=303)


# ── Webhooks ──

@app.get("/guild/{guild_id}/webhooks", response_class=HTMLResponse)
async def webhooks_page(request: Request, guild_id: int):
    cfg_row = db.fetchone(
        "SELECT webhook_url, enabled, events_json FROM webhook_config WHERE guild_id = ?", (guild_id,)
    )
    config = None
    if cfg_row:
        events = {}
        if cfg_row["events_json"]:
            try:
                events = json.loads(cfg_row["events_json"])
            except json.JSONDecodeError:
                pass
        config = {
            "webhook_url": cfg_row["webhook_url"],
            "enabled": bool(cfg_row["enabled"]),
            "events": events,
        }
    return templates.TemplateResponse(request, "webhooks.html", {
        "request": request, "guild_id": guild_id, "config": config,
    })


@app.post("/guild/{guild_id}/webhooks/config")
async def webhooks_save_config(
    guild_id: int,
    enabled: str = Form("0"),
    webhook_url: str = Form(""),
    events_json: str = Form("{}"),
):
    db.execute(
        "INSERT INTO webhook_config (guild_id, webhook_url, enabled, events_json) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
        "webhook_url=excluded.webhook_url, enabled=excluded.enabled, events_json=excluded.events_json",
        (guild_id, webhook_url or None, int(enabled), events_json or None),
    )
    return RedirectResponse(f"/guild/{guild_id}/webhooks", status_code=303)


# ── Lockdown ──

@app.get("/guild/{guild_id}/lockdown", response_class=HTMLResponse)
async def lockdown_page(request: Request, guild_id: int):
    cfg_row = db.fetchone(
        "SELECT lockdown_role_id, log_channel_id, auto_lockon_mass_join, "
        "mass_join_threshold, mass_join_window_seconds "
        "FROM lockdown_config WHERE guild_id = ?", (guild_id,)
    )
    config = None
    if cfg_row:
        config = {
            "lockdown_role_id": cfg_row["lockdown_role_id"],
            "log_channel_id": cfg_row["log_channel_id"],
            "auto_lockon_mass_join": bool(cfg_row["auto_lockon_mass_join"]),
            "mass_join_threshold": cfg_row["mass_join_threshold"],
            "mass_join_window_seconds": cfg_row["mass_join_window_seconds"],
        }
    return templates.TemplateResponse(request, "lockdown.html", {
        "request": request, "guild_id": guild_id, "config": config,
    })


@app.post("/guild/{guild_id}/lockdown/config")
async def lockdown_save_config(
    guild_id: int,
    lockdown_role_id: int = Form(0),
    log_channel_id: int = Form(0),
    auto_lockon_mass_join: str = Form("0"),
    mass_join_threshold: int = Form(10),
    mass_join_window_seconds: int = Form(60),
):
    db.execute(
        "INSERT INTO lockdown_config "
        "(guild_id, lockdown_role_id, log_channel_id, auto_lockon_mass_join, mass_join_threshold, mass_join_window_seconds) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
        "lockdown_role_id=excluded.lockdown_role_id, log_channel_id=excluded.log_channel_id, "
        "auto_lockon_mass_join=excluded.auto_lockon_mass_join, mass_join_threshold=excluded.mass_join_threshold, "
        "mass_join_window_seconds=excluded.mass_join_window_seconds",
        (guild_id, lockdown_role_id or None, log_channel_id or None,
         int(auto_lockon_mass_join), mass_join_threshold, mass_join_window_seconds),
    )
    return RedirectResponse(f"/guild/{guild_id}/lockdown", status_code=303)


# ── Invitations ──

@app.get("/guild/{guild_id}/invitations", response_class=HTMLResponse)
async def invitations_page(request: Request, guild_id: int):
    invites = db.fetchall(
        "SELECT user_id, invited, left FROM invites WHERE guild_id = ? ORDER BY invited DESC",
        (guild_id,),
    )
    total_invited = sum(i["invited"] for i in invites)
    total_left = sum(i["left"] for i in invites)
    rewards = db.fetchall(
        "SELECT threshold, amount FROM invite_rewards WHERE guild_id = ? ORDER BY threshold",
        (guild_id,),
    )
    return templates.TemplateResponse(request, "invitations.html", {
        "request": request, "guild_id": guild_id,
        "invites": invites, "total_invited": total_invited,
        "total_left": total_left, "total_active": total_invited - total_left,
        "rewards": rewards,
    })


# ── Minecraft ──

@app.get("/guild/{guild_id}/minecraft", response_class=HTMLResponse)
async def minecraft_page(request: Request, guild_id: int):
    cfg = db.fetchone("SELECT * FROM minecraft_config WHERE guild_id = ?", (guild_id,))
    return templates.TemplateResponse(request, "minecraft.html", {
        "request": request, "guild_id": guild_id, "config": cfg,
    })


@app.post("/guild/{guild_id}/minecraft/config")
async def minecraft_save(
    request: Request, guild_id: int,
    enabled: str = Form("0"),
    channel_id: int = Form(0),
    method: str = Form("tmux"),
    tmux_session: str = Form(""),
    use_sudo: str = Form("0"),
    rcon_host: str = Form(""),
    rcon_port: int = Form(0),
    rcon_password: str = Form(""),
):
    db.execute(
        "INSERT INTO minecraft_config "
        "(guild_id, channel_id, method, tmux_session, use_sudo, rcon_host, rcon_port, rcon_password, enabled) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET "
        "channel_id=excluded.channel_id, method=excluded.method, tmux_session=excluded.tmux_session, "
        "use_sudo=excluded.use_sudo, rcon_host=excluded.rcon_host, rcon_port=excluded.rcon_port, "
        "rcon_password=excluded.rcon_password, enabled=excluded.enabled",
        (guild_id, channel_id or None, method, tmux_session or None,
         int(use_sudo), rcon_host or None, rcon_port or None, rcon_password or None, int(enabled)),
    )
    return RedirectResponse(f"/guild/{guild_id}/minecraft", status_code=303)


# ── Steam ──

@app.get("/guild/{guild_id}/steam", response_class=HTMLResponse)
async def steam_page(request: Request, guild_id: int):
    cfg = db.fetchone("SELECT * FROM steam_config WHERE guild_id = ?", (guild_id,))
    return templates.TemplateResponse(request, "steam.html", {
        "request": request, "guild_id": guild_id, "config": cfg,
    })


@app.post("/guild/{guild_id}/steam/config")
async def steam_save(
    request: Request, guild_id: int,
    api_key: str = Form(""),
):
    db.execute(
        "INSERT INTO steam_config (guild_id, api_key) VALUES (?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET api_key=excluded.api_key",
        (guild_id, api_key or None),
    )
    return RedirectResponse(f"/guild/{guild_id}/steam", status_code=303)


# ── Work / Income ──

@app.get("/guild/{guild_id}/work", response_class=HTMLResponse)
async def work_income_page(request: Request, guild_id: int):
    work = db.fetchone("SELECT * FROM work_settings WHERE guild_id = ?", (guild_id,))
    income = db.fetchone("SELECT * FROM income_config WHERE guild_id = ?", (guild_id,))
    role_incomes = db.fetchall("SELECT * FROM role_income ORDER BY amount DESC")
    return templates.TemplateResponse(request, "work_income.html", {
        "request": request, "guild_id": guild_id,
        "work": work, "income": income, "role_incomes": role_incomes,
    })


@app.post("/guild/{guild_id}/work/config")
async def work_save(
    request: Request, guild_id: int,
    min_amount: float = Form(10),
    max_amount: float = Form(100),
    reward_tiers: int = Form(3),
    cooldown: int = Form(4),
):
    db.execute(
        "INSERT INTO work_settings (guild_id, min_amount, max_amount, reward_tiers, cooldown, rewards_json) "
        "VALUES (?, ?, ?, ?, ?, '[]') "
        "ON CONFLICT(guild_id) DO UPDATE SET "
        "min_amount=excluded.min_amount, max_amount=excluded.max_amount, "
        "reward_tiers=excluded.reward_tiers, cooldown=excluded.cooldown",
        (guild_id, min_amount, max_amount, reward_tiers, cooldown),
    )
    return RedirectResponse(f"/guild/{guild_id}/work", status_code=303)


@app.post("/guild/{guild_id}/income/config")
async def income_save(
    request: Request, guild_id: int,
    collect_enabled: str = Form("0"),
    default_amount: float = Form(100),
    default_interval_hours: int = Form(24),
    log_channel_id: int = Form(0),
):
    db.execute(
        "INSERT INTO income_config "
        "(guild_id, collect_enabled, default_amount, default_interval_hours, log_channel_id) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET "
        "collect_enabled=excluded.collect_enabled, default_amount=excluded.default_amount, "
        "default_interval_hours=excluded.default_interval_hours, log_channel_id=excluded.log_channel_id",
        (guild_id, int(collect_enabled), default_amount, default_interval_hours, log_channel_id or None),
    )
    return RedirectResponse(f"/guild/{guild_id}/work", status_code=303)


# ── Notifications TV ──

@app.get("/guild/{guild_id}/rss", response_class=HTMLResponse)
async def rss_page(request: Request, guild_id: int):
    notifications = db.fetchall(
        "SELECT id, show_name, season, number, airdate, user_id FROM notifications ORDER BY show_name, season, number"
    )
    return templates.TemplateResponse(request, "rss.html", {
        "request": request, "guild_id": guild_id, "notifications": notifications,
    })


# ── Langue / i18n ──

@app.get("/guild/{guild_id}/lang", response_class=HTMLResponse)
async def lang_page(request: Request, guild_id: int):
    lang_config = db.fetchone("SELECT * FROM guild_lang WHERE guild_id = ?", (guild_id,))
    return templates.TemplateResponse(request, "lang.html", {
        "request": request, "guild_id": guild_id, "lang_config": lang_config,
    })


@app.post("/guild/{guild_id}/lang/config")
async def lang_save(
    request: Request, guild_id: int,
    lang: str = Form("fr"),
):
    db.execute(
        "INSERT INTO guild_lang (guild_id, lang) VALUES (?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET lang=excluded.lang",
        (guild_id, lang),
    )
    return RedirectResponse(f"/guild/{guild_id}/lang", status_code=303)


# ── API JSON ──

@app.get("/api/guilds")
async def api_guilds():
    return {"guilds": get_guilds()}


@app.get("/api/guild/{guild_id}/economy")
async def api_guild_economy(guild_id: int):
    cfg_row = db.fetchone("SELECT * FROM economy_config WHERE guild_id = ?", (guild_id,))
    balances = db.fetchall("SELECT user_id, amount FROM balances ORDER BY amount DESC LIMIT 50")
    return {"config": dict(cfg_row) if cfg_row else None, "balances": [dict(b) for b in balances]}


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
    return {"config": config, "warns": [{"user_id": w["user_id"], "count": w["count"]} for w in warns]}


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


def _json_safe(row):
    return dict(row) if row else None


# ── API JSON par module ──

@app.get("/api/guild/{guild_id}/leveling")
async def api_guild_leveling(guild_id: int):
    row = db.fetchone(
        "SELECT enabled, xp_per_message, cooldown_seconds, announce_channel_id "
        "FROM xp_config WHERE guild_id = ?", (guild_id,)
    )
    levels = db.fetchall("SELECT user_id, xp FROM levels ORDER BY xp DESC LIMIT 50")
    return {"config": _json_safe(row), "levels": [dict(lv) for lv in levels]}


@app.get("/api/guild/{guild_id}/welcome")
async def api_guild_welcome(guild_id: int):
    row = db.fetchone(
        "SELECT welcome_enabled, welcome_channel_id, welcome_message, "
        "leave_enabled, leave_channel_id, leave_message "
        "FROM guild_settings WHERE guild_id = ?", (guild_id,)
    )
    return {"config": _json_safe(row)}


@app.get("/api/guild/{guild_id}/automod")
async def api_guild_automod(guild_id: int):
    row = db.fetchone(
        "SELECT enabled, warn_on_match, delete_on_match, log_channel_id "
        "FROM automod_config WHERE guild_id = ?", (guild_id,)
    )
    words = db.fetchall(
        "SELECT word FROM automod_words WHERE guild_id = ? ORDER BY word", (guild_id,)
    )
    return {"config": _json_safe(row), "words": [w["word"] for w in words]}


@app.get("/api/guild/{guild_id}/logs")
async def api_guild_logs(guild_id: int):
    row = db.fetchone("SELECT config_json FROM logs_config WHERE guild_id = ?", (guild_id,))
    config = {}
    if row:
        try:
            config = json.loads(row["config_json"])
        except json.JSONDecodeError:
            config = {}
    return {"config": config}


@app.get("/api/guild/{guild_id}/error-logs")
async def api_guild_error_logs(guild_id: int, limit: int = 50):
    rows = db.fetchall(
        "SELECT id, guild_id, user_id, command, error_type, error_message, traceback, occurred_at "
        "FROM error_logs WHERE guild_id = ? ORDER BY occurred_at DESC LIMIT ?",
        (guild_id, limit),
    )
    result = []
    for row in rows:
        result.append({
            "id": row["id"],
            "guild_id": row["guild_id"],
            "user_id": row["user_id"],
            "command": row["command"],
            "error_type": row["error_type"],
            "error_message": row["error_message"],
            "traceback": row["traceback"] if row["traceback"] else "",
            "occurred_at": row["occurred_at"],
        })
    return {"error_logs": result}


@app.delete("/api/guild/{guild_id}/error-logs/{log_id}")
async def api_delete_error_log(guild_id: int, log_id: int):
    db.execute("DELETE FROM error_logs WHERE guild_id = ? AND id = ?", (guild_id, log_id))
    return {"deleted": True}


@app.get("/api/guild/{guild_id}/aimod")
async def api_guild_aimod(guild_id: int):
    row = db.fetchone(
        "SELECT enabled, action, log_channel_id, threshold, cooldown_seconds "
        "FROM ai_moderation_config WHERE guild_id = ?", (guild_id,)
    )
    ignored = db.fetchall(
        "SELECT role_id FROM ai_moderation_ignored_roles WHERE guild_id = ?", (guild_id,)
    )
    return {
        "config": _json_safe(row),
        "ignored_roles": [r["role_id"] for r in ignored],
    }


@app.get("/api/guild/{guild_id}/tickets")
async def api_guild_tickets(guild_id: int):
    row = db.fetchone(
        "SELECT enabled, category_id, log_channel_id, welcome_message, close_message, max_open_tickets "
        "FROM ticket_config WHERE guild_id = ?", (guild_id,)
    )
    open_tickets = db.fetchall(
        "SELECT id, user_id, channel_id, created_at FROM tickets "
        "WHERE guild_id = ? AND status = 'open' ORDER BY created_at DESC", (guild_id,)
    )
    closed_tickets = db.fetchall(
        "SELECT id, user_id, channel_id, created_at, closed_at FROM tickets "
        "WHERE guild_id = ? AND status = 'closed' ORDER BY closed_at DESC LIMIT 30", (guild_id,)
    )
    return {
        "config": _json_safe(row),
        "open_tickets": [dict(t) for t in open_tickets],
        "closed_tickets": [dict(t) for t in closed_tickets],
    }


@app.get("/api/guild/{guild_id}/webhooks")
async def api_guild_webhooks(guild_id: int):
    row = db.fetchone(
        "SELECT webhook_url, enabled, events_json FROM webhook_config WHERE guild_id = ?", (guild_id,)
    )
    config = None
    if row:
        events = {}
        if row["events_json"]:
            try:
                events = json.loads(row["events_json"])
            except json.JSONDecodeError:
                pass
        config = {"webhook_url": row["webhook_url"], "enabled": bool(row["enabled"]), "events": events}
    return {"config": config}


@app.get("/api/guild/{guild_id}/lockdown")
async def api_guild_lockdown(guild_id: int):
    row = db.fetchone(
        "SELECT lockdown_role_id, log_channel_id, auto_lockon_mass_join, "
        "mass_join_threshold, mass_join_window_seconds "
        "FROM lockdown_config WHERE guild_id = ?", (guild_id,)
    )
    return {"config": _json_safe(row)}


@app.get("/api/guild/{guild_id}/invitations")
async def api_guild_invitations(guild_id: int):
    invites = db.fetchall(
        "SELECT user_id, invited, left FROM invites WHERE guild_id = ? ORDER BY invited DESC",
        (guild_id,),
    )
    total_invited = sum(i["invited"] for i in invites)
    total_left = sum(i["left"] for i in invites)
    return {
        "invites": [dict(i) for i in invites],
        "total_invited": total_invited,
        "total_left": total_left,
        "total_active": total_invited - total_left,
    }


@app.get("/api/guild/{guild_id}/minecraft")
async def api_guild_minecraft(guild_id: int):
    row = db.fetchone("SELECT * FROM minecraft_config WHERE guild_id = ?", (guild_id,))
    return {"config": _json_safe(row)}


@app.get("/api/guild/{guild_id}/steam")
async def api_guild_steam(guild_id: int):
    row = db.fetchone("SELECT * FROM steam_config WHERE guild_id = ?", (guild_id,))
    return {"config": _json_safe(row)}


@app.get("/api/guild/{guild_id}/work")
async def api_guild_work(guild_id: int):
    work = db.fetchone("SELECT * FROM work_settings WHERE guild_id = ?", (guild_id,))
    return {"config": _json_safe(work)}


@app.get("/api/guild/{guild_id}/income")
async def api_guild_income(guild_id: int):
    income = db.fetchone("SELECT * FROM income_config WHERE guild_id = ?", (guild_id,))
    role_incomes = db.fetchall("SELECT * FROM role_income ORDER BY amount DESC")
    return {
        "config": _json_safe(income),
        "role_income": [dict(r) for r in role_incomes],
    }


@app.get("/api/guild/{guild_id}/rss")
async def api_guild_rss(guild_id: int):
    notifications = db.fetchall(
        "SELECT id, show_name, season, number, airdate, user_id FROM notifications "
        "ORDER BY show_name, season, number"
    )
    return {"notifications": [dict(n) for n in notifications]}


@app.get("/api/guild/{guild_id}/lang")
async def api_guild_lang(guild_id: int):
    row = db.fetchone("SELECT * FROM guild_lang WHERE guild_id = ?", (guild_id,))
    return {"config": _json_safe(row)}


@app.get("/api/transactions")
async def api_transactions(guild_id: int = 0):
    if guild_id:
        txs = db.fetchall(
            "SELECT * FROM transactions WHERE guild_id = ? ORDER BY created_at DESC LIMIT 100",
            (guild_id,),
        )
    else:
        txs = db.fetchall("SELECT * FROM transactions ORDER BY created_at DESC LIMIT 100")
    return {"transactions": [dict(t) for t in txs]}


@app.get("/api/reminders")
async def api_reminders():
    now = time.time()
    pending = db.fetchall(
        "SELECT * FROM reminders WHERE remind_at > ? ORDER BY remind_at LIMIT 100",
        (now,),
    )
    return {"reminders": [dict(r) for r in pending]}


@app.get("/api/giveaways")
async def api_giveaways():
    active = db.fetchall("SELECT * FROM giveaways WHERE ended = 0 ORDER BY ends_at")
    ended = db.fetchall("SELECT * FROM giveaways WHERE ended = 1 ORDER BY ends_at DESC LIMIT 30")
    return {
        "active": [dict(g) for g in active],
        "ended": [dict(g) for g in ended],
    }


# ── Casino ──
# Les jeux sont des donnees : tout ce qui est editable ici (jeux, lots, poids,
# cooldowns, quetes, effets) est lu tel quel par le bot via casino_engine.

@app.get("/guild/{guild_id}/casino", response_class=HTMLResponse)
async def casino_page(request: Request, guild_id: int):
    games = casino.list_games(guild_id, include_disabled=True)
    for game in games:
        game["lots"] = casino.list_lots(game["id"])
        game["expected"] = casino.expected_value(game)
        game["rtp"] = casino.theoretical_rtp(game)
        game["stats"] = casino.actual_stats(guild_id, game["slug"])
    return templates.TemplateResponse(request, "casino.html", {
        "request": request, "guild_id": guild_id, "games": games,
        "quests": casino.list_quests(guild_id, include_disabled=True),
        "style": casino.get_style(guild_id),
        "overall": casino.actual_stats(guild_id),
    })


@app.post("/guild/{guild_id}/casino/game/add")
async def casino_game_add(
    guild_id: int,
    display_name: str = Form(...),
    slug: str = Form(""),
    kind: str = Form("weighted"),
    category: str = Form("box"),
    price: float = Form(0),
    cooldown_seconds: int = Form(0),
    description: str = Form(""),
    dice: int = Form(2),
    faces: int = Form(6),
    win_amount: float = Form(0),
    lose_amount: float = Form(0),
):
    config = {}
    if kind == "dice_sum":
        config = {"dice": dice, "faces": faces}
    elif kind == "dice_guess":
        config = {"faces": faces, "win_amount": win_amount, "lose_amount": lose_amount}
    try:
        casino.create_game(
            guild_id, slug or display_name, display_name=display_name, kind=kind,
            category=category, price=price, cooldown_seconds=cooldown_seconds,
            description=description, config=config,
        )
    except CasinoError:
        pass
    return RedirectResponse(f"/guild/{guild_id}/casino", status_code=303)


@app.post("/guild/{guild_id}/casino/game/{game_id}/edit")
async def casino_game_edit(
    guild_id: int, game_id: int,
    display_name: str = Form(...),
    category: str = Form("box"),
    price: float = Form(0),
    cooldown_seconds: int = Form(0),
    description: str = Form(""),
    enabled: int = Form(0),
):
    casino.update_game(
        game_id, display_name=display_name, category=category, price=price,
        cooldown_seconds=cooldown_seconds, description=description, enabled=enabled,
    )
    return RedirectResponse(f"/guild/{guild_id}/casino#jeu-{game_id}", status_code=303)


@app.post("/guild/{guild_id}/casino/game/{game_id}/delete")
async def casino_game_delete(guild_id: int, game_id: int):
    casino.delete_game(game_id)
    return RedirectResponse(f"/guild/{guild_id}/casino", status_code=303)


@app.post("/guild/{guild_id}/casino/game/{game_id}/lot/add")
async def casino_lot_add(
    guild_id: int, game_id: int,
    reward_kind: str = Form("money"),
    reward_value: str = Form(...),
    label: str = Form(""),
    weight: float = Form(1),
    outcome: str = Form(""),
):
    try:
        casino.add_lot(
            game_id, reward_kind, reward_value, label=label, weight=weight,
            outcome=int(outcome) if outcome.strip() else None,
        )
    except (CasinoError, ValueError):
        pass
    return RedirectResponse(f"/guild/{guild_id}/casino#jeu-{game_id}", status_code=303)


@app.post("/guild/{guild_id}/casino/lot/{lot_id}/edit")
async def casino_lot_edit(
    guild_id: int, lot_id: int,
    reward_value: str = Form(...),
    weight: float = Form(1),
    game_id: int = Form(0),
):
    try:
        casino.update_lot(lot_id, reward_value=reward_value, weight=weight)
    except CasinoError:
        pass
    return RedirectResponse(f"/guild/{guild_id}/casino#jeu-{game_id}", status_code=303)


@app.post("/guild/{guild_id}/casino/lot/{lot_id}/delete")
async def casino_lot_delete(guild_id: int, lot_id: int, game_id: int = Form(0)):
    casino.delete_lot(lot_id)
    return RedirectResponse(f"/guild/{guild_id}/casino#jeu-{game_id}", status_code=303)


@app.post("/guild/{guild_id}/casino/quest/add")
async def casino_quest_add(
    guild_id: int,
    name: str = Form(...),
    goal: int = Form(1),
    reward_kind: str = Form("money"),
    reward_value: str = Form(...),
    target_kind: str = Form("any"),
    target_value: str = Form(""),
    description: str = Form(""),
    repeatable: int = Form(0),
):
    try:
        casino.create_quest(
            guild_id, name, goal, reward_kind, reward_value,
            target_kind=target_kind, target_value=target_value,
            description=description, repeatable=bool(repeatable),
        )
    except CasinoError:
        pass
    return RedirectResponse(f"/guild/{guild_id}/casino#quetes", status_code=303)


@app.post("/guild/{guild_id}/casino/quest/{quest_id}/delete")
async def casino_quest_delete(guild_id: int, quest_id: int):
    casino.delete_quest(quest_id)
    return RedirectResponse(f"/guild/{guild_id}/casino#quetes", status_code=303)


@app.post("/guild/{guild_id}/casino/style")
async def casino_style_save(
    guild_id: int,
    animations_enabled: int = Form(0),
    frame_count: int = Form(4),
    frame_delay_ms: int = Form(650),
    reel_symbols: str = Form(""),
    reel_width: int = Form(3),
    suspense_text: str = Form(""),
    win_emoji: str = Form("🎉"),
    lose_emoji: str = Form("💸"),
    win_color: str = Form("#57F287"),
    lose_color: str = Form("#ED4245"),
    jackpot_threshold: float = Form(0),
    jackpot_text: str = Form(""),
    currency_symbol: str = Form("$"),
):
    casino.update_style(
        guild_id, animations_enabled=animations_enabled, frame_count=frame_count,
        frame_delay_ms=frame_delay_ms, reel_symbols=reel_symbols, reel_width=reel_width,
        suspense_text=suspense_text, win_emoji=win_emoji, lose_emoji=lose_emoji,
        win_color=win_color, lose_color=lose_color, jackpot_threshold=jackpot_threshold,
        jackpot_text=jackpot_text, currency_symbol=currency_symbol,
    )
    return RedirectResponse(f"/guild/{guild_id}/casino#effets", status_code=303)


@app.post("/guild/{guild_id}/invitations/reward")
async def invite_reward_save(guild_id: int, threshold: int = Form(...),
                             amount: float = Form(...)):
    db.execute(
        "INSERT INTO invite_rewards (guild_id, threshold, amount) VALUES (?, ?, ?) "
        "ON CONFLICT(guild_id, threshold) DO UPDATE SET amount = excluded.amount",
        (guild_id, threshold, amount),
    )
    return RedirectResponse(f"/guild/{guild_id}/invitations", status_code=303)


@app.post("/guild/{guild_id}/invitations/reward/delete")
async def invite_reward_delete(guild_id: int, threshold: int = Form(...)):
    db.execute(
        "DELETE FROM invite_rewards WHERE guild_id = ? AND threshold = ?",
        (guild_id, threshold),
    )
    return RedirectResponse(f"/guild/{guild_id}/invitations", status_code=303)


@app.get("/api/guild/{guild_id}/casino")
async def api_casino(guild_id: int):
    games = []
    for game in casino.list_games(guild_id, include_disabled=True):
        games.append({
            "slug": game["slug"], "name": game["display_name"], "kind": game["kind"],
            "category": game["category"], "price": game["price"],
            "cooldown_seconds": game["cooldown_seconds"], "enabled": bool(game["enabled"]),
            "expected_value": casino.expected_value(game),
            "rtp": casino.theoretical_rtp(game),
            "lots": casino.list_lots(game["id"]),
        })
    return {"games": games, "stats": casino.actual_stats(guild_id)}


@app.get("/api/notes")
async def api_notes(guild_id: int = 0):
    if guild_id:
        notes = db.fetchall(
            "SELECT guild_id, title, content FROM notes WHERE guild_id IN (?, 0) "
            "ORDER BY guild_id DESC, title",
            (guild_id,),
        )
    else:
        notes = db.fetchall("SELECT guild_id, title, content FROM notes ORDER BY guild_id, title")
    return {"notes": [dict(n) for n in notes]}


# ── Notes (par serveur) ──
# Les notes sont scopees par serveur depuis la migration 0010. Les notes creees
# avant portent guild_id = 0 : elles restent visibles partout, signalees comme
# heritees, et peuvent etre supprimees depuis n'importe quel serveur.

@app.get("/guild/{guild_id}/notes", response_class=HTMLResponse)
async def guild_notes_page(request: Request, guild_id: int):
    notes = db.fetchall(
        "SELECT guild_id, title, content FROM notes WHERE guild_id IN (?, 0) "
        "ORDER BY guild_id DESC, title",
        (guild_id,),
    )
    return templates.TemplateResponse(request, "notes.html", {
        "request": request, "guild_id": guild_id, "notes": notes,
    })


@app.post("/guild/{guild_id}/notes/add")
async def guild_notes_add(guild_id: int, title: str = Form(...), content: str = Form(...)):
    db.execute(
        "INSERT INTO notes (guild_id, title, content) VALUES (?, ?, ?) "
        "ON CONFLICT(guild_id, title) DO UPDATE SET content = excluded.content",
        (guild_id, title.strip(), content),
    )
    return RedirectResponse(f"/guild/{guild_id}/notes", status_code=303)


@app.post("/guild/{guild_id}/notes/delete")
async def guild_notes_delete(guild_id: int, title: str = Form(...), scope: int = Form(0)):
    db.execute("DELETE FROM notes WHERE guild_id = ? AND title = ?", (scope, title))
    return RedirectResponse(f"/guild/{guild_id}/notes", status_code=303)


# ── Transactions (par serveur) ──

@app.get("/guild/{guild_id}/transactions", response_class=HTMLResponse)
async def guild_transactions_page(request: Request, guild_id: int):
    txs = db.fetchall(
        "SELECT * FROM transactions WHERE guild_id = ? ORDER BY created_at DESC LIMIT 100",
        (guild_id,),
    )
    return templates.TemplateResponse(request, "transactions.html", {
        "request": request, "guild_id": guild_id, "transactions": txs,
    })


# ── Rappels (par serveur) ──
# Consultation seule : un rappel a besoin d'un salon et d'un auteur Discord,
# c'est ,rmd cote bot qui les cree. Le dashboard liste et supprime.

@app.get("/guild/{guild_id}/reminders", response_class=HTMLResponse)
async def guild_reminders_page(request: Request, guild_id: int):
    now = time.time()
    pending = db.fetchall(
        "SELECT * FROM reminders WHERE guild_id = ? AND remind_at > ? ORDER BY remind_at LIMIT 100",
        (guild_id, now),
    )
    past = db.fetchall(
        "SELECT * FROM reminders WHERE guild_id = ? AND remind_at <= ? "
        "ORDER BY remind_at DESC LIMIT 30",
        (guild_id, now),
    )
    return templates.TemplateResponse(request, "reminders.html", {
        "request": request, "guild_id": guild_id, "reminders": pending, "past": past,
    })


@app.post("/guild/{guild_id}/reminders/delete")
async def guild_reminders_delete(guild_id: int, reminder_id: int = Form(...)):
    db.execute("DELETE FROM reminders WHERE id = ? AND guild_id = ?", (reminder_id, guild_id))
    return RedirectResponse(f"/guild/{guild_id}/reminders", status_code=303)


# ── Giveaways (par serveur) ──
# Consultation seule : un giveaway vit sur un message Discord (reactions), il ne
# peut pas etre cree depuis le web sans salon ni message.

@app.get("/guild/{guild_id}/giveaways", response_class=HTMLResponse)
async def guild_giveaways_page(request: Request, guild_id: int):
    active = db.fetchall(
        "SELECT * FROM giveaways WHERE guild_id = ? AND ended = 0 ORDER BY ends_at", (guild_id,)
    )
    ended = db.fetchall(
        "SELECT * FROM giveaways WHERE guild_id = ? AND ended = 1 ORDER BY ends_at DESC LIMIT 30",
        (guild_id,),
    )
    return templates.TemplateResponse(request, "giveaways.html", {
        "request": request, "guild_id": guild_id, "active": active, "ended": ended,
    })


@app.post("/guild/{guild_id}/giveaways/end")
async def guild_giveaway_end(guild_id: int, giveaway_id: int = Form(...)):
    db.execute(
        "UPDATE giveaways SET ended = 1 WHERE id = ? AND guild_id = ?", (giveaway_id, guild_id)
    )
    return RedirectResponse(f"/guild/{guild_id}/giveaways", status_code=303)


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", "8080"))
    uvicorn.run(app, host=host, port=port)
