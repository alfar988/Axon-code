"""OpenRouter client: streaming, retries, stall detection, error classification."""

import http.client
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from axion.config import API_BASE, MAXREQ_DEFAULT, STALL_DEFAULT, UA
from axion.state import ApiError, bump_req, key_of, NoToolsError


NET_ERRORS = (socket.timeout, TimeoutError, ConnectionError, OSError, http.client.HTTPException)


# --- network: prefer IPv4 (fixes Errno 103 on many mobile networks) ----------------
_REAL_GAI = socket.getaddrinfo


NETSTATE = {"ipv4_only": False}


def _gai_v4_first(host, port, family=0, type=0, proto=0, flags=0):
    res = _REAL_GAI(host, port, family, type, proto, flags)
    v4 = [r for r in res if r[0] == socket.AF_INET]
    v6 = [r for r in res if r[0] != socket.AF_INET]
    if NETSTATE["ipv4_only"] and v4:
        return v4
    return v4 + v6


socket.getaddrinfo = _gai_v4_first


def open_conn(url, connect_timeout, read_timeout):
    u = urllib.parse.urlparse(url)
    cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    conn = cls(u.hostname, u.port, timeout=connect_timeout)
    conn.connect()
    try:
        s = conn.sock
        s.settimeout(read_timeout)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for opt, val in (("TCP_KEEPIDLE", 15), ("TCP_KEEPINTVL", 8), ("TCP_KEEPCNT", 8)):
            if hasattr(socket, opt):
                s.setsockopt(socket.IPPROTO_TCP, getattr(socket, opt), val)
    except OSError:
        pass
    return conn, u.path + (("?" + u.query) if u.query else "")


def read_json(resp, on_text):
    """Non-streaming mode (fallback when the stream keeps dropping)."""
    data = json.loads(resp.read().decode("utf-8", "replace"))
    if data.get("error"):
        raise ApiError(extract_error(json.dumps(data)), retryable=True, kind="server")
    ch = (data.get("choices") or [{}])[0]
    m = ch.get("message") or {}
    content = m.get("content")
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if content:
        on_text(content)
    tcs = []
    for i, tc in enumerate(m.get("tool_calls") or []):
        fn = tc.get("function") or {}
        a = fn.get("arguments")
        a = json.dumps(a) if isinstance(a, dict) else (a or "{}")
        tcs.append({"id": tc.get("id") or "call_%d" % i, "type": "function", "function": {"name": fn.get("name", ""), "arguments": a}})
    msg = {"role": "assistant", "content": content or None}
    if tcs:
        msg["tool_calls"] = tcs
    return msg, ch.get("finish_reason"), data.get("usage"), (m.get("reasoning") or m.get("reasoning_content") or "")


def extract_error(txt):
    try:
        j = json.loads(txt)
        e = j.get("error", j)
        if isinstance(e, dict):
            msg = e.get("message") or json.dumps(e)
            raw = (e.get("metadata") or {}).get("raw")
            return msg + (" | " + str(raw)[:200] if raw else "")
        return str(e)
    except Exception:
        if "<html" in txt[:600].lower() or "cloudflare" in txt[:2000].lower():
            return "an HTML page from the server (probably blocked by the network or Cloudflare)"
        return txt[:300]


def classify_http(code, low):
    if code == 401:
        return "auth"
    if code == 403:
        if re.search(r"cloudflare|just a moment|error code: ?10\d\d|attention required|<html", low):
            return "blocked"
        if re.search(r"invalid.{0,12}(api[ _-]?)?key|api[ _-]?key.{0,30}(invalid|revoked|disabled|expired|not found)|"
                     r"unauthorized|no auth|missing.{0,10}credentials|user not found", low):
            return "auth"
        if re.search(r"key.{0,40}limit|spend limit|limit exceeded", low):
            return "credits"
        return "forbidden"
    if code == 402:
        return "credits"
    if code == 429:
        return "daily" if ("per-day" in low or "per day" in low or "daily" in low) else "rate"
    if code == 400 and re.search(r"context|too long|maximum.{0,20}length|token limit|too many tokens|exceed", low):
        return "ctx"
    if code in (400, 422) and re.search(r"invalid json|json in tool|tool[ _]call|malformed|invalid.{0,24}argument", low):
        return "badreq"
    if code in (400, 422) and re.search(r"max[_ ]?(?:completion[_ ])?tokens|max_new_tokens|output tokens|maximum.{0,14}(?:completion|output)", low):
        return "maxtok"
    if code in (404, 410):
        return "notfound"
    if code in (408, 409, 425, 500, 502, 503, 504, 520, 521, 522, 524):
        return "server"
    return "other"


def err_reason(e):
    names = {"rate": "rate limited", "server": "server model error", "net": "connection dropped", "stall": "model stalled",
             "notfound": "model unavailable", "notools": "no tool-calling support", "ctx": "context too long",
             "empty": "empty response", "credits": "not a free model", "badreq": "history format rejected", "maxtok": "output limit rejected",
             "forbidden": "model access denied", "blocked": "blocked by the network"}
    base = names.get(e.kind, "error")
    return base + (" (HTTP %s)" % e.code if e.code else "")


def read_stream(resp, on_text, on_status, emitted, stall_secs, max_secs):
    parts, rparts, calls, finish, usage = [], [], {}, None, None
    t0 = last = time.time()
    done_seen = False
    for raw in resp:
        now = time.time()
        if now - t0 > max_secs:
            raise ApiError("response took too long (> %d s)" % max_secs, retryable=not emitted[0], kind="stall")
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            if now - last > stall_secs:
                raise ApiError("model silent for %d s with no output" % stall_secs, retryable=not emitted[0], kind="stall")
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            done_seen = True
            break
        try:
            ch = json.loads(data)
        except ValueError:
            continue
        if ch.get("error"):
            raise ApiError(extract_error(json.dumps(ch)), retryable=not emitted[0], kind="server")
        if ch.get("usage"):
            usage = ch["usage"]
        for choice in ch.get("choices") or []:
            d = choice.get("delta") or {}
            if choice.get("finish_reason"):
                finish = choice["finish_reason"]
            txt = d.get("content")
            if isinstance(txt, list):
                txt = "".join(p.get("text", "") for p in txt if isinstance(p, dict))
            rs = d.get("reasoning") or d.get("reasoning_content")
            if txt or rs or d.get("tool_calls"):
                last = now
            if rs:
                rparts.append(rs)
                if on_status:
                    on_status("thinking")
            if txt:
                parts.append(txt)
                emitted[0] = True
                on_text(txt)
            for tc in d.get("tool_calls") or []:
                idx = tc.get("index")
                if idx is None:
                    idx = 0 if not calls else (max(calls) + (1 if tc.get("id") else 0))
                slot = calls.setdefault(idx, {"id": None, "name": "", "args": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                nm = fn.get("name")
                if nm and (not slot["name"] or (nm != slot["name"] and not slot["name"].endswith(nm))):
                    slot["name"] += nm
                a = fn.get("arguments")
                if isinstance(a, dict):
                    a = json.dumps(a)
                if a:
                    slot["args"] += a
                emitted[0] = True
                if on_status and slot["name"]:
                    on_status("preparing " + slot["name"])
    if not done_seen and finish is None:
        raise ApiError("connection dropped mid-answer (stream did not finish)", retryable=not emitted[0], kind="net")
    if finish == "error":
        raise ApiError("the provider returned an error mid-stream", retryable=not emitted[0], kind="server")
    msg = {"role": "assistant", "content": "".join(parts) or None}
    tcs = []
    for i in sorted(calls):
        c = calls[i]
        if not c["name"]:
            continue
        tcs.append({"id": c["id"] or "call_%d_%d" % (int(time.time()), i), "type": "function",
                    "function": {"name": c["name"], "arguments": c["args"] or "{}"}})
    if tcs:
        msg["tool_calls"] = tcs
    return msg, finish, usage, "".join(rparts)


def stream_chat(ctx, model, messages, tools, on_text, on_status=None, retries=1, stream=True, on_reset=None,
                fast_rate=False, max_tokens=None):
    body = {"model": model, "messages": messages, "temperature": ctx.cfg.get("temperature", 0.2)}
    if max_tokens or ctx.cfg.get("max_tokens"):
        body["max_tokens"] = int(max_tokens or ctx.cfg["max_tokens"])
    if tools:
        body["tools"] = tools
    headers = {"Authorization": "Bearer " + key_of(ctx), "Content-Type": "application/json", "X-Title": "Axion Code",
               "User-Agent": UA, "HTTP-Referer": "https://github.com/alfar988/Axion-code"}
    stall = int(ctx.cfg.get("stall_secs", STALL_DEFAULT))
    maxs = int(ctx.cfg.get("max_request_secs", MAXREQ_DEFAULT))
    delays = [3, 8, 20, 35]
    net_try = srv_try = 0
    while True:
        use_stream = stream and net_try < 2
        body["stream"] = use_stream
        headers["Accept"] = "text/event-stream" if use_stream else "application/json"
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        emitted = [False]
        status_err = None
        try:
            conn, path = open_conn(API_BASE + "/chat/completions", 20, stall if use_stream else max(stall, 240))
            try:
                conn.request("POST", path, body=payload, headers=headers)
                resp = conn.getresponse()
                if resp.status >= 400:
                    status_err = (resp.status, resp.read().decode("utf-8", "replace"), resp.getheader("Retry-After"))
                    conn.close()
            except BaseException:
                conn.close()
                raise
        except NET_ERRORS as e:
            kind = "stall" if isinstance(e, (socket.timeout, TimeoutError)) else "net"
            if kind == "net" and net_try < 3:
                net_try += 1
                if not NETSTATE["ipv4_only"]:
                    NETSTATE["ipv4_only"] = True
                    ctx.cfg["ipv4_only"] = True
                if on_status:
                    on_status("connection dropped, retry %d/3%s" % (net_try, " (non-stream)" if net_try >= 2 else ""))
                time.sleep(min(2 * net_try, 6))
                continue
            raise ApiError("connection failed: %s" % getattr(e, "reason", e), kind=kind)
        if status_err:
            code, txt, retry_hdr = status_err
            try:
                retry_after = min(int(float(retry_hdr)), 120) if retry_hdr else None
            except (TypeError, ValueError):
                retry_after = None
            msg = extract_error(txt)
            low = (msg + txt).lower()
            kind = classify_http(code, low)
            if kind == "daily":
                raise ApiError("The daily free-model quota is used up. It resets at 00:00 UTC. Adding credit to your OpenRouter account raises the daily allowance, or switch to a paid model.", code=429, kind="daily")
            if kind in ("rate", "server") and srv_try < retries and not (kind == "rate" and fast_rate):
                wait = min(max(delays[min(srv_try, 3)], retry_after or 0), 60)
                if on_status:
                    on_status("server busy (%s), waiting %ds" % (code, wait))
                time.sleep(wait)
                srv_try += 1
                continue
            if code == 404 and tools and "tool" in low:
                raise NoToolsError(msg)
            if kind == "auth":
                raise ApiError("API key rejected (%s)." % code, code=code, kind="auth")
            raise ApiError("HTTP %s: %s" % (code, msg), code=code, kind=kind, retry_after=retry_after)
        bump_req(ctx)
        ctx.turn["reqs"] = ctx.turn.get("reqs", 0) + 1
        try:
            if use_stream:
                return read_stream(resp, on_text, on_status, emitted, stall, maxs)
            return read_json(resp, on_text)
        except ApiError as e:
            if e.kind == "net" and net_try < 3:
                net_try += 1
                NETSTATE["ipv4_only"] = True
                ctx.cfg["ipv4_only"] = True
                if emitted[0] and on_reset:
                    on_reset()
                if on_status:
                    on_status("connection dropped, retry %d/3%s" % (net_try, " (non-stream)" if net_try >= 2 else ""))
                time.sleep(min(2 * net_try, 6))
                continue
            if e.kind == "server" and e.retryable and srv_try < retries:
                srv_try += 1
                if on_status:
                    on_status("provider error, retry %d" % srv_try)
                time.sleep(delays[min(srv_try - 1, 3)])
                continue
            raise
        except NET_ERRORS as e:
            kind = "stall" if isinstance(e, (socket.timeout, TimeoutError)) else "net"
            if kind == "net" and net_try < 3:
                net_try += 1
                NETSTATE["ipv4_only"] = True
                ctx.cfg["ipv4_only"] = True
                if emitted[0] and on_reset:
                    on_reset()
                if on_status:
                    on_status("connection dropped, retry %d/3%s" % (net_try, " (non-stream)" if net_try >= 2 else ""))
                time.sleep(min(2 * net_try, 6))
                continue
            raise ApiError("stream interrupted: %s" % e, retryable=not emitted[0], kind=kind)
        finally:
            try:
                conn.close()
            except Exception:
                pass
