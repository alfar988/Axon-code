"""scripts/page_check.js must pass the shipped templates and catch the failures that give a blank or frozen screen."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "page_check.js"

PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>t</title></head><body>
<canvas id="c"></canvas>
<script>
%s
</script></body></html>"""

HEALTHY = """
const c = document.getElementById('c'), x = c.getContext('2d');
function resize() { c.width = Math.max(1, window.innerWidth); c.height = Math.max(1, window.innerHeight); }
window.addEventListener('resize', resize); resize();
let t = 0;
function frame() { t++; x.fillStyle = '#123'; x.fillRect(0, 0, c.width, c.height); x.fillStyle = '#fff'; x.fillRect(t % 50, 40, 20, 20); requestAnimationFrame(frame); }
frame();
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PageCheck(unittest.TestCase):
    def check(self, html, *extra):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "page.html"
            f.write_text(html, encoding="utf-8")
            r = subprocess.run(["node", str(SCRIPT), str(f)] + list(extra), capture_output=True, text=True, timeout=120)
            return r.returncode, r.stdout + r.stderr

    def test_shipped_templates_pass(self):
        man = json.loads((ROOT / "templates" / "manifest.json").read_text(encoding="utf-8"))["templates"]
        for name in [k for k, v in man.items() if v["file"].endswith(".html")]:
            r = subprocess.run(["node", str(SCRIPT), str(ROOT / "templates" / (name + ".html"))], capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, name + "\n" + r.stdout + r.stderr)
        r = subprocess.run(["node", str(SCRIPT), str(ROOT / "templates" / "game-2d.html")], capture_output=True, text=True, timeout=120)
        self.assertRegex(r.stdout, r"first frame [1-9]\d*")

    def test_healthy_canvas_page_passes_in_both_orientations(self):
        code, out = self.check(PAGE % HEALTHY)
        self.assertEqual(code, 0, out)
        self.assertIn("390x780", out)
        self.assertIn("844x390", out)

    def test_blank_canvas_is_reported(self):
        code, out = self.check(PAGE % "const x = document.getElementById('c').getContext('2d'); function f(){ x.fillStyle='#000'; requestAnimationFrame(f);} f();")
        self.assertEqual(code, 1, out)
        self.assertIn("blank", out)

    def test_exception_at_load_is_reported_with_its_line(self):
        code, out = self.check(PAGE % "const a = 1;\nundefinedFunction();")
        self.assertEqual(code, 1, out)
        self.assertIn("ReferenceError", out)
        self.assertRegex(out, r"line \d+")

    def test_exception_in_the_loop_is_reported(self):
        code, out = self.check(PAGE % (HEALTHY + "\nlet n = 0; const old = frame; window.frame2 = function(){}; setTimeout(function(){ x.fillRect(); }, 30);\nrequestAnimationFrame(function boom(){ if (++n > 3) { null.crash; } requestAnimationFrame(boom); });"))
        self.assertEqual(code, 1, out)
        self.assertIn("animation frame", out)

    def test_landscape_only_size_bug_is_caught(self):
        # the canvas height is "viewport height minus fixed UI": fine in portrait, negative in landscape
        code, out = self.check(PAGE % HEALTHY.replace("c.height = Math.max(1, window.innerHeight)", "c.height = window.innerHeight - 500"))
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"844x390: PROBLEM")
        self.assertRegex(out, r"390x780: ok")

    def test_bad_usage_exits_with_2(self):
        r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)
        r = subprocess.run(["node", str(SCRIPT), "/nonexistent/page.html"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
