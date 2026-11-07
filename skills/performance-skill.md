---
name: performance-skill
description: Make slow code fast by measuring first: timeit and cProfile, algorithmic fixes (sets, dicts, caching), I/O and database batching, front-end rendering costs, memory limits on phones. Runnable examples.
---
# Performance skill

## Quick rules (read first)
1. Measure first. Change one thing. Measure again. Keep the change only if the numbers improved.
2. Fix the algorithm or data structure before the details: a set instead of a list scan, one query instead of one per row.
3. Do work once: move it out of loops, cache results, read files in one go.
4. On phones, memory and battery matter: avoid huge arrays, timers that never stop and constant redraws.
5. Report real numbers with the conditions ("1.8 s down to 0.4 s on 50,000 rows").

## Safety in this skill
- Never remove validation, authentication, rate limits or error handling just to make something faster.
- Load-test only your own servers, at a rate you control. Do not write tools that flood a site or a service you do not own.
- Report honest measurements. Do not claim a speed-up you did not measure.

## Rule 1: measure, then change one thing
Guessing finds the wrong bottleneck most of the time. Get a number before and after, on realistic data, and keep the change only if the number improves.

## Python: time it, profile it
```python
# check: runs
import cProfile
import io
import pstats
import timeit

def slow(items, wanted):
    return [w for w in wanted if w in items]            # `in` on a list scans it: O(n) per lookup

def fast(items, wanted):
    pool = set(items)                                   # O(1) per lookup
    return [w for w in wanted if w in pool]

items, wanted = list(range(3000)), list(range(0, 6000, 3))
assert slow(items, wanted) == fast(items, wanted)       # same answer first, then compare speed
t_slow = timeit.timeit(lambda: slow(items, wanted), number=3)
t_fast = timeit.timeit(lambda: fast(items, wanted), number=3)
print("list %.4fs  set %.4fs" % (t_slow, t_fast))

prof = cProfile.Profile()
prof.runcall(slow, items, wanted)
buf = io.StringIO()
pstats.Stats(prof, stream=buf).sort_stats("cumulative").print_stats(5)
print(buf.getvalue().splitlines()[0])
```
From the shell: `python -m cProfile -s cumtime app.py | head -30`. Look at `cumtime` for the function that dominates, not at the longest-looking line.

## Usual wins, in order of payoff
1. **Better algorithm or data structure.** List membership in a loop becomes a set or dict. Sorting inside a loop moves out of it. Nested loops over two big lists become a dict lookup (a join).
2. **Do less work.** Cache results of pure functions; stop early (`any`, `next`, `break`); filter before transforming; read only the needed columns.
3. **Fewer round trips.** One query for many rows instead of one per row (see database-skill); `executemany`; batch HTTP calls; download once and cache on disk.
4. **Stream, do not load.** Iterate a file line by line; use generators for big data.
5. Only then micro-optimizations or another language.

```python
# check: runs
from functools import lru_cache

calls = 0

@lru_cache(maxsize=None)
def fib(n):
    global calls
    calls += 1
    return n if n < 2 else fib(n - 1) + fib(n - 2)

assert fib(80) == 23416728348467685 and calls == 81     # without the cache this takes minutes
assert sum(1 for _ in (x * x for x in range(1_000_000))) == 1_000_000     # generator: no million-item list in memory
```
`lru_cache` is only safe for pure functions with hashable arguments; bound it (`maxsize=1024`) when keys vary.

## Strings and files
Build strings with `"".join(parts)`, not `+=` in a loop. Read big files with `for line in f`. Compile a regex once, outside the loop (`re.compile`). Parse JSON once.

## JavaScript and the browser
- Measure with `console.time("x")`, the Performance panel, and Lighthouse.
- Animation: `requestAnimationFrame`, change `transform` and `opacity`, not `top/left/width`. Read layout (`offsetHeight`) before writing styles, never alternate in a loop (layout thrashing).
- Long lists: render only visible rows (virtual list) or paginate. Many listeners: delegate to the parent.
- Input handlers that trigger work: debounce (see javascript-skill). Scroll handlers: `{ passive: true }`.
- Load: `defer` on scripts, `loading="lazy"` on images below the fold, explicit `width` and `height` on images, compress images (WebP/AVIF), subset or skip custom fonts.
- Games: no allocation inside the frame loop (reuse objects and arrays), cap `devicePixelRatio` at 2, use sprite sheets or offscreen canvases for static art, update on a fixed time step.

## Memory on phones
A phone browser tab dies at a few hundred megabytes. Do not keep decoded images you do not draw, free large arrays by dropping references, and test the heaviest scene, not the menu.

## Report
State the measurement: "report generation 41 s to 3 s on 100k rows: replaced the per-row query with one grouped query". Say what you did not optimize and why.

## Good and bad examples

### 1. Measuring
Bad: "I think this loop is slow" and a rewrite.
Good: time it, change one thing, time it again.
```python
# check: runs
import time

def timed(fn, *args, repeat=5):
    best = float("inf")
    for _ in range(repeat):
        t = time.perf_counter()
        fn(*args)
        best = min(best, time.perf_counter() - t)
    return best

assert timed(sum, range(1000)) >= 0
```

### 2. Repeated work
Bad: the same Fibonacci value is computed again and again (exponential time).
Good: remember results.
```python
# check: runs
from functools import lru_cache

calls = 0

@lru_cache(maxsize=None)
def fib(n):
    global calls
    calls += 1
    return n if n < 2 else fib(n - 1) + fib(n - 2)

assert fib(80) == 23416728348467685
assert calls == 81                      # every value was computed once
```

### 3. Building strings
Bad: `text += piece` in a loop copies the string every time.
Good:
```python
# check: runs
parts = [str(i) for i in range(1000)]
assert "".join(parts) == "".join(str(i) for i in range(1000))
```

### 4. Lookups
Bad: `if name in names_list` inside a loop over 100,000 names.
Good: `names = set(names_list)` once, then `if name in names`.

### 5. The browser
Bad: read and write the DOM alternately in a loop, which forces layout each time.
Good: read everything first, then write; or build a `DocumentFragment` and insert it once.
```js
// check: syntax
function fill(list, rows) {
  const frag = document.createDocumentFragment();
  for (const r of rows) {
    const li = document.createElement("li");
    li.textContent = r;
    frag.appendChild(li);
  }
  list.appendChild(frag);
}
```

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Optimizing code that takes 1% of the time | Profile (`python3 -m cProfile -s cumtime app.py`) and fix the top entry |
| Cache that never expires | Set a size or a time limit; say what invalidates it |
| Loading a whole file to read one line | Iterate over the file lazily |
| Redrawing every frame when nothing changed | Redraw only when state changes |
| Many small network calls | Batch them, or request only what you need |
| Timers and listeners left running | Clear them when a screen closes |

## Checklist before you finish
- [ ] I measured before and after, and the change helped.
- [ ] The result is still correct: tests pass.
- [ ] No safety check was removed for speed.
- [ ] The report gives the numbers and the conditions.
