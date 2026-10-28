"""Session state (Ctx), configuration, API key, secrets and base errors."""

import getpass
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from datetime import timezone
from pathlib import Path

from axion.config import API_BASE, CONFIG_FILE, DEFAULT_MODEL, HOME_DIR, ROUTER_MODEL, UA
from axion.ui import acc, bold, C_ERR, C_WARN, clip, dim, err, ok, out, paint, rl, Spinner, tw, warn
from axion.util import rel


class ToolError(Exception):
    pass


class NoToolsError(Exception):
    pass


class ApiError(Exception):
    def __init__(self, msg, retryable=False, code=None, kind="other", retry_after=None):
        Exception.__init__(self, msg)
        self.retryable = retryable
        self.code = code
        self.kind = kind
        self.retry_after = retry_after


class Ctx:
    def __init__(self, cfg, workspace):
        self.cfg = cfg
        self.ws = Path(os.path.realpath(str(workspace)))
        self.key = None
        self.auto = False
        self.full_access = False
        self.grants = set()
        self.warned_outside = False
        self.sysinfo_ok = False
        self.undo = []
        self.todos = []
        self.messages = []
        self.changes = []
        self.all_changes = []
        self.bg = {}
        self.model_list = []
        self.models_all = None
        self.models_by_id = {}
        self.override = None
        self.fail_ts = {}
        self.rotations = 0
        self.handoff = False
        self.plan = None
        self.task = ""
        self.intent = "task"
        self.force_intent = None
        self.active_skills = []
        self.pinned_skills = set()
        self.skill_shown = {}
        self.skill_report = []
        self.cooldown = {}
        self.max_out = {}
        self.chunk = {}
        self.templates_used = {}
        self.pending_events = []
        self.all_events = []
        self.hist_count = 0
        self.verified_sig = {}
        self.usage = {"prompt": 0, "completion": 0, "last_prompt": 0}
        self.loaded_skills = set()
        self.turn = {"t0": 0.0, "tools": 0, "reqs": 0}

    def cur_model(self):
        base = self.cfg.get("model", DEFAULT_MODEL)
        if self.override and self.override[0] == base:
            return self.override[1]
        return base

    def set_override(self, model):
        self.override = (self.cfg.get("model", DEFAULT_MODEL), model)


def track(ctx, sym, path, extra=""):
    ctx.changes.append((sym, str(path), extra))
    try:
        ctx.all_changes.append((sym, rel(ctx, path)))
        if len(ctx.all_changes) > 400:
            del ctx.all_changes[:100]
    except Exception:
        pass


def ask(ctx, verb, target, details=None, level="normal", force=False):
    """Ask for permission. level: normal | danger. force=True asks even in auto mode."""
    if ctx.auto and level == "normal" and not force:
        return True, ""
    col = C_WARN if level == "normal" else C_ERR
    bar = paint("▍", *col)
    out("  %s %s %s" % (bar, bold(verb), target))
    for d in (details or [])[:8]:
        out("  %s %s" % (bar, dim(clip(d, tw() - 6))))
    hint = "[y] yes · [n] no · [a] auto ›" if level == "normal" else "type 'yes' to continue ›"
    try:
        ans = input(rl("  %s %s " % (bar, dim(hint)))).strip()
    except EOFError:
        return False, "no interactive input available"
    low = ans.lower()
    if level == "danger":
        allowed = low == "yes"
    else:
        allowed = low in ("", "y", "yes", "ya", "a", "auto")
        if low in ("a", "auto"):
            ctx.auto = True
            out("  " + dim("auto mode is on for this workspace (access outside it still asks). Turn off: /auto off"))
    reason = ans.split(None, 1)[1] if (not allowed and " " in ans) else ""
    return allowed, reason


def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg):
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(str(CONFIG_FILE), 0o600)
    except Exception:
        pass


def key_of(ctx):
    return ctx.key or os.environ.get("OPENROUTER_API_KEY") or ctx.cfg.get("api_key") or ""


def mask_key(k):
    return (k[:9] + "…" + k[-4:]) if len(k) > 16 else "…"


def api_get(path, key=None, timeout=20):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(API_BASE + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace") or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return None, {"error": str(e)}


def validate_key(key):
    st, data = api_get("/key", key)
    if st == 200:
        return "ok", (data.get("data") if isinstance(data, dict) and "data" in data else data) or {}
    if st in (401, 403):
        return "invalid", {}
    return "unknown", {"status": st}


def ensure_key(ctx, force=False):
    if key_of(ctx) and not force:
        return True
    out()
    out("  " + bold("API key OpenRouter"))
    out("  " + dim("Create one for free at ") + acc("https://openrouter.ai/keys"))
    out("  " + dim("Paste the key and press Enter (input is hidden)."))
    for _ in range(3):
        try:
            k = getpass.getpass("  key › ")
        except (EOFError, KeyboardInterrupt):
            return False
        k = k.replace("Bearer ", "").strip().strip("'\"")
        if not k:
            return False
        sp = Spinner("checking key")
        sp.start()
        state, info = validate_key(k)
        sp.stop()
        if state == "invalid":
            out("  " + err("✗ OpenRouter rejected the key.") + dim(" Make sure it is complete and starts with sk-or-"))
            continue
        ctx.cfg["api_key"] = k
        ctx.key = k
        if isinstance(info, dict):
            fd = info.get("free_model_daily_requests")
            if isinstance(fd, dict) and fd.get("limit"):
                ctx.cfg["free_daily"] = fd["limit"]
        save_config(ctx.cfg)
        if state == "ok":
            out("  " + ok("✓ key valid ") + dim(mask_key(k)))
        else:
            out("  " + warn("! could not verify it (connection?), key saved: ") + dim(mask_key(k)))
        return True
    out("  " + err("✗ failed 3 times. Run again: python run.py --setup"))
    return False


def today_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def bump_req(ctx):
    u = ctx.cfg.setdefault("req_day", {})
    if u.get("d") != today_utc():
        u.clear()
        u.update({"d": today_utc(), "n": 0})
    u["n"] = u.get("n", 0) + 1


def req_today(ctx):
    u = ctx.cfg.get("req_day") or {}
    return u.get("n", 0) if u.get("d") == today_utc() else 0


def is_free_model(model):
    return str(model).endswith(":free") or model == ROUTER_MODEL


# --- secrets: store other API keys; the model only sees {{NAME}} ---------------
def secret_values(ctx):
    return dict(ctx.cfg.get("secrets", {}))


def expand_secrets(ctx, obj):
    secrets = secret_values(ctx)

    def sub(s):
        def rep(m):
            name = m.group(1)
            if name in secrets:
                return secrets[name]
            if name in os.environ:
                return os.environ[name]
            raise ToolError("secret '%s' is not set. Ask the user to run: /secret set %s" % (name, name))
        return re.sub(r"\{\{([A-Za-z0-9_]+)\}\}", rep, s)

    if isinstance(obj, str):
        return sub(obj)
    if isinstance(obj, dict):
        return {k: expand_secrets(ctx, v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand_secrets(ctx, v) for v in obj]
    return obj


def redact(ctx, text):
    pairs = list(secret_values(ctx).items())
    k = key_of(ctx)
    if k:
        pairs.append(("OPENROUTER_API_KEY", k))
    for name, val in pairs:
        if val and len(val) >= 6:
            text = text.replace(val, "{{%s}}" % name)
    return text
