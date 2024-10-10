import discord
from discord.ext import commands
from discord import Permissions

class cmdmoderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.intents = discord.Intents.all()
    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason):
        await ctx.send(f"{member.mention} **a reçu un avertissement pour:** {reason}")
        await member.send(f'**Vous avez été averti pour:** {reason}')

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason):
        await member.send(f'vous avez été banni du serveur {ctx.guild.name} pour {reason}')    
        await ctx.guild.ban(member, reason = reason)
        await ctx.send(f'{member.mention} a été banni')

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member = None, *, reason = None):
        invite = await ctx.channel.create_invite()
        await member.send(f'vous avez été kick du serveur {invite} pour {reason}')    
        await member.kick(reason=reason)
        await ctx.send(f'{member.mention} a été kick pour {reason}')

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int):
        await ctx.channel.purge(limit=amount+1)
        embed = discord.Embed(title=f"{amount} messages ont été effacés.", color=discord.Color.green())
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(cmdmoderation(bot))