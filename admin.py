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
})
