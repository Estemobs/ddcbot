import json
import os
from datetime import timedelta

import discord
from discord.ext import commands


DEFAULT_MOD_CONFIG = {
    "warn": {
        "dm_user": True,
        "announce_public": True,
        "require_reason": True,
        "log_channel_id": None,
    },
    "actions": {
        "auto_timeout_enabled": False,
        "auto_timeout_after_warns": 3,
        "auto_timeout_minutes": 30,
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

ADMIN_COMMANDS = [
    "modpanel",
    "warnconfig",
    "permpanel",
    "warn",
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
    "addmoney",
    "removemoney",
    "reset_money",
    "reset_economy",
    "clean_leaderboard",
    "ecopanel",
    "config_work",
    "role_income_add",
    "role_income_remove",
    "role_income_edit",
    "addgame",
    "deletegame",
    "addquest",
    "deletequete",
    "config_quete",
    "clearinventory",
    "gstart",
    "gend",
    "gcancel",
]


class BaseModPanelView(discord.ui.View):
    page_name = "warn"

    def __init__(self, cog, guild_id: int, author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Seul l'auteur de la commande peut modifier ce panneau.",
                ephemeral=True,
            )
            return False
        permissions = interaction.user.guild_permissions
        if not permissions.manage_guild:
            await interaction.response.send_message(
                "Permission manquante: Manage Server.",
                ephemeral=True,
            )
            return False
        return True

    async def _render_page(self, interaction: discord.Interaction, page: str):
        embed = self.cog.build_mod_panel_embed(interaction.guild, page)
        view = self.cog.build_mod_panel_view(page, interaction.guild.id, self.author_id)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _refresh(self, interaction: discord.Interaction):
        await self._render_page(interaction, self.page_name)

    @discord.ui.button(label="Warn", style=discord.ButtonStyle.secondary, row=0)
    async def goto_warn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render_page(interaction, "warn")

    @discord.ui.button(label="Actions", style=discord.ButtonStyle.secondary, row=0)
    async def goto_actions(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render_page(interaction, "actions")

    @discord.ui.button(label="Notifications", style=discord.ButtonStyle.secondary, row=0)
    async def goto_notifications(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render_page(interaction, "notifications")

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, row=0)
    async def close_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        embed = self.cog.build_mod_panel_embed(interaction.guild, self.page_name)
        embed.set_footer(text="Panneau ferme")
        await interaction.response.edit_message(embed=embed, view=self)


class WarnPanelView(BaseModPanelView):
    page_name = "warn"

    @discord.ui.button(label="Toggle raison obligatoire", style=discord.ButtonStyle.primary, row=1)
    async def toggle_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["warn"]["require_reason"] = not cfg["warn"]["require_reason"]
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Toggle DM warn", style=discord.ButtonStyle.primary, row=1)
    async def toggle_dm_warn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["warn"]["dm_user"] = not cfg["warn"]["dm_user"]
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Toggle annonce publique", style=discord.ButtonStyle.primary, row=1)
    async def toggle_warn_public(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["warn"]["announce_public"] = not cfg["warn"]["announce_public"]
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Canal logs = ici", style=discord.ButtonStyle.secondary, row=2)
    async def set_log_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["warn"]["log_channel_id"] = interaction.channel_id
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Reset warns membre", style=discord.ButtonStyle.secondary, row=2)
    async def reset_warns_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_history = self.cog.warn_history.setdefault(str(self.guild_id), {})
        guild_history[str(interaction.user.id)] = 0
        self.cog.save_warn_history()
        await interaction.response.send_message("Vos warns ont ete reinitialises.", ephemeral=True)


class ActionsPanelView(BaseModPanelView):
    page_name = "actions"

    @discord.ui.button(label="Toggle auto-timeout", style=discord.ButtonStyle.primary, row=1)
    async def toggle_auto_timeout(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["actions"]["auto_timeout_enabled"] = not cfg["actions"]["auto_timeout_enabled"]
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Seuil warns +1", style=discord.ButtonStyle.secondary, row=1)
    async def threshold_plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["actions"]["auto_timeout_after_warns"] += 1
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Seuil warns -1", style=discord.ButtonStyle.secondary, row=1)
    async def threshold_minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["actions"]["auto_timeout_after_warns"] = max(1, cfg["actions"]["auto_timeout_after_warns"] - 1)
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Duree auto-timeout +5m", style=discord.ButtonStyle.secondary, row=2)
    async def timeout_plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["actions"]["auto_timeout_minutes"] += 5
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Duree auto-timeout -5m", style=discord.ButtonStyle.secondary, row=2)
    async def timeout_minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["actions"]["auto_timeout_minutes"] = max(5, cfg["actions"]["auto_timeout_minutes"] - 5)
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Clear par defaut +1", style=discord.ButtonStyle.secondary, row=3)
    async def clear_plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["defaults"]["clear_amount"] += 1
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Clear par defaut -1", style=discord.ButtonStyle.secondary, row=3)
    async def clear_minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["defaults"]["clear_amount"] = max(1, cfg["defaults"]["clear_amount"] - 1)
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Timeout defaut +5m", style=discord.ButtonStyle.secondary, row=4)
    async def default_timeout_plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["defaults"]["timeout_minutes"] += 5
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Timeout defaut -5m", style=discord.ButtonStyle.secondary, row=4)
    async def default_timeout_minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["defaults"]["timeout_minutes"] = max(1, cfg["defaults"]["timeout_minutes"] - 5)
        self.cog.save_mod_config()
        await self._refresh(interaction)


class NotificationsPanelView(BaseModPanelView):
    page_name = "notifications"

    @discord.ui.button(label="Toggle DM kick", style=discord.ButtonStyle.primary, row=1)
    async def toggle_dm_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["notifications"]["dm_on_kick"] = not cfg["notifications"]["dm_on_kick"]
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Toggle DM ban", style=discord.ButtonStyle.primary, row=1)
    async def toggle_dm_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_guild_config(self.guild_id)
        cfg["notifications"]["dm_on_ban"] = not cfg["notifications"]["dm_on_ban"]
        self.cog.save_mod_config()
        await self._refresh(interaction)

    @discord.ui.button(label="Reset config moderation", style=discord.ButtonStyle.danger, row=2)
    async def reset_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.mod_config[str(self.guild_id)] = self.cog._default_config()
        self.cog.save_mod_config()
        await self._refresh(interaction)


class PermissionCommandSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Default admin roles", value="__default__"),
        ]
        for cmd_name in ADMIN_COMMANDS[:24]:
            options.append(discord.SelectOption(label=cmd_name, value=cmd_name))
        super().__init__(
            placeholder="Selectionner une commande admin",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selected_command = self.values[0]
        await self.parent_view.refresh(interaction)


class PermissionRoleSelect(discord.ui.RoleSelect):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        super().__init__(
            placeholder="Selectionner un role",
            min_values=1,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values:
            self.parent_view.selected_role_id = self.values[0].id
        await self.parent_view.refresh(interaction)


class PermissionPanelView(discord.ui.View):
    def __init__(self, cog, guild_id: int, author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.author_id = author_id
        self.selected_command = "__default__"
        self.selected_role_id = None
        self.add_item(PermissionCommandSelect(self))
        self.add_item(PermissionRoleSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Seul l'auteur de la commande peut modifier ce panneau.",
                ephemeral=True,
            )
            return False
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Permission manquante: Manage Server.",
                ephemeral=True,
            )
            return False
        return True

    def _roles_for_selection(self):
        cfg = self.cog.get_permission_config(self.guild_id)
        if self.selected_command == "__default__":
            return cfg["admin_roles"]
        return cfg["command_roles"].get(self.selected_command, [])

    def build_embed(self, guild: discord.Guild):
        selected_label = "Default admin roles" if self.selected_command == "__default__" else self.selected_command
        role_ids = self._roles_for_selection()
        roles_display = "Aucun role configure"
        if role_ids:
            roles_display = "\n".join(f"<@&{rid}>" for rid in role_ids)

        chosen_role = f"<@&{self.selected_role_id}>" if self.selected_role_id else "Aucun"

        embed = discord.Embed(
            title="Panneau Permissions Admin",
            description="Configurez quels roles accedent aux commandes d'administration.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Selection commande", value=selected_label, inline=False)
        embed.add_field(name="Roles autorises", value=roles_display, inline=False)
        embed.add_field(name="Role choisi", value=chosen_role, inline=False)
        embed.set_footer(text=f"Serveur: {guild.name}")
        return embed

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Ajouter role", style=discord.ButtonStyle.success, row=2)
    async def add_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_role_id:
            await interaction.response.send_message("Selectionnez un role d'abord.", ephemeral=True)
            return
        cfg = self.cog.get_permission_config(self.guild_id)
        if self.selected_command == "__default__":
            target = cfg["admin_roles"]
        else:
            target = cfg["command_roles"].setdefault(self.selected_command, [])
        if self.selected_role_id not in target:
            target.append(self.selected_role_id)
            self.cog.save_permission_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Retirer role", style=discord.ButtonStyle.secondary, row=2)
    async def remove_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_role_id:
            await interaction.response.send_message("Selectionnez un role d'abord.", ephemeral=True)
            return
        cfg = self.cog.get_permission_config(self.guild_id)
        if self.selected_command == "__default__":
            target = cfg["admin_roles"]
        else:
            target = cfg["command_roles"].setdefault(self.selected_command, [])
        if self.selected_role_id in target:
            target.remove(self.selected_role_id)
            self.cog.save_permission_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Reset selection", style=discord.ButtonStyle.danger, row=2)
    async def reset_selection(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.get_permission_config(self.guild_id)
        if self.selected_command == "__default__":
            cfg["admin_roles"] = []
        else:
            cfg["command_roles"][self.selected_command] = []
        self.cog.save_permission_config()
        await self.refresh(interaction)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, row=3)
    async def close_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        embed = self.build_embed(interaction.guild)
        embed.set_footer(text="Panneau ferme")
        await interaction.response.edit_message(embed=embed, view=self)


class cmdmoderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()
        base_dir = os.path.abspath(os.path.dirname(__file__))
        self.mod_config_path = os.path.join(base_dir, "moderation_config.json")
        self.legacy_warn_path = os.path.join(base_dir, "warnconfig.json")
        self.warn_history_path = os.path.join(base_dir, "warn_history.json")
        self.permission_config_path = os.path.join(base_dir, "permission_config.json")
        self.mod_config = self._load_json(self.mod_config_path)
        self.warn_history = self._load_json(self.warn_history_path)
        self.permission_config = self._load_json(self.permission_config_path)
        self._migrate_legacy_warn_config()

    def _default_config(self):
        return json.loads(json.dumps(DEFAULT_MOD_CONFIG))

    def _load_json(self, path: str):
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_json(self, path: str, data: dict):
        with open(path, "w") as f:
            json.dump(data, f, indent=4)

    def save_mod_config(self):
        self._save_json(self.mod_config_path, self.mod_config)

    def save_warn_history(self):
        self._save_json(self.warn_history_path, self.warn_history)

    def save_permission_config(self):
        self._save_json(self.permission_config_path, self.permission_config)

    def get_permission_config(self, guild_id: int):
        key = str(guild_id)
        if key not in self.permission_config or not isinstance(self.permission_config[key], dict):
            self.permission_config[key] = {"admin_roles": [], "command_roles": {}}
            self.save_permission_config()
        cfg = self.permission_config[key]
        if "admin_roles" not in cfg or not isinstance(cfg["admin_roles"], list):
            cfg["admin_roles"] = []
        if "command_roles" not in cfg or not isinstance(cfg["command_roles"], dict):
            cfg["command_roles"] = {}
        self.save_permission_config()
        return cfg

    def _migrate_legacy_warn_config(self):
        if not os.path.exists(self.legacy_warn_path):
            return
        legacy = self._load_json(self.legacy_warn_path)
        changed = False
        for guild_id, warn_cfg in legacy.items():
            if not isinstance(warn_cfg, dict):
                continue
            cfg = self.get_guild_config(int(guild_id))
            for key in ("dm_user", "announce_public", "require_reason", "log_channel_id"):
                if key in warn_cfg:
                    cfg["warn"][key] = warn_cfg[key]
            changed = True
        if changed:
            self.save_mod_config()

    def get_guild_config(self, guild_id: int):
        key = str(guild_id)
        if key not in self.mod_config or not isinstance(self.mod_config[key], dict):
            self.mod_config[key] = self._default_config()
            self.save_mod_config()
            return self.mod_config[key]

        cfg = self.mod_config[key]
        default_cfg = self._default_config()
        for section_name, section_defaults in default_cfg.items():
            if section_name not in cfg or not isinstance(cfg[section_name], dict):
                cfg[section_name] = section_defaults
            else:
                for setting_key, setting_default in section_defaults.items():
                    if setting_key not in cfg[section_name]:
                        cfg[section_name][setting_key] = setting_default
        self.save_mod_config()
        return cfg

    def get_warn_count(self, guild_id: int, user_id: int):
        return int(self.warn_history.get(str(guild_id), {}).get(str(user_id), 0))

    def increment_warn(self, guild_id: int, user_id: int):
        guild_history = self.warn_history.setdefault(str(guild_id), {})
        guild_history[str(user_id)] = int(guild_history.get(str(user_id), 0)) + 1
        self.save_warn_history()
        return guild_history[str(user_id)]

    def clear_warns(self, guild_id: int, user_id: int):
        guild_history = self.warn_history.setdefault(str(guild_id), {})
        guild_history[str(user_id)] = 0
        self.save_warn_history()

    def build_mod_panel_embed(self, guild: discord.Guild, page: str):
        cfg = self.get_guild_config(guild.id)
        embed = discord.Embed(title="Panneau Moderation", color=discord.Color.orange())

        if page == "warn":
            warn_cfg = cfg["warn"]
            log_channel_id = warn_cfg.get("log_channel_id")
            log_channel = guild.get_channel(log_channel_id) if log_channel_id else None
            log_channel_label = f"#{log_channel.name}" if log_channel else "Non defini"
            embed.description = "Section Warn: configuration des avertissements."
            embed.add_field(name="Raison obligatoire", value="Active" if warn_cfg["require_reason"] else "Desactive", inline=True)
            embed.add_field(name="DM warn", value="Active" if warn_cfg["dm_user"] else "Desactive", inline=True)
            embed.add_field(name="Annonce publique", value="Active" if warn_cfg["announce_public"] else "Desactive", inline=True)
            embed.add_field(name="Canal logs", value=log_channel_label, inline=False)
        elif page == "actions":
            actions_cfg = cfg["actions"]
            defaults_cfg = cfg["defaults"]
            embed.description = "Section Actions: automatisations et valeurs par defaut."
            embed.add_field(name="Auto-timeout", value="Active" if actions_cfg["auto_timeout_enabled"] else "Desactive", inline=True)
            embed.add_field(name="Seuil warns", value=str(actions_cfg["auto_timeout_after_warns"]), inline=True)
            embed.add_field(name="Duree auto-timeout", value=f"{actions_cfg['auto_timeout_minutes']} min", inline=True)
            embed.add_field(name="Clear par defaut", value=str(defaults_cfg["clear_amount"]), inline=True)
            embed.add_field(name="Timeout par defaut", value=f"{defaults_cfg['timeout_minutes']} min", inline=True)
        else:
            notif_cfg = cfg["notifications"]
            embed.description = "Section Notifications: messages envoyes aux membres sanctionnes."
            embed.add_field(name="DM sur kick", value="Active" if notif_cfg["dm_on_kick"] else "Desactive", inline=True)
            embed.add_field(name="DM sur ban", value="Active" if notif_cfg["dm_on_ban"] else "Desactive", inline=True)

        embed.set_footer(text=f"Serveur: {guild.name} • Page: {page}")
        return embed

    def build_mod_panel_view(self, page: str, guild_id: int, author_id: int):
        if page == "actions":
            return ActionsPanelView(self, guild_id, author_id)
        if page == "notifications":
            return NotificationsPanelView(self, guild_id, author_id)
        return WarnPanelView(self, guild_id, author_id)

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason=""):
        cfg = self.get_guild_config(ctx.guild.id)
        warn_cfg = cfg["warn"]
        actions_cfg = cfg["actions"]

        reason = reason.strip() if reason else ""
        if warn_cfg["require_reason"] and not reason:
            await ctx.send("La raison est obligatoire. Syntaxe: `,warn <membre> <raison>`")
            return

        final_reason = reason if reason else "Aucune raison fournie"
        warn_count = self.increment_warn(ctx.guild.id, member.id)

        mod_embed = discord.Embed(title="Avertissement", color=discord.Color.red())
        mod_embed.add_field(name="Membre", value=member.mention, inline=True)
        mod_embed.add_field(name="Moderateur", value=ctx.author.mention, inline=True)
        mod_embed.add_field(name="Raison", value=final_reason, inline=False)
        mod_embed.add_field(name="Total warns", value=str(warn_count), inline=True)

        dm_failed = False
        if warn_cfg["dm_user"]:
            dm_embed = discord.Embed(
                title=f"Avertissement - {ctx.guild.name}",
                description="Vous avez recu un avertissement.",
                color=discord.Color.red(),
            )
            dm_embed.add_field(name="Raison", value=final_reason, inline=False)
            dm_embed.add_field(name="Total warns", value=str(warn_count), inline=True)
            try:
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                dm_failed = True

        if warn_cfg["announce_public"]:
            await ctx.send(embed=mod_embed)
        else:
            await ctx.send(f"{member.mention} a recu un avertissement.")

        log_channel_id = warn_cfg.get("log_channel_id")
        if log_channel_id:
            log_channel = ctx.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=mod_embed)

        if (
            actions_cfg["auto_timeout_enabled"]
            and warn_count >= actions_cfg["auto_timeout_after_warns"]
        ):
            duration = discord.utils.utcnow() + timedelta(minutes=actions_cfg["auto_timeout_minutes"])
            try:
                await member.edit(
                    timed_out_until=duration,
                    reason=f"Auto-timeout apres {warn_count} warns",
                )
                await ctx.send(
                    f"Auto-timeout applique a {member.mention} pendant {actions_cfg['auto_timeout_minutes']} minutes."
                )
            except (discord.Forbidden, discord.HTTPException):
                await ctx.send("Auto-timeout impossible: permissions insuffisantes.")

        if dm_failed:
            await ctx.send("Impossible d'envoyer le DM a cet utilisateur.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def modpanel(self, ctx):
        embed = self.build_mod_panel_embed(ctx.guild, "warn")
        view = self.build_mod_panel_view("warn", ctx.guild.id, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def warnconfig(self, ctx):
        await self.modpanel(ctx)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def permpanel(self, ctx):
        self.get_permission_config(ctx.guild.id)
        view = PermissionPanelView(self, ctx.guild.id, ctx.author.id)
        embed = view.build_embed(ctx.guild)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def warns(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        count = self.get_warn_count(ctx.guild.id, target.id)
        await ctx.send(f"{target.mention} a {count} warn(s).")

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def clearwarns(self, ctx, member: discord.Member):
        self.clear_warns(ctx.guild.id, member.id)
        await ctx.send(f"Les warns de {member.mention} ont ete reinitialises.")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="Aucune raison fournie"):
        cfg = self.get_guild_config(ctx.guild.id)
        if cfg["notifications"]["dm_on_ban"]:
            try:
                await member.send(f"Vous avez ete banni du serveur {ctx.guild.name} pour: {reason}")
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.guild.ban(member, reason=reason)
        await ctx.send(f"{member.mention} a ete banni.")

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="Aucune raison fournie"):
        cfg = self.get_guild_config(ctx.guild.id)
        if cfg["notifications"]["dm_on_kick"]:
            try:
                invite = await ctx.channel.create_invite(max_age=86400, max_uses=1)
                await member.send(f"Vous avez ete kick du serveur {ctx.guild.name} pour: {reason}. Invitation: {invite}")
            except (discord.Forbidden, discord.HTTPException):
                pass
        await member.kick(reason=reason)
        await ctx.send(f"{member.mention} a ete kick pour {reason}.")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = None):
        cfg = self.get_guild_config(ctx.guild.id)
        if amount is None:
            amount = int(cfg["defaults"]["clear_amount"])
        if amount <= 0:
            await ctx.send("Le nombre de messages a supprimer doit etre superieur a 0.")
            return
        await ctx.channel.purge(limit=amount + 1)
        embed = discord.Embed(title=f"{amount} messages ont ete effaces.", color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason="Aucune raison fournie"):
        user = await self.bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f"{user} a ete debanni.")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, minutes: int = None, *, reason="Aucune raison fournie"):
        cfg = self.get_guild_config(ctx.guild.id)
        if minutes is None:
            minutes = int(cfg["defaults"]["timeout_minutes"])
        if minutes <= 0:
            await ctx.send("La duree doit etre superieure a 0 minute.")
            return
        duration = discord.utils.utcnow() + timedelta(minutes=minutes)
        await member.edit(timed_out_until=duration, reason=reason)
        await ctx.send(f"{member.mention} est timeout pour {minutes} minute(s).")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member, *, reason="Aucune raison fournie"):
        await member.edit(timed_out_until=None, reason=reason)
        await ctx.send(f"Timeout retire pour {member.mention}.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int):
        if seconds < 0:
            await ctx.send("Le slowmode ne peut pas etre negatif.")
            return
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f"Slowmode defini a {seconds}s pour ce salon.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("Salon verrouille.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("Salon deverrouille.")


def setup(bot):
    bot.add_cog(cmdmoderation(bot))