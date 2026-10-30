"""Constants, folder locations and default limits."""

import os
from pathlib import Path


VERSION = "1.1.0"


API_BASE = (os.environ.get("AXION_API_BASE") or os.environ.get("AXON_API_BASE") or "https://openrouter.ai/api/v1").rstrip("/")


ROUTER_MODEL = "openrouter/free"


DEFAULT_MODEL = ROUTER_MODEL


HOME_DIR = Path(os.environ.get("AXION_HOME") or os.environ.get("AXON_HOME") or str(Path.home() / ".axion"))


CONFIG_FILE = HOME_DIR / "config.json"


SKILLS_DIR = HOME_DIR / "skills"


SESSIONS_DIR = HOME_DIR / "sessions"


TRASH_DIR = HOME_DIR / "trash"


BG_DIR = HOME_DIR / "bg"


HISTORY_FILE = HOME_DIR / "input_history"


UA = "Mozilla/5.0 (compatible; AxionCode/%s; +https://github.com/alfar988/Axon-code)" % VERSION


MAX_STEPS = 60             # max steps (requests) per user message


MAX_TOOL_OUTPUT = 14000    # max characters of a tool result sent to the model


COMPACT_AT_CHARS = 110000  # auto-compact the conversation beyond this size


IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cache",
               ".idea", ".next", "dist", "build", ".gradle", ".kode"}


HISTORY_DIRNAME = "history"


SNAP_IGNORE = IGNORE_DIRS | {HISTORY_DIRNAME}


STALL_DEFAULT = 90


MAXREQ_DEFAULT = 1500


PLAN_MAX_STEPS = 10


READ_TOOLS = {"list_dir", "read_file", "search_files", "find_files", "project_overview", "read_notes", "save_note",
              "use_skill", "web_search", "web_fetch", "review_website", "verify_files", "system_info",
              "deep_research", "package_info", "learn", "recall"}


WEB_TOOLS = {"web_search", "web_fetch", "review_website", "deep_research", "package_info"}


PLAN_TOOLS = READ_TOOLS | {"submit_plan", "ask_user", "todo"}


CHAT_TOOLS = set(READ_TOOLS)


MODELS_CACHE = HOME_DIR / "models_cache.json"


# --- package locations (the folder you extracted or cloned: run.py, prompts/, skills/, templates/) ---
APP_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = APP_DIR / "prompts"
BUNDLED_SKILLS_DIR = APP_DIR / "skills"
TEMPLATES_DIR = APP_DIR / "templates"

# --- resilience ---
MAX_ROT_PER_TURN = 8       # fallback-model switches allowed per user message
COOLDOWN_RATE = 75         # seconds a rate-limited model rests
COOLDOWN_SERVER = 120      # seconds a failing or stalled model rests
COOLDOWN_GONE = 3600       # seconds for a model that is missing or has no tool calling
WRITE_CHUNK_LINES = 100    # recommended maximum lines per write_file / append_file call
MAX_OUT_DEFAULT = 12000    # default output-token budget requested from the provider
