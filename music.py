import asyncio
from typing import Any

import discord
from discord.ext import commands


FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class MusicPlayModal(discord.ui.Modal, title="Ajouter une piste"):
    source = discord.ui.TextInput(
        label="URL ou source audio",
        placeholder="https://... (flux audio direct recommandé)",
        required=True,
        max_length=500,
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.enqueue_from_interaction(interaction, str(self.source))


class MusicPanelView(discord.ui.View):
    def __init__(self, cog, author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message("Cette action doit être utilisée sur un serveur.", ephemeral=True)
            return False
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Seul l'auteur peut utiliser ce panneau.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success, emoji="🎵", row=0)
    async def add_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MusicPlayModal(self.cog))

    @discord.ui.button(label="Pause/Reprendre", style=discord.ButtonStyle.primary, emoji="⏯️", row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        message = await self.cog.toggle_pause_for_guild(interaction.guild)
        await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️", row=0)
    async def skip_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        message = await self.cog.skip_for_guild(interaction.guild)
        await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️", row=1)
    async def stop_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        message = await self.cog.stop_for_guild(interaction.guild)
        await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label="Déconnecter", style=discord.ButtonStyle.danger, emoji="📤", row=1)
    async def leave_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        message = await self.cog.leave_for_guild(interaction.guild)
        await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label="Rafraîchir", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.cog.build_music_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)


class cmdmusic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_states: dict[int, dict[str, Any]] = {}

    def get_state(self, guild_id: int) -> dict[str, Any]:
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = {"queue": [], "current": None, "text_channel_id": None}
        return self.guild_states[guild_id]

    def build_music_embed(self, guild: discord.Guild) -> discord.Embed:
        state = self.get_state(guild.id)
        voice_client = guild.voice_client
        status = "Déconnecté"
        if voice_client and voice_client.is_connected():
            if voice_client.is_paused():
                status = "En pause"
            elif voice_client.is_playing():
                status = "Lecture"
            else:
                status = "Connecté"

        current = state["current"] or "Aucune piste en cours"
        upcoming = state["queue"][:5]
        queue_display = "\n".join(f"{index + 1}. {item}" for index, item in enumerate(upcoming))
        if not queue_display:
            queue_display = "Aucune piste en file d'attente"

        embed = discord.Embed(
            title="🎶 Panneau musique",
            description="Interface moderne pour contrôler la musique du serveur.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="État", value=status, inline=True)
        embed.add_field(name="En cours", value=current, inline=False)
        embed.add_field(name="File d'attente", value=queue_display, inline=False)
        embed.set_footer(text=f"Serveur: {guild.name}")
        return embed

    async def ensure_voice_for_member(self, member: discord.Member) -> tuple[discord.VoiceClient | None, str | None]:
        if member.voice is None or member.voice.channel is None:
            return None, "Tu dois être dans un salon vocal."
        channel = member.voice.channel
        voice_client = member.guild.voice_client
        if voice_client is None:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)
        return voice_client, None

    async def enqueue_track(self, guild: discord.Guild, source: str, text_channel_id: int):
        state = self.get_state(guild.id)
        state["queue"].append(source.strip())
        state["text_channel_id"] = text_channel_id
        voice_client = guild.voice_client
        if voice_client and not voice_client.is_playing() and not voice_client.is_paused() and state["current"] is None:
            await self.play_next(guild)

    async def enqueue_from_interaction(self, interaction: discord.Interaction, source: str):
        if interaction.guild is None:
            await interaction.response.send_message("Commande indisponible en message privé.", ephemeral=True)
            return
        if source.strip().startswith("-"):
            await interaction.response.send_message(
                "Source invalide : les sources ne peuvent pas commencer par un tiret.",
                ephemeral=True,
            )
            return
        voice_client, error = await self.ensure_voice_for_member(interaction.user)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await self.enqueue_track(interaction.guild, source, interaction.channel_id)
        if voice_client is None:
            await interaction.response.send_message("Impossible de rejoindre le salon vocal.", ephemeral=True)
            return
        state = self.get_state(interaction.guild.id)
        await interaction.response.send_message(
            f"✅ Piste ajoutée ({len(state['queue'])} en attente).",
            ephemeral=True,
        )

    async def send_music_message(self, guild: discord.Guild, content: str):
        state = self.get_state(guild.id)
        channel_id = state.get("text_channel_id")
        if channel_id is None:
            return
        channel = guild.get_channel(channel_id)
        if channel:
            await channel.send(content)

    async def play_next(self, guild: discord.Guild):
        state = self.get_state(guild.id)
        voice_client = guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            state["current"] = None
            return
        if not state["queue"]:
            state["current"] = None
            await self.send_music_message(guild, "📭 File d'attente terminée.")
            return

        source = state["queue"].pop(0)
        state["current"] = source
        try:
            audio_source = discord.FFmpegPCMAudio(source, **FFMPEG_OPTIONS)
        except Exception as exc:
            await self.send_music_message(guild, f"❌ Impossible de lire la source: {exc}")
            state["current"] = None
            await self.play_next(guild)
            return

        def _after_play(error):
            if error:
                future = asyncio.run_coroutine_threadsafe(
                    self.send_music_message(guild, f"❌ Erreur de lecture: {error}"),
                    self.bot.loop,
                )
                future.result()
            asyncio.run_coroutine_threadsafe(self.play_next(guild), self.bot.loop)

        voice_client.play(audio_source, after=_after_play)
        await self.send_music_message(guild, f"▶️ Lecture: {source}")

    async def skip_for_guild(self, guild: discord.Guild) -> str:
        voice_client = guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            return "❌ Le bot n'est pas connecté en vocal."
        if not voice_client.is_playing() and not voice_client.is_paused():
            return "❌ Rien à skip."
        voice_client.stop()
        return "⏭️ Piste passée."

    async def stop_for_guild(self, guild: discord.Guild) -> str:
        state = self.get_state(guild.id)
        state["queue"].clear()
        state["current"] = None
        voice_client = guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
        return "⏹️ Lecture stoppée et file vidée."

    async def leave_for_guild(self, guild: discord.Guild) -> str:
        state = self.get_state(guild.id)
        state["queue"].clear()
        state["current"] = None
        voice_client = guild.voice_client
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
            return "📤 Déconnecté du vocal."
        return "❌ Le bot n'est pas connecté en vocal."

    async def toggle_pause_for_guild(self, guild: discord.Guild) -> str:
        voice_client = guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            return "❌ Le bot n'est pas connecté en vocal."
        if voice_client.is_playing():
            voice_client.pause()
            return "⏸️ Lecture en pause."
        if voice_client.is_paused():
            voice_client.resume()
            return "▶️ Lecture reprise."
        return "❌ Rien à mettre en pause."

    @commands.command()
    async def musicpanel(self, ctx):
        embed = self.build_music_embed(ctx.guild)
        view = MusicPanelView(self, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def join(self, ctx):
        _, error = await self.ensure_voice_for_member(ctx.author)
        if error:
            await ctx.send(error)
            return
        await ctx.send("✅ Connecté au salon vocal.")

    @commands.command()
    async def play(self, ctx, *, source: str):
        if source.strip().startswith("-"):
            await ctx.send("❌ Source invalide : les sources ne peuvent pas commencer par un tiret.")
            return
        voice_client, error = await self.ensure_voice_for_member(ctx.author)
        if error:
            await ctx.send(error)
            return
        await self.enqueue_track(ctx.guild, source, ctx.channel.id)
        if voice_client is None:
            await ctx.send("❌ Impossible de rejoindre le salon vocal.")
            return
        state = self.get_state(ctx.guild.id)
        await ctx.send(f"🎵 Ajouté à la file ({len(state['queue'])} en attente).")

    @commands.command()
    async def queue(self, ctx):
        state = self.get_state(ctx.guild.id)
        if not state["queue"]:
            await ctx.send("📭 File d'attente vide.")
            return
        listing = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(state["queue"][:10]))
        await ctx.send(f"🎶 File d'attente:\n{listing}")

    @commands.command()
    async def nowplaying(self, ctx):
        state = self.get_state(ctx.guild.id)
        if not state["current"]:
            await ctx.send("📭 Aucune piste en cours.")
            return
        await ctx.send(f"🎧 En cours: {state['current']}")

    @commands.command()
    async def skip(self, ctx):
        await ctx.send(await self.skip_for_guild(ctx.guild))

    @commands.command()
    async def stop(self, ctx):
        await ctx.send(await self.stop_for_guild(ctx.guild))

    @commands.command()
    async def pause(self, ctx):
        voice_client = ctx.guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            await ctx.send("❌ Le bot n'est pas connecté en vocal.")
            return
        if not voice_client.is_playing():
            await ctx.send("❌ Rien à mettre en pause.")
            return
        voice_client.pause()
        await ctx.send("⏸️ Lecture en pause.")

    @commands.command()
    async def resume(self, ctx):
        voice_client = ctx.guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            await ctx.send("❌ Le bot n'est pas connecté en vocal.")
            return
        if not voice_client.is_paused():
            await ctx.send("❌ Rien à reprendre.")
            return
        voice_client.resume()
        await ctx.send("▶️ Lecture reprise.")

    @commands.command()
    async def leave(self, ctx):
        await ctx.send(await self.leave_for_guild(ctx.guild))
