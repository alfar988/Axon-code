---
name: scraping-skill
description: Collect data from websites responsibly: look for an API first, honor robots.txt, rate limit with jitter, retry with backoff, cache, parse HTML with the standard library, paginate, store results. Runnable examples.
---
# Scraping skill

## Quick rules (read first)
1. Use the official API first, then an RSS or JSON feed, and only then the HTML page.
2. Read the site's terms and `robots.txt`. If the site forbids it, do not scrape it.
3. Be polite: identify yourself in the User-Agent, wait between requests, cache pages, and stop when the server asks you to slow down (429).
4. Use timeouts and retries with growing delays. Handle every error.
5. Parse with the standard library (`html.parser`, `json`, `csv`). Save the result as CSV or JSON.

## Safety in this skill
- Do not collect personal data about private people, build contact lists for spam, or copy content that is not yours to copy.
- Do not get around logins, paywalls, captchas, rate limits or blocks (rotating proxies or fake browsers to avoid a ban). Do not hammer a server: a few requests per second is already a lot for a small site.

## Order of preference
1. An official API or a data download. Check the site's developer docs and `/sitemap.xml`.
2. A JSON endpoint the page itself calls (browser dev tools, Network tab; or search the page source for `fetch(` and `.json`).
3. RSS or Atom feeds.
4. Parsing the HTML.
Respect terms of service and `robots.txt`. Identify yourself with a User-Agent that says what you are and how to reach you. Do not collect personal data you do not need. Go slowly: one request per second per site is a good default.

## robots.txt
```python
# check: runs
from urllib.robotparser import RobotFileParser

rules = """User-agent: *
Disallow: /private/
Crawl-delay: 2
"""
rp = RobotFileParser()
rp.parse(rules.splitlines())                       # in real use: rp.set_url(site + "/robots.txt"); rp.read()
assert rp.can_fetch("MyBot", "https://example.com/blog/1")
assert not rp.can_fetch("MyBot", "https://example.com/private/data")
assert rp.crawl_delay("MyBot") == 2
```

## Polite fetching: delay, retries, cache
```python
# check: runs
import hashlib
import os
import random
import tempfile
import time
import urllib.error
import urllib.request

class Fetcher:
    def __init__(self, delay=1.0, cache_dir=None, user_agent="MyResearchBot/1.0 (contact: you@example.com)", opener=None):
        self.delay, self.ua, self.last = delay, user_agent, 0.0
        self.cache_dir = cache_dir or tempfile.mkdtemp(prefix="cache_")
        self.opener = opener or self._open

    def _open(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept-Encoding": "identity"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", "replace")

    def get(self, url, tries=3):
        path = os.path.join(self.cache_dir, hashlib.sha1(url.encode()).hexdigest())
        if os.path.exists(path):                                  # a cached page costs the site nothing
            return open(path, encoding="utf-8").read()
        for attempt in range(1, tries + 1):
            wait = self.delay - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait + random.uniform(0, self.delay / 4))      # jitter
            self.last = time.monotonic()
            try:
                body = self.opener(url)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(body)
                return body
            except (urllib.error.URLError, TimeoutError) as e:
                code = getattr(e, "code", None)
                if code in (400, 401, 403, 404, 410) or attempt == tries:
                    raise
                time.sleep(2 ** attempt)                            # back off on 429 / 5xx / timeouts

calls = []
f = Fetcher(delay=0.01, opener=lambda u: calls.append(u) or "<html>ok</html>")
assert f.get("https://example.com/a") == f.get("https://example.com/a") == "<html>ok</html>"
assert len(calls) == 1                                               # second call came from the cache
```
HTTP 429 or a `Retry-After` header means slow down, not retry harder. HTTP 403 repeatedly: stop; the site does not want this.

## Parse with the standard library
```python
# check: runs
from html.parser import HTMLParser

class Products(HTMLParser):
    """Collects <li class="product"> items: name from <h2>, price from <span class="price">, link from <a>."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items, self._cur, self._field = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "li" and "product" in (a.get("class") or "").split():
            self._cur = {"name": "", "price": "", "url": ""}
        elif self._cur is not None:
            if tag == "h2":
                self._field = "name"
            elif tag == "span" and "price" in (a.get("class") or "").split():
                self._field = "price"
            elif tag == "a" and a.get("href"):
                self._cur["url"] = a["href"]

    def handle_data(self, data):
        if self._cur is not None and self._field:
            self._cur[self._field] += data.strip()

    def handle_endtag(self, tag):
        if tag in ("h2", "span"):
            self._field = None
        elif tag == "li" and self._cur is not None:
            self.items.append(self._cur)
            self._cur = None

page = """<ul>
<li class="product"><h2>Lamp</h2><span class="price">$12.50</span><a href="/p/1">view</a></li>
<li class="product"><h2>Desk &amp; chair</h2><span class="price">$99</span><a href="/p/2">view</a></li>
</ul>"""
p = Products()
p.feed(page)
assert p.items == [{"name": "Lamp", "price": "$12.50", "url": "/p/1"}, {"name": "Desk & chair", "price": "$99", "url": "/p/2"}]
print(p.items)
```
`beautifulsoup4` (`pip install beautifulsoup4`) is shorter for big jobs: `soup.select("li.product h2")`. Selectors break when the site changes: print a clear error when zero items match instead of writing an empty file.

## Pagination and links
Follow the "next" link or increment `?page=` until a page returns no items; stop at a hard maximum. Resolve relative links with `urllib.parse.urljoin(page_url, href)`. Keep a `seen` set of URLs.

## Store the result
CSV for tables (`csv.DictWriter`), JSON lines for nested data, SQLite for anything you will query (see database-skill). Save raw HTML next to the result while developing, so you can fix the parser without hitting the site again. Record the source URL and the fetch date in every row.

## Pages that need JavaScript
Look for the underlying JSON call first. If there is none, a headless browser (Playwright) is the heavy option and may not exist on a phone; say so and offer the API or a manual export instead.

## Good and bad examples

### 1. Checking robots.txt
Bad: fetch every path without looking.
Good: parse the rules and ask before each fetch.
```python
# check: runs
from urllib.robotparser import RobotFileParser

rp = RobotFileParser()
rp.parse(["User-agent: *", "Disallow: /private/"])
assert rp.can_fetch("my-bot", "https://example.com/blog/")
assert not rp.can_fetch("my-bot", "https://example.com/private/data")
```

### 2. Parsing
Bad: a regular expression on HTML, which breaks on any change.
Good: a small parser.
```python
# check: runs
from html.parser import HTMLParser

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

p = Links()
p.feed('<p><a href="/a">A</a> <a name="x">no href</a> <a href="/b">B</a></p>')
assert p.links == ["/a", "/b"]
```

### 3. Retrying
Bad: `while True: fetch()` in a tight loop. Good: wait longer after every failure, with a cap.
```python
# check: runs
def backoff_delays(retries=4, base=1.0, cap=30.0):
    return [min(cap, base * 2 ** i) for i in range(retries)]

assert backoff_delays() == [1.0, 2.0, 4.0, 8.0]
assert backoff_delays(6, cap=10.0)[-1] == 10.0
```

### 4. Identity
Bad: pretend to be a normal browser to avoid blocks.
Good: `User-Agent: my-tool/1.0 (+contact address)`, so the site owner can reach you.

### 5. Repeated pages
Bad: download the same page ten times while debugging.
Good: save each response to disk named by a hash of the URL, and reuse it.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Empty result | The page builds its content with JavaScript; look for the JSON endpoint it calls |
| `403` or `429` | Slow down, check the terms, or stop; do not disguise the client |
| Garbled characters | Decode with the charset from the response header, falling back to UTF-8 |
| Relative links | Join them with `urllib.parse.urljoin(base, href)` |
| Duplicates | Keep a set of seen URLs |
| Long run lost on error | Write results as you go |

## Checklist before you finish
- [ ] An API or feed was considered first; terms and robots.txt were checked.
- [ ] Delays, timeouts, retries and a clear User-Agent are in place.
- [ ] No personal data of private people is collected; no block is bypassed.
- [ ] Results are saved to CSV or JSON, and errors are counted and reported.
- [ ] I ran it on a few pages first and showed the output.
