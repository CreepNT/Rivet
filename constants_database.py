import json
import gc
from os import error

#Database format :
# The database is a dictionnary which maps a FACILITY code (int) to a Facility.
# 
# A Facility is a dict() which contains the following :
#   - a mandatory 'name' key (str)
#   - an optional 'description' key (str)
#   - a mandatory 'errors' key (dict), which maps a FACILITY ERROR code (int) to an Error
#       - this dictionnary may be empty, if a facility name is known, but no error codes associated to it
#
# An Error is a dict() which contains the following :
#   - a mandatory 'name' key (str)
#   - an optional 'description' key (str)
#
# This format was chosen to mimic a JSON structure.
# Note that in JSON, keys CANNOT be intergers, so a JSON->db parsing is required first.
# See createDbFromJSON() for more info.
#

def getErrorCodeName(db : dict, error_code : int) -> str:
    facility_num = (error_code & FACILITY_MASK) >> 16
    error_num = error_code & ERROR_CODE_MASK

    facility_obj = db.get(facility_num, None)
    if (facility_obj != None):
        errors_obj = facility_obj['errors'].get(error_num)
        if (errors_obj != None):
            ret = "Error code : " + errors_obj['name']
            desc = errors_obj.get('description', None)
            if (desc != None):
                ret += "\nError description : " + desc
            return ret

    return "Unknown error code (0x%04X)" % error_num


def getFacilityName(db : dict, error_code : int) -> str:
    facility_num = (error_code & FACILITY_MASK) >> 16
    facility_obj = db.get(facility_num, None)
    if (facility_obj != None):
        ret = "Facility : " + facility_obj['name']
        desc = facility_obj.get('description', None)
        if desc != None:
            ret += " (" + desc + ")"
        return ret
    else:
        return "Unknown facility (0x%03X)" % (facility_num)

#Get the name of a taiHEN error.
def getErrorNameForTaiHENFacility(taiErrCode : int) -> str:
    taiHenErrors = [
        "TAI_ERROR_SYSTEM",
        "TAI_ERROR_MEMORY",
        "TAI_ERROR_NOT_FOUND",
        "TAI_ERROR_INVALID_ARGS",
        "TAI_ERROR_INVALID_KERNEL_ADDR",
        "TAI_ERROR_PATCH_EXISTS",
        "TAI_ERROR_HOOK_ERROR",
        "TAI_ERROR_STUB_NOT_RESOLVED",
        "TAI_ERROR_INVALID_MODULE",
        "TAI_ERROR_MODULE_OVERFLOW",
        "TAI_ERROR_BLOCKING"]
    return taiHenErrors[taiErrCode & ERROR_CODE_MASK]

#Can this be a taiHEN error code ?
#Code by Princess of Sleeping
def isTaiHENErrorCode(error_code : int) -> bool: 
    if (error_code - 0x90010000) <= 0xD and (error_code - 0x90010000) >= 0:
        return True
    else:
        return False

#Can this integer be a valid SceUID ?
#Code by Princess of Sleeping
def canBeSceUID(code : int) -> bool:
    if((code & 0xF0000000) == 0x40000000) and ((code & 0xF0000) != 0) and ((code & 1) == 1):
        return True
    else:
        return False

#Returns a formated string containing information about an error code - looking like following :
# Facility : FACILITY_NAME (description if avaliable) / Unknown facility (facility number)
# Error code : ERROR_CODE_NAME (description if avaliable) / Unknown error code (error code)
# Fatal : Yes/No
def getErrorCodeInfo(db : dict, error_code : int) -> str:
    if isTaiHENErrorCode(error_code):
        ret = "Facility : taiHEN\n"
        ret += "Error code : %s\n" % getErrorNameForTaiHENFacility(error_code)
        ret += "Fatal : No"
        return ret

    if not (error_code & IS_ERROR_MASK):
        if canBeSceUID(error_code):
            return "Not an error code - may be a SceUID."
        else:
            return "Not an error code."
    
    if (error_code & RESERVED_MASK) != 0:
        return "Invalid error code."

    facility_id = error_code & FACILITY_MASK
    error_id = error_code & ERROR_CODE_MASK
    fatal = (error_code & IS_FATAL_MASK)

    ret = getFacilityName(db, error_code) + "\n" + getErrorCodeName(db, error_code) + "\n"
    if fatal:
        ret += "Fatal : Yes"
    else:
        ret += "Fatal : No"
    return ret

def createDbFromJSONString(s : str) -> dict:
    initDict = json.loads(s)
    ret = dict()

    try:
        for facility_code, facility_obj in initDict.items():
            facility_code_num = int(facility_code, 16) #Convert to int
            ret[facility_code_num] = dict()
            ret[facility_code_num]['name'] = facility_obj['name']
            ret[facility_code_num]['errors'] = dict()

            fdesc = facility_obj.get('description', None) #Description is optional
            if (fdesc != None):
                ret[facility_code_num]['description'] = fdesc

            for error_code, error_obj in facility_obj['errors'].items():
                error_code_num = int(error_code, 16)
                ret[facility_code_num]['errors'][error_code_num] = {'name' : error_obj['name']}
                edesc = error_obj.get('description', None)
                if (edesc != None):
                    ret[facility_code_num]['errors'][error_code_num]['description'] = error_obj['description']
    except:
        ret = None

    finally:
        del initDict
        gc.collect() #Ensure the temporary dictionary is free'd from memory, since we don't need it anymore
        return ret

def createDbFromJSONFile(dbFilePath : str) -> dict:
    try:
        fh = open(dbFilePath, "r")
    except:
        print(f"Failed to open {dbFilePath}.\n")
        return None

    dbData = fh.read()
    fh.close()
    ret = createDbFromJSONString(dbData)

    del dbData
    gc.collect() #Ensure that file contents are free'd from memory, since we don't need them anymore

    return ret