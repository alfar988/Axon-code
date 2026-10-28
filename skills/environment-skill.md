---
name: environment-skill
description: Set up and repair the working environment (Termux, Linux, macOS): packages, Python venv and pip, Node, git, ports and background processes, storage permissions, previewing web pages.
---
# Environment skill

Know where you are first: `uname -a; echo $PREFIX; python3 --version; node --version; git --version` (use system_info for RAM, disk, battery and installed tools).

## Package managers
| System | Update | Install | Notes |
|---|---|---|---|
| Termux (Android) | `pkg update && pkg upgrade -y` | `pkg install -y python git nodejs clang` | No sudo. Home is `/data/data/com.termux/files/home` |
| Debian / Ubuntu / Kali | `sudo apt update` | `sudo apt install -y python3 python3-venv git nodejs` | Python is "externally managed": use a venv |
| macOS | `brew update` | `brew install python git node` | |
Always pass `-y` (commands run non-interactively).

## Python
```
python3 -m venv .venv && . .venv/bin/activate    # Debian/Kali/macOS
python -m pip install -U pip && pip install -r requirements.txt
```
On Termux plain `pip install name` works. If a package needs a compiler: `pkg install clang make` (Termux) or `apt install build-essential python3-dev`. If it still fails, look for a pure-Python alternative.

## Node
`npm init -y`, `npm install pkg`, `npm run <script>`. Missing script: read package.json. For one-off tools use `npx -y tool`.

## Git (basics the user may need)
```
git init && git add -A && git commit -m "Initial commit"
git remote add origin https://github.com/USER/REPO.git && git branch -M main && git push -u origin main
```
Tokens and passwords: never paste into chat; use `/secret`. `.gitignore` must exclude `.venv/`, `node_modules/`, `__pycache__/`, `.env`.

## Servers, ports and processes
- Start long-running servers with `run_shell(background=true)`; check output with manage_process (list/log/stop).
- Port busy: `fuser -k 8000/tcp` or `lsof -i :8000`, or pick another port.
- Show a web page: `preview_web(path="index.html")` serves it on 127.0.0.1 and opens the browser on Termux. Stop it afterwards.
- Termux keeps the phone awake with `termux-wake-lock`; long builds survive a locked screen.

## Storage and permissions (Android)
`termux-setup-storage` once, then shared storage is at `~/storage/shared`. Do not write outside the workspace without the user's approval. `chmod +x script.sh` for scripts.

## Network
`curl -I https://example.com` to test reachability; `/net` in Axion checks DNS and the OpenRouter connection. SSL errors: `pkg install ca-certificates`, check the system date.

## Disk and memory
`df -h .`, `du -sh * | sort -h | tail`. Free space by deleting `node_modules`, caches (`pip cache purge`, `pkg clean`), old builds. Big builds on phones: use `--no-daemon`, close other apps.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `pkg: command not found` | Not Termux: use `apt` (check `/etc/os-release`) |
| `sudo: command not found` (Termux) | Not needed; Termux has no root |
| `python: command not found` | Use `python3`, or install it |
| Interactive prompt hangs a command | Re-run with `-y`/`--yes`/`--no-input`, or pipe `yes |` |
| `EACCES` writing a global npm package | Use a local install or `npm config set prefix ~/.npm-global` |
