"""Limit saver: an optional mode that spends fewer requests and tokens, for free-tier and rate-limited keys.

Hidden command: /safelimit (switch on or off), /safelimit on, /safelimit off, /safelimit status.
It is not listed in /help or in Tab completion. The choice is saved in config.json.
With the mode off nothing here has any effect: every function returns the normal value.

What it changes while it is on:
  - answers are requested with a smaller output budget (OUT_TOKENS)
  - tool results sent back to the model are cut shorter (TOOL_OUTPUT)
  - old history is tidied earlier, and compacted when it still grows (CONTEXT_TOKENS, KEEP_LAST)
  - less skill text goes into the prompt (SKILL_SHARE)
  - web research reads fewer pages and starts fewer searches (RESEARCH_SOURCES, RESEARCH_QUERIES)
  - planning gets fewer research steps (PLAN_STEPS)
  - the optional extra rounds after a build (UI polish, plan review, reflection) are skipped.
    Error fixing, automatic verification and the template check still run.
"""

OUT_TOKENS = 4096           # largest output budget requested for one answer
TOOL_OUTPUT = 6000          # characters of one tool result sent to the model
CONTEXT_TOKENS = 24000      # tidy old history once prompt + history pass this many tokens
KEEP_LAST = 4               # most recent messages left untouched while tidying
SKILL_SHARE = 0.6           # share of the usual skill text placed in the prompt
RESEARCH_SOURCES = 4        # pages read by one deep_research call
RESEARCH_QUERIES = 3        # searches started by one deep_research call
PLAN_STEPS = 8              # research steps allowed while planning

_STATE = {"on": False}


def active():
    return _STATE["on"]


def load(cfg):
    """Read the saved choice (called once at startup)."""
    _STATE["on"] = bool(cfg.get("safelimit"))


def set_on(cfg, flag):
    _STATE["on"] = bool(flag)
    cfg["safelimit"] = bool(flag)


def pick(normal, saver):
    """The normal value, or the saver value while the mode is on."""
    return saver if _STATE["on"] else normal


def summary():
    return [
        "answers use at most %d output tokens" % OUT_TOKENS,
        "tool results are cut to %d characters" % TOOL_OUTPUT,
        "old history is tidied earlier and compacted when it keeps growing",
        "less skill text in the prompt",
        "web research reads at most %d pages with %d searches" % (RESEARCH_SOURCES, RESEARCH_QUERIES),
        "planning gets at most %d research steps" % PLAN_STEPS,
        "UI polish, plan review and reflection rounds after a build are skipped",
        "still on: error fixing, automatic verification, template check",
    ]
