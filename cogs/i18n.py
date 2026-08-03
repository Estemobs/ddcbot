"""Systeme de langues du bot.

Resolution : langue du serveur d'abord (table guild_lang), puis langue de
l'utilisateur (table user_lang), puis francais par defaut.
Les messages non encore traduits retombent sur leur cle / le francais.
"""

DEFAULT_LANG = "fr"
LANGUAGES = ("fr", "en")

STRINGS = {
    "lang_changed": {
        "fr": "Langue définie sur **{lang}**.",
        "en": "Language set to **{lang}**.",
    },
    "lang_invalid": {
        "fr": "Langue invalide. Langues disponibles : fr, en.",
        "en": "Invalid language. Available languages: fr, en.",
    },
    "guild_lang_changed": {
        "fr": "Langue du serveur définie sur **{lang}**.",
        "en": "Server language set to **{lang}**.",
    },
    "guild_lang_permission": {
        "fr": "Vous devez avoir la permission Manage Server.",
        "en": "You need the Manage Server permission.",
    },
    "rank_title": {
        "fr": "📊 Rang de {member}",
        "en": "📊 Rank of {member}",
    },
    "rank_field_level": {
        "fr": "Niveau",
        "en": "Level",
    },
    "rank_field_xp": {
        "fr": "XP",
        "en": "XP",
    },
    "rank_field_server_rank": {
        "fr": "Rang sur le serveur",
        "en": "Server rank",
    },
    "rank_field_global_rank": {
        "fr": "Rang global",
        "en": "Global rank",
    },
    "xp_not_enabled": {
        "fr": "Le système d'XP est désactivé sur ce serveur.",
        "en": "The XP system is disabled on this server.",
    },
    "xp_leveled_up": {
        "fr": "🎉 {mention} est passé au **niveau {level}** !",
        "en": "🎉 {mention} reached **level {level}**!",
    },
    "xp_gained": {
        "fr": "+{xp} XP ({level})",
        "en": "+{xp} XP ({level})",
    },
    "xp_config_saved": {
        "fr": "Configuration XP enregistrée.",
        "en": "XP configuration saved.",
    },
    "xp_config_title": {
        "fr": "⚙️ Configuration XP",
        "en": "⚙️ XP configuration",
    },
    "xp_config_enabled": {
        "fr": "Activé",
        "en": "Enabled",
    },
    "xp_config_xp_per_message": {
        "fr": "XP par message",
        "en": "XP per message",
    },
    "xp_config_cooldown": {
        "fr": "Cooldown (secondes)",
        "en": "Cooldown (seconds)",
    },
    "xp_config_announce": {
        "fr": "Salon d'annonce",
        "en": "Announce channel",
    },
    "xp_config_none": {
        "fr": "Aucun",
        "en": "None",
    },
    "reactrole_prompt": {
        "fr": "Envoyez le message où ajouter les réactions.",
        "en": "Send the message to add reactions to.",
    },
    "reactrole_invalid_message": {
        "fr": "ID de message invalide.",
        "en": "Invalid message ID.",
    },
    "reactrole_prompt_emoji": {
        "fr": "Réagissez au message de configuration avec l'emoji souhaité.",
        "en": "React to the setup message with the desired emoji.",
    },
    "reactrole_timeout": {
        "fr": "Temps écoulé. Commande annulée.",
        "en": "Timed out. Command cancelled.",
    },
    "reactrole_prompt_role": {
        "fr": "Quel rôle attribuer ? (ID ou mention)",
        "en": "Which role should be assigned? (ID or mention)",
    },
    "reactrole_invalid_role": {
        "fr": "Rôle invalide.",
        "en": "Invalid role.",
    },
    "reactrole_added": {
        "fr": "✅ Reaction-role ajouté : {emoji} → {role} sur le message {link}.",
        "en": "✅ Reaction role added: {emoji} → {role} on message {link}.",
    },
    "reactrole_removed": {
        "fr": "✅ Reaction-role retiré.",
        "en": "✅ Reaction role removed.",
    },
    "reactrole_not_found": {
        "fr": "Aucun reaction-role trouvé.",
        "en": "No reaction role found.",
    },
    "reactrole_list_empty": {
        "fr": "Aucun reaction-role configuré sur ce serveur.",
        "en": "No reaction roles configured on this server.",
    },
    "reactrole_list_title": {
        "fr": "🎭 Reaction roles du serveur",
        "en": "🎭 Server reaction roles",
    },
    "reactrole_need_manage": {
        "fr": "Vous devez avoir la permission Manage Server.",
        "en": "You need the Manage Server permission.",
    },
    "welcome_set": {
        "fr": "✅ Message de bienvenue configuré.",
        "en": "✅ Welcome message configured.",
    },
    "welcome_disabled": {
        "fr": "✅ Message de bienvenue désactivé.",
        "en": "✅ Welcome message disabled.",
    },
    "leave_set": {
        "fr": "✅ Message de départ configuré.",
        "en": "✅ Leave message configured.",
    },
    "leave_disabled": {
        "fr": "✅ Message de départ désactivé.",
        "en": "✅ Leave message disabled.",
    },
    "welcome_config_title": {
        "fr": "📋 Configuration accueil",
        "en": "📋 Welcome configuration",
    },
    "welcome_config_welcome": {
        "fr": "Bienvenue",
        "en": "Welcome",
    },
    "welcome_config_leave": {
        "fr": "Départs",
        "en": "Leaves",
    },
    "welcome_config_channel": {
        "fr": "Salon",
        "en": "Channel",
    },
    "welcome_config_message": {
        "fr": "Message",
        "en": "Message",
    },
    "welcome_placeholders": {
        "fr": "Placeholders : {{user}} (mention), {{server}}, {{count}} (nombre de membres).",
        "en": "Placeholders: {{user}} (mention), {{server}}, {{count}} (member count).",
    },
    "automod_enabled": {
        "fr": "Auto-mod activé.",
        "en": "Auto-mod enabled.",
    },
    "automod_disabled": {
        "fr": "Auto-mod désactivé.",
        "en": "Auto-mod disabled.",
    },
    "automod_word_added": {
        "fr": "Mot banni ajouté : `{word}`.",
        "en": "Banned word added: `{word}`.",
    },
    "automod_word_removed": {
        "fr": "Mot banni retiré : `{word}`.",
        "en": "Banned word removed: `{word}`.",
    },
    "automod_word_not_found": {
        "fr": "Ce mot n'est pas dans la liste.",
        "en": "This word is not in the list.",
    },
    "automod_list_empty": {
        "fr": "Aucun mot banni configuré.",
        "en": "No banned words configured.",
    },
    "automod_list_title": {
        "fr": "🚫 Mots bannis",
        "en": "🚫 Banned words",
    },
    "automod_config_title": {
        "fr": "⚙️ Auto-mod",
        "en": "⚙️ Auto-mod",
    },
    "automod_config_warn": {
        "fr": "Avertir",
        "en": "Warn",
    },
    "automod_config_delete": {
        "fr": "Supprimer le message",
        "en": "Delete message",
    },
    "automod_warned": {
        "fr": "Auto-mod : message supprimé pour mot banni.",
        "en": "Auto-mod: message deleted for banned word.",
    },
    "translation_error": {
        "fr": "Impossible de traduire ce message.",
        "en": "Unable to translate this message.",
    },
    "reminder_deleted": {
        "fr": "Rappel [{reminder_id}] annulé.",
        "en": "Reminder [{reminder_id}] cancelled.",
    },
    "minecraft_need_log": {
        "fr": "Configurez d'abord le chemin du log : `,mcconfig log <chemin>`.",
        "en": "First set the log path: `,mcconfig log <path>`.",
    },
    "minecraft_enabled": {
        "fr": "✅ Pont Discord <-> Minecraft activé. Canal de relais : ce salon.",
        "en": "✅ Discord <-> Minecraft bridge enabled. Relay channel: this channel.",
    },
    "minecraft_disabled": {
        "fr": "❌ Pont Discord <-> Minecraft désactivé.",
        "en": "❌ Discord <-> Minecraft bridge disabled.",
    },
    "minecraft_config_title": {
        "fr": "⚙️ Configuration du pont Minecraft",
        "en": "⚙️ Minecraft bridge configuration",
    },
    "minecraft_set_log": {
        "fr": "✅ Chemin du log défini : `{path}`.",
        "en": "✅ Log path set: `{path}`.",
    },
    "minecraft_set_channel": {
        "fr": "✅ Canal de relais défini sur ce salon.",
        "en": "✅ Relay channel set to this channel.",
    },
    "minecraft_set_method": {
        "fr": "✅ Méthode d'envoi : `{method}`.",
        "en": "✅ Send method: `{method}`.",
    },
    "minecraft_set_rcon": {
        "fr": "✅ RCON configuré : `{host}`.",
        "en": "✅ RCON configured: `{host}`.",
    },
    "minecraft_set_tmux": {
        "fr": "✅ Session tmux définie : `{session}`.",
        "en": "✅ tmux session set: `{session}`.",
    },
    "minecraft_set_sudo": {
        "fr": "✅ sudo : `{state}`.",
        "en": "✅ sudo: `{state}`.",
    },
    "minecraft_config_usage": {
        "fr": "Syntaxe : `,mcconfig log <chemin>` | `channel` | `method <rcon|tmux>` | "
              "`rcon <host> <port> <motdepasse>` | `tmux <session>` | `sudo on/off` | `show`.",
        "en": "Usage: `,mcconfig log <path>` | `channel` | `method <rcon|tmux>` | "
              "`rcon <host> <port> <password>` | `tmux <session>` | `sudo on/off` | `show`.",
    },
    "minecraft_empty": {
        "fr": "Message vide après nettoyage.",
        "en": "Message empty after sanitization.",
    },
    "minecraft_send_error": {
        "fr": "❌ Échec d'envoi vers Minecraft : {error}.",
        "en": "❌ Failed to send to Minecraft: {error}.",
    },
    "minecraft_sent": {
        "fr": "✅ Envoyé via {method} : {text}.",
        "en": "✅ Sent via {method}: {text}.",
    },
    "minecraft_status_title": {
        "fr": "📡 Statut du pont Minecraft",
        "en": "📡 Minecraft bridge status",
    },
    # --- invitations ---
    "inv_total_title": {
        "fr": "📊 Invitations sur le serveur",
        "en": "📊 Server invitations",
    },
    "inv_total": {
        "fr": "Total invitées",
        "en": "Total invited",
    },
    "inv_left": {
        "fr": "Parties",
        "en": "Left",
    },
    "inv_member_title": {
        "fr": "📊 Informations d'invitation",
        "en": "📊 Invitation info",
    },
    "inv_member": {
        "fr": "Utilisateur",
        "en": "User",
    },
    "inv_invited": {
        "fr": "Invitées",
        "en": "Invited",
    },
    "inv_remained": {
        "fr": "Restées",
        "en": "Remained",
    },
    "inv_top_title": {
        "fr": "🏆 Top invitateurs",
        "en": "🏆 Top inviters",
    },
    "inv_no_data": {
        "fr": "Aucune invitation enregistrée sur ce serveur.",
        "en": "No invitations recorded on this server.",
    },
    "inv_marked_left": {
        "fr": "✅ {member} est marqué comme ayant quitté le serveur.",
        "en": "✅ {member} marked as having left the server.",
    },
    # --- steam ---
    "steam_config_saved": {
        "fr": "✅ Clé API Steam enregistrée pour ce serveur.",
        "en": "✅ Steam API key saved for this server.",
    },
    "steam_no_key": {
        "fr": "❌ Aucune clé API Steam configurée. Un admin doit lancer `,steamconfig <cle_api>`.",
        "en": "❌ No Steam API key configured. An admin must run `,steamconfig <api_key>`.",
    },
    "steam_resolving": {
        "fr": "🔎 Résolution du pseudo Steam…",
        "en": "🔎 Resolving Steam username…",
    },
    "steam_not_found": {
        "fr": "❌ Aucun compte Steam trouvé pour `{name}`.",
        "en": "❌ No Steam account found for `{name}`.",
    },
    "steam_fetching": {
        "fr": "📦 Récupération de l'inventaire de `{steam_id}`…",
        "en": "📦 Fetching inventory for `{steam_id}`…",
    },
    "steam_empty": {
        "fr": "📭 L'inventaire de `{steam_id}` est vide ou privé.",
        "en": "📭 Inventory for `{steam_id}` is empty or private.",
    },
    "steam_inventory_title": {
        "fr": "🎮 Inventaire CS:GO de `{steam_id}`",
        "en": "🎮 CS:GO inventory of `{steam_id}`",
    },
    "steam_id_result": {
        "fr": "✅ SteamID64 de `{name}` : `{steam_id}`",
        "en": "✅ SteamID64 of `{name}`: `{steam_id}`",
    },
}


def _get(key, lang):
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get(DEFAULT_LANG) or key


def resolve_lang(db, guild_id=None, user_id=None):
    if guild_id:
        row = db.fetchone("SELECT lang FROM guild_lang WHERE guild_id = ?", (guild_id,))
        if row and row["lang"] in LANGUAGES:
            return row["lang"]
    if user_id:
        row = db.fetchone("SELECT lang FROM user_lang WHERE user_id = ?", (user_id,))
        if row and row["lang"] in LANGUAGES:
            return row["lang"]
    return DEFAULT_LANG


def t(db, key, guild_id=None, user_id=None, **kwargs):
    lang = resolve_lang(db, guild_id, user_id)
    return _get(key, lang).format(**kwargs)
