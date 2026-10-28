"""Helper tools: todo list and ask_user."""

import difflib

from axion.state import ToolError
from axion.tools.registry import S, tool
from axion.ui import acc, bold, clip, dim, faint, ok, out, progress_bar, rl, tw, vio, warn
from axion.util import as_items, item_text


# --- tools: helpers ------------------------------------------------------
@tool("todo", "Write or update the task list for multi-step work (shown to the user). Update statuses as you go; do not end your turn while items remain unfinished.",
      {"items": {"type": "array", "description": "list of steps",
                 "items": {"type": "object", "properties": {
                     "content": {"type": "string"},
                     "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}},
                     "required": ["content", "status"]}}}, ["items"])
def t_todo(a, ctx):
    raw = a.get("items") if a.get("items") is not None else (a.get("todos") if a.get("todos") is not None else a.get("tasks"))
    smap = {"done": "completed", "complete": "completed", "finished": "completed", "doing": "in_progress",
            "active": "in_progress", "in-progress": "in_progress", "progress": "in_progress", "todo": "pending", "open": "pending"}
    todos = []
    for i in as_items(raw):
        if not isinstance(i, dict):
            i = {"content": str(i)}
        text = item_text(i)
        st = str(i.get("status", "pending")).lower()
        st = smap.get(st, st)
        if st not in ("pending", "in_progress", "completed"):
            st = "pending"
        if len(text) >= 2:
            todos.append({"content": clip(text, 200), "status": st})
    if raw and not todos:
        raise ToolError('todo needs a list of items, for example [{"content": "Write the HTML", "status": "pending"}]')
    if ctx.plan and len(ctx.todos) >= 3 and len(todos) < max(2, int(len(ctx.todos) * 0.6)):
        todos = merge_todos(ctx.todos, todos)
    ctx.todos = todos
    print_todos(ctx)
    done = sum(1 for t in ctx.todos if t["status"] == "completed")
    return "OK: %d/%d done" % (done, len(ctx.todos))


def print_todos(ctx):
    if not ctx.todos:
        out("  " + dim("(no plan yet)"))
        return
    for t in ctx.todos:
        txt = clip(t["content"], tw() - 12)
        if t["status"] == "completed":
            out("    " + ok("✓ ") + dim(txt))
        elif t["status"] == "in_progress":
            out("    " + warn("◐ ") + bold(txt))
        else:
            out("    " + faint("○ ") + dim(txt))
    done = sum(1 for t in ctx.todos if t["status"] == "completed")
    out("    " + progress_bar(done, len(ctx.todos)) + dim(" %d/%d" % (done, len(ctx.todos))))


@tool("ask_user", "Ask the user when you need a decision or information, especially before an irreversible action on an ambiguous request.", {"question": S("short question; include your interpretation")}, ["question"])
def t_ask_user(a, ctx):
    out("  " + vio("▍") + " " + bold("Question"))
    for l in str(a.get("question")).splitlines():
        out("  " + vio("▍") + " " + l)
    try:
        return "User answer: " + input(rl("  " + vio("▍") + " " + acc("› "))).strip()
    except EOFError:
        return "(no answer from the user)"


def merge_todos(old, new):
    """The model sent a much shorter todo than the plan: update matching plan steps instead of replacing them."""
    merged = [dict(x) for x in old]
    for n in new:
        best, score = None, 0.0
        for o in merged:
            r = difflib.SequenceMatcher(None, o["content"].lower(), n["content"].lower()).ratio()
            if r > score:
                best, score = o, r
        if best is not None and score >= 0.5:
            best["status"] = n["status"]
    return merged
