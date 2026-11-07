"""/checklimit: how much of the AI allowance is left on the active provider."""

import json
import re
import textwrap
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from lumo import providers
from lumo.client import build_request
from lumo.state import api_get, bump_req, key_of, mask_key, req_today, req_today_for, save_config
from lumo.ui import dim, err, out, panel, Spinner, tw
from lumo.ui import C_DIM, C_ERR, C_WARN

FREE_DAILY_UNPAID, FREE_DAILY_PAID = 50, 1000        # OpenRouter free-model requests per day


def bar_text(frac, width=12):
    frac = 0.0 if frac is None else max(0.0, min(1.0, frac))
    n = int(round(width * frac))
    return "▰" * n + "▱" * (width - n)


def reset_in_utc():
    now = datetime.now(timezone.utc)
    left = 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
    return "%dh %02dm" % (left // 3600, (left % 3600) // 60)


def reset_text(v):
    """Rate-limit reset values are durations ('6s', '1m30s') or RFC 3339 timestamps."""
    if not v:
        return ""
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        secs = int((t - datetime.now(timezone.utc)).total_seconds())
        return "in %ds" % secs if 0 <= secs < 120 else ("in %dm" % (secs // 60) if secs >= 120 else "now")
    except ValueError:
        return "in " + str(v)


def money(v):
    try:
        return "$%.2f" % float(v)
    except (TypeError, ValueError):
        return "-"


def probe(ctx):
    """One tiny request (a single output token) to read the provider's rate-limit headers right now."""
    prov = providers.active(ctx.cfg)
    _prov, url, body, headers = build_request(ctx, ctx.cur_model(), [{"role": "user", "content": "hi"}], None, 1, False)
    headers["Accept"] = "application/json"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    seen, status, message = {}, None, ""
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            status = r.status
            seen = providers.pick_limit_headers(r.getheaders())
            r.read()
    except urllib.error.HTTPError as e:
        status = e.code
        seen = providers.pick_limit_headers(e.headers.items())
        try:
            message = str((json.loads(e.read().decode("utf-8", "replace")).get("error") or {}).get("message") or "")[:160]
        except Exception:
            message = ""
    except Exception as e:
        message = str(e)[:160]
    bump_req(ctx)
    if seen:
        ctx.rate_info[prov["id"]] = {"time": time.time(), "headers": seen}
    return status, message


def openrouter_rows(ctx, rows):
    st, data = api_get("/key", key_of(ctx))
    info = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else (data if isinstance(data, dict) else {})
    if st != 200:
        rows.append(("The key check failed (HTTP %s). Try /key to enter it again, or /net to test the connection." % st, C_ERR))
        return
    free_tier = info.get("is_free_tier")
    rows.append(("account     " + ("free tier (no credits bought)" if free_tier else "paid account" if free_tier is False else "unknown tier"), None))
    cap = ctx.cfg.get("free_daily") or (FREE_DAILY_UNPAID if free_tier is not False else FREE_DAILY_PAID)
    left = max(0, cap - req_today(ctx))
    rows.append(("free calls  %s  %d of %d left today" % (bar_text(left / float(cap)), left, cap), C_WARN if left <= cap * 0.15 else None))
    rows.append(("            counted on this device", C_DIM))
    rows.append(("            resets in %s (00:00 UTC)" % reset_in_utc(), C_DIM))
    limit, remaining = info.get("limit"), info.get("limit_remaining")
    if limit is not None and remaining is not None:
        try:
            frac = float(remaining) / float(limit) if float(limit) else 0.0
        except (TypeError, ValueError):
            frac = 0.0
        rows.append(("credit      %s  %s of %s left" % (bar_text(frac), money(remaining), money(limit)), C_WARN if frac < 0.15 else None))
    elif info.get("usage") is not None:
        rows.append(("credit      no limit set · spent %s" % money(info.get("usage")), None))
    names = {"usage_daily": "day", "usage_weekly": "week", "usage_monthly": "month"}
    spent = [(n, info.get(k)) for k, n in names.items() if info.get(k) is not None]
    if spent:
        rows.append(("spent       " + " · ".join("%s %s" % (n, money(v)) for n, v in spent), None))
    rl = info.get("rate_limit")
    if isinstance(rl, dict) and rl.get("requests"):
        rows.append(("rate limit  %s requests per %s" % (rl.get("requests"), rl.get("interval") or "interval"), None))
    rows.append(("note        free models: about 20 requests per minute", C_DIM))
    rows.append(("            more credit raises the daily allowance", C_DIM))


def header_rows(ctx, prov, rows, note=""):
    info = ctx.rate_info.get(prov["id"])
    metrics = providers.summarize_limits(info["headers"]) if info else {}
    if not metrics:
        rows.append(("No rate-limit data from %s yet. Send a message, or run /checklimit probe (one tiny request)." % prov["name"], C_WARN))
        return
    age = time.time() - info["time"]
    rows.append(("as of %s ago" % ("%ds" % age if age < 120 else "%dm" % (age // 60)), C_DIM))
    for name, m in list(metrics.items())[:5]:
        limit, rem = m.get("limit"), m.get("remaining")
        if limit and rem is not None:
            frac = float(rem) / float(limit)
            rows.append(("%-11s %s  %s of %s left" % (name, bar_text(frac), rem, limit), C_WARN if frac < 0.15 else None))
        elif rem is not None:
            rows.append(("%-11s %s left" % (name, rem), None))
        else:
            continue
        if m.get("reset"):
            rows.append(("            resets " + reset_text(m.get("reset")), C_DIM))
    if "retry-after" in info["headers"]:
        rows.append(("retry after %ss" % info["headers"]["retry-after"], C_ERR))
    if note:
        rows.append((note, C_DIM))


def wrap_rows(rows):
    """Wrap long rows ourselves so continuation lines hang under the value instead of the label."""
    inner = min(tw(), 62) - 6
    res = []
    for text, c in rows:
        if len(text) <= inner or not text.strip():
            res.append((text, c))
            continue
        hang = " " * 12 if (text.startswith(" " * 12) or re.match(r"^[a-z ]{3,11}\s{2,}\S", text)) else ""
        for line in textwrap.wrap(text, inner, subsequent_indent=hang, drop_whitespace=True) or [text]:
            res.append((line, c))
    return res


def cmd_checklimit(ctx, arg):
    prov = providers.active(ctx.cfg)
    out()
    if providers.needs_key(prov) and not key_of(ctx):
        out("  " + err("✗ no API key for %s. " % prov["name"]) + dim("Set one with /key"))
        return
    status, message = None, ""
    if arg and arg[0].lower() in ("probe", "now", "test") and prov["id"] != "openrouter":
        sp = Spinner("reading the limits (one tiny request)")
        sp.start()
        try:
            status, message = probe(ctx)
        finally:
            sp.stop()
    rows = [("provider    " + prov["name"], None), ("model       " + ctx.cur_model(), None)]
    if providers.needs_key(prov):
        rows.append(("key         " + mask_key(key_of(ctx)), None))
    rows.append(("", None))
    if prov["id"] == "openrouter":
        sp = Spinner("checking the key")
        sp.start()
        try:
            openrouter_rows(ctx, rows)
        finally:
            sp.stop()
    else:
        if status is not None and status >= 400:
            rows.append(("The probe returned HTTP %s%s" % (status, (": " + message) if message else ""), C_ERR if status != 429 else C_WARN))
        elif status is None and message:
            rows.append(("The probe failed: " + message, C_ERR))
        header_rows(ctx, prov, rows)
        rows.append(("", None))
        rows.append(("requests today on this device: %d (all providers %d)" % (req_today_for(ctx, prov["id"]), req_today(ctx)), None))
        if prov.get("console"):
            rows.append(("Balance and usage: " + prov["console"], C_DIM))
        elif prov.get("local"):
            rows.append(("A local server has no usage limits.", C_DIM))
    for line in panel("Limits · " + prov["name"], wrap_rows(rows)):
        out(line)
    u = ctx.usage
    out("  " + dim("this session: %d requests · %dk tokens in · %dk tokens out" % (ctx.session_reqs, u["prompt"] // 1000, u["completion"] // 1000)))
