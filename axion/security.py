"""File access boundaries: workspace, allowed folders and outside-access approval."""

import os
import re
from pathlib import Path

from axion.config import BG_DIR, BUNDLED_SKILLS_DIR, PROMPTS_DIR, SKILLS_DIR, TEMPLATES_DIR
from axion.state import ToolError
from axion.ui import bold, clip, dim, err, out, rl, tw


def inside(path, root):
    try:
        Path(path).relative_to(root)
        return True
    except ValueError:
        return False


def protected_roots():
    raw = ["/", "/storage", "/storage/emulated", "/storage/emulated/0", "/sdcard", "/system", "/vendor",
           "/data", "/data/data", "/etc", "/usr", "/bin", "/sbin", "/lib", "/proc", "/sys", "/dev",
           "/boot", "/root", "/home", str(Path.home()), os.environ.get("PREFIX", "")]
    return {os.path.realpath(r) for r in raw if r}


def system_prefixes():
    raw = ["/system", "/vendor", "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot", "/proc",
           "/sys", "/dev", "/apex", "/product", os.environ.get("PREFIX", "")]
    return [os.path.realpath(r) for r in raw if r]


def is_system_path(path):
    return any(inside(path, s) for s in system_prefixes())


def readable_extra():
    return [Path(os.path.realpath(str(p))) for p in (SKILLS_DIR, BG_DIR, PROMPTS_DIR, BUNDLED_SKILLS_DIR, TEMPLATES_DIR)]


def ask_outside(ctx, paths, action):
    """Warn and ask for permission to access paths outside the workspace. Returns (allowed, scope)."""
    paths = [Path(p) for p in paths]
    system = any(is_system_path(p) for p in paths)
    first = not ctx.warned_outside
    ctx.warned_outside = True
    bar = err("▍")
    out()
    out("  %s %s%s" % (bar, bold(err("WARNING")), dim("  access outside the workspace")))
    if first:
        for l in ("The AI is asking to touch locations outside the project folder.",
                  "This can read, change or delete data on your device or system.",
                  "Approve only if you understand the request and trust it."):
            out("  %s %s" % (bar, dim(l)))
    out("  %s %s %s" % (bar, dim("action"), clip(action, tw() - 14)))
    for p in paths[:4]:
        out("  %s %s %s" % (bar, dim("locations"), clip(str(p), tw() - 14)))
    if len(paths) > 4:
        out("  %s %s" % (bar, dim("… +%d more locations" % (len(paths) - 4))))
    if system:
        out("  %s %s" % (bar, err("SYSTEM area: high risk, can damage the device")))
        hint = "type 'yes' to continue, anything else denies ›"
    else:
        hint = "[y] once · [d] allow this folder · [n] deny ›"
    try:
        ans = input(rl("  %s %s " % (bar, dim(hint)))).strip().lower()
    except EOFError:
        return False, ""
    if system:
        return (ans == "yes"), "once"
    if ans in ("y", "ya", "yes"):
        return True, "once"
    if ans in ("d", "dir", "folder"):
        for p in paths:
            ctx.grants.add(Path(p) if Path(p).is_dir() else Path(p).parent)
        return True, "dir"
    return False, ""


def fs_path(ctx, p, action="access", write=False, destructive=False):
    raw = os.path.expanduser(str(p if p not in (None, "") else "."))
    path = Path(raw) if os.path.isabs(raw) else ctx.ws / raw
    path = Path(os.path.realpath(str(path)))
    if write and (str(path) in protected_roots() or (destructive and path == ctx.ws)):
        raise ToolError("protected path, cannot be changed or deleted: %s" % path)
    if inside(path, ctx.ws):
        return path
    if not write and any(inside(path, r) for r in readable_extra()):
        return path
    if ctx.full_access or any(inside(path, g) for g in ctx.grants):
        return path
    allowed, _scope = ask_outside(ctx, [path], action)
    if not allowed:
        raise ToolError("denied by the user: access outside the workspace (%s). Do not try another way; ask the user." % path)
    return path


SAFE_CMD_PATHS = ("/dev/null", "/dev/zero", "/dev/urandom", "/dev/random", "/dev/stdin", "/dev/stdout",
                  "/dev/stderr", "/dev/tty", "/tmp", "/usr/bin", "/usr/local/bin", "/usr/lib", "/usr/share",
                  "/usr/include", "/bin", "/sbin", "/proc/cpuinfo", "/proc/meminfo", "/proc/version",
                  "/etc/os-release", "/etc/hostname", "/etc/resolv.conf")


CMD_PATH_RE = re.compile(r"""(?<![\w./:$-])(~/[^\s'"`;|&<>()]*|/[^\s'"`;|&<>()]*|\$HOME[^\s'"`;|&<>()]*)""")


def outside_paths(ctx, cmd):
    safe = [os.path.realpath(s) for s in SAFE_CMD_PATHS]
    if os.environ.get("PREFIX"):
        safe.append(os.path.realpath(os.environ["PREFIX"]))
    found = []
    for m in CMD_PATH_RE.finditer(cmd):
        tok = m.group(1).rstrip(".,:)")
        tok = tok.replace("$HOME", str(Path.home()))
        tok = os.path.expanduser(tok)
        if not tok.startswith("/"):
            continue
        p = os.path.realpath(tok)
        if inside(p, ctx.ws) or any(inside(p, g) for g in ctx.grants) or any(inside(p, s) for s in safe):
            continue
        if p not in found:
            found.append(p)
    return found
