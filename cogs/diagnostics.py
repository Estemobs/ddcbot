import importlib

import discord
from discord.ext import commands


EXPECTED_COMMANDS = {
    "help",
    "role_id",
    "role_name",
    "rmd",
    "avatar",
    "serverpicture",
    "devoir",
    "warn",
    "modpanel",
    "warnconfig",
    "permpanel",
    "warns",
    "clearwarns",
    "ban",
    "kick",
    "clear",
    "unban",
    "timeout",
    "untimeout",
    "slowmode",
    "lock",
    "unlock",
    "mybalance",
    "balance",
    "paye",
    "leaderboard",
    "addmoney",
    "removemoney",
    "reset_money",
    "reset_economy",
    "clean_leaderboard",
    "ecopanel",
    "work",
    "show_work_config",
    "config_work",
    "collect_income",
    "role_income_list",
    "role_income_add",
    "role_income_remove",
    "role_income_edit",
    "incomepanel",
    "shop",
    "openlot",
    "inventaire",
    "quest",
    "addgame",
    "deletegame",
    "addquest",
    "deletequete",
    "config_quete",
    "clearinventory",
    "gamepanel",
    "gstart",
    "gend",
    "gcancel",
    "subscribe",
    "notifications",
    "delnotif",
    "selftest",
    "addtag",
    "removetag",
    "tagedit",
    "tagrename",
    "tag",
    "taglist",
    "changelog",
    "version",
    "setlog",
    "unsetlog",
    "listlogs",
    "logspanel",
}

REQUIRED_MODULES = [
    "discord",
    "aiohttp",
    "requests",
    "g4f",
    "numpy",
    "cv2",
    "PIL",
    "easyocr",
    "nest_asyncio",
    "curl_cffi",
]

EXPECTED_TABLES = [
    "balances",
    "economy_config",
    "role_income",
    "income_config",
    "work_settings",
    "work_state",
    "games",
    "quests",
    "inventory_tickets",
    "game_panel_config",
    "moderation_config",
    "warn_counts",
    "permission_config",
    "logs_config",
    "notes",
    "notifications",
]


class cmddiagnostics(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    def _table_exists(self, table_name: str) -> bool:
        row = self.db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,)
        )
        return row is not None

    def run_selftest(self, mode: str = "basic"):
        checks_ok = 0
        checks_total = 0
        details = []

        registered_commands = {command.name: command for command in self.bot.commands}
        registered_names = set(registered_commands.keys())
        missing_commands = sorted(EXPECTED_COMMANDS - registered_names)
        checks_total += 1
        if not missing_commands:
            checks_ok += 1
            details.append("[OK] Registre commandes")
        else:
            details.append(f"[KO] Commandes manquantes: {', '.join(missing_commands)}")

        loaded_cogs = sorted(self.bot.cogs.keys())
        checks_total += 1
        if loaded_cogs:
            checks_ok += 1
            details.append(f"[OK] Cogs charges ({len(loaded_cogs)})")
        else:
            details.append("[KO] Aucun cog charge")

        module_issues = []
        for module_name in REQUIRED_MODULES:
            checks_total += 1
            try:
                importlib.import_module(module_name)
                checks_ok += 1
            except Exception as exc:
                module_issues.append(f"{module_name}: {exc}")
        if not module_issues:
            details.append("[OK] Modules Python requis")
        else:
            details.append("[KO] Modules manquants/invalides: " + " | ".join(module_issues))

        table_issues = []
        for table_name in EXPECTED_TABLES:
            checks_total += 1
            if self._table_exists(table_name):
                checks_ok += 1
            else:
                table_issues.append(table_name)
        if not table_issues:
            details.append("[OK] Tables SQLite")
        else:
            details.append("[KO] Tables manquantes: " + ", ".join(table_issues))

        if mode == "deep":
            callback_issues = []
            check_issues = []
            for command_name in sorted(EXPECTED_COMMANDS):
                checks_total += 1
                command = registered_commands.get(command_name)
                if not command:
                    callback_issues.append(f"{command_name}: absent")
                    continue
                if not callable(getattr(command, "callback", None)):
                    callback_issues.append(f"{command_name}: callback invalide")
                    continue
                checks_ok += 1

                checks_total += 1
                if command.checks is None:
                    check_issues.append(f"{command_name}: checks None")
                else:
                    checks_ok += 1

            if callback_issues:
                details.append("[KO] Callbacks commandes: " + " | ".join(callback_issues))
            else:
                details.append("[OK] Callbacks commandes")

            if check_issues:
                details.append("[KO] Structure checks commandes: " + " | ".join(check_issues))
            else:
                details.append("[OK] Structure checks commandes")

            checks_total += 1
            integrity_row = self.db.fetchone("PRAGMA integrity_check")
            integrity_status = integrity_row[0] if integrity_row else "inconnue"
            if integrity_status == "ok":
                checks_ok += 1
                details.append("[OK] Integrite base SQLite")
            else:
                details.append(f"[KO] Integrite base SQLite: {integrity_status}")

        return {
            "checks_ok": checks_ok,
            "checks_total": checks_total,
            "details": details,
            "missing_commands": missing_commands,
            "loaded_cogs": loaded_cogs,
        }

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def selftest(self, ctx, mode: str = "basic"):
        mode = mode.lower().strip()
        if mode not in {"basic", "deep"}:
            await ctx.send("Mode invalide. Utilisez `,selftest` ou `,selftest deep`.")
            return

        result = self.run_selftest(mode=mode)
        checks_ok = result["checks_ok"]
        checks_total = result["checks_total"]
        details = result["details"]
        missing_commands = result["missing_commands"]
        loaded_cogs = result["loaded_cogs"]

        ratio = f"{checks_ok}/{checks_total}"
        color = discord.Color.green() if checks_ok == checks_total else discord.Color.orange()

        embed = discord.Embed(
            title="Selftest Bot",
            description=f"Diagnostic global des commandes et fonctionnalites (mode: {mode}).",
            color=color,
        )
        embed.add_field(name="Resultat", value=ratio, inline=False)
        embed.add_field(name="Cogs", value=", ".join(loaded_cogs) if loaded_cogs else "Aucun", inline=False)

        if missing_commands:
            missing_preview = ", ".join(missing_commands[:15])
            if len(missing_commands) > 15:
                missing_preview += ", ..."
            embed.add_field(name="Commandes manquantes", value=missing_preview, inline=False)

        await ctx.send(embed=embed)

        for line in details:
            await ctx.send(line)


def setup(bot, db):
    bot.add_cog(cmddiagnostics(bot, db))
