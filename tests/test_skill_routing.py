"""Requests must reach the right skills, and no guide may push the agent past what the user asked for."""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LUMO_HOME", tempfile.mkdtemp(prefix="lumo_test_home_"))

from lumo.cli import *  # noqa: F401,F403,E402  (registers every tool)
from lumo.config import CHAT_TOOLS, PLAN_TOOLS  # noqa: E402
from lumo.skills import pick_skills  # noqa: E402
from lumo.state import Ctx  # noqa: E402

IMPORTED = ("skill-complex-thinking", "skill-deep-research-fact-checking", "skill-game-development-implementation",
            "skill-memory-knowledge-management", "skill-planning", "skill-ui-css-color")


class Routing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws = Path(tempfile.mkdtemp(prefix="axrouting_"))
        cls.ctx = Ctx({"model": "m/a:free"}, cls.ws)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls.ws), True)

    def picks(self, text, intent):
        return pick_skills(self.ctx, text, intent)

    def test_hard_questions_get_the_reasoning_skill(self):
        for text in ("Berapa probabilitas dapat minimal satu angka 6 dalam 4 lemparan dadu?",
                     "Buktikan bahwa akar 2 itu irasional",
                     "Berapa jumlah cara membayar 100 dengan koin 1, 5, 10, 25 dan 50?",
                     "How many ways can I climb 10 stairs taking 1 or 2 steps?",
                     "Berapa 15% dari 240?"):
            self.assertEqual(self.picks(text, "chat"), ["reasoning-skill"], text)

    def test_algorithm_requests_get_the_algorithms_skill(self):
        self.assertIn("algorithms-skill", self.picks("Tulis fungsi python yang mencari jalur terpendek di grid dengan BFS", "task"))
        self.assertIn("algorithms-skill", self.picks("Optimalkan fungsi ini supaya lebih cepat, sekarang O(n^2)", "task"))
        self.assertEqual(self.picks("Jelaskan kompleksitas waktu quicksort dan kapan worst case terjadi", "chat"), ["algorithms-skill"])

    def test_errors_still_go_to_debugging(self):
        self.assertEqual(self.picks("Kenapa muncul ModuleNotFoundError: No module named 'requests'?", "chat"), ["debug-skill"])
        self.assertIn("debug-skill", self.picks("perbaiki error TypeError di app.py", "task"))

    def test_build_requests_do_not_pull_in_reasoning_or_algorithms(self):
        for text in ("buatkan game snake", "buatkan game luar angkasa dengan bahan bakar dan planet", "buatkan landing page untuk toko kopi",
                     "buat kalkulator bunga majemuk dengan HTML"):
            picked = self.picks(text, "build")
            self.assertTrue(picked, text)
            self.assertNotIn("reasoning-skill", picked, text)
            self.assertNotIn("algorithms-skill", picked, text)
        self.assertIn("game-skill", self.picks("buatkan game snake", "build"))

    def test_chat_mode_can_calculate_but_not_change_files(self):
        self.assertIn("run_python", CHAT_TOOLS)
        for forbidden in ("write_file", "edit_file", "append_file", "run_shell", "delete_file", "use_template"):
            self.assertNotIn(forbidden, CHAT_TOOLS)
        self.assertNotIn("run_python", PLAN_TOOLS)


class StayInScope(unittest.TestCase):
    def test_no_guide_or_template_demands_extras_the_user_did_not_ask_for(self):
        forbidden = re.compile(r"at least (two|three) (mechanics|features|real features|things)|beyond (a|the) template|two or more new mechanics|minimum bar \(required\)", re.I)
        files = [p for p in (ROOT / "skills").glob("*.md") if p.stem not in IMPORTED] + list((ROOT / "prompts").glob("*.md")) + [ROOT / "templates" / "manifest.json", ROOT / "README.md"]
        for p in files:
            self.assertIsNone(forbidden.search(p.read_text(encoding="utf-8")), p.name)
        src = (ROOT / "lumo" / "tools" / "project.py").read_text(encoding="utf-8") + (ROOT / "lumo" / "templates.py").read_text(encoding="utf-8")
        self.assertIsNone(forbidden.search(src))

    def test_every_template_customization_list_is_request_driven(self):
        templates = json.loads((ROOT / "templates" / "manifest.json").read_text(encoding="utf-8"))["templates"]
        for name, t in templates.items():
            self.assertTrue(t["customize"], name)
            joined = " ".join(t["customize"]).lower()
            self.assertTrue(re.search(r"request|user|asked|described", joined), name)

    def test_skills_say_to_stay_inside_the_request(self):
        for name in ("code-quality-skill", "game-skill", "reasoning-skill"):
            text = (ROOT / "skills" / (name + ".md")).read_text(encoding="utf-8").lower()
            self.assertTrue("did not ask" in text or "nobody asked" in text or "do not turn it into a build" in text, name)


if __name__ == "__main__":
    unittest.main()
