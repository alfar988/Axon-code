---
name: testing-skill
description: Write tests that catch real bugs: reproduce a bug as a failing test first, unittest/pytest/node:test patterns, fake servers instead of the internet, CLI tests, flaky-test fixes. Runnable examples.
---
# Testing skill

## Workflow for a bug
1. Reproduce it in the smallest test that fails for the right reason.
2. Fix the code. The test turns green.
3. Run the whole suite. Keep the test: it is the regression guard.

For new code: write the test for the behavior the user asked for, including one boundary (empty input, zero, very long, wrong type) and one error path. Test behavior, not private details.

## Python: unittest (stdlib, always available)
```python
# check: runs
import re
import unittest

def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not text:
        raise ValueError("nothing left after cleaning")
    return text

class SlugifyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_collapses_separators(self):
        self.assertEqual(slugify("  a --- b  "), "a-b")

    def test_empty_is_an_error(self):
        with self.assertRaises(ValueError):
            slugify("!!!")

    def test_cases(self):
        for raw, want in [("A_B", "a-b"), ("x1", "x1"), ("x_y z", "x-y-z")]:
            with self.subTest(raw=raw):
                self.assertEqual(slugify(raw), want)

if __name__ == "__main__":
    unittest.main(argv=["tests"], exit=False, verbosity=0)
```
Run: `python -m unittest discover -s tests -v`. With pytest installed: `pytest -q`, `pytest -k slug -x`, parametrize with `@pytest.mark.parametrize("raw,want", [...])`, temp files with the `tmp_path` fixture.

## Replace the internet with a local server
Tests that call real sites are slow and flaky. Start a tiny server on a free port instead:
```python
# check: runs
import json
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"path": self.path, "ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

def get_json(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.load(r)

class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)       # port 0: the OS picks a free port
        cls.base = "http://127.0.0.1:%d" % cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_get_json(self):
        self.assertEqual(get_json(self.base + "/items?page=2"), {"path": "/items?page=2", "ok": True})

unittest.main(argv=["tests"], exit=False, verbosity=0)
```
Failure cases (500, slow response, bad JSON) get their own handler paths. For code that reads the clock or randomness, pass the clock or a seeded `random.Random(1)` in as a parameter.

## Test a command line program
```python
# check: runs
import subprocess
import sys

def run(*args):
    return subprocess.run([sys.executable, "-c", "import sys; print(sys.argv[1:]); sys.exit(2 if 'bad' in sys.argv else 0)", *args],
                          capture_output=True, text=True, timeout=30)

ok = run("a", "b")
assert ok.returncode == 0 and ok.stdout.strip() == "['a', 'b']"
assert run("bad").returncode == 2
print("cli checks passed")
```
Assert exit code, stdout and stderr separately.

## JavaScript: node:test (Node 18+, no install)
```js
// check: syntax
import test from "node:test";
import assert from "node:assert/strict";

export const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));

test("clamp keeps values inside the range", () => {
  assert.equal(clamp(5, 0, 3), 3);
  assert.equal(clamp(-1, 0, 3), 0);
  assert.equal(clamp(2, 0, 3), 2);
});
```
Run: `node --test`. Browser code: keep game rules and calculations in pure functions (no `document`) so they can be imported and tested the same way.

## Flaky tests
| Cause | Fix |
|---|---|
| Real clock or `sleep` | inject a fake clock; wait for a condition with a timeout, not a fixed delay |
| Randomness | seed it; assert properties, not exact values |
| Network | local fake server |
| Shared state or order | each test builds its own data; temp directories; no globals |
| Port already in use | bind to port 0 |

## Checklist before saying "tested"
The test failed before the fix and passes after. The whole suite ran. You read the output, not just the exit code. No test was deleted or loosened to make it pass.
