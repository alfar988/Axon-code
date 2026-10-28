"""Simple HTTP fetch and HTML-to-text parsing."""

import gzip
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


def http_fetch(method, url, headers=None, body=None, timeout=25, max_bytes=3000000):
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip, deflate"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        resp = e
    except urllib.error.URLError as e:
        raise ToolError("could not connect to %s: %s (on SSL errors: pkg install ca-certificates)" % (url, e.reason))
    except (socket.timeout, TimeoutError):
        raise ToolError("timed out opening %s" % url)
    except Exception as e:
        raise ToolError("failed to open %s: %s" % (url, e))
    try:
        raw = resp.read(6000000)
    finally:
        try:
            resp.close()
        except Exception:
            pass
    hdrs = {k.lower(): v for k, v in resp.headers.items()}
    enc = hdrs.get("content-encoding", "")
    try:
        if "gzip" in enc:
            raw = gzip.decompress(raw)
        elif "deflate" in enc:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                raw = zlib.decompress(raw, -15)
    except Exception:
        pass
    status = getattr(resp, "status", None) or resp.getcode()
    return {"status": status, "headers": hdrs, "body": raw[:max_bytes], "url": resp.geturl(),
            "ms": int((time.time() - t0) * 1000), "encoding": enc, "truncated": len(raw) > max_bytes}


def decode_body(info):
    ct = info["headers"].get("content-type", "")
    m = re.search(r"charset=([\w-]+)", ct)
    for enc in ([m.group(1)] if m else []) + ["utf-8"]:
        try:
            return info["body"].decode(enc)
        except Exception:
            continue
    return info["body"].decode("utf-8", "replace")


def norm_url(u):
    u = str(u or "").strip()
    if not u:
        raise ToolError("empty url")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", u):
        u = "https://" + u
    return u


class PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template"}
    BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "nav", "ul", "ol",
             "li", "br", "tr", "table", "pre", "blockquote", "form", "hr"}

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.text = []
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
        self._cur_script_inline = False
        self._head = None
        self._a = None

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
        elif tag == "script":
            self.scripts.append(a.get("src") or "")
            self._cur_script_inline = not a.get("src")
        if tag in self.SKIP:
            self.skip += 1
        if re.match(r"^h[1-6]$", tag):
            self._head = [int(tag[1]), ""]
            self.text.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in self.BLOCK:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "script":
            self._cur_script_inline = False
        if tag == "a" and self._a:
            self.links.append((self._a[0], self._a[1].strip()))
            self._a = None
            if not self.skip:
                self.text.append(" ")
        if re.match(r"^h[1-6]$", tag) and self._head:
            self.headings.append((self._head[0], self._head[1].strip()))
            self._head = None
            self.text.append("\n")
        elif tag in self.BLOCK:
            self.text.append("\n")

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
        self.text.append(data)

    def page_text(self):
        t = "".join(self.text)
        t = re.sub(r"[ \t\r\f\v]+", " ", t)
        t = re.sub(r"\n[ ]+", "\n", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()


def page_text_of(html_):
    pp = PageParser()
    try:
        pp.feed(html_)
    except Exception:
        return ""
    return pp.page_text()
