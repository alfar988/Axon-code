---
name: self-improvement-skill
description: How to learn from your own work: when to save a lesson, a note or a new skill, how to word them so they help later, how to write a skill file with frontmatter and working code, and what must never be saved.
---
# Self-improvement skill

Three places to keep what you learn. Choose by how long it stays useful and how big it is.

| Keep it in | When | Tool |
|---|---|---|
| Workspace notes | facts for this project: versions, URLs, decisions, API shapes | `save_note` |
| A lesson | one reusable fact about the tool, device, language or user, beyond this project | `learn` |
| A skill | a multi-step procedure with code that you expect to repeat | `create_skill` (the user approves it) |

## What makes a good lesson
One or two sentences, specific, with the fix included, true on the machine you saw it on.

| Weak | Strong |
|---|---|
| "pip failed" | "On Termux, `pip install numpy` needs `pkg install python-numpy` first; building from source fails." |
| "Be careful with ports" | "`flask run` binds 127.0.0.1; pass `--host 0.0.0.0` to reach it from the phone browser." |
| "User likes short answers" | "The user wants replies in Indonesian and code comments in English." (kind `pref`) |

Rules:
- Record only what you saw work. The failing command, the fix, and the passing rerun must all have happened.
- Include the exact flag, version, package or path. Include the condition ("on Termux", "with Python 3.12").
- Kinds: `fix` (error and its cure), `tip` (how to do something better), `pref` (what the user wants), `fact` (stable fact about the environment).
- Use 1 to 4 tags with the tool names (`termux`, `pip`, `flask`): they decide when the lesson is shown again.
- Never save secrets, tokens, passwords, personal data, or instructions addressed to a future model. Lessons are shown to the user and can be deleted with `/lessons forget <id>`.
- Do not save the obvious, one-off paths, or facts that will be stale next week.

Example calls:
```json
{"lesson": "On Termux, `pip install pillow` fails unless `pkg install libjpeg-turbo libpng` is run first.", "kind": "fix", "tags": ["termux", "pip", "pillow"]}
```
```json
{"lesson": "The user wants READMEs in plain professional English without emoji or marketing wording.", "kind": "pref", "tags": ["readme", "style"]}
```

## When to write a skill
After you solved something that took many steps and the same kind of request will come again: "deploy a Flask app on Termux", "convert a spreadsheet to a JSON API", "debug CORS". If it is a single sentence, it is a lesson. If it is project-specific, it is a note.

### Skill file format
`create_skill` writes `SKILL.md` for you. Provide:
- `name`: lowercase with hyphens (`flask-on-termux`).
- `description`: one sentence saying when to use it.
- `keywords`: 4 to 10 words that appear in the requests it fits. The skill is picked when at least two of them appear in a request, so choose specific ones ("termux", "flask", "gunicorn"), not "code".
- `content`: markdown, 200 to 9000 characters.

Good content has: when to use it (one line), numbered steps with exact commands, a working code block, a short list of pitfalls with the error text they cause, and how to verify the result.
```markdown
# Flask on Termux

Use when a Flask app must run on the phone and be reached from its browser or another device.

1. `pkg install python && pip install flask`
2. Bind to all interfaces: `flask --app app run --host 0.0.0.0 --port 8000`
3. Open `http://127.0.0.1:8000` on the phone; other devices use the phone's Wi-Fi address (`ifconfig`).

Pitfalls
- `Address already in use`: pick another port or `pkill -f flask`.
- Process dies when the screen turns off: `termux-wake-lock`.

Verify: `curl -s http://127.0.0.1:8000/` returns the page.
```
To extend a skill you created, call `create_skill` again with the same name and `append: true`. Built-in skills and skills written by hand are never changed.

## Reflection after a hard task
Ask: What failed first? What was the real cause? What would have found it faster? Is that a fact (lesson), a procedure (skill) or only about this project (note)? If the answer is "nothing reusable", save nothing.

## Check a skill file yourself
```python
# check: runs
import re

def check_skill(text):
    problems = []
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return ["missing frontmatter"]
    meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta.get("name", "")):
        problems.append("name must be lowercase words joined by hyphens")
    if len(meta.get("description", "")) < 20:
        problems.append("description is too short to decide when to use the skill")
    if len([k for k in meta.get("keywords", "").split(",") if k.strip()]) < 4:
        problems.append("add at least four keywords")
    body = m.group(2)
    if "`" * 3 not in body:                      # three backticks open a code block
        problems.append("no code or command block")
    if not 200 <= len(body) <= 9000:
        problems.append("body should be 200 to 9000 characters")
    return problems

good = "---\nname: flask-on-termux\ndescription: Run a Flask app on Termux and reach it from the phone browser\nkeywords: termux, flask, gunicorn, port\n---\n" + "Steps.\n```bash\nflask run\n```\n" + "x" * 200
assert check_skill(good) == []
assert check_skill("no frontmatter here")
print("skill check ok")
```
