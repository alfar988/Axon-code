"""Web tools: fetch, search, website audit, HTTP requests."""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape

from axion.state import ask, expand_secrets, ToolError
from axion.tools.registry import B, I, S, tool
from axion.ui import clip, tw
from axion.util import cap, denied, human_size, to_int
from axion.webutil import decode_body, http_fetch, norm_url, page_text_of, PageParser


# --- tool: web --------------------------------------------------------------
@tool("web_fetch", "Fetch a web page or URL and convert it to clean text (title, headings, body, links).",
      {"url": S("URL"), "max_chars": I("character limit, default 12000"),
       "raw": B("true = return the raw body (HTML/JSON/code)")}, ["url"])
def t_web_fetch(a, ctx):
    url = norm_url(a.get("url"))
    limit = max(1000, min(to_int(a.get("max_chars"), 12000), 40000))
    info = http_fetch("GET", url)
    ct = info["headers"].get("content-type", "")
    body = decode_body(info)
    head = "[HTTP %s · %s · %d ms · %s]\n" % (info["status"], ct.split(";")[0] or "?", info["ms"], info["url"])
    if info["status"] >= 400:
        return head + "Error page. Excerpt:\n" + cap(re.sub(r"\s+", " ", body)[:600])
    if a.get("raw") or ("html" not in ct.lower() and "<html" not in body[:500].lower()):
        if "json" in ct.lower():
            try:
                body = json.dumps(json.loads(body), indent=2, ensure_ascii=False)
            except ValueError:
                pass
        return head + cap(body, limit)
    pp = PageParser()
    pp.feed(body)
    text = pp.page_text()
    links = [(h, t) for h, t in pp.links if h and not h.startswith(("#", "javascript:"))][:40]
    res = head + ("Title: %s\n\n" % pp.title.strip() if pp.title.strip() else "") + cap(text, limit)
    if links:
        res += "\n\n[Link]\n" + "\n".join("- %s -> %s" % (t[:60] or "(no text)", urllib.parse.urljoin(info["url"], h))
                                          for h, t in links)
    if len(text) < 200 and len(pp.scripts) >= 2:
        res += "\n\n[Note: very little text; the site may be rendered with JavaScript (SPA).]"
    return cap(res, limit + 4000)


def strip_tags(s):
    return unescape(re.sub(r"<[^>]+>", "", s)).strip()


@tool("web_search", "Search the web (DuckDuckGo). Returns titles, URLs and snippets.",
      {"query": S("search query"), "max_results": I("number of results, default 8")}, ["query"])
def t_web_search(a, ctx):
    q = str(a.get("query", "")).strip()
    if not q:
        raise ToolError("empty query")
    n = max(1, min(to_int(a.get("max_results"), 8), 15))
    info = http_fetch("POST", "https://html.duckduckgo.com/html/",
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      body=urllib.parse.urlencode({"q": q}).encode())
    html_ = decode_body(info)
    anchors = list(re.finditer(r'<a\s+([^>]*class="[^"]*result__a[^"]*"[^>]*)>(.*?)</a>', html_, re.S))
    res = []
    for i, m in enumerate(anchors):
        href = re.search(r'href="([^"]+)"', m.group(1))
        if not href:
            continue
        link = unescape(href.group(1))
        if link.startswith("//"):
            link = "https:" + link
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
        if "uddg" in qs:
            link = qs["uddg"][0]
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(html_)
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', html_[m.end():end], re.S)
        res.append("%d. %s\n   %s\n   %s" % (len(res) + 1, strip_tags(m.group(2)), link,
                                             strip_tags(sn.group(1)) if sn else ""))
        if len(res) >= n:
            break
    if not res:
        return "(no results; the search engine may be blocking requests. Try web_fetch on a URL directly)"
    return "\n".join(res)


@tool("review_website", "Audit a website: status, speed, SEO, headings, images without alt text, broken links, security headers, robots/sitemap, SPA detection. Returns raw data; write a review with prioritized fixes based on this report.",
      {"url": S("website URL"), "check_links": B("check the status of internal links (default true)")}, ["url"])
def t_review_website(a, ctx):
    url = norm_url(a.get("url"))
    info = http_fetch("GET", url, timeout=30)
    body = decode_body(info)
    final = info["url"]
    pu = urllib.parse.urlparse(final)
    origin = "%s://%s" % (pu.scheme, pu.netloc)
    R = ["=== AUDIT: %s ===" % final,
         "HTTP status: %s | response time: %d ms | HTML size: %s | compression: %s | HTTPS: %s"
         % (info["status"], info["ms"], human_size(len(info["body"])), info["encoding"] or "none",
            "ya" if pu.scheme == "https" else "NO")]
    if final.rstrip("/") != url.rstrip("/"):
        R.append("Redirected from %s" % url)
    if info["status"] >= 400:
        R.append("!! The page returned error %s. The deploy may have failed, the URL may be wrong, or the project was removed." % info["status"])
        R.append("Excerpt: " + re.sub(r"\s+", " ", page_text_of(body))[:300])
    pp = PageParser()
    pp.feed(body)
    text = pp.page_text()
    words = len(text.split())
    title = pp.title.strip()
    desc = pp.meta.get("description", "")
    R.append("\n-- SEO & meta --")
    R.append("title: %r (%d characters, ideal 30-60)" % (title, len(title)))
    R.append("meta description: %r (%d characters, ideal 70-160)" % (desc, len(desc)))
    R.append("lang: %s | viewport: %s | charset: %s | canonical: %s" % (
        pp.lang or "MISSING", "present" if "viewport" in pp.meta else "MISSING (not mobile-friendly)",
        pp.meta.get("charset") or "-", pp.canonical or "none"))
    og = [k for k in ("og:title", "og:description", "og:image") if k in pp.meta]
    R.append("Open Graph: %s | twitter:card: %s" % (", ".join(og) or "MISSING", pp.meta.get("twitter:card", "none")))
    h1 = [t for l, t in pp.headings if l == 1]
    R.append("H1 count: %d %s" % (len(h1), "(ideal 1)" if len(h1) != 1 else ""))
    for l, t in pp.headings[:15]:
        R.append("%sH%d %s" % ("  " * (l - 1), l, t[:70]))
    for path in ("/robots.txt", "/sitemap.xml"):
        try:
            r = http_fetch("GET", origin + path, timeout=10, max_bytes=2000)
            R.append("%s: %s" % (path, "present" if r["status"] == 200 else "HTTP %s" % r["status"]))
        except ToolError:
            R.append("%s: check failed" % path)
    R.append("\n-- Content --")
    R.append("about %d visible words" % words)
    if words < 40 and len(pp.scripts) >= 2:
        R.append("!! Almost no text but many scripts: likely a SPA (React/Vue). Search engines and readers without JS cannot see the content. Consider SSR or prerendering.")
    R.append("\n-- Assets --")
    noalt = [s for s, al, _ in pp.imgs if al is None]
    emptyalt = [s for s, al, _ in pp.imgs if al == ""]
    nolazy = [s for s, _, ld in pp.imgs if ld != "lazy"]
    R.append("images: %d | missing alt: %d | empty alt: %d | no lazy-loading: %d"
             % (len(pp.imgs), len(noalt), len(emptyalt), len(nolazy)))
    for s in noalt[:5]:
        R.append("  missing alt: " + s[:80])
    ext_js = [s for s in pp.scripts if s]
    R.append("scripts: %d (external %d, inline %s) | stylesheets: %d | forms: %d"
             % (len(pp.scripts), len(ext_js), human_size(pp.inline_js), len(pp.styles), pp.forms))
    R.append("\n-- Link --")
    internal, external, empty = [], [], 0
    for href, _t in pp.links:
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            empty += 1
            continue
        if href.lower().startswith(("mailto:", "tel:")):
            continue
        full = urllib.parse.urljoin(final, href)
        (internal if urllib.parse.urlparse(full).netloc == pu.netloc else external).append(full)
    R.append("total %d | internal %d | external %d | empty/# %d" % (len(pp.links), len(internal), len(external), empty))
    if a.get("check_links", True) and internal:
        seen, bad, checked = set(), [], 0
        for l in internal:
            l = l.split("#")[0]
            if l in seen or l.rstrip("/") == final.rstrip("/"):
                continue
            seen.add(l)
            if checked >= 8:
                break
            checked += 1
            try:
                r = http_fetch("GET", l, timeout=8, max_bytes=500)
                if r["status"] >= 400:
                    bad.append("%s -> %s" % (l, r["status"]))
            except ToolError:
                bad.append("%s -> failed" % l)
        R.append("checked %d internal links, broken: %s" % (checked, ("; ".join(bad) if bad else "none")))
    R.append("\n-- Security headers --")
    sec = ["strict-transport-security", "content-security-policy", "x-content-type-options",
           "x-frame-options", "referrer-policy", "permissions-policy"]
    R.append("present: %s" % (", ".join(h for h in sec if h in info["headers"]) or "-"))
    R.append("not found: %s" % (", ".join(h for h in sec if h not in info["headers"]) or "-"))
    R.append("server: %s | cache-control: %s" % (info["headers"].get("server", "-"), info["headers"].get("cache-control", "-")))
    return "\n".join(R)


@tool("http_request", "Call any REST API. For API keys use a {{SECRET_NAME}} placeholder in the url, headers or body; the user stores it with /secret set NAME. Never ask for keys to be pasted into chat.",
      {"method": S("GET/POST/PUT/PATCH/DELETE"), "url": S("full URL"),
       "headers": {"type": "object", "description": "header HTTP"},
       "json": {"type": "object", "description": "JSON body (optional)"},
       "body": S("raw body (optional)"), "timeout": I("seconds, default 30")}, ["url"])
def t_http_request(a, ctx):
    method = str(a.get("method") or "GET").upper()
    url = norm_url(expand_secrets(ctx, a.get("url")))
    shown_url = norm_url(a.get("url"))
    headers = expand_secrets(ctx, a.get("headers") or {})
    body = None
    if a.get("json") is not None:
        body = json.dumps(expand_secrets(ctx, a["json"])).encode()
        headers.setdefault("Content-Type", "application/json")
    elif a.get("body") is not None:
        body = expand_secrets(ctx, str(a["body"])).encode()
    if method not in ("GET", "HEAD"):
        okk, why = ask(ctx, method, clip(shown_url, tw() - 14), [clip(str(a.get("json") or a.get("body") or ""), 200)])
        if not okk:
            return denied(why)
    info = http_fetch(method, url, headers=headers, body=body, timeout=max(3, min(to_int(a.get("timeout"), 30), 120)))
    txt = decode_body(info)
    try:
        txt = json.dumps(json.loads(txt), indent=2, ensure_ascii=False)
    except ValueError:
        pass
    keep = ("content-type", "content-length", "location", "retry-after", "x-ratelimit-remaining")
    hs = "\n".join("%s: %s" % (k, v) for k, v in info["headers"].items() if k in keep)
    return "HTTP %s · %d ms\n%s\n\n%s" % (info["status"], info["ms"], hs, cap(txt, 10000))
