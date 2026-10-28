"""Shared helpers: file sizes, diffs, output trimming, dangerous-command detection."""

import difflib
import json
import re
from pathlib import Path

from axion.config import MAX_TOOL_OUTPUT
from axion.ui import clip, dim, err, faint, ok, out, short_path, tw


DANGER_RE = re.compile(
    r"(rm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+(/|~|\$HOME|\*|\.\s|\.$))|\bmkfs|\bdd\s+if=|:\(\)\s*\{|"
    r"chmod\s+-R\s+[0-7]+\s+/|>\s*/dev/(sd|mmc|block)|(curl|wget)[^|]*\|\s*(sudo\s+)?(sh|bash)|"
    r"\b(shutdown|reboot|poweroff)\b|\bpkg\s+uninstall\b|\bformat\b\s+/")


def is_dangerous(cmd):
    return bool(DANGER_RE.search(cmd))


def denied(reason=""):
    return "DENIED by the user." + ((" Reason: " + reason) if reason else
                                   " Do not repeat the same action; ask what the user wants.")


def show_diff(old, new, limit=50):
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=2))
    plus = sum(1 for l in diff[2:] if l.startswith("+"))
    minus = sum(1 for l in diff[2:] if l.startswith("-"))
    out("    " + dim("diff  ") + ok("+%d" % plus) + " " + err("-%d" % minus))
    shown = 0
    for line in diff[2:]:
        if shown >= limit:
            out("    " + dim("… diff truncated"))
            break
        shown += 1
        t = clip(line, tw() - 6)
        if line.startswith("+"):
            out("    " + ok(t))
        elif line.startswith("-"):
            out("    " + err(t))
        else:
            out("    " + faint(t))


def human_size(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%d%s" % (n, u) if u == "B" else "%.1f%s" % (n, u)
        n /= 1024.0
    return "%.1fTB" % n


def to_int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def cap(text, n=MAX_TOOL_OUTPUT):
    if len(text) <= n:
        return text
    h = int(n * 0.7)
    return text[:h] + "\n…[%d characters trimmed]…\n" % (len(text) - n) + text[-(n - h):]


def rel(ctx, path):
    try:
        return str(Path(path).relative_to(ctx.ws)) or "."
    except ValueError:
        return short_path(path)




# ---------------------------------------------------------------------------
#  Normalizing model-supplied lists. Models sometimes send "steps" as ONE string instead of a list; iterating that
#  string splits it into single characters (one "todo" per letter). These helpers never do that.
# ---------------------------------------------------------------------------
TEXT_KEYS = ("content", "title", "step", "text", "task", "description", "name")
_BULLET_RX = re.compile(r"^\s*(?:[-*•–]|\d+[.)]|\(\d+\))\s+")


def item_text(d, keys=TEXT_KEYS):
    """Text of an item: the string itself, or the first non-empty value among keys of a dict."""
    if not isinstance(d, dict):
        return str(d or "").strip()
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def as_items(value):
    """A list from whatever the model sent: a list, a JSON string, bulleted/numbered/multi-line text, or one dict."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        res = []
        for x in value:
            if isinstance(x, str):
                x = _BULLET_RX.sub("", x.strip())
                if len(x) >= 2:
                    res.append(x)
            elif isinstance(x, dict):
                res.append(x)
            elif x not in (None, ""):
                res.append(str(x))
        return res
    if isinstance(value, dict):
        for k in ("items", "steps", "todos", "tasks", "list"):
            if isinstance(value.get(k), (list, str)):
                return as_items(value[k])
        return [value]
    s = str(value).strip()
    if not s:
        return []
    if s[0] in "[{":
        try:
            return as_items(json.loads(s))
        except ValueError:
            pass
    lines = [l for l in re.split(r"\r?\n", s) if l.strip()]
    if len(lines) == 1 and (";" in lines[0] or re.search(r"(?:^|\s)\d+[.)]\s", lines[0])):
        lines = [p for p in re.split(r"\s*;\s*|\s+(?=\d+[.)]\s)", lines[0]) if p.strip()]
    res = [_BULLET_RX.sub("", l).strip() for l in lines]
    return [x for x in res if len(x) >= 2]
