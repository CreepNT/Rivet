# Rivet
A Discord bot

# Features
Resolves PSVita error codes from a JSON database.

# Usage
You need the following Python modules : `json`, `requests`, `re` and `discord.py`.
Create a file named `SECRETS.py` with the following content :
```py
TOKEN = 'your bot token here'
WHITELIST = [
    000000000, #User IDs of whitelisted people - turn on Discord's developper mode to be able to get them.
]
```

Run `main.py`, ??, profit.
See `CONFIG.py` for more informations about the configuration.