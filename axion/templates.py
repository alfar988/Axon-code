"""Ready-made, tested starters (games, web pages, apps, APIs) the model adapts instead of writing from scratch."""

import difflib
import html
import json
import os
import re
from pathlib import Path

from axion.config import TEMPLATES_DIR
from axion.state import ToolError
from axion.tools.files import t_write_file
from axion.tools.registry import S, tool


# ---------------------------------------------------------------------------
#  TEMPLATES: tested, working starting points (games, web pages, apps, APIs).
#  Adapting a good starter is faster and far more reliable than writing the same engine from scratch.
#  templates/manifest.json lists them; placeholders look like __TITLE__.
# ---------------------------------------------------------------------------
_TPL_VAR_RX = re.compile(r"__([A-Z][A-Z0-9_]*)__")


def load_template_manifest():
    try:
        return json.loads((TEMPLATES_DIR / "manifest.json").read_text(encoding="utf-8")).get("templates", {})
    except (OSError, ValueError):
        return {}


def template_catalog():
    rows = []
    for k, m in load_template_manifest().items():
        rows.append("- %s: %s (default file: %s; variables: %s)" % (k, m.get("desc", ""), m.get("default_path", "?"),
                                                                   ", ".join(m.get("vars", {})) or "none"))
    return "\n".join(rows) or "(none)"


@tool("use_template", "Copy a tested, working starter into the workspace and fill in its variables. Use it as the base for games, "
      "web pages, apps and APIs, then adapt it with edit_file instead of writing the same engine from scratch. name='list' shows "
      "all templates.",
      {"name": S("template id, or 'list'"), "path": S("destination file in the workspace (optional, each template has a default)"),
       "vars": {"type": "object", "description": "placeholder values, e.g. {\"TITLE\": \"Bunny Garden\", \"ACCENT\": \"#2f9e6f\"}"}},
      ["name"])
def t_use_template(a, ctx):
    man = load_template_manifest()
    nm = str(a.get("name") or "").strip().lower()
    if nm in ("", "list", "all"):
        return "Templates (tested starters):\n" + template_catalog()
    m = man.get(nm) or next((v for k, v in man.items() if nm in k), None)
    if not m:
        raise ToolError("unknown template '%s'. Available: %s" % (nm, ", ".join(man) or "-"))
    try:
        text = (TEMPLATES_DIR / m["file"]).read_text(encoding="utf-8")
    except OSError as e:
        raise ToolError("cannot read template: %s" % e)
    vals = {k: str(v) for k, v in m.get("vars", {}).items()}
    for k, v in (a.get("vars") or {}).items():
        vals[str(k).upper()] = str(v)
    is_html = m["file"].lower().endswith((".html", ".htm"))
    if is_html:
        vals = {k: (v if k.endswith("_RAW") or k in ("ACCENT", "LANG") else html.escape(v, quote=True)) for k, v in vals.items()}
    elif m["file"].lower().endswith((".py", ".js", ".mjs", ".ts")):             # values may land inside string literals
        vals = {k: (v if k.endswith("_RAW") else json.dumps(v, ensure_ascii=False)[1:-1]) for k, v in vals.items()}
    text = _TPL_VAR_RX.sub(lambda mo: vals.get(mo.group(1), mo.group(0)), text)
    dest = a.get("path") or m.get("default_path") or m["file"]
    res = t_write_file({"path": dest, "content": text}, ctx)
    if not res.startswith("OK"):
        return res
    key = nm if nm in man else next((k for k in man if nm in k), nm)
    ctx.templates_used[str(dest)] = {"name": key, "lines": text.splitlines(), "min": float(m.get("min_novelty", 0.3)),
                                     "customize": list(m.get("customize", []))}
    todo = "\n".join("  - " + c for c in m.get("customize", []))
    return (res + "\n" + m.get("guide", "") + "\n\nThis is a FOUNDATION, not the finished product. The user expects a result designed for THEIR request. "
            "Changing only colors, the title or names is rejected: Axion compares your final file with the template and sends you back "
            "when it is too similar. Customize substantially:\n" + todo +
            "\nWork with edit_file / append_file in small parts, then verify_files and review_ui / preview_web.")


def template_novelty(base_lines, cur_text):
    """Share of the current file that does not come from the template: 0 = untouched, 1 = completely new."""
    cur = cur_text.splitlines()
    if not cur:
        return 0.0
    sm = difflib.SequenceMatcher(None, base_lines, cur, autojunk=False)
    same = sum(b.size for b in sm.get_matching_blocks())
    return 1.0 - same / float(len(cur))


def template_nudge(ctx):
    """After a build: is the result still (almost) the template? Returns a message asking for real customization, or None."""
    for path, info in list(ctx.templates_used.items()):
        p = Path(path) if os.path.isabs(path) else Path(ctx.ws) / path
        try:
            cur = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        nov = template_novelty(info["lines"], cur)
        if nov < info["min"]:
            return ("[system] %s is still %d%% identical to the '%s' template (a recolor or rename is not enough). The user asked for something "
                    "designed for THEIR request, not the starter with different paint. Customize it substantially now, with edit_file and "
                    "append_file in small parts, covering:\n%s\nKeep what works (the engine, tokens and accessibility), replace and extend "
                    "everything that makes it generic. Then run verify_files and review_ui."
                    % (path, int(round((1 - nov) * 100)), info["name"], "\n".join("- " + c for c in info["customize"])))
    return None
