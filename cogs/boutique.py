"""Boutique du serveur.

Separe volontairement du catalogue des jeux : `,games` montre a quoi on peut
jouer, `,shop` montre ce qu'on peut acheter. Les deux se rejoignent par
l'inventaire — un article de type ticket depose une entree que `,<jeu>`
consomme ensuite.

Les regles vivent dans shop_engine, sans discord.py.

Commandes :
  ,shop                        — articles en vente
  ,buy <article> [quantite]    — achete
  ,shopadd <slug> <prix> <ticket|role|objet> <valeur> [nom]
  ,shopdel <slug>
  ,shopstats
"""

import discord
from discord.ext import commands

from casino_engine import CasinoEngine, normalize_slug
from settings_fields import Field, FieldError, apply_field, describe_fields
from shop_engine import ShopEngine, ShopError, describe_item, stock_label

# Memes champs que le formulaire de la page Boutique.
ITEM_FIELDS = {
    "nom": Field("text", "Nom affiché"),
    "prix": Field("float", "Prix", minimum=0),
    "stock": Field("int", "Stock disponible (-1 = illimité)", minimum=-1),
    "limite": Field("int", "Achats maximum par joueur (0 = sans limite)", minimum=0),
    "role": Field("id", "Rôle requis pour acheter (vide = ouvert à tous)"),
    "categorie": Field("text", "Catégorie d'affichage"),
    "description": Field("text", "Description"),
    "actif": Field("bool", "Article en vente"),
}
ITEM_FIELD_COLUMNS = {
    "nom": "display_name", "prix": "price", "stock": "stock",
    "limite": "per_user_limit", "role": "required_role_id",
    "categorie": "category", "description": "description", "actif": "enabled",
}

KIND_ALIASES = {
    "ticket": "ticket", "entree": "ticket", "entrée": "ticket", "jeu": "ticket",
    "role": "role", "rôle": "role", "grade": "role",
    "objet": "item", "item": "item",
}


class cmdboutique(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.shop = ShopEngine(db)
        self.casino = CasinoEngine(db)

    def get_balance(self, user_id: int) -> float:
        row = self.db.fetchone("SELECT amount FROM balances WHERE user_id = ?", (user_id,))
        return row["amount"] if row else 0.0

    def add_balance(self, user_id: int, delta: float):
        self.db.execute(
            "INSERT INTO balances (user_id, amount) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET amount = amount + excluded.amount",
            (user_id, delta),
        )

    def money(self, guild_id: int, amount: float) -> str:
        style = self.casino.get_style(guild_id)
        return f"{amount:,.0f}".replace(",", " ") + style["currency_symbol"]

    def role_names(self, guild, items) -> dict:
        names = {}
        for item in items:
            if item["kind"] == "role" and str(item["value"]).isdigit():
                role = guild.get_role(int(item["value"]))
                if role is not None:
                    names[int(item["value"])] = role.name
        return names

    # --- commandes joueur ---

    @commands.command()
    async def shop(self, ctx):
        """Articles en vente sur le serveur."""
        items = self.shop.list_items(ctx.guild.id)
        if not items:
            await ctx.send(
                "La boutique est vide. Un admin peut la remplir avec `,shopadd` "
                "ou depuis le dashboard.\nPour voir les jeux : `,games`."
            )
            return

        names = self.role_names(ctx.guild, items)
        by_category = {}
        for item in items:
            by_category.setdefault(item["category"] or "Articles", []).append(item)

        embed = discord.Embed(
            title="🛒 Boutique",
            description=f"Votre solde : **{self.money(ctx.guild.id, self.get_balance(ctx.author.id))}**",
            color=discord.Color.blurple(),
        )
        for category, entries in by_category.items():
            lines = []
            for item in entries:
                line = (f"`,buy {item['slug']}` — **{item['display_name']}** · "
                        f"{self.money(ctx.guild.id, item['price'])}")
                if item["stock"] != -1:
                    line += f" · stock {stock_label(item)}"
                if item["per_user_limit"]:
                    already = self.shop.bought_by(ctx.guild.id, ctx.author.id, item["slug"])
                    line += f" · {already}/{item['per_user_limit']}"
                lines.append(line + f"\n　{describe_item(item, role_names=names)}")
            embed.add_field(name=str(category).capitalize(), value="\n".join(lines),
                            inline=False)
        embed.set_footer(text="Les jeux se lancent avec ,games puis ,<nom du jeu>")
        await ctx.send(embed=embed)

    @commands.command()
    async def buy(self, ctx, slug: str = None, quantity: int = 1):
        """,buy <article> [quantité] — paie et livre immédiatement."""
        if slug is None:
            await ctx.send("Usage : `,buy <article> [quantité]` — voir `,shop`.")
            return
        item = self.shop.get_item(ctx.guild.id, normalize_slug(slug))
        if item is None:
            await ctx.send(f"❌ Aucun article `{slug}` en boutique. Voir `,shop`.")
            return

        role_ids = [role.id for role in getattr(ctx.author, "roles", [])]
        refusal = self.shop.check_purchase(
            item, ctx.guild.id, ctx.author.id, quantity,
            balance=self.get_balance(ctx.author.id), role_ids=role_ids,
        )
        if refusal:
            await ctx.send(f"❌ {refusal}")
            return

        # Livraison d'abord pour ce qui peut echouer cote Discord : inutile de
        # debiter quelqu'un pour un role que le bot ne peut pas attribuer.
        if item["kind"] == "role":
            role = ctx.guild.get_role(int(item["value"]))
            if role is None:
                await ctx.send("❌ Le rôle vendu par cet article est introuvable.")
                return
            try:
                await ctx.author.add_roles(role, reason=f"Achat boutique : {item['slug']}")
            except discord.Forbidden:
                await ctx.send("❌ Le bot n'a pas la permission d'attribuer ce rôle.")
                return
        else:
            kind = "ticket" if item["kind"] == "ticket" else "item"
            for _ in range(quantity):
                self.casino.add_item(ctx.guild.id, ctx.author.id, item["value"], kind)

        total = self.shop.record_purchase(ctx.guild.id, ctx.author.id, item, quantity)
        self.add_balance(ctx.author.id, -total)
        self.db.log_transaction(
            ctx.guild.id, ctx.author.id, -total, "shop", f"achat {item['slug']} x{quantity}"
        )

        names = self.role_names(ctx.guild, [item])
        embed = discord.Embed(
            title="🛒 Achat effectué",
            description=f"Vous recevez {describe_item(item, role_names=names)}"
                        + (f" × {quantity}" if quantity > 1 else ""),
            color=discord.Color.green(),
        )
        embed.add_field(name="Payé", value=self.money(ctx.guild.id, total), inline=True)
        embed.add_field(name="Solde",
                        value=self.money(ctx.guild.id, self.get_balance(ctx.author.id)),
                        inline=True)
        if item["kind"] == "ticket":
            embed.set_footer(text=f"Utilisez-la avec ,{item['value']}")
        await ctx.send(embed=embed)

    # --- commandes d'administration ---

    @commands.command()
    async def shopadd(self, ctx, slug: str = None, price: float = None,
                      kind: str = None, value: str = None, *, display_name: str = None):
        """,shopadd <slug> <prix> <ticket|role|objet> <valeur> [nom affiché]"""
        if slug is None or price is None or kind is None or value is None:
            await ctx.send(
                "Usage : `,shopadd <slug> <prix> <ticket|role|objet> <valeur> [nom]`\n"
                "Exemples :\n"
                "`,shopadd ticket-loto 5000 ticket loto Ticket de Loto`\n"
                "`,shopadd vip 25000 role 123456789012345678 VIP`\n"
                "`,shopadd sticker 500 objet \"Sticker rare\"`"
            )
            return
        resolved = KIND_ALIASES.get(kind.lower())
        if resolved is None:
            await ctx.send("❌ Types : `ticket`, `role`, `objet`.")
            return
        if resolved == "ticket" and self.casino.get_game(ctx.guild.id, normalize_slug(value)) is None:
            await ctx.send(
                f"❌ Aucun jeu `{normalize_slug(value)}` : un ticket doit désigner un jeu existant."
            )
            return
        try:
            self.shop.create_item(
                ctx.guild.id, slug, display_name or slug, resolved,
                normalize_slug(value) if resolved == "ticket" else value, price,
            )
        except ShopError as exc:
            await ctx.send(f"❌ {exc}")
            return
        await ctx.send(
            f"✅ **{display_name or slug}** en vente pour "
            f"{self.money(ctx.guild.id, price)} — `,buy {normalize_slug(slug)}`"
        )

    @commands.command()
    async def shopedit(self, ctx, slug: str = None, field: str = None, *, value: str = None):
        """,shopedit <article> <champ> <valeur> — sans champ, liste les réglages."""
        if slug is None:
            await ctx.send("Usage : `,shopedit <article> <champ> <valeur>`")
            return
        item = self.shop.get_item(ctx.guild.id, normalize_slug(slug))
        if item is None:
            await ctx.send("❌ Cet article n'existe pas.")
            return
        if field is None:
            current = {key: item[column] for key, column in ITEM_FIELD_COLUMNS.items()}
            await ctx.send(embed=discord.Embed(
                title=f"Réglages — {item['display_name']}",
                description=describe_fields(ITEM_FIELDS, current),
                color=discord.Color.blurple(),
            ))
            return
        try:
            key, parsed = apply_field(ITEM_FIELDS, field, value)
        except FieldError as exc:
            await ctx.send(f"❌ {exc}")
            return
        try:
            self.shop.update_item(item["id"], **{ITEM_FIELD_COLUMNS[key]: parsed})
        except ShopError as exc:
            await ctx.send(f"❌ {exc}")
            return
        await ctx.send(f"✅ **{item['display_name']}** — `{key}` = **{parsed}**")

    @commands.command()
    async def shopdel(self, ctx, *, slug: str):
        if self.shop.delete_item(ctx.guild.id, normalize_slug(slug)):
            await ctx.send("✅ Article retiré de la boutique.")
        else:
            await ctx.send("❌ Cet article n'existe pas.")

    @commands.command()
    async def shopstats(self, ctx):
        """Ce que la boutique a vendu."""
        overall = self.shop.sales_stats(ctx.guild.id)
        embed = discord.Embed(
            title="🛒 Ventes",
            description=f"**{overall['orders']}** achat(s) · {overall['units']} article(s) · "
                        f"{self.money(ctx.guild.id, overall['revenue'])} retirés de l'économie",
            color=discord.Color.gold(),
        )
        for item in self.shop.list_items(ctx.guild.id, include_disabled=True)[:15]:
            stats = self.shop.sales_stats(ctx.guild.id, item["slug"])
            if not stats["units"]:
                continue
            embed.add_field(
                name=item["display_name"],
                value=f"{stats['units']} vendu(s) · "
                      f"{self.money(ctx.guild.id, stats['revenue'])}",
                inline=True,
            )
        await ctx.send(embed=embed)


def setup(bot, db):
    bot.add_cog(cmdboutique(bot, db))
