"""Model list, automatic fallback rotation, rate-limit cooldowns, output budget and context management."""

import json
import re
import time

from axion.client import stream_chat
from axion.config import (
    COOLDOWN_GONE, COOLDOWN_RATE, COOLDOWN_SERVER, DEFAULT_MODEL, MAX_OUT_DEFAULT, MAX_ROT_PER_TURN,
    MODELS_CACHE, ROUTER_MODEL,
)
from axion.memory import log_event, save_history
from axion.prompts import build_system
from axion.state import api_get, ApiError, NoToolsError, save_config
from axion.ui import acc, bold, clip, dim, err, ok, out, rl, short_model, Spinner, tw, warn


def note_model(ctx, model, kind):
    try:
        st = ctx.cfg.setdefault("model_stats", {}).setdefault(model, {"ok": 0, "fail": 0, "empty": 0, "badfmt": 0})
        st[kind] = st.get(kind, 0) + 1
    except Exception:
        pass


def model_rel(ctx, model):
    st = (ctx.cfg.get("model_stats") or {}).get(model) or {}
    return (min(st.get("ok", 0), 5) / 5.0 * 8 - 6 * min(st.get("fail", 0), 3)
            - 6 * min(st.get("empty", 0) + st.get("badfmt", 0), 3))


def ranked_models(ctx, models):
    return sorted(models, key=lambda m: model_score(m) + model_rel(ctx, m["id"]), reverse=True)


def model_score(m):
    mid = (m.get("id") or "").lower()
    s = min(m.get("context_length") or 0, 262144) / 262144.0 * 10
    sizes = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)b", mid)]
    if sizes:
        s += min(max(sizes), 500) / 500.0 * 30
    for kw, w in (("coder", 25), ("devstral", 18), ("qwen3", 12), ("deepseek", 14), ("glm", 12), ("kimi", 14),
                  ("gpt-oss", 12), ("minimax", 10), ("llama-3.3", 6), ("nemotron", 4), ("mistral", 3), ("hermes", 3)):
        if kw in mid:
            s += w
    for slow, w in (("ultra", 12), ("thinking", 6), ("reasoning", 6), ("-r1", 4), ("preview", 10), ("beta", 8),
                    ("exp", 6), ("alpha", 8)):
        if slow in mid:
            s -= w
    for small in ("-1b", "-2b", "-3b", "-4b", "-7b", "-8b", "-9b", "mini", "nano", "tiny", "lite", "small"):
        if small in mid:
            s -= 12
    return s


def fetch_models_all():
    st, data = api_get("/models", None, timeout=30)
    if st != 200 or not isinstance(data, dict):
        return None, {}
    by_id = {m["id"]: m for m in data.get("data", []) if m.get("id")}
    free = []
    for m in by_id.values():
        pr = m.get("pricing") or {}
        try:
            is_free = float(pr.get("prompt", 1)) == 0 and float(pr.get("completion", 1)) == 0
        except (TypeError, ValueError):
            is_free = False
        if not is_free or m.get("id") == ROUTER_MODEL:
            continue
        sp = m.get("supported_parameters")
        if sp is not None and "tools" not in sp:
            continue
        free.append(m)
    free.sort(key=model_score, reverse=True)
    return free, by_id


def ensure_models(ctx):
    if ctx.models_all is not None:
        return ctx.models_all
    try:
        c = json.loads(MODELS_CACHE.read_text(encoding="utf-8"))
        if time.time() - c.get("time", 0) < 6 * 3600 and c.get("free"):
            ctx.models_all = c["free"]
            ctx.models_by_id = {i: {"id": i, "context_length": n} for i, n in (c.get("ctx") or {}).items()}
            for m in ctx.models_all:
                ctx.models_by_id[m["id"]] = m
            return ctx.models_all
    except Exception:
        pass
    free, by_id = fetch_models_all()
    if free is not None:
        ctx.models_all, ctx.models_by_id = free, by_id
        try:
            slim = [{"id": m["id"], "name": m.get("name"), "context_length": m.get("context_length"),
                     "pricing": m.get("pricing"), "supported_parameters": m.get("supported_parameters")} for m in free]
            MODELS_CACHE.write_text(json.dumps({"time": time.time(), "free": slim,
                                                "ctx": {i: (m.get("context_length") or 0) for i, m in by_id.items()}}), encoding="utf-8")
        except Exception:
            pass
    return ctx.models_all


def model_ctx_len(ctx, model):
    if model == ROUTER_MODEL:
        return 200000
    m = ctx.models_by_id.get(model)
    if m and m.get("context_length"):
        return int(m["context_length"])
    return int(ctx.cfg.get("model_ctx", {}).get(model) or 32768)


def rotation_enabled(ctx):
    return bool(ctx.cfg.get("rotate", True))


def auto_rotation(ctx, n=10):
    free = ensure_models(ctx) or []
    st = ctx.cfg.get("model_stats") or {}
    ranked = [m for m in ranked_models(ctx, free)
              if not (st.get(m["id"], {}).get("fail", 0) >= 3 and st.get(m["id"], {}).get("ok", 0) == 0)]
    first, rest, seen = [], [], set()
    for m in ranked:
        v = m["id"].split("/")[0]
        (rest if v in seen else first).append(m["id"])
        seen.add(v)
    return (first + rest)[:n]


def candidate_models(ctx):
    lst = list(ctx.cfg.get("rotation") or []) or auto_rotation(ctx)
    if ROUTER_MODEL not in lst:
        lst.append(ROUTER_MODEL)
    return lst


def pick_next_model(ctx, tried, need_tokens=0):
    """Pick a fallback model: skip the ones resting after a rate limit, prefer reliable ones with enough context."""
    cur = ctx.cur_model()
    cands = [x for x in candidate_models(ctx) if x not in tried and x != cur]
    now = time.time()
    ready = [x for x in cands if ctx.cooldown.get(x, 0) <= now]
    fresh = [x for x in ready if now - ctx.fail_ts.get(x, 0) > 600]
    pool = sorted(fresh or ready, key=lambda x: -model_rel(ctx, x))
    if not pool and cands:
        pool = sorted(cands, key=lambda x: ctx.cooldown.get(x, 0))[:1]
    big = [x for x in pool if model_ctx_len(ctx, x) >= need_tokens * 1.2]
    return (big or pool or [None])[0]


def show_rotation(ctx, old, new, reason):
    out("  " + warn("⇄ ") + dim("%s → " % short_model(old)) + acc(short_model(new)) + dim("  " + clip(reason, max(10, tw() - 8 - len(short_model(old)) - len(short_model(new))))))
    if ctx.turn.get("rot", 0) <= 1:
        out("    " + dim("memory, plan and progress carried over"))


def rotate_now(ctx, reason, tried=None, need_tokens=0):
    cur = ctx.cur_model()
    ctx.fail_ts[cur] = time.time()
    if not rotation_enabled(ctx) or ctx.turn.get("rot", 0) >= MAX_ROT_PER_TURN:
        return None
    nxt = pick_next_model(ctx, set(tried or []) | {cur}, need_tokens)
    if not nxt:
        return None
    wait = ctx.cooldown.get(nxt, 0) - time.time()
    if wait > 1:
        wait_cooldown(wait)
    ctx.set_override(nxt)
    ctx.handoff = True
    ctx.rotations += 1
    ctx.turn["rot"] = ctx.turn.get("rot", 0) + 1
    log_event(ctx, "MODEL SWITCH: %s -> %s (%s)" % (cur, nxt, reason))
    save_history(ctx, "rotation")
    show_rotation(ctx, cur, nxt, reason)
    return nxt


def models_cmd(ctx, filt="", interactive=False):
    if filt == "refresh":
        try:
            MODELS_CACHE.unlink()
        except OSError:
            pass
        ctx.models_all = None
        filt = ""
    sp = Spinner("fetching the model list")
    sp.start()
    try:
        models = ensure_models(ctx)
    finally:
        sp.stop()
    if models is None:
        out("  " + err("✗ could not fetch the model list") + dim(" (check the connection: /net)"))
        return
    models = ranked_models(ctx, models)
    if filt:
        f = filt.lower()
        models = [m for m in models if f in m["id"].lower() or f in (m.get("name") or "").lower()]
    if not models:
        out("  " + dim("no suitable free models found"))
        return
    top = models[:12]
    ctx.model_list = top
    out()
    out("  " + bold("Free models with tool calling") + dim("  (order = estimated quality + session experience)"))
    cur = ctx.cfg.get("model")
    st = ctx.cfg.get("model_stats") or {}
    for i, m in enumerate(top, 1):
        cl = (m.get("context_length") or 0) // 1000
        s = st.get(m["id"], {})
        if m["id"] == cur:
            mark = ok("●")
        elif s.get("ok", 0) > s.get("fail", 0):
            mark = ok("✓")
        elif s.get("fail", 0) + s.get("empty", 0) + s.get("badfmt", 0) >= 2:
            mark = err("✗")
        else:
            mark = " "
        out("  %s %s %s %s" % (mark, acc("%2d" % i), clip(m["id"], tw() - 16), dim("%dk" % cl)))
    if interactive:
        out()
        out("  " + dim("The random router (openrouter/free) switches models on every request, so quality is inconsistent."))
        try:
            ans = input(rl("  " + acc("▍") + " " + dim("choose a number (Enter = 1, r = random router) › "))).strip().lower()
        except EOFError:
            ans = "r"
        if ans in ("", "1") or ans.isdigit():
            idx = int(ans or "1")
            if 1 <= idx <= len(top):
                ctx.cfg["model"] = top[idx - 1]["id"]
                ctx.cfg["model_chosen"] = True
                save_config(ctx.cfg)
                out("  " + ok("✓ model: ") + ctx.cfg["model"])
                return
        ctx.cfg["model_chosen"] = True
        save_config(ctx.cfg)
        out("  " + dim("keeping ") + ctx.cfg.get("model", DEFAULT_MODEL))
    else:
        out()
        out("  " + dim("choose: /model <number> · random router: /model openrouter/free · fallbacks: /rotate · refresh: /models refresh"))


def est_tokens(msgs):
    return int(sum(len(json.dumps(m, ensure_ascii=False)) for m in msgs) / 3.0)


def local_compact(ctx, keep_last=8):
    """Trim old content without calling the model (code in tool calls already exists in files)."""
    msgs = ctx.messages
    target = msgs[:-keep_last] if keep_last else list(msgs)
    saved = 0
    for m in target:
        role = m.get("role")
        if role == "tool":
            c = m.get("content") or ""
            if len(c) > 700:
                m["content"] = c[:450] + "\n…[trimmed %d characters to save context]" % (len(c) - 450)
                saved += len(c) - len(m["content"])
        elif role == "assistant":
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                args = fn.get("arguments") or ""
                if len(args) > 1500:
                    try:
                        d = json.loads(args)
                    except ValueError:
                        continue
                    if isinstance(d, dict):
                        for k, v in list(d.items()):
                            if isinstance(v, str) and len(v) > 600:
                                d[k] = "[%d characters; already written to the file]" % len(v)
                        new = json.dumps(d, ensure_ascii=False)
                        saved += max(0, len(args) - len(new))
                        fn["arguments"] = new
            c = m.get("content")
            if isinstance(c, str) and len(c) > 3500:
                m["content"] = c[:2000] + "\n…[trimmed]"
                saved += len(c) - len(m["content"])
    return saved


def hist_chars(msgs):
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in msgs)


def compact_history(ctx, auto=False):
    local_compact(ctx)
    msgs = ctx.messages
    idx = len(msgs) - 6
    while idx > 0 and msgs[idx].get("role") != "user":
        idx -= 1
    if idx <= 0:
        if not auto:
            out("  " + dim("the conversation is still short; no need to compact it."))
        return
    old, keep = msgs[:idx], msgs[idx:]
    lines = []
    for m in old:
        c = m.get("content") or ""
        if m.get("tool_calls"):
            c += " [tool: %s]" % ", ".join(t["function"]["name"] for t in m["tool_calls"])
        lines.append("%s: %s" % (m["role"], str(c)[:1200]))
    sp = Spinner("summarizing")
    sp.start()
    buf = []
    summary = ""
    try:
        msg, _, _, _ = stream_chat(ctx, ctx.cur_model(), [
            {"role": "system", "content": "Summarize the following coding conversation densely: the user's goal, decisions, files created or changed, current status, and what is unfinished. At most 300 words. Use the same language as the conversation."},
            {"role": "user", "content": "\n".join(lines)[:60000]}], None, buf.append, None, 1)
        summary = (msg.get("content") or "".join(buf)).strip()
    except (ApiError, NoToolsError):
        summary = ""
    finally:
        sp.stop()
    if not summary:
        summary = "(automatic summary failed; see history/handoff.md and history/transcript.md for the full context)"
    ctx.messages = [{"role": "user", "content": "[Summary of the earlier conversation]\n" + summary},
                    {"role": "assistant", "content": "Understood. I will continue from that summary."}] + keep
    log_event(ctx, "history compacted (%d old messages). Summary: %s" % (len(old), summary[:600]))
    ctx.hist_count = len(ctx.messages)
    out("  " + ok("✓ history compacted") + dim(" (%d → %d messages)" % (len(old) + len(keep), len(ctx.messages))))


def cur_est(ctx, phase):
    return est_tokens([{"role": "system", "content": build_system(ctx, phase)}] + ctx.messages)


def guard_context(ctx, phase):
    limit = model_ctx_len(ctx, ctx.cur_model())
    est = cur_est(ctx, phase)
    if est < limit * 0.8:
        return
    out("  " + warn("↻ ") + dim("context ~%dk of %dk tokens, tidying history…" % (est // 1000, limit // 1000)))
    local_compact(ctx)
    est = cur_est(ctx, phase)
    if est >= limit * 0.8:
        compact_history(ctx, auto=True)
        est = cur_est(ctx, phase)
    if est >= limit * 0.9:
        if not rotate_now(ctx, "context full (~%dk tokens)" % (est // 1000), None, est):
            out("  " + warn("! the context is very long. Use /compact or /clear."))


def mark_cooldown(ctx, model, e):
    """Let a model that just failed rest, so rotation does not come straight back to it."""
    k = e.kind
    if k == "rate":
        secs = e.retry_after or COOLDOWN_RATE
    elif k in ("server", "stall", "empty"):
        secs = COOLDOWN_SERVER
    elif k in ("notfound", "notools", "credits"):
        secs = COOLDOWN_GONE
    elif k == "forbidden":
        secs = 1800
    elif k == "blocked":
        secs = 60
    else:
        return
    ctx.cooldown[model] = max(ctx.cooldown.get(model, 0), time.time() + min(secs, 3600))


def wait_cooldown(secs):
    secs = int(min(max(secs, 1), 45))
    out("  " + dim("every fallback model is rate limited; waiting %d s…" % secs))
    for _ in range(secs):
        time.sleep(1)


def out_budget(ctx, model, msgs):
    """Largest output budget the context allows. Lowered automatically if a provider rejects it."""
    cap_ = ctx.max_out.get(model)
    if cap_:
        return cap_
    if ctx.cfg.get("max_tokens"):
        return int(ctx.cfg["max_tokens"])
    room = model_ctx_len(ctx, model) - est_tokens(msgs) - 1024
    return int(max(2048, min(MAX_OUT_DEFAULT, room)))
