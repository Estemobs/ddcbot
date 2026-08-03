"""Pont Discord <-> Minecraft (intègre NerdMC).

Permet de relayer en temps réel le tchat Minecraft vers un canal Discord et
inversement. Configuration entièrement par serveur (table minecraft_config).

Deux méthodes d'envoi vers Minecraft :
  - RCON (recommandé) : fonctionne avec n'importe quel serveur (Vanilla, moddé,
    Spigot/Paper via plugin, etc.) via le protocole RCON asynchrone intégré.
  - tmux : envoi via `tmux send-keys` sur la session du serveur (fallback).

La lecture du tchat Minecraft -> Discord se fait en suivant le fichier
`latest.log` avec `tail -F` (gère la rotation des logs) via un sous-processus
asynchrone, un lecteur par serveur, démarré/arrêté par `,mcenable`/`,mcdisable`.
"""

from __future__ import annotations

import asyncio
import re
import struct

import discord
from discord.ext import commands

from cogs.i18n import t

# ---------------------------------------------------------------------------
# RCON (protocole Source / Minecraft)
# ---------------------------------------------------------------------------

_RCON_PACKET_TYPE_AUTH = 3
_RCON_PACKET_TYPE_EXECCOMMAND = 2
_RCON_PACKET_TYPE_RESPONSE = 0


class RCONError(Exception):
    """Erreur de connexion / authentification RCON."""


class RCONClient:
    """Client RCON asynchrone minimal (aucune dépendance externe)."""

    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id = 0

    async def connect(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise RCONError(f"connexion impossible à {self.host}:{self.port}: {exc}") from exc

        self._request_id += 1
        await self._send_packet(self._request_id, _RCON_PACKET_TYPE_AUTH, self.password)
        response_id, packet_type, _payload = await self._read_packet()

        if packet_type != _RCON_PACKET_TYPE_AUTH or response_id != self._request_id:
            await self.close()
            raise RCONError("authentification RCON refusée")

    async def _send_packet(self, request_id: int, packet_type: int, payload: str) -> None:
        if self._writer is None:
            raise RCONError("RCON non connecté")
        body = payload.encode("utf-8") + b"\x00\x00"
        packet = struct.pack("<ii", request_id, packet_type) + body
        self._writer.write(struct.pack("<i", len(packet)) + packet)
        await self._writer.drain()

    async def _read_packet(self) -> tuple[int, int, str]:
        if self._reader is None:
            raise RCONError("RCON non connecté")
        header = await asyncio.wait_for(self._reader.readexactly(4), timeout=self.timeout)
        length = struct.unpack("<i", header)[0]
        body = await asyncio.wait_for(self._reader.readexactly(length), timeout=self.timeout)
        request_id, packet_type = struct.unpack("<ii", body[:8])
        payload = body[8:-2].decode("utf-8", errors="replace")
        return request_id, packet_type, payload

    async def command(self, command: str) -> str:
        self._request_id += 1
        await self._send_packet(self._request_id, _RCON_PACKET_TYPE_EXECCOMMAND, command)

        output = ""
        while True:
            request_id, packet_type, payload = await self._read_packet()
            if packet_type == _RCON_PACKET_TYPE_RESPONSE and request_id == self._request_id:
                output = payload
                break
            if packet_type == _RCON_PACKET_TYPE_AUTH and request_id == -1:
                raise RCONError("session RCON fermée par le serveur")
        return output

    async def close(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None


def sanitize_minecraft_input(text: str) -> str:
    """Nettoie une entrée Discord avant envoi vers Minecraft.

    Retire les retours à la ligne, caractères de contrôle et les mentions
    Discord qui pourraient casser la commande `say` (injection RCON/console).
    """
    # Mentions Discord -> pseudo lisible
    text = re.sub(r"<@!?(\d+)>", lambda m: f"@<{m.group(1)}>", text)
    text = re.sub(r"<#(\d+)>", lambda m: f"#<{m.group(1)}>", text)
    text = re.sub(r"<a?:\w+:\d+>", "", text)
    # Caractères dangereux / contrôle, puis espaces multiples
    text = text.replace("\n", " ").replace("\r", " ").replace("\x00", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:500]


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(r"<([^>]+)>\s*(.+)$")


class cmdminecraft(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._log_tasks: dict[int, asyncio.Task] = {}
        self._rcon_clients: dict[int, RCONClient] = {}

    # --- configuration ---

    def get_config(self, guild_id: int) -> dict:
        row = self.db.fetchone(
            "SELECT channel_id, log_path, method, tmux_session, use_sudo, "
            "rcon_host, rcon_port, rcon_password, enabled "
            "FROM minecraft_config WHERE guild_id = ?",
            (guild_id,),
        )
        if row is None:
            return {}
        return {
            "channel_id": row["channel_id"],
            "log_path": row["log_path"],
            "method": row["method"],
            "tmux_session": row["tmux_session"],
            "use_sudo": bool(row["use_sudo"]),
            "rcon_host": row["rcon_host"],
            "rcon_port": row["rcon_port"],
            "rcon_password": row["rcon_password"],
            "enabled": bool(row["enabled"]),
        }

    def save_config(self, guild_id: int, **fields):
        existing = self.get_config(guild_id)
        merged = {**existing, **fields}
        merged.setdefault("method", "tmux")
        merged.setdefault("use_sudo", False)
        merged.setdefault("enabled", False)
        self.db.execute(
            "INSERT INTO minecraft_config "
            "(guild_id, channel_id, log_path, method, tmux_session, use_sudo, "
            " rcon_host, rcon_port, rcon_password, enabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET "
            " channel_id=excluded.channel_id, log_path=excluded.log_path, "
            " method=excluded.method, tmux_session=excluded.tmux_session, "
            " use_sudo=excluded.use_sudo, rcon_host=excluded.rcon_host, "
            " rcon_port=excluded.rcon_port, rcon_password=excluded.rcon_password, "
            " enabled=excluded.enabled",
            (
                guild_id,
                merged.get("channel_id"),
                merged.get("log_path"),
                merged.get("method"),
                merged.get("tmux_session"),
                int(bool(merged.get("use_sudo"))),
                merged.get("rcon_host"),
                merged.get("rcon_port"),
                merged.get("rcon_password"),
                int(bool(merged.get("enabled"))),
            ),
        )

    # --- envoi vers Minecraft ---

    async def _get_rcon(self, guild_id: int) -> RCONClient:
        cfg = self.get_config(guild_id)
        host = cfg.get("rcon_host")
        port = cfg.get("rcon_port") or 25575
        password = cfg.get("rcon_password") or ""
        if not host or not password:
            raise RCONError("RCON non configuré (host/mot de passe manquants)")

        client = self._rcon_clients.get(guild_id)
        if client is not None:
            return client

        client = RCONClient(host, int(port), password)
        await client.connect()
        self._rcon_clients[guild_id] = client
        return client

    async def _send_via_tmux(self, guild_id: int, text: str) -> None:
        cfg = self.get_config(guild_id)
        session = cfg.get("tmux_session") or "minecraft"
        base = ["sudo", "tmux"] if cfg.get("use_sudo") else ["tmux"]
        command = ["send-keys", "-t", session, f"say {text}", "C-j"]
        proc = await asyncio.create_subprocess_exec(
            *base, *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    async def send_to_minecraft(self, guild_id: int, text: str) -> str:
        """Envoie *text* vers Minecraft, via RCON ou tmux selon la config."""
        cfg = self.get_config(guild_id)
        method = cfg.get("method") or "tmux"

        if method == "rcon":
            try:
                client = await self._get_rcon(guild_id)
                await client.command(f"say {text}")
                return "rcon"
            except RCONError as exc:
                raise RuntimeError(str(exc)) from exc

        try:
            await self._send_via_tmux(guild_id, text)
            return "tmux"
        except Exception as exc:
            raise RuntimeError(f"envoi tmux échoué: {exc}") from exc

    # --- lecture du log Minecraft ---

    async def _log_reader(self, guild_id: int) -> None:
        """Suit latest.log et relaie les messages `<joueur> message` vers Discord."""
        cfg = self.get_config(guild_id)
        log_path = cfg.get("log_path")
        channel_id = cfg.get("channel_id")
        if not log_path or not channel_id:
            return

        base = ["sudo", "tail"] if cfg.get("use_sudo") else ["tail"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *base, "-F", "-n", "0", log_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return

        try:
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                match = _LOG_LINE_RE.search(text)
                if not match:
                    continue
                username, message = match.groups()
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    continue
                await channel.send(f"**{username}** : {message}")
        except asyncio.CancelledError:
            pass
        finally:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass

    def _start_reader(self, guild_id: int) -> None:
        if guild_id in self._log_tasks and not self._log_tasks[guild_id].done():
            return
        task = asyncio.create_task(self._log_reader(guild_id))
        self._log_tasks[guild_id] = task

    def _stop_reader(self, guild_id: int) -> None:
        task = self._log_tasks.pop(guild_id, None)
        if task is not None and not task.done():
            task.cancel()
        client = self._rcon_clients.pop(guild_id, None)
        if client is not None:
            asyncio.get_event_loop().create_task(client.close())

    def cog_unload(self) -> None:
        for guild_id in list(self._log_tasks):
            self._stop_reader(guild_id)

    # --- commandes ---

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def mcenable(self, ctx):
        """Active le pont Discord <-> Minecraft sur ce serveur."""
        cfg = self.get_config(ctx.guild.id)
        if not cfg.get("log_path"):
            await ctx.send(t(self.db, "minecraft_need_log", ctx.guild.id, ctx.author.id))
            return
        if not cfg.get("channel_id"):
            cfg = {**cfg, "channel_id": ctx.channel.id}
            self.save_config(ctx.guild.id, channel_id=ctx.channel.id)
        self.save_config(ctx.guild.id, enabled=True)
        self._start_reader(ctx.guild.id)
        await ctx.send(t(self.db, "minecraft_enabled", ctx.guild.id, ctx.author.id))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def mcdisable(self, ctx):
        """Désactive le pont Discord <-> Minecraft sur ce serveur."""
        self.save_config(ctx.guild.id, enabled=False)
        self._stop_reader(ctx.guild.id)
        await ctx.send(t(self.db, "minecraft_disabled", ctx.guild.id, ctx.author.id))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def mcconfig(self, ctx, *options: str):
        """Configure le pont Minecraft (voir `,mcconfig show` pour la syntaxe)."""
        args = [o.lower() for o in options]
        if not args or args[0] == "show":
            cfg = self.get_config(ctx.guild.id)
            embed = discord.Embed(
                title=t(self.db, "minecraft_config_title", ctx.guild.id, ctx.author.id),
                color=discord.Color.blue(),
            )
            embed.add_field(name="Enabled", value="✅" if cfg.get("enabled") else "❌", inline=True)
            embed.add_field(name="Méthode", value=cfg.get("method") or "tmux", inline=True)
            embed.add_field(name="Log", value=cfg.get("log_path") or "—", inline=False)
            if cfg.get("channel_id"):
                embed.add_field(name="Canal", value=f"<#{cfg['channel_id']}>", inline=True)
            else:
                embed.add_field(name="Canal", value="—", inline=True)
            embed.add_field(name="Session tmux", value=cfg.get("tmux_session") or "minecraft", inline=True)
            if cfg.get("rcon_host"):
                embed.add_field(
                    name="RCON",
                    value=f"{cfg['rcon_host']}:{cfg.get('rcon_port')}",
                    inline=True,
                )
            else:
                embed.add_field(name="RCON", value="—", inline=True)
            embed.add_field(name="sudo", value="✅" if cfg.get("use_sudo") else "❌", inline=True)
            await ctx.send(embed=embed)
            return

        action = args[0]
        if action == "log" and len(args) >= 2:
            self.save_config(ctx.guild.id, log_path=args[1])
            await ctx.send(t(self.db, "minecraft_set_log", ctx.guild.id, ctx.author.id, path=args[1]))
        elif action == "channel":
            self.save_config(ctx.guild.id, channel_id=ctx.channel.id)
            await ctx.send(t(self.db, "minecraft_set_channel", ctx.guild.id, ctx.author.id))
        elif action == "method" and len(args) >= 2 and args[1] in ("rcon", "tmux"):
            self.save_config(ctx.guild.id, method=args[1])
            await ctx.send(t(self.db, "minecraft_set_method", ctx.guild.id, ctx.author.id, method=args[1]))
        elif action == "rcon" and len(args) >= 4:
            self.save_config(ctx.guild.id, rcon_host=args[1], rcon_port=int(args[2]), rcon_password=args[3])
            await ctx.send(t(self.db, "minecraft_set_rcon", ctx.guild.id, ctx.author.id, host=args[1]))
        elif action == "tmux" and len(args) >= 2:
            self.save_config(ctx.guild.id, tmux_session=args[1])
            await ctx.send(t(self.db, "minecraft_set_tmux", ctx.guild.id, ctx.author.id, session=args[1]))
        elif action == "sudo" and len(args) >= 2 and args[1] in ("on", "off"):
            self.save_config(ctx.guild.id, use_sudo=(args[1] == "on"))
            await ctx.send(t(self.db, "minecraft_set_sudo", ctx.guild.id, ctx.author.id, state=args[1]))
        else:
            await ctx.send(t(self.db, "minecraft_config_usage", ctx.guild.id, ctx.author.id))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def mcsay(self, ctx, *, message: str):
        """Envoie un message depuis Discord vers Minecraft (en tant que serveur)."""
        text = sanitize_minecraft_input(message)
        if not text:
            await ctx.send(t(self.db, "minecraft_empty", ctx.guild.id, ctx.author.id))
            return
        try:
            method = await self.send_to_minecraft(ctx.guild.id, text)
        except RuntimeError as exc:
            await ctx.send(t(self.db, "minecraft_send_error", ctx.guild.id, ctx.author.id, error=exc))
            return
        await ctx.send(t(self.db, "minecraft_sent", ctx.guild.id, ctx.author.id, method=method, text=text))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def mcstatus(self, ctx):
        """Affiche l'état du pont Discord <-> Minecraft."""
        cfg = self.get_config(ctx.guild.id)
        running = ctx.guild.id in self._log_tasks and not self._log_tasks[ctx.guild.id].done()
        embed = discord.Embed(
            title=t(self.db, "minecraft_status_title", ctx.guild.id, ctx.author.id),
            color=discord.Color.blue(),
        )
        embed.add_field(name="Enabled", value="✅" if cfg.get("enabled") else "❌", inline=True)
        embed.add_field(name="Lecteur log", value="🟢 actif" if running else "⚫ arrêté", inline=True)
        embed.add_field(name="Canal", value=f"<#{cfg['channel_id']}>" if cfg.get("channel_id") else "—", inline=True)
        await ctx.send(embed=embed)

    # --- écouteur Discord -> Minecraft ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.content.startswith((self.bot.command_prefix, "/", "!")):
            return
        cfg = self.get_config(message.guild.id)
        if not cfg.get("enabled") or not cfg.get("channel_id"):
            return
        if message.channel.id != cfg["channel_id"]:
            return

        username = message.author.display_name.replace(" ", "_")[:32]
        text = sanitize_minecraft_input(message.content)
        if not text:
            return
        try:
            await self.send_to_minecraft(message.guild.id, f"<{username}> {text}")
        except RuntimeError as exc:
            print(f"[minecraft] échec envoi Discord->MC : {exc}")


def setup(bot, db):
    bot.add_cog(cmdminecraft(bot, db))
