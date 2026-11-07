"""/compact: move the older part of the conversation out of the model's context and into the workspace.

Everything before the newest COMPACT_KEEP messages is written to <workspace>/history/archive/compact-<time>.md and is
removed from the history that is sent to the model, so every later request carries far fewer tokens. Nothing is deleted:
the archive holds the full text, and history/transcript.md keeps a running log of the whole session. If the archive cannot
be written, nothing is removed.

No model request is made, so this also works when the key has hit its rate limit. (/compact summary is the older way:
the model writes a summary of the earlier conversation.)
"""

import os
import time

from lumo.config import COMPACT_KEEP
from lumo.memory import hist_dir, log_event, save_history
from lumo.models import est_tokens
from lumo.ui import dim, err, ok, out

NOTE_PREFIX = "[Earlier conversation archived"
SUMMARY_PREFIX = "[Summary of the earlier conversation]"
ACK = "Understood. I will continue from the newest messages and open the archive only if I need an older detail."


def cut_index(msgs, keep=COMPACT_KEEP):
    """Where the kept part starts: the newest `keep` messages, moved back so that a tool result never starts it
    (a tool result needs the assistant message that asked for it)."""
    cut = len(msgs) - keep
    while cut > 0 and msgs[cut].get("role") == "tool":
        cut -= 1
    return max(cut, 0)


def _clip(text, n=400):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def _is_note(m):
    c = str(m.get("content") or "")
    return m.get("role") == "user" and (c.startswith(NOTE_PREFIX) or c.startswith(SUMMARY_PREFIX))


def _first_request(old):
    """The request that started the conversation. An earlier note already carries it, so reuse that."""
    for m in old:
        c = str(m.get("content") or "")
        if _is_note(m):
            for line in c.splitlines():
                if line.startswith("First request: "):
                    return line[len("First request: "):]
        elif m.get("role") == "user" and c.strip():
            return _clip(c)
    return ""


def _last_request(old):
    for m in reversed(old):
        if m.get("role") == "user" and not _is_note(m) and str(m.get("content") or "").strip():
            return _clip(m.get("content"))
    return ""


def note_text(ctx, old, rel_path, keep_count):
    """What the model sees in place of the archived messages. It points to the archive and keeps the thread of the work."""
    lines = ["%s: %d messages moved to %s]" % (NOTE_PREFIX, len(old), rel_path),
             "Only the newest %d messages stay in this conversation, to save tokens. If you need an earlier detail, read that "
             "file instead of asking the user to repeat it. All archives are in history/archive/." % keep_count]
    first, last, task = _first_request(old), _last_request(old), _clip(getattr(ctx, "task", ""))
    if first:
        lines.append("First request: " + first)
    if last and last != first:
        lines.append("Last request before the cut: " + last)
    if task and task not in (first, last):
        lines.append("Current task: " + task)
    return "\n".join(lines)


def write_archive(ctx, old, total, kept):
    """Write the older messages to history/archive/. Returns the path, or None if it could not be written."""
    try:
        d = hist_dir(ctx) / "archive"
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = d / ("compact-%s.md" % stamp)
        n = 1
        while path.exists():                                   # two compactions in the same second
            n += 1
            path = d / ("compact-%s-%d.md" % (stamp, n))
        lines = ["# Lumo Code conversation archive", "",
                 "Archived: %s · %d older messages (of %d) · the newest %d stay in the conversation" % (
                     time.strftime("%Y-%m-%d %H:%M:%S"), len(old), total, kept),
                 "Workspace: %s" % ctx.ws,
                 "A running log of the whole session is also kept in history/transcript.md.", ""]
        for i, m in enumerate(old, 1):
            lines.append("### %d · %s" % (i, m.get("role", "?")))
            c = m.get("content")
            if c:
                lines.append(str(c)[:20000])
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                lines.append("**tool_call** `%s` %s" % (fn.get("name"), str(fn.get("arguments"))[:20000]))
            lines.append("")
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        os.replace(str(tmp), str(path))
        return path
    except Exception:
        return None


def _k(n):
    return "%.1fk" % (n / 1000.0) if n >= 1000 else str(n)


def compact_archive(ctx, keep=COMPACT_KEEP, quiet=False):
    """Archive every message except the newest `keep`. Returns True when something was archived.
    quiet: print one dim line instead of the full report (used by the automatic archive of the maximum limit saver)."""
    msgs = ctx.messages
    cut = cut_index(msgs, keep)
    if cut <= 0:
        if not quiet:
            out("  " + dim("only %d messages so far: nothing to archive (/compact keeps the newest %d)." % (len(msgs), keep)))
        return False
    old, kept = msgs[:cut], msgs[cut:]
    if all(_is_note(m) or (m.get("role") == "assistant" and m.get("content") == ACK) for m in old):
        if not quiet:
            out("  " + dim("already compacted: only the note and the newest %d messages are left." % len(kept)))
        return False
    save_history(ctx, "before-compact")                         # flush everything to history/transcript.md first
    path = write_archive(ctx, old, len(msgs), len(kept))
    if path is None:
        out("  " + err("could not write the archive in %s. Nothing was removed." % hist_dir(ctx)))
        return False
    rel_path = os.path.relpath(str(path), str(ctx.ws))
    before = est_tokens(msgs)
    head = [{"role": "user", "content": note_text(ctx, old, rel_path, len(kept))}]
    if kept[0].get("role") == "user":
        head.append({"role": "assistant", "content": ACK})      # keep user / assistant alternating
    ctx.messages = head + kept
    ctx.hist_count = len(ctx.messages)
    log_event(ctx, "conversation compacted: %d older messages archived to %s" % (len(old), rel_path))
    save_history(ctx, "compact")
    if quiet:
        out("  " + dim("older history archived: %d messages → %s (about %s → %s tokens)" % (
            len(old), rel_path, _k(before), _k(est_tokens(ctx.messages)))))
        return True
    out("  " + ok("✓ conversation compacted"))
    out("    " + dim("archived %d older messages → %s" % (len(old), rel_path)))
    out("    " + dim("kept the newest %d messages · about %s → %s tokens (estimate)" % (len(kept), _k(before), _k(est_tokens(ctx.messages)))))
    return True
