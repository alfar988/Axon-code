"""End to end: a command fails and is fixed, the agent is asked to reflect, saves a lesson, and the next session sees it."""

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
STATE = {"mode": "", "log": []}


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
        tools = sum(1 for m in msgs if m.get("role") == "tool")
        reflected = any(m.get("role") == "user" and isinstance(m.get("content"), str) and "[system] Reflection" in m["content"] for m in msgs)
        learned = any(tc["function"]["name"] == "learn" for m in msgs for tc in (m.get("tool_calls") or []))
        STATE["log"].append({"system": system, "tools": tools, "reflected": reflected})
        if STATE["mode"] == "second":
            return sse(self, text_chunks("Noted."))
        if tools == 0:
            return sse(self, tool_chunks("run_shell", {"command": "python3 -c 'import nosuchmodule_abc'"}))
        if tools == 1:
            return sse(self, tool_chunks("run_shell", {"command": "python3 -c \"print('fixed')\""}, "call_2"))
        if not reflected:
            return sse(self, text_chunks("The check passes now."))
        if not learned:
            return sse(self, tool_chunks("learn", {"lesson": "A missing python module is reported as ModuleNotFoundError and pip install fixes it on this device.",
                                                  "kind": "fix", "tags": ["python", "pip"]}, "call_3"))
        return sse(self, text_chunks("Done."))


class LearningFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def launch(self, wd, mode, prompt):
        STATE["mode"], STATE["log"] = mode, []
        env = dict(os.environ, AXION_API_BASE="http://127.0.0.1:%d/api/v1" % self.port, AXION_HOME=str(wd / "home"),
                   OPENROUTER_API_KEY="sk-or-test-1234567890", NO_COLOR="1", PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, str(ROOT / "run.py"), str(wd / "ws"), "-m", "m/a:free", "--auto", "-p", prompt],
                           env=env, capture_output=True, text=True, timeout=180, cwd=str(ROOT))
        return p.stdout + p.stderr

    def test_a_fixed_failure_becomes_a_lesson_that_the_next_session_sees(self):
        wd = Path(tempfile.mkdtemp(prefix="axlearn_"))
        self.addCleanup(shutil.rmtree, str(wd), True)
        (wd / "ws").mkdir()
        out = self.launch(wd, "first", "run the import check script and tell me if it passes")
        self.assertIn("worth remembering", out)
        lessons = (wd / "home" / "knowledge" / "lessons.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lessons), 1)
        self.assertIn("ModuleNotFoundError", json.loads(lessons[0])["text"])
        asked = [r for r in STATE["log"] if r["reflected"]]
        self.assertEqual([r["tools"] for r in asked], [2, 3])                                          # asked once; the answer was a `learn` call
        self.assertNotIn("Lessons from earlier work", STATE["log"][0]["system"])                      # nothing was known yet
        # a later session that touches the same subject is told about it
        self.launch(wd, "second", "my python script fails with ModuleNotFoundError after a pip install")
        self.assertIn("Lessons from earlier work", STATE["log"][0]["system"])
        self.assertIn("pip install fixes it", STATE["log"][0]["system"])

    def test_learning_can_be_switched_off(self):
        wd = Path(tempfile.mkdtemp(prefix="axlearn_"))
        self.addCleanup(shutil.rmtree, str(wd), True)
        (wd / "ws").mkdir()
        (wd / "home").mkdir()
        (wd / "home" / "config.json").write_text(json.dumps({"lessons": False}), encoding="utf-8")
        out = self.launch(wd, "first", "run the import check script and tell me if it passes")
        self.assertNotIn("worth remembering", out)
        self.assertFalse((wd / "home" / "knowledge" / "lessons.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
