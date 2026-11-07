"""Limit saver: optional modes that spend fewer requests and tokens, for free-tier and rate-limited keys.

Two hidden commands (not listed in /help, in Tab completion or in the README):
  /safelimit     balanced saver (level 1)
  /safetylimit   maximum saver (level 2): everything level 1 does, stricter, and more
Typing a command switches its level on, and off again when it is typed a second time. "on", "off" and "status" are also
accepted. The choice is saved in config.json (false, true for level 1, 2 for level 2).
With the mode off nothing here has any effect: every function returns the normal value.

Level 1 (balanced):
  - answers are requested with a smaller output budget, tool results are cut shorter
  - old history is tidied earlier, and compacted when it still grows
  - less skill text goes into the prompt; web research reads fewer pages; planning gets fewer research steps
  - the optional extra rounds after a build (UI polish, plan review, reflection) are skipped

Level 2 (maximum) adds:
  - smaller limits everywhere (see MAXIMUM) and shorter tool descriptions
  - the skill and template lists in the prompt shrink to names, and notes and project text are cut to under half
  - old history is archived by itself, like /compact (no model request), once it grows
  - planning has no web research, and the model is asked for short answers and as few tool calls as possible
Error fixing, automatic verification, the template check and the safety rules always stay on.
  - rarely used tools are offered only when the request mentions what they do (see HIDDEN_UNLESS_ASKED)
"""

import re

BALANCED = {"out_tokens": 4096, "tool_output": 6000, "context_tokens": 24000, "keep_last": 4, "skill_share": 0.6,
            "research_sources": 4, "research_queries": 3, "plan_steps": 8, "text_share": 1.0}
MAXIMUM = {"out_tokens": 3072, "tool_output": 3500, "context_tokens": 14000, "keep_last": 3, "skill_share": 0.35,
           "research_sources": 3, "research_queries": 2, "plan_steps": 2, "text_share": 0.45}

# Level 1 values under their older names.
OUT_TOKENS = BALANCED["out_tokens"]           # largest output budget requested for one answer
TOOL_OUTPUT = BALANCED["tool_output"]         # characters of one tool result sent to the model
CONTEXT_TOKENS = BALANCED["context_tokens"]   # tidy old history once prompt + history pass this many tokens
KEEP_LAST = BALANCED["keep_last"]             # most recent messages left untouched while tidying
SKILL_SHARE = BALANCED["skill_share"]         # share of the usual skill text placed in the prompt
RESEARCH_SOURCES = BALANCED["research_sources"]
RESEARCH_QUERIES = BALANCED["research_queries"]
PLAN_STEPS = BALANCED["plan_steps"]

# Tools that the maximum saver leaves out of every request unless the user's request mentions what they do.
# Each entry: (tool names, regular expression that brings them back). Without them each request is about 2,500 tokens smaller.
HIDDEN_UNLESS_ASKED = (
    ({"create_archive", "extract_archive"},
     r"\b(zip|unzip|tar|tarball|archive|extract|compress|decompress|rar|7z|gz|kompres|ekstrak)\b"),
    ({"download_file", "http_request"},
     r"\b(download|unduh|http|https|curl|wget|endpoint|webhook|api call|fetch)\b|https?://"),
    ({"create_skill", "install_skill"}, r"\bskills?\b"),
    ({"deep_research", "review_website", "package_info"},
     r"\b(research|riset|compare|comparison|bandingkan|review|audit|analy[sz]e|latest|terbaru|version|versions|versi|npm|pypi|pip|package|paket|"
     r"library|libraries|website|situs|site|url)\b|https?://"),
    ({"manage_process", "system_info"},
     r"\b(process|processes|proses|kill|port|ports|background|daemon|cpu|ram|memory|memori|disk|storage|penyimpanan|battery|baterai|system|sistem|uptime)\b"),
    ({"copy_path", "move_path"}, r"\b(copy|salin|move|pindah|pindahkan|rename|ganti nama|duplicate|relocate|cp|mv)\b"),
)

_STATE = {"level": 0}


def level():
    return _STATE["level"]


def active():
    return _STATE["level"] > 0


def maximum():
    return _STATE["level"] >= 2


def label():
    return {0: "off", 1: "on", 2: "maximum"}[_STATE["level"]]


def load(cfg):
    """Read the saved choice (called once at startup). An older config holds true or false."""
    try:
        n = int(cfg.get("safelimit") or 0)
    except (TypeError, ValueError):
        n = 0
    _STATE["level"] = max(0, min(2, n))


def set_level(cfg, n):
    n = max(0, min(2, int(n)))
    _STATE["level"] = n
    cfg["safelimit"] = {0: False, 1: True, 2: 2}[n]


def set_on(cfg, flag):
    set_level(cfg, 1 if flag else 0)


def hidden_tools(text):
    """Names of the tools to leave out of this request (maximum saver only)."""
    if _STATE["level"] < 2:
        return set()
    text = (text or "").lower()
    hide = set()
    for names, rx in HIDDEN_UNLESS_ASKED:
        if not re.search(rx, text):
            hide |= names
    return hide


def get(key, normal):
    """The normal value, or the value of the current level while a saver mode is on."""
    n = _STATE["level"]
    if n <= 0:
        return normal
    return (MAXIMUM if n >= 2 else BALANCED)[key]


def pick(normal, saver):
    """The normal value, or the level 1 value. Kept for older callers; use get() for new code."""
    return saver if _STATE["level"] > 0 else normal


def summary():
    if _STATE["level"] >= 2:
        m = MAXIMUM
        return [
            "answers use at most %d output tokens; short answers are requested" % m["out_tokens"],
            "tool results are cut to %d characters and tool descriptions are shortened" % m["tool_output"],
            "rarely used tools (archives, downloads, skill creation, deep research, process info, copy and move) are offered only when the request mentions them",
            "the skill and template lists in the prompt shrink to names; notes and project text are cut to under half",
            "old history is archived by itself, like /compact, once it grows (no model request)",
            "skill text in the prompt is cut to %d%%" % int(m["skill_share"] * 100),
            "web research reads at most %d pages with %d searches" % (m["research_sources"], m["research_queries"]),
            "planning gets %d steps and no web research" % m["plan_steps"],
            "UI polish, plan review and reflection rounds after a build are skipped",
            "still on: error fixing, automatic verification, template check, safety rules",
        ]
    b = BALANCED
    return [
        "answers use at most %d output tokens" % b["out_tokens"],
        "tool results are cut to %d characters" % b["tool_output"],
        "old history is tidied earlier and compacted when it keeps growing",
        "less skill text in the prompt",
        "web research reads at most %d pages with %d searches" % (b["research_sources"], b["research_queries"]),
        "planning gets at most %d research steps" % b["plan_steps"],
        "UI polish, plan review and reflection rounds after a build are skipped",
        "still on: error fixing, automatic verification, template check",
    ]
