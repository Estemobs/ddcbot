import discord
import asyncio
import random
from discord.ext import commands

class cmdanim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()
        self.giveaways = {}

    @commands.command()
    @commands.has_role(605448594010669076)
    async def gstart(self, ctx, duration: int, *, prize: str):
        if ctx.guild.id in self.giveaways:
            return await ctx.send("Il y a déjà un Giveaway en cours.")

        self.giveaways[ctx.guild.id] = {"PRIZE": prize, "USERS": [], "RUNNING": True, "DURATION": duration}
        await ctx.send(f"Giveaway démarré pour {duration} secondes! Le prix est {prize}")
        await asyncio.sleep(duration)
        if self.giveaways[ctx.guild.id]["RUNNING"] == True:
            await ctx.send("fin du Giveaway")


    @commands.command()
    @commands.has_role(605448594010669076)
    async def gend(self, ctx):
        if ctx.guild.id not in self.giveaways:
            return await ctx.send("Il n'y a pas de Giveaway en cours.")
        self.giveaways[ctx.guild.id]["RUNNING"] = False
        winner = random.choice(self.giveaways[ctx.guild.id]["USERS"])
        await ctx.send(f"Giveaway terminé! Le gagnant est {winner}! Le prix était {self.giveaways[ctx.guild.id]['PRIZE']}")
        self.giveaways.pop(ctx.guild.id)

    @commands.command()
    @commands.has_role(605448594010669076)
    async def gcancel(self, ctx):
        if ctx.guild.id not in self.giveaways:
            return await ctx.send("Il n'y a pas de Giveaway en cours.")
        self.giveaways[ctx.guild.id]["RUNNING"] = False
        await ctx.send(f"Giveaway annulé! Le prix était {self.giveaways[ctx.guild.id]['PRIZE']}")
        self.botgiveaways.pop(ctx.guild.id)


def setup(bot):
    bot.add_cog(cmdanim(bot))    