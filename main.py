
import os
import re
import discord
from discord import sticker
import requests
from discord.ext import commands

import SECRETS #TOKEN
import CONFIG #REPO_URL, PREFIX
import error_database

#Get JSON data from GitHub's repos API
async def fetch_api(ctx, api_entry : str) -> dict:
    global api_endpoint
    r = requests.get(api_endpoint + api_entry, headers={"Accept": "application/vnd.github.v3+json"})
    if (r.status_code != 200):
        await ctx.send(f"Failed to fetch API endpoint `{api_endpoint + api_entry}` - Got HTTP error {r.status_code}")
        return None

    else:
        return r.json()

#Generates the GitHub API URL for a given repository
def generate_api_endpoint(repo_url : str) -> str:
    s = re.findall("^https://github.com/([a-zA-Z0-9_\-.]+/[a-zA-Z0-9_\-.]+)/?$", repo_url)
    if (len(s) != 1):
        print(f"Couldn't generate API endpoint URL from provided repo URL '{repo_url}' !")
        exit(0)
    else:
        return "https://api.github.com/repos/" + s[0] + "/"

#Update the local database file
async def update_db(db_file_path : str, db_dowload_url : str) -> bool:
    r = requests.get(db_dowload_url)
    if (r.status_code == 200):
        try:
            os.rename(db_file_path, db_file_path + ".old")
        except:
            pass
        try:
            fh = open(db_file_path, "wb")
            fh.write(r.content)
            fh.close()
            return True
        except:
            print(f"Error when opening '{db_file_path}' for writing.")
            return False
    else:
        return False

####Initialization####
#Load database hash
try:
    fh = open(CONFIG.SHA1_SUM_STORAGE, "r")
    errorsDbSha1 = fh.readline().lower().rstrip()
    print(f"Loaded errors database SHA-1 : '{errorsDbSha1}'.")
    fh.close()
except:
    print("Failed to open '%s' for reading.\nUsing all zeroes as hash..." % CONFIG.SHA1_SUM_STORAGE)
    errorsDbSha1 = "0000000000000000000000000000000000000000"


#Generate API endpoint (for refreshing)
api_endpoint = generate_api_endpoint(CONFIG.REPO_URL) 
print(f"API endpoint URL is '{api_endpoint}'.")

#Load database
errorsDb = error_database.createDbFromJSONFile(CONFIG.DATABASE_PATH)
if (errorsDb == None):
    print("Error while loading errors database.")

#Create bot
bot = commands.Bot(command_prefix=commands.when_mentioned_or(CONFIG.PREFIX), case_insensitive=True)

@bot.event
async def on_ready():
    print(f'Bot user - {bot.user} - has connected to Discord.')
    if (errorsDb == None):
        game = discord.Game(name="Database is broken")
        status = discord.Status.do_not_disturb
    else:
        game = discord.Game(name="resolving PSVita error codes !")
        status = discord.Status.online
    await bot.change_presence(activity=game, status=status)

@bot.command(name="updatedb", aliases=["refresh", "refreshdb"], help='Updates the database of the bot')
async def refreshcfg(ctx):
    if not (ctx.message.author.id in SECRETS.WHITELIST):
        await ctx.send("Sorry, but you are not allowed to use this command.")
        return

    print(f"User {ctx.message.author.name}#{ctx.message.author.discriminator} (ID : {ctx.message.author.id}) initiated a database update.")

    global errorsDbSha1, constantsDbSha1, errorsDb, constantsDb

    errorsUpdated = False
    constantsUpdated = False

    await ctx.send("Updating errors database...")
    api_resp = await fetch_api(ctx, f"contents/{CONFIG.REMOTE_DATABASE_PATH}")
    if (api_resp == None) or (len(api_resp) == 0):
        await ctx.send("Failed to fetch errors database information. It will not be updated")
    else:
        await ctx.send(f"Local database SHA-1 : `{errorsDbSha1}`\nOnline database SHA-1 :`{api_resp['sha']}`")
        if (errorsDbSha1 != api_resp['sha'].lower()) or errorsDb == None:
            errorsUpdated = await update_db(CONFIG.DATABASE_PATH, api_resp['download_url'])
            errorsDbSha1 = api_resp['sha'].lower()
            if errorsUpdated:
                errorsDb = error_database.createDbFromJSONFile(CONFIG.DATABASE_PATH)
                if errorsDb == None:
                    await ctx.send("Failed to load new errors database.")
                else:
                    await ctx.send("Errors database updated and reloaded successfully !")
            else:
                await ctx.send("Failed to update errors database.")
        else:
            errorsUpdated = False
            await ctx.send("SHA-1 hashes are identical, update is not needed.")

    if errorsUpdated:
        await saveHash(ctx)

    if (errorsDb == None):
        game = discord.Game(name="Database is broken")
        status = discord.Status.do_not_disturb
    else:
        game = discord.Game(name="resolving PSVita error codes !")
        status = discord.Status.online
    await bot.change_presence(activity=game, status=status)
    await ctx.send("Update finished !\n")

@bot.command(name='error_code', aliases=["sce_error", "error"], help='Displays the name of a given error code')
async def errorCode(ctx, error_str : str):
    if error_str.startswith("0x"):
        try:
            errcode = int(error_str[2:], 16)
        except:
            await ctx.send(f"`{error_str}` is not a valid input.")
            return
    else:
        try:
            errcode = int(error_str, 10)
        except:
            try:
                errcode = int(error_str, 16)
            except:
                await ctx.send(f"`{error_str}` is not a valid input.")
                return

    if (errorsDb == None):
        await ctx.send("Errors database is not loaded.\n")
    else:
        await ctx.send("```\n" + error_database.getErrorCodeInfo(errorsDb, errcode) + "\n```")

@bot.command(name='save_hash', help="Update the database hash save file - only use if you know what you're doing")
async def saveHash(ctx) -> bool:
    if not (ctx.message.author.id in SECRETS.WHITELIST):
        await ctx.send("Sorry, but you are not allowed to use this command.")
        return

    global errorsDbSha1, constantsDbSha1
    try:
        fh = open(CONFIG.SHA1_SUM_STORAGE, "w")
    except:
        await ctx.send(f"Failed to open '{CONFIG.SHA1_SUM_STORAGE}' for writing.\nSHA-1 sum have not been saved.")
        return False
    fh.write(errorsDbSha1 + "\n")
    fh.close()
    await ctx.send(f"New SHA-1 sum has been saved successfully.")
    return True

@bot.event
async def on_command_error(ctx, error):
    print(f"{error}")
    if (str(error).rfind("is not found") == -1):
        await ctx.send(f"{error}")
    else:
        await ctx.send("😥Sorry, command not found.")

#Launch bot
bot.run(SECRETS.TOKEN)