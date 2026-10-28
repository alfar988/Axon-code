"""Runs tools, renders tool headers and results."""

from axion.diagnose import with_hints
from axion.state import redact, ToolError
from axion.tools.registry import TOOLS
from axion.ui import bold, C_ACC, C_ERR, C_OK, C_VIO, C_WARN, clip, dim, err, faint, ok, out, paint, tw, warn


RESULT_LINES = {"search_files": 6, "find_files": 5, "web_search": 6, "list_dir": 4, "read_file": 1}


TOOL_META = {
    "list_dir": ("List", C_ACC), "read_file": ("Read", C_ACC), "search_files": ("Search", C_ACC),
    "find_files": ("Find", C_ACC), "write_file": ("Write", C_WARN), "edit_file": ("Edit", C_WARN),
    "make_dir": ("Mkdir", C_WARN), "move_path": ("Move", C_WARN), "copy_path": ("Copy", C_WARN),
    "delete_path": ("Delete", C_ERR), "extract_archive": ("Extract", C_WARN), "create_archive": ("Archive", C_WARN),
    "run_shell": ("Bash", C_VIO), "manage_process": ("Proc", C_VIO), "web_fetch": ("Fetch", C_VIO),
    "web_search": ("Web", C_VIO), "review_website": ("Audit", C_VIO), "http_request": ("API", C_VIO),
    "install_skill": ("Skill+", C_VIO), "use_skill": ("Skill", C_VIO), "todo": ("Plan", C_ACC),
    "ask_user": ("Ask", C_ACC),
}


def tool_label(name, a, w):
    def g(k):
        v = a.get(k)
        return "" if v is None else str(v)

    if name == "run_shell":
        s = g("command").replace("\n", " ⏎ ")
        return clip(("[bg] " if a.get("background") else "") + s, w)
    if name in ("read_file", "write_file", "append_file", "edit_file", "make_dir", "delete_path", "list_dir"):
        extra = ""
        if name == "read_file" and (a.get("start_line") or a.get("end_line")):
            extra = " [%s-%s]" % (a.get("start_line", 1), a.get("end_line", "…"))
        if name == "delete_path" and a.get("permanent"):
            extra = " (PERMANENT)"
        return clip(g("path") + extra, w)
    if name in ("move_path", "copy_path"):
        return clip("%s → %s" % (g("src"), g("dst")), w)
    if name == "extract_archive":
        return clip(g("path") + (" → " + g("dest") if a.get("dest") else ""), w)
    if name == "create_archive":
        return clip(g("output"), w)
    if name in ("web_fetch", "review_website", "install_skill"):
        return clip(g("url"), w)
    if name == "http_request":
        return clip("%s %s" % (g("method") or "GET", g("url")), w)
    if name in ("search_files", "find_files"):
        return clip(g("pattern"), w)
    if name == "web_search":
        return clip(g("query"), w)
    if name == "use_skill":
        return clip(g("name") + (" part %s" % a["part"] if a.get("part") else ""), w)
    if name == "use_template":
        return clip(g("name") + (" → " + g("path") if a.get("path") else ""), w)
    if name == "todo":
        return "(%d steps)" % len(a.get("items") or [])
    if name == "manage_process":
        return clip(("%s %s" % (g("action"), g("id"))).strip(), w)
    for v in a.values():
        if isinstance(v, str):
            return clip(v.replace("\n", " ⏎ "), w)
    return ""


def tool_header(name, a):
    verb, col = TOOL_META.get(name, (name, C_ACC))
    out("%s %s %s" % (paint("●", *col), bold("%-7s" % verb), dim(tool_label(name, a, tw() - 12))))


def show_result(name, text):
    if name in ("run_shell", "run_python") and not text.startswith(("ERROR", "DENIED")):
        return  # already shown live
    lines = [l for l in text.splitlines() if l.strip()] or ["(empty)"]
    first = lines[0]
    if first.startswith("OK:"):
        out("  " + ok("✓ ") + clip(first[3:].strip().split(". ")[0], tw() - 6))
        return
    if first.startswith("ERROR"):
        out("  " + err("✗ ") + paint(clip(first[5:].lstrip(": "), tw() - 6), *C_ERR))
        return
    if first.startswith("DENIED"):
        out("  " + warn("⊘ ") + dim("denied"))
        return
    if first.startswith("ISSUES"):
        out("  " + warn("! ") + clip(first, tw() - 6))
        for l in lines[1:6]:
            out("    " + dim(clip(l, tw() - 8)))
        return
    n = RESULT_LINES.get(name, 1)
    for i, l in enumerate(lines[:n]):
        out(faint("  ⎿ " if i == 0 else "    ") + dim(clip(l, tw() - 6)))
    if len(lines) > n:
        out(faint("    ") + dim("… +%d lines" % (len(lines) - n)))


def exec_tool(ctx, name, args):
    t = TOOLS.get(name)
    if not t:
        return "ERROR: unknown tool '%s'. Available: %s" % (name, ", ".join(TOOLS))
    try:
        res = t["fn"](args, ctx)
    except ToolError as e:
        res = "ERROR: %s" % e
    except KeyboardInterrupt:
        raise
    except Exception as e:
        res = "ERROR: %s: %s" % (type(e).__name__, e)
    return with_hints(name, args, redact(ctx, str(res)))


TOOL_META.update({
    "save_note": ("Note", C_ACC), "read_notes": ("Notes", C_ACC), "submit_plan": ("Plan", C_VIO),
    "project_overview": ("Scan", C_ACC), "verify_files": ("Check", C_OK), "download_file": ("Download", C_WARN),
    "system_info": ("System", C_VIO), "preview_web": ("Preview", C_VIO), "run_python": ("Python", C_VIO),
    "append_file": ("Append", C_WARN), "use_template": ("Template", C_WARN), "review_ui": ("Review", C_OK),
})
