"""Workspace memory (history/): plan, notes, transcript, handoff, recovery."""

import json
import os
import time

from axion.config import HISTORY_DIRNAME
from axion.state import is_free_model, req_today
from axion.toolcalls import sanitize_messages
from axion.ui import C_ACC, C_DIM, dim, out, panel


def hist_dir(ctx):
    return ctx.ws / HISTORY_DIRNAME


def log_event(ctx, text):
    item = (time.strftime("%H:%M:%S"), str(text))
    ctx.pending_events.append(item)
    ctx.all_events.append(item)
    if len(ctx.all_events) > 80:
        del ctx.all_events[:30]


def msg_to_md(m):
    role = m.get("role", "?")
    parts = ["### %s · %s\n" % (role, time.strftime("%H:%M:%S"))]
    c = m.get("content")
    if c:
        parts.append(str(c)[:20000] + "\n")
    for tc in m.get("tool_calls") or []:
        fn = tc.get("function", {})
        parts.append("**tool_call** `%s` %s\n" % (fn.get("name"), str(fn.get("arguments"))[:20000]))
    return "\n".join(parts) + "\n"


def read_notes_text(ctx, limit=4000):
    try:
        return (hist_dir(ctx) / "notes.md").read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return ""


def plan_markdown(plan):
    parts = ["# Plan: %s" % plan.get("title", "Project"), "", plan.get("summary", ""), ""]
    if plan.get("features"):
        parts += ["## Features"] + ["- " + f for f in plan["features"]] + [""]
    if plan.get("architecture"):
        parts += ["## Architecture", plan["architecture"], ""]
    if plan.get("files"):
        parts += ["## Files"] + ["- `%s`: %s" % (f["path"], f["purpose"]) for f in plan["files"]] + [""]
    if plan.get("steps"):
        parts += ["## Steps"] + ["%d. **%s** %s" % (i, s["title"], s.get("details", "")) for i, s in enumerate(plan["steps"], 1)] + [""]
    if plan.get("research_notes"):
        parts += ["## Research", plan["research_notes"], ""]
    if plan.get("verification"):
        parts += ["## Verification"] + ["- " + v for v in plan["verification"]]
    return "\n".join(parts)


def handoff_text(ctx, reason=""):
    parts = ["# Handoff for the next model", "", "created: " + time.strftime("%Y-%m-%d %H:%M:%S")]
    if reason:
        parts.append("trigger: " + reason)
    parts.append("last model: " + ctx.cur_model())
    if ctx.task:
        parts += ["", "## User request", ctx.task[:1500]]
    if ctx.plan:
        parts += ["", "## Plan", plan_markdown(ctx.plan)[:5000]]
    if ctx.todos:
        mark = {"completed": "x", "in_progress": ">"}
        parts += ["", "## Progress"] + ["- [%s] %s" % (mark.get(t["status"], " "), t["content"]) for t in ctx.todos]
    if ctx.all_changes:
        parts += ["", "## Files created or changed"] + ["- %s %s" % (s, p) for s, p in ctx.all_changes[-60:]]
    notes = read_notes_text(ctx, 3000)
    if notes:
        parts += ["", "## Notes and research", notes]
    if ctx.all_events:
        parts += ["", "## Recent events"] + ["- [%s] %s" % e for e in ctx.all_events[-8:]]
    return "\n".join(parts)


def save_history(ctx, reason="auto"):
    """Save all memory to <workspace>/history. Never raises."""
    try:
        d = hist_dir(ctx)
        d.mkdir(parents=True, exist_ok=True)
        if ctx.hist_count > len(ctx.messages):
            ctx.hist_count = len(ctx.messages)
        new = ctx.messages[ctx.hist_count:]
        if new or ctx.pending_events:
            tr = d / "transcript.md"
            fresh = not tr.exists()
            with open(str(tr), "a", encoding="utf-8") as f:
                if fresh:
                    f.write("# Axion Code transcript\n\n")
                for t, text in ctx.pending_events:
                    f.write("> [%s] %s\n\n" % (t, text))
                for m in new:
                    f.write(msg_to_md(m))
            ctx.pending_events = []
            ctx.hist_count = len(ctx.messages)
        state = {"version": 3, "saved": time.strftime("%Y-%m-%d %H:%M:%S"), "reason": reason, "workspace": str(ctx.ws),
                 "model": ctx.cur_model(), "primary_model": ctx.cfg.get("model"), "rotations": ctx.rotations,
                 "intent": ctx.intent, "task": ctx.task, "plan": ctx.plan, "todos": ctx.todos,
                 "changes": ctx.all_changes[-200:], "events": ctx.all_events[-50:], "messages": ctx.messages}
        tmp = d / "state.json.tmp"
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(d / "state.json"))
        (d / "handoff.md").write_text(handoff_text(ctx, reason), encoding="utf-8")
        if ctx.plan:
            (d / "plan.md").write_text(plan_markdown(ctx.plan), encoding="utf-8")
        return True
    except Exception:
        return False


def peek_history(ctx):
    try:
        return json.loads((hist_dir(ctx) / "state.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def load_history(ctx):
    d = peek_history(ctx)
    if not d or not d.get("messages"):
        return None
    ctx.messages = d["messages"]
    ctx.plan = d.get("plan")
    ctx.todos = d.get("todos") or []
    ctx.task = d.get("task", "")
    ctx.all_changes = [tuple(x) for x in d.get("changes", [])]
    ctx.hist_count = len(ctx.messages)
    repair_history(ctx)
    ctx.handoff = True
    return d


def show_plan(ctx, plan):
    rows = []
    if plan.get("summary"):
        rows.append((plan["summary"], None))
    feats = plan.get("features") or []
    if feats:
        rows += [("", None), ("Features", C_ACC)] + [("• " + f, None) for f in feats[:8]]
        if len(feats) > 8:
            rows.append(("… +%d more features" % (len(feats) - 8), C_DIM))
    files = plan.get("files") or []
    if files:
        rows += [("", None), ("Files", C_ACC)] + [("• %s: %s" % (f["path"], f["purpose"]) if f["purpose"] else "• " + f["path"], None)
                                                  for f in files[:8]]
    steps = plan.get("steps") or []
    rows += [("", None), ("Steps", C_ACC)] + [("%d. %s" % (i, s["title"]), None) for i, s in enumerate(steps[:14], 1)]
    for line in panel("Plan · " + plan["title"], rows):
        out(line)
    est = max(6, int(len(steps) * 1.6) + 5)
    msg = "estimated ±%d requests · plan saved in history/plan.md" % est
    if is_free_model(ctx.cur_model()):
        left = (ctx.cfg.get("free_daily") or 50) - req_today(ctx)
        if est > left:
            msg += "  · ±%d free requests left today, which may not be enough" % max(left, 0)
    out("  " + dim(msg))


def repair_history(ctx):
    """After Ctrl+C, a crash or a session load: make the history valid (paired tool calls, valid JSON arguments)."""
    sanitize_messages(ctx.messages)
