---
name: performance-skill
description: Make slow code fast by measuring first: timeit and cProfile, algorithmic fixes (sets, dicts, caching), I/O and database batching, front-end rendering costs, memory limits on phones. Runnable examples.
---
# Performance skill

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
