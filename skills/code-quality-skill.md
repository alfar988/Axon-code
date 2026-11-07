---
name: code-quality-skill
description: Write correct, readable, safe code the first time: structure, naming, error handling, input validation, security basics, tests and a self-review checklist, with Python and JavaScript examples.
---
# Code quality skill

Most bad AI code fails in the same few ways. Avoid them on purpose.

## Quick rules (read first)
1. Read the existing code before you write new code. Match its names, structure and style.
2. Take the requirements from the user's own words. Do what was asked, completely, and nothing else.
3. Choose the smallest design that works. A function beats a class; a class beats a framework.
4. Write complete code: no `TODO`, no `pass` stubs, no `...`, no calls to functions that do not exist.
5. Handle the bad cases: empty input, wrong type, missing file, network failure. Say what went wrong in plain words.
6. Put tunable numbers and texts in one place at the top.
7. Run it. Check each requirement against evidence (a run, a test, a file), then report.

## Safety in this skill
- Do not write code meant to hide what it does from the user or from security tools (obfuscated payloads, disabling antivirus, fake error screens), or code that collects data the user was not told about.
- Never `eval` or `exec` text that came from a user, a web page or a file. Respect licenses: do not paste large pieces of someone else's code without saying where it came from.

## Work in this order
1. **Read first.** Open the files you will change and the code that calls them. Copy the project's style, names and structure; do not introduce a second way of doing the same thing.
2. **List the requirements** the user gave, and only those. Anything else is out of scope: leave it out, and mention it in one line at the end if it matters.
3. **Pick examples before code:** two normal inputs, one edge case (empty, zero, huge) and one failure. They become your first test.
4. **Smallest design that works.** Plain functions and data first; no class hierarchy, framework or dependency unless the request needs it.
5. **Write in small steps and run after each.** A bug found within ten lines is cheap; found after three hundred it is not.
6. **Review your own diff** like a stranger (checklist below), then report with evidence for each requirement: the command you ran and what it printed.

## The ten rules
1. **Every name you use exists.** Before calling a function, constant or element id, make sure you defined it (search_files if unsure). Undefined helpers are the number one bug. verify_files now reports them; fix them, do not wave them off.
2. **Complete code only.** No `...`, `TODO`, `pass`-only functions, "implement later", or pseudo-code. If a feature is out of scope, leave it out, not half-built.
3. **Small functions, one job.** A function that needs "and" in its description should be two functions. Keep nesting under 3 levels (return early).
4. **Names say what things are:** `remaining_lives`, `is_expired(item)`, not `x`, `flag`, `data2`.
5. **Validate at the boundary.** Anything from the user, a file, the network or localStorage is untrusted: check type, range and length once, where it enters.
6. **Handle failure explicitly.** Catch the specific error you can handle, add context, never swallow errors silently, never `except:` bare.
7. **No magic numbers.** Put tunable values in one CONFIG object at the top.
8. **State in one place.** One source of truth; derive everything else. Do not store the same fact twice.
9. **No duplication.** The third copy of a block becomes a function.
10. **Verify, then claim.** Run it, read the output, then say it works.

## Error handling patterns
```python
# check: runs
# Python: specific exceptions, context, no silent failure
import json
def load_config(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}                                   # a missing file is a normal case: defaults
    except json.JSONDecodeError as e:
        raise ValueError("config %s is not valid JSON (line %d)" % (path, e.lineno)) from e

assert load_config("missing-file.json") == {}
```
```javascript
// JavaScript: network call with timeout, status check and a useful error
async function getJSON(url, ms = 8000) {
  const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), ms);
  try {
    const res = await fetch(url, { signal: ctl.signal });
    if (!res.ok) throw new Error("HTTP " + res.status + " for " + url);
    return await res.json();
  } catch (err) {
    throw new Error(err.name === "AbortError" ? "Timed out after " + ms + " ms: " + url : err.message);
  } finally { clearTimeout(timer); }
}
```

## Input validation
```python
# check: runs
def parse_quantity(raw):
    try:
        n = int(str(raw).strip())
    except ValueError:
        raise ValueError("quantity must be a whole number")
    if not 1 <= n <= 999:
        raise ValueError("quantity must be between 1 and 999")
    return n

assert parse_quantity(" 7 ") == 7
for bad in ("abc", "0", "1000"):
    try:
        parse_quantity(bad)
        raise SystemExit("should have failed: " + bad)
    except ValueError:
        pass
```
```javascript
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const asInt = (v, d = 0) => { const n = parseInt(v, 10); return Number.isFinite(n) ? n : d; };
```

## Security basics (non-negotiable)
- **XSS:** never put user text into `innerHTML`. Use `textContent`, or build nodes with `createElement`.
- **SQL injection:** parameterized queries only: `cur.execute("SELECT * FROM t WHERE id = ?", (item_id,))`. Never build SQL with string formatting.
- **Secrets:** never in code or git. Read from environment variables; in Lumo use `{{NAME}}` placeholders and `/secret set NAME`.
- **Passwords:** hash with `hashlib.scrypt` (salted); never store or log plain text.
- **Paths:** never join untrusted input into a file path without checking it stays inside the intended folder.
- **Shell:** never pass user text into a shell string; pass an argument list (`subprocess.run([...])`).
- **CORS/CSRF:** allow only the origins you need; state-changing requests need a token or SameSite cookies.

## Structure that scales a little
```
project/
  app.py or index.html     entry point, wiring only
  core/ or js section      logic with no I/O (easy to test)
  io/  or storage section  files, network, database
  tests/test_core.py       one test per rule
  README.md                how to run and test
```
Keep logic pure (input -> output) and I/O thin. That is what makes code testable.

## Tests that catch real bugs
```python
import unittest
from core import parse_quantity

class QuantityTests(unittest.TestCase):
    def test_valid(self):            self.assertEqual(parse_quantity(" 7 "), 7)
    def test_rejects_text(self):     self.assertRaises(ValueError, parse_quantity, "abc")
    def test_rejects_range(self):    self.assertRaises(ValueError, parse_quantity, 0)

if __name__ == "__main__":
    unittest.main()
```
Run with `python -m unittest -v`. For browser code, expose a small `window.app` / `window.game` object (the templates do) and drive it from a test or the console.

## Performance basics
- Measure before optimizing. The usual wins: avoid work inside loops, cache DOM lookups, batch DOM writes, debounce input handlers, reuse objects in game loops (no allocation per frame), paginate large lists.
- Algorithms first: replacing a nested loop with a Map/dict lookup beats any micro-optimization.

## Self-review checklist (do this before saying "done")
- [ ] verify_files is clean (syntax, undefined names, HTML structure).
- [ ] I ran the program or opened the page, and the main path works.
- [ ] Errors from bad input, a missing file and a failed request show a clear message instead of a crash.
- [ ] No leftover placeholders, debug prints or commented-out blocks.
- [ ] The README or my final message says how to run it.
- [ ] Every requirement the user gave maps to something I ran or tested, and I added nothing they did not ask for.

## Typical AI mistakes and their fixes
| Mistake | Fix |
|---|---|
| Calls a helper that was never written | Define it, or inline it; run verify_files |
| Forgets to `return` / `await` | Read the function once as a caller |
| Mutates a shared default argument (`def f(x, items=[])`) | Use `None` and create the list inside |
| Off-by-one in loops and slices | Test the first, last and empty cases |
| Uses an API that does not exist in the loaded version | Read the docs of that exact version; check the template |
| Rewrites a whole file for a small change | Use edit_file with a unique snippet |
| Adds features, files or dependencies nobody asked for | Tie every change to a requirement; remove the rest |
| Catches an error and quietly returns a default | Let it fail loudly, or log it and re-raise |
| Trusts the first idea on a hard problem | Write a brute force and compare on random small inputs (algorithms-skill) |
| Says "done" without running anything | Run it and quote the output |

## Good and bad examples

### 1. Placeholders
Bad: the function looks finished and does nothing.
```python
def save_score(name, score):
    # TODO: write to file
    pass
```
Good: it works, and it fails loudly when it cannot.
```python
# check: runs
import json, os, tempfile

def save_score(path, name, score):
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    data[name] = max(score, data.get(name, 0))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

p = os.path.join(tempfile.mkdtemp(), "scores.json")
save_score(p, "ann", 5)
save_score(p, "ann", 3)
assert json.load(open(p, encoding="utf-8")) == {"ann": 5}
```

### 2. Errors
Bad: the error disappears and the program goes on with wrong data.
```python
try:
    data = json.loads(text)
except:
    pass
```
Good: catch the specific error and explain it.
```python
# check: runs
import json

def load_config(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError("config is not valid JSON (line %d)" % e.lineno) from e
    if "port" not in data:
        raise ValueError("config needs a 'port'")
    return data

try:
    load_config("{bad")
except ValueError as e:
    assert "not valid JSON" in str(e)
assert load_config('{"port": 80}')["port"] == 80
```

### 3. A shared default value
Bad: the same list is reused by every call.
```python
def add_item(item, items=[]):
    items.append(item)
    return items
```
Good:
```python
# check: runs
def add_item(item, items=None):
    items = [] if items is None else items
    items.append(item)
    return items

assert add_item(1) == [1]
assert add_item(2) == [2]
```

### 4. Doing only what was asked
Bad: the user asked for a score counter and gets a settings page, dark mode, accounts and a leaderboard.
Good: the counter, with the polish it needs to be good (clear text, responsive layout, keyboard use, error handling), and one line at the end: "A leaderboard would be a natural next step if you want it."

### 5. Size of the solution
Bad: three classes and a factory for a 20-line script.
Good: two functions and a `main()`.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Names like `data2`, `tmp`, `x` | Name things by what they hold: `unpaid_orders` |
| A function that does five things | Split by reason to change; each function does one |
| Copy-pasted blocks | Extract one function, or one loop over a table |
| Silent `except` | Catch the specific error; log or show it |
| Comments that repeat the code | Comment why, not what |
| New dependency for one helper | Write the helper, or use the standard library |
| Changing unrelated files | Touch only what the request needs; mention anything else in one line |

## Checklist before you finish
- [ ] I read the surrounding code first and followed its style.
- [ ] Every requirement the user gave is met, and I checked each against evidence.
- [ ] No placeholder, no unused code, no call to a missing function.
- [ ] Bad input and failures give a clear message instead of a crash or silence.
- [ ] I ran the code, or tests, and I state exactly what I ran.
- [ ] I did not add features, files or notes nobody asked for.
