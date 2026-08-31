"""Auto-moderation intelligente par IA.

Utilise g4f pour analyser les messages et detecter le contenu toxique.
Envoie un avertissement automatique et/ou supprime le message selon la config.
"""

import json
import time

import discord
from discord.ext import commands

from cogs.i18n import t

DEFAULT_AI_MOD_CONFIG = {
    "enabled": False,
    "action": "warn",
    "log_channel_id": None,
    "threshold": 0.7,
    "ignored_roles": [],
    "cooldown_seconds": 10,
}


class cmdaimoderation(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._cfg_initialized = set()
        self._last_check = {}

    def get_config(self, guild_id: int) -> dict:
        if guild_id not in self._cfg_initialized:
            self._cfg_initialized.add(guild_id)
            self.db.execute(
                "INSERT OR IGNORE INTO ai_moderation_config "
                "(guild_id, enabled, action, log_channel_id, threshold, cooldown_seconds) "
                "VALUES (?, 0, 'warn', NULL, 0.7, 10)",
                (guild_id,),
            )
        row = self.db.fetchone(
            "SELECT enabled, action, log_channel_id, threshold, cooldown_seconds "
            "FROM ai_moderation_config WHERE guild_id = ?",
            (guild_id,),
        )
        return {
            "enabled": bool(row["enabled"]),
            "action": row["action"],
            "log_channel_id": row["log_channel_id"],
            "threshold": row["threshold"],
            "cooldown_seconds": row["cooldown_seconds"],
        }

    def save_config(self, guild_id: int, **fields):
        self.get_config(guild_id)
        assignments = []
        values = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(int(value) if isinstance(value, bool) else value)
        values.append(guild_id)
        self.db.execute(
            f"UPDATE ai_moderation_config SET {', '.join(assignments)} WHERE guild_id = ?",
            values,
        )

    def add_ignored_role(self, guild_id: int, role_id: int):
        self.db.execute(
            "INSERT OR IGNORE INTO ai_moderation_ignored_roles (guild_id, role_id) VALUES (?, ?)",
            (guild_id, role_id),
        )

    def remove_ignored_role(self, guild_id: int, role_id: int):
        self.db.execute(
            "DELETE FROM ai_moderation_ignored_roles WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id),
        )

    def get_ignored_roles(self, guild_id: int) -> list:
        rows = self.db.fetchall(
            "SELECT role_id FROM ai_moderation_ignored_roles WHERE guild_id = ?", (guild_id,)
        )
        return [row["role_id"] for row in rows]

    async def _check_message(self, message: discord.Message):
        if not message.guild:
            return
        if message.author.bot:
            return

        cfg = self.get_config(message.guild.id)
        if not cfg["enabled"]:
            return

        if message.author.guild_permissions.administrator:
            return

        ignored_roles = self.get_ignored_roles(message.guild.id)
        member_role_ids = {role.id for role in message.author.roles}
        if any(rid in member_role_ids for rid in ignored_roles):
            return

        now = time.time()
        last = self._last_check.get((message.guild.id, message.author.id), 0)
        if now - last < cfg["cooldown_seconds"]:
            return
        self._last_check[(message.guild.id, message.author.id)] = now

        try:
            from g4f.client import Client
            client = Client()

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es un moderateur de serveur Discord. Analyse le message suivant "
                            "et determine s'il contient du contenu toxique (harcèlement, insultes, "
                            "menaces, spam, contenu NSFW, discrimination, etc.). "
                            "Reponds UNIQUEMENT avec un JSON: "
                            '{"toxic": true/false, "score": 0.0-1.0, "reason": "explication courte"}'
                        ),
                    },
                    {"role": "user", "content": message.content},
                ],
                timeout=10,
            )

            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(raw)

            if result.get("toxic") and result.get("score", 0) >= cfg["threshold"]:
                await self._enforce(message, cfg, result)

        except json.JSONDecodeError:
            pass
        except Exception:
            pass

    async def _enforce(self, message: discord.Message, cfg: dict, result: dict):
        action = cfg["action"]
        reason = f"[AI-Mod] {result.get('reason', 'Contenu toxique detecte')} (score: {result.get('score', '?')})"

        if action in ("delete", "warn_delete"):
            try:
                await message.delete()
            except discord.errors.NotFound:
                pass

        if action in ("warn", "warn_delete"):
            try:
                await message.author.send(
                    f"⚠️ Vous avez recu un avertissement sur **{message.guild.name}**.\n"
                    f"Raison: {result.get('reason', 'Contenu toxique')}"
                )
            except discord.errors.Forbidden:
                pass

            mod_cog = self.bot.get_cog("cmdmoderation")
            if mod_cog:
                mod_cog.increment_warns(message.guild.id, message.author.id)

        log_channel = self.bot.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None
        if log_channel:
            embed = discord.Embed(
                title="🛡️ AI-Moderation",
                description=f"Message de {message.author.mention} detecte comme toxique.",
                color=discord.Color.red(),
            )
            embed.add_field(name="Score", value=str(result.get("score", "?")), inline=True)
            embed.add_field(name="Action", value=action, inline=True)
            embed.add_field(name="Contenu", value=message.content[:500], inline=False)
            embed.add_field(name="Raison", value=result.get("reason", "—"), inline=False)
            try:
                await log_channel.send(embed=embed)
            except discord.errors.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self._check_message(message)

    @commands.command()
    async def aimod(self, ctx, state: str = None):
        """Active/desactive l'AI-moderation (on/off) ou affiche la config."""
        if state is None:
            await ctx.invoke(self.bot.get_command("aimodconfig"))
            return
        state = state.lower()
        if state not in ("on", "off"):
            await ctx.invoke(self.bot.get_command("aimodconfig"))
            return
        self.save_config(ctx.guild.id, enabled=(state == "on"))
        if state == "on":
            await ctx.send("✅ AI-Moderation activee.")
        else:
            await ctx.send("❌ AI-Moderation desactivee.")

    @commands.command()
    async def aimodconfig(self, ctx):
        """Affiche la configuration de l'AI-moderation."""
        cfg = self.get_config(ctx.guild.id)
        ignored = self.get_ignored_roles(ctx.guild.id)
        embed = discord.Embed(
            title="Configuration AI-Moderation",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Active", value="✅" if cfg["enabled"] else "❌", inline=True)
        embed.add_field(name="Action", value=cfg["action"], inline=True)
        embed.add_field(name="Seuil", value=str(cfg["threshold"]), inline=True)
        embed.add_field(name="Cooldown", value=f"{cfg['cooldown_seconds']}s", inline=True)
        log_ch = f"<#{cfg['log_channel_id']}>" if cfg["log_channel_id"] else "—"
        embed.add_field(name="Canal logs", value=log_ch, inline=True)
        if ignored:
            role_list = ", ".join(f"<@&{rid}>" for rid in ignored)
            embed.add_field(name="Roles ignores", value=role_list, inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def aimodaction(self, ctx, action: str = None):
        """Change l'action de l'AI-mod (warn/delete/warn_delete)."""
        if action is None or action not in ("warn", "delete", "warn_delete"):
            await ctx.send("Usage: `,aimodaction warn|delete|warn_delete`")
            return
        self.save_config(ctx.guild.id, action=action)
        await ctx.send(f"✅ Action AI-mod definie sur `{action}`.")

    @commands.command()
    async def aimodthreshold(self, ctx, threshold: float = None):
        """Change le seuil de detection (0.0-1.0)."""
        if threshold is None or not (0.0 <= threshold <= 1.0):
            await ctx.send("Usage: `,aimodthreshold 0.7` (entre 0.0 et 1.0)")
            return
        self.save_config(ctx.guild.id, threshold=threshold)
        await ctx.send(f"✅ Seuil AI-mod defini sur `{threshold}`.")

    @commands.command()
    async def aimodignore(self, ctx, role: discord.Role = None):
        """Ajoute/retire un role de la liste d'ignorance de l'AI-mod."""
        if role is None:
            await ctx.send("Usage: `,aimodignore @role`")
            return
        ignored = self.get_ignored_roles(ctx.guild.id)
        if role.id in ignored:
            self.remove_ignored_role(ctx.guild.id, role.id)
            await ctx.send(f"❌ Le role {role.mention} n'est plus ignore par l'AI-mod.")
        else:
            self.add_ignored_role(ctx.guild.id, role.id)
            await ctx.send(f"✅ Le role {role.mention} est ignore par l'AI-mod.")

    @commands.command()
    async def aimodlog(self, ctx, channel: discord.TextChannel = None):
        """Definit le canal de logs pour l'AI-moderation."""
        if channel is None:
            self.save_config(ctx.guild.id, log_channel_id=None)
            await ctx.send("Logs AI-mod desactivees.")
        else:
            self.save_config(ctx.guild.id, log_channel_id=channel.id)
            await ctx.send(f"✅ Canal de logs AI-mod defini sur {channel.mention}.")


def setup(bot, db):
    bot.add_cog(cmdaimoderation(bot, db))
