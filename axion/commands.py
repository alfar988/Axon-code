"""Slash commands (/help, /models, /skills, ...)."""

import getpass
import os
import re
import shutil
import socket
import subprocess
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from axion import search as engine
from axion.client import _REAL_GAI, NETSTATE
from axion.config import API_BASE, DEFAULT_MODEL, ROUTER_MODEL, SESSIONS_DIR, SKILLS_DIR, VERSION
from axion.knowledge import add_lesson, all_lessons, forget
from axion.memory import hist_dir, load_history, peek_history, read_notes_text, show_plan
from axion.models import (
    auto_rotation, candidate_models, compact_history, hist_chars, model_ctx_len, models_cmd,
    rotation_enabled,
)
from axion.security import ask_outside, fs_path, inside
from axion.sessions import cmd_trash, do_undo, load_session, save_session
from axion.skills import find_skill, install_skill, list_skills, safe_name, skill_body, split_parts
from axion.state import api_get, ensure_key, key_of, mask_key, req_today, save_config, ToolError
from axion.templates import template_catalog
from axion.tools.files import t_list_dir
from axion.tools.misc import print_todos
from axion.tools.project import overview_text, start_preview
from axion.tools.research import keys_of
from axion.tools.registry import TOOLS
from axion.tools.shell import kill_group
from axion.ui import acc, bold, clip, dim, err, faint, ok, out, rl, short_model, short_path, Spinner, tw, warn
from axion.util import human_size, rel
from axion.verify import changed_files, format_issues, verify_paths


def cmd_secret(ctx, parts):
    sub = parts[0].lower() if parts else "list"
    sec = ctx.cfg.setdefault("secrets", {})
    if sub == "set" and len(parts) > 1:
        name = re.sub(r"[^A-Za-z0-9_]", "_", parts[1]).upper()
        try:
            val = getpass.getpass("  value for %s (hidden) › " % name).strip()
        except (EOFError, KeyboardInterrupt):
            return
        if val:
            sec[name] = val
            save_config(ctx.cfg)
            out("  " + ok("✓ saved. Use it in prompts as: ") + acc("{{%s}}" % name))
    elif sub in ("del", "rm", "remove") and len(parts) > 1:
        if sec.pop(parts[1].upper(), None) is not None:
            save_config(ctx.cfg)
            out("  " + ok("✓ removed"))
        else:
            out("  " + err("none"))
    else:
        out("  " + dim("secret: ") + (", ".join("{{%s}}" % k for k in sec) or "(empty)"))
        out("  " + dim("usage: /secret set NAME  (example: /secret set MESHY_API_KEY)"))


def cmd_access(ctx, parts):
    sub = parts[0].lower() if parts else ""
    if sub == "full":
        bar = err("▍")
        out()
        out("  %s %s" % (bar, bold(err("FULL ACCESS to the whole device storage and system"))))
        for l in ("The AI can read, change and DELETE any file this account can reach",
                  "(photos, documents, app data, even system files), without asking per file.",
                  "Stays on until Axion Code is closed or you run /access reset.",
                  "Core folders (/, HOME, /system, etc.) stay protected from deletion."):
            out("  %s %s" % (bar, dim(l)))
        try:
            ans = input(rl("  %s %s " % (bar, dim("type: I UNDERSTAND › ")))).strip()
        except EOFError:
            return
        if ans.strip().upper() in ("I UNDERSTAND", "SAYA PAHAM"):
            ctx.full_access = True
            ctx.warned_outside = True
            out("  " + warn("full access ENABLED") + dim(" (turn off: /access reset)"))
        else:
            out("  " + dim("cancelled"))
    elif sub == "add" and len(parts) > 1:
        p = Path(os.path.realpath(os.path.expanduser(" ".join(parts[1:]))))
        if not p.exists():
            out("  " + err("path does not exist"))
            return
        allowed, _ = ask_outside(ctx, [p], "giving the AI access to this folder for the session")
        if allowed:
            ctx.grants.add(p if p.is_dir() else p.parent)
            out("  " + ok("✓ allowed: ") + short_path(p))
    elif sub == "reset":
        ctx.full_access = False
        ctx.grants.clear()
        out("  " + ok("✓ access restored to the workspace only"))
    else:
        out("  " + dim("workspace : ") + short_path(ctx.ws))
        out("  " + dim("outside access: ") + ("FULL" if ctx.full_access else
                                           (", ".join(short_path(g) for g in ctx.grants) or "none (asks every time)")))
        out("  " + dim("/access add <path> · /access full · /access reset"))


def cmd_ps(ctx):
    if not ctx.bg:
        out("  " + dim("no background processes"))
        return
    for k, v in ctx.bg.items():
        run = v["proc"].poll() is None
        out("  %s %s %s" % (ok("●") if run else faint("○"), acc(k), dim("pid %s · %s" % (v["pid"], clip(v["cmd"], tw() - 24)))))


HELP = """
%s
  /game <idea>          build a game (plan, research, build, check)
  /web <idea>           build a website
  /ask <question>       Q&A mode (never changes files)
  /plan [task]          plan + research first, then build · on|off|confirm
  /build · /test · /fix · /ui · /review <url>
  /readme · /explain <file> · /refactor <file>

%s
  /models · /model [id|n]     choose a free model
  /rotate [auto|on|off|add id]  automatic fallback models
  /mode auto|chat|code        how the AI works
  /research on|off · /status · /abilities
  /search [kind] <query>        search the web now (kinds: news code qa docs packages academic wiki)
  /dig <question>               research a question across several sources

%s
  /history · /resume · /notes   memory in the workspace
  /lessons [list|add|forget|on|off]   what Axion learned from earlier work
  /auto · /access · /undo · /trash · /ps
  /serve [file] · /open <file> · /verify
  /overview · /ls · /cd

%s
  /skills · /skill show|use|unpin|why|install|remove
  /templates                    list ready-made starters
  /secret set|list|del <NAME>   store other API keys
  /todo · /compact · /clear · /save · /load
  /key · /tokens · /net · /wakelock · /exit

%s
  !command    run a shell command (live output)
  @file       include a file in the message
  Tab         complete commands and file names
  \"\"\"         start/end a multi-line message
"""


SLASH = ["/help", "/game", "/web", "/ask", "/plan", "/build", "/test", "/fix", "/review", "/readme", "/explain",
         "/refactor", "/models", "/model", "/rotate", "/mode", "/research", "/status", "/abilities", "/history",
         "/resume", "/notes", "/auto", "/access", "/undo", "/trash", "/ps", "/kill", "/serve", "/open", "/verify",
         "/overview", "/ls", "/cd", "/skills", "/skill", "/templates", "/ui", "/secret", "/todo", "/compact", "/clear", "/save", "/load",
         "/sessions", "/key", "/tokens", "/net", "/wakelock", "/init", "/search", "/dig", "/lessons", "/exit"]


def cmd_skill(ctx, parts):
    sub = parts[0].lower() if parts else ""
    arg = parts[1] if len(parts) > 1 else ""
    if sub == "install" and arg:
        sp = Spinner("downloading skill")
        sp.start()
        try:
            names = install_skill(arg, parts[2] if len(parts) > 2 else None)
        except ToolError as e:
            sp.stop()
            out("  " + err("✗ %s" % e))
            return
        finally:
            sp.stop()
        out("  " + ok("✓ installed: ") + ", ".join(names))
    elif sub == "show" and arg:
        s = find_skill(list_skills(ctx), arg)
        if not s:
            out("  " + err("skill not found"))
            return
        parts_ = split_parts(skill_body(s))
        out(parts_[0][:3500] if parts_ else "(empty)")
        if len(parts_) > 1:
            out("  " + dim("… %d parts; the model loads the rest with use_skill(part=N)" % len(parts_)))
    elif sub in ("use", "pin") and arg:
        s = find_skill(list_skills(ctx), arg)
        if not s:
            out("  " + err("skill not found"))
            return
        ctx.pinned_skills.add(s["name"])
        out("  " + ok("✓ skill pinned: ") + s["name"] + dim("  (release with /skill unpin %s)" % s["name"]))
    elif sub in ("unpin", "off"):
        if arg in ("", "all"):
            ctx.pinned_skills.clear()
            out("  " + ok("✓ all skills released; Axion picks them automatically again"))
        else:
            s = find_skill(list_skills(ctx), arg)
            ctx.pinned_skills.discard(s["name"] if s else arg)
            out("  " + ok("✓ released: ") + (s["name"] if s else arg))
    elif sub == "why":
        if not ctx.skill_report:
            out("  " + dim("no skill scoring yet. Send a request first."))
            return
        out("  " + dim("skill scores for the last request:"))
        for sc, nm, kind in ctx.skill_report:
            out("  %s %s %s" % (acc("%5.1f" % sc), bold(nm), dim(kind + (" · active" if nm in ctx.active_skills else ""))))
    elif sub in ("remove", "rm", "del") and arg:
        d = SKILLS_DIR / safe_name(arg)
        if d.is_dir():
            shutil.rmtree(str(d))
            out("  " + ok("✓ removed: " + d.name))
        else:
            out("  " + err("no installed skill in " + short_path(SKILLS_DIR) + " (built-in skills cannot be removed)"))
    else:
        out("  " + dim("usage: /skill show <name> | use <name> | unpin [name] | why | install <url> | remove <name>"))


def cmd_status(ctx):
    k = key_of(ctx)
    cur, base = ctx.cur_model(), ctx.cfg.get("model", DEFAULT_MODEL)
    out("  " + dim("active model ") + cur + (warn("  (random router)") if cur == ROUTER_MODEL else ""))
    if cur != base:
        out("  " + dim("main model   ") + base + dim("  (switched automatically)"))
    out("  " + dim("rotation     ") + ("on · %d fallbacks" % max(0, len(candidate_models(ctx)) - 1) if rotation_enabled(ctx) else "off"))
    out("  " + dim("key          ") + (mask_key(k) if k else err("not set")))
    out("  " + dim("usage today  ") + "%d%s" % (req_today(ctx), (" / %d" % ctx.cfg["free_daily"]) if ctx.cfg.get("free_daily") else
                                               dim("  (free-tier limits apply; adding credit raises them)")))
    out("  " + dim("network      ") + ("IPv4 only" if NETSTATE["ipv4_only"] else "IPv4 preferred"))
    out("  " + dim("workspace    ") + short_path(ctx.ws))
    out("  " + dim("permissions  ") + ("auto" if ctx.auto else "ask first") + dim("  · outside access: ") +
        ("FULL" if ctx.full_access else "%d folder" % len(ctx.grants)))
    out("  " + dim("planning     ") + ("on" if ctx.cfg.get("plan", True) else "off") + dim(" · research ") +
        ("on" if ctx.cfg.get("research", True) else "off") + dim(" · mode ") + ctx.cfg.get("mode", "auto"))
    out("  " + dim("history      ") + "%d messages · ~%dk characters" % (len(ctx.messages), hist_chars(ctx.messages) // 1000))


def cmd_mode(ctx, arg):
    if arg and arg[0] in ("auto", "chat", "code"):
        ctx.cfg["mode"] = arg[0]
        save_config(ctx.cfg)
    m = ctx.cfg.get("mode", "auto")
    desc = {"auto": "the AI chooses on its own: Q&A, build, or a regular task",
            "chat": "always Q&A; never changes files",
            "code": "always work mode with all tools"}[m]
    out("  " + dim("mode: ") + bold(m) + dim("  " + desc))
    out("  " + dim("change: /mode auto | chat | code"))


def cmd_plan(ctx, arg, rest):
    sub = arg[0].lower() if arg else ""
    if sub in ("on", "off"):
        ctx.cfg["plan"] = sub == "on"
        save_config(ctx.cfg)
        out("  " + ok("✓ plan + research: ") + ("on" if ctx.cfg["plan"] else "off"))
        return None
    if sub == "confirm":
        ctx.cfg["plan_confirm"] = not (len(arg) > 1 and arg[1].lower() == "off")
        save_config(ctx.cfg)
        out("  " + ok("✓ plan confirmation: ") + ("on" if ctx.cfg["plan_confirm"] else "off"))
        return None
    if rest:
        return "BUILD:" + rest
    if ctx.plan:
        show_plan(ctx, ctx.plan)
        print_todos(ctx)
    else:
        out("  " + dim("no plan yet. Use /plan <task> or ask for something to be built."))
        out("  " + dim("settings: /plan on|off · /plan confirm [off]"))
    return None


def cmd_research(ctx, arg):
    if arg and arg[0] in ("on", "off"):
        ctx.cfg["research"] = arg[0] == "on"
        save_config(ctx.cfg)
    out("  " + dim("web research while planning: ") + ("on" if ctx.cfg.get("research", True) else "off") + dim("  (/research on|off)"))


def cmd_lessons(ctx, arg, rest):
    sub = arg[0].lower() if arg else "list"
    if sub in ("on", "off"):
        ctx.cfg["lessons"] = sub == "on"
        save_config(ctx.cfg)
        out("  " + dim("learning from earlier work: ") + (ok("on") if sub == "on" else warn("off")))
    elif sub == "add" and len(arg) > 1:
        try:
            status, d = add_lesson(rest.split(None, 1)[1], "pref", [])
        except ToolError as e:
            out("  " + err("✗ %s" % e))
            return
        out("  " + ok("✓ lesson %s " % status) + dim("[%s]" % d["id"]))
    elif sub in ("forget", "delete", "rm") and len(arg) > 1:
        if arg[1] == "all":
            try:
                okk = input(rl("  delete ALL lessons? type 'yes' to confirm › ")).strip().lower() == "yes"
            except EOFError:
                okk = False
            if not okk:
                out("  " + dim("cancelled"))
                return
        n = forget(arg[1])
        out("  " + (ok("✓ removed %d" % n) if n else warn("no lesson with that id")))
    else:
        items = all_lessons()
        state = ok("on") if ctx.cfg.get("lessons", True) is not False else warn("off")
        out("  " + bold("Lessons") + dim("  · %d saved · learning " % len(items)) + state)
        for d in items[:30]:
            wrapped = textwrap.wrap(d["text"], max(20, tw() - 18)) or [""]
            out("  " + dim("%s " % d["id"]) + acc("%-4s " % d.get("kind", "tip")) + wrapped[0])
            for extra in wrapped[1:]:
                out(" " * 15 + extra)
        if not items:
            out("  " + dim("nothing yet. Axion saves a lesson after it fixes a non-obvious error, or you can add one: /lessons add <text>"))
        else:
            out("  " + dim("/lessons forget <id|all> · /lessons add <text> · /lessons on|off"))


def cmd_search(ctx, arg, rest):
    if not arg:
        out("  " + dim("usage: /search [kind] <query>   kinds: " + " ".join(engine.KINDS) + "   ·   /search providers"))
        return
    if arg[0] == "providers":
        for name, state in engine.provider_status(keys_of(ctx)):
            out("  %-14s %s" % (name, ok(state) if state == "ready" else dim(state)))
        out("  " + dim("optional keys (env or /secret set): BRAVE_API_KEY TAVILY_API_KEY SERPER_API_KEY SEARXNG_URL GITHUB_TOKEN"))
        return
    if arg[0] == "reset":
        engine.reset_state()
        out("  " + ok("✓ search cache and provider cooldowns cleared"))
        return
    kind, query = "general", rest
    if arg[0].lower() in engine.KINDS and len(arg) > 1:
        kind, query = arg[0].lower(), rest.split(None, 1)[1]
    sp = Spinner("searching")
    sp.start()
    try:
        found = engine.search(query, kind=kind, n=8, keys=keys_of(ctx))
    except ToolError as e:
        sp.stop()
        out("  " + err("✗ %s" % e))
        return
    finally:
        sp.stop()
    out("  " + dim("%d results via %s" % (len(found["results"]), ", ".join(found["used"]) or "-")))
    for i, r in enumerate(found["results"], 1):
        out("  " + acc("%d " % i) + bold(clip(r["title"], tw() - 8)) + (dim("  " + r["date"]) if r["date"] else ""))
        out("    " + dim(clip(r["url"], tw() - 8)))
    for n in found["notes"][:3]:
        out("  " + warn("! ") + dim(clip(n, tw() - 8)))


def cmd_rotate(ctx, arg):
    sub = arg[0].lower() if arg else ""
    if sub in ("on", "off"):
        ctx.cfg["rotate"] = sub == "on"
        save_config(ctx.cfg)
    elif sub == "auto":
        sp = Spinner("building the fallback list")
        sp.start()
        try:
            ctx.cfg["rotation"] = auto_rotation(ctx)
        finally:
            sp.stop()
        save_config(ctx.cfg)
    elif sub == "add" and len(arg) > 1:
        ctx.cfg.setdefault("rotation", []).append(arg[1])
        save_config(ctx.cfg)
    elif sub == "clear":
        ctx.cfg["rotation"] = []
        save_config(ctx.cfg)
    out("  " + dim("automatic rotation: ") + (ok("on") if rotation_enabled(ctx) else warn("off")))
    out("  " + dim("switches model automatically on errors, stalls, empty responses or a full context"))
    cur = ctx.cur_model()
    for i, m in enumerate(candidate_models(ctx), 1):
        mark = ok("●") if m == cur else " "
        out("  %s %s %s %s" % (mark, acc("%d" % i), clip(m, tw() - 16), dim("%dk" % (model_ctx_len(ctx, m) // 1000))))
    out("  " + dim("/rotate auto · add <id> · clear · on|off"))


def cmd_history(ctx):
    d = hist_dir(ctx)
    if not d.is_dir():
        out("  " + dim("no history in this workspace yet"))
        return
    out("  " + dim("folder: ") + short_path(d))
    for f in sorted(d.iterdir()):
        if f.is_file():
            out("  %s %s %s" % (acc("•"), f.name, dim(human_size(f.stat().st_size))))
    st = peek_history(ctx)
    if st:
        out("  " + dim("last: %s · %d messages · model %s" % (st.get("saved"), len(st.get("messages", [])), short_model(st.get("model", "")))))
    out("  " + dim("continue the work: /resume"))


def cmd_resume(ctx):
    d = load_history(ctx)
    if not d:
        out("  " + err("no history to resume in this workspace"))
        return None
    pend = [t for t in ctx.todos if t["status"] != "completed"]
    out("  " + ok("✓ history loaded") + dim(" (%d messages%s)" % (len(ctx.messages),
                                                             (", plan: " + ctx.plan["title"]) if ctx.plan else "")))
    if ctx.todos:
        print_todos(ctx)
    return ("PROMPT:Continue the previous work from the last point, following the plan and the handoff. "
            + ("Remaining steps: " + "; ".join(t["content"] for t in pend)[:300] if pend else
               "Check the latest result and finish whatever is not done."))


def cmd_notes(ctx):
    t = read_notes_text(ctx, 3000)
    out(t if t else "  " + dim("no notes yet (the AI saves them to history/notes.md)"))


def cmd_abilities(ctx):
    rows = [
        ("Build", "2D/3D games, websites, apps, APIs, bots, scripts: plan, research, build from tested templates, check automatically"),
        ("Self-repair", "reads errors, installs missing modules, fixes its own bugs and reruns until the check passes"),
        ("Quality", "static checks for undefined names, broken HTML and UI/accessibility/contrast review before it says done"),
        ("Files", "read/write/edit, delete (to trash), move/rename, copy, extract and create zip/tar, download, /undo"),
        ("Shell", "build and run commands with live output, background processes, web preview in the browser"),
        ("Research", "search with several providers (web, news, code, Q&A, docs, packages, papers), read pages in parallel, cite sources"),
        ("Web", "read pages, audit websites, call APIs, download files"),
        ("Learning", "saves lessons from fixed errors, applies them in later sessions, can write new skills (/lessons)"),
        ("Memory", "research notes and a full transcript in workspace/history, /resume, handoff between models"),
        ("Resilience", "automatic fallback models, rate-limit cooldowns, stall detection, context compaction, auto-save on errors"),
        ("Q&A", "answer questions, explain code, debug (/ask)"),
        ("Skills", "%d built-in skills picked automatically per request, plus installable ones" % len([s for s in list_skills(ctx) if s["builtin"]])),
    ]
    out()
    out("  " + bold("What Axion Code can do") + dim("  · %d tools" % len(TOOLS)))
    for k, v in rows:
        wrapped = textwrap.wrap(v, max(16, tw() - 19)) or [""]
        out("  " + acc("▸ ") + bold("%-12s" % k) + dim(wrapped[0]))
        for extra in wrapped[1:]:
            out(" " * 16 + dim(extra))


def cmd_verify(ctx, arg):
    paths = [fs_path(ctx, p, "checking files") for p in arg] or changed_files(ctx)
    if not paths:
        out("  " + dim("no files to check. Use /verify <file>"))
        return
    issues, n = verify_paths(ctx, paths)
    out("  " + (ok("✓ ") if not issues else err("✗ ")) + format_issues(issues, n).splitlines()[0].replace("OK: ", ""))
    for lv, m in issues[:15]:
        out("    " + (err if lv == "error" else warn)(clip(m, tw() - 8)))


def cmd_serve(ctx, arg):
    target = arg[0] if arg else ""
    port = int(arg[1]) if len(arg) > 1 and arg[1].isdigit() else None
    p = fs_path(ctx, target or ".", "preview web")
    if not inside(p, ctx.ws):
        out("  " + err("preview is only available for files inside the workspace"))
        return
    try:
        url, opened = start_preview(ctx, rel(ctx, p) if p != ctx.ws else "", port)
    except ToolError as e:
        out("  " + err("✗ %s" % e))
        return
    out("  " + ok("✓ preview: ") + acc(url) + (dim("  (opened in the browser)") if opened else dim("  (open it manually in a browser)")))
    out("  " + dim("stop it: /ps then /kill <id>"))


def cmd_open(ctx, rest):
    if not rest:
        out("  " + dim("usage: /open <file or url>"))
        return
    if re.match(r"^https?://", rest):
        exe, arg0 = shutil.which("termux-open-url"), rest
    else:
        exe, arg0 = shutil.which("termux-open"), str(fs_path(ctx, rest, "opening a file"))
    if not exe:
        out("  " + warn("termux-open is not installed.") + dim(" Install it with: pkg install termux-tools. Location: %s" % arg0))
        return
    try:
        subprocess.run([exe, arg0], timeout=8, capture_output=True)
        out("  " + ok("✓ opened: ") + clip(arg0, tw() - 14))
    except Exception as e:
        out("  " + err("✗ could not open: %s" % e))


def cmd_wakelock(ctx, arg):
    on, off = shutil.which("termux-wake-lock"), shutil.which("termux-wake-unlock")
    if not on:
        out("  " + dim("termux-wake-lock is not available here."))
        return
    if arg and arg[0] == "off":
        ctx.cfg["wakelock"] = False
        subprocess.run([off], capture_output=True, timeout=5)
        out("  " + ok("✓ wake-lock off"))
    else:
        ctx.cfg["wakelock"] = True
        subprocess.run([on], capture_output=True, timeout=5)
        out("  " + ok("✓ wake-lock on") + dim(" (the device stays awake while Axion works)"))
    save_config(ctx.cfg)


def cmd_overview(ctx):
    out(overview_text(ctx))


QUICK_PROMPTS = {
    "/test": "Run this project's tests (detect the test framework from the files present). If they fail, fix the cause and rerun until they pass, or explain what blocks you. ",
    "/readme": "Read this project and write a clear README.md: description, features, how to install and run it, folder structure. Use facts from the code; do not invent anything. ",
}


def cmd_net(ctx, arg):
    sub = arg[0].lower() if arg else "test"
    if sub in ("ipv4", "v4"):
        on = not (len(arg) > 1 and arg[1].lower() in ("off", "0", "no"))
        NETSTATE["ipv4_only"] = on
        ctx.cfg["ipv4_only"] = on
        save_config(ctx.cfg)
        out("  " + ok("✓ ") + "IPv4-only mode: " + ("on" if on else "off"))
        return
    u = urllib.parse.urlparse(API_BASE)
    host, port = u.hostname, u.port or (443 if u.scheme == "https" else 80)
    out("  " + dim("network to ") + host)
    for fam, label in ((socket.AF_INET, "IPv4"), (socket.AF_INET6, "IPv6")):
        try:
            infos = _REAL_GAI(host, port, fam, socket.SOCK_STREAM)
        except OSError:
            out("  " + dim("%s: no address" % label))
            continue
        t0 = time.time()
        try:
            s = socket.socket(fam, socket.SOCK_STREAM)
            s.settimeout(6)
            s.connect(infos[0][4])
            s.close()
            out("  %s %s connected in %d ms" % (ok("✓"), label, int((time.time() - t0) * 1000)))
        except OSError as e:
            out("  %s %s failed: %s" % (err("✗"), label, clip(str(e), tw() - 16)))
    t0 = time.time()
    st, _data = api_get("/models", None, timeout=20)
    out("  %s GET /models: %s in %d ms" % (ok("✓") if st == 200 else err("✗"), st, int((time.time() - t0) * 1000)))
    out("  " + dim("IPv4-only mode: ") + ("on" if NETSTATE["ipv4_only"] else "off (IPv4 is tried first)"))
    out("  " + dim("if you often see Errno 103: /net ipv4 on · and run termux-wake-lock"))


def handle_command(ctx, line):
    parts = line.strip().split()
    cmd = parts[0].lower()
    arg = parts[1:]
    rest = line.strip()[len(parts[0]):].strip()
    if cmd in ("/exit", "/quit", "/q"):
        return "exit"
    if cmd in ("/help", "/?"):
        out(HELP % (bold("Build & ask"), bold("Models & mode"), bold("Memory & permissions"), bold("More"), bold("Tips")))
    elif cmd == "/clear":
        ctx.messages, ctx.todos, ctx.plan, ctx.hist_count = [], [], None, 0
        out("  " + ok("✓ new conversation"))
    elif cmd == "/cd":
        if not rest:
            out("  " + dim("workspace: ") + str(ctx.ws))
            return None
        p = Path(os.path.expanduser(rest))
        p = p if p.is_absolute() else ctx.ws / p
        if not p.exists():
            try:
                yn = input(rl("  " + warn("the folder does not exist. Create it? ") + dim("[y/N] › "))).strip().lower()
            except EOFError:
                yn = "n"
            if yn in ("y", "ya"):
                p.mkdir(parents=True, exist_ok=True)
            else:
                return None
        if not p.is_dir():
            out("  " + err("not a folder"))
            return None
        ctx.ws = Path(os.path.realpath(str(p)))
        ctx.undo.clear()
        ctx.grants.clear()
        out("  " + ok("✓ workspace: ") + short_path(ctx.ws))
    elif cmd == "/ls":
        try:
            out(t_list_dir({"path": rest or ".", "depth": 1}, ctx))
        except ToolError as e:
            out("  " + err(str(e)))
    elif cmd == "/models":
        models_cmd(ctx, rest)
    elif cmd == "/model":
        if rest.isdigit():
            if not ctx.model_list:
                models_cmd(ctx)
            i = int(rest)
            if 1 <= i <= len(ctx.model_list):
                ctx.cfg["model"] = ctx.model_list[i - 1]["id"]
                ctx.cfg["model_chosen"] = True
                save_config(ctx.cfg)
                out("  " + ok("✓ model: ") + ctx.cfg["model"])
            else:
                out("  " + err("no such number. See /models"))
        elif rest:
            ctx.cfg["model"] = rest
            ctx.cfg["model_chosen"] = True
            save_config(ctx.cfg)
            out("  " + ok("✓ model: ") + rest)
        else:
            out("  " + dim("model: ") + ctx.cfg.get("model", DEFAULT_MODEL))
            out("  " + dim("list of free models: /models"))
    elif cmd == "/status":
        cmd_status(ctx)
    elif cmd == "/auto":
        ctx.auto = not (arg and arg[0].lower() in ("off", "0", "no"))
        out("  " + (warn("auto mode on: edits and commands inside the workspace run without asking (dangerous ones and anything outside the workspace still ask)")
                    if ctx.auto else ok("auto mode off (asks first)")))
    elif cmd == "/access":
        cmd_access(ctx, arg)
    elif cmd == "/skills":
        sk = list_skills(ctx)
        if not sk:
            out("  " + dim("no skills yet. Install one with: /skill install <github url>"))
        for s in sk:
            mark = ok("●") if s["name"] in ctx.active_skills else acc("•")
            tag = {"reference": " · large", "external": " · installed"}.get(s["kind"], "")
            out("  " + mark + " " + bold(s["name"]) + dim(tag + " - " + clip(s["desc"], max(10, tw() - len(s["name"]) - len(tag) - 8))))
        out("  " + dim("● = active for the current request · Axion picks skills itself · pin one with /skill use <name>"))
    elif cmd == "/templates":
        out(template_catalog())
        out("  " + dim("the AI copies one with use_template and adapts it; ask for a game or a page and it starts from the best match"))
    elif cmd == "/ui":
        return ("PROMPT:Run review_ui on the HTML pages in this workspace, fix every HIGH and MEDIUM finding with small, targeted "
                "edit_file changes, and run it again until the score is at least 85. " + rest)
    elif cmd == "/skill":
        cmd_skill(ctx, arg)
    elif cmd == "/secret":
        cmd_secret(ctx, arg)
    elif cmd == "/undo":
        do_undo(ctx)
    elif cmd == "/trash":
        cmd_trash(ctx, arg)
    elif cmd == "/ps":
        cmd_ps(ctx)
    elif cmd == "/kill":
        if arg and arg[0] in ctx.bg:
            kill_group(ctx.bg[arg[0]]["proc"])
            out("  " + ok("✓ stopped: ") + arg[0])
        else:
            out("  " + err("no such id. See /ps"))
    elif cmd == "/todo":
        print_todos(ctx)
    elif cmd == "/compact":
        compact_history(ctx)
    elif cmd == "/save":
        out("  " + ok("✓ saved: ") + short_path(save_session(ctx, rest or "manual")))
    elif cmd == "/load":
        if load_session(ctx, rest or "manual"):
            out("  " + ok("✓ session loaded (%d messages)" % len(ctx.messages)))
        else:
            out("  " + err("no such session. See /sessions"))
    elif cmd == "/sessions":
        files = sorted(SESSIONS_DIR.glob("*.json")) if SESSIONS_DIR.is_dir() else []
        out("\n".join("  • " + f.stem for f in files) if files else "  " + dim("(no sessions yet)"))
    elif cmd == "/key":
        ensure_key(ctx, force=True)
    elif cmd == "/tokens":
        u = ctx.usage
        out("  " + dim("last prompt     : ") + "%d token" % u["last_prompt"])
        out("  " + dim("session total   : ") + "%d in · %d out" % (u["prompt"], u["completion"]))
    elif cmd == "/init":
        return "PROMPT:Analyze the project in this workspace (structure and key files), then create an AXION.md file containing: a project summary, how to run/test/build it, the folder structure, and code conventions. Keep it short and dense."
    elif cmd == "/build":
        return ("PROMPT:Build the project in this workspace until it SUCCEEDS. Steps: detect the project type from the files present, install missing dependencies, run the build with run_shell (large timeout, live output), fix errors step by step until it succeeds or explain the concrete blocker, then report where the build output is (for example the APK) and its size. " + rest)
    elif cmd == "/fix":
        return ("PROMPT:Look at the latest error in this conversation (or rerun the failing command), find the root cause, fix the code, and run it again until it works. " + rest)
    elif cmd == "/review":
        if not rest:
            out("  " + dim("usage: /review <url>"))
            return None
        return "PROMPT:Audit the website %s with review_website, then give a structured review: summary, main problems, and prioritized fixes (high/medium/low) with concrete steps." % rest
    elif cmd == "/mode":
        cmd_mode(ctx, arg)
    elif cmd == "/net":
        cmd_net(ctx, arg)
    elif cmd == "/plan":
        return cmd_plan(ctx, arg, rest)
    elif cmd == "/research":
        cmd_research(ctx, arg)
    elif cmd == "/rotate":
        cmd_rotate(ctx, arg)
    elif cmd == "/history":
        cmd_history(ctx)
    elif cmd == "/resume":
        return cmd_resume(ctx)
    elif cmd == "/notes":
        cmd_notes(ctx)
    elif cmd == "/lessons":
        cmd_lessons(ctx, arg, rest)
    elif cmd == "/search":
        cmd_search(ctx, arg, rest)
    elif cmd == "/dig":
        if not rest:
            out("  " + dim("usage: /dig <question>"))
            return None
        return "CHAT:Research this thoroughly with deep_research (use several differently worded queries), then answer with numbered sources and say what you could not verify: " + rest
    elif cmd == "/abilities":
        cmd_abilities(ctx)
    elif cmd == "/verify":
        cmd_verify(ctx, arg)
    elif cmd == "/serve":
        cmd_serve(ctx, arg)
    elif cmd == "/open":
        cmd_open(ctx, rest)
    elif cmd == "/wakelock":
        cmd_wakelock(ctx, arg)
    elif cmd == "/overview":
        cmd_overview(ctx)
    elif cmd in ("/game", "/web"):
        if not rest:
            out("  " + dim("usage: %s <description>  (example: %s 3D zombie shooter, single HTML file)" % (cmd, cmd)))
            return None
        return "BUILD:Create %s: %s" % ("game" if cmd == "/game" else "website", rest)
    elif cmd == "/ask":
        if not rest:
            out("  " + dim("usage: /ask <question>"))
            return None
        return "CHAT:" + rest
    elif cmd in QUICK_PROMPTS:
        return "PROMPT:" + QUICK_PROMPTS[cmd] + rest
    elif cmd == "/explain":
        if not rest:
            out("  " + dim("usage: /explain <file>"))
            return None
        return "CHAT:Explain what @%s contains and how it works, briefly and clearly." % rest
    elif cmd == "/refactor":
        if not rest:
            out("  " + dim("usage: /refactor <file>"))
            return None
        return "PROMPT:Refactor @%s: tidy the structure, remove duplication, improve names, without changing behavior. Run or check the result." % rest
    elif cmd == "/version":
        out("  Axion Code v%s" % VERSION)
    else:
        out("  " + err("unknown command: %s" % cmd) + dim("  (type /help)"))
    return None
