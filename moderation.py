import discord
from discord.ext import commands
from datetime import timedelta

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