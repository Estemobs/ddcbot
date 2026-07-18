import os
import subprocess

import discord
from discord.ext import commands, tasks


STATE_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), ".last_announced_commit")
MAX_COMMITS = 10


def _git_log(count):
    try:
        out = subprocess.run(
            ["git", "log", f"-{count}", "--pretty=format:%h %s"],
            cwd=os.path.abspath(os.path.dirname(__file__)),
            capture_output=True, text=True, timeout=5, check=True,
        )
        lines = [line for line in out.stdout.splitlines() if line.strip()]
        return lines
    except (subprocess.SubprocessError, OSError):
        return []


def _current_commit():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=os.path.abspath(os.path.dirname(__file__)),
            capture_output=True, text=True, timeout=5, check=True,
        )
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


class cmdchangelog(commands.Cog):
    """Annonce les mises à jour du bot (nouveaux commits) dans un salon Discord."""

    def __init__(self, bot):
        self.bot = bot
        self.channel_id = os.environ.get("CHANGELOG_CHANNEL_ID")
        self._announce_once.start()

    def cog_unload(self):
        self._announce_once.cancel()

    def _read_last_announced(self):
        try:
            with open(STATE_FILE, "r") as f:
                return f.read().strip()
        except OSError:
            return None

    def _write_last_announced(self, commit_hash):
        try:
            with open(STATE_FILE, "w") as f:
                f.write(commit_hash)
        except OSError:
            pass

    @tasks.loop(count=1)
    async def _announce_once(self):
        await self.bot.wait_until_ready()

        current = _current_commit()
        if not current:
            return

        last_announced = self._read_last_announced()
        if last_announced == current:
            return

        commits = _git_log(MAX_COMMITS)
        self._write_last_announced(current)

        if not last_announced or not self.channel_id or not commits:
            return

        channel = self.bot.get_channel(int(self.channel_id))
        if channel is None:
            return

        description = "\n".join(f"`{line}`" for line in commits)
        embed = discord.Embed(
            title="🚀 DDCBot mis à jour",
            description=description,
            color=discord.Color.blurple(),
        )
        await channel.send(embed=embed)

    @commands.command()
    async def changelog(self, ctx, count: int = 5):
        """Affiche les derniers commits déployés sur le bot."""
        count = max(1, min(count, MAX_COMMITS))
        commits = _git_log(count)
        if not commits:
            await ctx.send("Historique Git indisponible.")
            return
        description = "\n".join(f"`{line}`" for line in commits)
        embed = discord.Embed(title="Derniers changements", description=description, color=discord.Color.blurple())
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(cmdchangelog(bot))
