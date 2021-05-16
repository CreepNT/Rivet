
import os #rename
import re
import discord
import requests
from hashlib import sha1
from discord.ext import commands
from requests.models import MissingSchema
from requests.sessions import InvalidSchema

import SECRETS #TOKEN
import CONFIG #REPO_URL, PREFIX
import database

SHA1_ALL_ZEROES =  "0000000000000000000000000000000000000000"

####Util functions####
#Generates the GitHub API URL for a given repository, needed for later operations
def generate_api_endpoint(repo_url : str) -> str:
    s = re.findall("^https://github.com/([a-zA-Z0-9_\-.]+/[a-zA-Z0-9_\-.]+)/?$", repo_url)
    if (len(s) != 1):
        print(f"Couldn't generate API endpoint URL from provided repo URL '{repo_url}' !")
        exit(0)
    else:
        return "https://api.github.com/repos/" + s[0] + "/"

#Update the local database file
async def install_new_db(db_file_path : str, db_data) -> bool:
    try:
        os.remove(db_file_path + ".old")
        os.rename(db_file_path, db_file_path + ".old")
    except FileNotFoundError:
        pass
    try:
        fh = open(db_file_path, "wb")
        fh.write(db_data)
        fh.close()
        return True
    except IOError:
        print(f"IOError raised when operating on '{db_file_path}'.")
        return False

#Refresh the status message of the bot
async def refresh_status() -> None:
    global databaseObject
    if (databaseObject == None):
        game = discord.Game(name="Database is broken")
        status = discord.Status.dnd
    else:
        game = discord.Game(name="resolving PS Vita error codes !")
        status = discord.Status.online
    await bot.change_presence(activity=game, status=status)

####Initialization####
#Generate GitHub API endpoint
api_endpoint = generate_api_endpoint(CONFIG.REPO_URL)
print(f"Generated API Endpoint : {api_endpoint}")

#Calculate database SHA-1
try:
    fh = open(CONFIG.DATABASE_PATH, "rb")
    content = fh.read()
    fh.close()
    sha1ctx = sha1()
    sha1ctx.update(content)
    databaseSha1 = sha1ctx.hexdigest().lower()
    print(f"Calculated database SHA-1 : {sha1ctx.hexdigest()}")
    del content, sha1ctx
except IOError:
    print(f"IOError raised while operating on '{CONFIG.DATABASE_PATH}'.")
    print("Using all zeroes as SHA-1 hash...")
    databaseSha1 = SHA1_ALL_ZEROES

#Load database
databaseObject = database.getDatabaseFromJSONFile(CONFIG.DATABASE_PATH)
if (databaseObject == None):
    print(f"Failed to load database from local file ({CONFIG.DATABASE_PATH}).")
    print("Using all zeroes as SHA-1 hash...")
    databaseSha1 = SHA1_ALL_ZEROES

#Create bot
bot = commands.Bot(command_prefix=commands.when_mentioned_or(CONFIG.PREFIX), case_insensitive=True)

####Events####
@bot.event
async def on_ready():
    print(f'Bot user - {bot.user} - has connected to Discord.')
    await refresh_status()

@bot.event
async def on_command_error(ctx, error):
    print(f"{error}")
    if (str(error).rfind("is not found") == -1): #Yes.
        await ctx.send(f"{error}")
    else:
        await ctx.send("😥Sorry, command not found.")

####Commands####
@bot.command(name="update_db", aliases=["refresh", "refresh_db"], help="Updates the database of the bot")
async def updateDb(ctx):
    if not (ctx.message.author.id in SECRETS.WHITELIST):
        await ctx.send("Sorry, but you are not allowed to use this command.")
        return

    print(f"User {ctx.message.author.name}#{ctx.message.author.discriminator} (ID : {ctx.message.author.id}) initiated a database update.")

    global databaseSha1, databaseObject, api_endpoint

    await ctx.send("Updating database...")

    #We need to get content of the folder our database is in
    #Everything before the last / are folders, everything after is the filename
    slashIdx = CONFIG.REMOTE_DATABASE_PATH.rfind("/")
    if slashIdx == -1: #No / found
        remoteDbName = CONFIG.REMOTE_DATABASE_PATH
        apiRequestURL = api_endpoint + "contents/"
    else:
        remoteDbName = CONFIG.REMOTE_DATABASE_PATH[slashIdx + 1:] #+1 to skip the /
        apiRequestURL = api_endpoint + f"contents/{CONFIG.REMOTE_DATABASE_PATH[:slashIdx]}"

    req = requests.get(apiRequestURL, headers={"Accept": "application/vnd.github.v3+json"})
    if req.status_code != 200:
        await ctx.send(f"Failed to fetch API (`{apiRequestURL}`) - got HTTP Status {req.status_code}.")
        await ctx.send("😡 Update failed !")
        await refresh_status()
        return
    
    try:
        jsonData = req.json()
    except ValueError:
        await ctx.send("Failed to decode API response for blob SHA-1.")
        await ctx.send(f"API Response :\n```{req.content}```")
        await ctx.send("😡 Update failed !")
        await refresh_status()
        return
    
    downloadURL = None
    for data in jsonData:
        filename = data.get('name')
        if filename == None or filename != remoteDbName:
            continue
        else:
            downloadURL = data.get("download_url")
    
    if downloadURL == None:
        await ctx.send("Failed to find database file on remote repository.")
        await ctx.send("😡 Update failed !")
        return
        
    req = requests.get(downloadURL)
    if req.status_code != 200:
        await ctx.send(f"Failed to download database from repository - got HTTP Status {req.status_code}.")
        await ctx.send("😡 Update failed !")
        await refresh_status()
        return
    
    sha1ctx = sha1()
    sha1ctx.update(req.content)
    remoteSha1 = sha1ctx.hexdigest().lower() #We always store local SHA-1 in lowercase, so we convert just to be sure.
    await ctx.send(f"```diff\n- Local database SHA-1 :\n- {databaseSha1}\n+ Repository database SHA-1 :\n+ {remoteSha1}\n```")

    if (databaseSha1 != remoteSha1) or databaseObject == None:
        databaseUpdated = await install_new_db(CONFIG.DATABASE_PATH, req.content)
        if databaseUpdated:
            databaseSha1 = remoteSha1
            print(f"New database SHA-1 : {databaseSha1}")
            databaseObject = database.getDatabaseFromJSONFile(CONFIG.DATABASE_PATH)
            if databaseObject == None:
                await ctx.send("Failed to load new database.")
                await ctx.send("😡 Update failed !")
                await refresh_status()
                return
            else:
                await ctx.send("Database updated and reloaded successfully !")
                await ctx.send("🥰 Update finished !\n")
                await refresh_status()
                return
        else:
            await ctx.send("Failed to download new database.")
            await ctx.send("😡 Update failed !")
            await refresh_status()
            return
    else:
        await ctx.send("SHA-1 hashes are identical, update is not needed.")
        await ctx.send("🥰 Update finished !\n")
        await refresh_status()

@bot.command(name="reload_db", help="Reload the local copy of the database")
async def reloadDb(ctx):
    databaseObject = database.getDatabaseFromJSONFile(CONFIG.DATABASE_PATH)
    await refresh_status()
    if (databaseObject == None):
        await ctx.send("Reload failed.")
    else:
        await ctx.send("Reload OK.")

@bot.command(name="save_db", help="Save the live database as local copy")
async def saveDb(ctx):
    if not (ctx.message.author.id in SECRETS.WHITELIST):
        await ctx.send("Sorry, but you are not allowed to use this command.")
        return

    global databaseObject
    if databaseObject == None:
        await ctx.send("**No valid database is currently loaded !**")
        return

    dbData = database.getJSONStringFromDatabase(databaseObject).encode("utf-8")
    if dbData == None:
        await ctx.send("Failed to serialize database !")
        await ctx.send("😡 Save failed !")
        return

    updated = await install_new_db(CONFIG.DATABASE_PATH, dbData)
    if not updated:
        await ctx.send("😡 Save failed !")
    else:
        await ctx.send("🥰 Saved database successfully !")
        
@bot.command(name="merge_db", help="Downloads a database and merges it with live database")
async def mergeDb(ctx, database_url : str, overwrite : bool = False):
    if not (ctx.message.author.id in SECRETS.WHITELIST):
        await ctx.send("Sorry, but you are not allowed to use this command.")
        return

    print(f"User {ctx.message.author.name}#{ctx.message.author.discriminator} (ID : {ctx.message.author.id}) requested a database download from {database_url}.")

    global databaseObject, databaseSha1
    if databaseObject == None:
        await ctx.send("**No valid database is currently loaded !**")
        return

    try:
        req = requests.get(database_url)
    except  MissingSchema or InvalidSchema:
        await ctx.send("Illegal URL provided.")
        return

    if req.status_code != 200:
        await ctx.send(f"Failed to download database from `{database_url}` - got HTTP Status {req.status_code}.")
        return

    try:
        jsonStr = str(req.content(), "utf-8")
    except ValueError:
        await ctx.send("URL doesn't point to a valid UTF-8 encoded JSON file.")
        return

    newDb = database.getMergedDbAndJSONString(databaseObject, jsonStr, overwrite)
    if newDb == None:
        await ctx.send("Merging databases failed ! Current database will be left untouched.")
        return

    databaseObject = newDb
    databaseSha1 = SHA1_ALL_ZEROES
    
    sha1ctx = sha1()
    sha1ctx.update(database.getJSONStringFromDatabase(databaseObject).encode("utf-8"))
    databaseSha1 = sha1ctx.hexdigest().lower() #We always store local SHA-1 in lowercase, so we convert just to be sure.
    await ctx.send(f"New SHA-1 hash is `{databaseSha1}`.")

@bot.command(name="download_db", help="Downloads a database and loads it")
async def downloadDb(ctx, database_url : str):
    if not (ctx.message.author.id in SECRETS.WHITELIST):
        await ctx.send("Sorry, but you are not allowed to use this command.")
        return

    print(f"User {ctx.message.author.name}#{ctx.message.author.discriminator} (ID : {ctx.message.author.id}) requested a database download from {database_url}.")

    global databaseObject, databaseSha1
    try:
        req = requests.get(database_url)
    except MissingSchema or InvalidSchema:
        await ctx.send("Illegal URL provided.")
        return

    if req.status_code != 200:
        await ctx.send(f"Failed to download database from `{database_url}` - got HTTP Status {req.status_code}.")
        return
    
    sha1ctx = sha1()
    sha1ctx.update(req.content)
    remoteSha1 = sha1ctx.hexdigest().lower() #We always store local SHA-1 in lowercase, so we convert just to be sure.
    await ctx.send(f"```diff\n- Local database SHA-1 :\n- {databaseSha1}\n+ Downloaded database SHA-1 :\n+ {remoteSha1}\n```")

    if (databaseSha1 != remoteSha1) or databaseObject == None:
        databaseUpdated = await install_new_db(CONFIG.DATABASE_PATH, req.content)
        if databaseUpdated:
            databaseSha1 = remoteSha1
            print(f"New database SHA-1 : {databaseSha1}")
            databaseObject = database.getDatabaseFromJSONFile(CONFIG.DATABASE_PATH)
            if databaseObject == None:
                await ctx.send("Failed to load new database - I am now going to cry 😥")
                await refresh_status()
                return
            else:
                await ctx.send("New database loaded successfully !")
                await refresh_status()
                return
        else:
            await ctx.send("Failed to download new database - current database left untouched.")
            await refresh_status()
            return
    else:
        await ctx.send("SHA-1 hashes are identical - current database will be left untouched.")

@bot.command(name="dump_db", help="Displays a dump of the currently loaded database")
async def dumpDb(ctx):
    global databaseObject
    if databaseObject == None:
        await ctx.send("**No valid database is currently loaded !**")
        return

    await ctx.send("```\n" + database.dumpDatabase(databaseObject) + "```")

@bot.command(name="error_code", aliases=["sce_error", "error"], help="Displays the name of a given error code (in hexadecimal)")
async def errorCode(ctx, input_str : str):
    try:
        errcode = int(input_str, 16)
    except ValueError:
        await ctx.send(f"**`{input_str}` is not a valid input.**")
        return

    if (errcode & 0xFFFFFFFF) != errcode:
        await ctx.send("**Input too long - error codes are only 4 bytes wide.**")
        return

    if (databaseObject == None):
        await ctx.send("**No valid database is currently loaded !**")
    else:
        await ctx.send("```\n" + database.getDecoratedErrorCodeInfo(databaseObject, errcode) + "\n```")

@bot.command(name="dump_db_json", help="Displays a JSON bot-parsable dump of the current database")
async def dumpDbJson(ctx):
    if not (ctx.message.author.id in SECRETS.WHITELIST):
        await ctx.send("Sorry, but you are not allowed to use this command.")
        return

    print(f"User {ctx.message.author.name}#{ctx.message.author.discriminator} (ID : {ctx.message.author.id}) requested a database dump.")

    global databaseObject
    if databaseObject == None:
        await ctx.send("**No valid database is currently loaded !**")
        return

    s = database.getJSONStringFromDatabase(databaseObject)
    if s != None:
        await ctx.send("```json\n" + s + "\n```")
    else:
        await ctx.send("Failed to serialize database.")

@bot.command(name="exit", help="Stops the bot")
async def exit(ctx):
    if not (ctx.message.author.id in SECRETS.WHITELIST):
        await ctx.send("Sorry, but you are not allowed to use this command.")
        return

    print(f"User {ctx.message.author.name}#{ctx.message.author.discriminator} (ID : {ctx.message.author.id}) requested to stop the bot.")

    await ctx.send("Exiting...")
    await bot.change_presence(activity=discord.Game("Busy"), status=discord.Status.dnd)
    os.abort()

#Launch bot
bot.run(SECRETS.TOKEN)