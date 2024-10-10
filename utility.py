import discord
import asyncio
from discord.ext import commands

class cmdutility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()


    @commands.command()
    async def role_id(self, ctx, *, role_name):
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if role is not None:
            await ctx.send(f"L'ID du rôle {role_name} est : {role.id}")
        else:
            await ctx.send(f"Le rôle {role_name} n'existe pas sur ce serveur.")

    @commands.command()
    async def role_name(self, ctx, role_id: int):
        role = discord.utils.get(ctx.guild.roles, id=role_id)
        if role is not None:
            await ctx.send(f"Le nom du rôle avec l'ID {role_id} est : {role.name}")
        else:
            await ctx.send(f"Aucun rôle n'a l'ID {role_id} sur ce serveur.")
            
    @commands.command()
    async def rmd(self, ctx, duree: str, *, message: str):
        # Extraire l'argument temps et unite à partir de la chaîne duree
        temps = duree[:-1]
        unite = duree[-1]
        # Vérifiez si l'argument temps est un entier valide
        if not temps.isnumeric():
            await ctx.send("Format du rappel incorrect, veuillez utiliser les unités de temps telles que `d, h, m, s` pour votre rappel. Exemple : `,rmd 30m je vais dormir.`")
            return
        # Convertir l'argument temps en un int
        temps = int(temps)
        # Définir le dictionnaire pour associer les unités de chaîne à leur durée correspondante en secondes
        unites = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        # Vérifiez si l'unité passée est une clé valide dans le dictionnaire unites
        if unite not in unites:
            await ctx.send("Format du rappel incorrect, veuillez utiliser les unités de temps telles que `d, h, m, s` pour votre rappel. Exemple : `,rmd 30m je vais dormir.`")
            return
        retard = temps * unites[unite]
        await ctx.send(f"Rappel enregistré, je vous enverrai **{message}** dans **{temps}{unite}.**")
        await asyncio.sleep(retard)
        await ctx.send(f"{ctx.author.mention} ⏰ **Rappel:** {message}")

    @commands.command()
    async def avatar(self, ctx, member:discord.Member):
        em = discord.Embed(description=f'● Voici la photo de profil de {member}', color=0x04ff00)
        em.set_image(url=member.avatar)
        
        await ctx.send(embed=em)

    @commands.command()
    async def serverpicture(self, ctx):
        embed = discord.Embed(title="Server Icon", color=discord.Color.green())
        embed.set_image(url=ctx.guild.icon)
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(cmdutility(bot))