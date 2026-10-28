"""Saved sessions, undo and trash."""

import json
import shutil
from pathlib import Path

from axion.config import SESSIONS_DIR, TRASH_DIR
from axion.memory import repair_history
from axion.skills import safe_name
from axion.tools.files import restore_trash, trash_item
from axion.ui import acc, clip, dim, err, ok, out, rl, short_path, tw
from axion.util import human_size, rel


def save_session(ctx, name):
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    p = SESSIONS_DIR / (safe_name(name) + ".json")
    p.write_text(json.dumps({"workspace": str(ctx.ws), "model": ctx.cfg.get("model"),
                             "messages": ctx.messages, "todos": ctx.todos}, ensure_ascii=False), encoding="utf-8")
    return p


def load_session(ctx, name):
    p = SESSIONS_DIR / (safe_name(name) + ".json")
    if not p.is_file():
        return False
    d = json.loads(p.read_text(encoding="utf-8"))
    ctx.messages = d.get("messages", [])
    ctx.todos = d.get("todos", [])
    repair_history(ctx)
    ctx.hist_count = len(ctx.messages)
    return True


def do_undo(ctx):
    if not ctx.undo:
        out("  " + dim("nothing to undo"))
        return
    e = ctx.undo.pop()
    t = e["t"]
    try:
        if t == "write":
            if e["old"] is None:
                e["path"].unlink()
                out("  " + ok("✓ file removed: ") + rel(ctx, e["path"]))
            else:
                e["path"].write_text(e["old"], encoding="utf-8")
                out("  " + ok("✓ reverted: ") + rel(ctx, e["path"]))
        elif t == "move":
            e["src"].parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(e["dst"]), str(e["src"]))
            out("  " + ok("✓ moved back: ") + rel(ctx, e["src"]))
        elif t == "trash":
            d = restore_trash(e["trash"], str(e["orig"]))
            out("  " + ok("✓ restored from trash: ") + rel(ctx, d))
        elif t == "copy":
            d = trash_item(e["dst"])
            out("  " + ok("✓ copy/archive moved to trash: ") + rel(ctx, e["dst"]))
        elif t == "mkdir":
            e["path"].rmdir()
            out("  " + ok("✓ folder removed: ") + rel(ctx, e["path"]))
        elif t == "extract":
            if e["new_dir"]:
                trash_item(e["dest"])
            else:
                for f in e["created"]:
                    try:
                        Path(f).unlink()
                    except OSError:
                        pass
            out("  " + ok("✓ extraction undone: ") + rel(ctx, e["dest"]))
    except (OSError, KeyError) as ex:
        out("  " + err("✗ could not undo: %s" % ex))


def trash_items():
    if not TRASH_DIR.is_dir():
        return []
    items = []
    for f in sorted(TRASH_DIR.glob("*.meta.json")):
        try:
            meta = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        item = Path(str(f)[:-len(".meta.json")])
        if item.exists():
            items.append((item, meta))
    return items


def cmd_trash(ctx, parts):
    sub = parts[0].lower() if parts else "list"
    items = trash_items()
    if sub == "empty":
        if not items:
            out("  " + dim("trash is empty"))
            return
        try:
            ans = input(rl("  " + err("▍") + " " + dim("permanently delete %d items? type 'yes' › " % len(items)))).strip()
        except EOFError:
            return
        if ans == "yes":
            shutil.rmtree(str(TRASH_DIR), ignore_errors=True)
            out("  " + ok("✓ trash emptied"))
        return
    if sub == "restore" and len(parts) > 1 and parts[1].isdigit():
        i = int(parts[1])
        if 1 <= i <= len(items):
            d = restore_trash(items[i - 1][0])
            out("  " + ok("✓ restored: ") + short_path(d))
        else:
            out("  " + err("no such number"))
        return
    if not items:
        out("  " + dim("trash is empty"))
        return
    for i, (item, meta) in enumerate(items, 1):
        out("  %s %s %s" % (acc("%2d" % i), clip(short_path(meta.get("orig", item.name)), tw() - 22),
                            dim("%s · %s" % (meta.get("time", "")[:8], human_size(meta.get("size", 0))))))
    out("  " + dim("restore: /trash restore <number>  ·  empty: /trash empty"))
