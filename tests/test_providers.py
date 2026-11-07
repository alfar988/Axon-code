"""Providers: registry, keys, the Anthropic wire format, and complete sessions against fake servers."""

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
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LUMO_HOME", tempfile.mkdtemp(prefix="lumo_test_home_"))

from lumo import anthropic_wire, providers  # noqa: E402
from lumo.state import ApiError  # noqa: E402


class Registry(unittest.TestCase):
    def test_every_provider_is_complete(self):
        ids = set()
        for p in providers.PROVIDERS:
            self.assertNotIn(p["id"], ids)
            ids.add(p["id"])
            self.assertIn(p["style"], ("openai", "anthropic"))
            if not p.get("custom"):
                self.assertTrue(p["base"].startswith(("https://", "http://localhost")), p["id"])
            if not p.get("local") and not p.get("custom"):
                self.assertTrue(p["env"], p["id"])
        for needed in ("openrouter", "anthropic", "xai", "openai", "gemini", "groq", "mistral", "deepseek", "together", "ollama", "custom"):
            self.assertIn(needed, ids)
        self.assertEqual(providers.BY_ID["anthropic"]["style"], "anthropic")
        self.assertEqual(providers.BY_ID["xai"]["base"], "https://api.x.ai/v1")

    def test_names_and_aliases(self):
        self.assertEqual(providers.find("Grok")["id"], "xai")
        self.assertEqual(providers.find("claude")["id"], "anthropic")
        self.assertEqual(providers.find("google")["id"], "gemini")
        self.assertIsNone(providers.find("nonsense"))

    def test_key_lookup_prefers_the_environment_then_the_saved_key(self):
        prov = providers.BY_ID["xai"]
        with mock.patch.dict(os.environ, {}, clear=False):
            for n in ("XAI_API_KEY", "GROK_API_KEY"):
                os.environ.pop(n, None)
            cfg = {"keys": {"xai": "saved-key"}}
            self.assertEqual(providers.key_for(cfg, prov), "saved-key")
            os.environ["GROK_API_KEY"] = "env-key"
            self.assertEqual(providers.key_for(cfg, prov), "env-key")
            self.assertEqual(providers.key_for({}, providers.BY_ID["ollama"]), "")

    def test_openrouter_still_reads_the_legacy_key(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENROUTER_API_KEY", None)
            self.assertEqual(providers.key_for({"api_key": "old"}, providers.BY_ID["openrouter"]), "old")
            self.assertEqual(providers.key_for({"api_key": "old"}, providers.BY_ID["openai"]), "")

    def test_base_override_applies_to_the_active_provider_only(self):
        with mock.patch.dict(os.environ, {"LUMO_API_BASE": "http://127.0.0.1:9/v1/"}):
            self.assertEqual(providers.base_url({"provider": "openai"}), "http://127.0.0.1:9/v1")
            self.assertEqual(providers.base_url({"provider": "openai"}, providers.BY_ID["xai"]), "https://api.x.ai/v1")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LUMO_API_BASE", None)
            os.environ.pop("AXON_API_BASE", None)
            self.assertEqual(providers.base_url({"provider": "custom", "custom_base": "https://h.example/v1/"}), "https://h.example/v1")

    def test_switching_remembers_the_model_of_each_provider(self):
        cfg = {"model": "qwen/qwen3-coder:free", "model_chosen": True}
        providers.switch(cfg, "anthropic")
        self.assertEqual((cfg["provider"], cfg["model"], cfg["model_chosen"]), ("anthropic", "", False))
        cfg["model"], cfg["model_chosen"] = "claude-sonnet-4-5", True
        providers.switch(cfg, "openrouter")
        self.assertEqual(cfg["model"], "qwen/qwen3-coder:free")
        providers.switch(cfg, "anthropic")
        self.assertEqual(cfg["model"], "claude-sonnet-4-5")

    def test_a_single_key_in_the_environment_picks_the_provider(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}, clear=False):
            for p in providers.PROVIDERS:
                if p["id"] != "anthropic":
                    for n in p["env"]:
                        os.environ.pop(n, None)
            cfg = {}
            self.assertEqual(providers.detect_from_env(cfg)["id"], "anthropic")
            self.assertEqual(cfg["provider"], "anthropic")
            self.assertIsNone(providers.detect_from_env({"provider": "openai"}))

    def test_auth_headers_follow_the_wire_format(self):
        self.assertEqual(providers.auth_headers(providers.BY_ID["openai"], "k"), {"Authorization": "Bearer k"})
        h = providers.auth_headers(providers.BY_ID["anthropic"], "k")
        self.assertEqual(h["x-api-key"], "k")
        self.assertEqual(h["anthropic-version"], "2023-06-01")
        self.assertEqual(providers.auth_headers(providers.BY_ID["ollama"], ""), {})
        self.assertEqual(providers.extra_headers(providers.BY_ID["openai"]), {})

    def test_rate_limit_headers_of_both_styles_are_understood(self):
        got = providers.summarize_limits({"x-ratelimit-limit-requests": "100", "x-ratelimit-remaining-requests": "42", "x-ratelimit-reset-requests": "6s",
                                          "anthropic-ratelimit-tokens-limit": "1000", "anthropic-ratelimit-tokens-remaining": "900",
                                          "anthropic-ratelimit-tokens-reset": "2026-11-05T10:00:00Z", "retry-after": "3"})
        self.assertEqual(got["requests"], {"limit": 100, "remaining": 42, "reset": "6s"})
        self.assertEqual((got["tokens"]["limit"], got["tokens"]["remaining"]), (1000, 900))
        self.assertEqual(providers.pick_limit_headers([("X-RateLimit-Limit", "5"), ("Content-Type", "x"), ("Retry-After", "2")]),
                         {"x-ratelimit-limit": "5", "retry-after": "2"})


class AnthropicConversion(unittest.TestCase):
    def test_messages_are_converted(self):
        msgs = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "make a file"},
                {"role": "assistant", "content": "ok", "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "write_file", "arguments": "{\"path\": \"a.txt\"}"}},
                                                                     {"id": "t2", "type": "function", "function": {"name": "list_dir", "arguments": ""}}]},
                {"role": "tool", "tool_call_id": "t1", "content": "OK"}, {"role": "tool", "tool_call_id": "t2", "content": "a.txt"},
                {"role": "user", "content": "[system] continue"}]
        system, out = anthropic_wire.convert_messages(msgs)
        self.assertEqual(system, "be brief")
        self.assertEqual([m["role"] for m in out], ["user", "assistant", "user"])
        self.assertEqual([b["type"] for b in out[1]["content"]], ["text", "tool_use", "tool_use"])
        self.assertEqual(out[1]["content"][1]["input"], {"path": "a.txt"})
        self.assertEqual(out[1]["content"][2]["input"], {})
        self.assertEqual([b["type"] for b in out[2]["content"]], ["tool_result", "tool_result", "text"])       # results first, in one turn
        self.assertEqual(out[2]["content"][0]["tool_use_id"], "t1")

    def test_conversation_always_starts_with_a_user_turn_and_skips_empty_assistant_turns(self):
        _s, out = anthropic_wire.convert_messages([{"role": "assistant", "content": "hello"}, {"role": "assistant", "content": ""}, {"role": "user", "content": "hi"}])
        self.assertEqual(out[0]["role"], "user")
        self.assertEqual([m["role"] for m in out], ["user", "assistant", "user"])

    def test_tools_and_body(self):
        tools = [{"type": "function", "function": {"name": "read_file", "description": "Read", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]
        body = anthropic_wire.build_body("claude-x", [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], tools, 4000, 0.2, True)
        self.assertEqual(body["tools"][0], {"name": "read_file", "description": "Read", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}})
        self.assertEqual((body["model"], body["max_tokens"], body["stream"], body["system"], body["temperature"]), ("claude-x", 4000, True, "s", 0.2))
        self.assertEqual(body["tool_choice"], {"type": "auto"})
        self.assertNotIn("tools", anthropic_wire.build_body("m", [{"role": "user", "content": "u"}], None, None, None, False))
        self.assertEqual(anthropic_wire.build_body("m", [{"role": "user", "content": "u"}], None, None, None, False)["max_tokens"], 8192)


def events(*items):
    return [("data: %s\n" % json.dumps(i)).encode() for i in items]


class AnthropicParsing(unittest.TestCase):
    TOOL_STREAM = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 25, "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Writing "}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "it."}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "write_file", "input": {}}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\"path\": \"a.txt\", "}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "\"content\": \"x\"}"}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 40}},
        {"type": "message_stop"}]

    def test_stream_with_text_and_a_tool_call(self):
        seen, emitted = [], [False]
        msg, finish, usage, _r = anthropic_wire.read_stream(events(*self.TOOL_STREAM), seen.append, None, emitted, 60, 600)
        self.assertEqual("".join(seen), "Writing it.")
        self.assertEqual(msg["content"], "Writing it.")
        self.assertEqual(finish, "tool_calls")
        call = msg["tool_calls"][0]
        self.assertEqual((call["id"], call["function"]["name"]), ("toolu_1", "write_file"))
        self.assertEqual(json.loads(call["function"]["arguments"]), {"path": "a.txt", "content": "x"})
        self.assertEqual((usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"]), (25, 40, 65))
        self.assertTrue(emitted[0])

    def test_stop_reasons_map_to_the_internal_ones(self):
        for stop, want in (("end_turn", "stop"), ("max_tokens", "length"), ("tool_use", "tool_calls"), ("stop_sequence", "stop")):
            _m, finish, _u, _r = anthropic_wire.read_stream(events({"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": 1}},
                                                                   {"type": "message_stop"}), lambda t: None, None, [False], 60, 600)
            self.assertEqual(finish, want)

    def test_error_event_and_dropped_stream_raise_api_errors(self):
        with self.assertRaises(ApiError) as cm:
            anthropic_wire.read_stream(events({"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}), lambda t: None, None, [False], 60, 600)
        self.assertEqual(cm.exception.kind, "rate")
        with self.assertRaises(ApiError) as cm:
            anthropic_wire.read_stream(events({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}), lambda t: None, None, [False], 60, 600)
        self.assertEqual(cm.exception.kind, "net")

    def test_non_streaming_answer(self):
        class R:
            def read(self):
                return json.dumps({"content": [{"type": "text", "text": "hi"}, {"type": "tool_use", "id": "t9", "name": "list_dir", "input": {"path": "."}}],
                                   "stop_reason": "tool_use", "usage": {"input_tokens": 3, "output_tokens": 4}}).encode()
        seen = []
        msg, finish, usage, _r = anthropic_wire.read_json(R(), seen.append)
        self.assertEqual((msg["content"], finish, usage["total_tokens"]), ("hi", "tool_calls", 7))
        self.assertEqual(json.loads(msg["tool_calls"][0]["function"]["arguments"]), {"path": "."})


# ---- whole sessions against fake servers -------------------------------------------------------------------------------
def sse(handler, items, named=True):
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.end_headers()
    for item in items:
        if isinstance(item, str):
            handler.wfile.write(("data: %s\n\n" % item).encode())
        else:
            handler.wfile.write((("event: %s\n" % item["type"] if named else "") + "data: %s\n\n" % json.dumps(item)).encode())
        handler.wfile.flush()


class Quiet(http.server.BaseHTTPRequestHandler):
    rec = []

    def log_message(self, *a):
        pass

    def reply(self, obj, code=200, headers=None):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def read_body(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        self.rec.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        return body


class FakeAnthropic(Quiet):
    rec = []

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            return self.reply({"data": [{"id": "claude-test", "display_name": "Claude Test", "created_at": "2025-06-01T00:00:00Z", "type": "model"}], "has_more": False})
        self.reply({}, 404)

    def do_POST(self):
        body = self.read_body()
        last = body["messages"][-1]
        got_result = isinstance(last["content"], list) and any(b.get("type") == "tool_result" for b in last["content"])
        head = {"type": "message_start", "message": {"id": "msg_1", "role": "assistant", "content": [], "usage": {"input_tokens": 30, "output_tokens": 1}}}
        if got_result:
            return sse(self, [head, {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                              {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Done: hello.txt contains hi."}},
                              {"type": "content_block_stop", "index": 0},
                              {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 9}}, {"type": "message_stop"}])
        sse(self, [head, {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}, {"type": "ping"},
                   {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Creating the file."}},
                   {"type": "content_block_stop", "index": 0},
                   {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_01", "name": "write_file", "input": {}}},
                   {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\"path\": \"hello.txt\", "}},
                   {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "\"content\": \"hi\\n\"}"}},
                   {"type": "content_block_stop", "index": 1},
                   {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 40}}, {"type": "message_stop"}])


class FakeOpenAI(Quiet):
    rec = []

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            return self.reply({"object": "list", "data": [{"id": "gpt-test", "created": 1750000000}, {"id": "text-embedding-x", "created": 1}]})
        self.reply({}, 404)

    def do_POST(self):
        body = self.read_body()
        if "max_tokens" in body:
            return self.reply({"error": {"message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.", "type": "invalid_request_error"}}, 400)
        sse(self, [json.dumps({"choices": [{"delta": {"content": "pong-7"}, "finish_reason": None}]}),
                   json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]}), "[DONE]"], named=False)


class Sessions(unittest.TestCase):
    def serve(self, handler):
        handler.rec = []
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        return srv.server_address[1]

    def run_lumo(self, port, provider, key_name, key, prompt, model):
        home = Path(tempfile.mkdtemp(prefix="axprov_"))
        self.addCleanup(shutil.rmtree, str(home), True)
        ws = home / "ws"
        ws.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
        env.update({"LUMO_HOME": str(home / "h"), key_name: key, "LUMO_API_BASE": "http://127.0.0.1:%d/v1" % port, "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8"})
        p = subprocess.run([sys.executable, str(ROOT / "run.py"), str(ws), "--provider", provider, "-m", model, "--auto", "-p", prompt],
                           env=env, capture_output=True, text=True, timeout=240, cwd=str(ROOT))
        return p.stdout + p.stderr, ws, home

    def test_anthropic_session_uses_the_native_messages_api_end_to_end(self):
        port = self.serve(FakeAnthropic)
        out, ws, _home = self.run_lumo(port, "anthropic", "ANTHROPIC_API_KEY", "sk-ant-test-key-123456", "create a file hello.txt containing hi", "claude-test")
        self.assertEqual((ws / "hello.txt").read_text(encoding="utf-8"), "hi\n", out[-1500:])
        self.assertIn("Done: hello.txt contains hi.", out)
        reqs = [r for r in FakeAnthropic.rec if r["path"].endswith("/messages")]
        self.assertGreaterEqual(len(reqs), 2)
        first, second = reqs[0], reqs[1]
        self.assertEqual(first["headers"].get("x-api-key"), "sk-ant-test-key-123456")
        self.assertEqual(first["headers"].get("anthropic-version"), "2023-06-01")
        self.assertNotIn("authorization", first["headers"])
        b = first["body"]
        self.assertTrue(b["stream"] and b["max_tokens"] > 0 and b["model"] == "claude-test")
        self.assertIsInstance(b["system"], str)
        self.assertIn("Lumo Code", b["system"])
        self.assertEqual(b["messages"][0]["role"], "user")
        write = [t for t in b["tools"] if t["name"] == "write_file"][0]
        self.assertEqual(write["input_schema"]["type"], "object")
        self.assertNotIn("function", write)
        msgs = second["body"]["messages"]
        self.assertEqual([m["role"] for m in msgs][-3:], ["user", "assistant", "user"])
        use = [blk for blk in msgs[-2]["content"] if blk["type"] == "tool_use"][0]
        self.assertEqual((use["id"], use["input"]), ("toolu_01", {"path": "hello.txt", "content": "hi\n"}))
        result = msgs[-1]["content"][0]
        self.assertEqual((result["type"], result["tool_use_id"]), ("tool_result", "toolu_01"))

    def test_openai_style_provider_learns_that_a_model_wants_max_completion_tokens(self):
        port = self.serve(FakeOpenAI)
        out, _ws, home = self.run_lumo(port, "openai", "OPENAI_API_KEY", "sk-test-openai-123456", "say pong", "gpt-test")
        self.assertIn("pong-7", out)
        chats = [r for r in FakeOpenAI.rec if r["path"].endswith("/chat/completions")]
        self.assertGreaterEqual(len(chats), 2)
        self.assertIn("max_tokens", chats[0]["body"])
        self.assertIn("max_completion_tokens", chats[1]["body"])
        self.assertNotIn("max_tokens", chats[1]["body"])
        self.assertEqual(chats[0]["headers"]["authorization"], "Bearer sk-test-openai-123456")
        self.assertNotIn("x-title", chats[0]["headers"])                       # OpenRouter-only header
        cfg = json.loads((home / "h" / "config.json").read_text(encoding="utf-8"))
        self.assertTrue(cfg["quirks"]["openai:gpt-test"]["max_completion_tokens"])


if __name__ == "__main__":
    unittest.main()
