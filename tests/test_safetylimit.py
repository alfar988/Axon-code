"""The two hidden limit savers: /safelimit (balanced, level 1) and /safetylimit (maximum, level 2)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LUMO_HOME", tempfile.mkdtemp(prefix="lumo_test_home_"))

import lumo.tools  # noqa: E402,F401  (registers the tools)
from lumo import agent, safelimit  # noqa: E402
from lumo.commands import HELP, SLASH, handle_command  # noqa: E402
from lumo.config import WEB_TOOLS, PLAN_MAX_STEPS  # noqa: E402
from lumo.models import guard_context, out_budget  # noqa: E402
from lumo.prompts import SAVER_NOTE, build_system, skill_budget  # noqa: E402
from lumo.state import Ctx  # noqa: E402
from lumo.toolcalls import slim_schemas  # noqa: E402
from lumo.tools.registry import TOOLS  # noqa: E402
from lumo.util import cap  # noqa: E402


def big_convo(pairs, size=3000):
    msgs = []
    for i in range(1, pairs + 1):
        msgs.append({"role": "user", "content": "question %d " % i + "y" * size})
        msgs.append({"role": "assistant", "content": "answer %d " % i + "x" * size})
    return msgs


class SaverLevels(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="lumo_lvl_"))
        self.ctx = Ctx({"model": "x/y"}, self.ws)
        safelimit.set_level({}, 0)

    def tearDown(self):
        safelimit.set_level({}, 0)
        shutil.rmtree(str(self.ws), True)

    def test_both_commands_stay_hidden(self):
        for word in ("safelimit", "safetylimit"):
            self.assertNotIn("/" + word, SLASH)
            self.assertNotIn(word, HELP)
            self.assertNotIn(word, (ROOT / "README.md").read_text(encoding="utf-8").lower())

    def test_commands_switch_levels_and_save(self):
        with mock.patch("lumo.commands.save_config") as save:
            handle_command(self.ctx, "/safetylimit")
            self.assertEqual(safelimit.level(), 2)
            self.assertEqual(self.ctx.cfg["safelimit"], 2)
            handle_command(self.ctx, "/safelimit")                 # the other command selects its own level
            self.assertEqual(safelimit.level(), 1)
            self.assertIs(self.ctx.cfg["safelimit"], True)
            handle_command(self.ctx, "/safelimit")                 # typed again: off
            self.assertEqual(safelimit.level(), 0)
            self.assertIs(self.ctx.cfg["safelimit"], False)
            handle_command(self.ctx, "/safetylimit on")
            handle_command(self.ctx, "/safetylimit")               # typed again: off
            self.assertEqual(safelimit.level(), 0)
            handle_command(self.ctx, "/safetylimit on")
            handle_command(self.ctx, "/safelimit off")             # off always means off
            self.assertEqual(safelimit.level(), 0)
            saved = save.call_count
            handle_command(self.ctx, "/safetylimit status")
            self.assertEqual(save.call_count, saved)
            handle_command(self.ctx, "/safetylimit nonsense")
            self.assertEqual(save.call_count, saved)

    def test_saved_choice_is_loaded(self):
        for saved, level in (({"safelimit": 2}, 2), ({"safelimit": True}, 1), ({"safelimit": False}, 0), ({}, 0),
                             ({"safelimit": "x"}, 0), ({"safelimit": 7}, 2)):
            safelimit.load(saved)
            self.assertEqual(safelimit.level(), level, saved)

    def test_maximum_limits_are_stricter_than_balanced(self):
        text = "x" * 20000
        safelimit.set_level({}, 1)
        balanced = (len(cap(text)), out_budget(self.ctx, "x/y", []), skill_budget(self.ctx, "build"))
        safelimit.set_level({}, 2)
        maximum = (len(cap(text)), out_budget(self.ctx, "x/y", []), skill_budget(self.ctx, "build"))
        for lo, hi in zip(maximum, balanced):
            self.assertLess(lo, hi)
        self.assertLessEqual(maximum[0], safelimit.MAXIMUM["tool_output"] + 60)
        self.assertLessEqual(maximum[1], safelimit.MAXIMUM["out_tokens"])

    def test_the_prompt_is_much_smaller_and_keeps_the_safety_rules(self):
        (self.ws / "history").mkdir()
        (self.ws / "history" / "notes.md").write_text("a note about the project. " * 300, encoding="utf-8")
        sizes = {}
        for lvl in (0, 1, 2):
            safelimit.set_level({}, lvl)
            text = build_system(self.ctx, "build")
            sizes[lvl] = len(text)
            self.assertIn("Safety rules (always on)", text)
            self.assertEqual(SAVER_NOTE in text, lvl == 2)
        self.assertEqual(sizes[1], sizes[0])
        self.assertLess(sizes[2], sizes[0] * 0.8)

    def test_short_lists_still_name_every_skill_and_template(self):
        safelimit.set_level({}, 2)
        text = build_system(self.ctx, "build")
        self.assertIn("use_skill(name)", text)
        for name in ("database-skill", "safety-skill", "game-2d", "api-python"):
            self.assertIn(name, text)

    def test_rarely_used_tools_come_back_when_the_request_mentions_them(self):
        self.assertEqual(safelimit.hidden_tools("make a snake game"), set())      # off: nothing is hidden
        safelimit.set_level({}, 2)
        quiet = safelimit.hidden_tools("make a snake game")
        self.assertTrue({"create_archive", "download_file", "deep_research", "copy_path", "create_skill"} <= quiet)
        self.assertNotIn("create_archive", safelimit.hidden_tools("zip the project folder"))
        self.assertNotIn("download_file", safelimit.hidden_tools("download https://example.com/a.png"))
        self.assertNotIn("copy_path", safelimit.hidden_tools("salin file ini"))
        for name in quiet:
            self.assertIn(name, TOOLS)                                 # no typo in the list
        for core in ("write_file", "edit_file", "read_file", "run_shell", "verify_files", "use_skill", "use_template", "submit_plan"):
            self.assertNotIn(core, quiet)

    def test_tight_schemas_are_smaller_and_the_write_tools_keep_their_text(self):
        schemas = [t["schema"] for t in TOOLS.values()]
        normal, tight = slim_schemas(schemas), slim_schemas(schemas, tight=True)
        self.assertLess(len(json.dumps(tight)), len(json.dumps(normal)))
        by = lambda lst: {s["function"]["name"]: s for s in lst}
        for name in ("write_file", "edit_file", "run_shell", "use_template"):
            self.assertEqual(by(tight)[name], by(normal)[name])
        for s in tight:                                                # strict providers need non-empty properties
            self.assertTrue(s["function"]["parameters"]["properties"])

    def test_old_history_is_archived_by_itself_at_the_maximum_level_only(self):
        self.ctx.messages = big_convo(20)
        safelimit.set_level({}, 1)
        with mock.patch("lumo.models.compact_history"):
            guard_context(self.ctx, "build")
        self.assertFalse((self.ws / "history" / "archive").exists())
        self.ctx.messages = big_convo(20)
        safelimit.set_level({}, 2)
        guard_context(self.ctx, "build")
        self.assertLess(len(self.ctx.messages), 20)
        self.assertEqual(len(list((self.ws / "history" / "archive").glob("compact-*.md"))), 1)
        self.assertTrue(self.ctx.messages[0]["content"].startswith("[Earlier conversation archived"))

    def test_planning_has_no_web_research_at_the_maximum_level(self):
        seen = []

        def fake_run_agent(ctx, phase, allowed, steps, stop_tool=None):
            seen.append((set(allowed), steps))
            return "done"
        with mock.patch.object(agent, "run_agent", side_effect=fake_run_agent):
            agent.plan_phase(self.ctx, "build a game")
            safelimit.set_level({}, 2)
            agent.plan_phase(self.ctx, "build a game")
        normal_tools, normal_steps = seen[0]
        max_tools, max_steps = seen[2]
        self.assertTrue(normal_tools & WEB_TOOLS)
        self.assertEqual(normal_steps, PLAN_MAX_STEPS)
        self.assertFalse(max_tools & WEB_TOOLS)
        self.assertEqual(max_steps, safelimit.MAXIMUM["plan_steps"])


if __name__ == "__main__":
    unittest.main()
