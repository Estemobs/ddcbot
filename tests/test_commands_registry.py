import importlib

import discord
import pytest
from discord.ext import commands

from Notifrss import cmdrss
from animations import cmdanim
from economie import cmdeco
from help_cmd import cmdhelp
from income import cmdincome
from jeu import cmdjeu
from moderation import cmdmoderation
from utility import cmdutility
from work import cmdwork
from ai_assistant import cmdai
from diagnostics import cmddiagnostics


EXPECTED_COMMANDS = {
    "help",
    "subscribe",
    "notifications",
    "delnotif",
    "role_id",
    "role_name",
    "rmd",
    "avatar",
    "serverpicture",
    "devoir",
    "selftest",
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
    "gstart",
    "gend",
    "gcancel",
    "role_income_add",
    "role_income_remove",
    "role_income_list",
    "role_income_edit",
    "collect_income",
    "incomepanel",
    "mybalance",
    "balance",
    "addmoney",
    "removemoney",
    "paye",
    "leaderboard",
    "clean_leaderboard",
    "ecopanel",
    "reset_money",
    "reset_economy",
    "config_work",
    "show_work_config",
    "work",
    "addgame",
    "openlot",
    "deletegame",
    "shop",
    "inventaire",
    "clearinventory",
    "addquest",
    "deletequete",
    "quest",
    "config_quete",
    "gamepanel",
}


@pytest.mark.asyncio
async def test_all_cogs_register_expected_commands():
    bot = commands.Bot(command_prefix=",", intents=discord.Intents.none(), help_command=None)

    await bot.add_cog(cmdrss(bot))
    await bot.add_cog(cmdutility(bot))
    await bot.add_cog(cmdmoderation(bot))
    await bot.add_cog(cmdanim(bot))
    await bot.add_cog(cmdincome(bot))
    await bot.add_cog(cmdeco(bot))
    await bot.add_cog(cmdwork(bot))
    await bot.add_cog(cmdjeu(bot))
    await bot.add_cog(cmdhelp(bot))
    await bot.add_cog(cmdai(bot))
    await bot.add_cog(cmddiagnostics(bot))

    registered = {command.name for command in bot.commands}
    missing = EXPECTED_COMMANDS - registered

    assert not missing, f"Commandes manquantes: {sorted(missing)}"

    await bot.close()


@pytest.mark.parametrize(
    "module_name",
    [
        "Notifrss",
        "utility",
        "moderation",
        "animations",
        "income",
        "economie",
        "work",
        "jeu",
        "help_cmd",
        "ai_assistant",
        "diagnostics",
    ],
)
def test_modules_import_without_syntax_error(module_name):
    importlib.import_module(module_name)
