#!/usr/bin/env python3
"""__TITLE__: a small JSON REST API using only the standard library and SQLite.

Run:        python api.py                  listens on 0.0.0.0:__PORT__ (override with --host/--port or the PORT variable)
Self test:  python api.py --selftest       starts the server on a free port, calls every route, exits 0 when all pass
Try:        curl -s localhost:__PORT__/items
            curl -s -X POST localhost:__PORT__/items -H 'Content-Type: application/json' -d '{"name": "First item"}'

Routes:     GET /health
            GET /items?q=text&limit=20&after=<id>      POST /items
            GET /items/<id>      PATCH /items/<id>      DELETE /items/<id>
Settings:   DB_PATH (default data.db), API_KEY (when set, writes need the X-API-Key header), CORS_ORIGIN (default *)

EDIT: MIGRATIONS (schema), validate() and row() for your own fields, the Store methods, and the routes below.
"""

import argparse
import hmac
import json
import logging
import os
import re
import signal
import sqlite3
import sys
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

DB_PATH = os.environ.get("DB_PATH", "data.db")
API_KEY = os.environ.get("API_KEY", "")
MAX_BODY = 64 * 1024
log = logging.getLogger("api")

# Append new steps; never edit one that has shipped. The database remembers how many ran (pragma user_version).
MIGRATIONS = [
    """create table items (
         id integer primary key,
         name text not null check (length(name) between 1 and 120),
         note text not null default '',
         done integer not null default 0 check (done in (0, 1)),
         created integer not null default (strftime('%s', 'now')))""",
    "create index idx_items_name on items(name)",
]


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        Exception.__init__(self, message)
        self.status, self.code, self.message, self.details = status, code, message, details


# --- data ---------------------------------------------------------------------------------------
def connect(path):
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("pragma foreign_keys = on")
    return db


def migrate(path):
    with closing(connect(path)) as db:
        db.execute("pragma journal_mode = wal")
        version = db.execute("pragma user_version").fetchone()[0]
        for number, sql in enumerate(MIGRATIONS[version:], start=version + 1):
            with db:
                db.execute(sql)
                db.execute("pragma user_version = %d" % number)


def row(r):
    return {"id": r["id"], "name": r["name"], "note": r["note"], "done": bool(r["done"]), "created": r["created"]}


def validate(body, partial=False):
    """Check one item sent by a client. Returns the clean fields or raises ApiError 422 with a message per field."""
    if not isinstance(body, dict):
        raise ApiError(422, "invalid_body", "The body must be a JSON object")
    clean, errors = {}, {}
    if "name" in body or not partial:
        name = body.get("name")
        if isinstance(name, str) and 1 <= len(name.strip()) <= 120:
            clean["name"] = name.strip()
        else:
            errors["name"] = "required, 1 to 120 characters"
    if "note" in body:
        if isinstance(body["note"], str) and len(body["note"]) <= 2000:
            clean["note"] = body["note"]
        else:
            errors["note"] = "text up to 2000 characters"
    if "done" in body:
        if isinstance(body["done"], bool):
            clean["done"] = int(body["done"])
        else:
            errors["done"] = "true or false"
    extra = sorted(set(body) - {"name", "note", "done"})
    if extra:
        errors["unknown"] = "unexpected field(s): " + ", ".join(extra)
    if errors:
        raise ApiError(422, "validation_failed", "Some fields are invalid", errors)
    return clean


class Store:
    """All SQL lives here. A short-lived connection per call keeps request threads independent."""

    def __init__(self, path):
        self.path = path

    def list(self, q, limit, after):
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with closing(connect(self.path)) as db:
            rows = db.execute("select * from items where id > ? and name like ? escape '\\' order by id limit ?", (after, like, limit)).fetchall()
        return [row(r) for r in rows]

    def get(self, item_id):
        with closing(connect(self.path)) as db:
            r = db.execute("select * from items where id = ?", (item_id,)).fetchone()
        return row(r) if r else None

    def create(self, data):
        with closing(connect(self.path)) as db, db:
            cur = db.execute("insert into items (name, note, done) values (?, ?, ?)", (data["name"], data.get("note", ""), data.get("done", 0)))
            new_id = cur.lastrowid
        return self.get(new_id)

    def update(self, item_id, data):
        if data:
            sets = ", ".join("%s = ?" % k for k in data)          # keys come from validate(), never from the client
            with closing(connect(self.path)) as db, db:
                db.execute("update items set %s where id = ?" % sets, list(data.values()) + [item_id])
        return self.get(item_id)

    def delete(self, item_id):
        with closing(connect(self.path)) as db, db:
            return db.execute("delete from items where id = ?", (item_id,)).rowcount > 0


# --- http ---------------------------------------------------------------------------------------
ROUTES = []


def route(method, pattern):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn))
        return fn
    return deco


def int_param(query, name, default, lo, hi):
    raw = query.get(name, [str(default)])[0]
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(400, "bad_parameter", "%s must be an integer" % name)
    if not lo <= value <= hi:
        raise ApiError(400, "bad_parameter", "%s must be between %d and %d" % (name, lo, hi))
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "api"
    store = None

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    def send_json(self, status, payload=None, headers=None):
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", os.environ.get("CORS_ORIGIN", "*"))
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            size = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "bad_length", "Invalid Content-Length header")
        if size > MAX_BODY:
            raise ApiError(413, "too_large", "The body is larger than %d bytes" % MAX_BODY)
        raw = self.rfile.read(size) if size else b""
        if not raw:
            raise ApiError(400, "empty_body", "A JSON body is required")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "invalid_json", "The body is not valid JSON")

    def dispatch(self):
        parts = urlsplit(self.path)
        try:
            if self.command == "OPTIONS":
                return self.send_json(204)
            path_known = False
            for method, rx, fn in ROUTES:
                m = rx.match(parts.path)
                if not m:
                    continue
                path_known = True
                if method != self.command:
                    continue
                if method != "GET" and API_KEY and not hmac.compare_digest(self.headers.get("X-API-Key", ""), API_KEY):
                    raise ApiError(401, "unauthorized", "Missing or wrong X-API-Key header")
                return fn(self, parse_qs(parts.query), *m.groups())
            raise ApiError(405, "method_not_allowed", "This path does not accept %s" % self.command) if path_known \
                else ApiError(404, "not_found", "No such path: %s" % parts.path)
        except ApiError as e:
            self.send_json(e.status, {"error": {"code": e.code, "message": e.message, "details": e.details}})
        except Exception:
            log.exception("unhandled error")
            self.send_json(500, {"error": {"code": "internal", "message": "Internal server error"}})

    do_GET = do_POST = do_PATCH = do_DELETE = do_OPTIONS = dispatch


@route("GET", "/health")
def health(h, q):
    h.send_json(200, {"status": "ok", "name": "__TITLE__"})


@route("GET", "/items")
def list_items(h, q):
    limit = int_param(q, "limit", 20, 1, 100)
    items = h.store.list(q.get("q", [""])[0][:100], limit, int_param(q, "after", 0, 0, 2 ** 62))
    h.send_json(200, {"items": items, "next_after": items[-1]["id"] if len(items) == limit else None})


@route("POST", "/items")
def create_item(h, q):
    item = h.store.create(validate(h.read_json()))
    h.send_json(201, item, {"Location": "/items/%d" % item["id"]})


@route("GET", r"/items/(\d+)")
def get_item(h, q, item_id):
    item = h.store.get(int(item_id))
    if not item:
        raise ApiError(404, "not_found", "No item with id %s" % item_id)
    h.send_json(200, item)


@route("PATCH", r"/items/(\d+)")
def patch_item(h, q, item_id):
    if not h.store.get(int(item_id)):
        raise ApiError(404, "not_found", "No item with id %s" % item_id)
    h.send_json(200, h.store.update(int(item_id), validate(h.read_json(), partial=True)))


@route("DELETE", r"/items/(\d+)")
def delete_item(h, q, item_id):
    if not h.store.delete(int(item_id)):
        raise ApiError(404, "not_found", "No item with id %s" % item_id)
    h.send_json(204)


# --- start-up and self test ---------------------------------------------------------------------
def make_server(host, port, db_path):
    migrate(db_path)
    Handler.store = Store(db_path)
    return ThreadingHTTPServer((host, port), Handler)


def selftest():
    import tempfile
    import urllib.error
    import urllib.request

    tmp = tempfile.mkdtemp(prefix="api_selftest_")
    server = make_server("127.0.0.1", 0, os.path.join(tmp, "test.db"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_address[1]

    def call(method, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                text = r.read()
                return r.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    failures = []

    def check(label, got, want):
        if got != want:
            failures.append("%s: got %r, wanted %r" % (label, got, want))

    try:
        check("health", call("GET", "/health")[0], 200)
        st, item = call("POST", "/items", {"name": "  First  ", "note": "hello"})
        check("create status", st, 201)
        check("create name trimmed", item["name"], "First")
        st, listing = call("GET", "/items?q=fir")
        check("search", (st, [i["name"] for i in listing["items"]]), (200, ["First"]))
        check("search is literal", call("GET", "/items?q=%25")[1]["items"], [])
        check("get", call("GET", "/items/%d" % item["id"])[1]["note"], "hello")
        st, changed = call("PATCH", "/items/%d" % item["id"], {"done": True})
        check("patch", (st, changed["done"], changed["name"]), (200, True, "First"))
        st, err = call("POST", "/items", {"name": "", "color": "red"})
        check("validation", (st, sorted(err["error"]["details"])), (422, ["name", "unknown"]))
        check("bad json", call("POST", "/items", raw=b"{nope")[0], 400)
        check("bad limit", call("GET", "/items?limit=abc")[0], 400)
        check("unknown id", call("GET", "/items/999")[0], 404)
        check("unknown path", call("GET", "/nothing")[0], 404)
        check("wrong method", call("POST", "/health", {})[0], 405)
        check("paging", [call("POST", "/items", {"name": "n%d" % i})[0] for i in range(3)], [201, 201, 201])
        st, page = call("GET", "/items?limit=2")
        check("next_after", page["next_after"], page["items"][-1]["id"])
        check("delete", call("DELETE", "/items/%d" % item["id"])[0], 204)
        check("deleted is gone", call("GET", "/items/%d" % item["id"])[0], 404)
    finally:
        server.shutdown()
        server.server_close()
    for f in failures:
        print("FAIL", f)
    print("selftest: %s" % ("all checks passed" if not failures else "%d check(s) failed" % len(failures)))
    return 1 if failures else 0


def main(argv=None):
    p = argparse.ArgumentParser(description="__TITLE__ API server")
    p.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "__PORT__")))
    p.add_argument("--db", default=DB_PATH, help="SQLite file (env DB_PATH)")
    p.add_argument("--selftest", action="store_true", help="run the built-in checks and exit")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.selftest:
        return selftest()
    server = make_server(args.host, args.port, args.db)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    log.info("listening on http://%s:%d (database %s)", args.host, args.port, args.db)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
