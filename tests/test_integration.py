"""End-to-end tests against a fake OpenRouter server that reproduces real failure modes:
broken tool-call JSON, rate limits, 403s, cut-off output and Cloudflare blocking.
Run: python -m unittest discover -s tests -v"""
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = {"scenario": "", "stats": {}}
FAIL_429 = {"m/a:free", "m/b:free", "m/c:free"}


def sse(h, chunks):
    h.send_response(200); h.send_header("Content-Type", "text/event-stream"); h.end_headers()
    for c in chunks:
        h.wfile.write(("data: " + (c if isinstance(c, str) else json.dumps(c)) + "\n\n").encode()); h.wfile.flush()


def text_chunks(t):
    return [{"choices": [{"delta": {"content": t}, "finish_reason": None}]}, {"choices": [{"delta": {}, "finish_reason": "stop"}]}, "[DONE]"]


def tool_chunks(name, raw, finish="tool_calls", cid="call_x1"):
    a, b = raw[:len(raw) // 2], raw[len(raw) // 2:]
    return [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": cid, "type": "function", "function": {"name": name, "arguments": a}}]}, "finish_reason": None}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": b}}]}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": finish}]}, "[DONE]"]


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, code, obj, extra=None):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/v1/key"): return self._json(200, {"data": {"label": "t"}})
        if self.path.startswith("/api/v1/models"):
            return self._json(200, {"data": [{"id": i, "context_length": 64000, "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["tools"]}
                                             for i in ("m/a:free", "m/b:free", "m/c:free", "m/d:free")]})
        self._json(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        st = STATE["stats"]; st["reqs"] = st.get("reqs", 0) + 1
        model, msgs = body.get("model"), body.get("messages", [])
        st.setdefault("models", []).append(model); st.setdefault("max_tokens", []).append(body.get("max_tokens"))
        for m in msgs:
            for tc in m.get("tool_calls") or []:
                try: json.loads(tc["function"]["arguments"])
                except Exception:
                    st["bad400"] = st.get("bad400", 0) + 1
                    return self._json(400, {"error": {"code": 400, "message": "Provider returned error", "metadata": {"raw": "Invalid JSON in tool call arguments"}}})
        sc = STATE["scenario"]
        if sc == "ratelimit" and model in FAIL_429:
            return self._json(429, {"error": {"message": "Rate limit exceeded: free-models-per-min", "code": 429}}, {"Retry-After": "30"})
        if sc == "forbidden" and model == "m/a:free":
            return self._json(403, {"error": {"message": "Forbidden", "code": 403}})
        if sc in ("cloudflare", "cfalways") and (sc == "cfalways" or not self.headers.get("User-Agent")):
            html = b"<!DOCTYPE html><html><head><title>Attention Required! | Cloudflare</title></head><body>error code: 1010</body></html>"
            self.send_response(403); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(html))); self.end_headers(); self.wfile.write(html); return
        if sc == "maxtok" and (body.get("max_tokens") or 0) > 6000:
            return self._json(400, {"error": {"code": 400, "message": "max_tokens must be <= 6000 for this model"}})
        last = msgs[-1] if msgs else {}
        sysmsg = msgs[0]["content"] if msgs and msgs[0]["role"] == "system" else ""
        st.setdefault("sys", []).append(sysmsg)
        if sc == "fullbuild":
            plan_phase = "PHASE: RESEARCH AND PLANNING" in sysmsg
            wrote = sum(1 for m in msgs for tc in (m.get("tool_calls") or []) if tc["function"]["name"] in ("write_file", "append_file"))
            planned = any(tc["function"]["name"] == "submit_plan" for m in msgs for tc in (m.get("tool_calls") or []))
            if plan_phase and not planned:
                plan = {"title": "Bunny Garden", "summary": "2D bunny game", "features": ["jump", "collect carrots"], "steps": ["write html", "write loop", "verify"]}
                return sse(self, tool_chunks("submit_plan", json.dumps(plan)))
            if plan_phase: return sse(self, text_chunks("Plan ready."))
            if wrote == 0:
                return sse(self, tool_chunks("write_file", json.dumps({"path": "bunny-garden.html", "content": '<!DOCTYPE html>\n<html lang="en">\n<head><meta charset="UTF-8"><title>Bunny</title></head>\n<body>\n<canvas id="c"></canvas>\n<script>\n'})))
            if wrote == 1:
                return sse(self, tool_chunks("append_file", json.dumps({"path": "bunny-garden.html", "content": "const c = document.getElementById('c');\nfunction loop(){ requestAnimationFrame(loop); }\nloop();\n</script>\n</body>\n</html>\n"})))
            return sse(self, text_chunks("Game finished: bunny-garden.html"))
        st.setdefault("users", []).extend(m.get("content") for m in msgs if m.get("role") == "user" and isinstance(m.get("content"), str))
        if sc in ("stringplan", "tplrecolor"):
            plan_phase = "PHASE: RESEARCH AND PLANNING" in sysmsg
            planned = any(tc["function"]["name"] == "submit_plan" for m in msgs for tc in (m.get("tool_calls") or []))
            if plan_phase and not planned:
                if sc == "stringplan":   # the real-world failure: steps/features sent as ONE string
                    plan = {"title": "Bunny", "summary": "S", "features": "Menu opens and closes, smooth scroll works, CTA shows an alert",
                            "steps": "1. Write the HTML skeleton 2. Add the styles 3. Add the script 4. Verify", "verification": "Open it and check each feature"}
                else:
                    plan = {"title": "Bunny", "summary": "S", "features": ["a"], "steps": ["use template", "customize", "verify"]}
                return sse(self, tool_chunks("submit_plan", json.dumps(plan)))
            if plan_phase: return sse(self, text_chunks("Plan ready."))
            used = any(tc["function"]["name"] == "use_template" for m in msgs for tc in (m.get("tool_calls") or []))
            if sc == "tplrecolor" and not used:
                return sse(self, tool_chunks("use_template", json.dumps({"name": "game-2d", "path": "index.html", "vars": {"TITLE": "Bunny Garden"}})))
            return sse(self, text_chunks("Finished."))
        if last.get("role") == "tool": return sse(self, text_chunks("Done."))
        if sc == "poison":
            return sse(self, tool_chunks("write_file", '{"path":"bunny.html","content":"<meta name="viewport" content="x">\\n<p class="a">hi</p>\\n</html>\\n"}'))
        if sc == "garbage": return sse(self, tool_chunks("list_dir", "{bad json"))
        if sc == "truncated":
            txt = "".join("line %d of the game code goes here\\n" % i for i in range(40))
            return sse(self, tool_chunks("write_file", '{"path":"big.js","content":"' + txt + 'line 41 cut o', finish="length"))
        return sse(self, tool_chunks("write_file", '{"path":"ok.txt","content":"hello\\n"}'))


class FakeOpenRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def run_axion(self, scenario, prompt="write the result file for me"):
        STATE["scenario"], STATE["stats"] = scenario, {}
        wd = Path(tempfile.mkdtemp(prefix="axit_"))
        (wd / "ws").mkdir()
        env = dict(os.environ, AXION_API_BASE="http://127.0.0.1:%d/api/v1" % self.port, AXION_HOME=str(wd / "home"),
                   OPENROUTER_API_KEY="sk-or-test-1234567890", NO_COLOR="1", PYTHONIOENCODING="utf-8")
        t0 = time.time()
        p = subprocess.run([sys.executable, str(ROOT / "run.py"), str(wd / "ws"), "-m", "m/a:free", "--auto", "-p", prompt],
                           env=env, capture_output=True, text=True, timeout=180, cwd=str(ROOT))
        self.addCleanup(shutil.rmtree, str(wd), True)
        return p.stdout + p.stderr, time.time() - t0, dict(STATE["stats"]), wd / "ws"

    def test_unescaped_quotes_are_repaired_and_history_stays_valid(self):
        out, _t, st, ws = self.run_axion("poison")
        self.assertEqual(st.get("bad400", 0), 0)
        self.assertIn('class="a"', (ws / "bunny.html").read_text(encoding="utf-8"))

    def test_garbage_tool_json_never_poisons_the_history(self):
        out, _t, st, _ws = self.run_axion("garbage")
        self.assertEqual(st.get("bad400", 0), 0)
        self.assertNotIn("HTTP 400", out)

    def test_rate_limited_models_are_skipped_quickly(self):
        out, secs, st, ws = self.run_axion("ratelimit")
        self.assertIn("m/d:free", st["models"])
        self.assertLess(secs, 25)
        self.assertTrue((ws / "ok.txt").exists())

    def test_403_from_a_model_is_not_blamed_on_the_key(self):
        out, _t, st, ws = self.run_axion("forbidden")
        self.assertNotIn("API key rejected", out)
        self.assertTrue((ws / "ok.txt").exists())

    def test_cloudflare_block_without_user_agent_is_fixed(self):
        out, _t, _st, ws = self.run_axion("cloudflare")
        self.assertNotIn("API key rejected", out)
        self.assertTrue((ws / "ok.txt").exists())

    def test_permanent_403_gives_an_honest_message(self):
        out, _t, _st, _ws = self.run_axion("cfalways")
        self.assertNotIn("API key rejected", out)
        self.assertIn("valid", out)

    def test_truncated_write_keeps_the_complete_lines(self):
        out, _t, st, ws = self.run_axion("truncated")
        text = (ws / "big.js").read_text(encoding="utf-8")
        self.assertIn("line 39 of the game code", text)
        self.assertNotIn("line 41 cut", text)
        self.assertNotIn("responsmu", out)

    def test_output_budget_is_negotiated_down(self):
        out, _t, st, ws = self.run_axion("maxtok")
        self.assertTrue((ws / "ok.txt").exists())
        self.assertTrue(any(m and m <= 6000 for m in st["max_tokens"]))

    def test_full_build_uses_plan_skills_and_chunked_writes(self):
        for prompt in ("buatkan game 2D kelinci lucu untuk anak di HP", "build a cute 2D bunny game for kids on a phone"):
            out, _t, st, ws = self.run_axion("fullbuild", prompt)
            self.assertTrue((ws / "bunny-garden.html").read_text(encoding="utf-8").rstrip().endswith("</html>"), prompt)
            self.assertTrue((ws / "history" / "plan.md").exists())
            last_sys = st["sys"][-1]
            self.assertIn("ACTIVE SKILLS", last_sys)
            self.assertIn("### Skill: game-skill", last_sys)
            self.assertNotIn("<<", last_sys)


    def test_plan_sent_as_one_string_is_not_split_into_letters(self):
        import re
        out, _t, _st, ws = self.run_axion("stringplan", "build a cute 2D bunny game for kids on a phone")
        plan = (ws / "history" / "plan.md").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"(?m)^\d+\. \*\*", plan)), 4)
        self.assertNotRegex(out, r"(?m)^\s*○ \S$")

    def test_a_recolored_template_is_sent_back_for_real_customization(self):
        out, _t, st, ws = self.run_axion("tplrecolor", "build a cute 2D bunny game for kids on a phone")
        self.assertTrue((ws / "index.html").exists())
        self.assertTrue(any("identical to the 'game-2d' template" in (u or "") for u in st["users"]))
        self.assertIn("too close to the template", out)

if __name__ == "__main__":
    unittest.main()
