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

import axion.tools  # noqa: E402,F401
from axion.state import Ctx  # noqa: E402
from axion.templates import t_use_template  # noqa: E402

SKILLS = ROOT / "skills"
# Skills imported from outside the project. They are shipped exactly as received and must never be edited here.
IMPORTED = {
    "skill-complex-thinking.md": "6358a3211bf70f16b43f932f951d277476e0ff4b7b530d3c4a8dbf714d5797b0",
    "skill-deep-research-fact-checking.md": "c2acea1295a4b712c1674d387bfecb97c86f93f97d6e5c91bab7c488795d5512",
    "skill-game-development-implementation.md": "0cedad0f3e846abc757935b83eaedc663c1188cf9beb2f94524f338c57eaf330",
    "skill-memory-knowledge-management.md": "3cfc8f621ba0df7d5601210c7f931a0f96b0e5e244d081f21b589e0eb0a2c119",
    "skill-planning.md": "120b1446f09d02ed6227f3b3f138d02bda2a129227b32e4178ba94bbaa74f071",
    "skill-ui-css-color.md": "db2764b1e408e3dd1807420d18167a462cdde2c9e5501a02797947c54da4910e",
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
        self.ws = Path(tempfile.mkdtemp(prefix="axion_tpl_"))
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
