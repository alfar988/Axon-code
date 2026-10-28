"""Project tools: notes, plan, project overview, download, system info, preview, Python snippets."""

import json
import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from axion.config import PLAN_MAX_STEPS, UA
from axion.memory import hist_dir, read_notes_text, save_history, show_plan
from axion.security import ask_outside, fs_path, inside, outside_paths
from axion.state import ask, ToolError, track
from axion.tools.archive import progress_done
from axion.tools.files import iter_files, t_list_dir
from axion.tools.registry import I, L, S, tool
from axion.tools.shell import run_status_line, shell_run, start_background
from axion.ui import acc, clip, IS_TTY, tw
from axion.util import as_items, cap, denied, human_size, item_text, rel, to_int
from axion.webutil import norm_url


@tool("save_note", "Save important notes or research to workspace memory (history/notes.md) so they survive a model switch.",
      {"title": S("short title"), "content": S("short, dense content: facts, versions, CDN URLs, APIs, decisions, sources")},
      ["title", "content"])
def t_save_note(a, ctx):
    d = hist_dir(ctx)
    d.mkdir(parents=True, exist_ok=True)
    with open(str(d / "notes.md"), "a", encoding="utf-8") as f:
        f.write("## [%s] %s\n%s\n\n" % (time.strftime("%Y-%m-%d %H:%M"), a.get("title", "note"), a.get("content", "")))
    return "OK: note saved: %s" % a.get("title", "note")


@tool("read_notes", "Read the notes and research saved in workspace memory (history/notes.md).", {})
def t_read_notes(a, ctx):
    return read_notes_text(ctx, 9000) or "(no notes yet)"


@tool("submit_plan", "Submit the final plan (planning phase). Call it once, after research is done.",
      {"title": S("project title"), "summary": S("what will be built, what will differ from the template, and the assumptions"),
       "features": L("concrete, testable features, including at least three that go beyond a template"),
       "architecture": S("file/module structure and how the parts connect"),
       "files": {"type": "array", "description": "list of files", "items": {"type": "object", "properties": {
           "path": {"type": "string"}, "purpose": {"type": "string"}}}},
       "steps": {"type": "array", "description": "ordered work steps (6-14), each a short sentence", "items": {"type": "object", "properties": {
           "title": {"type": "string"}, "details": {"type": "string"}}, "required": ["title"]}},
       "research_notes": S("key research findings with source URLs"), "verification": L("how to check each important feature")},
      ["title", "summary", "steps"])
def t_submit_plan(a, ctx):
    steps = []
    for s in as_items(a.get("steps")):
        if isinstance(s, dict):
            title = item_text(s, ("title", "step", "name", "content", "task", "description", "text"))
            details = str(s.get("details") or s.get("detail") or "")
            details = "" if details == title else details
        else:
            title, details = str(s), ""
        if len(title) >= 3:
            steps.append({"title": clip(title, 160), "details": clip(details, 400)})
    steps = steps[:PLAN_MAX_STEPS]
    if not steps:
        raise ToolError("steps is empty: provide the work steps as a list of short sentences")
    files = []
    for f in as_items(a.get("files")):
        if isinstance(f, dict):
            path, purpose = item_text(f, ("path", "file", "name")), str(f.get("purpose") or f.get("description") or "")
        else:
            path, purpose = str(f), ""
        if len(path) >= 2:
            files.append({"path": path, "purpose": purpose})

    def texts(v):
        return [clip(item_text(x), 240) for x in as_items(v) if item_text(x)]

    ctx.plan = {"title": clip(str(a.get("title") or "Project"), 120), "summary": str(a.get("summary") or ""),
                "features": texts(a.get("features")), "architecture": str(a.get("architecture") or ""), "files": files,
                "steps": steps, "research_notes": str(a.get("research_notes") or ""), "verification": texts(a.get("verification"))}
    ctx.todos = [{"content": s["title"], "status": "pending"} for s in steps]
    show_plan(ctx, ctx.plan)
    save_history(ctx, "plan")
    return ("OK: plan saved (%d steps) in history/plan.md. START BUILDING NOW: do step 1 and continue in order, keep todo updated. "
            "When a template fits, start from it with use_template, then customize it substantially (new visuals, new mechanics or "
            "sections, real content): a recolored template is rejected. Write code in parts (write_file, then append_file), then "
            "verify and run it." % len(steps))


KEY_FILES = ("README.md", "readme.md", "package.json", "requirements.txt", "pyproject.toml", "build.gradle",
             "build.gradle.kts", "settings.gradle", "pubspec.yaml", "Cargo.toml", "go.mod", "pom.xml", "Makefile",
             "CMakeLists.txt", "index.html", "main.py", "app.py", "manifest.json", "AXION.md", "AXION.md")


PROJECT_TYPES = (("build.gradle", "Android/Gradle"), ("build.gradle.kts", "Android/Gradle"), ("package.json", "Node.js"),
                 ("requirements.txt", "Python"), ("pyproject.toml", "Python"), ("pubspec.yaml", "Flutter"),
                 ("Cargo.toml", "Rust"), ("go.mod", "Go"), ("pom.xml", "Java/Maven"), ("CMakeLists.txt", "C/C++ CMake"),
                 ("index.html", "Static web"), ("project.rbxlx", "Roblox"), ("default.project.json", "Roblox (Rojo)"))


def overview_text(ctx, root=None, limit=6000):
    root = Path(root or ctx.ws)
    cache = getattr(ctx, "overview_cache", None)
    if cache and cache[0] == str(root) and time.time() - cache[1] < 90:
        return cache[2]
    L_ = ["Workspace: %s" % root]
    ext, total, size = {}, 0, 0
    for fp in iter_files(root):
        total += 1
        try:
            size += fp.stat().st_size
        except OSError:
            pass
        ext[fp.suffix.lower() or "(no extension)"] = ext.get(fp.suffix.lower() or "(no extension)", 0) + 1
        if total >= 6000:
            break
    L_.append("Files: %d%s, size %s" % (total, "+" if total >= 6000 else "", human_size(size)))
    if ext:
        L_.append("Jenis: " + ", ".join("%s×%d" % (k, v) for k, v in sorted(ext.items(), key=lambda kv: -kv[1])[:8]))
    types = sorted({label for fn, label in PROJECT_TYPES if (root / fn).exists()})
    L_.append("Project type: " + (", ".join(types) if types else "not detected / empty folder"))
    try:
        tree = t_list_dir({"path": str(root), "depth": 2}, ctx)
    except ToolError:
        tree = "(unreadable)"
    L_.append("\nStruktur:\n" + "\n".join(tree.splitlines()[:60]))
    shown = 0
    for kf in KEY_FILES:
        fp = root / kf
        if fp.is_file() and shown < 4:
            try:
                head = "\n".join(fp.read_text(encoding="utf-8", errors="replace").splitlines()[:22])[:1200]
            except OSError:
                continue
            L_.append("\n--- %s ---\n%s" % (kf, head))
            shown += 1
    if (root / ".git").exists() and shutil.which("git"):
        try:
            r = subprocess.run(["git", "-C", str(root), "status", "--short", "-b"], capture_output=True, text=True, timeout=6)
            L_.append("\n--- git ---\n" + "\n".join(r.stdout.splitlines()[:10]))
        except Exception:
            pass
    text = cap("\n".join(L_), limit)
    ctx.overview_cache = (str(root), time.time(), text)
    return text


@tool("project_overview", "Quick project summary of the workspace: structure, file types, project type, key files, git.",
      {"path": S("folder, default workspace")})
def t_project_overview(a, ctx):
    return overview_text(ctx, fs_path(ctx, a.get("path") or ".", "scanning the project"))


@tool("download_file", "Download a file from a URL into the workspace (JS libraries, images, assets, datasets). Max 100 MB.",
      {"url": S("file URL"), "path": S("destination path in the workspace")}, ["url", "path"])
def t_download_file(a, ctx):
    url = norm_url(a.get("url"))
    dest = fs_path(ctx, a.get("path"), "downloading a file", write=True)
    if dest.is_dir():
        dest = dest / (os.path.basename(urllib.parse.urlparse(url).path) or "download.bin")
    okk, why = ask(ctx, "Download", "%s  →  %s" % (clip(url, tw() - 24), rel(ctx, dest)),
                   ["Internet source: make sure you trust it."])
    if not okk:
        return denied(why)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
    except Exception as e:
        raise ToolError("download failed: %s" % e)
    total = int(resp.headers.get("Content-Length") or 0)
    if total > 100 * 1024 * 1024:
        resp.close()
        raise ToolError("file too large (%s), limit is 100 MB" % human_size(total))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(dest) + ".part")
    done = 0
    try:
        with open(str(tmp), "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                done += len(chunk)
                if done > 100 * 1024 * 1024:
                    raise ToolError("exceeded 100 MB, cancelled")
                f.write(chunk)
                if IS_TTY:
                    sys.stdout.write("\r\u001b[K  %s downloading %s%s" % (acc("⠿"), human_size(done),
                                                                      (" / " + human_size(total)) if total else ""))
                    sys.stdout.flush()
        os.replace(str(tmp), str(dest))
    except ToolError:
        raise
    except Exception as e:
        raise ToolError("download failed: %s" % e)
    finally:
        resp.close()
        progress_done()
        try:
            tmp.unlink()
        except OSError:
            pass
    ctx.undo.append({"t": "copy", "dst": dest})
    track(ctx, "+", dest, human_size(done))
    return "OK: downloaded %s (%s)" % (rel(ctx, dest), human_size(done))


def sysinfo_text(ctx):
    L_ = ["OS: %s" % platform.platform(), "Python: %s" % platform.python_version(), "CPU: %s core" % os.cpu_count()]
    try:
        mem = {}
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            mem[k] = int(v.split()[0]) * 1024
        L_.append("RAM: total %s, available %s" % (human_size(mem["MemTotal"]), human_size(mem.get("MemAvailable", 0))))
    except Exception:
        pass
    for label, path in (("workspace", str(ctx.ws)), ("device storage", "/storage/emulated/0")):
        try:
            du = shutil.disk_usage(path)
            L_.append("Disk %s: %s free of %s" % (label, human_size(du.free), human_size(du.total)))
        except Exception:
            pass
    bat = shutil.which("termux-battery-status")
    if bat:
        try:
            r = subprocess.run([bat], capture_output=True, text=True, timeout=5)
            j = json.loads(r.stdout)
            L_.append("Battery: %s%% (%s)" % (j.get("percentage"), j.get("status")))
        except Exception:
            pass
    tools_ = ["node", "npm", "git", "java", "gradle", "python3", "pip", "zip", "unzip", "7z", "clang", "go", "cargo", "termux-open"]
    L_.append("Tools: " + ", ".join("%s%s" % (t, "✓" if shutil.which(t) else "✗") for t in tools_))
    return "\n".join(L_)


@tool("system_info", "Device info: RAM, storage, battery, installed tools (node/git/java/python). Asks the user for permission.", {})
def t_system_info(a, ctx):
    if not ctx.sysinfo_ok and not ctx.full_access:
        okk, why = ask(ctx, "System info", "reading RAM, storage, battery and the tool list",
                       ["This only READS device information; it changes nothing."], force=True)
        if not okk:
            return denied(why)
        ctx.sysinfo_ok = True
    return sysinfo_text(ctx)


def free_port(start=8000, end=8020):
    for port in range(start, end):
        s = socket.socket()
        s.settimeout(0.2)
        try:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        finally:
            s.close()
    return None


def start_preview(ctx, rel_path="", port=None):
    base_port = None
    for v in ctx.bg.values():
        if v.get("preview") and v["proc"].poll() is None:
            base_port = v["preview"]
            break
    if base_port is None:
        port = port or free_port()
        if not port:
            raise ToolError("no free port in 8000-8019")
        py = shutil.which("python3") or sys.executable
        bid, alive, _log, tail = start_background(ctx, "%s -m http.server %d --bind 127.0.0.1" % (shlex.quote(py), port))
        ctx.bg[bid]["preview"] = port
        if not alive:
            raise ToolError("preview server failed to start: %s" % tail[-200:])
        base_port = port
    url = "http://127.0.0.1:%d/%s" % (base_port, urllib.parse.quote(rel_path.lstrip("/")))
    opened = False
    opener = shutil.which("termux-open-url")
    if opener:
        try:
            subprocess.run([opener, url], timeout=6, capture_output=True)
            opened = True
        except Exception:
            pass
    return url, opened


@tool("preview_web", "Start a local server to view a web page or game in the browser (http://127.0.0.1:PORT). path = an HTML file in the workspace.", {"path": S("file/folder di workspace, mis. index.html")})
def t_preview_web(a, ctx):
    p = fs_path(ctx, a.get("path") or ".", "preview web")
    if not inside(p, ctx.ws):
        raise ToolError("preview is only available for files inside the workspace")
    okk, why = ask(ctx, "Preview", "local server on 127.0.0.1 for %s" % rel(ctx, p), ["Reachable only from this device."])
    if not okk:
        return denied(why)
    url, opened = start_preview(ctx, rel(ctx, p) if p != ctx.ws else "")
    return "OK: preview running at %s%s. Stop it with /ps then /kill." % (url, " (opened in the browser)" if opened else "")


@tool("run_python", "Run a throwaway Python snippet (calculations, data handling, quick experiments). Output streams live.",
      {"code": S("Python code"), "timeout": I("seconds, default 60, max 600")}, ["code"])
def t_run_python(a, ctx):
    code = str(a.get("code", ""))
    if not code.strip():
        raise ToolError("empty code")
    timeout = max(1, min(to_int(a.get("timeout"), 60), 600))
    lines = code.splitlines()
    outs = [] if ctx.full_access else outside_paths(ctx, code)
    if outs:
        okk, _ = ask_outside(ctx, outs, "running Python code that references the locations above")
        if not okk:
            return denied("access outside the workspace is not allowed")
    else:
        okk, why = ask(ctx, "Python", clip(lines[0], tw() - 14), lines[1:6] or None)
        if not okk:
            return denied(why)
    d = hist_dir(ctx) / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    f = d / ("snippet_%d.py" % (int(time.time() * 1000) % 100000000))
    f.write_text(code, encoding="utf-8")
    py = shutil.which("python3") or sys.executable
    try:
        res = shell_run("%s %s" % (shlex.quote(py), shlex.quote(str(f))), ctx.ws, timeout, live=True)
    finally:
        try:
            f.unlink()
        except OSError:
            pass
    run_status_line(res, timeout)
    text = cap(res["text"].strip(), 12000) or "(no output)"
    return "%s\n[exit code %s · %.1fs]" % (text, res["code"], res["secs"])
