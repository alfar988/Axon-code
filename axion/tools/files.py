"""File tools: read, search, write, append, edit, folders, move, copy, delete."""

import difflib
import fnmatch
import json
import os
import re
import shutil
import time
from pathlib import Path

from axion.config import IGNORE_DIRS, TRASH_DIR
from axion.security import fs_path, inside
from axion.state import ask, ToolError, track
from axion.tools.registry import B, I, S, tool
from axion.ui import clip, dim, ok, out, tw
from axion.util import denied, human_size, rel, show_diff, to_int


# --- tools: read / search ---------------------------------------------------
@tool("list_dir", "List the contents of a folder (name, size). Defaults to the workspace folder.",
      {"path": S("folder, default '.'"), "depth": I("depth 1-4, default 1")})
def t_list_dir(a, ctx):
    root = fs_path(ctx, a.get("path") or ".", "listing a folder")
    if not root.is_dir():
        raise ToolError("not a folder: %s" % a.get("path"))
    depth = max(1, min(to_int(a.get("depth"), 1), 4))
    lines = []

    def walk(d, lvl):
        if len(lines) >= 300:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            lines.append("  " * lvl + "(access denied)")
            return
        for p in entries:
            if len(lines) >= 300:
                lines.append("… (truncated)")
                return
            pad = "  " * lvl
            if p.is_dir():
                lines.append("%s%s/" % (pad, p.name))
                if lvl + 1 < depth and p.name not in IGNORE_DIRS:
                    walk(p, lvl + 1)
            else:
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                lines.append("%s%s  (%s)" % (pad, p.name, human_size(size)))

    walk(root, 0)
    return "\n".join(lines) if lines else "(empty folder)"


@tool("read_file", "Read a text file with line numbers. Use start_line/end_line for large files.",
      {"path": S("path file"), "start_line": I("first line (default 1)"),
       "end_line": I("last line (default: start + 399)")}, ["path"])
def t_read_file(a, ctx):
    path = fs_path(ctx, a.get("path"), "reading a file")
    if not path.exists():
        raise ToolError("file not found: %s" % a.get("path"))
    if path.is_dir():
        raise ToolError("that is a folder; use list_dir")
    data = path.read_bytes()
    if b"\0" in data[:4096]:
        raise ToolError("binary file (%s), cannot be read as text" % human_size(len(data)))
    lines = data.decode("utf-8", "replace").splitlines()
    start = max(1, to_int(a.get("start_line"), 1))
    end = min(to_int(a.get("end_line"), start + 399), len(lines))
    seg = lines[start - 1:end]
    body = "\n".join("%5d\t%s" % (i, l) for i, l in enumerate(seg, start))
    head = "[%s · %d lines total · showing %d-%d]\n" % (rel(ctx, path), len(lines), start, end)
    note = ""
    if end < len(lines):
        note = "\n[… %d more lines, use start_line=%d]" % (len(lines) - end, end + 1)
    return head + body + note


def iter_files(root, glob_pat="*"):
    for dp, dns, fns in os.walk(str(root)):
        dns[:] = [d for d in dns if d not in IGNORE_DIRS]
        for fn in fns:
            if fnmatch.fnmatch(fn, glob_pat):
                yield Path(dp) / fn


@tool("search_files", "Search text or a regex across files (like grep).",
      {"pattern": S("regex to search for"), "path": S("folder, default '.'"),
       "glob": S("file name filter, e.g. '*.py'"), "ignore_case": B("case-insensitive")},
      ["pattern"])
def t_search_files(a, ctx):
    root = fs_path(ctx, a.get("path") or ".", "searching inside files")
    try:
        rx = re.compile(str(a.get("pattern")), re.I if a.get("ignore_case") else 0)
    except re.error as e:
        raise ToolError("invalid regex: %s" % e)
    res = []
    files = [root] if root.is_file() else iter_files(root, a.get("glob") or "*")
    for f in files:
        try:
            if f.stat().st_size > 1000000:
                continue
            data = f.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:2048]:
            continue
        for i, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            if rx.search(line):
                res.append("%s:%d: %s" % (rel(ctx, f), i, line.strip()[:200]))
                if len(res) >= 80:
                    return "\n".join(res) + "\n… (limited to 80 results)"
    return "\n".join(res) if res else "(no results)"


@tool("find_files", "Find files by name or glob pattern, e.g. '**/*.py' or '*.html'.",
      {"pattern": S("glob pattern"), "path": S("starting folder, default: workspace")}, ["pattern"])
def t_find_files(a, ctx):
    root = fs_path(ctx, a.get("path") or ".", "searching for files")
    pat = str(a.get("pattern"))
    if "/" not in pat and "**" not in pat:
        pat = "**/" + pat
    res = []
    for p in root.glob(pat):
        if set(p.relative_to(root).parts) & IGNORE_DIRS:
            continue
        res.append(rel(ctx, p) + ("/" if p.is_dir() else ""))
        if len(res) >= 200:
            res.append("… (limited to 200)")
            break
    return "\n".join(sorted(res)) if res else "(no results)"


# --- tools: write / edit ---------------------------------------------------
@tool("write_file", "Create a new file or overwrite an existing one. Parent folders are created automatically. Content must be COMPLETE, never placeholders. Large files: write the first part here (about 100 lines at most), then add each further part with append_file.",
      {"path": S("path file"), "content": S("file content"), "append": B("true = append to the end of the file")},
      ["path", "content"])
def t_write_file(a, ctx):
    path = fs_path(ctx, a.get("path"), "writing a file", write=True)
    if a.get("content") is None:
        raise ToolError("the content parameter is empty")
    content = str(a["content"])
    if path.is_dir():
        raise ToolError("that path is a folder")
    old = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
    appending = bool(a.get("append")) and old is not None
    n = len(content.splitlines())
    new_text = (old + content) if appending else content
    if old is None:
        out("    " + dim("new file · %d lines · %s" % (n, human_size(len(content.encode("utf-8"))))))
        for l in content.splitlines()[:6]:
            out("    " + ok(clip("+ " + l, tw() - 6)))
        if n > 6:
            out("    " + dim("… +%d lines" % (n - 6)))
        okk, why = ask(ctx, "Write", rel(ctx, path))
    elif appending:
        out("    " + dim("append %d lines to the end of the file" % n))
        okk, why = ask(ctx, "Append", rel(ctx, path))
    else:
        show_diff(old, new_text)
        okk, why = ask(ctx, "Overwrite", rel(ctx, path))
    if not okk:
        return denied(why)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    ctx.undo.append({"t": "write", "path": path, "old": old})
    track(ctx, "+" if old is None else "~", path, human_size(len(new_text.encode("utf-8"))) if old is None else "")
    return "OK: %s %s (%d lines%s)" % ("created" if old is None else ("appended" if appending else "overwritten"),
                                       rel(ctx, path), n, ", total %d" % len(new_text.splitlines()) if appending else "")


@tool("edit_file", "Edit text in an existing file. old_string must match exactly (without line numbers) and be unique, unless replace_all=true. For several changes at once pass 'edits'. Read the file before editing.",
      {"path": S("path file"), "old_string": S("exact existing text"), "new_string": S("replacement text"),
       "replace_all": B("replace every occurrence"),
       "edits": {"type": "array", "description": "several changes at once",
                 "items": {"type": "object", "properties": {
                     "old_string": {"type": "string"}, "new_string": {"type": "string"},
                     "replace_all": {"type": "boolean"}}, "required": ["old_string", "new_string"]}}},
      ["path"])
def t_edit_file(a, ctx):
    path = fs_path(ctx, a.get("path"), "editing a file", write=True)
    if not path.is_file():
        raise ToolError("file not found: %s" % a.get("path"))
    text = path.read_text(encoding="utf-8", errors="replace")
    edits = list(a.get("edits") or [])
    if a.get("old_string") is not None:
        edits.insert(0, {"old_string": a.get("old_string"), "new_string": a.get("new_string", ""),
                         "replace_all": a.get("replace_all")})
    if not edits:
        raise ToolError("no changes given: provide old_string/new_string or edits")
    new_text = text
    total = 0
    for i, e in enumerate(edits, 1):
        old_s, new_s = str(e.get("old_string", "")), str(e.get("new_string", ""))
        if not old_s:
            raise ToolError("edit #%d: old_string is empty" % i)
        if "\r\n" in new_text and "\r\n" not in old_s:
            old_s, new_s = old_s.replace("\n", "\r\n"), new_s.replace("\n", "\r\n")
        cnt = new_text.count(old_s)
        if cnt == 0:
            first = old_s.strip().splitlines()[0] if old_s.strip() else ""
            close = difflib.get_close_matches(first, [l.strip() for l in new_text.splitlines()], n=1, cutoff=0.6)
            hint = (" Similar line: %r" % close[0]) if close else ""
            raise ToolError("edit #%d: old_string not found.%s Re-read the file with read_file." % (i, hint))
        if cnt > 1 and not e.get("replace_all"):
            raise ToolError("edit #%d: old_string appears %d times. Add more context to make it unique, or set replace_all=true." % (i, cnt))
        new_text = new_text.replace(old_s, new_s) if e.get("replace_all") else new_text.replace(old_s, new_s, 1)
        total += cnt if e.get("replace_all") else 1
    show_diff(text, new_text)
    okk, why = ask(ctx, "Edit", rel(ctx, path))
    if not okk:
        return denied(why)
    path.write_text(new_text, encoding="utf-8")
    ctx.undo.append({"t": "write", "path": path, "old": text})
    track(ctx, "~", path)
    return "OK: %s edited (%d replacements)" % (rel(ctx, path), total)


# --- tool: file manager -----------------------------------------------------
def tree_stats(p, max_files=20000, budget=2.0):
    p = Path(p)
    if p.is_file() or p.is_symlink():
        try:
            return 1, p.stat().st_size
        except OSError:
            return 1, 0
    n, size, t0 = 0, 0, time.time()
    for dp, _dns, fns in os.walk(str(p)):
        for fn in fns:
            n += 1
            try:
                size += os.path.getsize(os.path.join(dp, fn))
            except OSError:
                pass
            if n >= max_files or time.time() - t0 > budget:
                return n, size
    return n, size


def safe_copy(src, dst):
    try:
        return shutil.copy2(src, dst)
    except OSError:
        return shutil.copy(src, dst)


def trash_item(p):
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    p = Path(p)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = "%s-%s" % (stamp, p.name)
    dest = TRASH_DIR / name
    i = 1
    while dest.exists():
        dest = TRASH_DIR / ("%s-%d" % (name, i))
        i += 1
    n, size = tree_stats(p)
    shutil.move(str(p), str(dest))
    meta = {"orig": str(p), "time": stamp, "files": n, "size": size}
    Path(str(dest) + ".meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return dest


def restore_trash(item, orig=None):
    item = Path(item)
    meta_f = Path(str(item) + ".meta.json")
    if orig is None:
        orig = json.loads(meta_f.read_text(encoding="utf-8"))["orig"]
    dest = Path(orig)
    if dest.exists():
        dest = Path(str(dest) + ".restored")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(item), str(dest))
    try:
        meta_f.unlink()
    except OSError:
        pass
    return dest


@tool("make_dir", "Create a folder (including parent folders).", {"path": S("path folder")}, ["path"])
def t_make_dir(a, ctx):
    p = fs_path(ctx, a.get("path"), "creating a folder", write=True)
    if p.exists():
        return "OK: already exists: %s" % rel(ctx, p)
    okk, why = ask(ctx, "Mkdir", rel(ctx, p))
    if not okk:
        return denied(why)
    p.mkdir(parents=True, exist_ok=True)
    ctx.undo.append({"t": "mkdir", "path": p})
    track(ctx, "+", p, "folder")
    return "OK: folder created: %s" % rel(ctx, p)


@tool("move_path", "Move or rename a file or folder. If dst is an existing folder, src is moved into it.",
      {"src": S("source"), "dst": S("destination / new name"), "overwrite": B("overwrite if the destination exists")},
      ["src", "dst"])
def t_move_path(a, ctx):
    src = fs_path(ctx, a.get("src"), "moving / renaming (source)", write=True, destructive=True)
    dst = fs_path(ctx, a.get("dst"), "moving / renaming (destination)", write=True)
    if not src.exists():
        raise ToolError("source not found: %s" % a.get("src"))
    if dst.is_dir() and dst != src:
        dst = dst / src.name
    if dst == src:
        return "OK: nothing to do (same path)"
    if inside(dst, src):
        raise ToolError("cannot move a folder into itself")
    if dst.exists() and not a.get("overwrite"):
        raise ToolError("destination already exists: %s. Set overwrite=true or choose another name." % rel(ctx, dst))
    okk, why = ask(ctx, "Move", "%s  →  %s" % (rel(ctx, src), rel(ctx, dst)),
                   ["the destination will be OVERWRITTEN (the old one goes to trash)"] if dst.exists() else None)
    if not okk:
        return denied(why)
    if dst.exists():
        trash_item(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    ctx.undo.append({"t": "move", "src": src, "dst": dst})
    track(ctx, "→", src, rel(ctx, dst))
    return "OK: moved %s → %s" % (rel(ctx, src), rel(ctx, dst))


@tool("copy_path", "Copy a file or folder.",
      {"src": S("source"), "dst": S("destination"), "overwrite": B("overwrite if it exists")}, ["src", "dst"])
def t_copy_path(a, ctx):
    src = fs_path(ctx, a.get("src"), "copying (source)")
    dst = fs_path(ctx, a.get("dst"), "copying (destination)", write=True)
    if not src.exists():
        raise ToolError("source not found: %s" % a.get("src"))
    if dst.is_dir() and not src.is_dir():
        dst = dst / src.name
    if dst.exists() and not a.get("overwrite"):
        raise ToolError("destination already exists: %s. Set overwrite=true." % rel(ctx, dst))
    n, size = tree_stats(src)
    okk, why = ask(ctx, "Copy", "%s  →  %s" % (rel(ctx, src), rel(ctx, dst)), ["%d file · %s" % (n, human_size(size))])
    if not okk:
        return denied(why)
    if dst.exists():
        trash_item(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(str(src), str(dst), copy_function=safe_copy)
    else:
        safe_copy(str(src), str(dst))
    ctx.undo.append({"t": "copy", "dst": dst})
    track(ctx, "+", dst, human_size(size))
    return "OK: copied %s → %s (%d files, %s)" % (rel(ctx, src), rel(ctx, dst), n, human_size(size))


@tool("delete_path", "Delete a file or folder. By default it is moved to the Axion trash (recoverable with /trash or /undo). Use permanent=true only when the user EXPLICITLY asks for permanent deletion.",
      {"path": S("path to delete"), "permanent": B("delete permanently (skip the trash)")}, ["path"])
def t_delete_path(a, ctx):
    p = fs_path(ctx, a.get("path"), "deleting", write=True, destructive=True)
    if not (p.exists() or p.is_symlink()):
        raise ToolError("not found: %s" % a.get("path"))
    n, size = tree_stats(p)
    perm = bool(a.get("permanent"))
    kind = "folder" if p.is_dir() else "file"
    det = ["%s · %d file · %s" % (kind, n, human_size(size))]
    if perm:
        det.append("PERMANENT: cannot be undone")
        okk, why = ask(ctx, "Delete PERMANENTLY", rel(ctx, p), det, level="danger")
    else:
        det.append("moved to trash (recoverable)")
        okk, why = ask(ctx, "Delete", rel(ctx, p), det)
    if not okk:
        return denied(why)
    if perm:
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(str(p))
        else:
            p.unlink()
        track(ctx, "-", p, "permanent")
        return "OK: permanently deleted: %s" % rel(ctx, p)
    dest = trash_item(p)
    ctx.undo.append({"t": "trash", "orig": p, "trash": dest})
    track(ctx, "-", p, "to trash")
    return "OK: %s moved to trash (%d files, %s). Restore with /undo or /trash." % (rel(ctx, p), n, human_size(size))




@tool("append_file", "Append content to the end of a file (the file is created if it does not exist). Use it for every part after "
      "the first when writing a large file. Same rules as write_file: complete code, never placeholders, at most the line "
      "limit given in your instructions per call.",
      {"path": S("file path"), "content": S("the next part, appended exactly as given")}, ["path", "content"])
def t_append_file(a, ctx):
    a = dict(a)
    a["append"] = True
    return t_write_file(a, ctx)
