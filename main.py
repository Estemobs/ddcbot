import asyncio
import discord
import json
import requests
import traceback
import os
import aiohttp
from discord import Permissions
from datetime import datetime
from io import BytesIO
from discord.ext import commands
from Notifrss import cmdrss
from utility import cmdutility
from moderation import cmdmoderation
from animations import cmdanim
from income import cmdincome
from economie import cmdeco
from work import cmdwork 
from jeu import cmdjeu

bot = commands.Bot(command_prefix=",", intents=discord.Intents.all())

@bot.event
async def on_ready():
    print("Le bot est en ligne")
    await bot.change_presence(activity=discord.Game(name=",help")) 
    
#automatisation pour signalé les erreurs
@bot.event
async def on_command_error(ctx, error):
    channel = bot.get_channel(827566899004440666)
    error_traceback = traceback.format_exception(type(error), error, error.__traceback__)
    error_msg = ''.join(error_traceback)
    await channel.send(f"Erreur lors de l'exécution de la commande {ctx.command} par {ctx.author}: {error}\n```{error_msg}```")
    print(error_msg)
    
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send_help(ctx.command)
        await ctx.send("Erreur de syntaxe : un ou plusieurs arguments manquants")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("Vous n'avez pas la permission d'utiliser cette commande.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("Vous n'avez pas le rôle requis pour utiliser cette commande.")

async def main():
    with open('secrets.json') as f:
        data = json.load(f)
    token = data['ddc_token']
    await bot.add_cog(cmdrss(bot)) 
    await bot.add_cog(cmdutility(bot)) 
    await bot.add_cog(cmdmoderation(bot)) 
    await bot.add_cog(cmdanim(bot))
    await bot.add_cog(cmdincome(bot))  
    await bot.add_cog(cmdeco(bot)) 
    await bot.add_cog(cmdwork(bot))
    await bot.add_cog(cmdjeu(bot))
    await bot.start(token)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())



