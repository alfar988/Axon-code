---
name: debug-skill
description: Fix errors systematically and on your own: reproduce, read the error, locate, hypothesize, fix the root cause, re-run; with a runbook of common errors for Python, JavaScript, Node, git, network, Termux and Gradle.
---
# Debug skill (fix it yourself, do not hand it back)

When a command, check or test fails you own the fix. Do not ask permission to repair your own bug; do not stop at "it failed". Loop until it passes or you can state the concrete blocker.

## Quick rules (read first)
1. Read the whole error, from the first line. The last `Caused by:` or the bottom frame of a traceback is usually the real place.
2. Reproduce it with the exact command. A bug you cannot repeat cannot be proven fixed.
3. Make one guess at a time, test it with the cheapest check (a print, a smaller input), then change one thing.
4. Fix the cause, not the symptom. Never silence an error, delete a check or loosen a test to make it pass.
5. After the fix, run the original failing command again and a nearby case.
6. Try up to four distinct ideas. Then stop and explain the concrete blocker and what you tried.

## Safety in this skill
- Do not "fix" a failure by switching off security: certificate checks, authentication, firewalls, `chmod 777`, running as root. If a local test needs a shortcut, say so and keep it out of the real setup.
- Do not paste secrets, tokens or private data into a search query or a bug report.

## The loop
1. **Reproduce.** Run the failing command again and capture the whole output. If you cannot reproduce it, collect facts (versions, input, environment) before changing anything.
2. **Read the error properly.** The last line is the cause; the last frame inside the user's own file is the location. Note the exact message and line number.
3. **Locate.** `read_file` around that line, `search_files` for the name and its callers. Never guess names, signatures or paths.
4. **Hypothesize.** One to three causes, most likely first. Test the cheapest by printing a value, running a smaller example, or reading config. The `[how to fix]` hints Lumo appends to failing results are good first guesses.
5. **Fix the root cause**, with the smallest change that makes the behavior correct. No unrelated refactors.
6. **Confirm.** Re-run the original failing command, then neighbours (verify_files, tests, the feature next to it).
7. **Explain in two sentences:** cause, fix, how to avoid it.

## Discipline
- Keep a three-line ledger: hypothesis, test, result. Never repeat a test whose result you already have.
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
| Canvas is black or the playfield is empty | Canvas size 0 or never set; `draw()` before `resize()`; the loop died on its first exception; entities off screen or the same color as the background; `clearRect` after drawing | Log `canvas.width`, `canvas.height` and the first entity's x, y; read the first console error; `node scripts/page_check.js page.html` |
| Fine in portrait, empty or cut off in landscape | Size computed from `innerHeight` minus fixed heights (zero or negative), or `aspect-ratio` fighting the container | Size from `getBoundingClientRect()`, clamp to >= 1, test both orientations |
| Text looks smeared or blurry | `filter: blur`, a large `text-shadow`, `backdrop-filter` behind text, canvas text not scaled for devicePixelRatio | Remove the effect from text; draw canvas text after `setTransform` for the pixel ratio |

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
- **No error but wrong result:** write the expected value down, print the actual one at each step, find the first step that differs. Check types and units (`repr`, `type`), off-by-one at the edges, shared data mutated by another part, and the order of operations.
- **It worked before:** `git diff`, or `git bisect run <test command>`, shows the change that broke it; undo only that change.

## Stop conditions
After four distinct attempts on the same problem without progress, stop and report: what you tried, what you learned, the most likely cause, and the one thing you need from the user.

## Good and bad examples

### 1. Hiding the error
Bad: the crash is gone, the wrong answer stays.
```python
try:
    total = sum(prices[item] for item in cart)
except KeyError:
    total = 0
```
Good: find which item has no price, and say it.
```python
# check: runs
def total_price(cart, prices):
    total = 0
    for item in cart:
        if item not in prices:
            raise KeyError("no price for %r" % item)
        total += prices[item]
    return total

assert total_price(["a", "b"], {"a": 2, "b": 3}) == 5
try:
    total_price(["zzz"], {"a": 2})
except KeyError as e:
    assert "zzz" in str(e)
```

### 2. Shotgun changes
Bad: change the import, the port, the version and a loop at once, then run. If it works, nobody knows why.
Good: write the guess ("the port is busy"), test it (`lsof -i :8000` or try another port), change that one thing, run again.

### 3. Claiming success
Bad: "I fixed it." (nothing was run)
Good: "`python app.py` failed with `KeyError: 'name'` because the form field is called `username`. I changed the lookup and ran it again: it starts and `curl localhost:8000` returns 200."

### 4. Reading a traceback
```text
Traceback (most recent call last):
  File "app.py", line 12, in <module>
    run()
  File "app.py", line 8, in run
    return load("data.json")
FileNotFoundError: [Errno 2] No such file or directory: 'data.json'
```
Bad: "Python is broken." Good: the file is looked up in the current folder. Check `pwd`, then either run from the right folder or build the path from the script's location.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Fixing the line the error points at, when the cause is earlier | Print the values one step earlier |
| Retrying the same command hoping it changes | Change one thing between runs |
| Trusting an old log | Run again and read the new output |
| A bug that only happens sometimes | Log inputs and timing; look for shared state, time, randomness, order |
| Fix works but a test now fails | You changed behavior: read the test, decide which one is right |
| "It works on my machine" | Compare versions, environment variables and working folder |

## Checklist before you finish
- [ ] I can state the cause in one sentence.
- [ ] The original failing command now passes, and I ran it.
- [ ] I changed the cause, not just the message.
- [ ] No check, test or security setting was removed to get a pass.
- [ ] If it is not fixed, I listed what I tried and what blocks me.
