---
name: python-skill
description: Python apps, CLIs, bots and scrapers: project structure, argparse/logging template, Telegram and Discord bots, resilient HTTP, tests, packaging and troubleshooting.
---
# Python skill (apps, CLIs, bots, scrapers)

## Structure
Small script: one file. Past about 300 lines split it: `main.py` (entry), `core.py` (pure logic), `io.py` (files/network), `tests/`. Always add `requirements.txt` and a README with install and run steps.

## CLI template (stdlib only)
```python
#!/usr/bin/env python3
"""Tool description in one sentence."""
import argparse, logging, sys
from pathlib import Path

log = logging.getLogger("tool")

def run(path: Path, limit: int) -> int:
    if not path.is_file():
        log.error("file not found: %s", path); return 2
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[:limit]:
        print(line)
    return 0

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path, help="input file")
    p.add_argument("-n", "--limit", type=int, default=10, help="max lines (default: 10)")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(levelname)s: %(message)s")
    try:
        return run(a.path, a.limit)
    except KeyboardInterrupt:
        return 130

if __name__ == "__main__":
    sys.exit(main())
```
Rules: `argparse` with `--help`; `logging` not `print` for diagnostics; exit codes (0 ok, 2 usage/input error, 130 Ctrl+C); `pathlib`; UTF-8 explicitly.

## Resilient HTTP with the stdlib
```python
import json, time, urllib.request, urllib.error

def get_json(url, retries=3, timeout=10):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tool/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last = e; time.sleep(2 ** attempt)                  # 1 s, 2 s, 4 s
    raise RuntimeError("failed after %d attempts: %s" % (retries, last))
```
Always a timeout, a User-Agent, limited retries with backoff, and a clear final error.

## Scraper rules
Respect robots.txt and the site's terms; sleep between requests (>= 1 s); set a User-Agent; parse with `html.parser` (stdlib) or BeautifulSoup if installed; save raw pages while developing so you do not hammer the site; handle missing elements (`None`) instead of crashing.

## Telegram bot (python-telegram-bot v20+)
```python
# pip install python-telegram-bot        token from the environment, never in code
import os, logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Send /help for commands.")

async def on_error(update, ctx):
    logging.exception("handler failed", exc_info=ctx.error)

def main():
    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_error_handler(on_error)
    app.run_polling()                      # long polling works fine on a phone

if __name__ == "__main__":
    main()
```
Discord: `discord.py` with explicit intents (`intents = discord.Intents.default(); intents.message_content = True`), token from the environment. Keep handlers short; put logic in plain functions you can test without the network. In Axion store the token with `/secret set BOT_TOKEN` and run with `BOT_TOKEN={{BOT_TOKEN}} python bot.py`.

## Tests
```python
import unittest
from core import slugify

class T(unittest.TestCase):
    def test_basic(self): self.assertEqual(slugify("Hello, World!"), "hello-world")
    def test_empty(self): self.assertEqual(slugify(""), "")
unittest.main() if __name__ == "__main__" else None
```
Run `python3 -m unittest -v`. Test pure functions, edge cases (empty, huge, unicode), and error paths.

## Environment
- Debian/Kali/Ubuntu: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`. Termux: plain `pip install` works (no venv needed).
- Pin minimum versions in requirements.txt (`requests>=2.31`). Freeze only for deployment.

## Before reporting done
`python3 -m py_compile` on every file (verify_files includes undefined-name detection), a smoke run with `--help` or a dry-run flag showing real output, and the exact run command in your report.

## Troubleshooting
| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` | Not installed, or wrong interpreter | `pip install X`; `python3 -m pip` to match the interpreter |
| `externally-managed-environment` | Debian/Ubuntu system Python | Use a venv, or `--break-system-packages` on Termux |
| `UnicodeDecodeError` | Wrong encoding | `open(p, encoding="utf-8", errors="replace")` |
| Script hangs | No timeout on network or subprocess | Add `timeout=`; use `subprocess.run(..., timeout=30)` |
| `RuntimeError: This event loop is already running` | `asyncio.run` inside a running loop | Await the coroutine instead, or use one entry `asyncio.run(main())` |
| Works in terminal, fails in the bot | Relative paths and cwd | Use `Path(__file__).parent / "data.json"` |
