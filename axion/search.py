"""Web search across several providers (standard library only).

Why several providers: any single free search endpoint can block, change its markup or rate-limit you.
This module tries a chain of providers per kind of question, runs them in parallel where that adds
coverage, merges the answers with reciprocal-rank fusion, caches results and rests providers that fail.

Providers that need no key: DuckDuckGo (html and lite), Bing, Wikipedia, Stack Exchange, GitHub,
Hacker News, npm, PyPI, MDN, arXiv, Crossref and Google/Bing News RSS.
Optional, used first when configured: BRAVE_API_KEY, TAVILY_API_KEY, SERPER_API_KEY, SEARXNG_URL.
"""

import base64
import json
import os
import re
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from html import unescape

from axion.state import ToolError
from axion.webutil import decode_body, http_fetch


BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
CACHE_TTL = 900            # seconds a successful answer is reused
CACHE_TTL_EMPTY = 120
CACHE_MAX = 400
COOL_BLOCKED = 180         # seconds a provider rests after being blocked or rate limited
COOL_ERROR = 60            # seconds after a network error
COOL_KEY = 900             # seconds after a rejected API key
KEY_NAMES = ("BRAVE_API_KEY", "TAVILY_API_KEY", "SERPER_API_KEY", "SEARXNG_URL", "GITHUB_TOKEN")
SPAN = {"day": 86400, "week": 7 * 86400, "month": 30 * 86400, "year": 365 * 86400}

# Endpoints live in a dict so tests (or a self-hosted mirror) can point them somewhere else.
E = {
    "ddg": "https://html.duckduckgo.com/html/",
    "ddg_lite": "https://lite.duckduckgo.com/lite/",
    "bing": "https://www.bing.com/search",
    "bing_news": "https://www.bing.com/news/search",
    "google_news": "https://news.google.com/rss/search",
    "brave": "https://api.search.brave.com/res/v1/web/search",
    "tavily": "https://api.tavily.com/search",
    "serper": "https://google.serper.dev/search",
    "wikipedia": "https://%s.wikipedia.org/w/api.php",
    "wikipedia_page": "https://%s.wikipedia.org/wiki/",
    "stackexchange": "https://api.stackexchange.com/2.3/search/advanced",
    "github": "https://api.github.com/search/repositories",
    "hackernews": "https://hn.algolia.com/api/v1/search",
    "npm_search": "https://registry.npmjs.org/-/v1/search",
    "npm_package": "https://registry.npmjs.org/",
    "pypi": "https://pypi.org/pypi/",
    "crates": "https://crates.io/api/v1/crates/",
    "mdn": "https://developer.mozilla.org/api/v1/search",
    "mdn_site": "https://developer.mozilla.org",
    "arxiv": "https://export.arxiv.org/api/query",
    "crossref": "https://api.crossref.org/works",
}

_LOCK = threading.Lock()
_CACHE = {}
_COOL = {}


class ProviderError(Exception):
    def __init__(self, msg, cool=COOL_ERROR):
        Exception.__init__(self, msg)
        self.cool = cool


class NotFound(ProviderError):
    pass


# --- small helpers -------------------------------------------------------------------------------
def _strip(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def _qs(**kw):
    return urllib.parse.urlencode([(k, v) for k, v in kw.items() if v not in (None, "")])


def _attr(attrs, name):
    m = re.search(r'\b%s\s*=\s*(?:"([^"]*)"|\'([^\']*)\')' % name, attrs, re.I)
    if not m:
        return ""
    return unescape(m.group(1) if m.group(1) is not None else m.group(2))


def _day(ts):
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(int(ts)))
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def R(title, url, snippet="", source="", date="", **extra):
    r = {"title": _strip(title)[:200] or url, "url": url, "snippet": _strip(snippet)[:400], "source": source,
         "date": date or "", "sources": [source]}
    r.update(extra)
    return r


_TRACK = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|ref_|igshid|yclid|_hs|spm$)", re.I)


def norm_key(url):
    """Identity of a result for de-duplication: no scheme, no www, no tracking parameters, no trailing slash."""
    p = urllib.parse.urlsplit(url)
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    q = sorted((k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not _TRACK.match(k))
    return host + (p.path.rstrip("/") or "") + (("?" + urllib.parse.urlencode(q)) if q else "")


_BOOST = ("wikipedia.org", "developer.mozilla.org", "docs.python.org", "github.com", "stackoverflow.com", "readthedocs.io",
          "pypi.org", "npmjs.com", "arxiv.org", "w3.org", "nodejs.org", "python.org", "whatwg.org", "rust-lang.org")
_DEMOTE = ("pinterest.", "facebook.com", "instagram.com", "tiktok.com", "slideshare.net", "scribd.com", "quora.com")


def domain_weight(url):
    host = urllib.parse.urlsplit(url).netloc.lower()
    if host.endswith((".gov", ".edu")) or ".gov." in host or ".edu." in host or any(b in host for b in _BOOST):
        return 1.25
    if any(d in host for d in _DEMOTE):
        return 0.7
    return 1.0


def _fetch(method, url, headers=None, body=None, timeout=15, retries=1):
    try:
        info = http_fetch(method, url, headers=headers, body=body, timeout=timeout, retries=retries)
    except ToolError as e:
        raise ProviderError(str(e))
    st = info["status"]
    if st == 404:
        raise NotFound("HTTP 404")
    if st in (401, 403):
        raise ProviderError("HTTP %d (access denied or key rejected)" % st, COOL_KEY if st == 401 else COOL_BLOCKED)
    if st == 429:
        raise ProviderError("HTTP 429 (rate limited)", COOL_BLOCKED)
    if st >= 400:
        raise ProviderError("HTTP %d" % st)
    return info


def _json(url, headers=None, timeout=15):
    info = _fetch("GET", url, dict({"Accept": "application/json"}, **(headers or {})), timeout=timeout)
    try:
        return json.loads(decode_body(info))
    except ValueError:
        raise ProviderError("invalid JSON in the response")


def _xml(info):
    body = info["body"]
    if b"<!ENTITY" in body or b"<!DOCTYPE" in body[:2000] and b"[" in body[:2000]:
        raise ProviderError("refused XML with a DTD")
    try:
        return ET.fromstring(body)
    except ET.ParseError:
        raise ProviderError("invalid XML in the response")


# --- web providers: scraped pages --------------------------------------------------------------
_A_RX = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)


def _unwrap_ddg(link):
    link = unescape(link)
    if link.startswith("//"):
        link = "https:" + link
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
    return qs["uddg"][0] if "uddg" in qs else link


def parse_ddg_html(page, n):
    anchors = [m for m in _A_RX.finditer(page) if "result__a" in _attr(m.group(1), "class")]
    out = []
    for i, m in enumerate(anchors):
        href = _unwrap_ddg(_attr(m.group(1), "href"))
        if not href.startswith("http") or "duckduckgo.com/y.js" in href:
            continue
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(page)
        sn = re.search(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div|td)>', page[m.end():end], re.S)
        out.append(R(m.group(2), href, sn.group(1) if sn else "", "ddg"))
        if len(out) >= n:
            break
    return out


def parse_ddg_lite(page, n):
    anchors = [m for m in _A_RX.finditer(page) if "result-link" in _attr(m.group(1), "class")]
    out = []
    for i, m in enumerate(anchors):
        href = _unwrap_ddg(_attr(m.group(1), "href"))
        if not href.startswith("http") or "duckduckgo.com/y.js" in href:
            continue
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(page)
        sn = re.search(r"class=['\"]result-snippet['\"][^>]*>(.*?)</td>", page[m.end():end], re.S)
        out.append(R(m.group(2), href, sn.group(1) if sn else "", "ddg_lite"))
        if len(out) >= n:
            break
    return out


def _unwrap_bing(link):
    link = unescape(link)
    m = re.search(r"[?&]u=a1([A-Za-z0-9_\-]+)", link)
    if "bing.com/ck/" in link and m:
        s = m.group(1)
        s += "=" * (-len(s) % 4)
        try:
            return base64.urlsafe_b64decode(s.encode()).decode("utf-8", "replace")
        except (ValueError, TypeError):
            return link
    return link


def parse_bing(page, n):
    out = []
    for blk in re.split(r'<li[^>]+class="[^"]*\bb_algo\b[^"]*"', page)[1:]:
        h = re.search(r"<h2[^>]*>\s*<a\b([^>]*)>(.*?)</a>", blk, re.S)
        if not h:
            continue
        href = _unwrap_bing(_attr(h.group(1), "href"))
        if not href.startswith("http"):
            continue
        sn = re.search(r"<p[^>]*>(.*?)</p>", blk, re.S)
        out.append(R(h.group(2), href, sn.group(1) if sn else "", "bing"))
        if len(out) >= n:
            break
    return out


def _scrape_headers():
    return {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"}


def _blocked(info, page, marker):
    return info["status"] in (202, 403, 429) or (marker not in page and re.search(r"captcha|unusual traffic|anomaly", page[:30000], re.I))


def p_ddg(q, n, o):
    form = {"q": q}
    df = {"day": "d", "week": "w", "month": "m", "year": "y"}.get(o.get("time_range"))
    if df:
        form["df"] = df
    h = dict(_scrape_headers(), **{"Content-Type": "application/x-www-form-urlencoded"})
    info = _fetch("POST", E["ddg"], h, urllib.parse.urlencode(form).encode(), timeout=15, retries=1)
    page = decode_body(info)
    if _blocked(info, page, "result__a"):
        raise ProviderError("blocked or rate limited (HTTP %s)" % info["status"], COOL_BLOCKED)
    return parse_ddg_html(page, n)


def p_ddg_lite(q, n, o):
    form = {"q": q}
    df = {"day": "d", "week": "w", "month": "m", "year": "y"}.get(o.get("time_range"))
    if df:
        form["df"] = df
    h = dict(_scrape_headers(), **{"Content-Type": "application/x-www-form-urlencoded"})
    info = _fetch("POST", E["ddg_lite"], h, urllib.parse.urlencode(form).encode(), timeout=15, retries=1)
    page = decode_body(info)
    if _blocked(info, page, "result-link"):
        raise ProviderError("blocked or rate limited (HTTP %s)" % info["status"], COOL_BLOCKED)
    return parse_ddg_lite(page, n)


def p_bing(q, n, o):
    info = _fetch("GET", E["bing"] + "?" + _qs(q=q, count=min(max(n, 10), 30), setlang="en"), _scrape_headers())
    page = decode_body(info)
    if _blocked(info, page, "b_algo"):
        raise ProviderError("blocked (captcha or rate limit)", COOL_BLOCKED)
    return parse_bing(page, n)


# --- web providers: APIs with a key ------------------------------------------------------------
def p_brave(q, n, o):
    fresh = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}.get(o.get("time_range"))
    d = _json(E["brave"] + "?" + _qs(q=q, count=min(n, 20), freshness=fresh), {"X-Subscription-Token": o["keys"]["BRAVE_API_KEY"]})
    return [R(x.get("title"), x.get("url"), x.get("description"), "brave", (x.get("page_age") or "")[:10])
            for x in (d.get("web") or {}).get("results", []) if x.get("url")][:n]


def p_tavily(q, n, o):
    payload = {"query": q, "max_results": min(n, 20), "search_depth": "basic", "include_answer": True}
    if o.get("time_range"):
        payload["time_range"] = o["time_range"]
    info = _fetch("POST", E["tavily"], {"Content-Type": "application/json", "Authorization": "Bearer " + o["keys"]["TAVILY_API_KEY"]},
                  json.dumps(payload).encode(), timeout=25, retries=0)
    d = json.loads(decode_body(info) or "{}")
    if d.get("answer"):
        o["answers"].append(str(d["answer"])[:800])
    return [R(x.get("title"), x.get("url"), x.get("content"), "tavily") for x in d.get("results", []) if x.get("url")][:n]


def p_serper(q, n, o):
    payload = {"q": q, "num": min(n, 20)}
    tbs = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}.get(o.get("time_range"))
    if tbs:
        payload["tbs"] = tbs
    info = _fetch("POST", E["serper"], {"Content-Type": "application/json", "X-API-KEY": o["keys"]["SERPER_API_KEY"]},
                  json.dumps(payload).encode(), timeout=20, retries=0)
    d = json.loads(decode_body(info) or "{}")
    if (d.get("answerBox") or {}).get("answer"):
        o["answers"].append(str(d["answerBox"]["answer"])[:800])
    return [R(x.get("title"), x.get("link"), x.get("snippet"), "serper", x.get("date") or "") for x in d.get("organic", []) if x.get("link")][:n]


def p_searxng(q, n, o):
    base = o["keys"]["SEARXNG_URL"].rstrip("/")
    d = _json(base + "/search?" + _qs(q=q, format="json", time_range=o.get("time_range")))
    return [R(x.get("title"), x.get("url"), x.get("content"), "searxng") for x in d.get("results", []) if x.get("url")][:n]


# --- specialised providers (no key) --------------------------------------------------------------
def p_wikipedia(q, n, o):
    lang = re.sub(r"[^a-z-]", "", (o.get("lang") or "en").lower()) or "en"
    d = _json(E["wikipedia"] % lang + "?" + _qs(action="query", list="search", srsearch=q, format="json", srlimit=min(n, 20), utf8=1))
    return [R(x["title"], E["wikipedia_page"] % lang + urllib.parse.quote(x["title"].replace(" ", "_")), x.get("snippet"), "wikipedia")
            for x in (d.get("query") or {}).get("search", [])][:n]


def p_stackexchange(q, n, o):
    args = {"order": "desc", "sort": "relevance", "q": q, "site": o.get("site") or "stackoverflow", "pagesize": min(n, 30)}
    if o.get("time_range"):
        args["fromdate"] = int(time.time() - SPAN[o["time_range"]])
    d = _json(E["stackexchange"] + "?" + _qs(**args))
    out = []
    for x in d.get("items", []):
        info = "score %s, %s answer(s)%s" % (x.get("score", 0), x.get("answer_count", 0), ", accepted answer" if x.get("accepted_answer_id") else "")
        tags = ", ".join((x.get("tags") or [])[:4])
        out.append(R(x.get("title"), x.get("link"), info + (" · tags: " + tags if tags else ""), "stackexchange", _day(x.get("creation_date"))))
    return out[:n]


def p_github(q, n, o):
    headers = {"Accept": "application/vnd.github+json"}
    if o["keys"].get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + o["keys"]["GITHUB_TOKEN"]
    d = _json(E["github"] + "?" + _qs(q=q, per_page=min(n, 20)), headers)
    return [R(x.get("full_name"), x.get("html_url"), "%s (stars %s, %s, updated %s)" % (x.get("description") or "", x.get("stargazers_count", 0),
                                                                                   x.get("language") or "n/a", (x.get("pushed_at") or "")[:10]),
              "github", (x.get("pushed_at") or "")[:10]) for x in d.get("items", []) if x.get("html_url")][:n]


def p_hackernews(q, n, o):
    args = {"query": q, "tags": "story", "hitsPerPage": min(n, 30)}
    if o.get("time_range"):
        args["numericFilters"] = "created_at_i>%d" % int(time.time() - SPAN[o["time_range"]])
    d = _json(E["hackernews"] + "?" + _qs(**args))
    out = []
    for x in d.get("hits", []):
        disc = "https://news.ycombinator.com/item?id=%s" % x.get("objectID")
        out.append(R(x.get("title"), x.get("url") or disc, "%s points, %s comments, discussion: %s" % (x.get("points", 0), x.get("num_comments", 0), disc),
                     "hackernews", (x.get("created_at") or "")[:10]))
    return out[:n]


def p_npm(q, n, o):
    d = _json(E["npm_search"] + "?" + _qs(text=q, size=min(n, 20)))
    out = []
    for x in d.get("objects", []):
        p = x.get("package") or {}
        if p.get("name"):
            out.append(R("%s %s" % (p["name"], p.get("version", "")), (p.get("links") or {}).get("npm") or "https://www.npmjs.com/package/" + p["name"],
                         p.get("description"), "npm", (p.get("date") or "")[:10]))
    return out[:n]


def p_pypi(q, n, o):
    """PyPI has no search API; an exact package name gets its page."""
    name = (q.split() or [""])[0]
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", name):
        return []
    try:
        d = _json(E["pypi"] + urllib.parse.quote(name, safe="") + "/json")
    except NotFound:
        return []
    i = d.get("info") or {}
    return [R("%s %s" % (i.get("name", name), i.get("version", "")), "https://pypi.org/project/%s/" % urllib.parse.quote(name, safe=""),
              i.get("summary"), "pypi")]


def p_mdn(q, n, o):
    d = _json(E["mdn"] + "?" + _qs(q=q, locale="en-US", size=min(n, 20)))
    return [R(x.get("title"), E["mdn_site"] + x["mdn_url"], x.get("summary"), "mdn") for x in d.get("documents", []) if x.get("mdn_url")][:n]


def p_arxiv(q, n, o):
    words = re.findall(r"[\w-]+", q)[:8]
    info = _fetch("GET", E["arxiv"] + "?" + _qs(search_query=" AND ".join("all:" + w for w in words), start=0, max_results=min(n, 20)), timeout=20)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in _xml(info).findall("a:entry", ns):
        out.append(R(e.findtext("a:title", "", ns), (e.findtext("a:id", "", ns) or "").strip(), e.findtext("a:summary", "", ns), "arxiv",
                     (e.findtext("a:published", "", ns) or "")[:10]))
    return [r for r in out if r["url"]][:n]


def p_crossref(q, n, o):
    d = _json(E["crossref"] + "?" + _qs(query=q, rows=min(n, 20), select="title,DOI,URL,container-title,issued"))
    out = []
    for x in (d.get("message") or {}).get("items", []):
        title = (x.get("title") or [""])[0]
        parts = ((x.get("issued") or {}).get("date-parts") or [[None]])[0]
        out.append(R(title, x.get("URL") or "https://doi.org/" + str(x.get("DOI", "")), ", ".join(x.get("container-title") or []), "crossref",
                     str(parts[0]) if parts and parts[0] else ""))
    return [r for r in out if r["title"]][:n]


def _parse_rss(root, source, n):
    out = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        m = re.search(r"[?&]url=([^&]+)", link) if "bing.com/news" in link else None
        if m:
            link = urllib.parse.unquote(m.group(1))
        date = ""
        try:
            date = parsedate_to_datetime(it.findtext("pubDate") or "").strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            pass
        src = (it.findtext("source") or "").strip()
        desc = _strip(it.findtext("description") or "")
        out.append(R(it.findtext("title") or "", link, ("%s: " % src if src else "") + desc, source, date))
        if len(out) >= n:
            break
    return [r for r in out if r["url"].startswith("http")]


def p_news_google(q, n, o):
    when = {"day": "1d", "week": "7d", "month": "30d", "year": "365d"}.get(o.get("time_range"))
    info = _fetch("GET", E["google_news"] + "?" + _qs(q=q + (" when:" + when if when else ""), hl="en-US", gl="US", ceid="US:en"))
    return _parse_rss(_xml(info), "news_google", n)


def p_news_bing(q, n, o):
    info = _fetch("GET", E["bing_news"] + "?" + _qs(q=q, format="rss"), _scrape_headers())
    return _parse_rss(_xml(info), "news_bing", n)


# name -> (function, needed key or None)
PROVIDERS = {
    "brave": (p_brave, "BRAVE_API_KEY"), "tavily": (p_tavily, "TAVILY_API_KEY"), "serper": (p_serper, "SERPER_API_KEY"),
    "searxng": (p_searxng, "SEARXNG_URL"), "ddg": (p_ddg, None), "ddg_lite": (p_ddg_lite, None), "bing": (p_bing, None),
    "wikipedia": (p_wikipedia, None), "stackexchange": (p_stackexchange, None), "github": (p_github, None),
    "hackernews": (p_hackernews, None), "npm": (p_npm, None), "pypi": (p_pypi, None), "mdn": (p_mdn, None),
    "arxiv": (p_arxiv, None), "crossref": (p_crossref, None), "news_google": (p_news_google, None), "news_bing": (p_news_bing, None),
}

KINDS = {
    "general": ["brave", "tavily", "serper", "searxng", "ddg", "bing", "ddg_lite"],
    "news": ["news_google", "news_bing", "hackernews"],
    "code": ["stackexchange", "github", "ddg", "bing"],
    "qa": ["stackexchange", "ddg", "bing"],
    "docs": ["mdn", "ddg", "bing"],
    "packages": ["npm", "pypi", "github"],
    "academic": ["arxiv", "crossref", "wikipedia"],
    "wiki": ["wikipedia"],
    "discussion": ["hackernews", "stackexchange", "ddg"],
}
PARALLEL_KINDS = {"news", "code", "docs", "packages", "academic", "discussion"}   # their providers cover different ground


# --- engine ------------------------------------------------------------------------------------
def env_keys(extra=None):
    keys = {k: os.environ.get(k, "") for k in KEY_NAMES}
    for k, v in (extra or {}).items():
        if v:
            keys[k] = v
    return {k: v for k, v in keys.items() if v}


def _available(name, keys):
    need = PROVIDERS[name][1]
    return need is None or bool(keys.get(need))


def _cooling(name):
    with _LOCK:
        return _COOL.get(name, 0) > time.time()


def rest_provider(name, seconds):
    with _LOCK:
        _COOL[name] = time.time() + seconds


def reset_state():
    """Forget the cache and all provider cooldowns (used by tests and by /search reset)."""
    with _LOCK:
        _CACHE.clear()
        _COOL.clear()


def _call(name, query, n, o):
    """Run one provider with caching. Returns (results, error message or '')."""
    ck = (name, query, n, o.get("time_range"), o.get("site"), o.get("lang"))
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(ck)
    if hit and hit[0] > now:
        return [dict(r) for r in hit[1]], ""
    fn = PROVIDERS[name][0]
    try:
        res = fn(query, n, o)
    except ProviderError as e:
        rest_provider(name, e.cool)
        return [], "%s: %s" % (name, e)
    except ToolError as e:
        rest_provider(name, COOL_ERROR)
        return [], "%s: %s" % (name, e)
    except (KeyError, TypeError, ValueError, AttributeError, ET.ParseError) as e:
        rest_provider(name, COOL_ERROR)
        return [], "%s: unexpected response format (%s)" % (name, type(e).__name__)
    with _LOCK:
        if len(_CACHE) >= CACHE_MAX:
            for k in sorted(_CACHE, key=lambda k_: _CACHE[k_][0])[:CACHE_MAX // 4]:
                del _CACHE[k]
        _CACHE[ck] = (now + (CACHE_TTL if res else CACHE_TTL_EMPTY), [dict(r) for r in res])
    return res, ""


def merge(lists, n):
    """Reciprocal-rank fusion of several ranked lists, de-duplicated by URL, with a small domain prior."""
    items, scores = {}, {}
    for prov, res in lists:
        for rank, r in enumerate(res):
            k = norm_key(r["url"])
            s = domain_weight(r["url"]) / (60.0 + rank)
            if k in items:
                it = items[k]
                scores[k] += s
                if prov not in it["sources"]:
                    it["sources"].append(prov)
                if len(r["snippet"]) > len(it["snippet"]):
                    it["snippet"] = r["snippet"]
                if r["date"] and not it["date"]:
                    it["date"] = r["date"]
            else:
                it = dict(r)
                it["sources"] = [prov]
                items[k], scores[k] = it, s
    return [items[k] for k in sorted(items, key=lambda k_: -scores[k_])][:n]


def search(query, kind="general", n=8, time_range=None, providers=None, keys=None, site=None, lang=None):
    """Search the web. Returns {'results', 'used', 'notes', 'answers'}; raises ToolError only when nothing worked at all."""
    query = " ".join(str(query or "").split())
    if not query:
        raise ToolError("empty query")
    kind = kind if kind in KINDS else "general"
    n = max(1, min(int(n), 30))
    time_range = time_range if time_range in SPAN else None
    keys = env_keys(keys)
    o = {"time_range": time_range, "keys": keys, "site": site, "lang": lang, "answers": []}
    wanted = [p for p in (providers or KINDS[kind]) if p in PROVIDERS]
    if providers and not wanted:
        raise ToolError("unknown provider(s). Available: %s" % ", ".join(sorted(PROVIDERS)))
    avail = [p for p in wanted if _available(p, keys)]
    order = [p for p in avail if not _cooling(p)] + [p for p in avail if _cooling(p)]
    if not order:
        raise ToolError("no search provider is available for this request (missing keys: %s)"
                        % ", ".join(sorted({PROVIDERS[p][1] for p in wanted if PROVIDERS[p][1]})) or "none")
    if providers or kind in PARALLEL_KINDS:
        sizes = [len(order)]
    else:
        sizes = [2] + [1] * max(0, len(order) - 2)      # two at once for coverage, then one by one while results are scarce
    lists, notes, used, i = [], [], [], 0
    for size in sizes:
        batch = order[i:i + size]
        i += size
        if not batch:
            break
        if len(batch) == 1:
            outs = [(batch[0],) + _call(batch[0], query, n, o)]
        else:
            with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                futs = [(p, pool.submit(_call, p, query, n, o)) for p in batch]
                outs = [(p,) + f.result() for p, f in futs]
        for p, res, err in outs:
            if err:
                notes.append(err)
            elif res:
                lists.append((p, res))
                used.append(p)
        if len(merge(lists, n)) >= min(n, 5):
            break
    results = merge(lists, n)
    if not results and notes and len(notes) >= len(order):
        raise ToolError("every search provider failed: " + "; ".join(notes[:4]))
    return {"results": results, "used": used, "notes": notes, "answers": o["answers"]}


def format_results(found, query, kind="general", limit_snippet=260):
    res = found["results"]
    head = "Search: %r (%s, %d result%s via %s)" % (query, kind, len(res), "" if len(res) == 1 else "s", ", ".join(found["used"]) or "no provider")
    lines = [head]
    for a in found.get("answers", [])[:1]:
        lines.append("Provider answer: " + a)
    for i, r in enumerate(res, 1):
        meta = " · ".join(x for x in (r["date"], "+".join(r["sources"]) if len(r["sources"]) > 1 else "") if x)
        lines.append("%d. %s%s\n   %s\n   %s" % (i, r["title"], ("  [%s]" % meta) if meta else "", r["url"], r["snippet"][:limit_snippet]))
    if not res:
        lines.append("(no results. Try fewer or different keywords, another kind, or web_fetch on a likely URL.)")
    if found["notes"]:
        lines.append("Notes: " + "; ".join(found["notes"][:4]))
    return "\n".join(lines)


def provider_status(keys=None):
    keys = env_keys(keys)
    rows = []
    for name, (_fn, need) in PROVIDERS.items():
        state = "needs %s" % need if (need and not keys.get(need)) else ("resting" if _cooling(name) else "ready")
        rows.append((name, state))
    return rows


# --- package registries ------------------------------------------------------------------------
def _pypi_info(name):
    d = _json(E["pypi"] + urllib.parse.quote(name, safe="") + "/json")
    i = d.get("info") or {}
    urls = d.get("urls") or []
    lic = (i.get("license_expression") or i.get("license") or "").strip().splitlines()
    return {"eco": "pypi", "name": i.get("name", name), "version": i.get("version", "?"),
            "date": (urls[0].get("upload_time_iso_8601") or "")[:10] if urls else "", "summary": i.get("summary") or "",
            "home": i.get("home_page") or (i.get("project_urls") or {}).get("Homepage") or i.get("package_url") or "",
            "license": (lic[0] if lic else "")[:60], "requires": i.get("requires_python") or "", "deps": len(i.get("requires_dist") or []),
            "install": "pip install %s==%s" % (i.get("name", name), i.get("version", ""))}


def _npm_info(name):
    d = _json(E["npm_package"] + urllib.parse.quote(name, safe="@") + "/latest")
    date = ""
    try:                                              # the search endpoint carries the publish date
        for x in _json(E["npm_search"] + "?" + _qs(text=name, size=5)).get("objects", []):
            if (x.get("package") or {}).get("name") == d.get("name"):
                date = (x["package"].get("date") or "")[:10]
    except (ProviderError, KeyError, TypeError):
        pass
    repo = d.get("repository")
    return {"eco": "npm", "name": d.get("name", name), "version": d.get("version", "?"), "date": date, "summary": d.get("description") or "",
            "home": d.get("homepage") or (repo.get("url") if isinstance(repo, dict) else repo) or "",
            "license": str(d.get("license") or "")[:60], "requires": (d.get("engines") or {}).get("node", ""),
            "deps": len(d.get("dependencies") or {}), "install": "npm install %s@%s" % (d.get("name", name), d.get("version", ""))}


def _crate_info(name):
    d = _json(E["crates"] + urllib.parse.quote(name, safe=""))
    c = d.get("crate") or {}
    ver = c.get("max_stable_version") or c.get("max_version") or "?"
    return {"eco": "crates", "name": c.get("name", name), "version": ver, "date": (c.get("updated_at") or "")[:10], "summary": c.get("description") or "",
            "home": c.get("homepage") or c.get("repository") or "", "license": "", "requires": "", "deps": 0,
            "install": "cargo add %s@%s" % (c.get("name", name), ver)}


def package_info(name, eco="auto"):
    """Latest version and basics of a package. eco: pypi | npm | crates | auto (pypi and npm). Returns a list of dicts."""
    name = str(name or "").strip()
    if not name or len(name) > 214 or not re.match(r"^[@A-Za-z0-9][@A-Za-z0-9._/-]*$", name):
        raise ToolError("invalid package name %r" % name)
    eco = (eco or "auto").lower()
    table = {"pypi": _pypi_info, "npm": _npm_info, "crates": _crate_info}
    todo = [eco] if eco in table else (["npm"] if name.startswith("@") else ["pypi", "npm"])
    found, errors = [], []
    for e in todo:
        try:
            found.append(table[e](name))
        except NotFound:
            errors.append("%s: not found" % e)
        except ProviderError as ex:
            errors.append("%s: %s" % (e, ex))
    if not found:
        raise ToolError("no package named %r (%s)" % (name, "; ".join(errors)))
    return found


def format_package(p):
    lines = ["%s: %s %s%s" % (p["eco"], p["name"], p["version"], " (released %s)" % p["date"] if p["date"] else "")]
    if p["summary"]:
        lines.append("  " + p["summary"][:200])
    facts = [x for x in (("requires %s" % p["requires"]) if p["requires"] else "", ("license %s" % p["license"]) if p["license"] else "",
                         ("%d dependencies" % p["deps"]) if p["deps"] else "") if x]
    if facts:
        lines.append("  " + " · ".join(facts))
    if p["home"]:
        lines.append("  home: " + p["home"])
    lines.append("  install: " + p["install"])
    return "\n".join(lines)
