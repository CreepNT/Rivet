# Rivet
A Discord bot to resolve PSVita error codes from a JSON database.

# Usage
You need the following Python modules : `hashlib`, `requests` and `discord.py`.
Create a file named `SECRETS.py` with the following content :
```py
TOKEN = 'your bot token here'
WHITELIST = [
    000000000, #User IDs of whitelisted people - turn on Discord's developper mode to be able to get them.
]
```

Run `main.py`, wait for the bot to connect, profit.<br>
See `CONFIG.py` for more informations about the configuration.<br>
Run the `help` command for more information about the avaliable commands.<br>
Some commands can only be run by users in the whitelist.

# Known issues/bugs
* After saving a database with `save_db`, the SHA-1 sum of the local copy will be different from i.e. a `download_db`'ed file's SHA-1 sum.
  * This is due to the fact the `json` library will return a compacted string when serializing, which may (and probably will) not match the original file's style.
  * Not fixable