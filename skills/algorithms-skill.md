---
name: algorithms-skill
description: Solve algorithm and data-structure problems correctly and fast: constraints to complexity target to pattern, brute force first, stress test against it. Tested reference code for binary search on the answer, sliding window, prefix sums, Dijkstra, BFS, union-find, topological sort, DP, intervals, backtracking.
---
# Algorithms skill

Correct first, fast second, and prove both with a test. An algorithm that was never run against a brute force is a guess.

## Quick rules (read first)
1. Read the limits first and turn them into a target: n up to 1e5 needs about O(n log n); n up to 20 allows O(2^n).
2. Write the slow, obviously correct version first. Then improve it, and compare both on many small random inputs.
3. Name the pattern before you code: window, prefix sums, two pointers, heap, BFS or DFS, union-find, binary search on the answer, DP.
4. Test the edges on purpose: empty input, one element, all equal, duplicates, negatives, the largest allowed size.
5. Use integers for exact answers. Never compare floats with `==`. Mind `//` and `%` with negative numbers.
6. Python recursion stops near depth 1000. Use a stack or a loop for deep inputs.
7. Say the time and memory cost in one line when you answer.

## Safety in this skill
- Algorithm practice is always fine. Do not write code whose purpose is to brute-force other people's passwords, tokens, PINs or captchas, or to scan accounts you do not own.

## Method
1. **Read the constraints.** The input size sets the complexity you can afford:
   | n | affordable | typical technique |
   |---|---|---|
   | up to 20 | O(2^n), O(n!) | backtracking, bitmasks |
   | up to 500 | O(n^3) | DP over triples, Floyd-Warshall |
   | up to 5 000 | O(n^2) | DP tables, pairwise loops |
   | up to 200 000 | O(n log n) | sort, heap, binary search, sweep |
   | up to 10^7 | O(n) | one pass, hash map, two pointers |
   | larger | O(log n), O(1) | math, closed form |
2. **Write the brute force first.** Obviously correct, however slow.
3. **Pick the pattern** (table), write the fast version.
4. **Stress test** both on thousands of small random inputs (helper below). The shrunk failing input is the bug report.
5. **Edge cases:** empty, one element, all equal, duplicates, negatives, sorted, reverse sorted, maximum size, no answer.
6. **Report** the code, the complexity with named variables ("O(E log V)") and the check you ran.

## Pattern table
| Signal | Technique |
|---|---|
| sorted data, "first position where..." | binary search; a number with a monotonic `feasible(x)`: binary search on the answer |
| contiguous subarray or substring with a condition | sliding window, or prefix sums + dict when values can be negative |
| pair with a target sum | two pointers on sorted data; unsorted: dict of seen values |
| top k, merge k lists, "earliest first" | heap (`heapq`) |
| shortest path: unweighted / weights >= 0 / negative weights | BFS / Dijkstra / Bellman-Ford |
| "are a and b connected", groups | union-find |
| dependencies, ordering, cycle check | topological sort |
| counting or optimizing over choices with repeated subproblems | DP: state, transition, base case, order |
| next greater or nearest smaller element | monotonic stack |
| overlapping ranges | sort by start, then merge or sweep |
| every combination under constraints, small n | backtracking with pruning |

## Stress test helper
```python
# check: runs
import random

def stress(fast, brute, gen, trials=2000, seed=0):
    """None when both agree on every random case, else the smallest failing input found."""
    rng = random.Random(seed)
    for _ in range(trials):
        case = gen(rng)
        if fast(case) != brute(case):
            return shrink(fast, brute, case)
    return None

def shrink(fast, brute, case):
    """Drop list elements one at a time while the two still disagree."""
    while isinstance(case, list):
        for i in range(len(case)):
            smaller = case[:i] + case[i + 1:]
            if smaller and fast(smaller) != brute(smaller):
                case = smaller
                break
        else:
            break
    return case

def brute_max_sub(a):
    return max(sum(a[i:j]) for i in range(len(a)) for j in range(i + 1, len(a) + 1))

def wrong_max_sub(a):                    # bug: starts at 0, so all-negative lists give 0
    best = cur = 0
    for x in a:
        cur = max(0, cur + x)
        best = max(best, cur)
    return best

bad = stress(wrong_max_sub, brute_max_sub, lambda r: [r.randint(-5, 5) for _ in range(r.randint(1, 6))])
assert bad is not None and len(bad) == 1 and bad[0] < 0        # shrunk to one negative number
```

## Search and windows
```python
# check: runs
from collections import defaultdict

def min_capacity(weights, days):
    """Binary search on the answer: smallest capacity that ships all packages, in order, within `days`."""
    def feasible(cap):
        need, used = 1, 0
        for w in weights:
            if used + w > cap:
                need, used = need + 1, 0
            used += w
        return need <= days
    lo, hi = max(weights), sum(weights)             # the answer always lies in [max, sum]
    while lo < hi:
        mid = (lo + hi) // 2
        if feasible(mid):
            hi = mid                                # mid works: keep it, try smaller
        else:
            lo = mid + 1
    return lo

def longest_unique(s):
    """Sliding window: longest substring without a repeated character."""
    last, start, best = {}, 0, 0
    for i, ch in enumerate(s):
        if last.get(ch, -1) >= start:
            start = last[ch] + 1
        last[ch] = i
        best = max(best, i - start + 1)
    return best

def count_subarrays(a, k):
    """Prefix sums + dict: contiguous subarrays with sum k (negatives allowed)."""
    seen, total, found = defaultdict(int), 0, 0
    seen[0] = 1
    for x in a:
        total += x
        found += seen[total - k]
        seen[total] += 1
    return found

assert min_capacity([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 5) == 15
assert longest_unique("abcabcbb") == 3 and longest_unique("") == 0
assert count_subarrays([1, 1, 1], 2) == 2 and count_subarrays([1, -1, 0], 0) == 3
```

## Graphs
```python
# check: runs
import heapq
from collections import defaultdict, deque

def dijkstra(graph, src):
    """graph = {u: [(v, weight >= 0), ...]}. Returns {node: shortest distance} for reachable nodes."""
    dist, heap = {src: 0}, [(0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue                                # stale entry: a shorter path was already found
        for v, w in graph.get(u, ()):
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist

def grid_bfs(grid, start, goal):
    """Fewest steps on a grid of '.' and '#' (4 directions), or -1."""
    rows, cols = len(grid), len(grid[0])
    seen, queue = {start}, deque([(start, 0)])
    while queue:
        (r, c), d = queue.popleft()
        if (r, c) == goal:
            return d
        for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] != "#" and (nr, nc) not in seen:
                seen.add((nr, nc))                  # mark when queued, not when popped
                queue.append(((nr, nc), d + 1))
    return -1

class UnionFind:
    def __init__(self, n):
        self.parent, self.size = list(range(n)), [1] * n
    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]        # path halving
            x = self.parent[x]
        return x
    def union(self, a, b):                                      # False when already connected
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        return True

def topo_order(n, edges):
    """Kahn's algorithm: nodes 0..n-1, edge (a, b) means a before b. None when there is a cycle."""
    indeg, adj = [0] * n, defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
        indeg[b] += 1
    queue, order = deque(i for i in range(n) if indeg[i] == 0), []
    while queue:
        u = queue.popleft()
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    return order if len(order) == n else None

g = {"a": [("b", 7), ("c", 9), ("f", 14)], "b": [("c", 10), ("d", 15)], "c": [("d", 11), ("f", 2)], "d": [("e", 6)], "f": [("e", 9)]}
assert dijkstra(g, "a") == {"a": 0, "b": 7, "c": 9, "f": 11, "d": 20, "e": 20}
assert grid_bfs(["..#", ".#.", "..."], (0, 0), (2, 2)) == 4
uf = UnionFind(4)
uf.union(0, 1)
uf.union(2, 3)
assert uf.find(0) == uf.find(1) and uf.find(0) != uf.find(2)
assert topo_order(3, [(0, 1), (1, 2)]) == [0, 1, 2] and topo_order(2, [(0, 1), (1, 0)]) is None
```

## Dynamic programming
Say the state in words first ("best[i] = ... using the first i items"), then the transition, the base case and the order of filling.
```python
# check: runs
from bisect import bisect_left

def coin_min(coins, amount):
    """Fewest coins that make `amount`, or -1."""
    inf = amount + 1
    dp = [0] + [inf] * amount
    for a in range(1, amount + 1):
        for c in coins:
            if c <= a and dp[a - c] + 1 < dp[a]:
                dp[a] = dp[a - c] + 1
    return dp[amount] if dp[amount] != inf else -1

def coin_ways(coins, amount):
    """Number of combinations (order does not matter): coins go in the OUTER loop."""
    dp = [1] + [0] * amount
    for c in coins:
        for a in range(c, amount + 1):
            dp[a] += dp[a - c]
    return dp[amount]

def lis(a):
    """Longest strictly increasing subsequence in O(n log n)."""
    tails = []
    for x in a:
        i = bisect_left(tails, x)
        if i == len(tails):
            tails.append(x)
        else:
            tails[i] = x
    return len(tails)

def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def knapsack(items, capacity):
    """0/1 knapsack over (weight, value): the capacity loop goes DOWN so every item is used at most once."""
    dp = [0] * (capacity + 1)
    for w, v in items:
        for c in range(capacity, w - 1, -1):
            dp[c] = max(dp[c], dp[c - w] + v)
    return dp[capacity]

assert coin_min([1, 2, 5], 11) == 3 and coin_min([2], 3) == -1
assert coin_ways([1, 2, 5], 5) == 4
assert lis([10, 9, 2, 5, 3, 7, 101, 18]) == 4
assert edit_distance("kitten", "sitting") == 3
assert knapsack([(1, 1), (3, 4), (4, 5), (5, 7)], 7) == 9
```
Top-down alternative: `@functools.lru_cache(maxsize=None)` on a pure recursive function; mind Python's recursion limit (about 1000), so use the table for long inputs.

## Intervals, stacks, backtracking
```python
# check: runs
def merge_intervals(intervals):
    out = []
    for start, end in sorted(intervals):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out

def next_greater(a):
    """Monotonic stack: for each element the next larger value to its right, or -1."""
    res, stack = [-1] * len(a), []                  # stack holds indexes still waiting for an answer
    for i, x in enumerate(a):
        while stack and a[stack[-1]] < x:
            res[stack.pop()] = x
        stack.append(i)
    return res

def n_queens(n):
    """Backtracking with pruning: columns and both diagonals are tracked in sets."""
    cols, d1, d2 = set(), set(), set()
    def place(r):
        if r == n:
            return 1
        total = 0
        for c in range(n):
            if c in cols or r - c in d1 or r + c in d2:
                continue
            cols.add(c); d1.add(r - c); d2.add(r + c)
            total += place(r + 1)
            cols.remove(c); d1.remove(r - c); d2.remove(r + c)        # undo the choice
        return total
    return place(0)

assert merge_intervals([[1, 3], [8, 10], [2, 6]]) == [[1, 6], [8, 10]]
assert next_greater([2, 1, 5, 3]) == [5, 5, -1, -1]
assert n_queens(6) == 4 and n_queens(8) == 92
```

## Speed traps
| Slow | Fast |
|---|---|
| `x in some_list`, `list.pop(0)`, `list.insert(0, x)` | `set` or `dict`; `collections.deque` |
| sorting or searching inside a loop | sort once; heap; dict |
| slicing in recursion (`a[1:]` copies) | pass indexes |
| recomputing subproblems | `lru_cache` or a DP table |
| deep recursion in Python (limit about 1000) | explicit stack or iteration |

Already in the standard library: `bisect`, `heapq` (`merge`, `nlargest`), `collections` (`Counter`, `deque`, `defaultdict`), `itertools` (`permutations`, `combinations`, `accumulate`), `math` (`gcd`, `comb`, `isqrt`), `pow(a, b, m)`.
JavaScript: `sort()` compares as strings unless you pass `(a, b) => a - b`; numbers are exact only up to 2^53 (use `BigInt`); `%` keeps the sign of the dividend.

## Good and bad examples

### 1. Finding a pair
Bad: two loops, O(n^2), too slow for 100000 numbers.
```python
def two_sum(nums, target):
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] + nums[j] == target:
                return i, j
```
Good: one pass with a dictionary, O(n).
```python
# check: runs
def two_sum(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        if target - x in seen:
            return seen[target - x], i
        seen[x] = i
    return None

assert two_sum([2, 7, 11, 15], 9) == (0, 1)
assert two_sum([3, 3], 6) == (0, 1)
assert two_sum([1, 2], 7) is None
```
Why: the dictionary answers "have I seen the partner?" in constant time.

### 2. Counting
Bad: `max(set(a), key=a.count)` calls `count` once per distinct value: O(n^2).
Good: count once.
```python
# check: runs
from collections import Counter

def most_common_word(words):
    counts = Counter(words)
    best = max(counts.values())
    return sorted(w for w, c in counts.items() if c == best)[0]

assert most_common_word(["b", "a", "b", "a", "c"]) == "a"
```
Why: one pass builds all counts, and ties are broken in a defined way.

### 3. Money and exact decimals
Bad: `0.1 + 0.2 == 0.3` is False with floats.
Good: count in whole cents, or use `Decimal`.
```python
# check: runs
from decimal import Decimal

total_cents = sum(int(Decimal(p) * 100) for p in ["0.10", "0.20"])
assert total_cents == 30
```

### 4. Deep graphs
Bad: a recursive DFS on a chain of 200000 nodes raises RecursionError.
Good: an explicit stack.
```python
# check: runs
def count_reachable(graph, start):
    seen, stack = {start}, [start]
    while stack:
        node = stack.pop()
        for nxt in graph.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return len(seen)

chain = {i: [i + 1] for i in range(200000)}
assert count_reachable(chain, 0) == 200001
```

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Coding the clever version first | Write brute force first and keep it as the checker |
| Off-by-one in binary search or windows | Use `lo < hi` with `mid = (lo + hi) // 2` consistently and test size 1 and 2 |
| Mutating a list while looping over it | Loop over a copy, or build a new list |
| `if not x` treating 0 as missing | Compare with `is None` when 0 is valid |
| Sorting inside a loop | Sort once outside |
| Using a list for membership tests | Use a set or dict |
| Forgetting the answer can be "none" | Decide the return value for no solution before coding |
| Hidden O(n^2) from `s += piece` or `list.insert(0, x)` | Use `"".join(parts)` and `collections.deque` |

## Checklist before you finish
- [ ] I computed the complexity from the limits and my code meets it.
- [ ] A brute-force version agrees with mine on hundreds of random small inputs.
- [ ] Empty, one-element, duplicate and maximum-size inputs were tried.
- [ ] No float equality, no recursion deeper than 1000, no hidden quadratic loop.
- [ ] The answer states the cost in one line.
