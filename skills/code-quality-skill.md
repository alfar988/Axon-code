---
name: code-quality-skill
description: Write correct, readable, safe code the first time: structure, naming, error handling, input validation, security basics, tests and a self-review checklist, with Python and JavaScript examples.
---
# Code quality skill

Most bad AI code fails in the same few ways. Avoid them on purpose.

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
def parse_quantity(raw):
    try:
        n = int(str(raw).strip())
    except ValueError:
        raise ValueError("quantity must be a whole number")
    if not 1 <= n <= 999:
        raise ValueError("quantity must be between 1 and 999")
    return n
```
```javascript
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const asInt = (v, d = 0) => { const n = parseInt(v, 10); return Number.isFinite(n) ? n : d; };
```

## Security basics (non-negotiable)
- **XSS:** never put user text into `innerHTML`. Use `textContent`, or build nodes with `createElement`.
- **SQL injection:** parameterized queries only: `cur.execute("SELECT * FROM t WHERE id = ?", (item_id,))`. Never build SQL with string formatting.
- **Secrets:** never in code or git. Read from environment variables; in Axion use `{{NAME}}` placeholders and `/secret set NAME`.
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

## Typical AI mistakes and their fixes
| Mistake | Fix |
|---|---|
| Calls a helper that was never written | Define it, or inline it; run verify_files |
| Forgets to `return` / `await` | Read the function once as a caller |
| Mutates a shared default argument (`def f(x, items=[])`) | Use `None` and create the list inside |
| Off-by-one in loops and slices | Test the first, last and empty cases |
| Uses an API that does not exist in the loaded version | Read the docs of that exact version; check the template |
| Rewrites a whole file for a small change | Use edit_file with a unique snippet |
