---
name: python-skill
description: Python apps, CLIs, bots and scrapers: project structure, argparse/logging template, Telegram and Discord bots, resilient HTTP, tests, packaging and troubleshooting.
---
# Python skill (apps, CLIs, bots, scrapers)

## Quick rules (read first)
1. Prefer the standard library. Add a package only when it saves real work, and say which one.
2. Use `pathlib`, `with open(...)`, f-strings and `subprocess.run([...], check=True, timeout=...)`.
3. A script ends with `if __name__ == "__main__": raise SystemExit(main())`.
4. Catch specific exceptions. Give network calls a `timeout`.
5. Never use mutable default arguments. Never use `shell=True` with text from outside.
6. Put the logic in functions and test it. Run the script before you report.

## Safety in this skill
- Do not `eval`, `exec` or `pickle.loads` data from a user, the web or a file you did not make. Use `json` and `yaml.safe_load`.
- Build file paths from a base folder and reject `..`. Run commands as a list of arguments, not as a string handed to a shell.
- Do not write scripts that scan or log in to systems you do not own, harvest accounts, or hide what they do.

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
Discord: `discord.py` with explicit intents (`intents = discord.Intents.default(); intents.message_content = True`), token from the environment. Keep handlers short; put logic in plain functions you can test without the network. In Lumo store the token with `/secret set BOT_TOKEN` and run with `BOT_TOKEN={{BOT_TOKEN}} python bot.py`.

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

## Good and bad examples

### 1. Running another program
Bad: a user-supplied name inside a shell string.
```python
import os
os.system("ping " + host)          # host = "x; rm -rf ~" runs the second command too
```
Good: a list of arguments, a timeout and a checked result.
```python
# check: runs
import subprocess, sys

out = subprocess.run([sys.executable, "-c", "print('hi')"], capture_output=True, text=True, timeout=10, check=True)
assert out.stdout.strip() == "hi"
```

### 2. File paths
Bad: `open("uploads/" + name)` with `name = "../../secret"`.
Good: resolve and check that the path stays inside the base folder.
```python
# check: runs
from pathlib import Path
import tempfile

def safe_join(base, name):
    base = Path(base).resolve()
    target = (base / name).resolve()
    if base != target and base not in target.parents:
        raise ValueError("path escapes the base folder: %r" % name)
    return target

base = tempfile.mkdtemp()
assert safe_join(base, "a/b.txt").name == "b.txt"
try:
    safe_join(base, "../secret")
except ValueError:
    pass
else:
    raise AssertionError("traversal was not blocked")
```

### 3. Reading data
Bad: `pickle.loads(data)` on bytes from the network (it can run code).
Good: `json.loads(text)` and check the fields you need.

### 4. Network calls
Bad: `urllib.request.urlopen(url).read()` with no timeout hangs forever.
Good: `urllib.request.urlopen(url, timeout=10)` inside `try/except urllib.error.URLError`.

### 5. Cleaning up
Bad: `f = open(p); data = f.read()` and never close it.
Good: `with open(p, encoding="utf-8") as f: data = f.read()`.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| `ModuleNotFoundError` | Install it in the active virtual environment; check `which python3` |
| `UnicodeDecodeError` | Open with `encoding="utf-8"` (and `errors="replace"` if the data is untrusted) |
| Changing a list while looping | Loop over a copy or build a new list |
| `datetime.now()` mixed with timezone-aware dates | Use `datetime.now(timezone.utc)` everywhere |
| Script works only from one folder | Build paths from `Path(__file__).parent` |
| Import fails with the script's own name | Do not name a file like a module you import (`json.py`, `random.py`) |

## Checklist before you finish
- [ ] I ran the script, and a test covers the main function.
- [ ] No `shell=True` with outside text, no `eval`, no `pickle` of untrusted data.
- [ ] Network calls have timeouts; files are opened with `with`.
- [ ] Paths cannot escape the folder they should stay in.
- [ ] The final message says how to run it and what I verified.
