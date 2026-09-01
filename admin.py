"""Source unique de la liste des commandes d'administration.

Utilisee par main.py (gate admin globale) et par le panneau de permissions
(cogs/moderation.py) pour rester coherente.
"""

ADMIN_COMMANDS = frozenset({
    "modpanel", "warnconfig", "permpanel", "warn", "warns", "clearwarns", "ban", "kick", "clear", "unban",
    "timeout", "untimeout", "slowmode", "lock", "unlock", "addmoney", "removemoney", "reset_money",
    "reset_economy", "clean_leaderboard", "ecopanel", "incomepanel", "gamepanel", "config_work",
    "role_income_add", "role_income_remove", "role_income_edit", "addgame", "deletegame", "addquest",
    "deletequete", "config_quete", "clearinventory", "gstart", "gend", "gcancel", "selftest", "logspanel",
    "guildlang", "xpconfig", "xpset", "xptoggle", "reactrole", "reactroles", "reactrolerm", "setwelcome", "setleave",
    "welcomeconfig", "automod", "automodconfig", "badword",
    "mcenable", "mcdisable", "mcconfig", "mcsay", "mcstatus",
    "invleft", "steamconfig",
    "aimod", "aimodconfig", "aimodaction", "aimodthreshold", "aimodignore", "aimodlog",
    "ticketpanel", "ticketcategory", "ticketwelcome", "ticketmax", "ticketlog",
    "webhookset", "webhooktoggle", "webhookevent", "webhookconfig", "webhooksend",
    "lockdown", "unlockdown", "lockdownchannel", "unlockdownchannel", "lockdownconfig",
    "lockdownrole", "lockdownlog", "lockdownmassjoin", "lockdownauto",
    "starboard", "starboardclear",
    "plugins", "plugins list", "plugins enable", "plugins disable", "plugins reload",
    # Commandes qui s'appuyaient sur @commands.has_permissions(manage_guild=True) :
    # le decorateur court-circuitait la delegation par role du panneau de permissions.
    "setlog", "unsetlog",
    "cmdadd", "cmdedit", "cmdrm", "cmdlist",
    "poll", "pollclose", "pollresults",
    "twitch", "twitchconfig",
    # Ecriture des notes du serveur : n'etait protegee par rien.
    "addtag", "removetag", "tagedit", "tagrename",
    # Casino : creation/edition des jeux, lots, quetes et statistiques.
    "addlot", "rmlot", "gamelots", "casinostats", "inviterewards",
    # Modules serveur ajoutes : configuration reservee aux admins.
    "annivconfig", "tempvoice", "statschannel", "alerts",
})
