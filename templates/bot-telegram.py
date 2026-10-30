#!/usr/bin/env python3
"""__TITLE__: a Telegram bot with long polling, using only the standard library and SQLite.

Setup:      1. Talk to @BotFather on Telegram, send /newbot, copy the token.
            2. export TELEGRAM_TOKEN=123456:ABC...            (never write the token into the code)
            3. python bot.py
Self test:  python bot.py --selftest      runs the bot against a local fake Telegram server; no token or internet needed
Settings:   TELEGRAM_TOKEN (required to run), ALLOWED_CHAT_IDS (comma separated; empty = everyone), BOT_DB (default bot.db),
            TELEGRAM_API_BASE (default https://api.telegram.org, used by the self test)

Commands:   /start  /help  /ping  /note <text>  /notes  /clear  /menu
EDIT: the handlers marked with @bot.command and on_button(); keep Api, Router and poll_once as they are.
"""

import argparse
import json
import logging
import os
import re
import signal
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing

log = logging.getLogger("bot")
API_BASE = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org")
MAX_TEXT = 4000                                      # Telegram limit is 4096 characters per message


# --- Telegram API -------------------------------------------------------------------------------
class Api:
    def __init__(self, token, base=None):
        self.token, self.base = token, (base or API_BASE).rstrip("/")

    def call(self, method, _tries=3, **params):
        data = urllib.parse.urlencode({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items()}).encode()
        url = "%s/bot%s/%s" % (self.base, self.token, method)
        for attempt in range(1, _tries + 1):
            try:
                with urllib.request.urlopen(url, data, timeout=params.get("timeout", 0) + 15) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                body = json.loads(e.read() or b"{}")
                if e.code == 429 and attempt < _tries:                      # flood control: wait as long as Telegram says
                    time.sleep(min(body.get("parameters", {}).get("retry_after", 3), 30))
                    continue
                raise RuntimeError("Telegram %s failed: HTTP %d %s" % (method, e.code, body.get("description", "")))
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == _tries:
                    raise RuntimeError("Telegram %s unreachable: %s" % (method, e))
                time.sleep(2 * attempt)

    def send(self, chat_id, text, **extra):
        parts = [text[i:i + MAX_TEXT] for i in range(0, len(text), MAX_TEXT)] or [""]
        for i, part in enumerate(parts):
            self.call("sendMessage", chat_id=chat_id, text=part or "(empty)", **(extra if i == len(parts) - 1 else {}))


# --- commands -----------------------------------------------------------------------------------
class Router:
    """Turns an update into an action. No network code here, so tests can feed it fake updates."""

    def __init__(self):
        self.commands = {}
        self.button_handler = None

    def command(self, name, help=""):
        def deco(fn):
            self.commands[name] = (fn, help)
            return fn
        return deco

    def handle(self, update, store):
        """Returns a dict of arguments for sendMessage (or {'callback': ...}), or None when there is nothing to answer."""
        if "callback_query" in update and self.button_handler:
            q = update["callback_query"]
            chat = q["message"]["chat"]["id"]
            return {"chat_id": chat, "text": self.button_handler(q.get("data", ""), chat, store), "answer": q["id"]}
        msg = update.get("message") or {}
        text, chat = (msg.get("text") or "").strip(), (msg.get("chat") or {}).get("id")
        if chat is None or not text.startswith("/"):
            return None
        name, _, arg = text[1:].partition(" ")
        entry = self.commands.get(re.sub(r"@\w+$", "", name).lower())            # /start@MyBot in groups
        if not entry:
            return {"chat_id": chat, "text": "Unknown command. Send /help for the list."}
        reply = entry[0](arg.strip(), chat, store, msg)
        return {"chat_id": chat, **(reply if isinstance(reply, dict) else {"text": reply})}


bot = Router()


@bot.command("start", "say hello")
def cmd_start(arg, chat, store, msg):
    return "Hello %s. Send /help to see the commands." % (msg.get("from") or {}).get("first_name", "there")


@bot.command("help", "list the commands")
def cmd_help(arg, chat, store, msg):
    return "\n".join("/%s  %s" % (k, v[1]) for k, v in sorted(bot.commands.items()))


@bot.command("ping", "check that the bot is alive")
def cmd_ping(arg, chat, store, msg):
    return "pong"


@bot.command("note", "save a note: /note buy milk")
def cmd_note(arg, chat, store, msg):
    if not arg:
        return "Usage: /note text to remember"
    store.add_note(chat, arg[:500])
    return "Saved."


@bot.command("notes", "show your notes")
def cmd_notes(arg, chat, store, msg):
    notes = store.notes(chat)
    return "\n".join("%d. %s" % (i, n) for i, n in enumerate(notes, 1)) if notes else "No notes yet. Use /note."


@bot.command("clear", "delete your notes")
def cmd_clear(arg, chat, store, msg):
    return "Deleted %d note(s)." % store.clear(chat)


@bot.command("menu", "show buttons")
def cmd_menu(arg, chat, store, msg):
    keyboard = {"inline_keyboard": [[{"text": "Notes", "callback_data": "notes"}, {"text": "Ping", "callback_data": "ping"}]]}
    return {"text": "Choose:", "reply_markup": keyboard}


def on_button(data, chat, store):
    return {"notes": lambda: cmd_notes("", chat, store, {}), "ping": lambda: "pong"}.get(data, lambda: "Unknown button")()


bot.button_handler = on_button


# --- storage ------------------------------------------------------------------------------------
class Store:
    def __init__(self, path):
        self.path = path
        with closing(self.db()) as db, db:
            db.execute("create table if not exists notes (id integer primary key, chat integer not null, text text not null)")
            db.execute("create table if not exists meta (key text primary key, value text not null)")

    def db(self):
        return sqlite3.connect(self.path, timeout=5)

    def add_note(self, chat, text):
        with closing(self.db()) as db, db:
            db.execute("insert into notes (chat, text) values (?, ?)", (chat, text))

    def notes(self, chat):
        with closing(self.db()) as db:
            return [r[0] for r in db.execute("select text from notes where chat = ? order by id", (chat,))]

    def clear(self, chat):
        with closing(self.db()) as db, db:
            return db.execute("delete from notes where chat = ?", (chat,)).rowcount

    def offset(self):
        with closing(self.db()) as db:
            r = db.execute("select value from meta where key = 'offset'").fetchone()
        return int(r[0]) if r else 0

    def set_offset(self, value):
        with closing(self.db()) as db, db:
            db.execute("insert into meta (key, value) values ('offset', ?) on conflict(key) do update set value = excluded.value", (str(value),))


# --- polling ------------------------------------------------------------------------------------
def poll_once(api, router, store, allowed=(), wait=25):
    """Fetch one batch of updates and answer them. Returns how many updates were handled."""
    res = api.call("getUpdates", offset=store.offset(), timeout=wait)
    updates = res.get("result", [])
    for upd in updates:
        store.set_offset(upd["update_id"] + 1)                                  # confirm first: a crashing update must not repeat forever
        try:
            chat = ((upd.get("message") or upd.get("callback_query", {}).get("message") or {}).get("chat") or {}).get("id")
            if allowed and chat not in allowed:
                continue
            reply = router.handle(upd, store)
            if reply:
                answer = reply.pop("answer", None)
                if answer:
                    api.call("answerCallbackQuery", callback_query_id=answer)
                api.send(reply.pop("chat_id"), reply.pop("text"), **reply)
        except Exception:
            log.exception("update %s failed", upd.get("update_id"))
    return len(updates)


def run(token, db_path, allowed):
    api, store, stop = Api(token), Store(db_path), threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    log.info("bot started; press Ctrl+C to stop")
    while not stop.is_set():
        try:
            poll_once(api, bot, store, allowed)
        except RuntimeError as e:                                               # network trouble: wait and keep going
            log.warning("%s; retrying in 5 s", e)
            stop.wait(5)
    log.info("stopped")


# --- self test with a fake Telegram server ------------------------------------------------------
def selftest():
    import tempfile
    from http.server import BaseHTTPRequestHandler, HTTPServer

    sent, queue = [], [[
        {"update_id": 10, "message": {"chat": {"id": 7}, "from": {"first_name": "Ann"}, "text": "/start"}},
        {"update_id": 11, "message": {"chat": {"id": 7}, "text": "/note buy milk"}},
        {"update_id": 12, "message": {"chat": {"id": 7}, "text": "/notes"}},
        {"update_id": 13, "message": {"chat": {"id": 8}, "text": "/ping"}},
        {"update_id": 14, "message": {"chat": {"id": 7}, "text": "/nope"}},
        {"update_id": 15, "callback_query": {"id": "cb1", "data": "ping", "message": {"chat": {"id": 7}}}},
        {"update_id": 16, "message": {"chat": {"id": 7}, "text": "just talking"}},
    ]]

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
            method = self.path.rsplit("/", 1)[1]
            if method == "getUpdates":
                result = queue.pop(0) if queue else []
            else:
                sent.append((method, {k: v[0] for k, v in form.items()}))
                result = True
            body = json.dumps({"ok": True, "result": result}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    api = Api("TEST", "http://127.0.0.1:%d" % server.server_port)
    store = Store(os.path.join(tempfile.mkdtemp(), "bot.db"))
    failures = []

    def check(label, got, want):
        if got != want:
            failures.append("%s: got %r, wanted %r" % (label, got, want))

    try:
        check("handled", poll_once(api, bot, store, wait=0), 7)
        check("offset saved", store.offset(), 17)
        texts = [p["text"] for m, p in sent if m == "sendMessage" and p["chat_id"] == "7"]
        check("start", texts[0], "Hello Ann. Send /help to see the commands.")
        check("note then notes", texts[1:3], ["Saved.", "1. buy milk"])
        check("unknown command", texts[3], "Unknown command. Send /help for the list.")
        check("button", (texts[4], [m for m, _ in sent].count("answerCallbackQuery")), ("pong", 1))
        check("plain text ignored", len(texts), 5)
        check("empty poll", poll_once(api, bot, store, wait=0), 0)
        queue.append([{"update_id": 20, "message": {"chat": {"id": 8}, "text": "/ping"}}, {"update_id": 21, "message": {"chat": {"id": 7}, "text": "/ping"}}])
        before = len(sent)
        poll_once(api, bot, store, allowed={7}, wait=0)
        check("allow list", [p["chat_id"] for _, p in sent[before:]], ["7"])
        long_parts = [i for i in range(0, 9000, MAX_TEXT)]
        before = len(sent)
        api.send(7, "x" * 9000)
        check("long text is split", len(sent) - before, len(long_parts))
    finally:
        server.shutdown()
    for f in failures:
        print("FAIL", f)
    print("selftest: %s" % ("all checks passed" if not failures else "%d check(s) failed" % len(failures)))
    return 1 if failures else 0


def main(argv=None):
    p = argparse.ArgumentParser(description="__TITLE__")
    p.add_argument("--selftest", action="store_true", help="run the built-in checks and exit")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.selftest:
        return selftest()
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token:
        print("error: set the TELEGRAM_TOKEN environment variable (get a token from @BotFather)", file=sys.stderr)
        return 1
    allowed = {int(x) for x in os.environ.get("ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if x}
    run(token, os.environ.get("BOT_DB", "bot.db"), allowed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
