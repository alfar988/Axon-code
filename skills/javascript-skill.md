---
name: javascript-skill
description: Modern JavaScript and Node: async patterns (timeout, retry, concurrency limit), DOM rules (textContent, event delegation, debounce), common bugs and their fixes, node:test. Runnable examples.
---
# JavaScript skill

Use `const` by default, `let` when reassigning, never `var`. ES modules (`import`/`export`, `"type": "module"` in package.json). Strict equality `===`. No framework unless the task needs one: a single HTML file with vanilla JS is often the right size.

## Async patterns that work
```js
// check: runs
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Fail after a deadline instead of hanging forever
async function withTimeout(promise, ms) {
  let timer;
  const timeout = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`timed out after ${ms} ms`)), ms); });
  try { return await Promise.race([promise, timeout]); } finally { clearTimeout(timer); }
}

// Retry with exponential backoff and jitter
async function retry(fn, { tries = 3, base = 100 } = {}) {
  for (let attempt = 1; ; attempt++) {
    try { return await fn(attempt); }
    catch (err) {
      if (attempt >= tries) throw err;
      await sleep(base * 2 ** (attempt - 1) * (0.5 + Math.random()));
    }
  }
}

// Run many tasks, at most `limit` at a time, keeping result order
async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let next = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) { const i = next++; results[i] = await fn(items[i], i); }
  });
  await Promise.all(workers);
  return results;
}

let calls = 0;
const flaky = async () => { if (++calls < 3) throw new Error("boom"); return "ok"; };
const out = await retry(flaky, { tries: 4, base: 5 });
const squares = await mapLimit([1, 2, 3, 4, 5], 2, async (n) => { await sleep(5); return n * n; });
await withTimeout(sleep(5), 100);
console.log(out, squares.join(","), calls);
if (out !== "ok" || squares.join() !== "1,4,9,16,25" || calls !== 3) process.exit(1);
```
Rules: `await` inside a `try/catch` or put `.catch` on it; unhandled rejections crash Node. `Promise.all` fails fast; `Promise.allSettled` collects every outcome. `array.forEach(async ...)` does not wait: use `for...of` with `await` or `mapLimit`.

## fetch with a deadline (browser and Node 18+)
```js
// check: syntax
async function getJson(url, { timeout = 8000 } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  try {
    const res = await fetch(url, { signal: ctl.signal, headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);   // fetch does not reject on 404/500
    return await res.json();
  } finally { clearTimeout(timer); }
}
```

## DOM rules
```js
// check: syntax
// 1. User text is text: textContent, never innerHTML
li.textContent = userInput;
// 2. One listener on the parent instead of one per child (works for items added later)
list.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action]");
  if (!btn || !list.contains(btn)) return;
  handlers[btn.dataset.action]?.(btn.closest("li").dataset.id);
});
// 3. Debounce input that triggers work
function debounce(fn, ms = 250) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
search.addEventListener("input", debounce((e) => render(e.target.value)));
// 4. Animate with requestAnimationFrame; read layout first, then write, never alternate in a loop
// 5. State in one object; render() draws it; handlers change state and call render()
```
Persist small data with `localStorage` inside `try/catch` (it throws in private mode and when full); wrap `JSON.parse` too.

## Bugs that come back
| Symptom | Cause and fix |
|---|---|
| `0.1 + 0.2 !== 0.3` | floating point: keep money in integer cents, compare with a tolerance |
| `"10" < "9"` is true | strings compare alphabetically: convert with `Number()` and sort with `(a, b) => a - b` |
| Loop callbacks all see the last `i` | use `let` in the loop, not `var` |
| `this` is undefined in a callback | use an arrow function or `.bind(this)` |
| `[1,2,3].sort()` gives `[1,10,2]` | default sort is alphabetical: pass a comparator |
| Object changed "by itself" | you mutated a shared reference: `structuredClone(obj)` or `{...obj}` |
| `NaN` spreads | check `Number.isFinite(x)` at the boundary |
| Timer or listener keeps running | store the id and clear it, remove listeners when the screen closes |

## Node basics
```js
// check: syntax
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import process from "node:process";

const dir = join(process.cwd(), "data");
await mkdir(dir, { recursive: true });
await writeFile(join(dir, "a.json"), JSON.stringify({ ok: true }, null, 2));
const data = JSON.parse(await readFile(join(dir, "a.json"), "utf8"));
```
Read secrets from `process.env`. Handle `SIGINT` to close servers and files. `node --check file.js` finds syntax errors; `node --test` runs tests (see testing-skill).
