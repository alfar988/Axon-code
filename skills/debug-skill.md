---
name: debug-skill
description: Fix errors systematically and on your own: reproduce, read the error, locate, hypothesize, fix the root cause, re-run; with a runbook of common errors for Python, JavaScript, Node, git, network, Termux and Gradle.
---
# Debug skill (fix it yourself, do not hand it back)

When a command, check or test fails you own the fix. Do not ask permission to repair your own bug; do not stop at "it failed". Loop until it passes or you can state the concrete blocker.

## The loop
1. **Reproduce.** Run the failing command again and capture the whole output. If you cannot reproduce it, collect facts (versions, input, environment) before changing anything.
2. **Read the error properly.** The last line is the cause; the last frame inside the user's own file is the location. Note the exact message and line number.
3. **Locate.** `read_file` around that line, `search_files` for the name and its callers. Never guess names, signatures or paths.
4. **Hypothesize.** One to three causes, most likely first. Test the cheapest by printing a value, running a smaller example, or reading config. The `[how to fix]` hints Axion appends to failing results are good first guesses.
5. **Fix the root cause**, with the smallest change that makes the behavior correct. No unrelated refactors.
6. **Confirm.** Re-run the original failing command, then neighbours (verify_files, tests, the feature next to it).
7. **Explain in two sentences:** cause, fix, how to avoid it.

## Discipline
- Change one thing at a time; if a change did not move the symptom, revert it before trying the next.
- After the same idea fails twice, change strategy: bisect (disable half the code), build a minimal reproduction, or print intermediate values.
- Never hide an error by catching and ignoring it, and never delete a test to make it pass.
- Missing dependency? Install it (`pip install`, `npm install`, `pkg install`) and re-run. Wrong port? Pick another. Stale process? Stop it. These are yours to fix.
- Ask the user only when the fix needs a decision only they can make (credentials, which of two behaviors, destructive actions).

## Runbook: error -> cause -> action
| Error | Usual cause | Action |
|---|---|---|
| `ModuleNotFoundError: No module named 'x'` | Not installed / wrong interpreter | `pip install x` (maybe a different PyPI name: yaml=pyyaml, cv2=opencv-python, PIL=pillow) |
| `error: externally-managed-environment` | Debian system Python | venv, or `pip install --break-system-packages x` on Termux |
| `NameError` / `ReferenceError: x is not defined` | Typo, defined later/elsewhere, missing import or script tag | Search for the name; define/import it; load the library before your code |
| `SyntaxError`, `Unexpected token` | Unclosed bracket or quote earlier, truncated file | Read the lines above the reported line; check the end of the file |
| `IndentationError` | Mixed tabs and spaces | 4 spaces everywhere |
| `TypeError: ... missing 1 required positional argument` | Call does not match the definition | Read the definition, fix the call |
| `Cannot read properties of null/undefined` | `getElementById` returned null (script ran before the element, wrong id) or missing data | Script at end of body; check ids; guard the access |
| `x is not a function` | Shadowed or never defined name; wrong object | Check spelling and definition order |
| `KeyError`, `IndexError` | Missing key / empty list | `.get()`, check length |
| `JSONDecodeError`, `Unexpected end of JSON input` | Empty or HTML response, truncated JSON | Print the raw text first |
| `FileNotFoundError`, `ENOENT` | Wrong cwd or path | `list_dir`, absolute path, `Path(__file__).parent` |
| `PermissionError`, `EACCES` | Mode/ownership | `ls -l`, `chmod +x`; Termux: `termux-setup-storage` for shared storage |
| `Address already in use` / `EADDRINUSE` | Old server running | manage_process stop, or another port |
| `Connection refused` | Server not started yet | Start in background, wait 2 s, retry |
| `command not found` | Tool not installed | `pkg install` / `apt install` / `brew install`; `which name` |
| `Unable to locate package` | Stale index | `pkg update` / `apt update` |
| `failed building wheel` | Needs a compiler | `pkg install clang make` / `apt install build-essential python3-dev`, or choose a pure-Python package |
| `npm ERR! missing script` | Script not in package.json | Read package.json, use an existing script |
| `Cannot find module 'x'` | Not installed or bad relative path | `npm install x`; fix `./path` |
| `SSL: CERTIFICATE_VERIFY_FAILED` | Missing CA certificates, wrong system date | `pkg install ca-certificates`; check date |
| `fatal: not a git repository` | Wrong folder | `git init` or `cd` |
| `no space left on device` | Disk full | Delete caches/node_modules, `pkg clean` |
| `Killed` / out of memory | Memory limit | Smaller input, fewer parallel jobs |
| Gradle `SDK location not found` | No Android SDK configured | `local.properties` with `sdk.dir=...` |
| Java `UnsupportedClassVersionError` | JDK older than the build target | Install/switch to the required JDK |
| Page is blank | Exception before render | First error in the console; verify_files |

## Instrumentation when the cause is unclear
```python
import logging; logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__); log.debug("value=%r type=%s", x, type(x).__name__)
# find who calls what
import traceback; traceback.print_stack(limit=6)
```
```javascript
console.log("state", JSON.parse(JSON.stringify(state)));   // snapshot, not a live reference
console.trace("who called me");
```
Remove temporary logging before finishing.

## Bisecting
Disable half of the code (comment out, early return). If the bug stays, it is in the other half; repeat. For regressions use `git stash` / `git diff` to see what changed.

## Hard cases
- **Works once, fails the second time:** leftover state (global, cache, file, database row). Reset state, then re-run.
- **Only on the phone:** touch events, viewport, memory, missing CDN access, absolute paths. Test with the smallest viewport and with the network blocked.
- **Intermittent:** time, randomness, concurrency. Make it deterministic (seed, fixed clock) to reproduce.
- **No error but wrong result:** write the expected value down, print the actual one at each step, find the first step that differs.

## Stop conditions
After four distinct attempts on the same problem without progress, stop and report: what you tried, what you learned, the most likely cause, and the one thing you need from the user.
