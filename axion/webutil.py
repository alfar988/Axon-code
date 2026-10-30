"""HTTP fetching and HTML-to-text parsing (standard library only)."""

import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser

from axion.config import UA
from axion.state import ToolError


RETRY_STATUS = (429, 500, 502, 503, 504)
MAX_READ = 6000000          # bytes read from the network per request
_DATE_META = ("article:published_time", "og:article:published_time", "datepublished", "date", "pubdate",
              "publishdate", "dc.date", "dc.date.issued", "article:modified_time", "og:updated_time")
_DATE_RX = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _inflate(raw, enc, limit):
    """Decompress gzip/deflate with an output limit, so a small download cannot expand without bound."""
    enc = (enc or "").lower()
    if "gzip" in enc:
        attempts = (16 + zlib.MAX_WBITS,)
    elif "deflate" in enc:
        attempts = (zlib.MAX_WBITS, -zlib.MAX_WBITS)
    else:
        return raw
    for wbits in attempts:
        try:
            return zlib.decompressobj(wbits).decompress(raw, limit)
        except zlib.error:
            continue
    return raw


def _ssl_hint(reason):
    text = str(reason)
    if "CERTIFICATE_VERIFY_FAILED" in text or "SSL" in text:
        return " (certificate problem: install or update the CA certificates, e.g. `pkg install ca-certificates` on Termux or `sudo apt install ca-certificates` on Debian)"
    return ""


def _http_once(method, url, headers, body, timeout, max_bytes):
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip, deflate"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        resp = e
    except urllib.error.URLError as e:
        raise ToolError("could not connect to %s: %s%s" % (url, e.reason, _ssl_hint(e.reason)))
    except (socket.timeout, TimeoutError):
        raise ToolError("timed out opening %s" % url)
    except ValueError as e:
        raise ToolError("invalid URL %s: %s" % (url, e))
    except Exception as e:
        raise ToolError("failed to open %s: %s" % (url, e))
    try:
        raw = resp.read(MAX_READ)
    except (socket.timeout, TimeoutError):
        raise ToolError("timed out while reading %s" % url)
    except Exception as e:
        raise ToolError("connection broke while reading %s: %s" % (url, e))
    finally:
        try:
            resp.close()
        except Exception:
            pass
    hdrs = {k.lower(): v for k, v in resp.headers.items()}
    enc = hdrs.get("content-encoding", "")
    raw = _inflate(raw, enc, MAX_READ * 3)
    status = getattr(resp, "status", None) or resp.getcode()
    return {"status": status, "headers": hdrs, "body": raw[:max_bytes], "url": resp.geturl(),
            "ms": int((time.time() - t0) * 1000), "encoding": enc, "truncated": len(raw) > max_bytes}


def _retry_after(headers):
    try:
        return max(0.5, float(headers.get("retry-after", "1")))
    except ValueError:
        return 1.0


def _transient(message):
    m = message.lower()
    return "timed out" in m or "reset" in m or "broke" in m or "temporarily" in m


def http_fetch(method, url, headers=None, body=None, timeout=25, max_bytes=3000000, retries=None):
    """One HTTP request. GET and HEAD are retried once on timeouts and on 429/5xx; other methods are not retried unless asked."""
    if retries is None:
        retries = 1 if method in ("GET", "HEAD") else 0
    for attempt in range(retries + 1):
        try:
            info = _http_once(method, url, headers, body, timeout, max_bytes)
        except ToolError as e:
            if attempt < retries and _transient(str(e)):
                time.sleep(0.7 * (attempt + 1))
                continue
            raise
        if info["status"] in RETRY_STATUS and attempt < retries:
            time.sleep(min(_retry_after(info["headers"]), 4.0))
            continue
        return info
    raise ToolError("could not fetch %s" % url)


def decode_body(info):
    body = info["body"]
    cands = []
    m = re.search(r"charset=([\w-]+)", info["headers"].get("content-type", ""), re.I)
    if m:
        cands.append(m.group(1))
    meta = re.search(br"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
    if meta:
        cands.append(meta.group(1).decode("ascii", "ignore"))
    cands.append("utf-8")
    for enc in cands:
        try:
            return body.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "replace")


def norm_url(u):
    u = str(u or "").strip()
    if not u:
        raise ToolError("empty url")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", u):
        u = "https://" + u
    return u


class PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template"}
    CHROME = {"nav", "footer", "aside"}
    BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "nav", "ul", "ol",
             "li", "br", "tr", "table", "pre", "blockquote", "form", "hr"}

    def __init__(self, skip_chrome=False):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.skip_chrome = skip_chrome
        self.text = []
        self.main_parts = []
        self.skip = 0
        self.title = ""
        self.in_title = False
        self.meta = {}
        self.links = []
        self.imgs = []
        self.scripts = []
        self.styles = []
        self.headings = []
        self.forms = 0
        self.lang = ""
        self.canonical = ""
        self.inline_js = 0
        self.time_attr = ""
        self._main_depth = 0
        self._cur_script_inline = False
        self._head = None
        self._a = None

    def _emit(self, s):
        self.text.append(s)
        if self._main_depth:
            self.main_parts.append(s)

    def _skips(self, tag):
        return tag in self.SKIP or (self.skip_chrome and tag in self.CHROME)

    def handle_starttag(self, tag, attrs):
        a = dict((k, v) for k, v in attrs)
        if tag == "html":
            self.lang = a.get("lang") or ""
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or a.get("http-equiv") or "").lower()
            if key:
                self.meta[key] = a.get("content") or ""
            if a.get("charset"):
                self.meta["charset"] = a["charset"]
        elif tag == "link":
            r = (a.get("rel") or "").lower()
            if "canonical" in r:
                self.canonical = a.get("href") or ""
            if "stylesheet" in r:
                self.styles.append(a.get("href") or "")
        elif tag == "a":
            self._a = [a.get("href") or "", ""]
        elif tag == "img":
            self.imgs.append((a.get("src") or a.get("data-src") or "", a.get("alt"), a.get("loading")))
        elif tag == "form":
            self.forms += 1
        elif tag == "time" and not self.time_attr:
            self.time_attr = a.get("datetime") or ""
        elif tag == "script":
            self.scripts.append(a.get("src") or "")
            self._cur_script_inline = not a.get("src")
        if tag in ("main", "article"):
            self._main_depth += 1
        if self._skips(tag):
            self.skip += 1
        if re.match(r"^h[1-6]$", tag):
            self._head = [int(tag[1]), ""]
            self._emit("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in self.BLOCK:
            self._emit("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if self._skips(tag) and self.skip:
            self.skip -= 1
        if tag in ("main", "article") and self._main_depth:
            self._main_depth -= 1
        if tag == "script":
            self._cur_script_inline = False
        if tag == "a" and self._a:
            self.links.append((self._a[0], self._a[1].strip()))
            self._a = None
            if not self.skip:
                self._emit(" ")
        if re.match(r"^h[1-6]$", tag) and self._head:
            self.headings.append((self._head[0], self._head[1].strip()))
            self._head = None
            self._emit("\n")
        elif tag in self.BLOCK:
            self._emit("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
            return
        if self._cur_script_inline:
            self.inline_js += len(data)
        if self.skip:
            return
        if self._head is not None:
            self._head[1] += data
        if self._a is not None:
            self._a[1] += data
        self._emit(data)

    @staticmethod
    def _norm(t):
        t = re.sub(r"[ \t\r\f\v]+", " ", t)
        t = re.sub(r"\n[ ]+", "\n", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    def page_text(self):
        return self._norm("".join(self.text))

    def main_text(self, min_chars=400):
        """Text of <main>/<article> when the page has a substantial one, otherwise the whole page."""
        m = self._norm("".join(self.main_parts))
        return m if len(m) >= min_chars else self.page_text()

    def published(self):
        """Best guess of the publication date (YYYY-MM-DD) from meta tags and <time>, or ''."""
        for k in _DATE_META:
            m = _DATE_RX.search(self.meta.get(k, ""))
            if m:
                return "-".join(m.groups())
        m = _DATE_RX.search(self.time_attr)
        return "-".join(m.groups()) if m else ""


def page_text_of(html_):
    pp = PageParser()
    try:
        pp.feed(html_)
    except Exception:
        return ""
    return pp.page_text()


_LD_DATE_RX = re.compile(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})')


def fetch_clean(url, timeout=20, max_chars=20000):
    """Fetch a URL and return readable text. Never raises: failures come back in the 'error' field.

    Keys: url, status, ctype, title, text, date, links, error.
    """
    res = {"url": url, "status": 0, "ctype": "", "title": "", "text": "", "date": "", "links": [], "error": ""}
    try:
        info = http_fetch("GET", norm_url(url), timeout=timeout)
    except ToolError as e:
        res["error"] = str(e)
        return res
    res["status"] = info["status"]
    res["url"] = info["url"]
    ctype = info["headers"].get("content-type", "").split(";")[0].strip().lower()
    res["ctype"] = ctype
    if info["status"] >= 400:
        res["error"] = "HTTP %s" % info["status"]
        return res
    if ctype and not (ctype.startswith("text/") or "json" in ctype or "xml" in ctype or "html" in ctype or "javascript" in ctype):
        res["error"] = "not a text page (%s)" % ctype
        return res
    body = decode_body(info)
    if "json" in ctype:
        try:
            body = json.dumps(json.loads(body), indent=2, ensure_ascii=False)
        except ValueError:
            pass
        res["text"] = body[:max_chars]
        return res
    if "html" not in ctype and "<html" not in body[:500].lower():
        res["text"] = body[:max_chars]
        return res
    pp = PageParser(skip_chrome=True)
    try:
        pp.feed(body)
    except Exception:
        pass
    res["title"] = re.sub(r"\s+", " ", pp.title).strip()
    res["text"] = pp.main_text()[:max_chars]
    res["date"] = pp.published()
    if not res["date"]:
        m = _LD_DATE_RX.search(body[:300000])
        res["date"] = m.group(1) if m else ""
    res["links"] = [(h, t) for h, t in pp.links if h and not h.startswith(("#", "javascript:", "mailto:", "tel:"))][:60]
    if len(res["text"]) < 200 and len(pp.scripts) >= 2:
        res["error"] = "very little text; the page is probably rendered with JavaScript"
    return res
