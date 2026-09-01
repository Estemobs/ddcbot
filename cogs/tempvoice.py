"""Salons vocaux temporaires.

Rejoindre le salon « hub » cree un vocal appartenant au membre, supprime des
qu'il se vide. Aucune dependance externe : tout passe par l'API Discord du bot.

Commandes :
  ,tempvoice                 — etat de la configuration
  ,tempvoice hub <id>        — salon dont l'entree cree un vocal
  ,tempvoice categorie <id>  — categorie ou creer les vocaux
  ,tempvoice nom <modele>    — modele de nom, variables {user} et {count}
  ,tempvoice limite <n>      — limite de membres (0 = illimitee)
  ,tempvoice on | off
  ,voicename <nom>            — le proprietaire renomme son salon
  ,voicelimit <n>           — le proprietaire change la limite
"""

import discord
from discord.ext import commands

DEFAULT_TEMPLATE = "Salon de {user}"


class cmdtempvoice(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    # --- configuration ---

    def get_config(self, guild_id: int) -> dict:
        self.db.execute("INSERT OR IGNORE INTO tempvoice_config (guild_id) VALUES (?)", (guild_id,))
        return dict(self.db.fetchone(
            "SELECT * FROM tempvoice_config WHERE guild_id = ?", (guild_id,)
        ))

    def set_config(self, guild_id: int, **fields):
        self.get_config(guild_id)
        allowed = {"hub_channel_id", "category_id", "name_template", "user_limit", "enabled"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(
            f"UPDATE tempvoice_config SET {sets} WHERE guild_id = ?",
            list(fields.values()) + [guild_id],
        )

    # --- salons crees ---

    def register(self, channel_id: int, guild_id: int, owner_id: int):
        self.db.execute(
            "INSERT OR REPLACE INTO tempvoice_channels (channel_id, guild_id, owner_id) "
            "VALUES (?, ?, ?)",
            (channel_id, guild_id, owner_id),
        )

    def forget(self, channel_id: int):
        self.db.execute("DELETE FROM tempvoice_channels WHERE channel_id = ?", (channel_id,))

    def is_temp(self, channel_id: int) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM tempvoice_channels WHERE channel_id = ?", (channel_id,)
        ) is not None

    def owner_of(self, channel_id: int):
        row = self.db.fetchone(
            "SELECT owner_id FROM tempvoice_channels WHERE channel_id = ?", (channel_id,)
        )
        return row["owner_id"] if row else None

    def list_channels(self, guild_id: int) -> list:
        return [dict(r) for r in self.db.fetchall(
            "SELECT channel_id, owner_id FROM tempvoice_channels WHERE guild_id = ?", (guild_id,)
        )]

    def render_name(self, template: str, member, count: int = 0) -> str:
        """Nom du salon. Discord tronque a 100 caracteres."""
        name = (template or DEFAULT_TEMPLATE)
        name = name.replace("{user}", getattr(member, "display_name", "?"))
        name = name.replace("{count}", str(count))
        return name[:100] or "Salon temporaire"

    # --- evenements ---

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        guild = member.guild
        cfg = self.get_config(guild.id)

        # Un salon temporaire qui se vide est supprime.
        if before.channel is not None and before.channel.id != (after.channel.id if after.channel else None):
            if self.is_temp(before.channel.id) and not before.channel.members:
                try:
                    await before.channel.delete(reason="Salon temporaire vide")
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
                self.forget(before.channel.id)

        if not cfg["enabled"] or not cfg["hub_channel_id"]:
            return
        if after.channel is None or after.channel.id != cfg["hub_channel_id"]:
            return

        # Entree dans le hub : on cree un salon a ce membre et on l'y deplace.
        category = guild.get_channel(cfg["category_id"]) if cfg["category_id"] else after.channel.category
        try:
            channel = await guild.create_voice_channel(
                name=self.render_name(cfg["name_template"], member),
                category=category,
                user_limit=cfg["user_limit"] or None,
                reason=f"Salon temporaire pour {member}",
            )
            await member.move_to(channel)
        except (discord.Forbidden, discord.HTTPException):
            return
        self.register(channel.id, guild.id, member.id)

    # --- commandes ---

    @commands.command()
    async def tempvoice(self, ctx, action: str = None, *, value: str = None):
        cfg = self.get_config(ctx.guild.id)
        if action is None:
            hub = ctx.guild.get_channel(cfg["hub_channel_id"]) if cfg["hub_channel_id"] else None
            category = ctx.guild.get_channel(cfg["category_id"]) if cfg["category_id"] else None
            embed = discord.Embed(title="Salons vocaux temporaires",
                                  color=discord.Color.blurple())
            embed.add_field(name="Etat", value="Actifs" if cfg["enabled"] else "Desactives",
                            inline=True)
            embed.add_field(name="Salon hub", value=hub.name if hub else "Non defini", inline=True)
            embed.add_field(name="Categorie",
                            value=category.name if category else "Celle du hub", inline=True)
            embed.add_field(name="Modele de nom", value=cfg["name_template"], inline=False)
            embed.add_field(name="Limite",
                            value=str(cfg["user_limit"]) if cfg["user_limit"] else "Illimitee",
                            inline=True)
            embed.add_field(name="Salons actifs",
                            value=str(len(self.list_channels(ctx.guild.id))), inline=True)
            await ctx.send(embed=embed)
            return

        action = action.lower()
        if action == "hub":
            channel = None
            if value and value.strip().isdigit():
                channel = ctx.guild.get_channel(int(value.strip()))
            if not isinstance(channel, discord.VoiceChannel):
                await ctx.send("Usage : `,tempvoice hub <id du salon vocal>`")
                return
            self.set_config(ctx.guild.id, hub_channel_id=channel.id)
            await ctx.send(f"✅ Le salon **{channel.name}** créera les vocaux temporaires.")
        elif action in ("categorie", "category"):
            category = None
            if value and value.strip().isdigit():
                category = ctx.guild.get_channel(int(value.strip()))
            if not isinstance(category, discord.CategoryChannel):
                await ctx.send("Usage : `,tempvoice categorie <id de la catégorie>`")
                return
            self.set_config(ctx.guild.id, category_id=category.id)
            await ctx.send(f"✅ Vocaux créés dans **{category.name}**.")
        elif action in ("nom", "name"):
            if not value:
                await ctx.send("Usage : `,tempvoice nom Salon de {user}`")
                return
            self.set_config(ctx.guild.id, name_template=value)
            await ctx.send("✅ Modèle de nom enregistré.")
        elif action in ("limite", "limit"):
            if not value or not value.strip().isdigit():
                await ctx.send("Usage : `,tempvoice limite 5` (0 = illimitée)")
                return
            self.set_config(ctx.guild.id, user_limit=int(value.strip()))
            await ctx.send("✅ Limite enregistrée.")
        elif action in ("on", "off"):
            self.set_config(ctx.guild.id, enabled=1 if action == "on" else 0)
            state = "activés." if action == "on" else "désactivés."
            await ctx.send(f"✅ Salons temporaires {state}")
        else:
            await ctx.send(
                "Actions : `hub <id>`, `categorie <id>`, `nom <modèle>`, `limite <n>`, `on`, `off`."
            )

    def _owned_channel(self, ctx):
        """Salon temporaire dont l'auteur est proprietaire, sinon None."""
        voice = getattr(ctx.author, "voice", None)
        channel = getattr(voice, "channel", None)
        if channel is None or not self.is_temp(channel.id):
            return None
        if self.owner_of(channel.id) != ctx.author.id:
            return None
        return channel

    @commands.command()
    async def voicename(self, ctx, *, name: str):
        """Renomme son propre salon temporaire."""
        channel = self._owned_channel(ctx)
        if channel is None:
            await ctx.send("❌ Vous devez être dans un salon temporaire qui vous appartient.")
            return
        try:
            await channel.edit(name=name[:100])
        except (discord.Forbidden, discord.HTTPException):
            await ctx.send("❌ Renommage impossible (Discord limite à 2 renommages / 10 min).")
            return
        await ctx.send(f"✅ Salon renommé en **{name[:100]}**.")

    @commands.command()
    async def voicelimit(self, ctx, limit: int):
        """Change la limite de membres de son salon temporaire."""
        channel = self._owned_channel(ctx)
        if channel is None:
            await ctx.send("❌ Vous devez être dans un salon temporaire qui vous appartient.")
            return
        if not 0 <= limit <= 99:
            await ctx.send("❌ La limite doit être comprise entre 0 et 99 (0 = illimitée).")
            return
        try:
            await channel.edit(user_limit=limit or None)
        except (discord.Forbidden, discord.HTTPException):
            await ctx.send("❌ Modification impossible.")
            return
        await ctx.send("✅ Limite mise à jour.")


def setup(bot, db):
    bot.add_cog(cmdtempvoice(bot, db))
