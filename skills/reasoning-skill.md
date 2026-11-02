---
name: reasoning-skill
description: Answer hard questions correctly (math, logic, probability, estimates, algorithms, trade-offs, "why" questions) by method: restate, pick an approach, compute instead of guessing, cross-check, state assumptions, answer directly. Runnable examples.
---
# Reasoning skill (hard questions)

A fluent answer that was never checked is the usual failure. Work by method, verify by computation, answer short. A question gets an answer: do not turn it into a build, a file or a refactor.

## Protocol
1. **Restate** the question in one line: the unknown, the givens, the constraints and the form of the answer (number, yes/no, proof, recommendation, code). If two readings are plausible, take the most literal one, say which in one line and answer it. Ask only when the readings give different answers and a wrong guess is costly.
2. **Pick the method** from the table and say which one.
3. **Work in small steps** and keep every intermediate value. More than two or three arithmetic steps go to code (`run_python`), never to mental math.
4. **Cross-check by a second route:** brute force on a small case, a bound, a simulation, a limiting case, units. If the routes disagree, find out why before you answer.
5. **Answer first, then why** (shape below).

## Method table
| Question | Method | Cross-check |
|---|---|---|
| Arithmetic, percentages, money, dates | exact types: `int`, `Fraction`, `Decimal`, `datetime` | redo it another way; check units |
| Counting, combinatorics | formula, then enumerate small n | brute-force equality for n = 1..8 |
| Probability, expected value | exact enumeration; else Monte Carlo with a fixed seed and the standard error | probabilities sum to 1; extreme cases |
| Logic puzzle, scheduling, constraints | enumerate and prune with code | test every clue against the result; is it unique? |
| Algorithm, complexity | name the input sizes, derive big-O, write a brute force (see algorithms-skill) | random tests against the brute force |
| Proof, derivation | small cases first, then induction or contradiction; justify every step | plug in numbers |
| Estimate ("how many", "how long") | split into factors, use a low and a high value | order of magnitude, a known reference |
| "Which is better?", design | criteria taken from the user's constraints, compare in a table, recommend, say when the other wins | failure modes, cost at 10x load |
| Facts that change (versions, prices, laws, news) | search (`deep_research`), cite source and date | two independent sources |
| "What does this code do?" | trace by hand, then run it | the run decides |
| "Why does X happen?" | the mechanism in 2 to 4 causal steps, one concrete example | does it predict a case you can test? |

## Compute, do not guess
```python
# check: runs
from fractions import Fraction
from decimal import Decimal
from itertools import product

# Exact probability by enumeration: three dice, sum 10.
hits = sum(1 for d in product(range(1, 7), repeat=3) if sum(d) == 10)
p = Fraction(hits, 6 ** 3)
assert p == Fraction(1, 8)

# Base rate: 1% have the condition, the test finds 90% of them and raises a false alarm for 9% of the rest.
prior, sens, fpr = Fraction(1, 100), Fraction(9, 10), Fraction(9, 100)
posterior = prior * sens / (prior * sens + (1 - prior) * fpr)
assert round(float(posterior), 3) == 0.092            # about 9%, not 90%

# Money is never a float.
assert Decimal("19.99") * 3 == Decimal("59.97") and 0.1 + 0.2 != 0.3
# A closed form is trusted only after it matches brute force on small cases.
assert all(n * (n + 1) * (2 * n + 1) // 6 == sum(i * i for i in range(n + 1)) for n in range(200))
print("p =", p, "| posterior =", round(float(posterior), 3))
```
```python
# check: runs
from itertools import product

# Logic puzzle by enumeration. Knight = always true, knave = always false.
# A: "B is a knave."   B: "A and C are the same type."   C: "A is a knave."
def consistent(a, b, c):                              # True = knight
    return a == (not b) and b == (a == c) and c == (not a)

solutions = [t for t in product([True, False], repeat=3) if consistent(*t)]
assert solutions == [(True, False, False)]            # exactly one: A is a knight, B and C are knaves
print("unique solution:", solutions[0])
```
```python
# check: runs
import math
import random

# Simulation with a fixed seed and an error bar, compared with the exact value (birthday problem, 23 people).
exact = 1 - math.prod((365 - i) / 365 for i in range(23))
rng, n, hit = random.Random(7), 60_000, 0
for _ in range(n):
    hit += len({rng.randrange(365) for _ in range(23)}) < 23
est = hit / n
se = math.sqrt(est * (1 - est) / n)
assert abs(est - exact) < 4 * se, (est, exact, se)
print("exact %.4f  simulated %.4f +/- %.4f" % (exact, est, se))
```
If `run_python` is not available (or the user declined it), do the same check by hand on a small case and show it.

## Traps that cost points
- **Fencepost:** n items have n-1 gaps; `range(a, b)` has b-a items; an inclusive range adds 1.
- **Percent and points:** 10% to 12% is +2 points and +20%. Successive changes multiply (+50% then -50% is -25%).
- **Averages:** speeds over equal distances use the harmonic mean; groups of different size need weights.
- **Floats:** never compare with `==`; money in `Decimal` or integer cents.
- **Modulo and division:** `-7 % 3` is 2 in Python and -1 in JavaScript and C; `//` floors in Python, `Math.trunc` truncates.
- **Time:** time zones, daylight saving, leap years, month lengths. Use explicit zones.
- **Units:** 8 bits per byte; MB (10^6) differs from MiB (2^20).
- **Probability:** multiply only independent events; "at least one" is 1 - P(none); a rare condition with a good test still gives mostly false alarms.
- **Causes:** correlation is not causation; check survivorship and selection before you explain a pattern.

## When you do not know
Say so in one line, then give the quickest way to find out (a search, a command, the number you would need). Never invent figures, version numbers, API names, quotes or sources. Anything that may have changed since your training gets a search first.

## Answer shape (phone screen: short)
```
Answer: one sentence (a yes/no question starts with yes or no).
Why: 3 to 6 lines, only the steps that matter.
Checked: what you verified and how.
Assumptions or limits: only when they exist.
```
Use the user's language and translate the labels. Code questions get the smallest code that works and the output you saw. No praise of the question, no restating all of it, no filler.
