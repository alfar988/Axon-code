"""Terminal UI: colors, spinner, markdown rendering, panels, progress."""

import os
import re
import shutil
import sys
import textwrap
import threading
import time
import unicodedata
from pathlib import Path


try:
    import readline  # input history, line editing, Tab completion
    HAS_READLINE = True
except Exception:  # pragma: no cover
    readline = None
    HAS_READLINE = False


IS_TTY = sys.stdout.isatty()


USE_COLOR = (IS_TTY or bool(os.environ.get("FORCE_COLOR"))) and not os.environ.get("NO_COLOR")


ANSI_RE = re.compile(r"\033\[[0-9;]*m")


C_ACC = (38, 5, 80)


C_VIO = (38, 5, 110)


C_OK = (38, 5, 114)


C_WARN = (38, 5, 214)


C_ERR = (38, 5, 203)


C_DIM = (38, 5, 245)


C_FAINT = (38, 5, 239)


C_TEXT = (38, 5, 252)


C_CODE = (38, 5, 180)


C_KW = (38, 5, 173)


C_STR = (38, 5, 114)


C_NUM = (38, 5, 215)


C_COM = (38, 5, 243)


C_USER = (38, 5, 80)


def paint(text, *codes):
    if not USE_COLOR or not codes:
        return text
    return "\033[" + ";".join(str(c) for c in codes) + "m" + text + "\033[0m"


def acc(t): return paint(t, *C_ACC)


def vio(t): return paint(t, *C_VIO)


def ok(t): return paint(t, *C_OK)


def warn(t): return paint(t, *C_WARN)


def err(t): return paint(t, *C_ERR)


def dim(t): return paint(t, *C_DIM)


def faint(t): return paint(t, *C_FAINT)


def bold(t): return paint(t, 1)


def italic(t): return paint(t, 3)


def vlen(s):
    """Display width of a string (ignores color codes, counts wide characters)."""
    s = ANSI_RE.sub("", str(s))
    n = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        n += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return n


def tw():
    return max(30, min(shutil.get_terminal_size((60, 24)).columns, 100))


def clip(s, n):
    s = str(s)
    return s if vlen(s) <= n else s[: max(0, n - 1)] + "…"


def short_path(p):
    s = str(p)
    home = str(Path.home())
    if s == home:
        return "~"
    if s.startswith(home + os.sep):
        s = "~" + s[len(home):]
    return s


def out(s=""):
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def rl(prompt):
    """Wrap color codes so readline measures the prompt width correctly."""
    if not (HAS_READLINE and USE_COLOR and sys.stdin.isatty()):
        return prompt
    return re.sub(r"(\033\[[0-9;]*m)", "\001\\1\002", prompt)


class Spinner:
    FR = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label="thinking"):
        self.label = label
        self._ev = threading.Event()
        self._t = None
        self.active = False
        self.t0 = time.time()

    def _run(self):
        i = 0
        while not self._ev.is_set():
            el = int(time.time() - self.t0)
            hint = "  Ctrl+C cancels" if el >= 6 else ""
            sys.stdout.write("\r\033[K  " + acc(self.FR[i % len(self.FR)]) + " "
                             + dim("%s… %ds%s" % (self.label, el, hint)))
            sys.stdout.flush()
            i += 1
            self._ev.wait(0.09)
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def start(self):
        if not IS_TTY or self.active:
            return
        self.active = True
        self._ev.clear()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def stop(self):
        if self.active:
            self._ev.set()
            if self._t:
                self._t.join()
            self.active = False


# --- light syntax highlighting ----------------------------------------------
_KW = {
    "py": "False None True and as assert async await break class continue def del elif else except finally for "
          "from global if import in is lambda nonlocal not or pass raise return try while with yield self print",
    "js": "async await break case catch class const continue default delete do else export extends finally for "
          "function if import in instanceof let new of return static super switch this throw try typeof var void "
          "while yield null true false undefined",
    "lua": "and break do else elseif end false for function goto if in local nil not or repeat return then true "
           "until while",
    "sh": "if then else elif fi for while do done case esac function in return export local echo cd exit",
    "c": "abstract break case catch class const continue default do else enum extends false final finally for "
         "fun func fn if implements import in instanceof interface let match mut namespace new null override "
         "package private protected public return static struct super switch this throw true try val var void "
         "when while use using",
    "json": "true false null",
    "css": "important",
    "html": "",
}


_LANG = {"python": "py", "py": "py", "javascript": "js", "js": "js", "jsx": "js", "ts": "js",
         "typescript": "js", "tsx": "js", "json": "json", "lua": "lua", "luau": "lua", "bash": "sh",
         "sh": "sh", "shell": "sh", "zsh": "sh", "html": "html", "xml": "html", "css": "css",
         "java": "c", "kotlin": "c", "kt": "c", "c": "c", "cpp": "c", "cs": "c", "csharp": "c",
         "go": "c", "rust": "c", "rs": "c", "php": "c", "swift": "c", "gradle": "c"}


_COMMENT = {"py": r"#.*$", "sh": r"#.*$", "js": r"//.*$", "c": r"//.*$", "lua": r"--.*$",
            "css": r"/\*.*?\*/", "html": r"<!--.*?-->", "json": None}


_TOK_CACHE = {}


def _tok_re(kind):
    if kind in _TOK_CACHE:
        return _TOK_CACHE[kind]
    parts = []
    if _COMMENT.get(kind):
        parts.append("(?P<c>%s)" % _COMMENT[kind])
    if kind == "html":
        parts.append(r"(?P<t></?[A-Za-z][^>]*>)")
    if kind == "json":
        parts.append(r'(?P<k>"(?:\\.|[^"\\])*"(?=\s*:))')
    parts.append(r"""(?P<s>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)""")
    parts.append(r"(?P<n>\b\d+(?:\.\d+)?\b)")
    parts.append(r"(?P<w>[A-Za-z_][A-Za-z0-9_]*)")
    rx = re.compile("|".join(parts))
    _TOK_CACHE[kind] = rx
    return rx


def highlight(line, lang):
    kind = _LANG.get((lang or "").lower())
    if not USE_COLOR:
        return line
    if not kind:
        return paint(line, *C_CODE)
    kws = set(_KW.get(kind, "").split())

    def rep(m):
        g, t = m.lastgroup, m.group(0)
        if g == "c":
            return paint(t, *C_COM)
        if g == "s":
            return paint(t, *C_STR)
        if g in ("t", "k"):
            return paint(t, *C_ACC)
        if g == "n":
            return paint(t, *C_NUM)
        if g == "w" and t in kws:
            return paint(t, *C_KW)
        return t
    return _tok_re(kind).sub(rep, line)


def inline_md(s):
    s = re.sub(r"`([^`]+)`", lambda m: paint(m.group(1), *C_CODE), s)
    s = re.sub(r"\*\*([^*]+)\*\*", lambda m: paint(m.group(1), 1), s)
    s = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", lambda m: paint(m.group(1), 3), s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
               lambda m: m.group(1) + " " + dim("(" + m.group(2) + ")"), s)
    return s


def render_table(raw_rows):
    rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in raw_rows]

    def is_sep(cells):
        return any(cells) and all(re.match(r"^:?-+:?$", c) for c in cells if c)

    if len(rows) >= 2 and is_sep(rows[1]):
        header, body = rows[0], rows[2:]
    else:
        header, body = None, [r for r in rows if not is_sep(r)]
    allrows = ([header] if header else []) + body
    if not allrows:
        return []
    n = max(len(r) for r in allrows)
    allrows = [r + [""] * (n - len(r)) for r in allrows]

    def plain(c):
        return re.sub(r"\[([^\]]+)\]\([^)]*\)|[`*]", lambda m: m.group(1) or "", c)

    widths = [max(vlen(plain(r[i])) for r in allrows) for i in range(n)]
    avail = tw() - 4 - (3 * n + 1)
    while sum(widths) > avail:
        i = widths.index(max(widths))
        if widths[i] <= 4:
            break
        widths[i] -= 1

    def line(cells, head=False):
        parts = []
        for i, c in enumerate(cells):
            t = clip(plain(c), widths[i])
            t += " " * (widths[i] - vlen(t))
            parts.append(bold(paint(t, *C_ACC)) if head else t)
        return faint("  │ ") + faint(" │ ").join(parts) + faint(" │")

    res = [faint("  ┌─" + "─┬─".join("─" * w for w in widths) + "─┐")]
    start = 0
    if header:
        res.append(line(allrows[0], head=True))
        res.append(faint("  ├─" + "─┼─".join("─" * w for w in widths) + "─┤"))
        start = 1
    for r in allrows[start:]:
        res.append(line(r))
    res.append(faint("  └─" + "─┴─".join("─" * w for w in widths) + "─┘"))
    return res


class MdStream:
    """Render markdown line by line (suited to streaming): headings, lists, code, tables."""

    def __init__(self):
        self.buf = ""
        self.in_code = False
        self.lang = ""
        self.table = []

    def feed(self, text):
        self.buf += text
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self._line(line)

    def flush(self):
        if self.buf:
            self._line(self.buf)
            self.buf = ""
        self._flush_table()
        if self.in_code:
            self.in_code = False
            out(faint("  ╰─"))

    def _flush_table(self):
        if self.table:
            rows, self.table = self.table, []
            for l in render_table(rows):
                out(l)

    def _line(self, line):
        st = line.strip()
        if not self.in_code and st.startswith("|") and st.count("|") >= 2:
            self.table.append(st)
            return
        self._flush_table()
        if st.startswith("```"):
            if not self.in_code:
                self.in_code = True
                rest = st[3:].strip()
                self.lang = rest.split()[0] if rest else ""
                out(faint("  ╭─ ") + dim(self.lang or "code"))
            else:
                self.in_code = False
                out(faint("  ╰─"))
            return
        if self.in_code:
            out(faint("  │ ") + highlight(line, self.lang))
            return
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            lvl, txt = len(m.group(1)), m.group(2).strip()
            if lvl == 1:
                out()
                out(bold(paint(txt, *C_ACC)))
                out(faint("─" * min(vlen(txt), tw() - 2)))
            elif lvl == 2:
                out()
                out(bold(paint(txt, *C_ACC)))
            else:
                out(bold(txt))
            return
        m = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        if m:
            out(m.group(1) + acc("•") + " " + inline_md(m.group(2)))
            return
        m = re.match(r"^(\s*)(\d+)[.)]\s+(.*)$", line)
        if m:
            out(m.group(1) + acc(m.group(2) + ".") + " " + inline_md(m.group(3)))
            return
        if re.match(r"^\s*([-*_])\1{2,}\s*$", line):
            out(faint("─" * min(tw() - 2, 40)))
            return
        if st.startswith(">"):
            out(faint("▎ ") + dim(inline_md(st.lstrip("> "))))
            return
        out(inline_md(line))


# --- extra UI components (Axion Code) ---------------------------------------
def rule(label="", col=None):
    w = min(tw(), 64) - 2
    if label:
        head = "─ " + label + " "
        return ("  " + paint("─ ", *C_FAINT) + bold(paint(label, *(col or C_ACC)))
                + paint(" " + "─" * max(0, w - vlen(head)), *C_FAINT))
    return "  " + faint("─" * w)


def progress_bar(done, total, width=10):
    total = max(total, 1)
    n = max(0, min(width, int(round(width * done / float(total)))))
    return paint("▰" * n, *C_OK) + faint("▱" * (width - n))


def panel(title, rows, col=None):
    """Draw a box. rows = [(text, color_or_None)]. Returns a list of lines."""
    col = col or C_ACC
    W = min(tw(), 62)
    inner = W - 6
    t = clip(title, inner - 2)
    lines = ["  " + paint("╭─ ", *col) + bold(paint(t, *col))
             + paint(" " + "─" * max(0, W - 7 - vlen(t)) + "╮", *col)]
    for text, c in rows:
        if text == "":
            wrapped = [""]
        else:
            ind = "  " if (text.startswith(("• ", "- ", "· ")) or re.match(r"^\d+\. ", text)) else ""
            wrapped = textwrap.wrap(text, inner, subsequent_indent=ind) or [""]
        for w_ in wrapped:
            pad = " " * max(0, inner - vlen(w_))
            body = paint(w_, *c) if c else w_
            lines.append("  " + paint("│ ", *col) + body + pad + paint(" │", *col))
    lines.append("  " + paint("╰" + "─" * (W - 4) + "╯", *col))
    return lines


def fit_path(p, n):
    s = short_path(p)
    if vlen(s) <= n:
        return s
    parts = s.split("/")
    tail = parts[-1]
    for seg in reversed(parts[:-1]):
        cand = seg + "/" + tail
        if vlen("…/" + cand) > n:
            break
        tail = cand
    r = "…/" + tail
    return r if vlen(r) <= n else "…" + s[-(max(n, 2) - 1):]


def short_model(m):
    return str(m).split("/")[-1].replace(":free", "")

