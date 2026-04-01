import importlib
import json
import os

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

JSON_FILES = [
    "balances.json",
    "income.json",
    "inventaire.json",
    "notifications.json",
    "quete.json",
    "gameconfig.json",
    "workconfig.json",
]

OPTIONAL_JSON_FILES = [
    "moderation_config.json",
    "economy_config.json",
    "income_config.json",
    "game_panel_config.json",
    "permission_config.json",
    "warn_history.json",
]


class cmddiagnostics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.base_dir = os.path.abspath(os.path.dirname(__file__))

    def _check_json_file(self, file_name: str):
        path = os.path.join(self.base_dir, file_name)
        if not os.path.exists(path):
            return False, "absent"
        try:
            with open(path, "r") as f:
                json.load(f)
            return True, "ok"
        except Exception as exc:
            return False, f"json invalide: {exc}"

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def selftest(self, ctx):
        checks_ok = 0
        checks_total = 0
        details = []

        registered = {command.name for command in self.bot.commands}
        missing_commands = sorted(EXPECTED_COMMANDS - registered)
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

        json_issues = []
        for file_name in JSON_FILES:
            checks_total += 1
            ok, msg = self._check_json_file(file_name)
            if ok:
                checks_ok += 1
            else:
                json_issues.append(f"{file_name} ({msg})")
        if not json_issues:
            details.append("[OK] JSON obligatoires")
        else:
            details.append("[KO] JSON obligatoires: " + " | ".join(json_issues))

        optional_issues = []
        for file_name in OPTIONAL_JSON_FILES:
            path = os.path.join(self.base_dir, file_name)
            if os.path.exists(path):
                checks_total += 1
                ok, msg = self._check_json_file(file_name)
                if ok:
                    checks_ok += 1
                else:
                    optional_issues.append(f"{file_name} ({msg})")
        if optional_issues:
            details.append("[KO] JSON optionnels invalides: " + " | ".join(optional_issues))
        else:
            details.append("[OK] JSON optionnels")

        ratio = f"{checks_ok}/{checks_total}"
        color = discord.Color.green() if checks_ok == checks_total else discord.Color.orange()

        embed = discord.Embed(
            title="Selftest Bot",
            description="Diagnostic global des commandes et fonctionnalites.",
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


def setup(bot):
    bot.add_cog(cmddiagnostics(bot))
