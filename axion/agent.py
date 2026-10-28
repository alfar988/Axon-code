"""The agent: intent detection, planning phase, model-tool loop, self-correction."""

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from axion.client import err_reason, stream_chat
from axion.config import (
    CHAT_TOOLS, MAX_ROT_PER_TURN, MAX_STEPS, PLAN_MAX_STEPS, PLAN_TOOLS, SNAP_IGNORE, WEB_TOOLS,
)
from axion.diagnose import first_error_line, is_failure
from axion.memory import hist_dir, log_event, save_history
from axion.models import (
    candidate_models, est_tokens, guard_context, local_compact, mark_cooldown, note_model,
    out_budget, rotate_now, rotation_enabled,
)
from axion.prompts import build_system
from axion.security import inside
from axion.skills import activate_skill, pick_skills
from axion.state import (
    ApiError, ensure_key, is_free_model, key_of, NoToolsError, req_today, save_config, validate_key,
)
from axion.templates import template_nudge
from axion.toolcalls import (
    bad_call_message, chunk_lines, fix_args, normalize_tool_name, parse_text_tool_calls,
    repair_tool_args, sanitize_messages, shrink_chunk, slim_schemas, strip_think, TextGate,
)
from axion.toolrun import exec_tool, show_result, tool_header
from axion.tools.registry import TOOLS
from axion.ui import (
    acc, C_ACC, C_DIM, C_ERR, C_OK, C_VIO, C_WARN, clip, dim, err, faint, MdStream, ok, out, paint,
    rl, rule, short_path, Spinner, tw, warn,
)
from axion.util import cap, human_size, rel
from axion.verify import changed_files, file_sig, ui_polish_findings, verify_paths


BUILD_VERBS = r"(buat(?:kan|in)?|bikin(?:in|kan)?|create|build|generate|develop|rancang|bangun|kembangkan|coding(?:kan)?|programkan|make)"


BUILD_NOUNS = (r"(game|gim|website|web\b|situs|landing|portofolio|portfolio|aplikasi|\bapp\b|bot\b|dashboard|tool|alat|program|"
               r"script|skrip|\bapi\b|server|plugin|extension|ekstensi|simulasi|simulator|shooter|rpg|platformer|puzzle|racing|"
               r"fps|\b3d\b|\b2d\b|template|toko|blog|kalkulator|chat|crud|scraper|mod\b)")


PLAN_NOUNS = (r"(game|gim|website|web\b|situs|landing|portofolio|portfolio|aplikasi|\bapp\b|bot\b|dashboard|simulasi|simulator|"
              r"shooter|rpg|platformer|puzzle|racing|fps|toko|blog|chat|crud|scraper|server|plugin|ekstensi|extension)")


ACTION_VERBS = (r"(hapus|delete|rename|ganti nama|pindah|salin|copy|ekstrak|extract|zip|unzip|arsip|install|jalankan|run\b|edit|"
                r"ubah|perbaiki|fix|tambah|buat|bikin|build|kompres|download|unduh|buka)")


Q_WORDS = (r"^(apa|apakah|siapa|kenapa|mengapa|bagaimana|gimana|kapan|dimana|di mana|berapa|jelaskan|jelasin|terangkan|"
           r"ceritakan|what|why|how|when|where|who|which|explain|tell me|can you explain)\b")


def decide_intent(ctx, text):
    """Returns (intent, needs_plan)."""
    forced, ctx.force_intent = ctx.force_intent, None
    t = text.strip().lower()
    mode = ctx.cfg.get("mode", "auto")
    plan_wanted = bool(re.search(PLAN_NOUNS, t)) or len(t) > 160
    if forced == "build":
        return "build", True
    if forced == "chat" or mode == "chat":
        return "chat", False
    build = bool(re.search(BUILD_VERBS, t)) and bool(re.search(BUILD_NOUNS, t))
    if build:
        return "build", plan_wanted
    if mode != "code" and (t.endswith("?") or re.match(Q_WORDS, t)) and not re.search(ACTION_VERBS, t):
        return "chat", False
    return "task", False


def expand_mentions(ctx, text):
    """@file -> include the file contents in the message (workspace only)."""
    extra = []
    for m in re.finditer(r"(?<!\S)@([\w./\-]+)", text):
        p = Path(os.path.realpath(str(ctx.ws / m.group(1))))
        if inside(p, ctx.ws) and p.is_file() and p.stat().st_size < 60000:
            try:
                extra.append("\n\n[file: %s]\n```\n%s\n```" % (rel(ctx, p), p.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass
    return text + "".join(extra)


def snapshot(root, limit=8000, budget=1.5):
    snap, t0 = {}, time.time()
    for dp, dns, fns in os.walk(str(root)):
        dns[:] = [d for d in dns if d not in SNAP_IGNORE]
        for fn in fns:
            fp = os.path.join(dp, fn)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            snap[fp] = (st.st_size, int(st.st_mtime))
            if len(snap) > limit or time.time() - t0 > budget:
                return snap, False
    return snap, True


def turn_report(ctx, before, comp_before):
    rows, seen, merged = [], [], {}
    for sym, path, extra in ctx.changes:
        key = (path, "m" if sym in ("+", "~") else sym)
        if key in merged:
            row = merged[key]
            if sym == "+":
                row[0], row[2] = "+", extra or row[2]
            continue
        merged[key] = [sym, rel(ctx, path), extra]
        rows.append(merged[key])
        seen.append(path)
    rows = [tuple(r) for r in rows]
    if comp_before:
        after, comp_after = snapshot(ctx.ws)
        if comp_after:
            def tracked(fp):
                return any(fp == s or fp.startswith(s + os.sep) for s in seen)
            for fp, st in after.items():
                if tracked(fp):
                    continue
                if fp not in before:
                    rows.append(("+", rel(ctx, fp), human_size(st[0])))
                elif before[fp] != st:
                    rows.append(("~", rel(ctx, fp), ""))
            for fp in before:
                if fp not in after and not tracked(fp):
                    rows.append(("-", rel(ctx, fp), ""))
    if rows:
        out()
        out(rule("changes"))
        col = {"+": C_OK, "~": C_WARN, "-": C_ERR, "→": C_ACC}
        for sym, txt, extra in rows[:14]:
            out("  %s %s%s" % (paint(sym, *col.get(sym, C_DIM)), clip(txt, tw() - 18), ("  " + dim(extra)) if extra else ""))
        if len(rows) > 14:
            out("  " + dim("… +%d more" % (len(rows) - 14)))
    t = ctx.turn
    if t["reqs"]:
        bits = ["%ds" % int(time.time() - t["t0"]), "%d tool" % t["tools"], "%d req" % t["reqs"]]
        if is_free_model(ctx.cur_model()):
            lim = ctx.cfg.get("free_daily")
            bits.append("today %d%s" % (req_today(ctx), ("/%d" % lim) if lim else ""))
        out("  " + faint("◦ ") + dim(" · ".join(bits)))
        if is_free_model(ctx.cur_model()) and req_today(ctx) and (ctx.cfg.get("free_daily") or 50) - req_today(ctx) <= 8:
            out("  " + warn("! ") + dim("approaching the daily free request limit."))


def notify_done(ctx, secs):
    exe = shutil.which("termux-notification")
    if secs < 45 or not exe or not ctx.cfg.get("notify", True):
        return
    try:
        subprocess.Popen([exe, "--title", "Axion Code", "--content", "Task finished (%d s)" % secs],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def announce_without_action(text):
    t = (text or "").strip()
    if not t or len(t) > 500:
        return False
    return bool(re.search(r"(saya akan|aku akan|selanjutnya|sekarang saya|langkah berikutnya|let me|i will|i'll|next,? i)", t[-200:].lower())
                and re.search(r"[:…]\s*$|\.\.\.\s*$", t))


def auto_verify(ctx):
    """Check the changed files. Returns a list of error texts (empty = passed)."""
    files = [p for p in changed_files(ctx) if file_sig(p) != ctx.verified_sig.get(str(p))]
    if not files:
        return []
    out()
    out(rule("verification"))
    sp = Spinner("checking the result")
    sp.start()
    try:
        issues, n = verify_paths(ctx, files)
    finally:
        sp.stop()
    for p in files:
        ctx.verified_sig[str(p)] = file_sig(p)
    errs = [m for lv, m in issues if lv == "error"]
    warns = [m for lv, m in issues if lv == "warn"]
    if not issues:
        out("  " + ok("✓ ") + "%d files checked, no problems" % n)
    else:
        out("  " + (err("✗ ") if errs else warn("! ")) + "%d files checked: %d errors, %d warnings" % (n, len(errs), len(warns)))
        for m in errs[:8]:
            out("    " + err(clip(m, tw() - 8)))
        for m in warns[:4]:
            out("    " + warn(clip(m, tw() - 8)))
    return errs


def trim_plan_messages(ctx, start):
    names = {}
    for m in ctx.messages[start:]:
        for tc in m.get("tool_calls") or []:
            names[tc["id"]] = tc["function"]["name"]
    for m in ctx.messages[start:]:
        if m.get("role") == "tool" and names.get(m.get("tool_call_id")) in (
                "web_search", "web_fetch", "review_website", "read_file", "search_files", "project_overview", "list_dir"):
            c = m.get("content") or ""
            if len(c) > 700:
                m["content"] = c[:500] + "\n…[research summary is in history/notes.md and the plan]"


def call_model(ctx, phase, tools, on_text, on_status, ui):
    tried, ctx_tries, bad_tries, tok_tries = [], 0, 0, 0
    while True:
        model = ctx.cur_model()
        sanitize_messages(ctx.messages)
        msgs = [{"role": "system", "content": build_system(ctx, phase)}] + ctx.messages
        can_rotate = rotation_enabled(ctx) and len(candidate_models(ctx)) > 1 and ctx.turn.get("rot", 0) < MAX_ROT_PER_TURN
        try:
            res = stream_chat(ctx, model, msgs, tools, on_text, on_status, 1 if can_rotate else 3, True, ui.get("reset"),
                              fast_rate=can_rotate, max_tokens=out_budget(ctx, model, msgs))
            note_model(ctx, model, "ok")
            return res
        except NoToolsError as e:
            e2 = ApiError(str(e), code=404, kind="notools")
        except ApiError as e:
            e2 = e
        ui["sp"].stop()
        rest = ui["gate"].flush()
        if rest:
            ui["md"].feed(rest)
        ui["md"].flush()
        log_event(ctx, "ERROR [%s] %s: %s" % (model, e2.kind, e2))
        save_history(ctx, "error")
        if e2.kind == "badreq" and bad_tries < 2:
            # the provider rejected the shape of the history (not the model's fault): clean it and retry the same model
            bad_tries += 1
            fixed = sanitize_messages(ctx.messages, aggressive=bad_tries > 1)
            out("  " + warn("↻ ") + dim("history cleaned (%d fixes), retrying…" % fixed))
            ui["gate"].__init__()
            ui["sp"].start()
            continue
        if e2.kind in ("maxtok", "ctx") and tok_tries < 3:
            # the requested output budget does not fit this model or provider: negotiate it down, then retry
            cur = out_budget(ctx, model, msgs)
            lim = re.search(r"(?:<=|at most|maximum(?: is| of)?|limit(?: is| of)?)\s*(\d{3,6})", str(e2).lower())
            new = int(lim.group(1)) - 64 if (lim and int(lim.group(1)) < cur) else cur // 2
            if 1024 <= new < cur:
                tok_tries += 1
                ctx.max_out[model] = new
                out("  " + warn("↻ ") + dim("output limit for this model set to %d tokens, retrying…" % new))
                ui["gate"].__init__()
                ui["sp"].start()
                continue
        tried.append(model)
        mark_cooldown(ctx, model, e2)
        if e2.kind not in ("net", "ctx", "auth", "daily", "badreq", "maxtok"):
            note_model(ctx, model, "fail")
        if e2.kind == "ctx" and ctx_tries < 1:
            ctx_tries += 1
            out("  " + warn("↻ ") + dim("the context is too long for this model, trimming history…"))
            local_compact(ctx, keep_last=4)
            ui["sp"].start()
            continue
        if e2.kind in ("auth", "daily") or (e2.kind == "credits" and is_free_model(model)):
            raise e2
        had_partial = ui["started"][0]
        if not (can_rotate and rotate_now(ctx, err_reason(e2), tried, est_tokens(msgs))):
            raise e2
        ui["gate"].__init__()
        if had_partial:
            out("  " + dim("(answer interrupted, continued by a fallback model)"))
            ui["started"][0] = False
        ui["sp"].start()


def run_agent(ctx, phase, allowed, max_steps, stop_tool=None):
    """Model <-> tool loop. Returns: done | stop_tool | error | limit."""
    schemas = slim_schemas([t["schema"] for n, t in TOOLS.items() if n in allowed])
    empty = nudges = steps = badjson = trunc = verifs = relogin = err_streak = polish = issue_nudges = 0
    reviewed = False
    while True:
        steps += 1
        if steps > max_steps:
            out("  " + warn("! step limit of %d reached." % max_steps) + dim(" Type 'continue' to resume."))
            save_history(ctx, "limit")
            return "limit"
        guard_context(ctx, phase)
        sp = Spinner("thinking")
        sp.start()
        md = MdStream()
        started = [False]
        gate = TextGate()
        ui = {"sp": sp, "md": md, "started": started, "gate": gate}

        def reset(sp=sp, md=md, started=started, gate=gate):
            rest = gate.flush()
            if rest:
                md.feed(rest)
            md.flush()
            if started[0]:
                out("  " + dim("(connection dropped, the answer restarts from the beginning)"))
                started[0] = False
            gate.__init__()
            sp.start()

        ui["reset"] = reset

        def show(vis, sp=sp, md=md, started=started):
            if vis:
                if not started[0]:
                    sp.stop()
                    started[0] = True
                    sys.stdout.write(acc("◆ "))
                md.feed(vis)

        def on_text(t, sp=sp, gate=gate, show=show):
            show(gate.feed(t))
            if gate.blocked:
                sp.label = "preparing a tool call"
            elif gate.in_think:
                sp.label = "thinking"

        def on_status(s, sp=sp):
            sp.label = s

        try:
            msg, finish, usage, reasoning = call_model(ctx, phase, schemas, on_text, on_status, ui)
        except ApiError as e:
            sp.stop()
            md.flush()
            if e.kind == "auth" and relogin < 1 and sys.stdin.isatty():
                out("  " + err("✗ API key rejected (401)."))
                relogin += 1
                if ensure_key(ctx, force=True):
                    continue
                return "error"
            out("  " + err("✗ " + str(e)))
            if e.kind in ("forbidden", "blocked"):
                state, _info = validate_key(key_of(ctx))
                if state == "invalid":
                    out("  " + dim("Your OpenRouter key really is rejected. Enter it again with: python run.py --setup"))
                else:
                    out("  " + dim("Your OpenRouter key is valid. This 403 comes from the model, the provider or your network, not from the key."))
                    out("  " + dim("Pick another model with /models, or check the connection with /net"))
            elif e.kind in ("rate", "server", "net", "stall"):
                out("  " + dim("all fallback models failed. Check the network with /net or pick another model: /models"))
            elif e.kind == "ctx":
                out("  " + dim("the history is too long: /compact or /clear"))
            log_event(ctx, "STOPPED: %s" % e)
            save_history(ctx, "error")
            out("  " + dim("memory saved in %s · continue later with /resume" % short_path(hist_dir(ctx))))
            return "error"
        finally:
            sp.stop()
        show(gate.flush())
        md.flush()
        if usage:
            ctx.usage["prompt"] += usage.get("prompt_tokens", 0) or 0
            ctx.usage["completion"] += usage.get("completion_tokens", 0) or 0
            ctx.usage["last_prompt"] = usage.get("prompt_tokens", 0) or 0
        names = set(TOOLS)
        calls = msg.get("tool_calls") or []
        for tc in calls:
            fn = tc["function"]
            fn["name"] = normalize_tool_name(fn.get("name"), names) or fn.get("name")
        content = strip_think(msg["content"]).strip() if msg.get("content") else ""
        if not calls and content:
            parsed, rest_text = parse_text_tool_calls(content, names)
            if parsed:
                calls = msg["tool_calls"] = parsed
                content = rest_text
                note_model(ctx, ctx.cur_model(), "badfmt")
                out("  " + dim("↻ tool-call format repaired"))
        if not content and not calls and (reasoning or "").strip() and finish != "length":
            content = reasoning.strip()[-3000:]
            out("  " + dim("◇ the model sent only its reasoning; showing it as is:"))
            for l in textwrap.wrap(content[-1200:], max(20, tw() - 6))[-14:]:
                out("    " + dim(l))
            note_model(ctx, ctx.cur_model(), "empty")
        msg["content"] = content or ("" if calls else None)
        if finish == "length" and not calls and content:
            trunc += 1
            ctx.messages.append(msg)
            if trunc >= 3 and rotate_now(ctx, "repeatedly cut-off answers"):
                trunc = 0
            ctx.messages.append({"role": "user", "content": "[system] Your answer was cut off by the length limit. Continue exactly where the "
                                                            "last text ended, without repeating anything."})
            out("  " + dim("↻ answer cut off, continuing…"))
            save_history(ctx, "length")
            continue
        if not content and not calls:
            empty += 1
            note_model(ctx, ctx.cur_model(), "empty")
            log_event(ctx, "empty response (%d) from %s" % (empty, ctx.cur_model()))
            save_history(ctx, "empty")
            if empty <= 1:
                out("  " + dim("↻ empty response, asking the model to continue…"))
                ctx.messages.append({"role": "user", "content": "[system] Your response was empty. Continue the task: call the tools you "
                                                                "need or give a final summary."})
                continue
            if rotate_now(ctx, "repeated empty responses"):
                empty = 0
                ctx.messages.append({"role": "user", "content": "[system] The previous model returned empty responses. Continue the work from "
                                                                "the last point (see the handoff)."})
                continue
            out("  " + warn("! the model returned an empty response.") + dim(" Retry or switch models: /models"))
            return "error"
        parsed_args, used_ids = {}, set()
        for tc in calls:
            fn = tc["function"]
            if not tc.get("id") or tc["id"] in used_ids:
                tc["id"] = "call_%d_%d" % (int(time.time() * 1000) % 10000000, len(used_ids))
            used_ids.add(tc["id"])
            a_, st_ = repair_tool_args(fn.get("arguments"), fn.get("name"))
            parsed_args[tc["id"]] = (a_, st_)
            fn["arguments"] = json.dumps(a_ if a_ is not None else {}, ensure_ascii=False)  # the history always holds valid JSON
        ctx.messages.append(msg)
        if not calls:
            if phase == "plan":
                return "done"
            pending = [t for t in ctx.todos if t["status"] != "completed"]
            if nudges < 1 and ctx.turn["tools"] > 0 and pending:
                nudges += 1
                out("  " + dim("↻ steps remain, continuing…"))
                ctx.messages.append({"role": "user", "content": "[system] There are unfinished steps: " +
                                     "; ".join(t["content"] for t in pending)[:300] +
                                     ". Continue now with tools, or mark them done / explain what blocks you."})
                continue
            if nudges < 2 and announce_without_action(content):
                nudges += 1
                out("  " + dim("↻ the model only announced an action, asking it to act…"))
                ctx.messages.append({"role": "user", "content": "[system] Do not just describe it. Do it now with tools."})
                continue
            issue = ctx.turn.get("issue")
            if phase == "build" and issue and issue_nudges < 2 and ctx.turn["tools"] > 0:
                issue_nudges += 1
                out("  " + dim("↻ the last check failed, asking the model to fix it…"))
                activate_skill(ctx, "debug-skill")
                ctx.messages.append({"role": "user", "content": "[system] The last %s call failed: %s. Nothing shows that it works now. Find the "
                                     "cause, fix it, and run the check again until it passes. If it truly cannot be fixed, explain exactly "
                                     "why. Do not ask for permission to fix your own bugs." % (issue["tool"], issue["summary"])})
                continue
            if phase == "build" and ctx.intent != "chat":
                if ctx.templates_used and ctx.turn.get("tpl_nudges", 0) < 2:
                    tpl_msg = template_nudge(ctx)
                    if tpl_msg:
                        ctx.turn["tpl_nudges"] = ctx.turn.get("tpl_nudges", 0) + 1
                        out("  " + dim("↻ the result is still too close to the template, asking for real customization…"))
                        ctx.messages.append({"role": "user", "content": tpl_msg})
                        continue
                if verifs < 2:
                    errs = auto_verify(ctx)
                    if errs:
                        verifs += 1
                        out("  " + dim("↻ fixing the verification results…"))
                        ctx.messages.append({"role": "user", "content": "[system] Automatic verification found problems that MUST be fixed:\n" +
                                             "\n".join("- " + e for e in errs[:12]) +
                                             "\nFix them now with tools, then run verify_files until it passes."})
                        continue
                if polish < 1 and ctx.turn["tools"] > 0:
                    polish += 1
                    found = ui_polish_findings(ctx)
                    if found:
                        out("  " + dim("↻ polishing the interface (%d findings)…" % len(found)))
                        activate_skill(ctx, "design-skill")
                        ctx.messages.append({"role": "user", "content": "[system] Automatic UI review found problems. Fix the HIGH and MEDIUM ones now "
                                             "with small, targeted edit_file changes, then run review_ui again:\n" +
                                             "\n".join("- " + f for f in found)})
                        continue
                if not reviewed and ctx.intent == "build" and ctx.plan and ctx.turn["tools"] > 0:
                    reviewed = True
                    out("  " + dim("↻ reviewing the result against the plan…"))
                    ctx.messages.append({"role": "user", "content": "[system] Review the result against the plan: are all features and steps present "
                                         "and working? Any bugs or missing logic? If something is lacking, fix it NOW with tools. If it is "
                                         "complete, reply with a short final summary: features, files, how to run it."})
                    continue
            save_history(ctx, "done")
            return "done"
        empty = 0
        if started[0]:
            out()
        stop, bad_round, n_ok, n_err = False, 0, 0, 0
        for tc in calls:
            name = tc["function"]["name"]
            args, st = parsed_args.get(tc["id"], (None, "bad"))
            note = ""
            if args is None or st == "truncated":
                cut = st == "truncated" or finish == "length"
                if cut:
                    shrink_chunk(ctx)  # this model hit its output limit: ask for smaller parts from now on
                salv = salvage_write(ctx, name, args) if (name in ("write_file", "append_file") and args is not None) else None
                if salv:
                    args, note = salv
                    out("  " + warn("↻ ") + dim("output limit reached: the complete part is saved, continuing in smaller parts"))
                else:
                    bad_round += 1
                    n_err += 1
                    if cut:
                        trunc += 1
                    out("  " + warn("↻ ") + dim("output was cut off, asking the model to resend smaller parts" if cut else
                                                "invalid tool JSON, asking the model to resend"))
                    ctx.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": bad_call_message(name, st, finish, chunk_lines(ctx))})
                    continue
            args = fix_args(name, args)
            if name not in allowed:
                out("  " + dim("· %s skipped (not used in this phase)" % name))
                ctx.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": "ERROR: tool '%s' is not available in this phase "
                                     "or mode. Available: %s" % (name, ", ".join(sorted(allowed)[:14]))})
                continue
            ctx.turn["tools"] += 1
            tool_header(name, args)
            key = loop_key(name, args)
            res = loop_check(ctx, key) or exec_tool(ctx, name, args)
            loop_record(ctx, key, res)
            if note:
                res = res + "\n" + note
            failed = is_failure(name, res)
            if failed:
                n_err += 1
            else:
                n_ok += 1
            if name in CHECK_TOOLS and (name != "run_shell" or is_check_command(args.get("command", ""))):
                if failed:
                    ctx.turn["issue"] = {"tool": name, "summary": first_error_line(res)}
                    activate_skill(ctx, "debug-skill")
                else:
                    ctx.turn.pop("issue", None)
            show_result(name, res)
            ctx.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": cap(res)})
            if stop_tool and name == stop_tool and res.startswith("OK"):
                stop = True
        badjson = badjson + 1 if bad_round and bad_round == len(calls) else 0
        if (badjson >= 3 or trunc >= 2) and rotate_now(ctx, "repeatedly broken or cut-off tool calls"):
            badjson = trunc = 0
        err_streak = err_streak + 1 if (n_err and not n_ok) else 0
        if err_streak == 3:
            activate_skill(ctx, "debug-skill")
        if err_streak == 4:
            ctx.messages.append({"role": "user", "content": "[system] Four steps in a row failed. Stop repeating the same approach: read the error "
                                 "messages, inspect the real state (list_dir / read_file), then choose a different strategy. If you are still "
                                 "stuck, explain the blocker to the user."})
            out("  " + dim("↻ several steps failed in a row, asking the model to change its approach"))
        elif err_streak >= 7 and rotate_now(ctx, "%d failed steps in a row" % err_streak):
            err_streak = 0
        save_history(ctx, "step")
        if stop:
            return "stop_tool"


def plan_phase(ctx, user_text):
    out()
    out(rule("planning", C_VIO))
    out("  " + dim("research and design first, then write code"))
    ctx.plan = None
    start = len(ctx.messages) - 1
    allowed = set(PLAN_TOOLS) - (set() if ctx.cfg.get("research", True) else WEB_TOOLS)
    reason = run_agent(ctx, "plan", allowed, PLAN_MAX_STEPS, stop_tool="submit_plan")
    if not ctx.plan and reason != "error":
        ctx.messages.append({"role": "user", "content": "[system] Call submit_plan now with the complete plan."})
        reason = run_agent(ctx, "plan", allowed, 2, stop_tool="submit_plan")
    if not ctx.plan:
        out("  " + warn("! no plan was produced; building directly."))
        return False
    trim_plan_messages(ctx, start)
    if ctx.cfg.get("plan_confirm"):
        try:
            ans = input(rl("  " + acc("▍") + " " + dim("build according to the plan? [Y/n] or type a revision › "))).strip()
        except EOFError:
            ans = ""
        if ans.lower() in ("n", "no", "tidak"):
            out("  " + dim("cancelled. The plan stays saved in history/plan.md"))
            return False
        if ans and ans.lower() not in ("y", "ya", "yes"):
            ctx.messages.append({"role": "user", "content": "[user revision of the plan] " + ans})
    out()
    out(rule("building", C_OK))
    return True


def run_turn(ctx, user_text):
    ctx.turn = {"t0": time.time(), "tools": 0, "reqs": 0, "rot": 0}
    ctx.templates_used = {}
    ctx.changes = []
    ctx.handoff = False
    intent, need_plan = decide_intent(ctx, user_text)
    ctx.intent = intent
    if intent != "chat":
        ctx.task = user_text
    if intent == "build":
        ctx.plan, ctx.todos = None, []
    picked = pick_skills(ctx, user_text, intent, bool(need_plan and ctx.cfg.get("plan", True)))
    if not picked and ctx.active_skills and (ctx.plan or len(user_text.strip()) < 40):
        picked = list(ctx.active_skills)  # "continue", "yes", ...: keep the previous skills
    ctx.active_skills = picked
    if intent == "chat":
        out("  " + dim("◇ Q&A mode"))
    elif intent == "build":
        out("  " + dim("◇ build mode" + (" · research and plan first" if need_plan and ctx.cfg.get("plan", True) else "")))
    if ctx.active_skills:
        out("  " + dim("◇ skills: " + ", ".join(ctx.active_skills)))
    before, comp_before = snapshot(ctx.ws)
    ctx.messages.append({"role": "user", "content": expand_mentions(ctx, user_text)})
    save_history(ctx, "start")
    try:
        if intent == "build" and need_plan and ctx.cfg.get("plan", True):
            plan_phase(ctx, user_text)
        if intent == "chat":
            run_agent(ctx, "chat", CHAT_TOOLS, MAX_STEPS)
        else:
            run_agent(ctx, "build", set(TOOLS), MAX_STEPS)
    finally:
        turn_report(ctx, before, comp_before)
        save_history(ctx, "end of turn")
        try:
            save_config(ctx.cfg)
        except Exception:
            pass
        notify_done(ctx, int(time.time() - ctx.turn["t0"]))


CHECK_TOOLS = ("run_shell", "run_python", "verify_files")
_CHECK_CMD_RX = re.compile(r"\b(python3?|node|npm|npx|pip3?|pytest|unittest|make|gradle|gradlew|cargo|go|java|javac|tsc|bash|sh|flask|uvicorn|"
                           r"gcc|clang|cmake|mvn|php|ruby|deno|bun)\b|^\s*\./")
_PROBE_RX = re.compile(r"^\s*(ls|cat|head|tail|grep|find|which|echo|test|pwd|cd|mkdir|cp|mv|rm|touch|wc|stat|file|du|df|env|printenv)\b")


def is_check_command(cmd):
    """Only build/run/test commands count as 'checks'; exploratory commands (grep, ls, ...) may fail without being a problem."""
    return bool(_CHECK_CMD_RX.search(cmd or "")) and not _PROBE_RX.search(cmd or "")


def loop_key(name, args):
    try:
        return name + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False)[:400]
    except (TypeError, ValueError):
        return name


def loop_check(ctx, key):
    """An identical call that already failed 3 times is not executed again (stops the model from going in circles)."""
    n = ctx.turn.setdefault("fails", {}).get(key, 0)
    if n >= 3:
        return ("ERROR: this identical call has already failed %d times. Do not repeat it. Read the earlier error, inspect the real "
                "state (read_file / list_dir), then change your approach or ask the user with ask_user." % n)
    return None


def loop_record(ctx, key, res):
    fails = ctx.turn.setdefault("fails", {})
    if res.startswith(("ERROR", "ISSUES")):
        fails[key] = fails.get(key, 0) + 1
    else:
        fails.pop(key, None)


def salvage_write(ctx, name, args):
    """Cut-off write_file/append_file: save the complete lines and ask the model to continue. Returns (args, note) or None."""
    path, content = args.get("path"), args.get("content")
    if not path or not isinstance(content, str) or len(content) < 120:
        return None
    cut = content.rfind("\n")
    if cut < 60:
        return None
    keep = content[:cut + 1]
    if name == "write_file" and "append" not in args:
        try:
            target = Path(os.path.expanduser(str(path)))
            target = target if target.is_absolute() else ctx.ws / target
            if target.exists() and target.stat().st_size > len(keep.encode("utf-8")):
                return None  # would overwrite a larger existing file with a fragment: let the model decide
        except (OSError, ValueError):
            return None
    new = dict(args)
    new["content"] = keep
    last = keep.rstrip("\n").splitlines()[-1][:80] if keep.strip() else ""
    note = ("[system] Output limit reached: only the first %d complete lines were saved (last saved line: %r). The file is NOT complete. "
            "Continue with append_file starting exactly AFTER that line, at most %d lines per call."
            % (len(keep.splitlines()), last, chunk_lines(ctx)))
    return new, note
