"""The agent must stay inside the user's current request.

Regression tests for a real session: after an unrelated research request, the automatic UI polish pass opened an old page
(blockblast.html) that the request never touched, and the plan and todo list of an earlier build kept steering new requests.
Run: python -m unittest discover -s tests -v"""

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LUMO_HOME", tempfile.mkdtemp(prefix="lumo_test_home_"))

from lumo.cli import *  # noqa: F401,F403,E402  (imports and registers every tool)
from lumo.agent import decide_intent, is_continuation, start_new_task  # noqa: E402
from lumo.prompts import build_system  # noqa: E402
from lumo.skills import pick_skills  # noqa: E402
from lumo.state import Ctx  # noqa: E402
from lumo.tools.registry import TOOLS  # noqa: E402
from lumo.verify import ui_polish_findings, web_files  # noqa: E402


# A page with real, known UI findings (no :focus-visible, no resize handling, no lang attribute).
FLAWED_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Block Blast</title>
<style>
body{margin:0;background:#111;color:#eee;font-family:sans-serif}
button{padding:6px;background:#335;color:#fff;border:0}
canvas{display:block;width:300px;height:300px}
</style></head>
<body>
<h1>Block Blast</h1>
<canvas id="c" width="300" height="300"></canvas>
<button id="restart">Restart</button>
<script>
const c = document.getElementById('c');
const x = c.getContext('2d');
function draw() { x.fillStyle = '#222'; x.fillRect(0, 0, 300, 300); requestAnimationFrame(draw); }
draw();
document.getElementById('restart').addEventListener('click', () => location.reload());
</script>
</body></html>
"""


def make_ctx(cfg=None):
    ws = Path(tempfile.mkdtemp(prefix="axscope_"))
    ctx = Ctx(dict({"model": "m/a:free"}, **(cfg or {})), ws)
    return ctx


class PolishScope(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx()
        self.addCleanup(shutil.rmtree, str(self.ctx.ws), True)
        (self.ctx.ws / "blockblast.html").write_text(FLAWED_PAGE, encoding="utf-8")
        (self.ctx.ws / "notes.txt").write_text("notes\n", encoding="utf-8")

    def test_old_pages_are_not_reviewed_when_the_task_changed_no_page(self):
        self.ctx.changes = [("+", str(self.ctx.ws / "notes.txt"), "")]
        self.assertEqual(web_files(self.ctx, fallback=False), [])
        self.assertEqual(ui_polish_findings(self.ctx), [])

    def test_pages_changed_in_this_task_are_reviewed(self):
        (self.ctx.ws / "new.html").write_text(FLAWED_PAGE, encoding="utf-8")
        self.ctx.changes = [("+", str(self.ctx.ws / "new.html"), "")]
        found = ui_polish_findings(self.ctx)
        self.assertTrue(found)
        self.assertTrue(all(f.startswith("new.html:") for f in found), found)

    def test_explicit_review_ui_without_paths_still_finds_workspace_pages(self):
        res = TOOLS["review_ui"]["fn"]({}, self.ctx)
        self.assertIn("blockblast.html", res)


class ContinuationAndFreshStart(unittest.TestCase):
    def test_continuation_words(self):
        for t in ("continue", "lanjut", "Lanjutkan", "terusin", "ya", "ok", "yes", "gas", "coba lagi", "go on",
                  "continue the previous work from the last point, following the plan"):
            self.assertTrue(is_continuation(t), t)

    def test_resume_prompt_is_a_continuation_and_never_a_new_build(self):
        ctx = make_ctx()
        self.addCleanup(shutil.rmtree, str(ctx.ws), True)
        prompt = ("Continue the previous work from the last point, following the plan and the handoff. "
                  "Remaining steps: build the game board; write the game loop; verify the page")
        self.assertTrue(is_continuation(prompt))
        self.assertEqual(decide_intent(ctx, prompt), ("task", False))
        self.assertEqual(decide_intent(ctx, "buatkan game puzzle")[0], "build")

    def test_new_requests_are_not_continuations(self):
        for t in ("belajar teknik belajar efektif untuk pemula", "buatkan game puzzle", "ubah warna tombol jadi biru",
                  "apa itu spaced repetition?", "continue reading the docs about flask and summarize the routing section for me please"):
            self.assertFalse(is_continuation(t), t)

    def test_new_task_clears_the_old_todo_list_and_plan(self):
        ctx = make_ctx()
        self.addCleanup(shutil.rmtree, str(ctx.ws), True)
        ctx.plan = {"title": "Block Blast", "summary": "s", "steps": [{"title": "a"}]}
        ctx.plan_active = True
        ctx.todos = [{"content": "write html", "status": "pending"}]
        start_new_task(ctx)
        self.assertEqual(ctx.todos, [])
        self.assertFalse(ctx.plan_active)
        self.assertNotIn("Approved plan", build_system(ctx, "build"))
        self.assertNotIn("Block Blast", build_system(ctx, "build"))

    def test_old_automatic_instructions_are_retired_on_a_new_task(self):
        ctx = make_ctx()
        self.addCleanup(shutil.rmtree, str(ctx.ws), True)
        ctx.messages = [{"role": "user", "content": "buatkan game puzzle"},
                        {"role": "assistant", "content": "Done."},
                        {"role": "user", "content": "[system] Automatic UI review found problems. Fix the HIGH and MEDIUM ones now"},
                        {"role": "assistant", "content": "Fixed."}]
        start_new_task(ctx)
        self.assertEqual(ctx.messages[0]["content"], "buatkan game puzzle")
        self.assertTrue(ctx.messages[2]["content"].startswith("[system]"))
        self.assertFalse("Fix the HIGH" in ctx.messages[2]["content"])
        start_new_task(ctx)                                      # idempotent
        self.assertEqual(len([m for m in ctx.messages if m["role"] == "user"]), 2)

    def test_active_plan_is_part_of_the_prompt_only_in_build_phase(self):
        ctx = make_ctx()
        self.addCleanup(shutil.rmtree, str(ctx.ws), True)
        ctx.plan = {"title": "Block Blast", "summary": "s", "steps": [{"title": "a"}]}
        ctx.plan_active = True
        self.assertIn("Approved plan", build_system(ctx, "build"))
        self.assertNotIn("Approved plan", build_system(ctx, "chat"))

    def test_current_request_is_stated_in_the_prompt(self):
        ctx = make_ctx()
        self.addCleanup(shutil.rmtree, str(ctx.ws), True)
        ctx.task = "belajar teknik belajar efektif untuk pemula"
        s = build_system(ctx, "build")
        self.assertIn("Current request", s)
        self.assertIn("belajar teknik belajar efektif", s)


class SkillRouting(unittest.TestCase):
    def test_workspace_type_alone_does_not_pull_in_unrelated_skills(self):
        ctx = make_ctx()
        self.addCleanup(shutil.rmtree, str(ctx.ws), True)
        for name in ("blockblast.html", "index.html", "package.json", "app.py", "requirements.txt"):
            (ctx.ws / name).write_text("x", encoding="utf-8")
        picked = pick_skills(ctx, "tolong rangkum cara menghafal dengan efektif", "task")
        for bad in ("frontend-skill", "design-skill", "backend-skill", "python-skill", "game-skill"):
            self.assertNotIn(bad, picked)


# --- end to end: a fake OpenRouter reproduces the session from the bug report ---------------------------------------
STATE = {"log": []}


def sse(h, chunks):
    h.send_response(200)
    h.send_header("Content-Type", "text/event-stream")
    h.end_headers()
    for c in chunks:
        h.wfile.write(("data: " + (c if isinstance(c, str) else json.dumps(c)) + "\n\n").encode())
        h.wfile.flush()


def text_chunks(t):
    return [{"choices": [{"delta": {"content": t}, "finish_reason": None}]}, {"choices": [{"delta": {}, "finish_reason": "stop"}]}, "[DONE]"]


def tool_chunks(name, args, cid="call_1"):
    return [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}, "[DONE]"]


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/v1/key"):
            return self._json(200, {"data": {"label": "t"}})
        if self.path.startswith("/api/v1/models"):
            return self._json(200, {"data": [{"id": "m/a:free", "context_length": 64000, "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["tools"]}]})
        self._json(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        msgs = body.get("messages", [])
        system = msgs[0]["content"] if msgs and msgs[0]["role"] == "system" else ""
        real = [i for i, m in enumerate(msgs) if m.get("role") == "user" and isinstance(m.get("content"), str) and not m["content"].startswith("[system]")]
        cur = real[-1] if real else 0
        prompt = msgs[cur]["content"] if msgs else ""
        since = msgs[cur + 1:]
        nudges = [m["content"] for m in since if m.get("role") == "user" and isinstance(m.get("content"), str) and m["content"].startswith("[system]")]
        tools_since = sum(1 for m in since if m.get("role") == "tool")
        calls_since = [tc["function"]["name"] for m in since for tc in (m.get("tool_calls") or [])]
        STATE["log"].append({"prompt": prompt, "system": system, "nudges": nudges, "tools": tools_since})
        last = msgs[-1] if msgs else {}
        if last.get("role") == "user" and str(last.get("content", "")).startswith("[system]"):
            return sse(self, text_chunks("Acknowledged."))
        if "warna tombol" in prompt:                                                      # turn 2 (variant): a small edit of the old page
            if tools_since == 0:
                return sse(self, tool_chunks("edit_file", {"path": "blockblast.html", "old_string": "background:#335", "new_string": "background:#2a4"}))
            return sse(self, text_chunks("Button color changed."))
        if "blockblast" in prompt:                                                        # turn 1: a build with a plan
            if "PHASE: RESEARCH AND PLANNING" in system:
                if "submit_plan" not in calls_since and not any(tc["function"]["name"] == "submit_plan" for m in msgs for tc in (m.get("tool_calls") or [])):
                    plan = {"title": "Block Blast", "summary": "puzzle game", "features": ["drag blocks"], "steps": ["write html", "polish", "verify"]}
                    return sse(self, tool_chunks("submit_plan", plan))
                return sse(self, text_chunks("Plan ready."))
            if "write_file" not in calls_since:
                return sse(self, tool_chunks("write_file", {"path": "blockblast.html", "content": FLAWED_PAGE}))
            return sse(self, text_chunks("Game finished: blockblast.html"))
        if tools_since == 0:                                                              # turn 2: an unrelated research request
            return sse(self, tool_chunks("save_note", {"title": "Study techniques", "content": "Spaced repetition, active recall, Feynman technique."}))
        return sse(self, text_chunks("Three techniques: spaced repetition, active recall, Feynman."))


class StaysOnTopic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def session(self, lines):
        STATE["log"] = []
        wd = Path(tempfile.mkdtemp(prefix="axscope_e2e_"))
        self.addCleanup(shutil.rmtree, str(wd), True)
        (wd / "ws").mkdir()
        env = dict(os.environ, LUMO_API_BASE="http://127.0.0.1:%d/api/v1" % self.port, LUMO_HOME=str(wd / "home"),
                   OPENROUTER_API_KEY="sk-or-test-1234567890", NO_COLOR="1", PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, str(ROOT / "run.py"), str(wd / "ws"), "-m", "m/a:free", "--auto"],
                           input="\n".join(lines) + "\n", env=env, capture_output=True, text=True, timeout=240, cwd=str(ROOT))
        return p.stdout + p.stderr, wd / "ws"

    def requests_for(self, needle):
        return [r for r in STATE["log"] if needle in r["prompt"]]

    def test_an_unrelated_request_after_a_build_is_not_steered_by_the_old_work(self):
        out, ws = self.session(["buatkan game puzzle blockblast", "belajar teknik belajar efektif untuk pemula"])
        self.assertTrue((ws / "blockblast.html").is_file(), out[-1500:])
        first, second = self.requests_for("blockblast"), self.requests_for("belajar teknik")
        self.assertTrue(first and second, out[-1500:])
        # the build itself still gets its automatic UI review (that is intended)
        self.assertTrue(any("Automatic UI review" in n for r in first for n in r["nudges"]), "the build lost its UI review")
        # the unrelated request gets none of the old work: no UI review, no unfinished-steps nudge, no old plan, no old skills
        for r in second:
            joined = "\n".join(r["nudges"])
            self.assertFalse("Automatic UI review" in joined, "UI review of an old page was injected")
            self.assertFalse("unfinished steps" in joined, "todo items of the old build were injected")
            self.assertFalse("Approved plan" in r["system"], "the old plan is still in the prompt")
            self.assertFalse("## ACTIVE SKILLS" in r["system"], "skills of the old build are still active")
            self.assertTrue("Current request" in r["system"], "the prompt does not state the current request")
        self.assertEqual((ws / "blockblast.html").read_text(encoding="utf-8"), FLAWED_PAGE)
        self.assertEqual(out.count("polishing the interface"), 1, "the polish pass must run for the build only, not again for the unrelated request")

    def test_a_small_edit_is_not_expanded_into_a_redesign(self):
        out, ws = self.session(["buatkan game puzzle blockblast", "ubah warna tombol di blockblast.html jadi hijau"])
        edit = self.requests_for("warna tombol")
        self.assertTrue(edit, out[-1500:])
        for r in edit:
            self.assertFalse(any("Automatic UI review" in n for n in r["nudges"]), "a one-line edit triggered the UI polish pass")
        page = (ws / "blockblast.html").read_text(encoding="utf-8")
        self.assertIn("background:#2a4", page)                    # the requested change was made
        self.assertIn("addEventListener", page)                   # and nothing else was rewritten
        self.assertEqual(out.count("polishing the interface"), 1)

    def test_continue_keeps_the_unfinished_work(self):
        out, ws = self.session(["buatkan game puzzle blockblast", "lanjut"])
        again = self.requests_for("lanjut")
        self.assertTrue(again, out[-1500:])
        self.assertTrue(any("Approved plan" in r["system"] for r in again), "the plan was dropped on 'continue'")
        self.assertTrue(any("Block Blast" in r["system"] and "Current request" in r["system"] for r in again), "the original request was lost")
        self.assertTrue(any("buatkan game puzzle blockblast" in r["system"] for r in again), "the original request was replaced by 'lanjut'")


if __name__ == "__main__":
    unittest.main()
