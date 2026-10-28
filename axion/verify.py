"""Checks before reporting done: syntax, undefined names, HTML structure, UI review."""

import ast
import builtins
import colorsys
import difflib
import json
import os
import re
import shutil
import subprocess
import time
from html.parser import HTMLParser
from pathlib import Path

from axion.config import HOME_DIR
from axion.security import fs_path
from axion.tools.registry import L, tool
from axion.util import rel


CODE_EXTS = {".py", ".js", ".mjs", ".html", ".htm", ".css", ".sh", ".lua", ".luau", ".ts", ".kt", ".java"}


PLACEHOLDER_RE = re.compile(
    r"(\bTODO\b|\bFIXME\b|lorem ipsum|\.\.\.\s*(sisa|rest|kode|code|lainnya)\b|rest of (the )?(code|file)|"
    r"your code here|isi (sendiri|dengan))", re.I)


def js_balance(code):
    """Check that brackets and quotes balance without node. Returns (line, message) or None."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    i, n, line, prev = 0, len(code), 1, ""
    regex_prev = ("", "(", ",", "=", ":", "[", "!", "&", "|", "?", "{", "}", ";", "+", "-", "*", "%", "<", ">", "~", "^")
    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch == "/" and nxt == "/":
            j = code.find("\n", i)
            i = n if j < 0 else j
            continue
        if ch == "/" and nxt == "*":
            j = code.find("*/", i + 2)
            if j < 0:
                return (line, "unclosed /* comment")
            line += code.count("\n", i, j)
            i = j + 2
            continue
        if ch in "\"'":
            q = ch
            i += 1
            while i < n and code[i] != q:
                if code[i] == "\\":
                    i += 1
                elif code[i] == "\n":
                    return (line, "unterminated string %s" % q)
                i += 1
            i += 1
            prev = "x"
            continue
        if ch == "`":
            i += 1
            while i < n and code[i] != "`":
                if code[i] == "\\":
                    i += 1
                elif code[i] == "\n":
                    line += 1
                i += 1
            if i >= n:
                return (line, "unterminated template string `")
            i += 1
            prev = "x"
            continue
        if ch == "/" and prev in regex_prev:
            j, in_cls = i + 1, False
            while j < n and code[j] != "\n":
                c2 = code[j]
                if c2 == "\\":
                    j += 1
                elif c2 == "[":
                    in_cls = True
                elif c2 == "]":
                    in_cls = False
                elif c2 == "/" and not in_cls:
                    break
                j += 1
            if j < n and code[j] == "/":
                i = j + 1
                prev = "x"
                continue
        if ch in "([{":
            stack.append((ch, line))
        elif ch in ")]}":
            if not stack or stack[-1][0] != pairs[ch]:
                return (line, "unmatched '%s'" % ch)
            stack.pop()
        if not ch.isspace():
            prev = ch
        i += 1
    if stack:
        return (stack[-1][1], "unclosed '%s'" % stack[-1][0])
    return None


def node_check_js(code, module=False):
    """Check syntax with node. None = node is not installed. [] = ok. [(line, message)] = errors."""
    node = shutil.which("node")
    if not node:
        return None
    d = HOME_DIR / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    f = d / ("chk_%d_%d%s" % (os.getpid(), int(time.time() * 1000) % 1000000, ".mjs" if module else ".js"))
    try:
        f.write_text(code, encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=25)
    except Exception:
        return None
    finally:
        try:
            f.unlink()
        except OSError:
            pass
    if r.returncode == 0:
        return []
    stderr = r.stderr or ""
    m = re.search(r":(\d+)\n", stderr)
    ln = int(m.group(1)) if m else 0
    msg = next((l for l in stderr.splitlines() if "Error" in l), "syntax error")
    return [(ln, msg.strip())]


class HtmlChecker(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    OPT_END = {"p", "li", "dt", "dd", "tr", "td", "th", "tbody", "thead", "tfoot", "option", "colgroup",
               "caption", "html", "body", "head"}

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=False)
        self.stack, self.errors, self.scripts, self.refs = [], [], [], []
        self.has_title = self.has_viewport = self.has_doctype = False
        self._script = None

    def handle_decl(self, decl):
        if decl.lower().startswith("doctype"):
            self.has_doctype = True

    def _start(self, tag, attrs, selfclose):
        a = dict((k, v) for k, v in attrs)
        if tag == "title":
            self.has_title = True
        if tag == "meta" and (a.get("name") or "").lower() == "viewport":
            self.has_viewport = True
        if tag in ("script", "link", "img", "source", "audio", "video", "iframe"):
            for k in ("src", "href"):
                if a.get(k):
                    self.refs.append((tag, a[k], self.getpos()[0]))
        if tag == "script" and not selfclose:
            self._script = [a, [], self.getpos()[0]]
        if tag not in self.VOID and not selfclose:
            self.stack.append((tag, self.getpos()[0]))

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def handle_endtag(self, tag):
        if tag == "script" and self._script:
            self.scripts.append((self._script[0], "".join(self._script[1]), self._script[2]))
            self._script = None
        if tag in self.VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for t, ln in self.stack[i + 1:]:
                    if t not in self.OPT_END:
                        self.errors.append("<%s> (line %d) is not closed" % (t, ln))
                del self.stack[i:]
                return
        self.errors.append("</%s> without an opening tag (line %d)" % (tag, self.getpos()[0]))

    def handle_data(self, data):
        if self._script is not None:
            self._script[1].append(data)


def check_js_code(code, label, base_line=0, module=False):
    res = node_check_js(code, module)
    if res is None:
        b = js_balance(code)
        return [("error", "%s:%d: %s" % (label, base_line + b[0] - 1, b[1]))] if b else []
    return [("error", "%s:%d: %s" % (label, base_line + ln - 1 if ln else base_line, msg)) for ln, msg in res]


def check_html(p, text, name):
    issues = []
    low = text.lower()
    full_page = "<html" in low or "<!doctype" in low
    if full_page and "</html>" not in low[-600:]:
        issues.append(("error", "%s: missing closing </html> (the file may be truncated)" % name))
    hc = HtmlChecker()
    try:
        hc.feed(text)
        hc.close()
    except Exception as e:
        issues.append(("error", "%s: HTML could not be parsed: %s" % (name, e)))
        return issues
    for t, ln in hc.stack:
        if t not in HtmlChecker.OPT_END:
            issues.append(("error", "%s:%d: <%s> is not closed before the end of the file" % (name, ln, t)))
    for e in hc.errors[:5]:
        issues.append(("error", "%s: %s" % (name, e)))
    if full_page:
        if not hc.has_doctype:
            issues.append(("warn", "%s: missing <!DOCTYPE html>" % name))
        if not hc.has_title:
            issues.append(("warn", "%s: missing <title>" % name))
        if not hc.has_viewport:
            issues.append(("warn", "%s: missing meta viewport (not mobile-friendly)" % name))
    all_js = ""
    has_three = False
    for tag, ref, ln in hc.refs:
        if tag == "script" and "three" in ref.lower():
            has_three = True
        if re.match(r"^(https?:|//|data:|#|mailto:|tel:|javascript:|blob:)", ref):
            continue
        target = p.parent / ref.split("?")[0].split("#")[0]
        if not target.exists():
            issues.append(("error", "%s:%d: referenced file is missing: %s" % (name, ln, ref)))
    for attrs, code, ln in hc.scripts:
        typ = (attrs.get("type") or "").lower()
        if attrs.get("src"):
            continue
        if typ and typ not in ("module", "text/javascript", "application/javascript"):
            continue
        if not code.strip():
            continue
        all_js += code + "\n"
        issues += check_js_code(code, name, ln, module=(typ == "module"))
    if re.search(r"\bTHREE\.", all_js) and not has_three and not re.search(r"from\s+['\"][^'\"]*three", all_js):
        issues.append(("error", "%s: the code uses THREE but the Three.js library is not loaded (<script src=...three...>)" % name))
    return issues


def verify_paths(ctx, paths):
    """Returns (issues[(level, msg)], number_of_files_checked)."""
    issues, n = [], 0
    for p in paths:
        p = Path(p)
        try:
            if not p.is_file() or p.stat().st_size > 3000000:
                continue
        except OSError:
            continue
        ext = p.suffix.lower()
        name = rel(ctx, p)
        if ext not in CODE_EXTS and ext != ".json":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        n += 1
        if ext == ".py":
            try:
                compile(text, name, "exec")
            except SyntaxError as e:
                issues.append(("error", "%s:%s: %s" % (name, e.lineno, e.msg)))
            else:
                for ln, nm in py_undefined_names(text)[:5]:
                    issues.append(("error", "%s:%d: undefined name '%s'" % (name, ln, nm)))
        elif ext == ".json":
            try:
                json.loads(text)
            except ValueError as e:
                issues.append(("error", "%s: invalid JSON: %s" % (name, e)))
        elif ext in (".js", ".mjs"):
            issues += check_js_code(text, name, 1, module=(ext == ".mjs"))
            issues += js_undefined_issues(text, name)
        elif ext in (".html", ".htm"):
            issues += check_html(p, text, name)
            issues += html_undefined_issues(p, text, name)
        elif ext == ".css":
            if text.count("{") != text.count("}"):
                issues.append(("error", "%s: unbalanced CSS braces (%d open, %d close)" % (name, text.count("{"), text.count("}"))))
        elif ext == ".sh" and shutil.which("bash"):
            r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                issues.append(("error", "%s: %s" % (name, (r.stderr or "shell syntax error").strip().splitlines()[0])))
        if ext in CODE_EXTS and PLACEHOLDER_RE.search(text):
            m = PLACEHOLDER_RE.search(text)
            ln = text.count("\n", 0, m.start()) + 1
            issues.append(("warn", "%s:%d: placeholder or leftover found ('%s')" % (name, ln, m.group(0)[:20])))
    return issues, n


def changed_files(ctx):
    seen, res = set(), []
    for sym, path, _extra in ctx.changes:
        if sym in ("+", "~") and path not in seen:
            seen.add(path)
            if Path(path).is_file():
                res.append(Path(path))
    return res


def file_sig(p):
    try:
        st = Path(p).stat()
        return (st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def format_issues(issues, n):
    if not issues:
        return "OK: %d files checked, no problems" % n
    errs = [m for lv, m in issues if lv == "error"]
    warns = [m for lv, m in issues if lv == "warn"]
    lines = ["ISSUES: %d errors, %d warnings (%d files checked)" % (len(errs), len(warns), n)]
    lines += ["- [error] " + m for m in errs[:15]]
    lines += ["- [warning] " + m for m in warns[:8]]
    return "\n".join(lines)


@tool("verify_files", "Automatically check the files you produced: Python/JS/HTML/JSON/CSS/sh syntax, unclosed HTML tags or truncated files, missing file references, THREE not loaded, placeholders. Without paths it checks every file created or changed in this task.",
      {"paths": L("list of files (optional)")})
def t_verify_files(a, ctx):
    paths = [fs_path(ctx, p, "checking files") for p in (a.get("paths") or [])] or changed_files(ctx)
    if not paths:
        return "OK: no files to check"
    issues, n = verify_paths(ctx, paths)
    return format_issues(issues, n)




# ---------------------------------------------------------------------------
#  Deeper static checks
#    py_undefined_names / js_undefined_calls : names that are used but never defined
#    ui_review                               : responsive, accessibility, contrast, design-quality review of HTML/CSS
# ---------------------------------------------------------------------------
def py_undefined_names(text):
    """Names that are read but never defined, imported or builtin anywhere in the file. [(line, name)]"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names):
            return []
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("exec", "eval", "globals", "locals", "vars", "setattr"):
            return []
    defined = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__", "__builtins__", "__path__", "__package__", "__loader__", "__class__"}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                defined.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            defined.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            defined.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            defined.update(n.names)
        elif isinstance(n, ast.arg):
            defined.add(n.arg)
        elif type(n).__name__ == "MatchAs" and getattr(n, "name", None):
            defined.add(n.name)
        elif type(n).__name__ == "MatchStar" and getattr(n, "name", None):
            defined.add(n.name)
    found = {(n.lineno, n.id) for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in defined}
    return sorted(found)[:10]


JS_GLOBALS = set("""window document console Math JSON Object Array String Number Boolean Date RegExp Error TypeError RangeError Promise Map Set
WeakMap WeakSet Symbol BigInt Proxy Reflect Intl Function parseInt parseFloat isNaN isFinite setTimeout clearTimeout setInterval clearInterval
requestAnimationFrame cancelAnimationFrame requestIdleCallback fetch alert confirm prompt atob btoa encodeURIComponent decodeURIComponent
encodeURI decodeURI structuredClone queueMicrotask AudioContext webkitAudioContext Audio Image Event CustomEvent XMLHttpRequest FormData URL
URLSearchParams Blob File FileReader TextEncoder TextDecoder Worker WebSocket ResizeObserver MutationObserver IntersectionObserver
performance navigator location history localStorage sessionStorage indexedDB crypto getComputedStyle matchMedia addEventListener
removeEventListener dispatchEvent Float32Array Float64Array Uint8Array Uint16Array Uint32Array Int8Array Int16Array Int32Array
ArrayBuffer DataView Path2D OffscreenCanvas createImageBitmap screen innerWidth innerHeight scrollTo scrollBy open close print
require module exports process Buffer setImmediate global globalThis eval escape unescape DOMParser Notification HTMLElement
KeyboardEvent MouseEvent TouchEvent PointerEvent AbortController Headers Request Response BroadcastChannel MessageChannel
EventTarget Element Node NodeList DocumentFragment Option SVGElement CSS getSelection speechSynthesis SpeechSynthesisUtterance""".split())
JS_KEYWORDS = set("""if for while switch catch function return typeof new delete void in of do else case throw try finally with yield await async
import export class super this var let const default break continue instanceof static get set extends constructor""".split())


def js_strip(code):
    """Blank out comments, strings, template literals and regex literals (line structure is preserved)."""
    out_, i, n, prev = [], 0, len(code), ""
    while i < n:
        c = code[i]
        two = code[i:i + 2]
        if two == "//":
            j = code.find("\n", i)
            j = n if j < 0 else j
            out_.append(" " * (j - i)); i = j; continue
        if two == "/*":
            j = code.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out_.append("".join(ch if ch == "\n" else " " for ch in code[i:j])); i = j; continue
        if c in "\"'`":
            q, j = c, i + 1
            while j < n and code[j] != q:
                j += 2 if code[j] == "\\" else 1
            j = min(j + 1, n)
            out_.append(q + "".join(ch if ch == "\n" else " " for ch in code[i + 1:j - 1]) + q); i = j; prev = q; continue
        if c == "/" and (prev in "(,=:[!&|?{};" or prev == "" or prev == "\n"):
            j, cls = i + 1, False
            while j < n and code[j] != "\n":
                if code[j] == "\\": j += 2; continue
                if code[j] == "[": cls = True
                elif code[j] == "]": cls = False
                elif code[j] == "/" and not cls: break
                j += 1
            if j < n and code[j] == "/":
                out_.append(" " * (j + 1 - i)); i = j + 1; prev = "x"; continue
        out_.append(c)
        if not c.isspace():
            prev = c
        i += 1
    return "".join(out_)


def js_defined_names(src):
    d = set()
    def idents(s):
        d.update(re.findall(r"[A-Za-z_$][\w$]*", s))
    for m in re.finditer(r"\b(?:function\*?|class)\s+([A-Za-z_$][\w$]*)", src): d.add(m.group(1))
    for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)", src): d.add(m.group(1))
    for m in re.finditer(r"\b(?:const|let|var)\s*[\[{]([^\]}=]*)[\]}]", src): idents(m.group(1))
    for m in re.finditer(r"(?<![\w$])([A-Za-z_$][\w$]*)\s*=(?![=>])", src): d.add(m.group(1))
    for m in re.finditer(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*:", src): d.add(m.group(1))
    for m in re.finditer(r"function\s*[\w$]*\s*\(([^)]*)\)", src): idents(m.group(1))
    for m in re.finditer(r"\(([^()]*)\)\s*=>", src): idents(m.group(1))
    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*=>", src): d.add(m.group(1))
    for m in re.finditer(r"(?m)(?:^|[;{},])\s*(?:static\s+|async\s+|get\s+|set\s+|\*\s*)*([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{", src):
        if m.group(1) not in JS_KEYWORDS:
            d.add(m.group(1)); idents(m.group(2))
    for m in re.finditer(r"catch\s*\(\s*([\w$]+)", src): d.add(m.group(1))
    for m in re.finditer(r"for\s*\(\s*(?:const|let|var)?\s*([\[{][^\]})]*[\]}]|[\w$]+)\s+(?:of|in)\b", src): idents(m.group(1))
    for m in re.finditer(r"\bimport\s+([^;]*?)\s+from", src): idents(m.group(1))
    return d


def js_undefined_calls(code, extra_defined=(), has_cdn=False):
    """Functions that are called but never defined. Returns ([(name, line)], certain?)."""
    src = js_strip(code)
    certain = not (has_cdn or re.search(r"\b(eval|with)\s*\(|new\s+Function|window\s*\[|globalThis\s*\[", src))
    defined = js_defined_names(src) | set(extra_defined)
    found = {}
    for m in re.finditer(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(", src):
        nm = m.group(1)
        if nm in JS_KEYWORDS or nm in JS_GLOBALS or nm in defined:
            continue
        if has_cdn:
            close = difflib.get_close_matches(nm, list(defined), n=1, cutoff=0.8)
            if not close:
                continue
        found.setdefault(nm, src.count("\n", 0, m.start()) + 1)
    return sorted(found.items(), key=lambda x: x[1])[:8], certain


def html_scripts(text, base_dir):
    """Inline script bodies, local script files, and whether CDN scripts are used."""
    inline, local, cdn = [], [], False
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", text, re.I | re.S):
        attrs, body = m.group(1), m.group(2)
        src = re.search(r"src\s*=\s*[\"']([^\"']+)", attrs, re.I)
        if src:
            if re.match(r"(?:https?:)?//", src.group(1)):
                cdn = True
            else:
                p = (Path(base_dir) / src.group(1).split("?")[0])
                try:
                    if p.is_file():
                        local.append(p.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
        elif body.strip() and not re.search(r"type\s*=\s*[\"'](?:application/(?:ld\+)?json|importmap|text/template)", attrs, re.I):
            inline.append(body)
    return inline, local, cdn


# ------------------------------- UI review ----------------------------------
def _rgb(h):
    h = h.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h[:3])
    if len(h) in (6, 8):
        try:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return None
    return None


_NAMED = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0), "gray": (128, 128, 128), "grey": (128, 128, 128),
          "silver": (192, 192, 192), "navy": (0, 0, 128), "yellow": (255, 255, 0), "blue": (0, 0, 255), "green": (0, 128, 0)}


def parse_color(v, vars_, depth=0):
    v = (v or "").strip().lower()
    for _ in range(6):
        m = re.match(r"var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)$", v)
        if not m:
            break
        nv = vars_.get(m.group(1))
        v = (nv if nv is not None else (m.group(2) or "")).strip().lower()
    if v.startswith("#"):
        return _rgb(v)
    m = re.match(r"rgba?\(\s*([\d.]+%?)[\s,/]+([\d.]+%?)[\s,/]+([\d.]+%?)\s*(?:[,/]\s*([\d.]+%?))?\)", v)
    if m:
        if m.group(4) and float(m.group(4).rstrip("%")) / (100 if m.group(4).endswith("%") else 1) < 0.99:
            return None
        return tuple(int(round(float(x[:-1]) * 2.55)) if x.endswith("%") else int(float(x)) for x in m.groups()[:3])
    m = re.match(r"hsla?\(\s*([\d.]+)(?:deg)?[\s,]+([\d.]+)%[\s,]+([\d.]+)%", v)
    if m:
        h, s, l = float(m.group(1)) / 360.0, float(m.group(2)) / 100.0, float(m.group(3)) / 100.0
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return (int(r * 255), int(g * 255), int(b * 255))
    return _NAMED.get(v)


def _lum(rgb):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def hue_of(rgb):
    h, _l, s = colorsys.rgb_to_hls(*(c / 255.0 for c in rgb))
    return h * 360.0, s


def parse_css(css):
    """Flat [(at_context, selector, {prop: value})]; @keyframes and @font-face are recorded and skipped."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    res, ctxs, depth, cur, i, n = [], [], [], "", 0, len(css)
    while i < n:
        ch = css[i]
        if ch == "{":
            head, cur = cur.strip(), ""
            if head.startswith("@"):
                if head.lower().startswith(("@media", "@supports", "@layer", "@container")):
                    ctxs.append(head.lower()); depth.append(1)
                else:
                    j, lvl = i, 0
                    while j < n:
                        lvl += (css[j] == "{") - (css[j] == "}")
                        j += 1
                        if lvl == 0:
                            break
                    res.append((" ".join(ctxs), head.lower(), {"__at__": "1"}))
                    i = j
                    continue
            else:
                j = css.find("}", i)
                if j < 0:
                    break
                decls = {}
                for part in css[i + 1:j].split(";"):
                    if ":" in part:
                        k, v = part.split(":", 1)
                        decls[k.strip().lower()] = v.strip()
                res.append((" ".join(ctxs), head, decls))
                i = j
        elif ch == "}":
            if ctxs:
                ctxs.pop(); depth.pop()
            cur = ""
        else:
            cur += ch
        i += 1
    return res


_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B06\u2705\u274C\u2728]")


def _strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def ui_review(html, css_extra="", name="page"):
    """Static review of one HTML page (+ its CSS). Returns [(severity, message)] with severity high|medium|low."""
    f = []
    add = lambda sev, msg: f.append((sev, msg))
    css_all = "\n".join(re.findall(r"<style\b[^>]*>(.*?)</style>", html, re.I | re.S)) + "\n" + css_extra
    body_html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.I | re.S)
    rules = parse_css(css_all)
    low_css = css_all.lower()
    has_canvas = bool(re.search(r"<canvas\b", html, re.I))

    # ---- document structure and accessibility
    if not re.search(r"<html[^>]*\blang\s*=", html, re.I):
        add("medium", "<html> has no lang attribute (screen readers and translation need it): <html lang=\"en\">")
    if not re.search(r"<h1\b", body_html, re.I) and not has_canvas:
        add("medium", "no <h1>: every page needs one clear main heading")
    elif len(re.findall(r"<h1\b", body_html, re.I)) > 1:
        add("low", "more than one <h1>; use one and make the rest <h2>")
    if not re.search(r"<main\b", body_html, re.I) and not has_canvas:
        add("low", "no <main> landmark around the primary content")
    imgs = [t for t in re.findall(r"<img\b[^>]*>", body_html, re.I) if not re.search(r"\balt\s*=", t, re.I)]
    if imgs:
        add("medium", "%d <img> without alt text (use alt=\"\" for decorative images)" % len(imgs))
    unlabeled = []
    for m in re.finditer(r"<(button|a)\b([^>]*)>(.*?)</\1>", body_html, re.I | re.S):
        if not _strip_tags(m.group(3)) and not re.search(r"aria-label|title=|aria-labelledby", m.group(2), re.I) and "<img" not in m.group(3).lower():
            unlabeled.append(m.group(1))
    if unlabeled:
        add("medium", "%d icon-only <%s> without aria-label: screen readers announce nothing" % (len(unlabeled), unlabeled[0]))
    label_spans = [(m.start(), m.end()) for m in re.finditer(r"<label\b.*?</label>", body_html, re.I | re.S)]
    label_for = set(re.findall(r"<label[^>]*\bfor\s*=\s*[\"']([^\"']+)", body_html, re.I))
    bad_inputs = 0
    for m in re.finditer(r"<(input|select|textarea)\b([^>]*)>", body_html, re.I):
        at = m.group(2)
        if re.search(r"type\s*=\s*[\"']?(hidden|submit|button|reset|image)", at, re.I) or re.search(r"aria-label|aria-labelledby", at, re.I):
            continue
        idm = re.search(r"\bid\s*=\s*[\"']([^\"']+)", at, re.I)
        if (idm and idm.group(1) in label_for) or any(a <= m.start() < b for a, b in label_spans):
            continue
        bad_inputs += 1
    if bad_inputs:
        add("medium", "%d form field(s) without a <label> (placeholder is not a label)" % bad_inputs)
    if re.search(r"tabindex\s*=\s*[\"']?[1-9]", html, re.I):
        add("low", "positive tabindex breaks the natural keyboard order; use 0 or -1")
    if len(re.findall(r"<(?:div|span)\b[^>]*\bonclick\s*=", body_html, re.I)):
        add("low", "onclick on <div>/<span>: use a <button> so keyboard and screen readers work")

    # ---- responsiveness
    responsive = bool(re.search(r"@media|clamp\(|auto-fit|auto-fill|flex-wrap|min\(\s*\d", low_css))
    if css_all.strip() and not responsive and not has_canvas:
        add("high", "no responsive rules (no @media, clamp(), flex-wrap or auto-fit grid): the layout will break on phones")
    wide = []
    for ctx_, sel, d in rules:
        if "@media" in ctx_ or "__at__" in d:
            continue
        for prop in ("width", "min-width"):
            m = re.match(r"^(\d+(?:\.\d+)?)px$", d.get(prop, ""))
            if m and float(m.group(1)) >= 500 and "max-width" not in d:
                wide.append("%s{%s:%spx}" % (sel.strip()[:30], prop, m.group(1)))
    if wide:
        add("medium", "fixed widths of 500px or more cause horizontal scrolling on phones: %s; use max-width or %%" % ", ".join(wide[:2]))
    if re.search(r"(?<!min-)height\s*:\s*100vh", low_css) and "dvh" not in low_css and "svh" not in low_css:
        add("low", "100vh ignores the mobile browser toolbar; prefer 100dvh with a 100vh fallback")
    small = [d["font-size"] for _c, _s, d in rules if re.match(r"^(?:[0-9]|1[01])(?:\.\d+)?px$", d.get("font-size", ""))]
    if small:
        add("low", "text smaller than 12px (%s) is hard to read on phones" % small[0])

    # ---- states, focus, motion
    if re.search(r"outline\s*:\s*(?:none|0)\b", low_css) and not re.search(r":focus-visible|:focus", low_css):
        add("high", "outline is removed without a replacement focus style: keyboard users cannot see where they are")
    interactive = bool(re.search(r"<(button|a)\b", body_html, re.I))
    if interactive and css_all.strip() and ":hover" not in low_css:
        add("medium", "no :hover styles: buttons and links give no feedback")
    if interactive and css_all.strip() and ":focus-visible" not in low_css and ":focus" not in low_css:
        add("medium", "no :focus-visible styles for keyboard navigation")
    if re.search(r"@keyframes|animation\s*:|transition\s*:", low_css) and "prefers-reduced-motion" not in low_css:
        add("low", "animations without @media (prefers-reduced-motion: reduce) support")

    # ---- contrast (WCAG): resolves CSS variables, light and dark palettes
    light, dark = {}, {}
    for ctx_, sel, d in rules:
        target = dark if ("prefers-color-scheme: dark" in ctx_ or re.search(r"dark", sel, re.I)) else light
        for k, v in d.items():
            if k.startswith("--"):
                target[k] = v
    bad_pairs, seen = [], set()
    for mode, extra in (("light", {}), ("dark", dark)):
        if mode == "dark" and not dark:
            continue
        vars_ = dict(light); vars_.update(extra)
        for ctx_, sel, d in rules:
            if "__at__" in d or "color" not in d:
                continue
            if mode == "light" and "prefers-color-scheme: dark" in ctx_:
                continue
            bg = d.get("background-color") or d.get("background", "")
            mm = re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|var\(--[\w-]+(?:\s*,[^)]*)?\)|\b(?:white|black)\b", bg)
            if not mm:
                continue
            fg_c, bg_c = parse_color(d["color"], vars_), parse_color(mm.group(0), vars_)
            if not fg_c or not bg_c:
                continue
            r = contrast_ratio(fg_c, bg_c)
            size_ok = bool(re.search(r"font-size\s*:\s*(?:[2-9]\d|1[89])px|font-weight\s*:\s*(?:[6-9]00|bold)", " ".join("%s:%s" % kv for kv in d.items())))
            need = 3.0 if size_ok else 4.5
            key = (sel.strip(), mode)
            if r < need and key not in seen:
                seen.add(key)
                bad_pairs.append((r, "%s (%s): %s on %s is %.1f:1, needs %.1f:1" % (sel.strip()[:34], mode, d["color"][:22], mm.group(0)[:22], r, need)))
    for r, msg in sorted(bad_pairs)[:4]:
        add("high" if r < 3 else "medium", "low contrast: " + msg + " (darken the text or lighten the background)")

    # ---- design quality ("generic AI look")
    grads = re.findall(r"linear-gradient\(([^;]*)\)", low_css)
    for g in grads:
        cols = [c for c in (parse_color(x, light) for x in re.findall(r"#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)", g)) if c]
        hues = [hue_of(c) for c in cols]
        if len(hues) >= 2 and all(215 <= h <= 335 and s > 0.3 for h, s in hues[:2]) and any(255 <= h <= 335 for h, s in hues[:2]):
            add("medium", "purple/indigo gradient: the most common generic-AI look; pick one accent color and use flat surfaces")
            break
    if re.search(r"background-clip\s*:\s*text", low_css) and grads:
        add("low", "gradient text is a cliche; use a solid color and let size and weight do the work")
    if low_css.count("backdrop-filter") >= 3 or len(re.findall(r"box-shadow\s*:[^;]*\b0\s+0\s+(?:[4-9]\d|\d{3})px", low_css)) >= 2:
        add("low", "glass/glow effects are overused; keep one subtle shadow style")
    visible_blocks = re.findall(r"<(h[1-6]|button|li|a|th|label)\b[^>]*>(.*?)</\1>", body_html, re.I | re.S)
    emoji_big = sum(1 for t_, inner in visible_blocks if t_.lower() in ("h1", "h2", "h3", "button") and _EMOJI.search(_strip_tags(inner)))
    emoji_any = sum(1 for _t, inner in visible_blocks if _EMOJI.search(_strip_tags(inner)))
    if emoji_big >= 1 or emoji_any >= 2:
        add("medium", "emoji used as icons or in headings/buttons; use inline SVG icons")
    if re.search(r"lorem ipsum|dolor sit amet", body_html, re.I):
        add("high", "placeholder text (lorem ipsum) is still on the page")
    if css_all.strip() and not re.search(r"font-family", low_css):
        add("low", "no font-family set: define a deliberate font stack")
    if re.search(r"comic sans", low_css):
        add("low", "Comic Sans: pick a considered typeface")
    colors = set(re.findall(r"#[0-9a-f]{6}\b|#[0-9a-f]{3}\b", low_css))
    if len(colors) > 14 and "--" not in low_css:
        add("low", "%d different literal colors and no CSS variables; define a small token palette" % len(colors))
    sizes = {d["font-size"] for _c, _s, d in rules if "font-size" in d}
    if len(sizes) > 9:
        add("low", "%d different font sizes; use a type scale of 6 to 8 steps" % len(sizes))

    # ---- canvas / games
    if has_canvas:
        js = "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.I | re.S))
        if "touch-action" not in low_css and "preventDefault" not in js:
            add("medium", "canvas without touch-action:none or preventDefault: scrolling/zooming will fight touch controls")
        if "devicePixelRatio" not in js:
            add("low", "canvas ignores devicePixelRatio: it will look blurry on phones")
        if not re.search(r"addEventListener\(\s*['\"]resize|onresize", js):
            add("medium", "canvas does not handle window resize/rotation")
        if "visibilitychange" not in js and "blur" not in js:
            add("low", "no auto-pause when the tab is hidden (visibilitychange)")
        if "requestAnimationFrame" not in js and "setInterval" in js:
            add("low", "use requestAnimationFrame instead of setInterval for the game loop")
    return f


def ui_score(findings):
    pen = {"high": 14, "medium": 6, "low": 2}
    return max(0, 100 - sum(pen[s] for s, _m in findings))


def review_html_file(ctx, p):
    text = Path(p).read_text(encoding="utf-8", errors="replace")
    extra = ""
    for href in re.findall(r"<link[^>]+rel\s*=\s*[\"']stylesheet[\"'][^>]*href\s*=\s*[\"']([^\"']+)", text, re.I) + \
            re.findall(r"<link[^>]+href\s*=\s*[\"']([^\"']+\.css[^\"']*)[\"'][^>]*rel\s*=\s*[\"']stylesheet", text, re.I):
        if not re.match(r"(?:https?:)?//", href):
            cp = Path(p).parent / href.split("?")[0]
            try:
                if cp.is_file():
                    extra += "\n" + cp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
    return ui_review(text, extra, rel(ctx, Path(p)))


def web_files(ctx, limit=4):
    cands = [p for p in changed_files(ctx) if p.suffix.lower() in (".html", ".htm")]
    if not cands:
        cands = sorted(Path(ctx.ws).glob("*.html"))[:limit]
    return cands[:limit]


def ui_polish_findings(ctx):
    """High/medium findings for the HTML files changed in this task (used by the auto-polish pass)."""
    res = []
    for p in web_files(ctx):
        try:
            fs = review_html_file(ctx, p)
        except OSError:
            continue
        res += ["%s: %s" % (rel(ctx, p), m) for sev, m in fs if sev in ("high", "medium")]
    return res[:8]


@tool("review_ui", "Static UI/UX review of HTML pages: responsiveness, accessibility, WCAG color contrast, interaction states, "
      "canvas/mobile game basics and generic-AI-look detection. Returns prioritized findings with a score; fix every HIGH and "
      "MEDIUM item, then run it again. Without paths it reviews the pages changed in this task.",
      {"paths": L("HTML files to review (optional)")})
def t_review_ui(a, ctx):
    files = [fs_path(ctx, p, "reviewing UI") for p in (a.get("paths") or [])] or web_files(ctx)
    files = [Path(p) for p in files if Path(p).suffix.lower() in (".html", ".htm") and Path(p).is_file()]
    if not files:
        return "OK: no HTML files to review"
    lines, worst = [], 100
    for p in files:
        fs = review_html_file(ctx, p)
        sc = ui_score(fs)
        worst = min(worst, sc)
        lines.append("%s: score %d/100" % (rel(ctx, p), sc))
        order = {"high": 0, "medium": 1, "low": 2}
        for sev, msg in sorted(fs, key=lambda x: order[x[0]])[:12]:
            lines.append("  %-6s %s" % (sev.upper(), msg))
    head = "OK: UI review passed" if worst >= 85 and not any("  HIGH" in l for l in lines) else "REVIEW: improve the items below"
    return head + "\n" + "\n".join(lines)


def js_undefined_issues(code, name, extra=(), has_cdn=False):
    calls, certain = js_undefined_calls(code, extra, has_cdn)
    return [("error" if certain else "warn", "%s:%d: '%s()' is called but never defined (typo, or the function was never written?)"
             % (name, ln, nm)) for nm, ln in calls]


def html_undefined_issues(p, text, name):
    inline, local, cdn = html_scripts(text, Path(p).parent)
    extra = set()
    for code in local + inline:
        extra |= js_defined_names(js_strip(code))
    issues = []
    for code in inline:
        issues += js_undefined_issues(code, name, extra, cdn)
    return issues
