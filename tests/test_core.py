"""Unit tests for the parts of Axion Code that must never regress. Run: python -m unittest discover -s tests -v"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AXION_HOME", tempfile.mkdtemp(prefix="axion_test_home_"))

from axion.cli import *  # noqa: F401,F403,E402  (imports and registers every tool)
import axion.tools  # noqa: F401,E402
from axion.diagnose import diagnose, is_failure, with_hints  # noqa: E402
from axion.skills import list_skills, load_manifest, pick_skills, split_parts, skill_body  # noqa: E402
from axion.state import Ctx  # noqa: E402
from axion.toolcalls import repair_tool_args, sanitize_messages  # noqa: E402
from axion.verify import js_undefined_calls, py_undefined_names, ui_review, ui_score  # noqa: E402


class ToolCallRepair(unittest.TestCase):
    def test_valid_json(self):
        self.assertEqual(repair_tool_args('{"path":"a","content":"b"}', "write_file"), ({"path": "a", "content": "b"}, "ok"))

    def test_raw_newline_inside_string(self):
        args, st = repair_tool_args('{"path":"a.txt","content":"l1\nl2"}', "write_file")
        self.assertEqual((args["content"], st), ("l1\nl2", "repaired"))

    def test_trailing_comma_and_fence(self):
        self.assertEqual(repair_tool_args('```json\n{"path":"a",}\n```')[0], {"path": "a"})

    def test_unescaped_quotes_in_html(self):
        raw = '{"path":"a.html","content":"<p class="x">hi</p>\n<p>b</p>\n","append":true}'
        args, st = repair_tool_args(raw, "write_file")
        self.assertEqual((args["path"], args["append"], st), ("a.html", True, "repaired"))
        self.assertIn('class="x"', args["content"])

    def test_truncated_is_reported(self):
        args, st = repair_tool_args('{"path":"a.html","content":"<html>\\n<body>', "write_file")
        self.assertEqual((args["path"], st), ("a.html", "truncated"))

    def test_garbage(self):
        self.assertEqual(repair_tool_args("not json")[1], "bad")

    def test_sanitize_makes_history_valid(self):
        msgs = [{"role": "user", "content": "x"},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "write_file", "arguments": '{"path":"a","content":"<a href="x">'}}]},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "list_dir", "arguments": "{bad"}}]},
                {"role": "tool", "tool_call_id": "orphan", "content": "x"}]
        self.assertGreater(sanitize_messages(msgs), 0)
        for m in msgs:
            for tc in m.get("tool_calls") or []:
                json.loads(tc["function"]["arguments"])
        ids = [tc["id"] for m in msgs for tc in m.get("tool_calls") or []]
        got = [m["tool_call_id"] for m in msgs if m["role"] == "tool"]
        self.assertEqual(sorted(ids), sorted(got))


class Diagnose(unittest.TestCase):
    def test_missing_module_hint(self):
        res = "Traceback (most recent call last):\nModuleNotFoundError: No module named 'yaml'\n[exit code 1 · 0.1s]"
        self.assertIn("pip install pyyaml", with_hints("run_shell", {}, res))

    def test_failure_detection(self):
        self.assertTrue(is_failure("run_shell", "[exit code 2 · 1s]"))
        self.assertFalse(is_failure("run_shell", "ok\n[exit code 0 · 1s]"))
        self.assertEqual(diagnose("run_shell", {}, "fine\n[exit code 0 · 1s]"), [])

    def test_port_in_use(self):
        self.assertTrue(diagnose("run_shell", {}, "OSError: [Errno 98] Address already in use\n[exit code 1 · 1s]"))


class StaticChecks(unittest.TestCase):
    def test_python_undefined_names(self):
        self.assertEqual([n for _l, n in py_undefined_names("def f():\n    return missing_name + 1\n")], ["missing_name"])
        self.assertEqual(py_undefined_names("import os\ndef f(a):\n    return [i for i in range(a)] + [os.sep]\n"), [])

    def test_js_undefined_calls(self):
        calls, certain = js_undefined_calls("function a(){ spawnEnemy(); }\na();\n")
        self.assertEqual([n for n, _l in calls], ["spawnEnemy"])
        self.assertTrue(certain)
        self.assertEqual(js_undefined_calls("class P { move(d){ this.x += d; } }\nnew P().move(1);\nconst f = (x) => x * 2;\nf(2);\n")[0], [])

    def test_ui_review_flags_known_problems(self):
        bad = ('<!DOCTYPE html><html><head><title>t</title><meta name="viewport" content="width=device-width">'
               '<style>body{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}.c{width:600px;background:#fff;color:#ddd}'
               'button{outline:none}</style></head><body><h1>Rocket</h1><img src="a.png"><input type="text"><p>Lorem ipsum dolor</p></body></html>')
        text = " ".join(m for _s, m in ui_review(bad, "", "bad.html"))
        for needle in ("contrast", "alt text", "label", "lorem", "outline", "purple"):
            self.assertIn(needle, text.lower())


class Skills(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws = Path(tempfile.mkdtemp(prefix="axion_ws_"))
        cls.ctx = Ctx({"model": "x/y"}, cls.ws)

    def test_manifest_matches_files(self):
        man = load_manifest()
        names = {s["name"] for s in list_skills()}
        self.assertTrue(set(man) <= names, set(man) - names)
        self.assertGreaterEqual(len([s for s in list_skills() if s["builtin"]]), 17)

    def test_every_skill_loads_in_parts(self):
        for s in list_skills():
            parts = split_parts(skill_body(s))
            self.assertTrue(parts and all(parts), s["name"])

    def test_router_picks_sensible_skills(self):
        cases = [("build a 3D FPS game with three.js and enemies", "build", True, "game-skill"),
                 ("buatkan website portofolio dengan tema gelap", "build", True, "design-skill"),
                 ("create a REST API with flask and sqlite and jwt login", "build", True, "backend-skill"),
                 ("I get NameError: name 'x' is not defined when I run it", "task", False, "debug-skill"),
                 ("make a telegram bot in python", "build", True, "python-skill"),
                 ("write a roblox datastore script", "build", True, "roblox-skill"),
                 ("research and verify the latest three.js version", "task", False, "skill-deep-research-fact-checking")]
        for text, intent, plan, want in cases:
            self.assertIn(want, pick_skills(self.ctx, text, intent, plan), text)

    def test_router_stays_quiet_for_unrelated_requests(self):
        self.assertEqual(pick_skills(self.ctx, "delete the old log files", "task", False), [])


class Templates(unittest.TestCase):
    def test_manifest_and_review_scores(self):
        man = json.loads((ROOT / "templates" / "manifest.json").read_text(encoding="utf-8"))["templates"]
        self.assertGreaterEqual(len(man), 4)
        for name, m in man.items():
            text = (ROOT / "templates" / m["file"]).read_text(encoding="utf-8")
            for k, v in m["vars"].items():
                text = text.replace("__%s__" % k, v)
            self.assertNotRegex(text, r"__[A-Z]{3,}__", name)
            self.assertGreaterEqual(ui_score(ui_review(text, "", name)), 85, name)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_templates_run_in_the_node_harness(self):
        for name in ("game-2d", "game-3d", "web-app", "web-landing"):
            r = subprocess.run(["node", str(ROOT / "tests" / "dom_harness.js"), str(ROOT / "templates" / (name + ".html"))],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, name + "\n" + r.stdout[-800:] + r.stderr[-400:])


class Prompts(unittest.TestCase):
    def test_prompt_files_exist_and_fill(self):
        from axion.prompts import build_system
        ws = Path(tempfile.mkdtemp(prefix="axion_ws_"))
        ctx = Ctx({"model": "x/y"}, ws)
        ctx.active_skills = ["game-skill"]
        text = build_system(ctx, "build")
        for needle in ("Axion Code", "ACTIVE SKILLS", "Tool rules", "use_template", "append_file"):
            self.assertIn(needle, text)
        self.assertNotIn("<<", text)


class PlanNormalization(unittest.TestCase):
    """Regression: a plan sent as ONE string used to be split into single characters (one todo per letter)."""

    def test_as_items_never_splits_into_characters(self):
        from axion.util import as_items
        sentence = "Open and close works, smooth scroll works, CTA shows an alert"
        self.assertEqual(as_items(sentence), [sentence])
        self.assertEqual(as_items("1. First step 2. Second step 3. Third step"), ["First step", "Second step", "Third step"])
        self.assertEqual(as_items("- a task\n- another task"), ["a task", "another task"])
        self.assertEqual(as_items('["one step", "two steps"]'), ["one step", "two steps"])
        self.assertEqual(as_items(["x", "real step"]), ["real step"])

    def test_submit_plan_accepts_strings(self):
        from axion.tools.registry import TOOLS
        ctx = Ctx({"model": "x/y"}, Path(tempfile.mkdtemp(prefix="axion_ws_")))
        res = TOOLS["submit_plan"]["fn"]({"title": "T", "summary": "S", "steps": "1. Write html 2. Write js 3. Verify",
                                          "features": "a feature, another feature", "verification": "check it works"}, ctx)
        self.assertTrue(res.startswith("OK"))
        self.assertEqual([s["title"] for s in ctx.plan["steps"]], ["Write html", "Write js", "Verify"])
        self.assertEqual(len(ctx.todos), 3)
        self.assertEqual(ctx.plan["features"], ["a feature, another feature"])

    def test_todo_accepts_strings(self):
        from axion.tools.registry import TOOLS
        ctx = Ctx({"model": "x/y"}, Path(tempfile.mkdtemp(prefix="axion_ws_")))
        TOOLS["todo"]["fn"]({"items": "Write the code\nTest it"}, ctx)
        self.assertEqual([t["content"] for t in ctx.todos], ["Write the code", "Test it"])


class TemplateCheck(unittest.TestCase):
    def test_recolor_is_flagged_and_real_work_passes(self):
        from axion.templates import template_novelty, template_nudge
        base = (ROOT / "templates" / "game-2d.html").read_text(encoding="utf-8").replace("__ACCENT__", "#35c48f").replace("__TITLE__", "Orb Rush")
        lines = base.splitlines()
        recolor = base.replace("#35c48f", "#ff8800").replace("Orb Rush", "Bunny Garden")
        self.assertLess(template_novelty(lines, recolor), 0.1)
        reworked = "\n".join(l if i % 5 > 1 else "// new line %d" % i for i, l in enumerate(lines))
        self.assertGreater(template_novelty(lines, reworked), 0.32)
        ws = Path(tempfile.mkdtemp(prefix="axion_ws_"))
        ctx = Ctx({"model": "x/y"}, ws)
        ctx.templates_used["index.html"] = {"name": "game-2d", "lines": lines, "min": 0.32, "customize": ["redraw the entities"]}
        (ws / "index.html").write_text(recolor, encoding="utf-8")
        self.assertIn("identical to the 'game-2d' template", template_nudge(ctx))
        (ws / "index.html").write_text(reworked, encoding="utf-8")
        self.assertIsNone(template_nudge(ctx))


if __name__ == "__main__":
    unittest.main()
