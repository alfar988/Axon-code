"""Model ranking and the 12-hour refresh, /checklimit, skills chosen by the AI, richer plans, and the license files."""

import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LUMO_HOME", tempfile.mkdtemp(prefix="lumo_test_home_"))

from lumo.cli import *  # noqa: F401,F403,E402  (registers every tool)
from lumo import models, providers  # noqa: E402
from lumo.config import MODELS_TTL, PLAN_MAX_STEPS  # noqa: E402
from lumo.memory import plan_markdown  # noqa: E402
from lumo.prompts import build_system  # noqa: E402
from lumo.skills import activate_skill, skill_mode  # noqa: E402
from lumo.state import Ctx, ToolError  # noqa: E402
from lumo.tools.registry import TOOLS  # noqa: E402


def order(ids, **extra):
    ms = [dict({"id": i, "context_length": 128000}, **extra) for i in ids]
    return [m["id"] for m in sorted(ms, key=models.model_score, reverse=True)]


def make_ctx(cfg=None):
    ws = Path(tempfile.mkdtemp(prefix="axv13_"))
    return Ctx(dict({"model": "m/a:free"}, **(cfg or {})), ws)


class Ranking(unittest.TestCase):
    def test_each_provider_lists_its_strongest_models_first(self):
        a = order(["claude-3-haiku-20240307", "claude-sonnet-4-5-20250929", "claude-opus-4-1-20250805", "claude-3-5-haiku-20241022", "claude-haiku-4-5-20251001"])
        self.assertEqual((a[0], a[-1]), ("claude-opus-4-1-20250805", "claude-3-haiku-20240307"))
        self.assertLess(a.index("claude-sonnet-4-5-20250929"), a.index("claude-haiku-4-5-20251001"))
        o = order(["gpt-3.5-turbo", "gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-5", "gpt-5-mini", "o3", "gpt-5-nano"])
        self.assertEqual((o[0], o[-1]), ("gpt-5", "gpt-3.5-turbo"))
        self.assertLess(o.index("o3"), o.index("gpt-4o"))
        x = order(["grok-2", "grok-3-mini", "grok-3", "grok-4"])
        self.assertEqual((x[0], x[-1]), ("grok-4", "grok-2"))
        g = order(["gemini-2.0-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemma-3-27b-it"])
        self.assertEqual((g[0], g[-1]), ("gemini-2.5-pro", "gemma-3-27b-it"))

    def test_free_openrouter_models_put_big_coders_above_tiny_ones(self):
        r = order(["meta-llama/llama-3.2-3b-instruct:free", "qwen/qwen3-coder:free", "mistralai/mistral-small-3.2-24b-instruct:free",
                   "moonshotai/kimi-k2:free", "nvidia/nemotron-nano-9b-v2:free", "deepseek/deepseek-r1:free"])
        self.assertEqual(r[0], "qwen/qwen3-coder:free")
        self.assertEqual(r[-1], "meta-llama/llama-3.2-3b-instruct:free")
        self.assertLess(r.index("deepseek/deepseek-r1:free"), r.index("mistralai/mistral-small-3.2-24b-instruct:free"))

    def test_a_newer_release_beats_an_older_one_of_the_same_kind(self):
        now = time.time()
        new = models.model_score({"id": "lab/model-x", "created": now - 20 * 86400, "context_length": 64000}, now)
        old = models.model_score({"id": "lab/model-x", "created": now - 700 * 86400, "context_length": 64000}, now)
        self.assertGreater(new, old)

    def test_user_results_nudge_the_order(self):
        ctx = make_ctx({"model_stats": {"b/model": {"ok": 30, "fail": 0}, "a/model": {"ok": 0, "fail": 6}}})
        got = [m["id"] for m in models.ranked_models(ctx, [{"id": "a/model", "context_length": 8000}, {"id": "b/model", "context_length": 8000}])]
        self.assertEqual(got, ["b/model", "a/model"])


class Normalizing(unittest.TestCase):
    def test_non_chat_models_are_dropped_and_prefixes_cleaned(self):
        openai = providers.BY_ID["openai"]
        data = {"data": [{"id": "gpt-5"}, {"id": "text-embedding-3-large"}, {"id": "whisper-1"}, {"id": "dall-e-3"}, {"id": "gpt-5-pro"},
                         {"id": "tts-1"}, {"id": "omni-moderation-latest"}, {"id": "gpt-4o-realtime-preview"}, {"id": "gpt-4.1"}]}
        self.assertEqual([m["id"] for m in models.normalize_models(openai, data)], ["gpt-5", "gpt-4.1"])
        gem = models.normalize_models(providers.BY_ID["gemini"], {"data": [{"id": "models/gemini-2.5-pro"}, {"id": "models/text-embedding-004"}]})
        self.assertEqual([m["id"] for m in gem], ["gemini-2.5-pro"])

    def test_other_list_shapes(self):
        together = [{"id": "meta/llama-3.3-70b", "type": "chat", "context_length": 131072}, {"id": "bge-large", "type": "embedding"}]
        self.assertEqual([m["id"] for m in models.normalize_models(providers.BY_ID["together"], together)], ["meta/llama-3.3-70b"])
        mistral = {"data": [{"id": "mistral-large-latest", "capabilities": {"completion_chat": True}, "max_context_length": 128000},
                            {"id": "mistral-embed", "capabilities": {"completion_chat": False}}]}
        got = models.normalize_models(providers.BY_ID["mistral"], mistral)
        self.assertEqual([(m["id"], m["context_length"]) for m in got], [("mistral-large-latest", 128000)])
        groq = {"data": [{"id": "llama-3.3-70b-versatile", "active": True, "context_window": 131072}, {"id": "old-model", "active": False}]}
        self.assertEqual([m["id"] for m in models.normalize_models(providers.BY_ID["groq"], groq)], ["llama-3.3-70b-versatile"])
        anth = {"data": [{"id": "claude-opus-4-1-20250805", "created_at": "2025-08-05T00:00:00Z", "type": "model"}]}
        got = models.normalize_models(providers.BY_ID["anthropic"], anth)
        self.assertGreater(got[0]["created"], 1.7e9)
        self.assertEqual(got[0]["context_length"], 200000)

    def test_openrouter_default_view_is_free_models_that_can_use_tools(self):
        full = [{"id": "a/free:free", "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["tools"]},
                {"id": "b/paid", "pricing": {"prompt": "0.000003", "completion": "0.000015"}, "supported_parameters": ["tools"]},
                {"id": "c/free-no-tools:free", "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["temperature"]},
                {"id": "openrouter/free", "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["tools"]}]
        self.assertEqual([m["id"] for m in models.default_view(providers.BY_ID["openrouter"], full)], ["a/free:free"])
        self.assertEqual(len(models.default_view(providers.BY_ID["openai"], full)), 4)

    def test_price_text(self):
        self.assertEqual(models.price_text({"pricing": {"prompt": "0", "completion": "0"}}), "free")
        self.assertEqual(models.price_text({"pricing": {"prompt": "0.000003", "completion": "0.000015"}}), "$3/M")
        self.assertEqual(models.price_text({}), "")


class ModelList(unittest.TestCase):
    """The list is fetched once, kept for 12 hours (memory and disk), refetched when stale, and an old list survives being offline."""

    def setUp(self):
        self.calls = []
        calls = self.calls

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                calls.append(self.path)
                body = json.dumps({"data": [{"id": "a/free-big:free", "context_length": 128000, "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["tools"]},
                                            {"id": "b/paid", "context_length": 128000, "pricing": {"prompt": "0.000003", "completion": "0.000015"}, "supported_parameters": ["tools"]}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        tmp = Path(tempfile.mkdtemp(prefix="axml_"))
        self.addCleanup(shutil.rmtree, str(tmp), True)
        self.cache = tmp / "models_cache.json"
        for p in (mock.patch.dict(os.environ, {"LUMO_API_BASE": "http://127.0.0.1:%d/api/v1" % self.srv.server_address[1]}),
                  mock.patch("lumo.models.MODELS_CACHE", self.cache)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        try:
            self.srv.shutdown()
            self.srv.server_close()
        except Exception:
            pass

    def test_refresh_cycle(self):
        ctx = make_ctx()
        self.assertEqual(MODELS_TTL, 12 * 3600)
        self.assertEqual([m["id"] for m in models.ensure_models(ctx)], ["a/free-big:free"])
        self.assertEqual(len(ctx.models_full), 2)
        self.assertEqual(len(self.calls), 1)
        models.ensure_models(ctx)
        self.assertEqual(len(self.calls), 1, "a fresh list must not be fetched again")
        other = make_ctx()
        models.ensure_models(other)
        self.assertEqual(len(self.calls), 1, "a new session reads the disk cache")
        self.assertFalse(models.refresh_due(ctx))
        data = json.loads(self.cache.read_text(encoding="utf-8"))
        data["time"] = time.time() - 13 * 3600                      # 13 hours old
        self.cache.write_text(json.dumps(data), encoding="utf-8")
        ctx.models_time = time.time() - 13 * 3600
        self.assertTrue(models.refresh_due(ctx))
        models.ensure_models(ctx, force=True)
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(models.refresh_due(ctx))
        stale = make_ctx()
        data["time"] = time.time() - 13 * 3600
        self.cache.write_text(json.dumps(data), encoding="utf-8")
        models.ensure_models(stale)                                   # stale disk cache: fetched again
        self.assertEqual(len(self.calls), 3)

    def test_offline_keeps_the_old_list(self):
        ctx = make_ctx()
        models.ensure_models(ctx)
        self.srv.shutdown()
        self.srv.server_close()
        got = models.ensure_models(ctx, force=True, timeout=2)
        self.assertEqual([m["id"] for m in got], ["a/free-big:free"])
        fresh = make_ctx()
        data = json.loads(self.cache.read_text(encoding="utf-8"))
        data["time"] = time.time() - 40 * 3600
        self.cache.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual([m["id"] for m in models.ensure_models(fresh, force=True, timeout=2)], ["a/free-big:free"])

    def test_a_provider_without_a_chosen_model_starts_with_the_best_ranked(self):
        class H2(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = json.dumps({"data": [{"id": "grok-2"}, {"id": "grok-4"}, {"id": "grok-3-mini"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H2)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        with mock.patch.dict(os.environ, {"LUMO_API_BASE": "http://127.0.0.1:%d/v1" % srv.server_address[1], "XAI_API_KEY": "xai-test-123456"}):
            with mock.patch("lumo.models.save_config"):
                ctx = make_ctx()
                providers.switch(ctx.cfg, "xai")
                self.assertEqual(models.auto_pick_model(ctx), "grok-4")
                self.assertEqual(ctx.cfg["models_by_provider"]["xai"], "grok-4")
                self.assertTrue(ctx.cfg["model_chosen"])


class CheckLimit(unittest.TestCase):
    DRIVER = r"""
import sys, time, tempfile
from pathlib import Path
sys.path.insert(0, %(root)r)
from lumo.cli import *
from lumo.state import Ctx
from lumo.limits import cmd_checklimit
ctx = Ctx(dict({"model": "m/a:free"}, **%(cfg)r), Path(tempfile.mkdtemp()))
ctx.rate_info = %(seed)r
for v in ctx.rate_info.values():
    v["time"] = time.time()
cmd_checklimit(ctx, %(args)r)
"""

    def serve(self, key_body=None, probe_headers=None):
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, obj, code=200, headers=None):
                b = json.dumps(obj).encode()
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if self.path.endswith("/key") and key_body is not None:
                    return self.send({"data": key_body})
                self.send({}, 404)

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self.send({"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}, 200, probe_headers)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        return srv.server_address[1]

    def run_cmd(self, port, cfg, key_env, args=(), seed=None):
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
        env.update(key_env)
        env.update({"LUMO_HOME": tempfile.mkdtemp(prefix="axlim_"), "LUMO_API_BASE": "http://127.0.0.1:%d/v1" % port, "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8"})
        code = self.DRIVER % {"root": str(ROOT), "cfg": cfg, "seed": seed or {}, "args": list(args)}
        p = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr[-800:])
        return p.stdout

    def test_openrouter_free_tier(self):
        port = self.serve({"label": "t", "usage": 0.0, "limit": None, "is_free_tier": True})
        out = self.run_cmd(port, {}, {"OPENROUTER_API_KEY": "sk-or-v1-testkey-123456"})
        self.assertIn("Limits · OpenRouter", out)
        self.assertIn("free tier", out)
        self.assertRegex(out, r"50 of 50 left today")
        self.assertIn("resets in", out)

    def test_openrouter_paid_account_shows_credit(self):
        port = self.serve({"label": "t", "usage": 1.5, "limit": 10, "limit_remaining": 8.5, "is_free_tier": False, "usage_daily": 0.1, "usage_weekly": 0.5, "usage_monthly": 1.5})
        out = self.run_cmd(port, {}, {"OPENROUTER_API_KEY": "sk-or-v1-testkey-123456"})
        self.assertIn("paid account", out)
        self.assertIn("$8.50 of $10.00 left", out)
        self.assertRegex(out, r"1000 of 1000 left today")
        self.assertIn("day $0.10", out)

    def test_other_providers_show_the_headers_of_the_last_response(self):
        seed = {"openai": {"headers": {"x-ratelimit-limit-requests": "50", "x-ratelimit-remaining-requests": "38", "x-ratelimit-reset-requests": "6s",
                                       "x-ratelimit-limit-tokens": "200000", "x-ratelimit-remaining-tokens": "150000"}}}
        out = self.run_cmd(self.serve(), {"provider": "openai", "model": "gpt-5"}, {"OPENAI_API_KEY": "sk-test-123456789"}, seed=seed)
        self.assertIn("Limits · OpenAI", out)
        self.assertIn("38 of 50 left", out)
        self.assertIn("150000 of 200000 left", out)
        self.assertIn("resets in 6s", out)
        self.assertIn("https://platform.openai.com/usage", out)

    def test_no_data_yet_explains_what_to_do(self):
        out = self.run_cmd(self.serve(), {"provider": "anthropic", "model": "claude-x"}, {"ANTHROPIC_API_KEY": "sk-ant-test-123456"})
        self.assertIn("No rate-limit data", out)
        self.assertIn("/checklimit probe", out)

    def test_probe_reads_the_limits_with_one_small_request(self):
        port = self.serve(probe_headers={"x-ratelimit-limit-requests": "10", "x-ratelimit-remaining-requests": "7"})
        out = self.run_cmd(port, {"provider": "openai", "model": "gpt-5"}, {"OPENAI_API_KEY": "sk-test-123456789"}, args=["probe"])
        self.assertIn("7 of 10 left", out)

    def test_missing_key_is_reported(self):
        out = self.run_cmd(self.serve(), {"provider": "xai", "model": "grok-4"}, {})
        self.assertIn("no API key for xAI", out)


class AiChosenSkills(unittest.TestCase):
    def test_default_is_ai_mode_and_the_model_loads_skills_itself(self):
        ctx = make_ctx()
        self.assertEqual(skill_mode(ctx), "ai")
        res = TOOLS["use_skill"]["fn"]({"name": "python-skill, algorithms-skill"}, ctx)
        self.assertIn("python-skill", ctx.active_skills)
        self.assertIn("algorithms-skill", ctx.active_skills)
        self.assertIn("loaded", res)
        sysmsg = build_system(ctx, "build")
        self.assertIn("## ACTIVE SKILLS (loaded by you with use_skill", sysmsg)
        self.assertIn("### Skill: algorithms-skill", sysmsg)
        self.assertIn("Available skills:", sysmsg)
        self.assertIn("YOU choose them", sysmsg)

    def test_unknown_names_are_reported_without_breaking_the_others(self):
        ctx = make_ctx()
        res = TOOLS["use_skill"]["fn"]({"name": "debug-skill, no-such-skill"}, ctx)
        self.assertIn("debug-skill", ctx.active_skills)
        self.assertIn("no-such-skill", res)
        with self.assertRaises(ToolError):
            TOOLS["use_skill"]["fn"]({"name": "no-such-skill"}, ctx)

    def test_the_system_does_not_add_skills_behind_the_models_back(self):
        ctx = make_ctx()
        self.assertFalse(activate_skill(ctx, "debug-skill"))
        self.assertEqual(ctx.active_skills, [])
        ctx.cfg["skill_mode"] = "auto"
        self.assertTrue(activate_skill(ctx, "debug-skill"))
        self.assertEqual(ctx.active_skills, ["debug-skill"])

    def test_the_mode_command(self):
        ctx = make_ctx()
        with mock.patch("lumo.commands.save_config"):
            handle_command(ctx, "/skill mode auto")
            self.assertEqual(skill_mode(ctx), "auto")
            handle_command(ctx, "/skill mode ai")
            self.assertEqual(skill_mode(ctx), "ai")


class RicherPlans(unittest.TestCase):
    def submit(self, ctx=None, **kw):
        ctx = ctx or make_ctx()
        args = dict({"title": "Parcel Run", "summary": "2D game", "steps": [{"title": "Write the loop", "verify": "page_check shows draw calls"}, {"title": "Add the menu", "verify": "menu opens"}]}, **kw)
        return ctx, TOOLS["submit_plan"]["fn"](args, ctx)

    def test_new_fields_are_stored_and_written_to_the_markdown(self):
        ctx, res = self.submit(acceptance=["Opening index.html shows the board"], risks=["Touch input on small screens"], assumptions=["Portrait layout"],
                               out_of_scope=["Online leaderboard"], features=["Menu"])
        p = ctx.plan
        self.assertEqual(p["acceptance"], ["Opening index.html shows the board"])
        self.assertEqual(p["steps"][0]["verify"], "page_check shows draw calls")
        md = plan_markdown(p)
        for head in ("## Done when", "## Risks", "## Assumptions", "## Out of scope"):
            self.assertIn(head, md)
        self.assertIn("(check: menu opens)", md)
        self.assertTrue(ctx.plan_active)

    def test_features_without_a_step_are_called_out(self):
        _ctx, res = self.submit(features=["Menu and pause screen", "Strawberries spawn every few seconds"])
        self.assertIn("Plan check", res)
        self.assertIn("Strawberries", res)
        self.assertNotIn("Menu and pause", res.split("Plan check")[1])

    def test_a_plan_with_one_step_is_sent_back(self):
        with self.assertRaises(ToolError):
            TOOLS["submit_plan"]["fn"]({"title": "T", "summary": "S", "steps": ["only one step"]}, make_ctx())

    def test_long_plans_are_cut_at_the_limit(self):
        _ctx, _res = self.submit(steps=["step number %d" % i for i in range(30)])
        self.assertEqual(len(_ctx.plan["steps"]), PLAN_MAX_STEPS)
        self.assertEqual(PLAN_MAX_STEPS, 12)

    def test_the_planning_prompt_teaches_the_method(self):
        text = (ROOT / "prompts" / "plan-prompt.md").read_text(encoding="utf-8")
        for needle in ("Acceptance criteria", "Risk first", "verify", "out_of_scope", "walking skeleton"):
            self.assertIn(needle, text)


class License(unittest.TestCase):
    def test_apache_license_and_notice(self):
        lic = (ROOT / "LICENSE").read_text(encoding="utf-8")
        for needle in ("Apache License", "Version 2.0, January 2004", "3. Grant of Patent License.", "6. Trademarks.", "8. Limitation of Liability.",
                       "END OF TERMS AND CONDITIONS", "Copyright 2026 alfar988"):
            self.assertIn(needle, lic)
        self.assertNotIn("MIT License", lic)
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("Copyright 2026 alfar988", notice)
        self.assertIn("MIT", notice)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Apache License 2.0", readme)
        self.assertIn("/checklimit", readme)
        self.assertIn("## Providers and keys", readme)

    def test_changelog_matches_the_version(self):
        from lumo.config import VERSION
        self.assertTrue(re.search(r"## \[%s\]" % re.escape(VERSION), (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
