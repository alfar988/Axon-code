"""Model list, automatic fallback rotation, rate-limit cooldowns, output budget and context management."""

import json
import math
import re
import threading
import time
from datetime import datetime, timezone

from lumo import providers, safelimit
from lumo.client import stream_chat
from lumo.config import (
    COOLDOWN_GONE, COOLDOWN_RATE, COOLDOWN_SERVER, DEFAULT_MODEL, MAX_OUT_DEFAULT, MAX_ROT_PER_TURN,
    MODELS_CACHE, MODELS_POLL, MODELS_TTL, ROUTER_MODEL,
)
from lumo.memory import log_event, save_history
from lumo.prompts import build_system
from lumo.state import api_get, ApiError, key_of, NoToolsError, save_config
from lumo.ui import acc, bold, clip, dim, err, ok, out, rl, rule, short_model, Spinner, tw, warn


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


# --- ranking: "smartest first" ------------------------------------------------------------------------------------
# Base points per model family (first match wins, so specific patterns come first). The numbers are a judgement, not a
# benchmark; the signals that update by themselves (size in the name, context length, release date, price) refine them.
TIERS = (
    (r"claude[-.]?(?:opus|\d+(?:[.-]\d+)?[-.]opus)", 64), (r"claude[-.]?(?:sonnet|\d+(?:[.-]\d+)?[-.]sonnet)", 56),
    (r"claude[-.]?(?:haiku|\d+(?:[.-]\d+)?[-.]haiku)", 34),
    (r"gpt-5.*nano", 30), (r"gpt-5.*mini", 48), (r"gpt-5", 66), (r"(?:^|[/-])o3(?:$|[-:])", 62), (r"o4-mini", 50), (r"(?:^|[/-])o1(?:$|[-:])", 54),
    (r"gpt-4\.1.*nano", 28), (r"gpt-4\.1.*mini", 40), (r"gpt-4\.1", 54), (r"gpt-4o.*mini", 34), (r"gpt-4o", 48),
    (r"gpt-oss-120b", 46), (r"gpt-oss-20b", 32), (r"gpt-4", 40), (r"gpt-3\.5", 14),
    (r"gemini.*flash-lite", 34), (r"gemini.*pro", 60), (r"gemini.*flash", 46), (r"gemini", 40),
    (r"grok-4.*fast", 52), (r"grok-4", 62), (r"grok-code", 48), (r"grok-3.*mini", 42), (r"grok-3", 52), (r"grok-2", 36), (r"grok", 34),
    (r"deepseek.*(?:r1|reasoner)", 54), (r"deepseek", 50), (r"kimi", 52), (r"glm-(?:4\.[5-9]|[5-9])", 50), (r"glm", 40), (r"minimax", 46),
    (r"qwen-?3.*coder", 52), (r"qwen3-max|qwen3-235b|qwen-max", 52), (r"qwen-?3", 44), (r"qwq", 44), (r"qwen", 38),
    (r"llama-?4", 46), (r"llama-?3\.[1-3]", 38), (r"llama", 30),
    (r"mistral-large|magistral", 46), (r"devstral|codestral", 42), (r"mistral-medium", 40), (r"mistral-small|ministral", 30), (r"mistral|mixtral", 28),
    (r"nemotron", 36), (r"hermes", 30), (r"gemma", 26), (r"phi-?\d", 22),
)
GENERATIONS = (
    (r"claude-(?:opus|sonnet|haiku)-(\d+)(?:[-.](\d)(?!\d))?", 2.0), (r"claude-(\d+)(?:[-.](\d))?-(?:opus|sonnet|haiku)", 2.0),
    (r"gpt-(\d+(?:\.\d)?)", 1.5), (r"gemini-(\d+(?:\.\d)?)", 3.0), (r"grok-(\d+)", 2.0), (r"llama-?(\d+(?:\.\d)?)", 1.5),
    (r"qwen-?(\d+(?:\.\d)?)", 1.5), (r"deepseek-v(\d+(?:\.\d)?)", 2.0), (r"glm-(\d+(?:\.\d)?)", 2.0), (r"kimi-k(\d+)", 2.0),
)
NON_CHAT = re.compile(r"embed|whisper|tts|transcri|dall-e|image|imagen|veo|sora|moderation|realtime|audio|speech|rerank|guard|davinci|babbage|"
                      r"search-preview|computer-use|codex|live|aqa|learnlm|vision-preview|ocr|diffusion|flux|stable-", re.I)


def clean_id(mid):
    return re.sub(r":free$", "", str(mid or "").lower().replace("models/", ""))


def parse_created(v):
    if isinstance(v, (int, float)) and v > 0:
        return float(v)
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def model_score(m, now=None):
    """Estimated capability: family tier + generation + size + context + recency + price, minus 'preview' style penalties."""
    mid = clean_id(m.get("id"))
    s, matched = 20.0, False
    for rx, pts in TIERS:
        if re.search(rx, mid):
            s, matched = float(pts), True
            break
    for rx, w in GENERATIONS:
        g = re.search(rx, mid)
        if g:
            ver = float(g.group(1)) + (float(g.group(2)) / 10 if g.lastindex and g.lastindex >= 2 and g.group(2) else 0.0)
            s += min(w * ver, 12.0)
            break
    sizes = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)b(?![a-z])", mid)]
    if sizes:
        size = max(sizes)
        s += min(size, 700.0) / 700.0 * (14 if matched else 30)
        if matched:
            s += max(-18.0, min(4.0, math.log2(size / 30.0) * 6))      # inside a family, a small model ranks below a big one
        elif size < 10:
            s -= 10
    cl = int(m.get("context_length") or 0)
    if cl > 0:
        s += (math.log10(min(max(cl, 8000), 1000000)) - math.log10(8000)) / (math.log10(1000000) - math.log10(8000)) * 8
    created = parse_created(m.get("created"))
    if created:
        age_months = max(0.0, ((now or time.time()) - created) / (30.4 * 86400))
        s += max(0.0, 14 - age_months) / 14 * 8
    if "coder" in mid or "code" in mid:
        s += 5
    for slow in ("preview", "beta", "exp", "alpha"):
        if re.search(r"(?:^|[-_/])%s(?:$|[-_.:\d])" % slow, mid):
            s -= 6
    if not matched:
        for small in ("nano", "tiny", "lite", "small", "mini"):
            if small in mid:
                s -= 8
    try:
        price = float((m.get("pricing") or {}).get("prompt") or 0) * 1e6
    except (TypeError, ValueError):
        price = 0.0
    if price > 0:
        s += min(math.log10(price + 1) * 3, 6)
    return s


def ranked_models(ctx, models):
    return sorted(models, key=lambda m: model_score(m) + model_rel(ctx, m["id"]), reverse=True)


# --- fetching and caching the model list (refreshed every 12 hours) ---------------------------------------------------
CTX_GUESS = ((r"claude", 200000), (r"gpt-5", 200000), (r"gpt-4\.1", 200000), (r"gemini", 200000), (r"grok-4", 200000),
             (r"o\d", 128000), (r"gpt-4", 128000), (r"deepseek", 64000), (r"llama-?3", 128000), (r"qwen", 128000), (r"mistral", 32000))


def guess_context(mid):
    for rx, n in CTX_GUESS:
        if re.search(rx, mid.lower()):
            return n
    return 32768


def normalize_models(prov, data):
    items = data.get("data") if isinstance(data, dict) else data
    if isinstance(data, dict) and not items:
        items = data.get("models")
    res = []
    for m in items or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "").replace("models/", "", 1)
        if not mid or NON_CHAT.search(mid):
            continue
        if prov["id"] == "openai" and re.search(r"-pro(?:$|-)", mid):
            continue                                   # responses-only models
        caps = m.get("capabilities")
        if isinstance(caps, dict) and caps.get("completion_chat") is False:
            continue
        if m.get("type") and str(m["type"]).lower() not in ("chat", "language", "code", "model"):
            continue
        if m.get("active") is False:
            continue
        cl = m.get("context_length") or m.get("context_window") or m.get("max_context_length") or m.get("max_model_len") \
            or (m.get("top_provider") or {}).get("context_length") or 0
        res.append({"id": mid, "name": m.get("name") or m.get("display_name") or mid, "context_length": int(cl or 0) or min(guess_context(mid), 200000),
                    "pricing": m.get("pricing"), "supported_parameters": m.get("supported_parameters"),
                    "created": parse_created(m.get("created") or m.get("created_at"))})
    return res


def default_view(prov, full):
    """OpenRouter: free models that can call tools (never paid ones by surprise). Other providers: every chat model."""
    if prov["id"] != "openrouter":
        return list(full)
    view = []
    for m in full:
        pr = m.get("pricing") or {}
        try:
            is_free = float(pr.get("prompt", 1)) == 0 and float(pr.get("completion", 1)) == 0
        except (TypeError, ValueError):
            is_free = False
        sp = m.get("supported_parameters")
        if is_free and m["id"] != ROUTER_MODEL and not (sp is not None and "tools" not in sp):
            view.append(m)
    return view


def fetch_models_full(ctx=None, timeout=30):
    prov = providers.active(ctx.cfg if ctx else None)
    key = key_of(ctx) if (ctx is not None and prov["id"] != "openrouter") else None
    path = "/models?limit=1000" if prov["style"] == "anthropic" else "/models"
    st, data = api_get(path, key, timeout=timeout, provider=prov)
    if st != 200 or not isinstance(data, (dict, list)):
        return None
    full = normalize_models(prov, data)
    return full or None


def fetch_models_all(ctx=None):
    """Kept for callers that want (view, by_id): the default view of the active provider and every model by id."""
    prov = providers.active(ctx.cfg if ctx else None)
    full = fetch_models_full(ctx)
    if full is None:
        return None, {}
    view = default_view(prov, full)
    view.sort(key=model_score, reverse=True)
    return view, {m["id"]: m for m in full}


def read_cache(pid, ignore_ttl=False):
    try:
        c = json.loads(MODELS_CACHE.read_text(encoding="utf-8"))
        if c.get("provider") == pid and c.get("models") and (ignore_ttl or time.time() - c.get("time", 0) < MODELS_TTL):
            return c
    except Exception:
        pass
    return None


def apply_models(ctx, prov, full, stamp):
    view = default_view(prov, full)
    view.sort(key=model_score, reverse=True)
    ctx.models_full = list(full)
    ctx.models_by_id = {m["id"]: m for m in full}
    ctx.models_all = view
    ctx.models_time, ctx.models_provider = stamp, prov["id"]


def ensure_models(ctx, force=False, timeout=30):
    """The model list of the active provider. Memory first, then the disk cache, then the network; valid for 12 hours."""
    prov = providers.active(ctx.cfg)
    fresh = ctx.models_all is not None and ctx.models_provider == prov["id"] and time.time() - ctx.models_time < MODELS_TTL
    if fresh and not force:
        return ctx.models_all
    if not force:
        c = read_cache(prov["id"])
        if c:
            apply_models(ctx, prov, c["models"], c["time"])
            return ctx.models_all
    full = fetch_models_full(ctx, timeout)
    if full is None:                                   # offline: an old list beats no list
        if ctx.models_all is not None and ctx.models_provider == prov["id"]:
            return ctx.models_all
        c = read_cache(prov["id"], ignore_ttl=True)
        if c:
            apply_models(ctx, prov, c["models"], c["time"])
            return ctx.models_all
        return None
    now = time.time()
    apply_models(ctx, prov, full, now)
    try:
        MODELS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        MODELS_CACHE.write_text(json.dumps({"provider": prov["id"], "time": now, "models": full}), encoding="utf-8")
    except Exception:
        pass
    return ctx.models_all


def refresh_due(ctx):
    return ctx.models_provider != providers.active(ctx.cfg)["id"] or time.time() - ctx.models_time >= MODELS_TTL


def start_refresher(ctx):
    """Load the list now and fetch it again whenever it is older than 12 hours, for as long as the program runs."""
    def loop():
        try:
            ensure_models(ctx)
        except Exception:
            pass
        while True:
            time.sleep(MODELS_POLL)
            try:
                if refresh_due(ctx):
                    ensure_models(ctx, force=True)
            except Exception:
                pass
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def auto_pick_model(ctx):
    """A provider without a chosen model starts with the best-ranked one (the user can change it with /model)."""
    if ctx.cfg.get("model") and ctx.cfg.get("model_chosen"):
        return ctx.cfg["model"]
    prov = providers.active(ctx.cfg)
    if prov["id"] == "openrouter" and ctx.cfg.get("model"):
        return ctx.cfg["model"]
    models = ensure_models(ctx)
    if not models:
        return ctx.cfg.get("model") or ""
    best = ranked_models(ctx, models)[0]["id"]
    ctx.cfg["model"], ctx.cfg["model_chosen"] = best, True
    ctx.cfg.setdefault("models_by_provider", {})[prov["id"]] = best
    save_config(ctx.cfg)
    return best


def model_ctx_len(ctx, model):
    if model == ROUTER_MODEL:
        return 200000
    m = ctx.models_by_id.get(model)
    if m and m.get("context_length"):
        return int(m["context_length"])
    return int(ctx.cfg.get("model_ctx", {}).get(model) or 32768)


def rotation_enabled(ctx):
    """Fallback models are on by default for OpenRouter's free models; paid providers only switch when asked to."""
    return bool(ctx.cfg.get("rotate", providers.active(ctx.cfg)["id"] == "openrouter"))


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
    if ROUTER_MODEL not in lst and providers.active(ctx.cfg)["id"] == "openrouter":
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


def age_text(secs):
    secs = int(max(0, secs))
    if secs < 90:
        return "just now"
    if secs < 3600:
        return "%d min ago" % (secs // 60)
    return "%dh %02dm ago" % (secs // 3600, (secs % 3600) // 60)


def price_text(m):
    pr = m.get("pricing") or {}
    try:
        p, c = float(pr.get("prompt")), float(pr.get("completion") or 0)
    except (TypeError, ValueError):
        return ""
    return "free" if p == 0 and c == 0 else "$%s/M" % ("%.2f" % (p * 1e6)).rstrip("0").rstrip(".")


def choose_model(ctx, mid):
    ctx.cfg["model"] = mid
    ctx.cfg["model_chosen"] = True
    ctx.cfg.setdefault("models_by_provider", {})[providers.active(ctx.cfg)["id"]] = mid
    save_config(ctx.cfg)


def models_cmd(ctx, filt="", interactive=False):
    prov = providers.active(ctx.cfg)
    force = filt == "refresh"
    show_all = filt == "all"
    if force or show_all:
        filt = ""
    sp = Spinner("fetching the model list")
    sp.start()
    try:
        models = ensure_models(ctx, force=force)
    finally:
        sp.stop()
    if models is None:
        out("  " + err("✗ could not fetch the model list") + dim(" (check the key and the connection: /net, /checklimit)"))
        return
    if show_all and ctx.models_full:
        models = ctx.models_full
    models = ranked_models(ctx, models)
    if filt:
        f = filt.lower()
        models = [m for m in models if f in m["id"].lower() or f in (m.get("name") or "").lower()]
    if not models:
        out("  " + dim("no matching models found"))
        return
    top = models[:(40 if show_all else 15)]
    ctx.model_list = top
    out()
    out(rule("Models · %s · best first" % prov["name"]))
    cur = ctx.cfg.get("model")
    st = ctx.cfg.get("model_stats") or {}
    idw = max(14, min(44, tw() - 27))
    for i, m in enumerate(top, 1):
        s = st.get(m["id"], {})
        if m["id"] == cur:
            mark = ok("●")
        elif s.get("ok", 0) > s.get("fail", 0):
            mark = ok("✓")
        elif s.get("fail", 0) + s.get("empty", 0) + s.get("badfmt", 0) >= 2:
            mark = err("✗")
        else:
            mark = " "
        cl = (m.get("context_length") or 0) // 1000
        out("  %s %s %s %s %s" % (mark, acc("%2d" % i), clip(m["id"], idw).ljust(idw), dim(("%dk" % cl).rjust(5)), dim(price_text(m))))
    if len(models) > len(top):
        out("  " + dim("… %d more: /models all, or filter with /models <text>" % (len(models) - len(top))))
    out("  " + dim("updated %s · refreshes every 12 hours · order = estimated capability + your session results" % age_text(time.time() - ctx.models_time)))
    if interactive:
        out()
        if prov["id"] == "openrouter":
            out("  " + dim("The random router (openrouter/free) switches models on every request, so quality is inconsistent."))
        hint = "choose a number (Enter = 1" + (", r = random router) › " if prov["id"] == "openrouter" else ") › ")
        try:
            ans = input(rl("  " + acc("▍") + " " + dim(hint))).strip().lower()
        except EOFError:
            ans = "r" if prov["id"] == "openrouter" else "1"
        if ans in ("", "1") or ans.isdigit():
            idx = int(ans or "1")
            if 1 <= idx <= len(top):
                choose_model(ctx, top[idx - 1]["id"])
                out("  " + ok("✓ model: ") + ctx.cfg["model"])
                return
        ctx.cfg["model_chosen"] = True
        save_config(ctx.cfg)
        out("  " + dim("keeping ") + (ctx.cfg.get("model") or DEFAULT_MODEL))
    else:
        out("  " + dim("choose: /model <number> · fallbacks: /rotate · refresh now: /models refresh"))


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
    if safelimit.active() and est >= safelimit.get("context_tokens", 0):
        local_compact(ctx, keep_last=safelimit.get("keep_last", 8))
        est = cur_est(ctx, phase)
        if safelimit.maximum():
            from lumo.compact import compact_archive, COMPACT_KEEP
            if est >= safelimit.get("context_tokens", 0) and len(ctx.messages) > COMPACT_KEEP + 6:
                compact_archive(ctx, quiet=True)               # moves the old part to history/archive/, no model request
                est = cur_est(ctx, phase)
        elif est >= safelimit.get("context_tokens", 0) * 1.4 and len(ctx.messages) > 12:
            compact_history(ctx, auto=True)
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
    return int(max(2048, min(MAX_OUT_DEFAULT, room, safelimit.get("out_tokens", MAX_OUT_DEFAULT))))
