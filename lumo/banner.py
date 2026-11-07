"""Startup banner: the LUMO wordmark drawn with half-block characters and a light-to-cool color gradient.

The logo has two sizes (34 and 23 columns wide) so it fits a phone terminal, and a plain ASCII version for
terminals that cannot show Unicode. Color is used only when the terminal supports it (NO_COLOR is respected).
"""

import os
import sys

from lumo.config import VERSION
from lumo.ui import ANSI_RE, USE_COLOR, bold, dim, faint, vlen


# Each glyph is a bitmap: '#' = lit pixel. Two pixel rows become one text row (upper half, lower half, full block).
BIG = {   # 8 pixel rows -> 4 text rows, 7 columns per letter
    "L": ["##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "#######"],
    "U": ["##...##", "##...##", "##...##", "##...##", "##...##", "##...##", ".#####.", "..###.."],
    "M": ["##...##", "###.###", "#######", "##.#.##", "##...##", "##...##", "##...##", "##...##"],
    "O": ["..###..", ".#####.", "##...##", "##...##", "##...##", "##...##", ".#####.", "..###.."],
}
SMALL = {  # 6 pixel rows -> 3 text rows, 5 columns per letter
    "L": ["#....", "#....", "#....", "#....", "#....", "#####"],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", ".###."],
}
WORD = "LUMO"
GAP = {"big": 2, "small": 1}

# Light to cool: ice cyan, soft blue, pale violet. One warm spark (gold) as the single accent.
STOPS = ((127, 227, 255), (122, 162, 255), (196, 161, 255))
SPARK = (255, 212, 121)
TRUECOLOR = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")


def _utf8():
    enc = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
    return enc.startswith("utf8")


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _gradient(t):
    t = min(max(t, 0.0), 1.0) * (len(STOPS) - 1)
    i = min(int(t), len(STOPS) - 2)
    return _lerp(STOPS[i], STOPS[i + 1], t - i)


def _to256(rgb):
    r, g, b = rgb
    cube = [0, 95, 135, 175, 215, 255]

    def near(v):
        return min(range(6), key=lambda i: abs(cube[i] - v))
    ri, gi, bi = near(r), near(g), near(b)
    cube_rgb = (cube[ri], cube[gi], cube[bi])
    gray = round((r + g + b) / 3.0)
    gi2 = max(0, min(23, int(round((gray - 8) / 10.0))))
    gray_rgb = (8 + 10 * gi2,) * 3
    dist = lambda p: sum((p[i] - rgb[i]) ** 2 for i in range(3))
    return 232 + gi2 if dist(gray_rgb) < dist(cube_rgb) else 16 + 36 * ri + 6 * gi + bi


def _fg(rgb, text):
    if not USE_COLOR:
        return text
    code = "38;2;%d;%d;%d" % rgb if TRUECOLOR else "38;5;%d" % _to256(rgb)
    return "\033[" + code + "m" + text + "\033[0m"


def _shade(rgb, k):
    return tuple(max(0, min(255, int(v * k))) for v in rgb)


def _bitmap(size):
    glyphs = BIG if size == "big" else SMALL
    rows = len(glyphs["L"])
    out = ["" for _ in range(rows)]
    for n, ch in enumerate(WORD):
        for r in range(rows):
            out[r] += glyphs[ch][r] + (" " * GAP[size] if n < len(WORD) - 1 else "")
    return out


def _half_blocks(bits):
    """Two bitmap rows -> one text row of upper-half, lower-half and full block characters."""
    text = []
    for r in range(0, len(bits), 2):
        top, bot = bits[r], bits[r + 1]
        text.append("".join("█" if (t == "#" and b == "#") else "▀" if t == "#" else "▄" if b == "#" else " "
                            for t, b in zip(top, bot)))
    return text


def wordmark(width):
    """The logo as colored text lines (no indent). Returns [] when the terminal is too narrow."""
    size = "big" if (width >= 38 and _utf8()) else "small"
    bits = _bitmap(size)
    if width < len(bits[0]) + 2:
        return []
    if not _utf8():
        return ["".join(c if c == " " else "#" for c in row) for row in bits]
    text = _half_blocks(bits)
    w, h = len(text[0]), len(text)
    lines = []
    for r, row in enumerate(text):
        cells = []
        for x, ch in enumerate(row):
            if ch == " ":
                cells.append(" ")
                continue
            rgb = _shade(_gradient(x / float(max(1, w - 1))), 1.0 - 0.16 * (r / float(max(1, h - 1))))
            cells.append(_fg(rgb, ch))
        lines.append("".join(cells))
    return lines


def beam(width):
    """A thin ray of light under the wordmark: bright at the spark, fading to the right."""
    if not _utf8():
        return "-" * width
    parts = [_fg(SPARK, "✦")]
    n = max(4, width - 2)
    for i in range(n):
        t = i / float(max(1, n - 1))
        ch = "━" if t < 0.62 else ("─" if t < 0.86 else "╌")
        parts.append(_fg(_shade(_gradient(t), 1.0 - 0.55 * t), ch))
    return "".join(parts)


def header_lines(width):
    """Everything above the settings rows: wordmark, beam, product line. Each line starts with two spaces."""
    mark = wordmark(width)
    lines = []
    if mark:
        lines += ["  " + l for l in mark]
        lines.append("  " + beam(vlen(mark[0])))
        lines.append("")
    title = "  " + bold("Lumo Code") + dim("  v" + VERSION) + faint("  ·  ") + dim("AI coding agent for the terminal")
    lines.append(title if vlen(title) <= width else "  " + bold("Lumo Code") + dim("  v" + VERSION))
    return lines


def print_header(out, width):
    for line in header_lines(width):
        out(line)
