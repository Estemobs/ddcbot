import asyncio
import discord
import json
import os
import traceback
from discord.ext import commands
from data.db import Database
from admin import ADMIN_COMMANDS
from cogs.Notifrss import cmdrss
from cogs.utility import cmdutility
from cogs.moderation import cmdmoderation
from cogs.animations import cmdanim
from cogs.income import cmdincome
from cogs.economie import cmdeco
from cogs.work import cmdwork
from cogs.jeu import cmdjeu
from cogs.help_cmd import cmdhelp
from cogs.ai_assistant import cmdai
from cogs.diagnostics import cmddiagnostics
from cogs.logs_cmd import cmdlogs
from cogs.notes import cmdnotes
from cogs.changelog import cmdchangelog
from cogs.leveling import cmdleveling
from cogs.reactroles import cmdreactroles
from cogs.guild_settings import cmdguildsettings
from cogs.automod import cmdautomod
from cogs.translation import cmdtranslation
from cogs.minecraft import cmdminecraft
from cogs.invitations import cmdinvitations
from cogs.steam import cmdsteam
from cogs.ai_moderation import cmdaimoderation
from cogs.tickets import cmdtickets
from cogs.webhooks import cmdwebhooks
from cogs.lockdown import cmdlockdown

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix=",", intents=intents, help_command=None)
db = Database()


def load_permission_config(guild_id: int):
    row = db.fetchone("SELECT config_json FROM permission_config WHERE guild_id = ?", (guild_id,))
    if row is None:
        return {}
    try:
        data = json.loads(row["config_json"])
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
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

    guild_cfg = load_permission_config(ctx.guild.id)
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
    print(f"[DEBUG] Commandes chargees: {len(bot.commands)}")
    await bot.change_presence(activity=discord.Game(name=",help"))
    try:
        await bot.tree.sync()
    except Exception as exc:
        print(f"[DEBUG] Synchronisation slash impossible: {exc}")


@bot.event
async def on_command(ctx):
    print(f"[DEBUG] Commande recue: {ctx.command} | auteur={ctx.author} | salon={ctx.channel}")


@bot.event
async def on_command_completion(ctx):
    print(f"[DEBUG] Commande terminee: {ctx.command} | auteur={ctx.author}")

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

    logs_cog = bot.get_cog("cmdlogs")
    channels = logs_cog.get_channels(ctx.guild, "user_errors" if is_expected else "unexpected_errors") if logs_cog else []
    command_name = ctx.command.qualified_name if ctx.command else "inconnue"
    for channel in channels:
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

def load_token():
    env_token = os.environ.get("DDC_TOKEN")
    if env_token:
        return env_token
    secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'secrets.json')
    if not os.path.exists(secrets_path):
        raise FileNotFoundError(
            "Aucun token trouvé. Définissez DDC_TOKEN dans l'environnement "
            "ou créez un fichier secrets.json contenant {\"ddc_token\": \"...\"}."
        )
    with open(secrets_path) as f:
        data = json.load(f)
    token = data.get('ddc_token')
    if not token:
        raise ValueError("La cle 'ddc_token' est absente de secrets.json.")
    return token


async def main():
    token = load_token()
    await bot.add_cog(cmdrss(bot, db))
    await bot.add_cog(cmdutility(bot, db))
    await bot.add_cog(cmdmoderation(bot, db))
    await bot.add_cog(cmdanim(bot, db))
    await bot.add_cog(cmdincome(bot, db))
    await bot.add_cog(cmdeco(bot, db))
    await bot.add_cog(cmdwork(bot, db))
    await bot.add_cog(cmdjeu(bot, db))
    await bot.add_cog(cmdhelp(bot))
    await bot.add_cog(cmdai(bot))
    await bot.add_cog(cmdlogs(bot, db))
    await bot.add_cog(cmdnotes(bot, db))
    await bot.add_cog(cmdchangelog(bot))
    await bot.add_cog(cmddiagnostics(bot, db))
    await bot.add_cog(cmdleveling(bot, db))
    await bot.add_cog(cmdreactroles(bot, db))
    await bot.add_cog(cmdguildsettings(bot, db))
    await bot.add_cog(cmdautomod(bot, db))
    await bot.add_cog(cmdtranslation(bot, db))
    await bot.add_cog(cmdminecraft(bot, db))
    await bot.add_cog(cmdinvitations(bot, db))
    await bot.add_cog(cmdsteam(bot, db))
    await bot.add_cog(cmdaimoderation(bot, db))
    await bot.add_cog(cmdtickets(bot, db))
    await bot.add_cog(cmdwebhooks(bot, db))
    await bot.add_cog(cmdlockdown(bot, db))
    await bot.start(token)

asyncio.run(main())
