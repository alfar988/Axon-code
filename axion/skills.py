"""Skill system: catalog, automatic router, staged loading and installation."""

import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from axion.config import BUNDLED_SKILLS_DIR, IGNORE_DIRS, SKILLS_DIR
from axion.state import ask, ToolError
from axion.tools.registry import I, S, tool
from axion.ui import clip, dim, out
from axion.util import cap, denied, to_int
from axion.webutil import decode_body, http_fetch, norm_url


# --- tool: skills -----------------------------------------------------------
def parse_frontmatter(text):
    meta, body = {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not m:
        return meta, body
    body = text[m.end():]
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if v in (">", "|", ">-", "|-", ""):
                buf = []
                while i + 1 < len(lines) and (lines[i + 1].startswith((" ", "\t")) or not lines[i + 1].strip()):
                    i += 1
                    buf.append(lines[i].strip())
                v = " ".join(x for x in buf if x)
            meta[k] = v.strip("'\"")
        i += 1
    return meta, body


def safe_name(s):
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(s).strip()).strip("-.").lower()
    return s or "skill"


GH_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?(?:/(tree|blob)/([^/]+)(?:/(.*?))?)?/?(?:[#?].*)?$")


def gh_api(path):
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    info = http_fetch("GET", "https://api.github.com" + path, headers=headers, timeout=30)
    if info["status"] == 403:
        raise ToolError("GitHub API rate limit reached. Set GITHUB_TOKEN or try again later.")
    if info["status"] != 200:
        raise ToolError("GitHub API returned HTTP %s for %s" % (info["status"], path))
    return json.loads(decode_body(info))


def gh_download_dir(owner, repo, path, ref, dest, depth=0, counter=None):
    counter = counter if counter is not None else [0]
    q = "/repos/%s/%s/contents/%s" % (owner, repo, urllib.parse.quote(path))
    q = q.rstrip("/") + ("?ref=" + urllib.parse.quote(ref) if ref else "")
    items = gh_api(q)
    if isinstance(items, dict):
        items = [items]
    dest.mkdir(parents=True, exist_ok=True)
    for it in items:
        name = os.path.basename(it.get("name", ""))
        if not name:
            continue
        if it.get("type") == "file" and it.get("download_url"):
            if it.get("size", 0) > 1000000 or counter[0] >= 60:
                continue
            r = http_fetch("GET", it["download_url"], timeout=30)
            if r["status"] == 200:
                (dest / name).write_bytes(r["body"])
                counter[0] += 1
        elif it.get("type") == "dir" and depth < 2 and name not in IGNORE_DIRS:
            gh_download_dir(owner, repo, it["path"], ref, dest / name, depth + 1, counter)


def install_skill(url, name=None):
    url = str(url).strip()
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    installed = []
    m = GH_RE.match(url)
    if m:
        owner, repo, kind, ref, path = m.group(1), m.group(2), m.group(3), m.group(4), (m.group(5) or "").strip("/")
        if kind == "blob":
            path = path.rsplit("/", 1)[0] if "/" in path else ""
        q = "/repos/%s/%s/contents/%s" % (owner, repo, urllib.parse.quote(path))
        q = q.rstrip("/") + ("?ref=" + urllib.parse.quote(ref) if ref else "")
        items = gh_api(q)
        if isinstance(items, dict):
            items = [items]
        names = {i["name"]: i for i in items}
        targets = []
        if "SKILL.md" in names:
            targets.append((path, name or (path.rsplit("/", 1)[-1] if path else repo)))
        else:
            cands = [i for i in items if i["type"] == "dir" and i["name"] not in IGNORE_DIRS]
            for sub in [i for i in cands if i["name"] == "skills"]:
                sq = "/repos/%s/%s/contents/%s" % (owner, repo, urllib.parse.quote(sub["path"]))
                sq += ("?ref=" + urllib.parse.quote(ref)) if ref else ""
                cands += [i for i in gh_api(sq) if i["type"] == "dir"]
            for c in cands[:30]:
                cq = "/repos/%s/%s/contents/%s" % (owner, repo, urllib.parse.quote(c["path"]))
                cq += ("?ref=" + urllib.parse.quote(ref)) if ref else ""
                try:
                    sub_items = gh_api(cq)
                except ToolError:
                    continue
                if any(i["name"] == "SKILL.md" for i in sub_items):
                    targets.append((c["path"], c["name"]))
                if len(targets) >= 20:
                    break
        if not targets:
            raise ToolError("no SKILL.md found at %s" % url)
        for p, nm in targets:
            dest = SKILLS_DIR / safe_name(nm)
            if dest.exists():
                shutil.rmtree(str(dest))
            gh_download_dir(owner, repo, p, ref, dest)
            installed.append(dest.name)
        return installed
    r = http_fetch("GET", norm_url(url), timeout=30)
    if r["status"] != 200:
        raise ToolError("HTTP %s while downloading %s" % (r["status"], url))
    text = decode_body(r)
    meta, _ = parse_frontmatter(text)
    nm = safe_name(name or meta.get("name") or Path(urllib.parse.urlparse(url).path).parent.name
                   or Path(urllib.parse.urlparse(url).path).stem)
    if not meta:
        text = "---\nname: %s\ndescription: Skill from %s\n---\n\n%s" % (nm, url, text)
    dest = SKILLS_DIR / nm
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text(text, encoding="utf-8")
    return [nm]


@tool("install_skill", "Install a skill from the internet (GitHub repo/folder/SKILL.md URL, or a raw .md URL). A skill is an instruction file that can be loaded with use_skill.",
      {"url": S("URL skill"), "name": S("local name (optional)")}, ["url"])
def t_install_skill(a, ctx):
    url = str(a.get("url", "")).strip()
    okk, why = ask(ctx, "Skill", "installing from the internet", [url, "A skill is third-party instruction text; make sure you trust its source."])
    if not okk:
        return denied(why)
    names = install_skill(url, a.get("name"))
    return "OK: skill installed: %s. Load it with use_skill(name)." % ", ".join(names)


# ---------------------------------------------------------------------------
#  SKILL CATALOG, AUTOMATIC ROUTER, STAGED LOADING
#
#  Built-in skills are .md files in the skills/ folder (next to run.py). skills/manifest.json gives each one a
#  description, a kind and trigger patterns. Kinds:
#    core       compact guide, loaded in full (or its first part) when it matches
#    reference  large guide, loaded in parts: outline + first part now, the rest on demand with use_skill(part=N)
#    external   installed by the user from the internet (~/.axion/skills/<name>/SKILL.md)
# ---------------------------------------------------------------------------
PART_SIZE = 8000          # characters per skill part
MAX_ACTIVE = 3            # skills active per request
_NOT_SKILLS = {"readme", "index", "manifest"}
_STOP = set("this that with from your have will been make like also each more only some such than them then they what which would about "
            "using into when where there their file files code want need please".split())
_MANIFEST = {"mtime": None, "data": {}}
_ENTRY_CACHE = {}
_RX_CACHE = {}
WS_BONUS = {"web": ("frontend-skill", "design-skill"), "python": ("python-skill",), "backend": ("backend-skill",),
            "node": ("frontend-skill", "backend-skill"), "android": ("android-skill",), "roblox": ("roblox-skill",)}


def load_manifest():
    p = BUNDLED_SKILLS_DIR / "manifest.json"
    try:
        mt = p.stat().st_mtime
    except OSError:
        return {}
    if _MANIFEST["mtime"] != mt:
        try:
            _MANIFEST["data"] = json.loads(p.read_text(encoding="utf-8")).get("skills", {})
        except (OSError, ValueError):
            _MANIFEST["data"] = {}
        _MANIFEST["mtime"] = mt
    return _MANIFEST["data"]


def _rx(pat):
    r = _RX_CACHE.get(pat)
    if r is None:
        try:
            r = re.compile(pat, re.I)
        except re.error:
            r = re.compile(r"(?!x)x")
        _RX_CACHE[pat] = r
    return r


def _first_line(body):
    for l in body.splitlines():
        l = l.strip().lstrip("#").strip()
        if l and not l.startswith(("---", "```")):
            return l[:140]
    return "(no description)"


def _bundled_entry(f, man):
    try:
        st = f.stat()
    except OSError:
        return None
    key = str(f)
    sig = (st.st_mtime, st.st_size, id(man))
    cached = _ENTRY_CACHE.get(key)
    if cached and cached[0] == sig:
        return cached[1]
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fm, body = parse_frontmatter(text)
    m = man.get(f.stem, {})
    entry = {"name": f.stem, "desc": m.get("desc") or fm.get("description") or _first_line(body),
             "file": f, "dir": None, "kind": m.get("kind", "reference"), "builtin": True, "size": len(body),
             "match": [(p, float(w)) for p, w in m.get("match", [])], "deny": list(m.get("deny", [])),
             "min": float(m.get("min", 3)), "pri": float(m.get("pri", 0))}
    _ENTRY_CACHE[key] = (sig, entry)
    return entry


def list_skills(ctx=None):
    man = load_manifest()
    items = []
    if BUNDLED_SKILLS_DIR.is_dir():
        for f in sorted(BUNDLED_SKILLS_DIR.glob("*.md")):
            if f.stem.lower() in _NOT_SKILLS:
                continue
            e = _bundled_entry(f, man)
            if e:
                items.append(e)
    order = {"core": 0, "reference": 1}
    items.sort(key=lambda s: (order.get(s["kind"], 2), s["name"]))
    names = {i["name"] for i in items}
    bases = [SKILLS_DIR]
    if ctx is not None:
        bases += [ctx.ws / ".axion" / "skills", ctx.ws / ".kode" / "skills"]
    for base in bases:
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            f = d / "SKILL.md"
            if not f.is_file() or d.name in names:
                continue
            try:
                meta, body = parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            names.add(d.name)
            items.append({"name": d.name, "desc": meta.get("description") or _first_line(body), "file": f, "dir": d,
                          "kind": "external", "builtin": False, "size": len(body), "match": [], "deny": [],
                          "min": 3.0, "pri": 0.0})
    return items


def find_skill(items, name):
    nm = str(name or "").strip()
    low = safe_name(nm)
    for s in items:
        if s["name"] == nm or s["name"] == low:
            return s
    cands = [s for s in items if low and (low in s["name"] or s["name"].replace("-skill", "").replace("skill-", "") == low)]
    cands.sort(key=lambda s: (0 if s["kind"] == "core" else 1, len(s["name"])))
    return cands[0] if cands else None


def skill_body(s):
    text = s["file"].read_text(encoding="utf-8", errors="replace")
    _, body = parse_frontmatter(text)
    return body.strip()


def split_parts(body, size=PART_SIZE):
    """Split at heading/paragraph boundaries; never inside a code block."""
    parts, cur, cur_len, fence = [], [], 0, False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        head = line.startswith("#") and not fence
        if cur and cur_len + len(line) + 1 > size and not fence and (head or not line.strip() or cur_len > size * 1.4):
            parts.append("\n".join(cur).strip())
            cur, cur_len = [], 0
        cur.append(line)
        cur_len += len(line) + 1
    if cur:
        parts.append("\n".join(cur).strip())
    return [p for p in parts if p]


def part_outline(parts, start=2):
    rows = []
    for i, p in enumerate(parts, 1):
        if i < start:
            continue
        heads = [l.lstrip("# ").strip() for l in p.splitlines() if l.startswith("#")][:4]
        rows.append("  part %d: %s" % (i, "; ".join(heads) if heads else clip(p.replace("\n", " "), 60)))
    return "\n".join(rows)


def _tokens(s):
    return {w for w in re.findall(r"[a-z0-9]{4,}", s.lower()) if w not in _STOP}


def workspace_hints(ctx):
    """Cheap fingerprint of the workspace: which kinds of projects live here (cached for 30 s)."""
    now = time.time()
    c = getattr(ctx, "_ws_hints", None)
    if c and now - c[0] < 30:
        return c[1]
    names = set()
    try:
        for p in list(ctx.ws.iterdir())[:200]:
            names.add(p.name.lower())
            if p.is_dir() and p.name not in IGNORE_DIRS:
                try:
                    names.update(q.name.lower() for q in list(p.iterdir())[:60])
                except OSError:
                    pass
    except OSError:
        pass
    ext = {os.path.splitext(n)[1] for n in names}
    kinds = set()
    if "package.json" in names:
        kinds.add("node")
    if {"requirements.txt", "pyproject.toml", "setup.py"} & names or ".py" in ext:
        kinds.add("python")
    if ".html" in ext:
        kinds.add("web")
    if {"build.gradle", "build.gradle.kts", "androidmanifest.xml"} & names:
        kinds.add("android")
    if ext & {".lua", ".luau", ".rbxl", ".rbxlx"}:
        kinds.add("roblox")
    if {"app.py", "server.py", "server.js", "manage.py", "api.py"} & names:
        kinds.add("backend")
    ctx._ws_hints = (now, kinds)
    return kinds


def score_skill(s, t, bonus):
    for d in s["deny"]:
        if _rx(d).search(t):
            return -1.0
    if s["kind"] == "external":
        ov = len(_tokens(s["name"].replace("-", " ") + " " + s["desc"]) & _tokens(t))
        sc = ov * 1.2 if ov >= 3 else 0.0
    else:
        sc = 0.0
        for pat, w in s["match"]:
            if _rx(pat).search(t):
                sc += w
    return sc + bonus.get(s["name"], 0.0)


ERROR_PASTE_RX = re.compile(r"traceback \(most recent|\b\w+error\b *:|uncaught |syntaxerror|cannot find module|command failed|"
                            r"exception in thread|segmentation fault|\bat \S+:\d+:\d+|errno \d+|exit code [1-9]", re.I)


def pick_skills(ctx, text, intent, need_plan=False, phase="build", limit=MAX_ACTIVE):
    """Choose the skills that fit this request. Returns names; user-pinned skills always come first."""
    t = " ".join(str(text or "").lower().split())
    items = list_skills(ctx)
    by_name = {s["name"]: s for s in items}
    steps = len(re.findall(r"\b(lalu|kemudian|terus|setelah itu|dan juga|selain itu|then|and also|after that|afterwards|also)\b", t))
    big = len(t) > 350 or steps >= 2
    bonus = {}
    if need_plan:
        bonus["planning-skill"] = 4.0
        if big or len(t) > 200:
            bonus["skill-planning"] = 3.0
    if big:
        bonus["skill-complex-thinking"] = 3.0
    if ctx.handoff:
        bonus["skill-memory-knowledge-management"] = 3.0
    if ERROR_PASTE_RX.search(text or ""):
        bonus["debug-skill"] = bonus.get("debug-skill", 0.0) + 4.0
    for kind in workspace_hints(ctx):
        for nm in WS_BONUS.get(kind, ()):
            bonus[nm] = bonus.get(nm, 0.0) + 1.2
    scored = []
    for s in items:
        sc = score_skill(s, t, bonus)
        if sc >= s["min"]:
            scored.append((sc + (0.4 if s["kind"] == "core" else 0.0) + s["pri"], s))
    scored.sort(key=lambda x: -x[0])
    ctx.skill_report = [(round(sc, 1), s["name"], s["kind"]) for sc, s in scored[:8]]
    if intent == "chat":
        limit = 1
    elif intent == "task":
        limit = min(limit, 2)
    picked, refs = [], 0
    for _, s in scored:
        if len(picked) >= limit:
            break
        if s["kind"] == "reference":
            if refs >= 2:
                continue
            refs += 1
        picked.append(s["name"])
    picked = [n for n in picked if by_name[n]["kind"] != "reference"] + [n for n in picked if by_name[n]["kind"] == "reference"]
    pinned = [n for n in sorted(ctx.pinned_skills) if n in by_name]
    return pinned + [n for n in picked if n not in pinned][:max(limit, 1)]


def activate_skill(ctx, name):
    """Add a skill to the active set mid-task (for example debug-skill after a failure)."""
    if name in ctx.active_skills or not any(s["name"] == name for s in list_skills(ctx)):
        return False
    ctx.active_skills = list(ctx.active_skills) + [name]
    out("  " + dim("◇ skill: %s (added automatically)" % name))
    return True


def catalog_text(ctx, active=()):
    rows = []
    for s in list_skills(ctx):
        tag = {"core": "", "reference": " [reference, large]", "external": " [installed]"}.get(s["kind"], "")
        rows.append("- %s%s: %s%s" % (s["name"], tag, clip(s["desc"], 130), "  (ACTIVE)" if s["name"] in active else ""))
    return "\n".join(rows) or "(none)"


def render_active_skills(ctx, names, budget):
    """Active-skill text for the system prompt. Small skills in full; large ones as first part + outline."""
    ctx.skill_shown = {}
    if not names:
        return ""
    items = {s["name"]: s for s in list_skills(ctx)}
    blocks, used, later = [], 0, []
    for n in names:
        s = items.get(n)
        if not s:
            continue
        try:
            body = skill_body(s)
        except OSError:
            continue
        parts = split_parts(body)
        if not parts:
            continue
        room = budget - used
        small = len(body) <= max(3000, int(budget * 0.55))
        if small and len(body) <= room:
            blocks.append("### Skill: %s\n%s" % (n, body))
            ctx.skill_shown[n] = len(parts)
            used += len(body)
        elif room >= len(parts[0]) + 400:
            more = part_outline(parts)
            blocks.append("### Skill: %s (part 1 of %d shown)\n%s\n\n"
                          "[More parts. Load the one you need with use_skill(name=\"%s\", part=N) when you reach that stage:\n%s]"
                          % (n, len(parts), parts[0], n, more or "  (none)"))
            ctx.skill_shown[n] = 1
            used += len(parts[0]) + len(more) + 200
        elif room >= 700:
            blocks.append("### Skill: %s (large, NOT preloaded)\nOutline:\n%s\nLoad parts with use_skill(name=\"%s\", part=N) "
                          "before you start the matching stage." % (n, part_outline(parts, 1), n))
            used += min(len(part_outline(parts, 1)), 900) + 200
        else:
            later.append(n)
    if later:
        blocks.append("Also relevant, not preloaded (call use_skill): " + ", ".join(later))
    if not blocks:
        return ""
    return ("## ACTIVE SKILLS (picked automatically for this request; follow them. Parts shown here need no use_skill call)\n"
            + "\n\n".join(blocks))


@tool("use_skill", "Load a skill (built-in or installed). Large skills are split into parts: pass part=2,3,... for the next "
      "ones. name='list' lists every skill.",
      {"name": S("skill name"), "part": I("part number, default 1")}, ["name"])
def t_use_skill(a, ctx):
    items = list_skills(ctx)
    nm = str(a.get("name", "")).strip()
    if nm.lower() in ("list", "all", ""):
        return catalog_text(ctx, ctx.active_skills)
    s = find_skill(items, nm)
    if not s:
        raise ToolError("skill '%s' does not exist. Available: %s" % (nm, ", ".join(x["name"] for x in items) or "-"))
    body = skill_body(s)
    parts = split_parts(body) or [body]
    part = max(1, min(to_int(a.get("part"), 1), len(parts)))
    ctx.loaded_skills.add(s["name"])
    if part <= ctx.skill_shown.get(s["name"], 0):
        return ("(part %d of skill %s is already in your instructions; follow it.%s)"
                % (part, s["name"], (" Next part: part=%d" % (part + 1)) if part < len(parts) else ""))
    head = "[skill %s · part %d/%d]\n" % (s["name"], part, len(parts))
    tail = ""
    if part < len(parts):
        tail = "\n\n[other parts:\n%s\nload with use_skill(name=\"%s\", part=N)]" % (part_outline(parts, part + 1), s["name"])
    extra = ""
    if s.get("dir") and part == 1:
        files = [str(p) for p in sorted(s["dir"].rglob("*")) if p.is_file() and p.name != "SKILL.md"][:40]
        if files:
            extra = "\n\n[Other files in this skill; read them with read_file when needed]\n" + "\n".join(files)
    return cap(head + parts[part - 1] + tail + extra, 16000)
