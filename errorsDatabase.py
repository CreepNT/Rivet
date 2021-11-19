import gc
import json
from hashlib import sha1
from dataclasses import dataclass
from typing import NewType, Dict, List

#Database format :
# The database is a dictionnary which maps a FACILITY code (int) to a Facility.
# 
# A Facility is a dict() which contains the following :
#   - a mandatory 'name' key (str)
#   - an optional 'description' key (str)
#   - an optional 'blacklist' key (array of Blacklist), which stores which ranges of error codes are known to be invalid/non-existent
#   - a mandatory 'errors' key (dict), which maps a FACILITY ERROR code (int) to an Error
#       - this dictionnary may be empty, if a facility name is known, but no error codes associated to it
#
# A Blacklist is a dict() which contains the following :
#   - a mandatory 'min' key (int) : first value of this range of the blacklist
#   - a mandatory 'max' key (int) : last value of this range of the blacklist
# All values x such that min <= x <= max are considered as invalid error codes.
#
# An Error is a dict() which contains the following :
#   - a mandatory 'name' key (str)
#   - an optional 'description' key (str)
#
# This format was chosen to mimic a JSON structure.
# Note that in JSON, keys CANNOT be intergers, so a JSON->db parsing is required first.
# See createDbFromJSON() for more info.
#

DESCRIPTION_KEY = 'description'
BLACKLIST_KEY = 'blacklist'
ERRORS_KEY = 'errors'
NAME_KEY = 'name'
MIN_KEY = 'min'
MAX_KEY = 'max'

BASE_HEX = 16

IS_ERROR_MASK       = 0x80000000 #1 if this is an error code, 0 otherwise.
IS_FATAL_MASK       = 0x40000000 #1 if this is a fatal error, 0 otherwise.
RESERVED_MASK       = 0x30000000 #Always 0.
FACILITY_MASK       = 0x0FFF0000 #Facility identifier
ERROR_NUM_MASK     = 0x0000FFFF #Error code identifier from facility


@dataclass
class Error:
    name : str
    description : str

@dataclass
class BlacklistEntry:
    min : int
    max : int

@dataclass
class Facility:
    name : str
    description : str
    blacklist : List[BlacklistEntry]
    errors : Dict[int, Error]

Database = NewType('Database', Dict[int, Facility])


#Can this be a taiHEN error code ?
#Code by Princess of Sleeping
def isTaiHENErrorCode(error_code : int) -> bool: 
    return (0 <= (error_code - 0x90010000) <= 0xD)

#Get the name of a taiHEN error.
def getTaiHENErrorName(taiErrCode : int) -> str:
    taiHenErrors = [
        "TAI_ERROR_SYSTEM",              #0x90010000
        "TAI_ERROR_MEMORY",              #0x90010001
        "TAI_ERROR_NOT_FOUND",           #0x90010002
        "TAI_ERROR_INVALID_ARGS",        #0x90010003
        "TAI_ERROR_INVALID_KERNEL_ADDR", #0x90010004
        "TAI_ERROR_PATCH_EXISTS",        #0x90010005
        "TAI_ERROR_HOOK_ERROR",          #0x90010006
        "TAI_ERROR_NOT_IMPLEMENTED",	 #0x90010007
        "TAI_ERROR_USER_MEMORY",	 #0x90010008
        "TAI_ERROR_NOT_ALLOWED",         #0x90010009
        "TAI_ERROR_STUB_NOT_RESOLVED",   #0x9001000A
        "TAI_ERROR_INVALID_MODULE",      #0x9001000B
        "TAI_ERROR_MODULE_OVERFLOW",     #0x9001000C
        "TAI_ERROR_BLOCKING"             #0x9001000D
    ]
    return taiHenErrors[taiErrCode & ERROR_NUM_MASK]

#Returns the name of a facility given its number, or a placeholder string if the facility is unknown
def getFacilityName(db : Database, facilityNum : int) -> str:
    facility = db.get(facilityNum)
    if (facility != None):
        return facility.name
    else:
        return "Unknown facility (0x%03X)" % (facilityNum)

#Returns the description of a facility given its number, or None if the facility doesn't have one or is unknown
def getFacilityDescription(db : Database, facilityNum : int) -> str:
    facility = db.get(facilityNum)
    if (facility != None):
        return facility.description
    else:
        return None

#Returns true if the error number is in the facility's blacklist, false otherwise.
def isErrorBlacklisted(db: Database, facilityNum : int, errorNum : int) -> bool:
    facility = db.get(facilityNum)
    if (facility != None):
        for blacklistRange in facility.blacklist:
            if blacklistRange.min <= errorNum <= blacklistRange.max:
                return True
    return False

#Returns the name of an error given the facility it belongs to and its number, or a placeholder string if either facility or error is unknown, or None if the error is blacklisted
def getErrorName(db : Database, facilityNum : int, errorNum : int) -> str:
    facility = db.get(facilityNum)
    if (facility != None):
        error = facility.errors.get(errorNum)
        if (error != None):
            return error.name
        elif isErrorBlacklisted(db, facilityNum, errorNum):
            return None
    
    return "Unknown error code (0x%04X)" % (errorNum)

#Returns the name of an error given the facility it belongs to and its number, or None if either facility or error is unknown, or the error is blacklisted
def getErrorDescription(db : Database, facilityNum : int, errorNum : int) -> str:
    facility = db.get(facilityNum)
    if (facility != None):
        error = facility.errors.get(errorNum)
        if (error != None):
            return error.description
        #Note - we don't need to check the blacklist for the description, because a blacklisted entry has by definition no description
    return None

#Get the name of the facility who emitted an error code
def getFacilityNameFromErrorCode(db : Database, error_code : int) -> str:
    return getFacilityName(db, (error_code & FACILITY_MASK) >> 16)

#Returns the description of a facility, or None if the facility doesn't have one or doesn't exist
def getFacilityDescriptionFromErrorCode(db : Database, error_code : int) -> str:
    return getFacilityDescription(db, (error_code & FACILITY_MASK) >> 16)

#Get the name of the error from a code
def getErrorNameFromErrorCode(db : Database, error_code : int) -> str:
    return getErrorName(db, (error_code & FACILITY_MASK) >> 16, error_code & ERROR_NUM_MASK)

#Get the description of the error from a code
def getErrorDescriptionFromErrorCode(db : Database, error_code : int) -> str:
    #No special cases for taiHEN, because there are no descriptions for taiHEN errors.
    return getErrorDescription(db, (error_code & FACILITY_MASK) >> 16, error_code & ERROR_NUM_MASK)

#Returns true if the error code is blacklisted (known invalid).
def isErrorCodeBlacklisted(db : Database, error_code : int) -> bool:
    return isErrorBlacklisted(db, (error_code & FACILITY_MASK) >> 16, error_code & ERROR_NUM_MASK)

#Can this integer be a valid SceUID ?
#Code by Princess of Sleeping
def canBeSceUID(code : int) -> bool:
    if((code & 0xF0000000) == 0x40000000) and ((code & 0xF0000) != 0) and ((code & 1) == 1):
        return True
    else:
        return False

#Returns a formated string containing information about an error code - looking like following :
# Facility : FACILITY_NAME (description if avaliable) / Unknown facility (facility number)
# Error code : ERROR_CODE_NAME / Unknown error code (error code)
# Error description : (only if avaliable)
# Fatal : Yes/No
def getDecoratedErrorCodeInfo(db : Database, error_code : int) -> str:
    if isTaiHENErrorCode(error_code): #This check is needed first, because taiHEN violates the error code convention (on purpose ?)
        ret = "Facility : taiHEN (taiHEN framework)\n"
        ret += f"Error code : {getTaiHENErrorName(error_code)}\n"
        ret += "Fatal : No"
        return ret

    if not (error_code & IS_ERROR_MASK):
        if canBeSceUID(error_code):
            return "Not an error code - may be a SceUID."
        else:
            return "Error bit not set - not an error code."
    
    if (error_code & RESERVED_MASK) != 0:
        return "Reserved bits not clear - not an error code."

    if isErrorCodeBlacklisted(db, error_code):
        return "Illegal error code."

    fatal = (error_code & IS_FATAL_MASK)
    
    ret = "Facility : " + getFacilityNameFromErrorCode(db, error_code)
    facDesc = getFacilityDescriptionFromErrorCode(db, error_code)
    if facDesc != None:
        ret += f" ({facDesc})\n"
    else:
        ret += "\n"
    
    ret += "Error code : " + getErrorNameFromErrorCode(db, error_code) + "\n"
    errDesc = getErrorDescriptionFromErrorCode(db, error_code)
    if errDesc != None:
        ret += f"Error description : {errDesc}\n"
    
    if fatal:
        ret += "Fatal : Yes"
    else:
        ret += "Fatal : No"
    return ret

#Print the content of a Database to stdout
def dumpDatabase(db : Database) -> str:
    ret = f"Number of facilities : {len(db)}\n"
    for facility_num, facility_obj in db.items():
        ret += " Facility #0x%03X :\n" % facility_num
        ret += f"  - Name : {facility_obj.name}\n"
        ret += f"  - Description : {facility_obj.description}\n" #None if there is no description
        ret += f"  - Number of blacklisted ranges : {len(facility_obj.blacklist)}\n"
        for blacklist in facility_obj.blacklist:
            ret += f"    -> [{blacklist.max} - {blacklist.max}]\n"
        ret += f"  - Number of errors : {len(facility_obj.errors)}\n"
        for errorNum, errorObj in facility_obj.errors.items():
            ret += "    Error 0x%04X :\n" % errorNum
            ret += f"     - Name : {errorObj.name}\n"
            ret += f"     - Description : {errorObj.description}\n"
    return ret

#Get a json.dumps()'able dict from a database.
def getJSONReadyDictFromDatabase(db : Database) -> dict:
    tmpDb = {}
    for facilityNum, facilityObj in db.items():
        facilityJSON = {NAME_KEY : facilityObj.name, ERRORS_KEY : {}}

        if len(facilityObj.blacklist) != 0:
            blacklist = []
            for blEntry in facilityObj.blacklist:
                blE = {MIN_KEY : "0x%04X" % blEntry.min, MAX_KEY : "0x%04X" % blEntry.max}
                blacklist.append(blE)
            facilityJSON[BLACKLIST_KEY] = blacklist
        
        for errorNum, errorObj in facilityObj.errors.items():
            facilityJSON[ERRORS_KEY]["0x%04X" % errorNum] = {NAME_KEY : errorObj.name}
            if errorObj.description != None:
                facilityJSON[ERRORS_KEY]["0x%04X" % errorNum][DESCRIPTION_KEY] = errorObj.description
        
        tmpDb["0x%03X" % facilityNum] = facilityJSON

    return tmpDb

#Get a JSON string containing a serialized database
def getJSONStringFromDatabase(db : Database) -> str:
    try:
        return json.dumps(getJSONReadyDictFromDatabase(db))
    except Exception as e:
        print(f"Exception {e.__class__.__name__} raised while json.dumps()'ing.")
        return None

#Parses a JSON database into a Database object. Returns None on failure.
def getDatabaseFromJSONString(s : str) -> Database:
    try:
        initDict = json.loads(s)
    except json.JSONDecodeError:
        print("Exception raised while decoding JSON object.")
        return None
    
    db = dict()

    try:
        for facility_code_str, facility_obj in initDict.items():
            #Build errors
            facilityErrors = dict()
            for error_code_str, error_obj in facility_obj[ERRORS_KEY].items():
               errorCode = int(error_code_str, BASE_HEX) #convert str->int
               errorDescription = error_obj.get(DESCRIPTION_KEY) #None if there is no desription
               facilityErrors[errorCode] = Error(name = error_obj[NAME_KEY], description = errorDescription)

            #Build blacklist
            facilityBlacklist = list()
            facility_obj_blacklist = facility_obj.get(BLACKLIST_KEY)
            if facility_obj_blacklist != None:
                for blacklistRange in facility_obj_blacklist:
                    blMin = int(blacklistRange[MIN_KEY], BASE_HEX)
                    blMax = int(blacklistRange[MAX_KEY], BASE_HEX)
                    facilityBlacklist.append(BlacklistEntry(min = blMin, max = blMax))

            facilityDescription = facility_obj.get(DESCRIPTION_KEY) #None if there is no description
            facilityCode = int(facility_code_str, BASE_HEX) #convert str->int

            #Build Facility object
            db[facilityCode] = Facility(name = facility_obj[NAME_KEY], description = facilityDescription, 
                blacklist = facilityBlacklist, errors = facilityErrors)
        
        ret = Database(db)

    except Exception as e:
        print(f"OUCH !\nException {e.__class__.__name__} caught while building Database object.")
        exit(0)
        ret = None

    finally:
        del initDict
        gc.collect() #Free initDict (and ret if it was discarded)
        return ret

#Returns merged database on success, None otherwise. Set overwrite to True if fields from appendedDb should overwrite those already present in dstDb.
def getMergedDatabases(destDb : Database, appendedDb : Database, overwrite : bool = False) -> Database:
    if appendedDb == None or destDb == None:
        return None
    else:
        for curFacilityNum, appendedDbFacility in appendedDb.items():
            if destDb.get(curFacilityNum) != None: #Facility exists in DB we append to - merge fields
                #Merge names
                if overwrite:
                    destDb[curFacilityNum].name = appendedDbFacility.name

                #Merge descriptions
                if (destDb[curFacilityNum].description == None or overwrite) and appendedDbFacility.description != None:
                    destDb[curFacilityNum].description = appendedDbFacility.description

                #Merge blacklists
                if not overwrite: #Overwrite-less, we make existing ranges bigger
                    for appendedBlacklistRange in appendedDbFacility.blacklist: #Yes, this is probably O(n^2). Deal with it.
                        i = 0
                        for dstBlacklistRange in destDb[curFacilityNum].blacklist:
                            if (appendedBlacklistRange.min < dstBlacklistRange.min) and (appendedBlacklistRange.max > dstBlacklistRange.max):
                                destDb[curFacilityNum].blacklist[i].min = appendedBlacklistRange.min
                                destDb[curFacilityNum].blacklist[i].max = appendedBlacklistRange.max
                else: #Overwrite old blacklist - technically not a merge, but it *should* be fine
                    destDb[curFacilityNum].blacklist = appendedDbFacility.blacklist

                #Merge errors
                for appendedErrorNum, appendedErrorObj in appendedDbFacility.errors.items():
                    if destDb[curFacilityNum].errors.get(appendedErrorNum) == None: #Error doesn't exist
                        destDb[curFacilityNum].errors[appendedErrorNum] = appendedErrorObj
                        continue

                    elif overwrite: #Else, if we overwrite, then copy name field
                        destDb[curFacilityNum].errors[appendedErrorNum].name = appendedErrorObj.name

                    #Then copy description, if it exists and we need to
                    if (destDb[curFacilityNum].errors[appendedErrorNum].description == None or overwrite) and appendedErrorObj.description != None: 
                        destDb[curFacilityNum].errors[appendedErrorNum].description = appendedErrorObj.description

            else: #Facility doesn't exist, just add it
                destDb[curFacilityNum] = appendedDbFacility

        return destDb

#Returns merged Database on success, None otherwise. Set overwrite to True if fields from appendedDb should overwrite those already present in dstDb.
def getMergedDbAndJSONString(dstDb : Database, appendedDbJSON : str, overwrite : bool = False) -> Database:
    appendedDb = getDatabaseFromJSONString(appendedDbJSON)
    ret = getMergedDatabases(dstDb, appendedDb, overwrite)
    
    del appendedDb
    gc.collect() #Ensure that temporary database is free'd from memory, since we don't need it anymore

    return ret
    
#Returns merged Database on success, None otherwise. Set overwrite to True if fields from the appended Database should overwrite those already present in dstDb.
def getMergedDbAndJSONFile(dstDb : Database, appendedDbFilePath : str, overwrite : bool = False) -> Database:
    try:
        fh = open(appendedDbFilePath, "r")
    except IOError:
        print(f"Failed to open {appendedDbFilePath} for reading.")
        return None

    appendDbData = fh.read()
    fh.close()
    ret = getMergedDbAndJSONString(dstDb, appendDbData, overwrite)

    del appendDbData
    gc.collect() #Ensure that file contents are free'd from memory, since we don't need them anymore

    return ret

#Returns a Database object and the SHA-1 sum of the database file on success, None otherwise.
def getDatabaseFromJSONFile(dbFilePath : str) -> Database:
    try:
        fh = open(dbFilePath, "r")
    except IOError:
        print(f"Failed to open '{dbFilePath}' for reading.")
        return None

    dbData = fh.read()
    fh.close()
    dbObj = getDatabaseFromJSONString(dbData)

    del dbData
    gc.collect() #Ensure that file contents are free'd from memory, since we don't need them anymore

    return dbObj
    