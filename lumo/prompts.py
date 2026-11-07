"""Builds the system prompt from prompts/*.md and the active skills."""

import os
import platform
import re
from datetime import datetime

from lumo import safelimit
from lumo.config import APP_DIR, BUNDLED_SKILLS_DIR, PROMPTS_DIR, TEMPLATES_DIR
from lumo.knowledge import lessons_block
from lumo.memory import handoff_text, plan_markdown, read_notes_text
from lumo.skills import catalog_text, render_active_skills
from lumo.templates import template_catalog
from lumo.toolcalls import chunk_lines
from lumo.tools.project import overview_text
from lumo.ui import short_path


def access_label(ctx):
    if ctx.full_access:
        return "FULL (whole system, approved by the user)"
    extra = ""
    if ctx.grants:
        extra = " + approved folders: " + ", ".join(short_path(g) for g in list(ctx.grants)[:4])
    return "workspace only%s. Anything outside needs the user's approval first." % extra


# ---------------------------------------------------------------------------
#  THE SYSTEM PROMPT IS LOADED FROM FILES in prompts/*.md
#    system-prompt.md  identity, work loop, quality bar, rules
#    tool-rules.md     tool-call rules that prevent errors (JSON, writing big files in parts, loops)
#    plan-prompt.md    research and planning phase
#    qa-prompt.md      question-and-answer mode
#  The model can read these files (read-only) and you can edit them at any time; changes apply to the next request.
# ---------------------------------------------------------------------------
_PROMPT_CACHE = {}

FALLBACK_SYSTEM = (
    "You are Lumo Code, a coding agent working in the user's terminal (<<ENV>>). "
    "Finish tasks end-to-end with tools; never only describe what you could do. Stay inside the user's current request and leave other files alone.\n"
    "Workspace: <<WORKSPACE>> | OS: <<OS>> | Python <<PYTHON>> | Date: <<DATE>> | File access: <<ACCESS>>\n"
    "Call tools through native tool-calling with valid JSON. Write files in parts of at most <<CHUNK_LINES>> lines "
    "(write_file, then append_file). Verify with verify_files, run what you build, fix errors yourself, and report briefly in the "
    "user's language.\nAvailable secrets: <<SECRETS>>\nSkills:\n<<SKILL_CATALOG>>\nTemplates:\n<<TEMPLATE_CATALOG>>"
)


def read_prompt(name, fallback=""):
    """Read prompts/<name>. Cached by mtime; if the file is missing a built-in fallback is used so Lumo never breaks."""
    p = PROMPTS_DIR / name
    try:
        st = p.stat()
        sig = (st.st_mtime, st.st_size)
        c = _PROMPT_CACHE.get(str(p))
        if c and c[0] == sig:
            return c[1]
        text = re.sub(r"<!--.*?-->", "", p.read_text(encoding="utf-8"), flags=re.S).strip()
        _PROMPT_CACHE[str(p)] = (sig, text)
        return text
    except OSError:
        return fallback


def fill_template(text, values):
    for k, v in values.items():
        text = text.replace("<<%s>>" % k, str(v))
    return text


def skill_budget(ctx, phase):
    try:
        from lumo.models import model_ctx_len  # late import: models imports this module
        cl = model_ctx_len(ctx, ctx.cur_model())
    except Exception:
        cl = 32768
    b = 18000 if cl >= 100000 else (14000 if cl >= 60000 else (10000 if cl >= 32000 else (6000 if cl >= 20000 else 3500)))
    b = int(b * safelimit.pick(1.0, safelimit.SKILL_SHARE))
    return b // 2 if phase == "chat" else b


def build_system(ctx, phase="build"):
    secrets = ", ".join("{{%s}}" % k for k in sorted(ctx.cfg.get("secrets", {}))) or "(none yet)"
    env = "Termux (Android)" if "com.termux" in os.environ.get("PREFIX", "") else platform.system()
    lines = chunk_lines(ctx)
    values = {"ENV": env, "WORKSPACE": ctx.ws, "OS": platform.platform()[:60], "PYTHON": platform.python_version(),
              "DATE": datetime.now().strftime("%A, %d %B %Y"), "ACCESS": access_label(ctx), "SECRETS": secrets,
              "SKILL_CATALOG": catalog_text(ctx, ctx.active_skills), "TEMPLATE_CATALOG": template_catalog(), "APP_DIR": APP_DIR,
              "PROMPTS_DIR": PROMPTS_DIR, "SKILLS_DIR": BUNDLED_SKILLS_DIR, "TEMPLATES_DIR": TEMPLATES_DIR,
              "CHUNK_LINES": lines, "CHUNK_CHARS": lines * 55}
    parts = [fill_template(read_prompt("system-prompt.md", FALLBACK_SYSTEM), values)]
    safety = read_prompt("safety-rules.md")
    if safety:
        parts.append(safety)                                  # always on, in every phase
    rules = fill_template(read_prompt("tool-rules.md"), values)
    if rules:
        parts.append(rules)
    if phase == "plan":
        parts.append(fill_template(read_prompt("plan-prompt.md", "# PHASE: PLANNING\nResearch briefly, then call submit_plan."), values))
        parts.append("## Workspace overview\n" + overview_text(ctx, limit=3500))
    elif phase == "chat":
        parts.append(fill_template(read_prompt("qa-prompt.md", "# MODE: Q&A\nAnswer directly; do not modify files."), values))
    for fn in ("LUMO.md", "AXION.md", "AGENTS.md", "CLAUDE.md"):
        p = ctx.ws / fn
        if p.is_file():
            parts.append("## Project instructions (%s)\n%s" % (fn, p.read_text(encoding="utf-8", errors="replace")[:6000]))
            break
    if ctx.plan and ctx.plan_active and phase == "build":
        parts.append("## Approved plan (history/plan.md). Follow it step by step and keep `todo` in sync.\n" + plan_markdown(ctx.plan)[:6000])
    notes = read_notes_text(ctx, 3500)
    if notes:
        parts.append("## Saved notes and research (history/notes.md; reference only, they may belong to earlier work. "
                     "Use them only when they help the current request)\n" + notes)
    lessons = lessons_block(ctx)
    if lessons:
        parts.append(lessons)
    if ctx.handoff:
        parts.append("## HANDOFF: you are taking over interrupted work\n" + handoff_text(ctx, "model switch / recovery")[:7000])
    skills = render_active_skills(ctx, ctx.active_skills, skill_budget(ctx, phase))
    if skills:
        parts.append(skills)
    task = (ctx.task or "").strip()
    if task and phase in ("build", "plan"):
        parts.append("## Current request (your only task)\n" + (task if len(task) <= 900 else task[:900] + "…") + "\n"
                     "Work on this and nothing else. Other files and projects in the workspace belong to earlier work: leave them alone. "
                     "Automatic [system] messages (verification, UI review, reminders) concern only the files you change for this request.")
    return "\n\n".join(parts)
