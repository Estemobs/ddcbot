import asyncio
import discord
import json
import os
import traceback
from discord.ext import commands
from Notifrss import cmdrss
from utility import cmdutility
from moderation import cmdmoderation
from animations import cmdanim
from income import cmdincome
from economie import cmdeco
from work import cmdwork
from jeu import cmdjeu
from help_cmd import cmdhelp

bot = commands.Bot(command_prefix=",", intents=discord.Intents.all(), help_command=None)

ADMIN_COMMANDS = {
    "modpanel", "warnconfig", "permpanel", "warn", "warns", "clearwarns", "ban", "kick", "clear", "unban",
    "timeout", "untimeout", "slowmode", "lock", "unlock", "addmoney", "removemoney", "reset_money",
    "reset_economy", "clean_leaderboard", "ecopanel", "config_work", "role_income_add", "role_income_remove",
    "role_income_edit", "addgame", "deletegame", "addquest", "deletequete", "config_quete", "clearinventory",
    "gstart", "gend", "gcancel",
}


def load_permission_config():
    path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "permission_config.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


@bot.check
async def admin_role_gate(ctx):
    if not ctx.guild or not ctx.command:
        return True

    command_name = ctx.command.qualified_name
    if command_name not in ADMIN_COMMANDS:
        return True

    member = ctx.author
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True

    config = load_permission_config()
    guild_cfg = config.get(str(ctx.guild.id), {}) if isinstance(config, dict) else {}
    admin_roles = guild_cfg.get("admin_roles", []) if isinstance(guild_cfg, dict) else []
    command_roles = guild_cfg.get("command_roles", {}) if isinstance(guild_cfg, dict) else {}
    allowed_roles = command_roles.get(command_name, admin_roles)

    if not allowed_roles:
        return False

    member_role_ids = {role.id for role in member.roles}
    return any(role_id in member_role_ids for role_id in allowed_roles)

@bot.event
async def on_ready():
    print("Le bot est en ligne")
    await bot.change_presence(activity=discord.Game(name=",help"))

@bot.event
async def on_command_error(ctx, error):
    # Laisse les handlers locaux de commandes prendre la main s'ils existent.
    if hasattr(ctx.command, "on_error"):
        return

    original = getattr(error, "original", error)
    expected_user_errors = (
        commands.MissingRequiredArgument,
        commands.BadArgument,
        commands.MemberNotFound,
        commands.UserNotFound,
        commands.ChannelNotFound,
        commands.RoleNotFound,
        commands.BadUnionArgument,
        commands.ArgumentParsingError,
        commands.MissingPermissions,
        commands.BotMissingPermissions,
        commands.CheckFailure,
        commands.CommandNotFound,
        commands.CommandOnCooldown,
    )
    is_expected = isinstance(original, expected_user_errors)

    channel = bot.get_channel(827566899004440666)
    if channel:
        command_name = ctx.command.qualified_name if ctx.command else "inconnue"
        if is_expected:
            await channel.send(
                f"Erreur utilisateur sur `{command_name}` par {ctx.author}: {original}"
            )
        else:
            error_traceback = traceback.format_exception(type(original), original, original.__traceback__)
            error_msg = ''.join(error_traceback)
            await channel.send(
                f"Erreur lors de l'exécution de la commande `{command_name}` par {ctx.author}: {original}\n```{error_msg}```"
            )

    if not is_expected:
        print(''.join(traceback.format_exception(type(original), original, original.__traceback__)))

    usage = None
    if ctx.command:
        signature = ctx.command.signature.strip()
        usage = f"{ctx.prefix}{ctx.command.qualified_name} {signature}".strip()

    if isinstance(original, commands.MissingRequiredArgument):
        await ctx.send("❌ Argument manquant.")
        if usage:
            await ctx.send(f"Syntaxe: `{usage}`")
        await ctx.send_help(ctx.command)
    elif isinstance(original, (commands.BadArgument, commands.MemberNotFound, commands.UserNotFound,
                               commands.ChannelNotFound, commands.RoleNotFound,
                               commands.BadUnionArgument, commands.ArgumentParsingError)):
        await ctx.send(f"❌ Argument invalide: {original}")
        if usage:
            await ctx.send(f"Syntaxe: `{usage}`")
        await ctx.send_help(ctx.command)
    elif isinstance(original, commands.MissingPermissions):
        await ctx.send("❌ Vous n'avez pas la permission d'utiliser cette commande.")
    elif isinstance(original, commands.BotMissingPermissions):
        missing = ", ".join(original.missing_permissions)
        await ctx.send(f"❌ Il me manque des permissions: {missing}")
    elif isinstance(original, commands.CheckFailure):
        await ctx.send("❌ Vous n'avez pas le rôle requis pour utiliser cette commande.")
    elif isinstance(original, commands.CommandNotFound):
        pass  # Ignorer les commandes inconnues silencieusement
    elif isinstance(original, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Commande en cooldown. Reessaie dans {original.retry_after:.1f}s.")
    else:
        await ctx.send("❌ Une erreur inattendue est survenue. L'incident a ete journalise.")

async def main():
    with open('secrets.json') as f:
        data = json.load(f)
    token = data['ddc_token']
    await bot.add_cog(cmdrss(bot))
    await bot.add_cog(cmdutility(bot))
    await bot.add_cog(cmdmoderation(bot))
    await bot.add_cog(cmdanim(bot))
    await bot.add_cog(cmdincome(bot))
    await bot.add_cog(cmdeco(bot))
    await bot.add_cog(cmdwork(bot))
    await bot.add_cog(cmdjeu(bot))
    await bot.add_cog(cmdhelp(bot))
    await bot.start(token)

asyncio.run(main())
