#!/usr/bin/env python3
"""__PROG__: __TITLE__

Usage:      python __PROG__.py add "Write the report" --tag work --due 2026-03-01
            python __PROG__.py list --open          python __PROG__.py done 1          python __PROG__.py rm 2 --yes
            python __PROG__.py export --format csv > tasks.csv       printf 'one\ntwo\n' | python __PROG__.py add -
Settings:   --file, or the environment variable named like the program in capitals plus _FILE (default __PROG__.json).
            NO_COLOR disables colors.
Exit codes: 0 success, 1 failure (message on stderr), 2 wrong usage, 130 interrupted.
Tests:      python __PROG__.py --run-tests

EDIT: the Task fields in make_task(), the subcommands in build_parser() and run(), the output in render().
"""

import argparse
import csv
import datetime
import io
import json
import logging
import os
import sys

PROG = "__PROG__"
VERSION = "1.0.0"
ENV_FILE = PROG.upper().replace("-", "_") + "_FILE"
log = logging.getLogger(PROG)


class CliError(Exception):
    """An expected problem: shown as one line without a traceback, exit code 1."""


# --- data ---------------------------------------------------------------------------------------
def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except ValueError as e:
        raise CliError("%s is not valid JSON (%s). Fix or delete the file." % (path, e))
    if not isinstance(data, list):
        raise CliError("%s does not contain a list of tasks" % path)
    return data


def save(path, tasks):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)                              # never leaves a half-written file


def make_task(text, tags, due):
    if due:
        try:
            datetime.date.fromisoformat(due)
        except ValueError:
            raise CliError("--due must look like 2026-03-01, got %r" % due)
    text = text.strip()
    if not text:
        raise CliError("the task text is empty")
    return {"text": text, "tags": sorted(set(tags)), "due": due or "", "done": False}


def pick(tasks, number):
    if not 1 <= number <= len(tasks):
        raise CliError("no task #%d (there are %d)" % (number, len(tasks)))
    return tasks[number - 1]


# --- output -------------------------------------------------------------------------------------
def color(text, code, stream):
    return text if os.environ.get("NO_COLOR") or not stream.isatty() else "\033[%sm%s\033[0m" % (code, text)


def render(tasks, out, as_json):
    if as_json:
        print(json.dumps(tasks, ensure_ascii=False), file=out)
        return
    if not tasks:
        print("(no tasks)", file=out)
    for n, t in tasks:
        mark = color("x", "32", out) if t["done"] else " "
        due = color(" due " + t["due"], "33", out) if t["due"] and not t["done"] else ""
        tags = " " + " ".join("#" + g for g in t["tags"]) if t["tags"] else ""
        print("%3d [%s] %s%s%s" % (n, mark, t["text"], due, tags), file=out)


# --- commands -----------------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(prog=PROG, description=__doc__.splitlines()[0].split(": ", 1)[1],
                                epilog="example: %s add 'Write the report' --tag work" % PROG)
    p.add_argument("--version", action="version", version="%s %s" % (PROG, VERSION))
    p.add_argument("--file", default=os.environ.get(ENV_FILE, PROG + ".json"), help="data file (env %s)" % ENV_FILE)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("-v", "--verbose", action="store_true", help="log details to stderr")
    p.add_argument("--run-tests", action="store_true", help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", metavar="command")
    a = sub.add_parser("add", help="add a task ('-' reads one task per line from stdin)")
    a.add_argument("text")
    a.add_argument("--tag", action="append", default=[], help="repeatable")
    a.add_argument("--due", help="date, YYYY-MM-DD")
    ls = sub.add_parser("list", help="show tasks")
    ls.add_argument("--open", action="store_true", help="only tasks that are not done")
    ls.add_argument("--tag", help="only tasks with this tag")
    d = sub.add_parser("done", help="mark a task done")
    d.add_argument("number", type=int)
    r = sub.add_parser("rm", help="remove a task")
    r.add_argument("number", type=int)
    r.add_argument("--yes", action="store_true", help="do not ask")
    e = sub.add_parser("export", help="write all tasks to stdout")
    e.add_argument("--format", choices=("json", "csv"), default="json")
    return p


def run(args, stdin, out):
    tasks = load(args.file)
    if args.cmd == "add":
        lines = [x for x in stdin.read().splitlines() if x.strip()] if args.text == "-" else [args.text]
        new = [make_task(x, args.tag, args.due) for x in lines]
        save(args.file, tasks + new)
        log.info("saved %d task(s) to %s", len(new), args.file)
        print(json.dumps(new, ensure_ascii=False) if args.json else "added %d task(s)" % len(new), file=out)
    elif args.cmd == "list":
        rows = [(n, t) for n, t in enumerate(tasks, 1) if (not args.open or not t["done"]) and (not args.tag or args.tag in t["tags"])]
        render([t for _, t in rows] if args.json else rows, out, args.json)
    elif args.cmd == "done":
        pick(tasks, args.number)["done"] = True
        save(args.file, tasks)
        print("task #%d marked done" % args.number, file=out)
    elif args.cmd == "rm":
        task = pick(tasks, args.number)
        if not args.yes:
            if not stdin.isatty():
                raise CliError("refusing to delete without --yes when input is not a terminal")
            if input("delete %r? [y/N] " % task["text"]).strip().lower() != "y":
                print("cancelled", file=out)
                return 0
        tasks.pop(args.number - 1)
        save(args.file, tasks)
        print("removed task #%d" % args.number, file=out)
    elif args.cmd == "export":
        if args.format == "json":
            print(json.dumps(tasks, ensure_ascii=False, indent=2), file=out)
        else:
            w = csv.writer(out)
            w.writerow(["text", "tags", "due", "done"])
            w.writerows([t["text"], " ".join(t["tags"]), t["due"], t["done"]] for t in tasks)
    return 0


def main(argv=None, stdin=None, out=None, err=None):
    stdin, out, err = stdin or sys.stdin, out or sys.stdout, err or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.run_tests:
        return run_tests()
    if not args.cmd:
        parser.print_help(out)
        return 2
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s", stream=err, force=True)
    try:
        return run(args, stdin, out)
    except CliError as e:
        print("error: %s" % e, file=err)
        return 1
    except OSError as e:
        print("error: %s" % e, file=err)
        return 1


# --- tests (python __PROG__.py --run-tests) -----------------------------------------------------
def run_tests():
    import tempfile
    import unittest

    class T(unittest.TestCase):
        def setUp(self):
            self.path = os.path.join(tempfile.mkdtemp(), "t.json")

        def call(self, *argv, stdin=""):
            out, err = io.StringIO(), io.StringIO()
            code = main(["--file", self.path] + list(argv), io.StringIO(stdin), out, err)
            return code, out.getvalue(), err.getvalue()

        def test_add_list_done_rm(self):
            self.assertEqual(self.call("add", "Write report", "--tag", "work")[0], 0)
            self.assertEqual(self.call("add", "-", stdin="one\n\ntwo\n")[1], "added 2 task(s)\n")
            code, text, _ = self.call("list", "--open")
            self.assertIn("Write report", text)
            self.assertIn("#work", text)
            self.assertEqual(self.call("done", "1")[0], 0)
            self.assertNotIn("Write report", self.call("list", "--open")[1])
            self.assertEqual(self.call("rm", "2", "--yes")[0], 0)
            self.assertEqual(len(json.loads(self.call("--json", "list")[1])), 2)

        def test_errors_are_one_line_with_exit_code_1(self):
            code, _, err = self.call("done", "5")
            self.assertEqual((code, err), (1, "error: no task #5 (there are 0)\n"))
            self.assertIn("--due", self.call("add", "x", "--due", "tomorrow")[2])
            self.assertEqual(self.call("rm", "1")[0], 1)

        def test_corrupt_file_is_reported(self):
            with open(self.path, "w") as f:
                f.write("{broken")
            code, _, err = self.call("list")
            self.assertEqual(code, 1)
            self.assertIn("not valid JSON", err)

        def test_csv_export(self):
            self.call("add", "a,b", "--tag", "x")
            self.assertEqual(self.call("export", "--format", "csv")[1].splitlines()[1], '"a,b",x,,False')

    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(T))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        print(file=sys.stderr)
        code = 130
    except BrokenPipeError:                            # `tool | head` closed the pipe
        code = 0
    sys.exit(code)
