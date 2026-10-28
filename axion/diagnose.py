"""Failure diagnosis: turns raw errors into concrete fixes the model applies on its own."""

import re

from axion.ui import clip


# ---------------------------------------------------------------------------
#  Failure diagnosis: turns raw error output into concrete next steps.
#  Appended to failing tool results so the model fixes the problem itself
#  instead of stopping to ask, or repeating the same mistake.
# ---------------------------------------------------------------------------
PIP_NAMES = {"cv2": "opencv-python", "PIL": "pillow", "yaml": "pyyaml", "bs4": "beautifulsoup4", "sklearn": "scikit-learn",
             "dotenv": "python-dotenv", "telegram": "python-telegram-bot", "discord": "discord.py", "jwt": "pyjwt",
             "serial": "pyserial", "dateutil": "python-dateutil", "Crypto": "pycryptodome", "flask_cors": "flask-cors",
             "skimage": "scikit-image", "attr": "attrs", "magic": "python-magic", "fitz": "pymupdf", "docx": "python-docx"}

# (regex on the lowercased output, hint template). {1},{2} are regex groups.
HINTS = [
    (r"modulenotfounderror: no module named ['\"]([\w.]+)['\"]",
     "Python module '{1}' is not installed (or the name/path is wrong). Install it with `pip install {pip}`. If pip refuses "
     "(externally-managed-environment) use a venv or add --break-system-packages. If '{1}' is your own file, check the filename "
     "and run from the folder that contains it."),
    (r"importerror: cannot import name ['\"](\w+)['\"] from ['\"]([\w.]+)['\"]",
     "'{1}' does not exist in '{2}'. Check the installed version (`pip show {2}`) and the real name; circular imports cause this too."),
    (r"externally-managed-environment",
     "pip is blocked system-wide here. Create a venv (`python -m venv .venv && . .venv/bin/activate`) or add --break-system-packages (fine on Termux)."),
    (r"(indentationerror|taberror)",
     "Fix the indentation: 4 spaces everywhere, no tabs. read_file the lines around the reported line before editing."),
    (r"syntaxerror",
     "Syntax error at the reported line. read_file around it; usual causes are an unclosed bracket or quote on an earlier line, a missing colon, or a truncated file."),
    (r"nameerror: name ['\"](\w+)['\"] is not defined",
     "'{1}' is used but never defined or imported. Define it, import it, or fix the spelling (search_files for '{1}')."),
    (r"attributeerror: ['\"]?([\w.]+)['\"]? (?:object|module) has no attribute ['\"](\w+)['\"]",
     "'{1}' has no attribute '{2}'. Check what it really provides (read the code or the library docs); do not guess names."),
    (r"typeerror: .*(?:missing|takes|expected) .*argument",
     "A call has the wrong number of arguments. Read the function definition and fix the call site."),
    (r"keyerror: (.+)", "Key {1} is missing. Use .get() with a default, or inspect the data first."),
    (r"indexerror: .*out of range", "An index is outside the list. Check len() before indexing, and for off-by-one errors."),
    (r"(jsondecodeerror|expecting value: line 1 column 1)",
     "The text is not valid JSON (it may be empty or an HTML error page). Print the raw response before parsing it."),
    (r"(unicodedecodeerror|codec can't (?:decode|encode))", "Encoding problem: open files with encoding='utf-8', errors='replace'."),
    (r"(recursionerror|maximum recursion depth)", "Unbounded recursion: add a base case or turn it into a loop."),
    (r"zerodivisionerror", "Guard the divisor against zero before dividing."),
    (r"(filenotfounderror|no such file or directory|enoent)",
     "That path does not exist. Check the exact path with list_dir or find_files; relative paths resolve from the workspace (or the command's cwd)."),
    (r"permission denied",
     "Permission denied. Check ownership/mode with `ls -l`. Scripts need `chmod +x`. Never use sudo on Termux; for phone storage run `termux-setup-storage`."),
    (r"(address already in use|errno 98|eaddrinuse)",
     "The port is taken. Pick another port, or stop the old process (manage_process action=list/stop, or `fuser -k PORT/tcp`)."),
    (r"(connection refused|econnrefused)",
     "Nothing is listening at that address. Start the server first (run_shell background=true), wait about 2 s, then retry; check host and port."),
    (r"(timed out|timeout|etimedout)", "Timed out. Retry once; if it persists check connectivity (/net) or use another source or a longer timeout."),
    (r"(name or service not known|could not resolve host|getaddrinfo failed|temporary failure in name resolution)",
     "DNS failure: the network is down or the hostname is misspelled."),
    (r"(ssl: |certificate verify failed|sslerror)", "TLS error: on Termux run `pkg install ca-certificates`; check that the system date is correct."),
    (r"(command not found|: not found$|is not recognized as an internal)",
     "That program is not installed. Termux: `pkg install NAME`; Debian/Ubuntu/Kali: `apt install NAME`; macOS: `brew install NAME`. Confirm with `which NAME`."),
    (r"unable to locate package", "Refresh the package index first: `pkg update` (Termux) or `apt update`."),
    (r"(failed building wheel|could not build wheels|error: command '.*gcc.*' failed)",
     "A native build failed. Install a compiler and headers (`pkg install clang make` / `apt install build-essential python3-dev`) or choose a pure-Python alternative."),
    (r"no space left on device", "The disk is full. Delete caches or node_modules, run `pkg clean`, and check free space with system_info."),
    (r"(cannot allocate memory|out of memory|\bkilled\b)", "The process ran out of memory. Retry with smaller inputs or fewer parallel jobs."),
    (r"cannot find module ['\"]([^'\"]+)['\"]",
     "Node module '{1}' is missing: run `npm install {1}` (or plain `npm install` if package.json lists it). For a local file, fix the relative path."),
    (r"npm err! missing script: (\S+)", "package.json has no '{1}' script. Read package.json and use an existing script, or add it."),
    (r"npm err! (code )?enoent", "npm cannot find package.json. cd into the project folder or run `npm init -y`."),
    (r"referenceerror: (\w+) is not defined",
     "'{1}' is used but not defined or loaded. Define it before use, fix the spelling, or load the library with a <script src> placed before your code."),
    (r"cannot read propert(?:y|ies) of (?:null|undefined)",
     "Something is null/undefined, most often getElementById returned null because the script runs before the element exists. Put the script at the end of <body> (or wait for DOMContentLoaded) and check the id spelling."),
    (r"(\w+) is not a function", "'{1}' is not callable: check that it is defined before use, spelled correctly, and not shadowed by a variable."),
    (r"unexpected token", "Syntax problem near the reported token: look for a missing comma, bracket or quote, or a file that was cut off."),
    (r"not a git repository", "Run `git init` first, or cd into the repository."),
    (r"(authentication failed|could not read username|permission denied \(publickey\))",
     "Git needs credentials: use a personal access token as the password, or SSH keys. Never paste tokens into chat; use /secret."),
    (r"(non-fast-forward|failed to push some refs|updates were rejected)", "The remote has newer commits: `git pull --rebase`, resolve conflicts, then push."),
    (r"sdk location not found", "Set ANDROID_HOME or create local.properties containing sdk.dir=/path/to/Android/sdk."),
    (r"(unsupportedclassversionerror|invalid source release|java.lang.unsupportedclassversion)",
     "Java version mismatch. Compare `java -version` with the version the project requires and switch JDKs."),
    (r"old_string not found",
     "Re-read the file with read_file and copy the exact text (whitespace matters), or use a smaller unique snippet."),
    (r"http (?:error )?(404)|\b404 not found", "URL not found: check the spelling, or find the current URL with web_search."),
    (r"http (?:error )?(401|403)|\b(401|403) (?:unauthorized|forbidden)",
     "Access denied: the endpoint needs credentials. Store the key with /secret and use the {{NAME}} placeholder."),
]
_HINT_RX = []


def _compile_hints():
    for pat, tpl in HINTS:
        _HINT_RX.append((re.compile(pat, re.I | re.M), tpl))


_compile_hints()


def is_failure(name, res):
    """True when a tool result represents a failure worth fixing before finishing."""
    if res.startswith(("ERROR", "DENIED")):
        return True
    if name in ("run_shell", "run_python"):
        m = re.search(r"\[exit code (-?\d+)", res)
        if m and m.group(1) != "0":
            return True
        if "[TIMEOUT after" in res or "Traceback (most recent call last)" in res:
            return True
    if name in ("verify_files", "check_project") and res.startswith("ISSUES"):
        return True
    return False


def first_error_line(res):
    """The most informative single line of a failing result."""
    lines = [l.strip() for l in res.splitlines() if l.strip()]
    for l in reversed(lines):
        if re.search(r"(error|exception|failed|cannot|not found|denied|refused|undefined|invalid)", l, re.I) and not l.startswith("[exit code"):
            return clip(l, 160)
    return clip(lines[0], 160) if lines else "(no output)"


def diagnose(name, args, res):
    """Return up to 3 actionable hints for a failing tool result."""
    if not is_failure(name, res):
        return []
    low = res.lower()
    hints = []
    for rx, tpl in _HINT_RX:
        m = rx.search(low)
        if not m:
            continue
        groups = [m.group(0)] + [g or "" for g in m.groups()]
        mod = (groups[1] if len(groups) > 1 else "").split(".")[0]
        orig = re.search(r"no module named ['\"]([\w.]+)['\"]", res, re.I)
        top = (orig.group(1) if orig else mod).split(".")[0]
        try:
            text = tpl.format(*groups, pip=PIP_NAMES.get(top, top))
        except (IndexError, KeyError):
            text = tpl
        if text not in hints:
            hints.append(text)
        if len(hints) >= 3:
            break
    return hints


def with_hints(name, args, res):
    hints = diagnose(name, args, res)
    if not hints:
        return res
    return res + "\n[how to fix]\n" + "\n".join("- " + h for h in hints)
