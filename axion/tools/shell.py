"""Shell tools: commands, background processes and process management."""

import codecs
import os
import re
import shutil
import subprocess
import sys
import threading
import time

from axion.config import BG_DIR
from axion.security import ask_outside, outside_paths
from axion.state import ask, ToolError
from axion.tools.registry import B, I, S, tool
from axion.ui import (
    C_ERR, C_OK, C_TEXT, C_WARN, clip, dim, err, faint, IS_TTY, ok, out, paint, short_path, tw,
    warn,
)
from axion.util import cap, denied, is_dangerous, to_int


# --- tools: shell (output streams live) -----------------------------------
def shell_env():
    env = dict(os.environ)
    env.update({"PYTHONUNBUFFERED": "1", "NO_COLOR": "1", "DEBIAN_FRONTEND": "noninteractive",
                "GIT_TERMINAL_PROMPT": "0", "PAGER": "cat", "GIT_PAGER": "cat"})
    env.setdefault("TERM", "xterm")
    return env


def kill_group(p):
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(p.pid), 9)
        else:
            p.kill()
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


class LiveOut:
    """Stream process output live with a gutter and status colors."""
    ERR = re.compile(r"\b(error|errors|failed|failure|exception|traceback|fatal|denied)\b", re.I)
    WRN = re.compile(r"\b(warn|warning|deprecated)\b", re.I)
    GOOD = re.compile(r"\b(success|successful|passed|complete|completed|done)\b", re.I)

    def __init__(self, limit=400):
        self.limit = limit
        self.n = 0
        self.partial = ""
        self.transient = False

    def _clear(self):
        if self.transient:
            sys.stdout.write("\r\033[K")
            self.transient = False

    def _emit(self, line):
        self.n += 1
        self._clear()
        if self.n <= self.limit:
            t = clip(line.expandtabs(4), tw() - 6)
            col = C_ERR if self.ERR.search(line) else C_WARN if self.WRN.search(line) \
                else C_OK if self.GOOD.search(line) else C_TEXT
            sys.stdout.write(faint("  │ ") + paint(t, *col) + "\n")
            sys.stdout.flush()
        elif IS_TTY:
            sys.stdout.write("\r\033[K" + faint("  │ ") + dim("… %d lines (Ctrl+C to cancel)" % self.n))
            sys.stdout.flush()
            self.transient = True

    def feed(self, text):
        self.partial += text
        while "\n" in self.partial:
            line, self.partial = self.partial.split("\n", 1)
            self._emit(line.rstrip("\r").rsplit("\r", 1)[-1])
        if IS_TTY and "\r" in self.partial:
            seg = self.partial.rsplit("\r", 1)[-1]
            if seg.strip():
                self._clear()
                sys.stdout.write("\r\033[K" + faint("  │ ") + dim(clip(seg, tw() - 6)))
                sys.stdout.flush()
                self.transient = True

    def finish(self):
        if self.partial.strip():
            self._emit(self.partial.rsplit("\r", 1)[-1])
        self.partial = ""
        self._clear()
        if self.n > self.limit:
            out(faint("  │ ") + dim("(%d lines not shown; the full log was sent to the AI)" % (self.n - self.limit)))
        sys.stdout.flush()


def shell_run(cmd, cwd, timeout=120, live=True):
    sh = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
    kw = {"start_new_session": True} if hasattr(os, "setsid") else {}
    p = subprocess.Popen([sh, "-c", cmd], cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, env=shell_env(), **kw)
    flag = {"timeout": False}

    def on_timeout():
        flag["timeout"] = True
        kill_group(p)

    timer = threading.Timer(timeout, on_timeout)
    timer.daemon = True
    timer.start()
    dec = codecs.getincrementaldecoder("utf-8")("replace")
    lo = LiveOut() if live else None
    chunks = []
    t0 = time.time()
    fd = p.stdout.fileno()
    try:
        while True:
            data = os.read(fd, 4096)
            if not data:
                break
            txt = dec.decode(data)
            chunks.append(txt)
            if lo:
                lo.feed(txt)
        tail = dec.decode(b"", final=True)
        if tail:
            chunks.append(tail)
            if lo:
                lo.feed(tail)
        p.wait()
    except KeyboardInterrupt:
        kill_group(p)
        if lo:
            lo.finish()
        raise
    finally:
        timer.cancel()
        try:
            p.stdout.close()
        except Exception:
            pass
    if lo:
        lo.finish()
    return {"text": "".join(chunks), "code": p.returncode, "timeout": flag["timeout"], "secs": time.time() - t0}


def run_status_line(res, timeout=None):
    secs = res["secs"]
    if res["timeout"]:
        out("  " + warn("⏱ timeout") + dim(" · process stopped after %ds" % (timeout or secs)))
    elif res["code"] == 0:
        out("  " + ok("✓ done") + dim(" · %.1fs · exit 0" % secs))
    else:
        out("  " + err("✗ failed") + dim(" · exit %s · %.1fs" % (res["code"], secs)))


def start_background(ctx, cmd):
    BG_DIR.mkdir(parents=True, exist_ok=True)
    bid = "%d" % (len(ctx.bg) + 1)
    while bid in ctx.bg:
        bid = str(int(bid) + 1)
    log = BG_DIR / ("%s-%d.log" % (bid, int(time.time())))
    f = open(str(log), "wb")
    sh = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
    kw = {"start_new_session": True} if hasattr(os, "setsid") else {}
    p = subprocess.Popen([sh, "-c", cmd], cwd=str(ctx.ws), stdin=subprocess.DEVNULL, stdout=f,
                         stderr=subprocess.STDOUT, env=shell_env(), **kw)
    ctx.bg[bid] = {"pid": p.pid, "cmd": cmd, "log": log, "proc": p, "t0": time.time()}
    time.sleep(1.5)
    alive = p.poll() is None
    try:
        tail = log.read_text(encoding="utf-8", errors="replace")[-1500:]
    except OSError:
        tail = ""
    return bid, alive, log, tail


@tool("run_shell", "Run a shell command in the workspace (python, git, pkg/apt, pip, npm, gradle, ...). Output streams LIVE to the user. Non-interactive (stdin is empty): use -y/--yes flags. timeout is in seconds (default 120; long builds 900-1800; max 3600). background=true for servers and long-running processes (inspect them with manage_process).",
      {"command": S("shell command"), "timeout": I("seconds, default 120, max 3600"),
       "background": B("run in the background")}, ["command"])
def t_run_shell(a, ctx):
    cmd = str(a.get("command", "")).strip()
    if not cmd:
        raise ToolError("empty command")
    timeout = max(1, min(to_int(a.get("timeout"), 120), 3600))
    bg = bool(a.get("background"))
    danger = is_dangerous(cmd)
    outs = [] if ctx.full_access else outside_paths(ctx, cmd)
    lines = cmd.splitlines()
    approved_outside = False
    if outs:
        okk, _ = ask_outside(ctx, outs, "running a command that touches the locations above")
        if not okk:
            return denied("access outside the workspace is not allowed")
        approved_outside = True
    if danger:
        okk, why = ask(ctx, "DANGEROUS COMMAND", clip(lines[0], tw() - 22), lines[1:] or None, level="danger")
        if not okk:
            return denied(why)
    elif not approved_outside:
        okk, why = ask(ctx, "Bash", clip(lines[0], tw() - 12), lines[1:] or None)
        if not okk:
            return denied(why)
    if bg:
        bid, alive, log, tail = start_background(ctx, cmd)
        out("  %s %s" % (ok("✓ running in the background") if alive else err("✗ exited immediately"),
                         dim("· id %s · log %s" % (bid, short_path(log)))))
        return ("OK: background process id=%s pid=%s %s. Log: %s\n--- first log lines ---\n%s"
                % (bid, ctx.bg[bid]["pid"], "RUNNING" if alive else "STOPPED", log, tail.strip() or "(empty)"))
    res = shell_run(cmd, ctx.ws, timeout, live=True)
    run_status_line(res, timeout)
    text = cap(res["text"].strip(), 12000) or "(no output)"
    if res["timeout"]:
        text += "\n[TIMEOUT after %ds, process stopped]" % timeout
    return "%s\n[exit code %s · %.1fs]" % (text, res["code"], res["secs"])


@tool("manage_process", "Manage background processes started with run_shell background=true.",
      {"action": S("list | logs | stop", enum=["list", "logs", "stop"]), "id": S("process id")}, ["action"])
def t_manage_process(a, ctx):
    act = a.get("action")
    if act == "list":
        if not ctx.bg:
            return "(no background processes)"
        return "\n".join("id=%s pid=%s %s · %s" % (k, v["pid"], "running" if v["proc"].poll() is None else "stopped",
                                                    clip(v["cmd"], 60)) for k, v in ctx.bg.items())
    pid = str(a.get("id", ""))
    if pid not in ctx.bg:
        raise ToolError("unknown process id. Use action=list")
    v = ctx.bg[pid]
    if act == "logs":
        return cap(v["log"].read_text(encoding="utf-8", errors="replace")[-8000:]) or "(empty log)"
    if act == "stop":
        kill_group(v["proc"])
        return "OK: process %s stopped" % pid
    raise ToolError("unknown action")
