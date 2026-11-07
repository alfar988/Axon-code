---
name: environment-skill
description: Set up and repair the working environment (Termux, Linux, macOS): packages, Python venv and pip, Node, git, ports and background processes, storage permissions, previewing web pages.
---
# Environment skill

Know where you are first: `uname -a; echo $PREFIX; python3 --version; node --version; git --version` (use system_info for RAM, disk, battery and installed tools).

## Quick rules (read first)
1. Find out where you are before you install anything: `uname -a`, `echo $PREFIX` (Termux has `/data/data/com.termux/files/usr`), `python3 --version`, `node --version`.
2. Use the system's package manager: `pkg` on Termux (no `sudo`), `apt` on Debian, Ubuntu and Kali, `brew` on macOS.
3. Install Python packages inside a virtual environment (`python3 -m venv .venv`) or with `--user`, not into the system.
4. Use non-interactive flags (`-y`, `--yes`, `--no-input`) so a command never waits for a question.
5. Before starting a server, check that the port is free. If not, use another port and say which.
6. Long jobs run in the background with a log file, and you check the log.

## Safety in this skill
- Do not run `curl ... | sh` or `wget ... | bash` from a source you cannot verify. Download the file, read it, then decide.
- Do not turn off certificate checks, open a port to the whole network, or change system security settings unless the user asked for exactly that and understands the risk.
- Stay in the workspace and the user's own folders; do not touch other apps' data.

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
`curl -I https://example.com` to test reachability; `/net` in Lumo checks DNS and the OpenRouter connection. SSL errors: `pkg install ca-certificates`, check the system date.

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

## Good and bad examples

### 1. Installing Python packages
Bad: `pip install requests` straight into the system, then a different project breaks.
Good:
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install requests
```
On Termux, upgrade pip with `pkg upgrade python-pip`, not with pip itself.

### 2. Running an installer you found
Bad: `curl -s https://example.com/install.sh | sh` with an unknown site.
Good: use `pkg install <name>` or the project's documented package. If a script is the only way, download it, read what it does, and ask the user before running it.

### 3. A busy port
Bad: the server fails with `Address already in use`, and you try the same command again.
Good:
```bash
(ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) | grep ':8000'
python3 -m http.server 8010
```
Then tell the user the page is at `http://localhost:8010`.

### 4. Background work
Bad: start a build in the foreground and hit the tool timeout.
Good: `nohup ./gradlew assembleDebug > build.log 2>&1 &` then read `tail -n 30 build.log` until it ends.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| `sudo: command not found` on Termux | Termux has no sudo; run the command without it |
| `Permission denied` for phone storage | Run `termux-setup-storage` and allow the permission |
| `command not found` after installing | Open a new shell, or check `echo $PATH` |
| SSL errors | `pkg install ca-certificates`; fix the system clock; do not disable verification |
| Out of space | `df -h`, then remove caches such as `~/.cache` and `node_modules` of old projects |
| Process keeps the phone awake or gets killed | `termux-wake-lock` for long jobs; stop what you started |

## Checklist before you finish
- [ ] I checked the environment first and used the right package manager.
- [ ] Packages were installed in a virtual environment or with the documented command.
- [ ] No unverified script was piped into a shell and no security setting was weakened.
- [ ] Servers use a free port and I told the user the address.
- [ ] Background jobs have a log, and I stopped anything I no longer need.
