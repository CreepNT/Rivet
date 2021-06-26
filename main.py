
import os #rename, abort
import re
import discord
import requests

from discord.ext import commands
from requests.models import MissingSchema
from requests.sessions import InvalidSchema

import SECRETS #TOKEN
import CONFIG #REPO_URL, PREFIX
from rivet_cog import RivetCogInitParam, RivetCog

#Create bot
bot = commands.Bot(command_prefix=commands.when_mentioned_or(CONFIG.PREFIX), case_insensitive=True)

initParam = RivetCogInitParam(RivetCog.REMOTE_API_TARGET_GITHUB, #Change this if you implement support for another site
    CONFIG.REPO_URL, CONFIG.LOCAL_ERRORS_DATABASE_PATH, CONFIG.REMOTE_ERRORS_DATABASE_PATH,
    CONFIG.LOCAL_SHORT_CODES_DATABASE_PATH, CONFIG.REMOTE_SHORT_CODES_DATABASE_PATH)

rivet_cog = RivetCog(bot, initParam)
bot.add_cog(rivet_cog)

####Events####
@bot.event
async def on_ready():
    print(f'Bot user - {bot.user} - has connected to Discord.')
    await rivet_cog.refreshStatus()

#Launch bot
bot.run(SECRETS.TOKEN)