"""The reference code in skills/algorithms-skill.md is checked against brute force on random inputs."""

import itertools
import random
import re
import sys
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "algorithms-skill.md"


def load_namespace():
    ns = {"__name__": "algorithms_skill"}
    text = SKILL.read_text(encoding="utf-8")
    for i, code in enumerate(re.findall(r"```python\n# check: runs\n(.*?)\n```", text, re.S), 1):
        exec(compile(code, "algorithms-skill block %d" % i, "exec"), ns)
    return ns


NS = load_namespace()


class Search(unittest.TestCase):
    def test_min_capacity_matches_a_linear_scan(self):
        rng = random.Random(1)
        for _ in range(400):
            w = [rng.randint(1, 9) for _ in range(rng.randint(1, 8))]
            days = rng.randint(1, len(w))

            def ok(cap):
                need, used = 1, 0
                for x in w:
                    if x > cap:
                        return False
                    if used + x > cap:
                        need, used = need + 1, 0
                    used += x
                return need <= days
            want = next(c for c in range(1, sum(w) + 1) if ok(c))
            self.assertEqual(NS["min_capacity"](w, days), want, (w, days))

    def test_longest_unique_matches_quadratic_brute_force(self):
        rng = random.Random(2)
        for _ in range(500):
            s = "".join(rng.choice("abc") for _ in range(rng.randint(0, 10)))
            want = max([j - i for i in range(len(s)) for j in range(i, len(s) + 1) if len(set(s[i:j])) == j - i] or [0])
            self.assertEqual(NS["longest_unique"](s), want, s)

    def test_count_subarrays_matches_quadratic_brute_force(self):
        rng = random.Random(3)
        for _ in range(500):
            a = [rng.randint(-3, 3) for _ in range(rng.randint(0, 9))]
            k = rng.randint(-4, 4)
            want = sum(1 for i in range(len(a)) for j in range(i + 1, len(a) + 1) if sum(a[i:j]) == k)
            self.assertEqual(NS["count_subarrays"](a, k), want, (a, k))

    def test_stress_helper_finds_nothing_in_correct_code_and_shrinks_bugs(self):
        stress = NS["stress"]
        gen = lambda r: [r.randint(-5, 5) for _ in range(r.randint(1, 6))]
        self.assertIsNone(stress(sorted, lambda a: sorted(a), gen, trials=200))
        self.assertEqual(len(stress(NS["wrong_max_sub"], NS["brute_max_sub"], gen)), 1)


class Graphs(unittest.TestCase):
    def test_dijkstra_matches_floyd_warshall(self):
        rng = random.Random(4)
        inf = float("inf")
        for _ in range(300):
            n = rng.randint(1, 6)
            g, d = {}, [[0 if i == j else inf for j in range(n)] for i in range(n)]
            for u in range(n):
                for v in range(n):
                    if u != v and rng.random() < 0.4:
                        w = rng.randint(0, 9)
                        g.setdefault(u, []).append((v, w))
                        d[u][v] = min(d[u][v], w)
            for k in range(n):
                for i in range(n):
                    for j in range(n):
                        d[i][j] = min(d[i][j], d[i][k] + d[k][j])
            want = {j: d[0][j] for j in range(n) if d[0][j] < inf}
            self.assertEqual(NS["dijkstra"](g, 0), want, g)

    def test_grid_bfs_matches_relaxation(self):
        rng = random.Random(5)
        for _ in range(300):
            rows, cols = rng.randint(1, 4), rng.randint(1, 4)
            grid = ["".join("#" if rng.random() < 0.25 else "." for _ in range(cols)) for _ in range(rows)]
            grid[0] = "." + grid[0][1:]
            grid[-1] = grid[-1][:-1] + "."
            goal = (rows - 1, cols - 1)
            dist = {(0, 0): 0}
            changed = True
            while changed:
                changed = False
                for (r, c), d in list(dist.items()):
                    for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                        if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] != "#" and dist.get((nr, nc), 10 ** 9) > d + 1:
                            dist[(nr, nc)] = d + 1
                            changed = True
            self.assertEqual(NS["grid_bfs"](grid, (0, 0), goal), dist.get(goal, -1), grid)

    def test_union_find_matches_label_propagation(self):
        rng = random.Random(6)
        for _ in range(300):
            n = rng.randint(1, 10)
            uf, label = NS["UnionFind"](n), list(range(n))
            for _ in range(rng.randint(0, 12)):
                a, b = rng.randrange(n), rng.randrange(n)
                merged = label[a] != label[b]
                self.assertEqual(uf.union(a, b), merged)
                if merged:
                    old = label[b]
                    label = [label[a] if x == old else x for x in label]
            for a in range(n):
                for b in range(n):
                    self.assertEqual(uf.find(a) == uf.find(b), label[a] == label[b])

    def test_topo_order_is_valid_and_none_exactly_on_cycles(self):
        rng = random.Random(7)
        for _ in range(300):
            n = rng.randint(1, 6)
            edges = list({(rng.randrange(n), rng.randrange(n)) for _ in range(rng.randint(0, 8))})
            got = NS["topo_order"](n, edges)
            exists = any(all(pos[a] < pos[b] for a, b in edges) for pos in (dict(zip(p, range(n))) for p in itertools.permutations(range(n))))
            if exists:
                self.assertIsNotNone(got, (n, edges))
                pos = {v: i for i, v in enumerate(got)}
                self.assertEqual(sorted(got), list(range(n)))
                self.assertTrue(all(pos[a] < pos[b] for a, b in edges))
            else:
                self.assertIsNone(got, (n, edges))


class Dynamic(unittest.TestCase):
    def test_coin_functions_match_recursion(self):
        rng = random.Random(8)
        for _ in range(200):
            coins = sorted({rng.randint(1, 6) for _ in range(rng.randint(1, 3))})
            amount = rng.randint(0, 15)

            @lru_cache(maxsize=None)
            def fewest(a):
                if a == 0:
                    return 0
                best = [fewest(a - c) for c in coins if c <= a]
                best = [b for b in best if b >= 0]
                return min(best) + 1 if best else -1

            def combos(a, i):
                if a == 0:
                    return 1
                if i == len(coins) or a < 0:
                    return 0
                return combos(a - coins[i], i) + combos(a, i + 1)
            self.assertEqual(NS["coin_min"](coins, amount), fewest(amount), (coins, amount))
            self.assertEqual(NS["coin_ways"](coins, amount), combos(amount, 0), (coins, amount))

    def test_lis_matches_quadratic_dp(self):
        rng = random.Random(9)
        for _ in range(400):
            a = [rng.randint(0, 6) for _ in range(rng.randint(0, 10))]
            best = []
            for i, x in enumerate(a):
                best.append(1 + max([best[j] for j in range(i) if a[j] < x] or [0]))
            self.assertEqual(NS["lis"](a), max(best or [0]), a)

    def test_edit_distance_matches_recursion(self):
        rng = random.Random(10)
        for _ in range(300):
            a = "".join(rng.choice("abc") for _ in range(rng.randint(0, 6)))
            b = "".join(rng.choice("abc") for _ in range(rng.randint(0, 6)))

            @lru_cache(maxsize=None)
            def ed(i, j):
                if i == 0:
                    return j
                if j == 0:
                    return i
                return min(ed(i - 1, j) + 1, ed(i, j - 1) + 1, ed(i - 1, j - 1) + (a[i - 1] != b[j - 1]))
            self.assertEqual(NS["edit_distance"](a, b), ed(len(a), len(b)), (a, b))

    def test_knapsack_matches_subset_enumeration(self):
        rng = random.Random(11)
        for _ in range(300):
            items = [(rng.randint(1, 6), rng.randint(0, 9)) for _ in range(rng.randint(0, 7))]
            cap = rng.randint(0, 15)
            best = 0
            for mask in range(1 << len(items)):
                chosen = [items[i] for i in range(len(items)) if mask >> i & 1]
                if sum(w for w, _ in chosen) <= cap:
                    best = max(best, sum(v for _, v in chosen))
            self.assertEqual(NS["knapsack"](items, cap), best, (items, cap))


class Misc(unittest.TestCase):
    def test_merge_intervals_matches_unit_cell_coverage(self):
        rng = random.Random(12)
        for _ in range(400):
            iv = []
            for _ in range(rng.randint(0, 6)):
                s = rng.randint(0, 9)
                iv.append([s, rng.randint(s + 1, 10)])
            cells = sorted({c for s, e in iv for c in range(s, e)})
            runs = []
            for c in cells:
                if runs and runs[-1][1] == c:
                    runs[-1][1] = c + 1
                else:
                    runs.append([c, c + 1])
            self.assertEqual(NS["merge_intervals"]([list(x) for x in iv]), runs, iv)

    def test_next_greater_matches_quadratic_scan(self):
        rng = random.Random(13)
        for _ in range(400):
            a = [rng.randint(0, 6) for _ in range(rng.randint(0, 9))]
            want = [next((y for y in a[i + 1:] if y > x), -1) for i, x in enumerate(a)]
            self.assertEqual(NS["next_greater"](a), want, a)

    def test_n_queens_counts(self):
        self.assertEqual([NS["n_queens"](n) for n in range(1, 9)], [1, 0, 0, 2, 10, 4, 40, 92])


if __name__ == "__main__":
    unittest.main()
