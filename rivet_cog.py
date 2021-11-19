import os
import discord
from hashlib import sha1
from discord.ext import commands
from dataclasses import dataclass
from re import findall as regexp_findall
from requests import get as make_http_request
from requests.exceptions import MissingSchema, InvalidSchema, HTTPError

import errorsDatabase
from shortCodesDatabase import SCDatabase
import SECRETS #WHITELIST

SHA1_ALL_ZEROES =  "0000000000000000000000000000000000000000"

@dataclass
class ErrDBHolder:
    sha1 : str
    localPath : str
    remotePath : str
    databaseObject : errorsDatabase.Database

@dataclass
class SCDBHolder:
    localPath : str
    remotePath : str
    databaseObject : SCDatabase

@dataclass
class RivetCogInitParam:
    apiTarget : int                 #One of the APIContractor.REMOTE_API_TARGET - which website the online repository is
    remoteRepositoryURL : str       #URL to the repository where the databases are located
    errorsDB_localPath : str        #Local path where the errors database should be stored
    errorsDB_remotePath : str       #Path on the remote repository where the errors database is stored
    shortCodesDB_localPath : str    #Local path where the short codes database should be stored
    shortCodesDB_remotePath : str   #Path on the remote repository where the short codes database is stored

async def _getSha1OfData(data : bytes) -> str:
    sha1Ctx = sha1()
    sha1Ctx.update(data)
    return sha1Ctx.hexdigest().lower()

async def _getSha1OfFile(path : str) -> str:
    try:
        fh = open(path, "rb")
    except IOError:
        return None
    ret = _getSha1OfData(fh.read())
    fh.close()
    return ret

def _getSha1OfDataSync(data : bytes) -> str:
    sha1Ctx = sha1()
    sha1Ctx.update(data)
    return sha1Ctx.hexdigest().lower()

def _getSha1OfFileSync(path : str) -> str:
    try:
        fh = open(path, "rb")
    except IOError:
        return None
    ret = _getSha1OfDataSync(fh.read())
    fh.close()
    return ret

async def isWhitelisted(ctx):
    return ctx.author.id in SECRETS.WHITELIST

#This class wraps the API requests in generic methods
#This allows you to use a non-GitHub service for the database
#Implementation of such methods is left over to the reader
class APIContractor:
    __slots__ = ["apiUrl", "apiTarget"]

    REMOTE_API_TARGET_INVALID = -1
    REMOTE_API_TARGET_GITHUB = 0

    def __generateApiUrlForGitHub(self, repoUrl : str) -> str :
        s = regexp_findall("^https://github.com/([a-zA-Z0-9_\-.]+/[a-zA-Z0-9_\-.]+)/?$", repoUrl)
        if (len(s) != 1):
            raise ValueError(f"Couldn't generate API URL from provided GitHub repository URL '{repoUrl}' !")
        else:
            return "https://api.github.com/repos/" + s[0] + "/"

    #Can raise ValueError if the apiTarget is invalid
    def __init__(self, remoteUrl : str, apiTarget : int = REMOTE_API_TARGET_GITHUB) -> None:
        self.apiTarget : int = apiTarget
        if (self.apiTarget == self.REMOTE_API_TARGET_GITHUB):
            self.apiUrl = self.__generateApiUrlForGitHub(remoteUrl)
        else:
            self.apiTarget = self.REMOTE_API_TARGET_INVALID
            raise ValueError("Unknown API target !")

    #May raise a HTTPError or ValueError or FileNotFoundError in case something goes wrong : print exception.args[0] in such cases
    def getContentOfFileAtPath(self, remotePath : str) -> bytes:
        if (self.apiTarget == self.REMOTE_API_TARGET_GITHUB):
            #We need to get content of the folder our database is in
            #Everything before the last / are folders, everything after is the filename
            slashIdx = remotePath.rfind("/")
            if slashIdx == -1: #No / found
                remoteDbName = remotePath
                apiRequestURL = self.apiUrl + "contents/"
            else:
                remoteDbName = remotePath[slashIdx + 1:] #+1 to skip the /
                apiRequestURL = self.apiUrl + f"contents/{remotePath[:slashIdx]}"

            req = make_http_request(apiRequestURL, headers={"Accept": "application/vnd.github.v3+json"})
            if req.status_code != 200:
                raise HTTPError(f"Failed to fetch API (`{apiRequestURL}` - got HTTP Status {req.status_code}.")

            try:
                jsonData = req.json()
            except ValueError:
                raise ValueError(f"Failed to decode API response as JSON :\n{req.content}")

            downloadURL = None

            for data in jsonData:
                filename = data.get('name')
                if filename == None or filename != remoteDbName:
                    continue
                else:
                    downloadURL = data.get("download_url")
                    break

            if downloadURL == None:
                raise FileNotFoundError(f"Failed to find file `{remoteDbName}` on remote repository.")
        
            req = make_http_request(downloadURL)
            if req.status_code != 200:
                raise HTTPError(f"Failed to download file from remote - got HTTP Status {req.status_code}.")
            
            return req.content
        else: #Not a known target
            raise ValueError("Unknown API target !")

class RivetCog(APIContractor, commands.Cog):
    __slots__ = ["bot", "errorsDB", "shortCodesDB", "whitelist"]

    #Returns True if loading the local databases went fine, False otherwise - may raise ValueError
    def __init__(self, bot, initParams : RivetCogInitParam) -> None:
        APIContractor.__init__(self, initParams.remoteRepositoryURL, initParams.apiTarget)
        self.bot = bot
        self.errorsDB : ErrDBHolder = ErrDBHolder(SHA1_ALL_ZEROES, initParams.errorsDB_localPath, initParams.errorsDB_remotePath, None)
        self.shortCodesDB : SCDBHolder = SCDBHolder(initParams.shortCodesDB_localPath, initParams.shortCodesDB_remotePath, SCDatabase())

        #Load local databases
        self.errorsDB.databaseObject = errorsDatabase.getDatabaseFromJSONFile(self.errorsDB.localPath)
        self.errorsDB.sha1 = _getSha1OfFileSync(self.errorsDB.localPath)

        self.shortCodesDB.databaseObject.LoadFromFile(self.shortCodesDB.localPath)

    #Returns True if the update went fine, False otherwise
    async def __installLocalDatabase(self, localPath : str, fileContent : bytes) -> bool:
        try: #Backup current db to {NAME}.old
            os.remove(localPath + ".old")
            os.rename(localPath, localPath + ".old")
        except FileNotFoundError:
            pass
        try:
            fh = open(localPath, "wb")
            fh.write(fileContent)
            fh.close()
            return True
        except IOError:
            print(f"IOError raised when operating on '{localPath}'.")
            return False

    async def __updateErrorsDatabase(self, ctx) -> None:
        exceptionRaised = False
        try:
            remoteDB = APIContractor.getContentOfFileAtPath(self, self.errorsDB.remotePath)
        except HTTPError as e:
            await ctx.send(e.args[0])
            exceptionRaised = True
        except ValueError as e:
            await ctx.send(e.args[0])
            exceptionRaised = True
        except FileNotFoundError as e:
            await ctx.send(e.args[0])
            exceptionRaised = True
        finally:
            if exceptionRaised:
                await ctx.send("❌ Update of errors database failed !")
                return

        sha1Ctx = sha1()
        sha1Ctx.update(remoteDB)
        remoteDBSha1 = sha1Ctx.hexdigest().lower() #We always store local SHA-1 in lowercase, so we convert just to be sure.
        await ctx.send(f"```diff\n- Local database SHA-1 :\n- {self.errorsDB.sha1}\n+ Repository database SHA-1 :\n+ {remoteDBSha1}\n```")

        updateFailed = False
        if (self.errorsDB.sha1 != remoteDBSha1) or self.errorsDB.databaseObject == None: #Force update if currently loaded DB is invalid
            if await self.__installLocalDatabase(self.errorsDB.localPath, remoteDB):
                self.errorsDB.sha1 = remoteDBSha1
                print(f"New errors database SHA-1 : {self.errorsDB.sha1}")
                self.errorsDB.databaseObject = errorsDatabase.getDatabaseFromJSONFile(self.errorsDB.localPath)
                if self.errorsDB.databaseObject == None:
                    await ctx.send("Failed to load new errors database.")
                    updateFailed = True
                else:
                    await ctx.send("🥰 Database updated and reloaded successfully !")
            else:
                await ctx.send("Failed to download new database.")
                updateFailed = True
        else:
            await ctx.send("SHA-1 hashes are identical, update is not needed.")
            
        if updateFailed:
            await ctx.send("❌ Update of errors database failed !")
    
    async def __updateShortCodesDatabase(self, ctx) -> None:
        exceptionRaised = False
        try:
            remoteDB = APIContractor.getContentOfFileAtPath(self, self.shortCodesDB.remotePath)
        except HTTPError as e:
            await ctx.send(e.args[0])
            exceptionRaised = True
        except ValueError as e:
            await ctx.send(e.args[0])
            exceptionRaised = True
        except FileNotFoundError as e:
            await ctx.send(e.args[0])
            exceptionRaised = True
        finally:
            if exceptionRaised:
                await ctx.send("❌ Update of short codes database failed !")
                return

        sha1Ctx = sha1()
        sha1Ctx.update(remoteDB)
        remoteDBSha1 = sha1Ctx.hexdigest().lower() #We always store local SHA-1 in lowercase, so we convert just to be sure.
        localSha1 = self.shortCodesDB.databaseObject.GetDBSha1()
        await ctx.send(f"```diff\n- Local database SHA-1 :\n- {localSha1}\n+ Repository database SHA-1 :\n+ {remoteDBSha1}\n```")

        updateFailed = False
        if (localSha1 != remoteDBSha1) or self.shortCodesDB.databaseObject == None: #Force update if currently loaded DB is invalid
            if await self.__installLocalDatabase(self.shortCodesDB.localPath, remoteDB):
                print(f"New database SHA-1 should be {remoteDBSha1}.")
                if not self.shortCodesDB.databaseObject.LoadFromFile(self.shortCodesDB.localPath):
                    await ctx.send("Failed to load new database.")
                    updateFailed = True
                else:
                    await ctx.send("🥰 Database updated and reloaded successfully !")
                    print(f"New database SHA-1 (from object) is {self.shortCodesDB.databaseObject.GetDBSha1()}.")
            else:
                await ctx.send("Failed to download new database.")
                updateFailed = True
        else:
            await ctx.send("SHA-1 hashes are identical, update is not needed.")
            
        if updateFailed:
            await ctx.send("❌ Update of short codes database failed !")

    async def refreshStatus(self) -> None:
        if self.errorsDB.databaseObject == None:
            if self.shortCodesDB.databaseObject.IsValidDatabaseLoaded():
                game = discord.Game(name="Errors database is broken")
                status = discord.Status.dnd
            else:
                game = discord.Game(name="Both databases are broken")
                status = discord.Status.dnd
        elif not self.shortCodesDB.databaseObject.IsValidDatabaseLoaded():
            game = discord.Game(name="Short codes database is broken")
            status = discord.Status.idle
        else:
            game = discord.Game(name="resolving PS Vita error codes !")
            status = discord.Status.online
        await self.bot.change_presence(activity=game, status=status)

    @commands.command(name="update_db", aliases=["refresh", "refresh_db"], help="Update the databases of the bot")
    @commands.check(isWhitelisted)
    async def updateDB(self, ctx):
        print(f"User {ctx.message.author.name}#{ctx.message.author.discriminator} (ID : {ctx.message.author.id}) initiated a database update.")
        await ctx.send("Updating errors database...")
        await self.__updateErrorsDatabase(ctx)
        await ctx.send("Updating short codes database...")
        await self.__updateShortCodesDatabase(ctx)
        await self.refreshStatus()
        
    @commands.command(name="reload_db", help="Reload the local copies of the databases")
    async def reloadDB(self, ctx):
        self.errorsDB.databaseObject = errorsDatabase.getDatabaseFromJSONFile(self.errorsDB.localPath)
        self.errorsDB.sha1 = _getSha1OfFile(self.errorsDB.localPath)
        if self.errorsDB.databaseObject == None:
            await ctx.send("Failed to reload errors database.")
        else:
            await ctx.send("Errors database reloaded successfully.")

        self.shortCodesDB.databaseObject.LoadFromFile(self.shortCodesDB.localPath)
        if not self.shortCodesDB.databaseObject.IsValidDatabaseLoaded():
            await ctx.send("Failed to reload short codes database.")
        else:
            await ctx.send("Short codes database reloaded successfully.")
        await self.refreshStatus()

    @commands.command(name="save_db", help="Save the live databases as local copy")
    @commands.check(isWhitelisted)
    async def saveDB(self, ctx):
        errDBData = errorsDatabase.getJSONStringFromDatabase(self.errorsDB.databaseObject).encode("utf-8")
        if errDBData == None:
            await ctx.send("Failed to serialize errors database !")
 
        if errDBData and await self.__installLocalDatabase(self.errorsDB.localPath, errDBData):
            await ctx.send("🥰 Saved errors database successfully !")
        else:
            await ctx.send("😡 Save of errors database failed !")

        shortCodesDBData = self.shortCodesDB.databaseObject.GetDatabaseAsString()
        if shortCodesDBData == None:
            await ctx.send("Failed to serialize short codes database !")
 
        if shortCodesDBData and await self.__installLocalDatabase(self.errorsDB.localPath, errDBData):
            await ctx.send("🥰 Saved short codes database successfully !")
        else:
            await ctx.send("😡 Save of short codes database failed !")

    @commands.command(name="merge_err_db", help="Downloads an errors database and merges it with live database")
    @commands.check(isWhitelisted)
    async def mergeDB(self, ctx, databaseURL : str, overwrite : bool = False):
        print(f"User {ctx.message.author.name}#{ctx.message.author.discriminator} (ID : {ctx.message.author.id}) requested a database merge from {databaseURL}.")

        if self.errorsDB.databaseObject == None:
            await ctx.send("No valid errors database is currently loaded.")
            return

        try:
            req = make_http_request(databaseURL)
        except MissingSchema or InvalidSchema:
            await ctx.send("Illegal URL provided.")
            return

        if req.status_code != 200:
            await ctx.send(f"Failed to download database - got HTTP Status {req.status_code}.")
            return

        try:
            jsonStr = str(req.content(), "utf-8")
        except ValueError:
            await ctx.send("URL doesn't point to a valid UTF-8 encoded JSON file.")
            return

        newDb = errorsDatabase.getMergedDbAndJSONString(self.errorsDB.databaseObject, jsonStr, overwrite)
        if newDb == None:
            await ctx.send("Merging databases failed ! Current database will be left untouched.")
            return

        self.errorsDB.databaseObject = newDb
        self.errorsDB.sha1 = SHA1_ALL_ZEROES

        sha1ctx = sha1()
        sha1ctx.update(errorsDatabase.getJSONStringFromDatabase(self.errorsDB.databaseObject).encode("utf-8"))
        self.errorsDB.sha1 = sha1ctx.hexdigest().lower() #We always store local SHA-1 in lowercase, so we convert just to be sure.
        await ctx.send(f"New SHA-1 hash is `{self.errorsDB.sha1}`.")

    @commands.command(name="download_err_db", help="Download an errors database and replaces the live database with it")
    @commands.check(isWhitelisted)
    async def downloadDB(self, ctx, databaseURL : str):
        print(f"User {ctx.message.author.name}#{ctx.message.author.discriminator} (ID : {ctx.message.author.id}) requested a database download from {databaseURL}.")
        try:
            req = make_http_request(databaseURL)
        except MissingSchema or InvalidSchema:
            await ctx.send("Illegal URL provided.")
            return

        if req.status_code != 200:
            await ctx.send(f"Failed to download database - got HTTP Status {req.status_code}.")
            return

        sha1ctx = sha1()
        sha1ctx.update(req.content)
        remoteSha1 = sha1ctx.hexdigest().lower() #We always store local SHA-1 in lowercase, so we convert just to be sure.
        await ctx.send(f"```diff\n- Local database SHA-1 :\n- {self.errorsDB.sha1}\n+ Downloaded database SHA-1 :\n+ {remoteSha1}\n```")

        if (self.errorsDB.sha1 != remoteSha1) or self.errorsDB.databaseObject == None:
            if self.__installLocalDatabase(ctx, self.errorsDB.localPath, req.content):
                self.errorsDB.databaseObject = errorsDatabase.getDatabaseFromJSONFile(self.errorsDB.localPath)
                self.errorsDB.sha1 = remoteSha1
                if self.errorsDB.databaseObject == None:
                    await ctx.send("Failed to load new database - I am now going to cry 😥")
                else:
                    await ctx.send("New database loaded successfully !")
                    print(f"New database SHA-1 : {self.errorsDB.sha1}")
            else:
                await ctx.send("Failed to download new database - current database left untouched.")
        else:
            await ctx.send("SHA-1 hashes are identical - current database will be left untouched.")
        await self.refreshStatus()

    @commands.command(name="error_code", aliases=["sce_error", "error", "ec"], help="Displays the name of a given error code (in hexadecimal or short code)")
    async def resolveErrorCode(self, ctx, input_str : str):
        printStr = "```\n"
        try:
            errcode = int(input_str, 16)
        except ValueError:
            if (self.shortCodesDB.databaseObject == None) or not self.shortCodesDB.databaseObject.IsValidDatabaseLoaded():
                await ctx.send("No valid short error codes database is currently loaded : cannot try to resolve.")
                return

            short_code = input_str.upper() #Our DB stores short codes in uppercase - we need to make input uppercase for matching to work
            errcode = self.shortCodesDB.databaseObject.ResolveShortCode(short_code)
            if errcode == 0:
                await ctx.send(f"`{input_str}` is an unknown short code or an invalid input.")
                return
            else:
		#Found a match - print which hex code this short code maps to, and process hex code
                printStr += f"Short code {short_code} -> 0x{errcode:08X}\n"
        if (errcode & 0xFFFFFFFF) != errcode:
            await ctx.send("Input too long - error codes are only 4 bytes wide.")
            return



        if (self.errorsDB.databaseObject == None):
            await ctx.send("No valid errors database is currently loaded.")
        else:
            await ctx.send(printStr + errorsDatabase.getDecoratedErrorCodeInfo(self.errorsDB.databaseObject, errcode) + "\n```")

    @commands.command(name="exit", help="Stops the bot")
    @commands.check(isWhitelisted)
    async def exit(self, ctx):
        print(f"User {ctx.message.author.name}#{ctx.message.author.discriminator} (ID : {ctx.message.author.id}) requested to stop the bot.")

        await ctx.send("Exiting...")
        await self.bot.change_presence(activity=discord.Game("Busy"), status=discord.Status.dnd)
        os._exit(0)
    
    async def cog_command_error(self, ctx, error):
        print(f"In cog_command_error : \n{error}")
        await ctx.send(f"Error while running command :\n```\n{error}\n```")