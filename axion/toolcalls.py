"""Tool-call repair: broken or truncated JSON, text-format calls, alias names, history sanitizing."""

import json
import re
import time

from axion.config import WRITE_CHUNK_LINES


TOOL_NAME_ALIASES = {
    "bash": "run_shell", "shell": "run_shell", "sh": "run_shell", "exec": "run_shell", "run": "run_shell",
    "terminal": "run_shell", "read": "read_file", "cat": "read_file", "ls": "list_dir", "list": "list_dir",
    "grep": "search_files", "search": "search_files", "find": "find_files", "glob": "find_files",
    "write": "write_file", "create_file": "write_file", "edit": "edit_file", "str_replace": "edit_file",
    "replace": "edit_file", "fetch": "web_fetch", "browse": "web_fetch", "websearch": "web_search", "research": "deep_research",
    "remember": "learn", "package": "package_info", "pkg_info": "package_info",
    "todowrite": "todo", "todo_write": "todo", "mkdir": "make_dir", "mv": "move_path", "rename": "move_path",
    "cp": "copy_path", "rm": "delete_path", "delete": "delete_path", "unzip": "extract_archive", "zip": "create_archive",
}


ARG_ALIASES = {
    "write_file": {"file": "path", "filename": "path", "file_path": "path", "filepath": "path", "text": "content",
                   "code": "content", "data": "content"},
    "read_file": {"file": "path", "filename": "path", "file_path": "path", "filepath": "path", "from": "start_line",
                  "to": "end_line", "offset": "start_line"},
    "edit_file": {"file": "path", "filename": "path", "file_path": "path", "old": "old_string", "search": "old_string",
                  "find": "old_string", "new": "new_string", "replace": "new_string", "replacement": "new_string"},
    "run_shell": {"cmd": "command", "script": "command", "shell": "command"},
    "list_dir": {"dir": "path", "directory": "path", "folder": "path"},
    "move_path": {"source": "src", "from": "src", "destination": "dst", "to": "dst", "new_name": "dst"},
    "copy_path": {"source": "src", "from": "src", "destination": "dst", "to": "dst"},
    "delete_path": {"file": "path", "target": "path"},
    "todo": {"todos": "items", "tasks": "items"},
    "web_fetch": {"link": "url", "uri": "url"},
    "web_search": {"q": "query", "search": "query", "keywords": "query", "type": "kind", "count": "max_results", "limit": "max_results",
                   "freshness": "time_range"},
    "deep_research": {"query": "question", "q": "question", "topic": "question", "sources": "max_sources"},
    "package_info": {"package": "name", "pkg": "name", "library": "name", "registry": "ecosystem"},
    "learn": {"text": "lesson", "note": "lesson", "content": "lesson", "memory": "lesson"},
    "create_skill": {"title": "name", "text": "content", "body": "content", "skill": "content"},
    "search_files": {"regex": "pattern", "query": "pattern", "text": "pattern", "dir": "path"},
    "find_files": {"glob": "pattern", "name": "pattern"},
}


TOOLCALL_BLOCK = re.compile(r"<tool_call>(.*?)(?:</tool_call>|$)", re.S)


FUNC_BLOCK = re.compile(r"<function=([\w.\-:]+)>(.*?)(?:</function>|$)", re.S)


PARAM_BLOCK = re.compile(r"<parameter=([\w.\-]+)>\s*(.*?)\s*</parameter>", re.S)


KV_BLOCK = re.compile(r"<(?:arg|param)_key>\s*(.*?)\s*</(?:arg|param)_key>\s*<(?:arg|param)_value>(.*?)</(?:arg|param)_value>", re.S)


class TextGate:
    """Filter streamed text: hide <think>...</think> and raw tool-call markup, hold leading whitespace."""
    TOOL_MARKERS = ("<tool_call", "<function=", "[TOOL_CALLS]", "<|tool", "<｜tool")
    ALL = ("<think>", "</think>") + TOOL_MARKERS

    def __init__(self):
        self.pending = ""
        self.in_think = False
        self.blocked = False
        self.shown = False

    def _find(self, buf):
        best = None
        for m in self.ALL:
            j = buf.find(m)
            if j >= 0 and (best is None or j < best[0]):
                best = (j, m)
        return best

    def _hold(self, buf):
        keep = 0
        for m in self.ALL:
            for k in range(min(len(m) - 1, len(buf)), keep, -1):
                if buf.endswith(m[:k]):
                    keep = k
                    break
        return keep

    def feed(self, text):
        if self.blocked:
            return ""
        buf = self.pending + text
        self.pending = ""
        res = []
        while buf:
            hit = self._find(buf)
            if hit is None:
                keep = self._hold(buf)
                safe = buf[:len(buf) - keep] if keep else buf
                self.pending = buf[len(buf) - keep:] if keep else ""
                if not self.in_think:
                    res.append(safe)
                break
            j, m = hit
            if not self.in_think:
                res.append(buf[:j])
            buf = buf[j + len(m):]
            if m == "<think>":
                self.in_think = True
            elif m == "</think>":
                self.in_think = False
            elif not self.in_think:
                self.blocked = True
                break
        vis = "".join(res)
        if not self.shown:
            vis = vis.lstrip()
            if vis:
                self.shown = True
        return vis

    def flush(self):
        if self.blocked or self.in_think:
            return ""
        vis, self.pending = self.pending, ""
        if not self.shown:
            vis = vis.lstrip()
        if vis:
            self.shown = True
        return vis


def strip_think(text):
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    t = re.sub(r"<think>.*$", "", t, flags=re.S)
    return t.replace("</think>", "")


def parse_tool_args(raw, name=None):
    """Backward-compatible wrapper: returns a dict, or raises ValueError when the JSON cannot be repaired."""
    args, status = repair_tool_args(raw, name)
    if args is None or status == "truncated":
        raise ValueError("truncated JSON" if status == "truncated" else "invalid JSON")
    return args


def normalize_tool_name(name, names):
    n = str(name or "").strip()
    if n in names:
        return n
    for sep in (".", ":", "/"):
        if sep in n and n.rsplit(sep, 1)[-1] in names:
            return n.rsplit(sep, 1)[-1]
    low = {x.lower(): x for x in names}
    if n.lower() in low:
        return low[n.lower()]
    alias = TOOL_NAME_ALIASES.get(n.lower())
    return alias if alias in names else None


def fix_args(name, args):
    al = ARG_ALIASES.get(name)
    if al:
        for k in list(args.keys()):
            c = al.get(k)
            if c and c not in args:
                args[c] = args.pop(k)
    return args


def _coerce(v):
    v = v.strip()
    if v[:1] in ("[", "{", '"') or v in ("true", "false", "null") or re.match(r"^-?\d+(\.\d+)?$", v):
        try:
            return json.loads(v)
        except ValueError:
            pass
    return v


def parse_text_tool_calls(text, names):
    """Convert tool calls the model wrote as TEXT (XML/JSON) into structured tool_calls."""
    calls, rest = [], text

    def add(name, args):
        nm = normalize_tool_name(name, names)
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                return False
        if nm and isinstance(args, dict):
            calls.append({"id": "txt_%d_%d" % (int(time.time() * 1000) % 1000000, len(calls)), "type": "function",
                          "function": {"name": nm, "arguments": json.dumps(args, ensure_ascii=False)}})
            return True
        return False

    for m in list(TOOLCALL_BLOCK.finditer(text)):
        body = m.group(1).strip()
        done = False
        if body.startswith("{"):
            try:
                obj = json.loads(body)
                done = add(obj.get("name") or obj.get("function") or "", obj.get("arguments") or obj.get("parameters") or {})
            except ValueError:
                pass
        if not done:
            fm = FUNC_BLOCK.search(body)
            if fm:
                done = add(fm.group(1), {k: _coerce(v) for k, v in PARAM_BLOCK.findall(fm.group(2))})
        if not done:
            nm = re.match(r"\s*([A-Za-z_][\w.\-:]*)", body)
            if nm:
                done = add(nm.group(1), {k.strip(): _coerce(v) for k, v in KV_BLOCK.findall(body)})
        if done:
            rest = rest.replace(m.group(0), "")
    if not calls:
        for m in list(FUNC_BLOCK.finditer(text)):
            if add(m.group(1), {k: _coerce(v) for k, v in PARAM_BLOCK.findall(m.group(2))}):
                rest = rest.replace(m.group(0), "")
    if not calls and "[TOOL_CALLS]" in text:
        try:
            arr = json.loads(text.split("[TOOL_CALLS]", 1)[1].strip())
            for o in (arr if isinstance(arr, list) else [arr]):
                add(o.get("name"), o.get("arguments") or {})
            rest = text.split("[TOOL_CALLS]", 1)[0]
        except (ValueError, AttributeError):
            pass
    if not calls:
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        if t.startswith("{") and '"name"' in t:
            try:
                obj = json.loads(t)
                if add(obj.get("name"), obj.get("arguments") or obj.get("parameters") or {}):
                    rest = ""
            except ValueError:
                pass
    return calls, rest.strip()


def slim_schemas(schemas):
    """Shrink tool schemas (saves tokens) and fix ones that strict providers reject (empty properties)."""
    res = []
    for sc in schemas:
        f = dict(sc["function"])
        d = f.get("description", "")
        f["description"] = d if len(d) <= 260 else d[:257] + "..."
        params = json.loads(json.dumps(f["parameters"]))
        props = params.get("properties") or {}
        if not props:
            params["properties"] = {"reason": {"type": "string", "description": "optional"}}
        for p in props.values():
            if isinstance(p, dict) and len(p.get("description", "")) > 110:
                p["description"] = p["description"][:107] + "..."
        f["parameters"] = params
        res.append({"type": "function", "function": f})
    return res


# ---------------------------------------------------------------------------
#  TOOL-CALL REPAIR (the fix for "Invalid JSON in tool call arguments" and cut-off output)
#
#  Old behavior: a tool call with broken or truncated JSON was stored RAW in the history. The next request
#  made strict providers reject the whole history with HTTP 400, and every fallback model rejected the
#  same history. Now:
#    1. repair_tool_args  repairs JSON (control characters, trailing commas, unescaped quotes in
#                         write_file, truncated output) and reports how much it trusts the result.
#    2. sanitize_messages guarantees that every tool call in the history is valid JSON and has a result.
#    3. chunk limits adapt: when a model hits its output limit we ask for smaller parts from then on.
# ---------------------------------------------------------------------------
_ESC = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


def _unescape_lenient(s):
    def rep(m):
        g = m.group(1)
        if g[0] == "u":
            try:
                return chr(int(g[1:], 16))
            except ValueError:
                return m.group(0)
        return _ESC.get(g, m.group(0))
    return re.sub(r'\\(u[0-9a-fA-F]{4}|["\\/bfnrt])', rep, s)


def _scan(s):
    """JSON scan state: (open-bracket stack, inside a string?, dangling backslash?, comma positions)."""
    stack, in_str, esc, commas = [], False, False, []
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
        elif ch == ",":
            commas.append(i)
    return stack, in_str, esc, commas


def _close_json(s):
    stack, in_str, esc, _ = _scan(s)
    t = s
    if in_str:
        if esc:
            t = t[:-1]
        t += '"'
    t = re.sub(r",\s*$", "", t.rstrip())
    return t + "".join(reversed(stack))


def _unwrap(v):
    if isinstance(v, str):
        try:
            v = json.loads(v, strict=False)
        except ValueError:
            return v
    if isinstance(v, list) and len(v) == 1 and isinstance(v[0], dict):
        return v[0]
    return v


def lenient_write_args(raw):
    """write_file whose content has unescaped quotes (common with HTML). Returns (args, complete?) or None."""
    s = (raw or "").strip()
    mp = re.search(r'"(?:path|file_path|filepath|filename|file)"\s*:\s*"((?:[^"\\]|\\.)*)"', s)
    mc = re.search(r'"(?:content|text|code|data)"\s*:\s*"', s)
    if not mp or not mc or mp.start() > mc.start():
        return None
    body = s[mc.end():]
    tail = re.search(r'"\s*(?:,\s*"append"\s*:\s*(?:true|false)\s*)?\}\s*$', body)
    if tail:
        body = body[:tail.start()]
    else:
        cut = re.search(r'"\s*,\s*"append"\s*:?\s*[a-z]*\s*$', body)
        if cut:  # the content is closed; only the append flag was cut off
            body = body[:cut.start()]
    content = body if body.count("\n") >= 2 else _unescape_lenient(body)
    ma = re.search(r'"append"\s*:\s*(true|false)', s[:mc.start()] + (s[mc.end() + len(body):] if tail else ""))
    args = {"path": _unescape_lenient(mp.group(1)), "content": content}
    if ma:
        args["append"] = ma.group(1) == "true"
    return args, bool(tail)


def repair_tool_args(raw, name=None):
    """Return (dict|None, status). status: ok | repaired | truncated | bad."""
    if isinstance(raw, dict):
        return raw, "ok"
    s = raw.strip() if isinstance(raw, str) else ""
    if not s:
        return {}, "ok"
    s = re.sub(r"\s*```$", "", re.sub(r"^```(?:json)?\s*", "", s))
    try:
        v = _unwrap(json.loads(s))
        if isinstance(v, dict):
            return v, "ok"
    except ValueError:
        pass
    attempts = [lambda: json.loads(s, strict=False),
                lambda: json.JSONDecoder(strict=False).raw_decode(s)[0],
                lambda: json.loads(re.sub(r",\s*([}\]])", r"\1", s), strict=False)]
    for fn in attempts:
        try:
            v = _unwrap(fn())
            if isinstance(v, dict):
                return v, "repaired"
        except ValueError:
            continue
    if name == "write_file":
        r = lenient_write_args(s)
        if r:
            return r[0], ("repaired" if r[1] else "truncated")
    commas = _scan(s)[3]
    for cand in [_close_json(s)] + [_close_json(s[:p]) for p in reversed(commas[-3:])]:
        try:
            v = json.loads(cand, strict=False)
            if isinstance(v, dict):
                return v, "truncated"
        except ValueError:
            continue
    return None, "bad"


def chunk_lines(ctx):
    """Recommended maximum lines per write_file / append_file call for the current model."""
    return ctx.chunk.get(ctx.cur_model(), WRITE_CHUNK_LINES)


def shrink_chunk(ctx):
    """The model hit its output limit: ask for smaller parts from now on (never below 30 lines)."""
    m = ctx.cur_model()
    ctx.chunk[m] = max(30, int(ctx.chunk.get(m, WRITE_CHUNK_LINES) * 0.6))
    return ctx.chunk[m]


def bad_call_message(name, status, finish, limit=None):
    limit = limit or WRITE_CHUNK_LINES
    if status == "truncated" or finish == "length":
        return ("ERROR: your response hit the output limit, so the JSON of '%s' is incomplete and nothing was saved. Do NOT resend "
                "the same large call. Split the content into parts of at most %d lines: write_file for part 1, then append_file for "
                "each following part. Use edit_file for small changes." % (name, limit))
    return ("ERROR: the arguments of '%s' are not valid JSON. Send ONE JSON object; inside strings escape quotes as \\\" and line "
            "breaks as \\n. For long files send smaller parts (at most %d lines each): write_file, then append_file." % (name, limit))


def sanitize_messages(msgs, aggressive=False):
    """Fix the history IN PLACE so strict providers accept it. Returns the number of fixes."""
    fixed = 0
    seen = set()
    origmap = {}
    for m in msgs:
        if m.get("role") != "assistant" or not m.get("tool_calls"):
            continue
        good = []
        for i, tc in enumerate(m["tool_calls"]):
            fn = (tc or {}).get("function") or {}
            nm = fn.get("name")
            if not nm:
                fixed += 1
                continue
            raw = fn.get("arguments")
            args, st = repair_tool_args(raw, nm)
            if args is None:
                args, fixed = {}, fixed + 1
            elif st != "ok" or not isinstance(raw, str):
                fixed += 1
            if aggressive:
                args = {k: ("[%d characters, removed from history]" % len(v) if isinstance(v, str) and len(v) > 400 else v)
                        for k, v in args.items()}
            tid = tc.get("id") or "call_fix_%d_%d" % (len(seen), i)
            if tid in seen:
                tid = "%s_%d" % (tid, len(seen))
                fixed += 1
            seen.add(tid)
            origmap[(id(m), tid)] = tc.get("id")
            good.append({"id": tid, "type": "function", "function": {"name": nm, "arguments": json.dumps(args, ensure_ascii=False)}})
        if good:
            m["tool_calls"] = good
        else:
            m.pop("tool_calls", None)
            if m.get("content") is None:
                m["content"] = ""
    out_msgs, i = [], 0
    while i < len(msgs):
        m = msgs[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            out_msgs.append(m)
            j, got = i + 1, {}
            while j < len(msgs) and msgs[j].get("role") == "tool":
                got[msgs[j].get("tool_call_id")] = msgs[j]
                j += 1
            for tc in m["tool_calls"]:
                r = got.get(origmap.get((id(m), tc["id"]), tc["id"]))
                if r is None:
                    fixed += 1
                    r = {"role": "tool", "tool_call_id": tc["id"], "content": "(no result: the call was cancelled or interrupted)"}
                else:
                    r["tool_call_id"] = tc["id"]
                    if not isinstance(r.get("content"), str):
                        r["content"] = str(r.get("content") or "")
                out_msgs.append(r)
            fixed += max(0, len(got) - len(m["tool_calls"]))
            i = j
        elif m.get("role") == "tool":
            fixed += 1
            i += 1
        else:
            out_msgs.append(m)
            i += 1
    if len(out_msgs) != len(msgs) or fixed:
        msgs[:] = out_msgs
    return fixed
