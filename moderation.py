import json
import os
from datetime import timedelta

import discord
from discord.ext import commands


DEFAULT_WARN_SETTINGS = {
    "dm_user": True,
    "announce_public": True,
    "require_reason": True,
    "log_channel_id": None,
}


class WarnConfigView(discord.ui.View):
    def __init__(self, cog, guild_id: int, author_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Seul l'auteur de la commande peut modifier cette configuration.",
                ephemeral=True,
            )
            return False
        return True

    def _refresh_embed(self, guild: discord.Guild) -> discord.Embed:
        settings = self.cog.get_warn_settings(guild.id)
        return self.cog.build_warn_config_embed(guild, settings)

    async def _update_panel(self, interaction: discord.Interaction):
        embed = self._refresh_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle raison obligatoire", style=discord.ButtonStyle.primary)
    async def toggle_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_warn_settings(self.guild_id)
        settings["require_reason"] = not settings["require_reason"]
        self.cog.save_warn_settings()
        await self._update_panel(interaction)

    @discord.ui.button(label="Toggle DM utilisateur", style=discord.ButtonStyle.primary)
    async def toggle_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_warn_settings(self.guild_id)
        settings["dm_user"] = not settings["dm_user"]
        self.cog.save_warn_settings()
        await self._update_panel(interaction)

    @discord.ui.button(label="Toggle annonce publique", style=discord.ButtonStyle.primary)
    async def toggle_public(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_warn_settings(self.guild_id)
        settings["announce_public"] = not settings["announce_public"]
        self.cog.save_warn_settings()
        await self._update_panel(interaction)

    @discord.ui.button(label="Canal logs = ici", style=discord.ButtonStyle.secondary)
    async def set_log_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_warn_settings(self.guild_id)
        settings["log_channel_id"] = interaction.channel_id
        self.cog.save_warn_settings()
        await self._update_panel(interaction)

    @discord.ui.button(label="Reset defaut", style=discord.ButtonStyle.secondary)
    async def reset_defaults(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.warn_settings[str(self.guild_id)] = dict(DEFAULT_WARN_SETTINGS)
        self.cog.save_warn_settings()
        await self._update_panel(interaction)

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger)
    async def close_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        embed = self._refresh_embed(interaction.guild)
        embed.set_footer(text="Panneau ferme")
        await interaction.response.edit_message(embed=embed, view=self)

class cmdmoderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()
        self.warn_config_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'warnconfig.json')
        self.warn_settings = self.load_warn_settings()

    def load_warn_settings(self):
        if not os.path.exists(self.warn_config_path):
            return {}
        try:
            with open(self.warn_config_path, 'r') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def save_warn_settings(self):
        with open(self.warn_config_path, 'w') as f:
            json.dump(self.warn_settings, f, indent=4)

    def get_warn_settings(self, guild_id: int):
        key = str(guild_id)
        if key not in self.warn_settings or not isinstance(self.warn_settings[key], dict):
            self.warn_settings[key] = dict(DEFAULT_WARN_SETTINGS)
            self.save_warn_settings()
        else:
            for setting_key, default_value in DEFAULT_WARN_SETTINGS.items():
                if setting_key not in self.warn_settings[key]:
                    self.warn_settings[key][setting_key] = default_value
                    self.save_warn_settings()
        return self.warn_settings[key]

    def build_warn_config_embed(self, guild: discord.Guild, settings: dict):
        log_channel_id = settings.get("log_channel_id")
        log_channel = guild.get_channel(log_channel_id) if log_channel_id else None
        log_channel_label = f"#{log_channel.name}" if log_channel else "Non defini"

        embed = discord.Embed(
            title="Configuration des warns",
            description="Utilisez les boutons ci-dessous pour activer/desactiver les options.",
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="Raison obligatoire",
            value="Active" if settings.get("require_reason") else "Desactive",
            inline=True,
        )
        embed.add_field(
            name="DM utilisateur",
            value="Active" if settings.get("dm_user") else "Desactive",
            inline=True,
        )
        embed.add_field(
            name="Annonce publique",
            value="Active" if settings.get("announce_public") else "Desactive",
            inline=True,
        )
        embed.add_field(name="Canal de logs", value=log_channel_label, inline=False)
        embed.set_footer(text="Commande: ,warnconfig")
        return embed

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason=""):
        settings = self.get_warn_settings(ctx.guild.id)
        reason = reason.strip() if reason else ""

        if settings.get("require_reason") and not reason:
            await ctx.send("La raison est obligatoire. Syntaxe: `,warn <membre> <raison>`")
            return

        final_reason = reason if reason else "Aucune raison fournie"

        mod_embed = discord.Embed(title="Avertissement", color=discord.Color.red())
        mod_embed.add_field(name="Membre", value=member.mention, inline=True)
        mod_embed.add_field(name="Moderateur", value=ctx.author.mention, inline=True)
        mod_embed.add_field(name="Raison", value=final_reason, inline=False)

        dm_failed = False
        if settings.get("dm_user"):
            dm_embed = discord.Embed(
                title=f"Avertissement - {ctx.guild.name}",
                description=f"Vous avez ete averti.",
                color=discord.Color.red(),
            )
            dm_embed.add_field(name="Raison", value=final_reason, inline=False)
            try:
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                dm_failed = True

        if settings.get("announce_public"):
            await ctx.send(embed=mod_embed)
        else:
            await ctx.send(f"{member.mention} a recu un avertissement.")

        log_channel_id = settings.get("log_channel_id")
        if log_channel_id:
            log_channel = ctx.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=mod_embed)

        if dm_failed:
            await ctx.send("Impossible d'envoyer le DM a cet utilisateur.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def warnconfig(self, ctx):
        settings = self.get_warn_settings(ctx.guild.id)
        embed = self.build_warn_config_embed(ctx.guild, settings)
        view = WarnConfigView(self, ctx.guild.id, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason):
        await member.send(f'vous avez été banni du serveur {ctx.guild.name} pour {reason}')    
        await ctx.guild.ban(member, reason = reason)
        await ctx.send(f'{member.mention} a été banni')

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="Aucune raison fournie"):
        invite = await ctx.channel.create_invite()
        await member.send(f'vous avez été kick du serveur {invite} pour {reason}')    
        await member.kick(reason=reason)
        await ctx.send(f'{member.mention} a été kick pour {reason}')

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int):
        if amount <= 0:
            await ctx.send("Le nombre de messages a supprimer doit etre superieur a 0.")
            return
        await ctx.channel.purge(limit=amount+1)
        embed = discord.Embed(title=f"{amount} messages ont été effacés.", color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason="Aucune raison fournie"):
        user = await self.bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f"✅ {user} a ete debanni.")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, minutes: int, *, reason="Aucune raison fournie"):
        if minutes <= 0:
            await ctx.send("La duree doit etre superieure a 0 minute.")
            return
        duration = discord.utils.utcnow() + timedelta(minutes=minutes)
        await member.edit(timed_out_until=duration, reason=reason)
        await ctx.send(f"⏱️ {member.mention} est timeout pour {minutes} minute(s).")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member, *, reason="Aucune raison fournie"):
        await member.edit(timed_out_until=None, reason=reason)
        await ctx.send(f"✅ Timeout retire pour {member.mention}.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int):
        if seconds < 0:
            await ctx.send("Le slowmode ne peut pas etre negatif.")
            return
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f"🐢 Slowmode defini a {seconds}s pour ce salon.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔒 Salon verrouille.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔓 Salon deverrouille.")

def setup(bot):
    bot.add_cog(cmdmoderation(bot))