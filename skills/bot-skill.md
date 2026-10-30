---
name: bot-skill
description: Chat bots that keep running: Telegram long polling and webhooks, a testable command router, rate limits and retry_after, Discord with discord.py, state in SQLite, running on Termux or a server. Runnable example.
---
# Bot skill

## Choose the transport
| Option | Use when |
|---|---|
| Telegram long polling (`getUpdates`) | no public URL, phone or home server; simplest |
| Telegram webhook | a public HTTPS URL exists; lower latency, no polling loop |
| Discord (`discord.py`) | community servers; needs `pip install discord.py` and intents |
Token comes from an environment variable (`TELEGRAM_TOKEN`), never from source files. Create a Telegram bot with @BotFather.

## Keep the logic separate from the network
`handle(update)` takes a dict and returns the reply (or `None`). It has no network code, so tests feed it fake updates.
```python
# check: runs
import re

class Router:
    def __init__(self):
        self.commands = {}

    def command(self, name, help=""):
        def deco(fn):
            self.commands[name] = (fn, help)
            return fn
        return deco

    def handle(self, update):
        msg = update.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat = (msg.get("chat") or {}).get("id")
        if chat is None or not text.startswith("/"):
            return None
        name, _, arg = text[1:].partition(" ")
        name = re.sub(r"@\w+$", "", name).lower()           # /start@MyBot in groups
        entry = self.commands.get(name)
        if not entry:
            return {"chat_id": chat, "text": "Unknown command. Try /help."}
        return {"chat_id": chat, "text": entry[0](arg.strip(), msg)}

bot = Router()

@bot.command("start", "greeting")
def start(arg, msg):
    return "Hello %s. Send /help to see what I can do." % msg.get("from", {}).get("first_name", "there")

@bot.command("add", "add two numbers: /add 2 3")
def add(arg, msg):
    try:
        a, b = (float(x) for x in arg.split())
    except ValueError:
        return "Usage: /add 2 3"
    return "%g" % (a + b)

@bot.command("help", "list commands")
def help_(arg, msg):
    return "\n".join("/%s  %s" % (k, v[1]) for k, v in sorted(bot.commands.items()))

u = lambda t: {"message": {"chat": {"id": 7}, "from": {"first_name": "Ann"}, "text": t}}
assert bot.handle(u("/add 2 3.5"))["text"] == "5.5"
assert bot.handle(u("/add x"))["text"] == "Usage: /add 2 3"
assert bot.handle(u("/start@MyBot"))["text"].startswith("Hello Ann")
assert bot.handle(u("hello")) is None and "Unknown" in bot.handle(u("/nope"))["text"]
print("router ok")
```

## Telegram long polling with the standard library
```python
# check: syntax
import json, os, time, urllib.error, urllib.parse, urllib.request

API = "https://api.telegram.org/bot%s/%s"

def call(token, method, **params):
    data = urllib.parse.urlencode({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items()}).encode()
    try:
        with urllib.request.urlopen(API % (token, method), data, timeout=params.get("timeout", 0) + 15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = json.loads(e.read() or b"{}")
        if e.code == 429:                                           # flood control: obey retry_after
            time.sleep(body.get("parameters", {}).get("retry_after", 5))
            return call(token, method, **params)
        raise

def run(router, token):
    offset = 0
    while True:
        try:
            res = call(token, "getUpdates", offset=offset, timeout=30)       # the server holds the request open
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5)                                                    # network blip: wait, keep the offset
            continue
        for upd in res.get("result", []):
            offset = upd["update_id"] + 1                                    # confirms the update
            try:
                reply = router.handle(upd)
                if reply:
                    call(token, "sendMessage", **reply)
            except Exception as e:                                           # one bad update must not stop the bot
                print("update failed:", e)
```
Limits: about 30 messages per second overall and one per second per chat; messages are at most 4096 characters, so split longer replies. The `templates/bot-telegram.py` starter contains this loop, offset persistence and graceful shutdown.

## Discord (discord.py)
```python
# check: syntax
import os
import discord
from discord import app_commands

intents = discord.Intents.default()          # message_content only if you read plain messages (enable it in the developer portal too)
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@tree.command(name="ping", description="Check that the bot is alive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("pong")

@client.event
async def on_ready():
    await tree.sync()

client.run(os.environ["DISCORD_TOKEN"])
```

## State and keeping it alive
Store per-user data in SQLite (see database-skill), not in memory: the bot restarts. Log to a file with timestamps. On Termux: `termux-wake-lock`, run inside `tmux`, and expect Android to kill background apps unless battery optimization is off for Termux. On a server: a systemd unit with `Restart=always`, or Docker with `restart: unless-stopped`.

## Checklist
Token only from the environment. Unknown commands get a friendly answer. Network errors retry with a pause instead of crashing. Replies are split under the length limit. The bot never echoes secrets and ignores messages from other bots.
