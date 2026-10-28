"""Interactive input, banner and main()."""

import argparse
import atexit
import glob
import os
import select
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from axion.agent import run_turn
from axion.client import NETSTATE
from axion.commands import cmd_resume, handle_command, SLASH
from axion.config import APP_DIR, DEFAULT_MODEL, HISTORY_FILE, HOME_DIR, ROUTER_MODEL, SKILLS_DIR, VERSION
from axion.memory import log_event, peek_history, repair_history, save_history
from axion.models import ensure_models, models_cmd, rotation_enabled
from axion.sessions import load_session, save_session
from axion.state import Ctx, ensure_key, is_free_model, load_config, req_today, save_config
from axion.tools.shell import run_status_line, shell_run
from axion.ui import (
    acc, bold, C_USER, clip, dim, err, faint, fit_path, gradient, HAS_READLINE, LOGO, ok, out,
    paint, readline, rl, rule, short_model, tw, vlen, warn,
)


CTX = None


def completer(text, state):
    try:
        buf = readline.get_line_buffer()
        opts = []
        if buf.startswith("/") and " " not in buf.strip():
            opts = [c for c in SLASH if c.startswith(text)]
        elif text.startswith("@") and CTX is not None:
            pat = str(CTX.ws / text[1:]) + "*"
            for f in sorted(glob.glob(pat))[:50]:
                opts.append("@" + os.path.relpath(f, str(CTX.ws)) + ("/" if os.path.isdir(f) else ""))
        return opts[state] if state < len(opts) else None
    except Exception:
        return None


def drain_paste():
    """Collect the remaining lines of a multi-line paste so they are not sent separately."""
    extra = []
    if not sys.stdin.isatty() or os.name == "nt":
        return extra
    try:
        while select.select([sys.stdin], [], [], 0.03)[0]:
            l = sys.stdin.readline()
            if not l:
                break
            extra.append(l.rstrip("\n"))
    except Exception:
        pass
    return extra


def mode_chip(ctx):
    if ctx.full_access:
        return err("full access"), "full access"
    if ctx.auto:
        return warn("auto"), "auto"
    return ok("ask"), "ask"


def status_line(ctx):
    """One status line that always fits the screen: workspace · model · permissions · requests."""
    budget = tw() - 5
    chip, chip_plain = mode_chip(ctx)
    rot = " ⇄" if ctx.override and ctx.override[0] == ctx.cfg.get("model", DEFAULT_MODEL) else ""
    model_s = clip(short_model(ctx.cur_model()) + rot, 22)
    req = ("req %d" % req_today(ctx)) if is_free_model(ctx.cur_model()) else ""
    with_req = bool(req)

    def total(ws_s):
        items = [ws_s, model_s, chip_plain] + ([req] if with_req else [])
        return sum(vlen(i) for i in items) + 3 * (len(items) - 1)

    ws_len = 30
    while True:
        ws_s = fit_path(ctx.ws, ws_len)
        if total(ws_s) <= budget:
            break
        if with_req and ws_len <= 14:
            with_req = False
        elif ws_len > 8:
            ws_len -= 2
        elif vlen(model_s) > 10:
            model_s = clip(model_s, vlen(model_s) - 2)
        else:
            break
    parts = [dim(ws_s), dim(model_s), chip] + ([dim(req)] if with_req else [])
    return faint("  ╭ ") + faint(" · ").join(parts)


def read_input(ctx):
    out()
    out(status_line(ctx))
    line = input(rl(faint("  ╰") + paint("❯ ", *C_USER)))
    if line.strip() == '"""':
        lines = []
        while True:
            l = input(rl(faint("  … ")))
            if l.strip() == '"""':
                break
            lines.append(l)
        return "\n".join(lines)
    extra = drain_paste()
    if extra:
        line = "\n".join([line] + extra)
        out("  " + dim("(pasted %d lines)" % (len(extra) + 1)))
    while line.endswith("\\"):
        line = line[:-1] + "\n" + input(rl(faint("  … ")))
    return line


def run_user_shell(ctx, cmd):
    if not cmd.strip():
        return
    try:
        res = shell_run(cmd, ctx.ws, 600, live=True)
    except KeyboardInterrupt:
        out("  " + dim("(cancelled)"))
        return
    run_status_line(res, 600)


def banner(ctx):
    w = min(tw(), 60)
    chip, _ = mode_chip(ctx)
    side = (bold("C O D E") + dim("  v" + VERSION), dim("AI coding agent for the terminal"))
    out()
    for i, row in enumerate(LOGO):
        out("  " + gradient(row) + (("    " + side[i]) if w >= 44 else ""))
    out(rule())
    out("  " + dim("workspace  ") + fit_path(ctx.ws, w - 14))
    out("  " + dim("model      ") + clip(ctx.cur_model(), w - 14))
    out("  " + dim("fallback   ") + (ok("on") + dim(" · switches model automatically on errors") if rotation_enabled(ctx) else warn("off")))
    out("  " + dim("access     ") + chip + dim(" · outside the workspace: ask"))
    out("  " + dim("memory     ") + "history/" + dim(" (automatic)"))
    out(rule())
    out("  " + dim("Describe what to build or fix.  /help · /skills · /models"))
    if ctx.cfg.get("model") == ROUTER_MODEL:
        out("  " + warn("!") + dim(" the random router gives inconsistent quality"))
        out("    " + dim("use /models to pick a fixed model"))


def start_wakelock(ctx):
    exe = shutil.which("termux-wake-lock")
    if not exe or ctx.cfg.get("wakelock", True) is False:
        return False
    try:
        subprocess.run([exe], capture_output=True, timeout=5)
    except Exception:
        return False

    def release():
        off = shutil.which("termux-wake-unlock")
        if off:
            try:
                subprocess.run([off], capture_output=True, timeout=5)
            except Exception:
                pass
    atexit.register(release)
    return True


def migrate_old_home():
    """Carry settings over from an older install (~/.axion or ~/.kode) into ~/.axion, once."""
    if HOME_DIR.exists() or os.environ.get("AXION_HOME") or os.environ.get("AXON_HOME"):
        return
    for old in (Path.home() / ".axon", Path.home() / ".kode"):
        if old.is_dir():
            try:
                shutil.copytree(str(old), str(HOME_DIR))
            except Exception:
                pass
            return


def main():
    global CTX
    ap = argparse.ArgumentParser(prog="axion", description="Axion Code - AI coding agent for the terminal (OpenRouter)")
    ap.add_argument("workspace", nargs="?", help="workspace folder (default: current directory, or ~/workspace when run from HOME)")
    ap.add_argument("-m", "--model", help="id model OpenRouter")
    ap.add_argument("-p", "--prompt", help="one-shot mode: send a single request, then exit")
    ap.add_argument("-c", "--continue", dest="cont", action="store_true", help="continue the last session")
    ap.add_argument("--auto", action="store_true", help="approve edits and commands inside the workspace automatically")
    ap.add_argument("--setup", action="store_true", help="enter the API key again")
    ap.add_argument("--version", action="version", version="Axion Code " + VERSION)
    args = ap.parse_args()

    migrate_old_home()
    for d in (HOME_DIR, SKILLS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    cfg.setdefault("model", DEFAULT_MODEL)
    NETSTATE["ipv4_only"] = bool(cfg.get("ipv4_only"))
    if args.model:
        cfg["model"] = args.model
        cfg["model_chosen"] = True

    if args.workspace:
        ws = Path(args.workspace).expanduser()
    else:
        cwd = Path.cwd().resolve()
        ws = (Path.home() / "workspace") if cwd in (Path.home().resolve(), APP_DIR.resolve()) else cwd
    ws.mkdir(parents=True, exist_ok=True)

    ctx = Ctx(cfg, ws)
    CTX = ctx
    ctx.auto = args.auto
    start_wakelock(ctx)

    if HAS_READLINE:
        try:
            if HISTORY_FILE.exists():
                readline.read_history_file(str(HISTORY_FILE))
            readline.set_history_length(500)
            readline.set_completer_delims(" \t\n")
            readline.set_completer(completer)
            readline.parse_and_bind("tab: complete")
        except Exception:
            pass

    out()
    if not ensure_key(ctx, force=args.setup):
        out("  " + err("An API key is required. Run again and paste your OpenRouter key."))
        return 1
    threading.Thread(target=ensure_models, args=(ctx,), daemon=True).start()
    if not cfg.get("model_chosen") and not args.prompt and sys.stdin.isatty():
        models_cmd(ctx, interactive=True)
    out()
    banner(ctx)

    first_prompt = None
    st = peek_history(ctx)
    if st and st.get("messages") and not args.prompt and not args.cont and sys.stdin.isatty():
        pend = [t for t in (st.get("todos") or []) if t.get("status") != "completed"]
        if pend or str(st.get("reason", "")).startswith(("error", "empty", "limit", "rotation")):
            out()
            out("  " + warn("↺ ") + "unfinished work found in history" +
                dim(" (%d messages%s)" % (len(st["messages"]), (", plan: " + st["plan"]["title"]) if st.get("plan") else "")))
            try:
                ans = input(rl("  " + acc("▍") + " " + dim("resume now? [Y/n] › "))).strip().lower()
            except EOFError:
                ans = "n"
            if ans in ("", "y", "ya", "yes"):
                r = cmd_resume(ctx)
                if r:
                    first_prompt = r[7:]

    if args.cont and load_session(ctx, "last"):
        out("  " + ok("✓ resumed the last session (%d messages)" % len(ctx.messages)))

    if args.prompt:
        try:
            run_turn(ctx, args.prompt)
        except KeyboardInterrupt:
            out("\n  " + dim("(cancelled)"))
        return 0

    last_int = 0.0
    while True:
        if first_prompt:
            line, first_prompt = first_prompt, None
        else:
            try:
                line = read_input(ctx)
            except EOFError:
                out()
                break
            except KeyboardInterrupt:
                now = time.time()
                if now - last_int < 2:
                    out()
                    break
                last_int = now
                out("\n  " + dim("(press Ctrl+C again or Ctrl+D to exit)"))
                continue
        line = line.strip()
        if not line:
            continue
        if line.startswith("!"):
            run_user_shell(ctx, line[1:])
            continue
        if line.startswith("/") and not line.startswith("//"):
            res = handle_command(ctx, line)
            if res == "exit":
                break
            if isinstance(res, str) and res.startswith("BUILD:"):
                ctx.force_intent, line = "build", res[6:]
            elif isinstance(res, str) and res.startswith("CHAT:"):
                ctx.force_intent, line = "chat", res[5:]
            elif isinstance(res, str) and res.startswith("PROMPT:"):
                line = res[7:]
            else:
                continue
        elif line in ("exit", "quit"):
            break
        try:
            run_turn(ctx, line)
        except KeyboardInterrupt:
            repair_history(ctx)
            out("\n  " + dim("(cancelled)"))
        except Exception as e:  # keep the session alive
            repair_history(ctx)
            log_event(ctx, "unexpected error: %s: %s" % (type(e).__name__, e))
            save_history(ctx, "error")
            out("  " + err("✗ unexpected error: %s: %s" % (type(e).__name__, e)))
        try:
            save_session(ctx, "last")
        except Exception:
            pass

    if HAS_READLINE:
        try:
            readline.write_history_file(str(HISTORY_FILE))
        except Exception:
            pass
    try:
        save_session(ctx, "last")
        save_config(ctx.cfg)
        save_history(ctx, "exit")
    except Exception:
        pass
    for v in ctx.bg.values():
        if v["proc"].poll() is None:
            out("  " + dim("background process still running: pid %s (stop it with: kill %s)" % (v["pid"], v["pid"])))
    out("  " + dim("goodbye · memory saved in history/"))
    return 0
