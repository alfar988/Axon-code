"""Research tools: web_search (several providers), deep_research (search, read and extract) and package_info."""

import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from axion import search as engine
from axion.state import ToolError
from axion.tools.registry import I, L, S, tool
from axion.util import cap, to_int
from axion.webutil import fetch_clean


_STOP = set("the a an of to in on for and or is are was were be been by with as at from that this it its how what why when which who "
            "does do did can could should would will i you your my we our about vs versus using use into than then there their "
            "get make best good new latest".split())


def keys_of(ctx):
    """API keys for optional search providers: environment first, then secrets stored with /secret set NAME."""
    secrets = (getattr(ctx, "cfg", None) or {}).get("secrets", {}) or {}
    return {k: secrets[k] for k in engine.KEY_NAMES if secrets.get(k)}


def _as_list(v):
    if isinstance(v, str):
        return [x.strip() for x in re.split(r"[,\n]", v) if x.strip()]
    return [str(x).strip() for x in (v or []) if str(x).strip()]


def keywords(text):
    seen, out = set(), []
    for w in re.findall(r"[a-z0-9][a-z0-9.+#_-]+", str(text).lower()):
        w = w.strip(".-_")
        if len(w) > 2 and w not in _STOP and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def pick_passages(text, kws, budget, each=650):
    """The paragraphs of a page that best match the keywords, in page order, within a character budget."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) >= 40]
    scored = []
    for i, p in enumerate(paras):
        low = p.lower()
        hits = sum(1 for w in kws if w in low)
        if hits:
            scored.append((hits * 2.0 + min(len(p), 600) / 600.0, i))
    if scored:
        chosen = []
        used = 0
        for _sc, i in sorted(scored, key=lambda x: -x[0]):
            piece = _clip(paras[i], each)
            if used + len(piece) > budget:
                continue
            chosen.append(i)
            used += len(piece)
            if used >= budget * 0.9:
                break
        picked = [(_clip(paras[i], each)) for i in sorted(chosen)]
    else:
        picked, used = [], 0
        for p in paras:
            piece = _clip(p, each)
            if used + len(piece) > budget // 2:
                break
            picked.append(piece)
            used += len(piece)
    return picked


def _clip(text, n):
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) <= n:
        return text
    cut = text[:n]
    end = max(cut.rfind(". "), cut.rfind("\n"))
    return (cut[:end + 1] if end > n * 0.5 else cut.rstrip()) + " …"


def _host(url):
    h = urllib.parse.urlsplit(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


@tool("web_search",
      "Search the web. Several providers are tried and merged automatically, so one blocked engine does not stop you. "
      "kind: general (default) | news | code | qa | docs | packages | academic | wiki | discussion. "
      "There is no limit on the number of searches: use short keyword queries, vary the wording, and search again when results are weak. "
      "For anything that needs several sources, call deep_research instead.",
      {"query": S("search keywords, not a full sentence"),
       "kind": S("general | news | code | qa | docs | packages | academic | wiki | discussion"),
       "max_results": I("1 to 30, default 8"),
       "time_range": S("day | week | month | year (optional, for fresh topics)"),
       "site": S("Stack Exchange site for kind=qa, e.g. stackoverflow, superuser, unix (optional)"),
       "lang": S("Wikipedia language code for kind=wiki, default en"),
       "providers": L("force specific providers (optional)")}, ["query"])
def t_web_search(a, ctx):
    q = str(a.get("query", "")).strip()
    kind = str(a.get("kind") or "general").lower()
    if kind not in engine.KINDS:
        raise ToolError("unknown kind %r. Use one of: %s" % (kind, ", ".join(engine.KINDS)))
    found = engine.search(q, kind=kind, n=to_int(a.get("max_results"), 8), time_range=(a.get("time_range") or None),
                          providers=_as_list(a.get("providers")) or None, keys=keys_of(ctx), site=a.get("site"), lang=a.get("lang"))
    return engine.format_results(found, q, kind)


def _auto_queries(question, queries):
    qs = []
    for q in [question] + list(queries):
        q = " ".join(str(q).split())
        if q and q.lower() not in [x.lower() for x in qs]:
            qs.append(q)
    if len(qs) == 1 and len(question.split()) > 7:
        short = " ".join(keywords(question)[:7])
        if short and short.lower() != qs[0].lower():
            qs.append(short)
    return qs[:6]


@tool("deep_research",
      "Research a question across many sources in ONE call: runs several searches in parallel, reads the best pages, and returns "
      "the passages that match your question with source numbers, dates and URLs. Use it for anything that needs current or verified "
      "facts (versions, APIs, comparisons, how-to, news). Give 2 to 5 differently worded `queries` for better coverage. "
      "Answer afterwards with citations like [2], and say what you could not verify.",
      {"question": S("what you need to find out, in one sentence"),
       "queries": L("2 to 5 differently worded search queries (optional but recommended)"),
       "kind": S("general (default) | news | code | qa | docs | academic"),
       "max_sources": I("pages to read, 3 to 10, default 6"),
       "time_range": S("day | week | month | year (optional)"),
       "focus": S("extra words that useful passages should contain (optional)")}, ["question"])
def t_deep_research(a, ctx):
    t0 = time.time()
    question = " ".join(str(a.get("question", "")).split())
    if not question:
        raise ToolError("empty question")
    kind = str(a.get("kind") or "general").lower()
    if kind not in engine.KINDS:
        kind = "general"
    n_src = max(3, min(to_int(a.get("max_sources"), 6), 10))
    tr = a.get("time_range") or None
    keys = keys_of(ctx)
    queries = _auto_queries(question, _as_list(a.get("queries")))
    kws = keywords(question + " " + str(a.get("focus") or ""))

    def run(q):
        try:
            return engine.search(q, kind=kind, n=10, time_range=tr, keys=keys)
        except ToolError as e:
            return {"results": [], "used": [], "notes": [str(e)], "answers": []}

    with ThreadPoolExecutor(max_workers=min(4, len(queries))) as pool:
        found = list(pool.map(run, queries))
    notes, used, answers = [], [], []
    for f in found:
        notes += f["notes"]
        answers += f["answers"]
        used += [p for p in f["used"] if p not in used]
    merged = engine.merge([("q%d" % i, f["results"]) for i, f in enumerate(found)], 40)
    if not merged:
        raise ToolError("no results for any of %d queries (%s)" % (len(queries), "; ".join(notes[:3]) or "nothing found"))
    cands, per_host = [], {}
    for r in merged:                                    # at most two pages per site, so sources stay independent
        h = _host(r["url"])
        if per_host.get(h, 0) < 2:
            per_host[h] = per_host.get(h, 0) + 1
            cands.append(r)
    cands = cands[:n_src + 3]
    with ThreadPoolExecutor(max_workers=min(6, len(cands))) as pool:
        pages = list(pool.map(lambda r: fetch_clean(r["url"], timeout=15, max_chars=40000), cands))
    good = [(r, p) for r, p in zip(cands, pages) if p["text"] and not (p["error"] and len(p["text"]) < 200)][:n_src]
    budget = max(700, min(2400, 11500 // max(1, len(good))))
    lines = ["DEEP RESEARCH: %s" % question,
             "%d queries · providers: %s · %d candidates · read %d page(s), %d failed · %.1f s"
             % (len(queries), ", ".join(used) or "-", len(merged), len(good), len(cands) - len(good), time.time() - t0)]
    if answers:
        lines.append("Provider answer (unverified): " + answers[0])
    for i, (r, p) in enumerate(good, 1):
        date = p["date"] or r["date"]
        lines.append("\n[%d] %s (%s%s)\n    %s" % (i, (p["title"] or r["title"])[:110], _host(p["url"]), ", " + date if date else "", p["url"]))
        for piece in pick_passages(p["text"], kws, budget):
            lines.append("    > " + piece.replace("\n", "\n      "))
    rest = [r for r in merged if r not in [g[0] for g in good]][:6]
    if rest:
        lines.append("\nNot read (title and URL only; web_fetch one if you need it):")
        lines += ["- %s: %s" % (r["title"][:80], r["url"]) for r in rest]
    failed = [(r, p) for r, p in zip(cands, pages) if (r, p) not in good and p["error"]]
    if failed and not good:
        lines.append("Fetch problems: " + "; ".join("%s (%s)" % (_host(r["url"]), p["error"]) for r, p in failed[:4]))
    lines.append("\nHow to use this: cite sources as [n]; prefer official and newer sources; if sources disagree, say so; "
                 "list what you could not verify. save_note the key facts if the work will continue.")
    if getattr(ctx, "intent", "task") != "chat" and good:
        try:
            from axion.tools.project import t_save_note
            t_save_note({"title": "Research: " + question[:60],
                         "content": "\n".join("[%d] %s %s" % (i, g[1]["url"], g[1]["date"]) for i, g in enumerate(good, 1))}, ctx)
        except Exception:
            pass
    if notes and not good:
        lines.append("Notes: " + "; ".join(notes[:3]))
    return cap("\n".join(lines), 14000)


@tool("package_info",
      "Look up a package on PyPI, npm or crates.io: latest version, release date, required Python/Node version, license and the exact install "
      "command. Use it before pinning versions or writing install commands instead of guessing.",
      {"name": S("package name, e.g. requests, express, @types/node, serde"),
       "ecosystem": S("auto (PyPI and npm, default) | pypi | npm | crates")}, ["name"])
def t_package_info(a, ctx):
    found = engine.package_info(a.get("name"), a.get("ecosystem") or "auto")
    return "\n\n".join(engine.format_package(p) for p in found)
