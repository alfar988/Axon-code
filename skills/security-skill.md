---
name: security-skill
description: Secure by default: SQL injection, XSS, path traversal, SSRF, password hashing, secrets, tokens and rate limiting, each as vulnerable vs safe code. Runnable examples.
---
# Security skill

Assume every input is hostile: form fields, query strings, headers, file names, uploaded files, API responses, text from web pages. Validate on the server even when the browser already did.

## Quick rules (read first)
1. SQL uses parameters. HTML gets text through `textContent` or escaping. Commands are lists of arguments, never joined strings.
2. Check every input: type, size, range and allowed characters. Reject, do not "clean up", when unsure.
3. Keep secrets out of code, logs and git. Read them from the environment.
4. Hash passwords with a salt (scrypt or PBKDF2). Compare secrets in constant time.
5. Give each part the least access it needs. Rate-limit login and anything expensive.
6. Server-side fetches of a user's URL must refuse private and local addresses.

## Safety in this skill
- Defence is always welcome: reviews, fixes, tests of the user's own systems.
- Do not write working attack tools or exploit code for systems the user does not own or may not test. If the user says it is their own system, keep it to checking and fixing, and suggest the vendor's responsible-disclosure route for anything found in someone else's product.

## SQL: parameters, never string building
```python
# check: runs
import sqlite3

db = sqlite3.connect(":memory:")
db.execute("create table users (name text, role text)")
db.executemany("insert into users values (?, ?)", [("ann", "admin"), ("bob", "user")])

evil = "x' or '1'='1"
unsafe = db.execute("select name from users where name = '%s'" % evil).fetchall()          # vulnerable
safe = db.execute("select name from users where name = ?", (evil,)).fetchall()             # parameterized
assert len(unsafe) == 2 and safe == []
print("unsafe leaked", len(unsafe), "rows; safe returned", len(safe))
```
Table or column names cannot be parameters: pick them from a fixed allow-list.

## HTML: text goes in as text
Browser: `el.textContent = value`, never `innerHTML` with user data. If you must build HTML, escape first:
```python
# check: runs
from html import escape
assert escape('<img src=x onerror="alert(1)">') == "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"
```
Set `Content-Security-Policy` for pages you serve (`default-src 'self'`), cookies `HttpOnly; Secure; SameSite=Lax`.

## Files: stay inside the folder
```python
# check: runs
from pathlib import Path

def safe_join(root, user_path):
    root = Path(root).resolve()
    target = (root / user_path).resolve()
    if root != target and root not in target.parents:
        raise ValueError("path escapes the base folder")
    return target

safe_join("/srv/files", "reports/a.txt")
for bad in ("../etc/passwd", "/etc/passwd", "a/../../x"):
    try:
        safe_join("/srv/files", bad)
    except ValueError:
        continue
    raise SystemExit("traversal not blocked: " + bad)
print("traversal blocked")
```
Archives: check every member path before extracting. Uploads: whitelist extensions and size, store under a generated name.

## SSRF: server-side fetches of user URLs
```python
# check: runs
import ipaddress
import socket
from urllib.parse import urlsplit

def is_public_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443)
    except socket.gaierror:
        return False
    return all(ipaddress.ip_address(i[4][0]).is_global for i in infos)

assert not is_public_url("http://127.0.0.1:8080/admin")
assert not is_public_url("file:///etc/passwd")
assert not is_public_url("http://169.254.169.254/latest/meta-data/")
print("private targets refused")
```
Also re-check after redirects, and set a timeout and a size limit.

## Passwords and tokens
```python
# check: runs
import hashlib
import hmac
import os
import secrets

def hash_password(password, n=2 ** 14):
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=8, p=1, dklen=32)
    return "scrypt$%d$%s$%s" % (n, salt.hex(), digest.hex())

def verify_password(password, stored):
    _, n, salt, digest = stored.split("$")
    check = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=8, p=1, dklen=32)
    return hmac.compare_digest(check.hex(), digest)          # constant-time comparison

h = hash_password("correct horse")
assert verify_password("correct horse", h) and not verify_password("wrong", h)
token = secrets.token_urlsafe(32)                            # session ids, reset links: never random.random()
print("ok", len(token))
```
Never store plain or fast-hashed (MD5, SHA-256) passwords. Same error message for "unknown user" and "wrong password". Sessions: expire them, rotate on login. JWT: pin the algorithm on verify, short expiry, secret from the environment, never put secrets in the payload.

## Secrets
Read from environment variables (`os.environ["API_KEY"]`, `process.env.API_KEY`); keep `.env` in `.gitignore`; ship `.env.example` with fake values. In Lumo use `{{NAME}}` placeholders and `/secret set NAME`. A secret that reached git is burned: rotate it first, then clean history.

## Rate limiting (token bucket)
```python
# check: runs
import time

class Bucket:
    def __init__(self, rate, burst):
        self.rate, self.burst, self.tokens, self.t = rate, burst, burst, time.monotonic()

    def allow(self):
        now = time.monotonic()
        self.tokens = min(self.burst, self.tokens + (now - self.t) * self.rate)
        self.t = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

b = Bucket(rate=1, burst=3)
assert [b.allow() for _ in range(5)] == [True, True, True, False, False]
```
Apply it per client (IP or user id) on login, signup, password reset and expensive endpoints.

## Web checklist
HTTPS only. CORS: list exact origins, never `*` with credentials. CSRF token or `SameSite` cookies for state-changing requests. Validate type, length and range of every field. Return generic errors to clients, log details on the server. Pin dependency versions and run `pip audit` or `npm audit`.

## Good and bad examples

### 1. Text in HTML
Bad: `html = "<p>" + comment + "</p>"` with `comment = "<script>steal()</script>"`.
Good: escape on the server, or set `textContent` in the browser.
```python
# check: runs
import html

comment = "<script>steal()</script>"
safe = "<p>" + html.escape(comment) + "</p>"
assert "<script>" not in safe
assert safe == "<p>&lt;script&gt;steal()&lt;/script&gt;</p>"
```

### 2. Fetching a user's URL
Bad: `urlopen(user_url)` lets someone ask your server to read `http://127.0.0.1/admin`.
Good: resolve the host and refuse anything that is not a public address.
```python
# check: runs
import ipaddress, socket
from urllib.parse import urlparse

def is_public_url(url):
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return False
    return all(ipaddress.ip_address(a).is_global for a in addrs)

assert not is_public_url("http://127.0.0.1/admin")
assert not is_public_url("http://localhost:8000")
assert not is_public_url("not a url")
```

### 3. Comparing secrets
Bad: `if token == expected:` leaks timing information.
Good:
```python
# check: runs
import hmac

assert hmac.compare_digest("abc123", "abc123")
assert not hmac.compare_digest("abc123", "abc124")
```

### 4. Secrets in code
Bad: `API_KEY = "sk-live-..."` committed to git.
Good: `API_KEY = os.environ["API_KEY"]`, a `.env.example` with fake values, and `.env` in `.gitignore`. If a key was committed, revoke it first.

### 5. Uploaded file names
Bad: save the file as the client names it (`../../app.py`).
Good: generate your own name (`uuid4().hex + allowed extension`) and keep files outside the web root.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Checking permission only in the page | Check on the server for every request |
| Using `Math.random()` or `random` for tokens | Use `secrets.token_urlsafe(32)` or `crypto.randomUUID()` |
| Verbose error pages in production | Log details privately; show a short message |
| Old dependencies with known holes | Update, and prefer fewer dependencies |
| CORS `*` with credentials | List the allowed origins |
| Trusting a hidden form field or a cookie value | Treat it as user input |

## Checklist before you finish
- [ ] No string-built SQL, no unescaped HTML, no `shell=True` with outside text.
- [ ] No secret in code, logs or git; passwords are hashed.
- [ ] Access is checked on the server; logins and heavy routes are rate-limited.
- [ ] User-supplied URLs and file names are validated.
- [ ] Anything offensive stayed inside the user's own systems.
