import discord
import pytest
from discord.ext import commands

from ai_assistant import cmdai
from animations import cmdanim
from diagnostics import EXPECTED_COMMANDS, cmddiagnostics
from economie import cmdeco
from help_cmd import cmdhelp
from income import cmdincome
from jeu import cmdjeu
from moderation import cmdmoderation
from Notifrss import cmdrss
from utility import cmdutility
from work import cmdwork


@pytest.mark.asyncio
async def test_run_selftest_deep_contract():
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

    diag = cmddiagnostics(bot)
    result = diag.run_selftest(mode="deep")

    assert result["checks_total"] >= len(EXPECTED_COMMANDS)
    assert result["checks_ok"] >= 1
    assert isinstance(result["details"], list)
    assert isinstance(result["missing_commands"], list)

    await bot.close()
