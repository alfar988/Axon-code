"""AI providers: where each one lives, how to authenticate, which wire format it speaks, key lookup and rate-limit headers.

Every provider except Anthropic speaks the OpenAI chat-completions format (streaming and tool calls). Anthropic uses
its own Messages format, which lumo/anthropic_wire.py converts to and from."""

import os
import re

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_PROVIDER = "openrouter"
REFERER = "https://github.com/alfar988/Lumo-code"

# style: "openai" = POST {base}/chat/completions, "anthropic" = POST {base}/messages.
# prefix is only a hint for typos; the provider itself decides whether a key is valid.
PROVIDERS = (
    {"id": "openrouter", "name": "OpenRouter", "base": "https://openrouter.ai/api/v1", "style": "openai", "env": ("OPENROUTER_API_KEY",),
     "keys_url": "https://openrouter.ai/keys", "console": "https://openrouter.ai/credits", "prefix": "sk-or-",
     "note": "many models, free ones included"},
    {"id": "anthropic", "name": "Anthropic (Claude)", "base": "https://api.anthropic.com/v1", "style": "anthropic", "env": ("ANTHROPIC_API_KEY",),
     "keys_url": "https://console.anthropic.com/settings/keys", "console": "https://console.anthropic.com", "prefix": "sk-ant-",
     "note": "Claude models"},
    {"id": "xai", "name": "xAI (Grok)", "base": "https://api.x.ai/v1", "style": "openai", "env": ("XAI_API_KEY", "GROK_API_KEY"),
     "keys_url": "https://console.x.ai", "console": "https://console.x.ai", "prefix": "xai-", "note": "Grok models"},
    {"id": "openai", "name": "OpenAI", "base": "https://api.openai.com/v1", "style": "openai", "env": ("OPENAI_API_KEY",),
     "keys_url": "https://platform.openai.com/api-keys", "console": "https://platform.openai.com/usage", "prefix": "sk-", "note": "GPT models"},
    {"id": "gemini", "name": "Google Gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai", "style": "openai",
     "env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "keys_url": "https://aistudio.google.com/apikey", "console": "https://aistudio.google.com",
     "prefix": "AIza", "note": "Gemini models, free tier available"},
    {"id": "groq", "name": "Groq", "base": "https://api.groq.com/openai/v1", "style": "openai", "env": ("GROQ_API_KEY",),
     "keys_url": "https://console.groq.com/keys", "console": "https://console.groq.com", "prefix": "gsk_", "note": "very fast, free tier available"},
    {"id": "mistral", "name": "Mistral AI", "base": "https://api.mistral.ai/v1", "style": "openai", "env": ("MISTRAL_API_KEY",),
     "keys_url": "https://console.mistral.ai/api-keys", "console": "https://console.mistral.ai", "prefix": "", "note": "Mistral and Codestral"},
    {"id": "deepseek", "name": "DeepSeek", "base": "https://api.deepseek.com/v1", "style": "openai", "env": ("DEEPSEEK_API_KEY",),
     "keys_url": "https://platform.deepseek.com/api_keys", "console": "https://platform.deepseek.com", "prefix": "sk-", "note": "low-cost coding models"},
    {"id": "together", "name": "Together AI", "base": "https://api.together.xyz/v1", "style": "openai", "env": ("TOGETHER_API_KEY",),
     "keys_url": "https://api.together.ai/settings/api-keys", "console": "https://api.together.ai", "prefix": "", "note": "open-weight models"},
    {"id": "cerebras", "name": "Cerebras", "base": "https://api.cerebras.ai/v1", "style": "openai", "env": ("CEREBRAS_API_KEY",),
     "keys_url": "https://cloud.cerebras.ai", "console": "https://cloud.cerebras.ai", "prefix": "csk-", "note": "very fast open models"},
    {"id": "fireworks", "name": "Fireworks AI", "base": "https://api.fireworks.ai/inference/v1", "style": "openai", "env": ("FIREWORKS_API_KEY",),
     "keys_url": "https://fireworks.ai/account/api-keys", "console": "https://fireworks.ai", "prefix": "fw_", "note": "open-weight models"},
    {"id": "nvidia", "name": "NVIDIA NIM", "base": "https://integrate.api.nvidia.com/v1", "style": "openai", "env": ("NVIDIA_API_KEY",),
     "keys_url": "https://build.nvidia.com", "console": "https://build.nvidia.com", "prefix": "nvapi-", "note": "hosted open models"},
    {"id": "ollama", "name": "Ollama (local)", "base": "http://localhost:11434/v1", "style": "openai", "env": (), "local": True,
     "keys_url": "https://ollama.com", "console": "", "prefix": "", "note": "models on this device or your network, no key"},
    {"id": "lmstudio", "name": "LM Studio (local)", "base": "http://localhost:1234/v1", "style": "openai", "env": (), "local": True,
     "keys_url": "https://lmstudio.ai", "console": "", "prefix": "", "note": "local server, no key"},
    {"id": "custom", "name": "Custom (OpenAI-compatible URL)", "base": "", "style": "openai", "env": ("LUMO_API_KEY", "AXION_API_KEY"), "custom": True,
     "keys_url": "", "console": "", "prefix": "", "note": "any server that speaks the OpenAI API"},
)
BY_ID = {p["id"]: p for p in PROVIDERS}
ALIASES = {"grok": "xai", "x.ai": "xai", "claude": "anthropic", "gpt": "openai", "chatgpt": "openai", "google": "gemini",
           "lm-studio": "lmstudio", "local": "ollama", "or": "openrouter"}

_STATE = {"cfg": {}}


def bind(cfg):
    """Remember the live config dict so helpers without a ctx (api_get, validate_key) use the active provider."""
    _STATE["cfg"] = cfg


def current_cfg():
    return _STATE["cfg"]


def find(name):
    n = str(name or "").strip().lower()
    n = ALIASES.get(n, n)
    return BY_ID.get(n)


def active(cfg=None):
    cfg = current_cfg() if cfg is None else cfg
    return BY_ID.get(str(cfg.get("provider") or DEFAULT_PROVIDER).lower()) or BY_ID[DEFAULT_PROVIDER]


def base_url(cfg=None, prov=None):
    cfg = current_cfg() if cfg is None else cfg
    prov = prov or active(cfg)
    override = os.environ.get("LUMO_API_BASE") or os.environ.get("AXION_API_BASE") or os.environ.get("AXON_API_BASE")
    if override and prov["id"] == active(cfg)["id"]:
        return override.rstrip("/")            # tests and proxies: applies to the active provider
    if prov.get("custom"):
        return str(cfg.get("custom_base") or os.environ.get("LUMO_CUSTOM_BASE") or os.environ.get("AXION_CUSTOM_BASE") or "").rstrip("/")
    return prov["base"]


def needs_key(prov):
    return not prov.get("local")


def key_for(cfg, prov):
    """Environment variable first, then the key saved for this provider (OpenRouter also reads the legacy api_key)."""
    for name in prov["env"]:
        v = os.environ.get(name)
        if v and v.strip():
            return v.strip()
    k = (cfg.get("keys") or {}).get(prov["id"])
    if k:
        return k
    return (cfg.get("api_key") or "") if prov["id"] == "openrouter" else ""


def providers_with_keys(cfg):
    return [p for p in PROVIDERS if needs_key(p) and key_for(cfg, p)]


def save_key(cfg, prov, key):
    cfg.setdefault("keys", {})[prov["id"]] = key
    if prov["id"] == "openrouter":
        cfg["api_key"] = key


def detect_from_env(cfg):
    """First run without a chosen provider: when only one provider has a key in the environment, use it."""
    if cfg.get("provider"):
        return None
    found = [p for p in PROVIDERS if needs_key(p) and any(os.environ.get(n) for n in p["env"])]
    if len(found) == 1 and found[0]["id"] != DEFAULT_PROVIDER:
        cfg["provider"] = found[0]["id"]
        return found[0]
    return None


def auth_headers(prov, key):
    if prov["style"] == "anthropic":
        h = {"anthropic-version": ANTHROPIC_VERSION}
        if key:
            h["x-api-key"] = key
        return h
    return {"Authorization": "Bearer " + key} if key else {}


def extra_headers(prov):
    if prov["id"] == "openrouter":
        return {"X-Title": "Lumo Code", "HTTP-Referer": REFERER}
    return {}


def switch(cfg, pid):
    """Make a provider active. Each provider remembers its own model."""
    old = active(cfg)["id"]
    per = cfg.setdefault("models_by_provider", {})
    if cfg.get("model") and cfg.get("model_chosen"):
        per[old] = cfg["model"]
    cfg["provider"] = pid
    if per.get(pid):
        cfg["model"], cfg["model_chosen"] = per[pid], True
    elif pid == DEFAULT_PROVIDER:
        cfg["model"], cfg["model_chosen"] = "openrouter/free", False
    else:
        cfg["model"], cfg["model_chosen"] = "", False
    return BY_ID[pid]


# --- rate-limit headers ---------------------------------------------------------------------------------------------
_LIMIT_KEYS = re.compile(r"^(?:x-ratelimit|anthropic-ratelimit|ratelimit)-|^retry-after$", re.I)
_A = re.compile(r"^(?:x-ratelimit|ratelimit)-(limit|remaining|reset)(?:-(.+))?$")
_B = re.compile(r"^anthropic-ratelimit-(.+)-(limit|remaining|reset)$")


def pick_limit_headers(pairs):
    return {k.lower(): str(v) for k, v in pairs if _LIMIT_KEYS.match(k)}


def _num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def summarize_limits(headers):
    """{metric: {limit, remaining, reset}} from the rate-limit headers of OpenAI-style and Anthropic responses."""
    metrics = {}
    for k, v in (headers or {}).items():
        m = _B.match(k)
        if m:
            metric, kind = m.group(1), m.group(2)
        else:
            m = _A.match(k)
            if not m:
                continue
            kind, metric = m.group(1), (m.group(2) or "requests")
        slot = metrics.setdefault(metric.replace("-", " "), {})
        slot[kind] = v if kind == "reset" else _num(v)
    return {name: slot for name, slot in metrics.items() if slot.get("limit") is not None or slot.get("remaining") is not None}
