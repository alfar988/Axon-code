#!/usr/bin/env python3
"""__TITLE__: a polite web scraper using only the standard library.

Run:        python scraper.py --out quotes.csv                 (also .json or .jsonl; default prints a table)
            python scraper.py --url __START_URL__ --max-pages 3 --delay 1.5
Self test:  python scraper.py --selftest      scrapes a local fake site (no internet), checks robots.txt, paging and the cache
What it does: checks robots.txt, waits between requests (with jitter), retries timeouts and 5xx with backoff, caches pages on
            disk so a rerun costs the site nothing, follows the "next" link, and stops at --max-pages.

EDIT: parse_page() (the rows to extract) and next_page() (the link to the next page) for your target site. Keep Fetcher.
Be a good citizen: read the site's terms, keep the delay at one second or more, identify yourself in USER_AGENT.
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import random
import sys
import tempfile
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

log = logging.getLogger("scraper")
USER_AGENT = "ResearchScraper/1.0 (+contact: you@example.com)"      # EDIT: say who you are and how to reach you


class ScrapeError(Exception):
    pass


# --- fetching -----------------------------------------------------------------------------------
class Fetcher:
    def __init__(self, delay=1.0, cache_dir=None, use_cache=True, opener=None):
        self.delay, self.use_cache, self.last = delay, use_cache, 0.0
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "scraper_cache")
        self.robots = {}
        self.opener = opener or self._open
        os.makedirs(self.cache_dir, exist_ok=True)
        self.requests = 0

    def _open(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity", "Accept-Language": "en"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")

    def allowed(self, url):
        parts = urlsplit(url)
        root = "%s://%s" % (parts.scheme, parts.netloc)
        if root not in self.robots:
            rp = RobotFileParser()
            try:
                rp.parse(self.opener(root + "/robots.txt").splitlines())
            except (urllib.error.URLError, OSError, ValueError):
                rp.parse([])                                  # no robots.txt: nothing is disallowed
            self.robots[root] = rp
            self.delay = max(self.delay, float(self.robots[root].crawl_delay(USER_AGENT) or 0))
        return self.robots[root].can_fetch(USER_AGENT, url)

    def get(self, url, tries=3):
        if not self.allowed(url):
            raise ScrapeError("robots.txt disallows %s" % url)
        path = os.path.join(self.cache_dir, hashlib.sha1(url.encode()).hexdigest())
        if self.use_cache and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
        for attempt in range(1, tries + 1):
            wait = self.delay - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait + random.uniform(0, self.delay / 4))
            self.last = time.monotonic()
            self.requests += 1
            try:
                body = self.opener(url)
            except urllib.error.HTTPError as e:
                if e.code in (400, 401, 403, 404, 410) or attempt == tries:
                    raise ScrapeError("%s returned HTTP %d" % (url, e.code))
                time.sleep(float(e.headers.get("Retry-After", 2 ** attempt)) if e.code == 429 else 2 ** attempt)
                continue
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == tries:
                    raise ScrapeError("could not reach %s: %s" % (url, e))
                time.sleep(2 ** attempt)
                continue
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            return body
        raise ScrapeError("gave up on " + url)


# --- parsing (EDIT for your site) ---------------------------------------------------------------
class QuotePage(HTMLParser):
    """Rows from <div class="quote"> blocks: text, author and tags; also finds <li class="next"><a href>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.next_href = [], ""
        self._row, self._field, self._in_next = None, None, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "div" and "quote" in classes:
            self._row = {"text": "", "author": "", "tags": []}
        elif tag == "li" and "next" in classes:
            self._in_next = True
        elif tag == "a" and self._in_next and a.get("href"):
            self.next_href = a["href"]
        elif self._row is not None:
            if tag == "span" and "text" in classes:
                self._field = "text"
            elif tag == "small" and "author" in classes:
                self._field = "author"
            elif tag == "a" and "tag" in classes:
                self._field = "tag"

    def handle_data(self, data):
        if self._row is None or not self._field:
            return
        if self._field == "tag":
            self._row["tags"].append(data.strip())
        else:
            self._row[self._field] += data

    def handle_endtag(self, tag):
        if tag in ("span", "small", "a"):
            self._field = None
        elif tag == "li":
            self._in_next = False
        elif tag == "div" and self._row is not None and self._row["text"]:
            self.rows.append(self._row)
            self._row = None


def parse_page(html, url):
    """Return a list of dicts, one per record on the page."""
    p = QuotePage()
    p.feed(html)
    return [{"text": r["text"].strip(" \u201c\u201d\"\n"), "author": r["author"].strip(), "tags": ",".join(r["tags"]), "source": url} for r in p.rows]


def next_page(html, url):
    """Return the absolute URL of the next page, or '' when this is the last one."""
    p = QuotePage()
    p.feed(html)
    return urljoin(url, p.next_href) if p.next_href else ""


# --- crawl and save -----------------------------------------------------------------------------
def crawl(fetcher, start, max_pages=5):
    rows, seen, url = [], set(), start
    while url and url not in seen and len(seen) < max_pages:
        seen.add(url)
        html = fetcher.get(url)
        found = parse_page(html, url)
        if not found:
            log.warning("no records on %s: the page layout may have changed", url)
        rows += found
        log.info("%s: %d record(s)", url, len(found))
        url = next_page(html, url)
    return rows


def write_rows(rows, out):
    if not rows:
        raise ScrapeError("nothing was scraped, so no file was written")
    if out.endswith(".json"):
        data = json.dumps(rows, ensure_ascii=False, indent=2)
    elif out.endswith(".jsonl"):
        data = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    else:
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        return
    with open(out, "w", encoding="utf-8") as f:
        f.write(data + "\n")


# --- self test against a local fake site --------------------------------------------------------
def selftest():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    def page(n, last):
        quotes = "".join('<div class="quote"><span class="text">\u201cQuote %d.%d\u201d</span><span>by <small class="author">Author %d</small>'
                         '<div class="tags"><a class="tag" href="/t/a">life</a><a class="tag" href="/t/b">books</a></div></span></div>' % (n, i, n) for i in (1, 2))
        nxt = "" if last else '<nav><ul class="pager"><li class="next"><a href="/page/%d/">Next</a></li></ul></nav>' % (n + 1)
        return "<html><body>%s%s</body></html>" % (quotes, nxt)

    hits = []

    class Site(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            hits.append(self.path)
            if self.path == "/robots.txt":
                body, status = "User-agent: *\nDisallow: /private/\n", 200
            elif self.path == "/":
                body, status = page(1, False), 200
            elif self.path in ("/page/2/", "/page/3/"):
                body, status = page(int(self.path.split("/")[2]), self.path.endswith("3/")), 200
            else:
                body, status = "not found", 404
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_port
    cache = tempfile.mkdtemp(prefix="scraper_test_")
    failures = []

    def check(label, got, want):
        if got != want:
            failures.append("%s: got %r, wanted %r" % (label, got, want))

    try:
        f = Fetcher(delay=0.01, cache_dir=cache)
        rows = crawl(f, base + "/", max_pages=10)
        check("records", len(rows), 6)
        check("first row", (rows[0]["text"], rows[0]["author"], rows[0]["tags"]), ("Quote 1.1", "Author 1", "life,books"))
        check("stops on the last page", sorted(set(h for h in hits if h.startswith("/page"))), ["/page/2/", "/page/3/"])
        check("max_pages", len(crawl(Fetcher(delay=0.01, cache_dir=tempfile.mkdtemp()), base + "/", max_pages=2)), 4)
        before = len(hits)
        crawl(Fetcher(delay=0.01, cache_dir=cache), base + "/", max_pages=10)
        check("cache means no new page requests", [h for h in hits[before:] if h != "/robots.txt"], [])
        try:
            f.get(base + "/private/secret")
            failures.append("robots.txt was ignored")
        except ScrapeError as e:
            check("robots", "robots.txt" in str(e), True)
        try:
            f.get(base + "/missing")
            failures.append("404 was not reported")
        except ScrapeError as e:
            check("404", "HTTP 404" in str(e), True)
        out = os.path.join(cache, "out.csv")
        write_rows(rows, out)
        with open(out, encoding="utf-8") as fh:
            check("csv", len(fh.read().splitlines()), 7)
    finally:
        server.shutdown()
    for msg in failures:
        print("FAIL", msg)
    print("selftest: %s" % ("all checks passed" if not failures else "%d check(s) failed" % len(failures)))
    return 1 if failures else 0


def main(argv=None):
    p = argparse.ArgumentParser(description="__TITLE__")
    p.add_argument("--url", default="__START_URL__", help="first page (default: %(default)s)")
    p.add_argument("--out", help="file to write: .csv, .json or .jsonl (default: print a table)")
    p.add_argument("--max-pages", type=int, default=5)
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1.0)")
    p.add_argument("--no-cache", action="store_true", help="ignore cached pages")
    p.add_argument("--selftest", action="store_true", help="run the built-in checks and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    if args.selftest:
        return selftest()
    try:
        rows = crawl(Fetcher(args.delay, use_cache=not args.no_cache), args.url, args.max_pages)
        if args.out:
            write_rows(rows, args.out)
            print("wrote %d record(s) to %s" % (len(rows), args.out))
        else:
            for r in rows:
                print("%-40.40s  %-22.22s  %s" % (r["text"], r["author"], r["tags"]))
    except ScrapeError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
