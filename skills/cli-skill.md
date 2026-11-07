---
name: cli-skill
description: Command-line programs people enjoy using: argparse subcommands, exit codes, stdout vs stderr, --json output, config precedence, stdin, Ctrl+C, packaging an entry point. Runnable Python example.
---
# CLI skill

## Quick rules (read first)
1. `--help` works and shows an example. Every option has a short description.
2. Results go to stdout, messages and errors go to stderr. Exit code 0 means success, 1 a runtime error, 2 bad usage.
3. Work when input comes from a pipe (`cat file | tool`) and when it comes from a file argument.
4. Do not ask questions when stdin is not a terminal. Take a `--yes` flag instead.
5. Anything that deletes or overwrites needs `--dry-run` and a confirmation.
6. Offer `--json` when another program may read the output.

## Safety in this skill
- A command that deletes, moves or overwrites files must show what it will do first and must stay inside the folder the user named.
- Do not write tools that run hidden in the background, add themselves to startup, capture keystrokes, or send data anywhere the user did not choose.

## Design rules
- Results go to stdout, messages and errors to stderr, so `tool | other` works.
- Exit code 0 on success, 1 for failures, 2 for bad usage (argparse does this), 130 after Ctrl+C.
- `--help` documents every option with an example. `--version` exists. `--json` gives machine-readable output.
- Quiet by default, `-v` for detail. Never print a stack trace for an expected problem (missing file, no network): one clear line saying what happened and what to do.
- Destructive actions ask first unless `--yes`. Dry run with `--dry-run`.
- Settings order: command-line flag, then environment variable, then config file, then default.

## A testable skeleton
`main(argv)` returns the exit code, so tests call it directly.
```python
# check: runs
import argparse
import json
import os
import sys

def build_parser():
    p = argparse.ArgumentParser(prog="notes", description="Small note keeper.", epilog="example: notes add 'buy milk' --tag home")
    p.add_argument("--version", action="version", version="notes 1.0")
    p.add_argument("--file", default=os.environ.get("NOTES_FILE", "notes.json"), help="data file (env NOTES_FILE)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="add a note")
    add.add_argument("text")
    add.add_argument("--tag", action="append", default=[], help="repeatable")
    sub.add_parser("list", help="list notes")
    rm = sub.add_parser("rm", help="remove a note by number")
    rm.add_argument("number", type=int)
    rm.add_argument("--yes", action="store_true", help="do not ask")
    return p

def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save(path, notes):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)                                   # never leaves a half-written file

def main(argv=None, out=sys.stdout, err=sys.stderr):
    args = build_parser().parse_args(argv)
    try:
        notes = load(args.file)
        if args.cmd == "add":
            notes.append({"text": args.text, "tags": args.tag})
            save(args.file, notes)
            print(json.dumps(notes[-1]) if args.json else "added #%d" % len(notes), file=out)
        elif args.cmd == "list":
            print(json.dumps(notes) if args.json else "\n".join("%d. %s" % (i, n["text"]) for i, n in enumerate(notes, 1)) or "(no notes)", file=out)
        elif args.cmd == "rm":
            if not 1 <= args.number <= len(notes):
                print("error: no note #%d (there are %d)" % (args.number, len(notes)), file=err)
                return 1
            if not args.yes and not sys.stdin.isatty():
                print("error: refusing to delete without --yes when input is not a terminal", file=err)
                return 1
            notes.pop(args.number - 1)
            save(args.file, notes)
        return 0
    except (OSError, ValueError) as e:                      # expected problems: one line, no traceback
        print("error: %s" % e, file=err)
        return 1

if __name__ == "__main__":
    import io, tempfile
    path = os.path.join(tempfile.mkdtemp(), "n.json")
    buf, errbuf = io.StringIO(), io.StringIO()
    assert main(["--file", path, "add", "buy milk", "--tag", "home"], buf, errbuf) == 0
    assert main(["--file", path, "--json", "list"], buf, errbuf) == 0
    assert "buy milk" in buf.getvalue()
    assert main(["--file", path, "rm", "7", "--yes"], buf, errbuf) == 1 and "no note #7" in errbuf.getvalue()
    print("cli ok")
```
(Run as a real program with `if __name__ == "__main__": sys.exit(main())` and no test lines.)

## Ctrl+C and pipes
```python
# at the program entry
try:
    code = main()
except KeyboardInterrupt:
    print(file=sys.stderr)
    code = 130
except BrokenPipeError:               # `tool | head` closed the pipe
    code = 0
sys.exit(code)
```

## Reading input
No file argument means read stdin: `data = sys.stdin.read() if args.path == "-" else open(args.path).read()`. Check `sys.stdin.isatty()` before prompting.

## Progress and color
Show progress on stderr only when `sys.stderr.isatty()`. Disable color when `NO_COLOR` is set or output is not a terminal.

## Package it
`pyproject.toml`:
```toml
[project]
name = "notes"
version = "1.0.0"
requires-python = ">=3.8"

[project.scripts]
notes = "notes.cli:main"
```
Then `pip install -e .` gives a `notes` command. For a single file: `chmod +x notes.py` and a `#!/usr/bin/env python3` first line.

## Good and bad examples

### 1. Arguments and exit codes
Bad: positional guessing and a bare traceback.
```python
import sys
n = int(sys.argv[1])            # IndexError or ValueError with no explanation
print(n * 2)
```
Good: argparse, a clear error and a return code.
```python
# check: runs
import argparse, sys

def main(argv=None):
    p = argparse.ArgumentParser(prog="double", description="Print a number times two.")
    p.add_argument("n", help="an integer, for example: 21")
    args = p.parse_args(argv)
    try:
        value = int(args.n)
    except ValueError:
        print("double: %r is not an integer" % args.n, file=sys.stderr)
        return 2
    print(value * 2)
    return 0

assert main(["21"]) == 0
assert main(["x"]) == 2
```

### 2. Destructive commands
Bad: `rm -rf "$DIR"/*` with an unchecked variable.
Good: list the files, show the count, ask `Delete 12 files? [y/N]`, accept `--yes`, and support `--dry-run`.

### 3. Output
Bad: progress text mixed into the data on stdout, which breaks pipes.
Good: data on stdout, progress on stderr, and no color codes when stdout is not a terminal.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Traceback on Ctrl+C | Catch `KeyboardInterrupt`, print one line, exit 130 |
| `BrokenPipeError` with `| head` | Catch it and exit quietly |
| Relative paths break in other folders | Resolve against the current directory, and print the path used |
| Config in three places, unclear winner | Order: flag, environment variable, config file, default; document it |
| Slow start | Import heavy modules inside the function that needs them |

## Checklist before you finish
- [ ] `--help` and a wrong argument were both tried.
- [ ] stdout holds only the result; errors go to stderr with the right exit code.
- [ ] It works with a pipe and with a file.
- [ ] Anything destructive has `--dry-run` and a confirmation.
- [ ] A test calls `main([...])` and checks output and return code.
