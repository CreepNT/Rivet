import json
from hashlib import sha1

class SCDatabase:
    __slots__ = ["hashMap", "sha1"]

    def __getSha1OfData(self, data : bytes) -> str:
        sha1Ctx = sha1()
        sha1Ctx.update(data)
        return sha1Ctx.hexdigest().lower()


    def __init__(self) -> None:
        self.hashMap : dict = None
        self.sha1 : str = None

    #Returns True on success, False on failure
    def LoadFromFile(self, filePath : str) -> bool:
        try:
            fh = open(filePath, "rb")
        except IOError:
            print(f"Failed to open '{filePath}' for reading.")
            return False

        fdata = fh.read()
        fh.close()

        self.sha1 = self.__getSha1OfData(fdata)
        try:
            self.hashMap = json.loads(fdata.decode("utf-8"))
        except json.JSONDecodeError:
            print(f"Failed to parse '{filePath}' as JSON.")
            self.hashMap = None
            return False
        except UnicodeDecodeError:
            print(f"Failed to decode '{filePath}' as UTF-8.")
            self.hashMap = None
            return False
        return True

    def IsValidDatabaseLoaded(self) -> bool:
        if self.hashMap == None:
            return False
        else:
            return True

    #Returns None if no valid database is currently loaded
    def GetDBSha1(self) -> str:
        if self.hashMap == None:
            return None
        else:
            return self.sha1

    #Returns True on success, False on failure
    def SaveToFile(self, filePath : str) -> bool:
        if self.hashMap == None:
            return False
        
        try:
            fh = open(filePath, "w")
        except IOError:
            print(f"Failed to open '{filePath}' for writing.")
            return False

        fh.write(json.dumps(self.hashMap))
        fh.close()
        return True

    #Returns None if no valid database is currently loaded
    def GetDatabaseAsString(self) -> str:
        if self.hashMap == None:
            return None
        else:
            return json.dumps(self.hashMap)

    #Returns a valid error code on success, 0 if the short code is invalid/unknown or no valid database is currently loaded.
    def ResolveShortCode(self, shortCode : str) -> int:
        if self.hashMap == None:
            return 0
        else:
            return int(self.hashMap.get(shortCode, "0"), 16)