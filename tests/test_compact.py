"""/compact: archive the older conversation in the workspace and keep the newest 15 messages."""

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

from lumo import compact  # noqa: E402
from lumo.commands import HELP, SLASH, handle_command  # noqa: E402
from lumo.models import est_tokens  # noqa: E402
from lumo.state import Ctx  # noqa: E402


def convo(pairs, prefix="q", pad=0):
    msgs = []
    for i in range(1, pairs + 1):
        msgs.append({"role": "user", "content": "%s%d" % (prefix, i)})
        msgs.append({"role": "assistant", "content": "answer %d %s" % (i, "x" * pad)})
    return msgs


def valid(msgs):
    """Every tool result follows the assistant message that asked for it; the history does not start with one."""
    asked = set()
    for i, m in enumerate(msgs):
        if m["role"] == "tool":
            if m.get("tool_call_id") not in asked:
                return False
        for tc in m.get("tool_calls") or []:
            asked.add(tc["id"])
    return msgs[0]["role"] != "tool"


def tool_turn():
    return [{"role": "user", "content": "build it"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "a", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
                {"id": "b", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "a", "content": "file a"},
            {"role": "tool", "tool_call_id": "b", "content": "file b"},
            {"role": "assistant", "content": "done"}]


class CompactTests(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="lumo_compact_"))
        self.ctx = Ctx({"model": "x/y"}, self.ws)

    def tearDown(self):
        shutil.rmtree(str(self.ws), True)

    def archives(self):
        return sorted((self.ws / "history" / "archive").glob("compact-*.md"))

    def test_keeps_the_newest_15_and_archives_the_rest(self):
        original = convo(15)                                   # 30 messages
        self.ctx.messages = list(original)
        self.assertTrue(compact.compact_archive(self.ctx))
        self.assertEqual(self.ctx.messages[1:], original[-15:])
        self.assertTrue(self.ctx.messages[0]["content"].startswith(compact.NOTE_PREFIX))
        files = self.archives()
        self.assertEqual(len(files), 1)
        text = files[0].read_text(encoding="utf-8")
        self.assertIn("q1", text)
        self.assertIn("answer 7", text)
        self.assertNotIn("answer 8", text)                     # that one is still in the conversation
        self.assertIn("history/archive/compact-", self.ctx.messages[0]["content"].replace(os.sep, "/"))

    def test_roles_keep_alternating(self):
        self.ctx.messages = convo(15) + [{"role": "user", "content": "one more"}]   # 31: the kept part starts with a user message
        compact.compact_archive(self.ctx)
        roles = [m["role"] for m in self.ctx.messages[:3]]
        self.assertEqual(roles, ["user", "assistant", "user"])
        self.assertEqual(len(self.ctx.messages), 17)

    def test_a_tool_result_never_starts_the_kept_part(self):
        self.ctx.messages = convo(4) + tool_turn() + convo(6, "z")[:12]   # index 25 - 15 = 10 is a tool result
        self.assertEqual(self.ctx.messages[len(self.ctx.messages) - 15]["role"], "tool")
        compact.compact_archive(self.ctx)
        self.assertTrue(valid(self.ctx.messages))
        self.assertEqual(self.ctx.messages[1]["role"], "assistant")
        self.assertTrue(self.ctx.messages[1].get("tool_calls"))
        self.assertEqual(len(self.ctx.messages), 1 + 16)

    def test_short_conversations_are_left_alone(self):
        self.ctx.messages = convo(7)                           # 14 messages
        before = list(self.ctx.messages)
        self.assertFalse(compact.compact_archive(self.ctx))
        self.assertEqual(self.ctx.messages, before)
        self.assertFalse((self.ws / "history" / "archive").exists())

    def test_no_model_request_is_made(self):
        self.ctx.messages = convo(20)
        with mock.patch("lumo.commands.compact_history", side_effect=AssertionError("the model was asked")):
            handle_command(self.ctx, "/compact")
        self.assertEqual(len(self.ctx.messages), 16)

    def test_summary_option_keeps_the_older_behavior(self):
        self.ctx.messages = convo(20)
        with mock.patch("lumo.commands.compact_history") as old_way:
            handle_command(self.ctx, "/compact summary")
        old_way.assert_called_once()
        self.assertEqual(len(self.ctx.messages), 40)

    def test_the_whole_conversation_stays_on_disk(self):
        self.ctx.messages = convo(20)
        compact.compact_archive(self.ctx)
        transcript = (self.ws / "history" / "transcript.md").read_text(encoding="utf-8")
        self.assertIn("q1", transcript)
        self.assertIn("answer 20", transcript)
        import json
        state = json.loads((self.ws / "history" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(len(state["messages"]), 16)           # a resumed session starts from the compacted history

    def test_the_note_keeps_the_thread_of_the_work(self):
        self.ctx.messages = convo(20)
        self.ctx.task = "build a parcel game"
        compact.compact_archive(self.ctx)
        note = self.ctx.messages[0]["content"]
        self.assertIn("First request: q1", note)
        self.assertIn("Last request before the cut: q13", note)
        self.assertIn("Current task: build a parcel game", note)
        self.ctx.messages += convo(20, "z")
        compact.compact_archive(self.ctx)
        self.assertIn("First request: q1", self.ctx.messages[0]["content"])   # carried over a second compaction
        self.assertEqual(len(self.archives()), 2)

    def test_fewer_tokens_are_sent(self):
        self.ctx.messages = convo(30, pad=1500)
        before = est_tokens(self.ctx.messages)
        compact.compact_archive(self.ctx)
        self.assertLess(est_tokens(self.ctx.messages), before / 2)

    def test_if_the_archive_cannot_be_written_nothing_is_removed(self):
        (self.ws / "history").write_text("this is a file, not a folder", encoding="utf-8")
        self.ctx.messages = convo(20)
        before = list(self.ctx.messages)
        self.assertFalse(compact.compact_archive(self.ctx))
        self.assertEqual(self.ctx.messages, before)

    def test_running_it_twice_in_a_row_does_nothing(self):
        self.ctx.messages = convo(20)
        compact.compact_archive(self.ctx)
        after_first = list(self.ctx.messages)
        self.assertFalse(compact.compact_archive(self.ctx))
        self.assertEqual(self.ctx.messages, after_first)
        self.assertEqual(len(self.archives()), 1)

    def test_command_is_listed_in_help_and_completion(self):
        self.assertIn("/compact", SLASH)
        self.assertIn("/compact [summary]", HELP)


if __name__ == "__main__":
    unittest.main()
