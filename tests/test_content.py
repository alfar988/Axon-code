"""Bundled skills and templates: structure, runnable examples, self tests of the code templates."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import lumo.tools  # noqa: E402,F401
from lumo.state import Ctx  # noqa: E402
from lumo.templates import t_use_template  # noqa: E402

SKILLS = ROOT / "skills"
# Skills imported from outside the project. They are shipped as received: the only edit made here is the assistant's
# name (the old product name -> Lumo AI) in the heading and in the sentences that name the assistant. Any other change must fail.
IMPORTED = {
    "skill-complex-thinking.md": "952fb4f72fe5e8ccdfd0af76df7c36ab0d363e77e8d936ed3ed21514fde91210",
    "skill-deep-research-fact-checking.md": "55dc93415e6e3392f95ade4dbb16b8dbf25754a3f098c485a6c0cafcd2b98950",
    "skill-game-development-implementation.md": "f33cb3865b555c07ab734a772f688dcd1161f15edc1e59939d2364207a0f0b2e",
    "skill-memory-knowledge-management.md": "daa457debd5cd95c7f92f7e250e0bf6b917ab5d82fb2dbf2de89fd77d563a249",
    "skill-planning.md": "3f127219973993ac48c7cfa3e430de91be069d0c3dd010b51ff40b59ee76e742",
    "skill-ui-css-color.md": "ba5fe84044020f6589261afd44a815040cb98844a4ae1946379c92419244d546",
}


def blocks(text, lang, marker, comment):
    return re.findall(r"```%s\n(%s check: %s\n.*?)\n```" % (lang, comment, marker), text, re.S)


class Skills(unittest.TestCase):
    def test_imported_skills_are_unmodified(self):
        for name, digest in IMPORTED.items():
            self.assertEqual(hashlib.sha256((SKILLS / name).read_bytes()).hexdigest(), digest, name)

    def test_files_and_manifest_agree(self):
        files = {p.stem for p in SKILLS.glob("*.md")}
        listed = set(json.loads((SKILLS / "manifest.json").read_text(encoding="utf-8"))["skills"])
        self.assertEqual(files, listed)

    def test_our_skills_have_frontmatter_and_valid_patterns(self):
        man = json.loads((SKILLS / "manifest.json").read_text(encoding="utf-8"))["skills"]
        for p in sorted(SKILLS.glob("*.md")):
            if p.name in IMPORTED:
                continue
            text = p.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\nname: %s\ndescription: " % p.stem), p.name)
            for rx, weight in man[p.stem]["match"]:
                re.compile(rx)
                self.assertGreater(weight, 0)

    def test_code_examples_in_new_skills_run(self):
        new = [p for p in SKILLS.glob("*-skill.md")]
        ran = 0
        for p in new:
            text = p.read_text(encoding="utf-8")
            for i, code in enumerate(blocks(text, "python", "runs", "#"), 1):
                with tempfile.TemporaryDirectory() as d:
                    f = Path(d) / "example.py"
                    f.write_text(code, encoding="utf-8")
                    r = subprocess.run([sys.executable, str(f)], capture_output=True, text=True, timeout=120, cwd=d)
                    self.assertEqual(r.returncode, 0, "%s python block %d\n%s%s" % (p.name, i, r.stdout[-400:], r.stderr[-800:]))
                    ran += 1
            for i, code in enumerate(blocks(text, "python", "syntax", "#"), 1):
                compile(code, p.name, "exec")
            if shutil.which("node"):
                for kind, args in (("runs", []), ("syntax", ["--check"])):
                    for i, code in enumerate(blocks(text, "js", kind, "//"), 1):
                        with tempfile.TemporaryDirectory() as d:
                            f = Path(d) / "example.mjs"
                            f.write_text(code, encoding="utf-8")
                            r = subprocess.run(["node"] + args + [str(f)], capture_output=True, text=True, timeout=120, cwd=d)
                            self.assertEqual(r.returncode, 0, "%s js %s block %d\n%s%s" % (p.name, kind, i, r.stdout[-400:], r.stderr[-800:]))
                            ran += 1
        self.assertGreaterEqual(ran, 20)


class CodeTemplates(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="lumo_tpl_"))
        self.ctx = Ctx({"model": "x/y"}, self.ws)
        self.ctx.auto = True

    def make(self, name, path, vars_=None):
        res = t_use_template({"name": name, "path": path, "vars": vars_ or {}}, self.ctx)
        self.assertTrue(res.startswith("OK"), res)
        text = (self.ws / path).read_text(encoding="utf-8")
        self.assertNotRegex(text, r"__[A-Z]{3,}__")
        return self.ws / path

    def run_py(self, path, *args):
        return subprocess.run([sys.executable, str(path)] + list(args), capture_output=True, text=True, timeout=120, cwd=str(self.ws))

    def test_api_python_selftest(self):
        r = self.run_py(self.make("api-python", "api.py", {"TITLE": "Books", "PORT": "8123"}), "--selftest")
        self.assertEqual(r.returncode, 0, r.stdout[-600:] + r.stderr[-600:])
        self.assertIn("all checks passed", r.stdout)

    def test_titles_with_quotes_do_not_break_code_templates(self):
        for name, path, flag in (("api-python", "api.py", "--selftest"), ("bot-telegram", "bot.py", "--selftest"), ("scraper-python", "scraper.py", "--selftest")):
            r = self.run_py(self.make(name, path, {"TITLE": 'Bob\'s "quoted" \\ title'}), flag)
            self.assertEqual(r.returncode, 0, name + "\n" + r.stdout[-500:] + r.stderr[-500:])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_api_node_selftest(self):
        path = self.make("api-node", "api.js", {"TITLE": 'Books "v2"', "PORT": "8124"})
        r = subprocess.run(["node", str(path), "--selftest"], capture_output=True, text=True, timeout=120, cwd=str(self.ws))
        self.assertEqual(r.returncode, 0, r.stdout[-600:] + r.stderr[-600:])
        self.assertIn("all checks passed", r.stdout)

    def test_cli_python_tests(self):
        r = self.run_py(self.make("cli-python", "cli.py", {"PROG": "todo", "TITLE": "A tiny to-do list."}), "--run-tests")
        self.assertEqual(r.returncode, 0, r.stdout[-600:] + r.stderr[-600:])
        h = self.run_py(self.ws / "cli.py", "--help")
        self.assertIn("A tiny to-do list.", h.stdout)
        self.assertIn("usage: todo", h.stdout)

    def test_bot_telegram_selftest(self):
        r = self.run_py(self.make("bot-telegram", "bot.py"), "--selftest")
        self.assertEqual(r.returncode, 0, r.stdout[-600:] + r.stderr[-600:])
        self.assertIn("all checks passed", r.stdout)
        refused = self.run_py(self.ws / "bot.py")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("TELEGRAM_TOKEN", refused.stderr)

    def test_scraper_selftest(self):
        r = self.run_py(self.make("scraper-python", "scraper.py"), "--selftest")
        self.assertEqual(r.returncode, 0, r.stdout[-600:] + r.stderr[-600:])
        self.assertIn("all checks passed", r.stdout)


if __name__ == "__main__":
    unittest.main()
