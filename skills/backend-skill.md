---
name: backend-skill
description: Build and test backends and APIs: stdlib, Flask, FastAPI and Express examples, SQLite, validation, auth, error handling, running the server and verifying every route.
---
# Backend skill (APIs, servers, databases)

## Choose the stack in one minute
Check what exists (`run_shell: python3 --version; node --version; pip list | head`). No packages and no internet? Use the **stdlib server** below. Python available with pip: **FastAPI** (typed, auto docs) or **Flask** (tiny). Node available: **Express**. Storage: SQLite (`sqlite3` is in the stdlib) unless the user needs multi-user scale. Do not add Docker, ORMs, queues or microservices unless asked.

## Project layout (small API)
```
app.py            routes only
db.py             connection, schema, queries
requirements.txt  pinned minimums
README.md         run + curl examples
tests/test_api.py
```

## Example A: FastAPI + SQLite (complete)
```python
# app.py   run: uvicorn app:app --port 8000        install: pip install fastapi uvicorn
import sqlite3
from contextlib import closing
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB = "items.db"
app = FastAPI(title="Items API")

def conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

with closing(conn()) as c:                                    # create the schema on startup
    c.execute("CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)"); c.commit()

class ItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    done: bool = False

@app.get("/items")
def list_items(limit: int = 50, offset: int = 0):
    with closing(conn()) as c:
        rows = c.execute("SELECT * FROM items ORDER BY id DESC LIMIT ? OFFSET ?", (min(limit, 200), max(offset, 0))).fetchall()
    return [dict(r) for r in rows]

@app.post("/items", status_code=201)
def create_item(item: ItemIn):
    with closing(conn()) as c:
        cur = c.execute("INSERT INTO items (title, done) VALUES (?, ?)", (item.title, int(item.done))); c.commit()
        return {"id": cur.lastrowid, **item.dict()}

@app.get("/items/{item_id}")
def get_item(item_id: int):
    with closing(conn()) as c:
        row = c.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row: raise HTTPException(404, "item not found")
    return dict(row)

@app.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int):
    with closing(conn()) as c:
        if c.execute("DELETE FROM items WHERE id = ?", (item_id,)).rowcount == 0: raise HTTPException(404, "item not found")
        c.commit()
```

## Example B: Flask (minimal)
```python
# pip install flask    run: flask --app app run --port 5000
from flask import Flask, jsonify, request, abort
app = Flask(__name__); ITEMS = {}; NEXT = [1]

@app.errorhandler(404)
def nf(e): return jsonify(error="not found"), 404

@app.post("/items")
def create():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    if not 1 <= len(title) <= 120: return jsonify(error="title must be 1-120 characters"), 422
    i = NEXT[0]; NEXT[0] += 1; ITEMS[i] = {"id": i, "title": title}; return jsonify(ITEMS[i]), 201

@app.get("/items/<int:i>")
def one(i): return jsonify(ITEMS[i]) if i in ITEMS else abort(404)
```

## Example C: Express
```javascript
// npm install express      run: node server.js
const express = require("express"); const app = express(); app.use(express.json());
const items = new Map(); let next = 1;
app.post("/items", (req, res) => {
  const title = String((req.body || {}).title || "").trim();
  if (!title || title.length > 120) return res.status(422).json({ error: "title must be 1-120 characters" });
  const item = { id: next++, title }; items.set(item.id, item); res.status(201).json(item);
});
app.get("/items/:id", (req, res) => items.has(+req.params.id) ? res.json(items.get(+req.params.id)) : res.status(404).json({ error: "not found" }));
app.use((err, req, res, next) => res.status(500).json({ error: "internal error" }));   // never leak stack traces
app.listen(3000, () => console.log("http://127.0.0.1:3000"));
```

## Example D: stdlib only (no installs): a working JSON API
```python
# server.py   run: python3 server.py
import json, sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

db = sqlite3.connect(":memory:", check_same_thread=False)
db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT NOT NULL)")

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj=None):
        body = json.dumps(obj).encode() if obj is not None else b""
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/items": return self._send(200, [{"id": r[0], "title": r[1]} for r in db.execute("SELECT id, title FROM items")])
        self._send(404, {"error": "not found"})
    def do_POST(self):
        try: data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except ValueError: return self._send(400, {"error": "invalid JSON"})
        title = str(data.get("title", "")).strip()
        if not 1 <= len(title) <= 120: return self._send(422, {"error": "title must be 1-120 characters"})
        cur = db.execute("INSERT INTO items (title) VALUES (?)", (title,)); db.commit(); self._send(201, {"id": cur.lastrowid, "title": title})
    def log_message(self, *a): pass

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()
```

## Rules that prevent most backend bugs
- Validate every input at the boundary (type, length, range). Return 400/422 with a clear message; never a stack trace.
- Parameterized SQL only (`?`). Create tables with `IF NOT EXISTS`. Use a transaction for multi-step writes.
- Consistent errors `{"error": "..."}` and honest status codes: 201 created, 204 deleted, 404 missing, 409 conflict, 422 invalid.
- Auth: hash passwords with `hashlib.scrypt` and a random salt; signed tokens with expiry (HMAC, `hmac.compare_digest`); secrets from environment variables, never in code.
- Bind to `127.0.0.1` unless the user needs network access. CORS only for needed origins. Rate-limit login endpoints if exposed.
- Timeouts and retries with backoff on every outgoing HTTP call. Log errors with context, never secrets.
- Paginate lists (default limit 50, max 200).

## Password hashing and tokens (stdlib)
```python
import hashlib, hmac, os, base64, json, time
def hash_pw(pw, salt=None):
    salt = salt or os.urandom(16); return salt.hex() + ":" + hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1).hex()
def check_pw(pw, stored):
    salt, _ = stored.split(":"); return hmac.compare_digest(hash_pw(pw, bytes.fromhex(salt)), stored)
SECRET = os.environ.get("APP_SECRET", "change-me").encode()
def make_token(uid, ttl=3600):
    payload = base64.urlsafe_b64encode(json.dumps({"u": uid, "exp": int(time.time()) + ttl}).encode()).decode()
    return payload + "." + hmac.new(SECRET, payload.encode(), "sha256").hexdigest()
def read_token(tok):
    payload, sig = tok.rsplit(".", 1)
    if not hmac.compare_digest(sig, hmac.new(SECRET, payload.encode(), "sha256").hexdigest()): return None
    data = json.loads(base64.urlsafe_b64decode(payload)); return data if data["exp"] > time.time() else None
```

## Run and verify (always do this before saying done)
1. Syntax: `python3 -m py_compile app.py` (verify_files does it too).
2. Install: `pip install -r requirements.txt` (on Debian/Kali use a venv: `python3 -m venv .venv && . .venv/bin/activate`).
3. Start: `run_shell(command="python3 server.py", background=true)`, wait 2 seconds.
4. Test every route with `http_request` or curl: one success case and one failure case each.
```
curl -s -X POST localhost:8000/items -H 'Content-Type: application/json' -d '{"title":"first"}'
curl -s localhost:8000/items
curl -s -X POST localhost:8000/items -d 'not json'          # must return 400, not crash
```
5. Stop the server with manage_process. Report the exact start command, port and example requests.

## Troubleshooting
| Symptom | Cause | Fix |
|---|---|---|
| `Address already in use` | Old server still running | manage_process list/stop, or use another port |
| `Connection refused` | Server not started or wrong port | Start first, wait 2 s, check the port |
| `ModuleNotFoundError` | Not installed or venv not active | `pip install`, activate the venv |
| 422 on a valid request | Wrong Content-Type or field names | Send `Content-Type: application/json` and exact field names |
| `database is locked` | Concurrent writes without timeout | `sqlite3.connect(db, timeout=10)`, short transactions |
| CORS error in the browser | Missing headers | Allow the exact origin, handle the OPTIONS preflight |
