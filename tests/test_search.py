"""Search providers, ranking, fallback, research tools and the HTTP helpers, against a local mock server (no internet needed)."""

import base64
import gzip
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from axion import search as engine  # noqa: E402
from axion.state import Ctx, ToolError  # noqa: E402
from axion.tools.research import keywords, pick_passages, t_deep_research, t_package_info, t_web_search  # noqa: E402
from axion.tools.web import t_web_fetch  # noqa: E402
from axion.webutil import fetch_clean, http_fetch, PageParser  # noqa: E402


def b64(s):
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


DDG_HTML = """<html><body>
<div class="result"><h2><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fdocs%3Futm_source%3Dx&amp;rut=abc">Example <b>Docs</b></a></h2>
<a class="result__snippet" href="//duckduckgo.com/l/?uddg=x">The <b>official</b> documentation &amp; guide.</a></div>
<div class="result result--ad"><a class="result__a" href="https://duckduckgo.com/y.js?ad_provider=bing">Ad</a></div>
<div class="result"><a class="result__a" href="https://other.net/a">Other page</a><a class="result__snippet" href="x">Second snippet</a></div>
</body></html>"""

DDG_LITE = """<table><tr><td><a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Flite.example%2Fone" class='result-link'>Lite one</a></td></tr>
<tr><td class='result-snippet'>Lite <b>snippet</b> one</td></tr>
<tr><td><a rel="nofollow" href="https://lite.example/two" class='result-link'>Lite two</a></td></tr>
<tr><td class='result-snippet'>Lite snippet two</td></tr></table>"""

BING_HTML = ("<ol id='b_results'><li class=\"b_algo\"><h2><a href=\"https://www.bing.com/ck/a?!&amp;&amp;p=abc&amp;u=a1%s&amp;ntb=1\">Guide <strong>one</strong></a></h2>"
             "<div class=\"b_caption\"><p class=\"b_lineclamp2\">A snippet about the guide.</p></div></li>"
             "<li class=\"b_algo\"><h2><a href=\"https://plain.example.net/page\">Plain</a></h2><div class=\"b_caption\"><p>Plain snippet</p></div></li></ol>"
             % b64("https://example.com/guide"))

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Big release ships</title><link>https://news.example/big</link><pubDate>Tue, 03 Mar 2026 10:00:00 GMT</pubDate><source>Example News</source><description>&lt;p&gt;Details here&lt;/p&gt;</description></item>
<item><title>Bing wrapped</title><link>http://www.bing.com/news/apiclick.aspx?ref=x&amp;url=https%3a%2f%2fwrapped.example%2fstory&amp;c=1</link><pubDate>Wed, 04 Mar 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2401.00001v1</id>
<published>2024-01-02T00:00:00Z</published><title>Attention variants</title><summary>We study attention.</summary></entry></feed>"""

PAGE_1 = """<html><head><title>Flask quickstart</title><meta property="article:published_time" content="2025-03-04T10:00:00Z"></head><body>
<nav>menu menu menu</nav><main><h1>Flask quickstart</h1>
<p>To create a Flask application you call Flask(__name__) and define routes with the route decorator, which maps URLs to functions.</p>
<p>Unrelated paragraph about cats and dogs and the weather today, long enough to count as a paragraph on its own.</p>
<p>The development server is started with flask run and the debug flag enables the reloader for faster work.</p></main><footer>footer links</footer></body></html>"""

PAGE_2 = """<html><head><title>Routing guide</title></head><body><article><h1>Routing</h1>
<p>Routes connect URL rules to view functions. A Flask application object keeps the routing table and creates the rules for you.</p></article></body></html>"""


class Mock(BaseHTTPRequestHandler):
    hits = {}
    flaky = {"n": 0}

    def log_message(self, *a):
        pass

    def reply(self, status, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_any(self):
        path = urllib.parse.urlsplit(self.path).path
        Mock.hits[path] = Mock.hits.get(path, 0) + 1
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        j = lambda obj: self.reply(200, json.dumps(obj))   # noqa: E731
        if path == "/ddg/blocked":
            return self.reply(202, "<html><div class='anomaly-modal'>unusual traffic</div></html>", "text/html")
        if path == "/ddg/html":
            return self.reply(200, DDG_HTML, "text/html")
        if path == "/ddg/lite":
            return self.reply(200, DDG_LITE, "text/html")
        if path == "/bing/search":
            return self.reply(200, BING_HTML, "text/html")
        if path == "/news/google":
            return self.reply(200, RSS, "application/rss+xml")
        if path == "/wikiapi/en":
            return j({"query": {"search": [{"title": "Flask (web framework)", "snippet": "A <span>micro</span> framework"}]}})
        if path == "/se":
            return j({"items": [{"title": "How do I use &amp; test flask?", "link": "https://stackoverflow.com/q/1", "score": 12,
                                 "answer_count": 3, "accepted_answer_id": 9, "tags": ["python", "flask"], "creation_date": 1700000000}]})
        if path == "/gh":
            return j({"items": [{"full_name": "pallets/flask", "html_url": "https://github.com/pallets/flask", "description": "web framework",
                                 "stargazers_count": 70000, "language": "Python", "pushed_at": "2026-01-02T00:00:00Z"}]})
        if path == "/hn":
            return j({"hits": [{"title": "Show HN: thing", "url": None, "objectID": "42", "points": 100, "num_comments": 7, "created_at": "2026-02-01T00:00:00Z"}]})
        if path == "/npm/search":
            return j({"objects": [{"package": {"name": "express", "version": "5.1.0", "description": "web framework",
                                               "date": "2026-01-10T00:00:00Z", "links": {"npm": "https://www.npmjs.com/package/express"}}}]})
        if path == "/npm/pkg/express/latest":
            return j({"name": "express", "version": "5.1.0", "description": "Fast web framework", "license": "MIT",
                      "engines": {"node": ">=18"}, "dependencies": {"a": "1", "b": "2"}, "homepage": "https://expressjs.com"})
        if path == "/pypi/requests/json":
            return j({"info": {"name": "requests", "version": "2.99.0", "summary": "HTTP for humans", "license_expression": "Apache-2.0",
                               "requires_python": ">=3.8", "requires_dist": ["urllib3", "idna"], "home_page": "https://requests.example"},
                      "urls": [{"upload_time_iso_8601": "2026-02-03T04:05:06Z"}]})
        if path.startswith("/pypi/"):
            return self.reply(404, "{}")
        if path == "/mdn":
            return j({"documents": [{"title": "fetch()", "mdn_url": "/en-US/docs/Web/API/fetch", "summary": "Fetch API"}]})
        if path == "/arxiv":
            return self.reply(200, ATOM, "application/atom+xml")
        if path == "/crossref":
            return j({"message": {"items": [{"title": ["A paper"], "DOI": "10.1/x", "URL": "https://doi.org/10.1/x",
                                             "container-title": ["Journal"], "issued": {"date-parts": [[2025, 1]]}}]}})
        if path == "/p/1":
            return self.reply(200, PAGE_1, "text/html; charset=utf-8")
        if path == "/p/2":
            return self.reply(200, PAGE_2, "text/html")
        if path == "/p/json":
            return self.reply(200, '{"a":1}', "application/json")
        if path == "/p/pdf":
            return self.reply(200, b"%PDF-1.4 fake", "application/pdf")
        if path == "/p/latin1":
            return self.reply(200, "<html><head><meta charset='iso-8859-1'><title>caf\xe9</title></head><body><p>caf\xe9 au lait</p></body></html>".encode("latin-1"), "text/html")
        if path == "/p/gzip-bomb":
            return self.reply(200, gzip.compress(b"\0" * 60000000), "text/plain", {"Content-Encoding": "gzip"})
        if path == "/p/flaky":
            Mock.flaky["n"] += 1
            return self.reply(503, "busy", "text/plain", {"Retry-After": "0"}) if Mock.flaky["n"] == 1 else self.reply(200, "recovered", "text/plain")
        return self.reply(404, "not found", "text/plain")

    do_GET = handle_any
    do_POST = handle_any


class SearchBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.saved = dict(engine.E)
        b = cls.base
        cls.endpoints = {"ddg": b + "/ddg/html", "ddg_lite": b + "/ddg/lite", "bing": b + "/bing/search", "bing_news": b + "/news/google",
                         "google_news": b + "/news/google", "wikipedia": b + "/wikiapi/%s", "wikipedia_page": b + "/wikipage/%s/",
                         "stackexchange": b + "/se", "github": b + "/gh", "hackernews": b + "/hn", "npm_search": b + "/npm/search",
                         "npm_package": b + "/npm/pkg/", "pypi": b + "/pypi/", "mdn": b + "/mdn", "mdn_site": "https://mdn.example",
                         "arxiv": b + "/arxiv", "crossref": b + "/crossref"}
        engine.E.update(cls.endpoints)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        engine.E.clear()
        engine.E.update(cls.saved)

    def setUp(self):
        engine.E.update(self.endpoints)
        engine.reset_state()
        Mock.hits.clear()
        Mock.flaky["n"] = 0


class Parsers(unittest.TestCase):
    def test_ddg_html_unwraps_links_skips_ads_and_reads_snippets(self):
        res = engine.parse_ddg_html(DDG_HTML, 10)
        self.assertEqual([r["url"] for r in res], ["https://example.org/docs?utm_source=x", "https://other.net/a"])
        self.assertEqual(res[0]["title"], "Example Docs")
        self.assertEqual(res[0]["snippet"], "The official documentation & guide.")

    def test_ddg_lite(self):
        res = engine.parse_ddg_lite(DDG_LITE, 10)
        self.assertEqual([r["url"] for r in res], ["https://lite.example/one", "https://lite.example/two"])
        self.assertEqual(res[0]["snippet"], "Lite snippet one")

    def test_bing_redirect_is_decoded(self):
        res = engine.parse_bing(BING_HTML, 10)
        self.assertEqual(res[0]["url"], "https://example.com/guide")
        self.assertEqual(res[0]["title"], "Guide one")
        self.assertEqual(res[1]["url"], "https://plain.example.net/page")

    def test_normalized_keys_ignore_tracking_and_www(self):
        a = engine.norm_key("https://www.Example.com/a/?utm_source=x&id=2")
        b = engine.norm_key("http://example.com/a?id=2&fbclid=zzz")
        self.assertEqual(a, b)

    def test_merge_rewards_agreement_and_dedupes(self):
        r = lambda u: engine.R("t", u, "s", "x")   # noqa: E731
        merged = engine.merge([("p1", [r("https://a.com/1"), r("https://b.com/2")]), ("p2", [r("https://b.com/2?utm_x=1"), r("https://c.com/3")])], 10)
        self.assertEqual(merged[0]["url"], "https://b.com/2")
        self.assertEqual(sorted(merged[0]["sources"]), ["p1", "p2"])
        self.assertEqual(len(merged), 3)

    def test_keywords_and_passages(self):
        self.assertEqual(keywords("How do I create a Flask application with routes?"), ["create", "flask", "application", "routes"])
        text = "Intro paragraph that is long enough to be kept as a paragraph.\n\nFlask routes map URLs to view functions in the application object.\n\nCats."
        self.assertEqual(pick_passages(text, ["flask", "routes"], 500), ["Flask routes map URLs to view functions in the application object."])


class Providers(SearchBase):
    def test_general_search_merges_two_providers(self):
        found = engine.search("flask docs", n=3, keys={})
        urls = [r["url"] for r in found["results"]]
        self.assertIn("https://example.org/docs?utm_source=x", urls)
        self.assertIn("https://example.com/guide", urls)
        self.assertEqual(sorted(found["used"]), ["bing", "ddg"])

    def test_blocked_provider_falls_back_and_rests(self):
        engine.E["ddg"] = self.base + "/ddg/blocked"
        found = engine.search("flask docs", keys={})
        self.assertTrue(found["results"])
        self.assertTrue(any(n.startswith("ddg:") for n in found["notes"]), found["notes"])
        self.assertTrue(engine._cooling("ddg"))
        engine.E["ddg"] = self.base + "/ddg/html"
        found2 = engine.search("another query", keys={})
        self.assertEqual(found2["used"][-1], "ddg")           # a resting provider is only a last resort
        self.assertTrue(found2["results"])

    def test_every_provider_failing_raises_a_clear_error(self):
        for k in ("ddg", "ddg_lite", "bing"):
            engine.E[k] = self.base + "/nothing-here"
        with self.assertRaises(ToolError) as cm:
            engine.search("flask docs", keys={})
        self.assertIn("every search provider failed", str(cm.exception))

    def test_results_are_cached(self):
        engine.search("cache me", keys={})
        n = Mock.hits["/ddg/html"]
        engine.search("cache me", keys={})
        self.assertEqual(Mock.hits["/ddg/html"], n)

    def test_news_parses_rss_and_unwraps_bing_links(self):
        found = engine.search("big release", kind="news", keys={})
        urls = {r["url"] for r in found["results"]}
        self.assertIn("https://news.example/big", urls)
        self.assertIn("https://wrapped.example/story", urls)
        first = [r for r in found["results"] if r["url"] == "https://news.example/big"][0]
        self.assertEqual(first["date"], "2026-03-03")
        self.assertIn("Example News", first["snippet"])

    def test_code_kind_uses_stackexchange_and_github(self):
        found = engine.search("flask test", kind="code", keys={})
        self.assertIn("https://stackoverflow.com/q/1", [r["url"] for r in found["results"]])
        self.assertIn("https://github.com/pallets/flask", [r["url"] for r in found["results"]])
        se = [r for r in found["results"] if "stackoverflow" in r["url"]][0]
        self.assertEqual(se["title"], "How do I use & test flask?")
        self.assertIn("accepted answer", se["snippet"])

    def test_other_kinds(self):
        self.assertEqual(engine.search("flask", kind="wiki", keys={})["results"][0]["url"], self.base + "/wikipage/en/Flask_%28web_framework%29")
        self.assertEqual(engine.search("fetch", kind="docs", keys={})["results"][0]["url"], "https://mdn.example/en-US/docs/Web/API/fetch")
        academic = engine.search("attention", kind="academic", keys={})
        self.assertEqual({r["source"] for r in academic["results"]}, {"arxiv", "crossref", "wikipedia"})
        hn = engine.search("thing", kind="discussion", providers=["hackernews"], keys={})
        self.assertEqual(hn["results"][0]["url"], "https://news.ycombinator.com/item?id=42")

    def test_keyed_providers_are_skipped_without_keys_and_validated(self):
        with self.assertRaises(ToolError):
            engine.search("x", providers=["brave"], keys={})
        with self.assertRaises(ToolError):
            engine.search("x", providers=["nope"], keys={})

    def test_package_info(self):
        pk = engine.package_info("requests")
        self.assertEqual([p["eco"] for p in pk], ["pypi"])                 # not on npm in the mock
        self.assertEqual(pk[0]["version"], "2.99.0")
        self.assertEqual(pk[0]["date"], "2026-02-03")
        self.assertIn("pip install requests==2.99.0", engine.format_package(pk[0]))
        ex = engine.package_info("express", "npm")[0]
        self.assertEqual((ex["version"], ex["date"], ex["requires"], ex["deps"]), ("5.1.0", "2026-01-10", ">=18", 2))
        with self.assertRaises(ToolError):
            engine.package_info("does-not-exist-123")
        with self.assertRaises(ToolError):
            engine.package_info("bad name;rm")


class Tools(SearchBase):
    def setUp(self):
        SearchBase.setUp(self)
        self.ctx = Ctx({"model": "x/y"}, Path(tempfile.mkdtemp(prefix="axion_ws_")))

    def test_web_search_tool_output(self):
        out = t_web_search({"query": "flask docs"}, self.ctx)
        self.assertIn("Search: 'flask docs'", out)
        self.assertIn("https://example.com/guide", out)
        with self.assertRaises(ToolError):
            t_web_search({"query": "x", "kind": "bogus"}, self.ctx)

    def test_package_info_tool(self):
        self.assertIn("express: ", t_package_info({"name": "express", "ecosystem": "npm"}, self.ctx).replace("npm: ", "express: "))

    def test_deep_research_reads_pages_and_cites_them(self):
        engine.E["bing"] = self.base + "/nothing-here"
        engine.E["ddg_lite"] = self.base + "/nothing-here"
        global DDG_HTML
        saved = DDG_HTML
        DDG_HTML = saved.replace("https%3A%2F%2Fexample.org%2Fdocs%3Futm_source%3Dx", urllib.parse.quote(self.base + "/p/1", safe="")) \
                        .replace("https://other.net/a", self.base + "/p/2")
        try:
            out = t_deep_research({"question": "How do I create a Flask application with routes?", "queries": ["flask routes tutorial"]}, self.ctx)
        finally:
            DDG_HTML = saved
        self.assertIn("DEEP RESEARCH", out)
        self.assertIn("[1] Flask quickstart", out)
        self.assertIn("2025-03-04", out)
        self.assertIn("route decorator", out)
        self.assertNotIn("cats and dogs", out)
        self.assertNotIn("menu menu", out)
        self.assertIn("[2] Routing guide", out)
        self.assertTrue((Path(self.ctx.ws) / "history" / "notes.md").exists())

    def test_web_fetch_reads_several_urls_at_once(self):
        out = t_web_fetch({"url": self.base + "/p/1", "urls": [self.base + "/p/2", self.base + "/p/missing"]}, self.ctx)
        self.assertIn("=== [1]", out)
        self.assertIn("route decorator", out)
        self.assertIn("Routing", out)
        self.assertIn("HTTP 404", out)
        self.assertIn("Published: 2025-03-04", out)

    def test_pdf_and_json(self):
        self.assertIn("PDF document", t_web_fetch({"url": self.base + "/p/pdf"}, self.ctx))
        self.assertIn('"a": 1', t_web_fetch({"url": self.base + "/p/json"}, self.ctx))


class HttpLayer(SearchBase):
    def test_retry_once_on_503(self):
        info = http_fetch("GET", self.base + "/p/flaky")
        self.assertEqual((info["status"], info["body"]), (200, b"recovered"))

    def test_charset_comes_from_the_meta_tag(self):
        res = fetch_clean(self.base + "/p/latin1")
        self.assertEqual(res["title"], "caf\xe9")
        self.assertIn("caf\xe9 au lait", res["text"])

    def test_decompression_is_bounded(self):
        t0 = time.time()
        info = http_fetch("GET", self.base + "/p/gzip-bomb")
        self.assertLessEqual(len(info["body"]), 3000000)
        self.assertTrue(info["truncated"])
        self.assertLess(time.time() - t0, 20)

    def test_fetch_clean_never_raises(self):
        res = fetch_clean("http://127.0.0.1:9/unreachable", timeout=2)
        self.assertTrue(res["error"])
        self.assertEqual(res["text"], "")

    def test_main_text_prefers_article_and_skips_chrome(self):
        pp = PageParser(skip_chrome=True)
        pp.feed(PAGE_1)
        text = pp.main_text(min_chars=50)
        self.assertIn("route decorator", text)
        self.assertNotIn("menu", text)
        self.assertNotIn("footer", text)
        self.assertEqual(pp.published(), "2025-03-04")


if __name__ == "__main__":
    unittest.main()
