---
name: docs-skill
description: Write READMEs, changelogs, docstrings and interface text in plain, professional English without hype: structure, wording rules, before and after rewrites, what to leave out.
---
# Docs skill

Documentation exists so a stranger can install, run and understand the project in a few minutes. Write it the way a careful colleague would explain it: concrete, short, honest about limits.

## Quick rules (read first)
1. The first sentence says what the project is and who it is for. Then show how to run it.
2. Every command in the docs was run. Show the real output when it helps.
3. Short sentences, active voice, one idea per paragraph. Put the most useful part first.
4. Name actions in buttons and messages ("Save changes", not "Submit"). Errors say what happened and what to do next.
5. Leave out empty praise: powerful, seamless, blazing fast, revolutionary, effortless.
6. Keep a changelog entry for each change a user can notice.

## Safety in this skill
- Do not invent features, benchmarks, statistics, awards, customers or licenses. If you did not check a claim, leave it out or mark it as unchecked.
- Never put real keys, tokens, passwords or personal data in examples; use obvious fakes such as `sk-xxxx` or `user@example.com`. Do not copy someone else's documentation wholesale; link to it.

## README structure
1. **Name and one sentence** saying what it is and who it is for.
2. **Requirements** with versions.
3. **Install and run**: commands that work when copied, in order. Test them on a clean folder.
4. **Usage**: two or three real examples with the expected output.
5. **Configuration**: options, environment variables, defaults, in a table.
6. **How it works** (only if it helps): a short paragraph or a file map.
7. **Troubleshooting**: the three problems people actually hit, with the exact error text and the fix.
8. **Development**: how to run the tests, how to contribute.
9. **License**.
Leave out sections that have nothing to say. A short accurate README beats a long padded one.

## Wording rules
- Say what it does, then stop. Facts and examples carry the argument; adjectives do not.
- Imperative for instructions ("Run `python run.py`"), present tense for behavior ("The server listens on port 8000").
- Name exact commands, file names, versions and numbers. Never "some", "various", "etc." where you can list.
- State limits and what is not supported. Readers trust a README that admits them.
- No emoji, no exclamation marks, no slogans, no first-person marketing ("we are proud to").
- Avoid these empty words: powerful, seamless, blazing fast, robust, cutting-edge, revolutionary, state-of-the-art, next-generation, effortless, world-class, best-in-class, game-changing, supercharge, unleash, leverage, delve. Replace each with the measurable fact behind it, or delete it.
- Do not praise the tool or the author, and do not write badges, awards or fake statistics.

### Before and after
| Before | After |
|---|---|
| "A blazing fast, powerful next-gen tool that supercharges your workflow!" | "Converts Markdown files to HTML. Converts 1,000 files in about 2 seconds on a laptop." |
| "Seamlessly integrates with all major platforms." | "Runs on Linux, macOS and Termux. Windows works through WSL." |
| "Simply install and enjoy!" | "Install with `pip install notes`, then run `notes add 'buy milk'`." |
| "Robust error handling." | "Retries failed downloads three times and prints the failing URL." |

## Quick-start section that works
````markdown
## Quick start

```bash
git clone https://github.com/<user>/<repo>.git
cd <repo>
python run.py
```

On the first run the program asks for an API key and stores it in `~/.config/<repo>/config.json`.
````

## Code comments and docstrings
Comment why, not what. A docstring says what the function returns, what it raises and any surprising rule:
```python
def parse_price(text):
    """Return the price in cents. Accepts "12.50", "$12.5" and "12,50". Raises ValueError for anything else."""
```
Delete comments that restate the code. Keep TODO notes out of shipped files; open an issue instead.

## Changelog (Keep a Changelog style)
```markdown
## [1.2.0] - 2026-03-04
### Added
- `--json` output for `list`.
### Changed
- Downloads retry three times instead of once.
### Fixed
- Crash when the data file is empty.
```
Newest first, one line per change, written for users, with the date.

## Interface text (buttons, errors, empty states)
Name the action ("Save changes", not "Submit"). Errors say what happened and what to do ("Could not save: the disk is full. Free some space and try again."). Empty states explain the next step. No exclamation marks, no jokes, no "Oops!". Never write "built with AI" or similar footers unless asked.

## Check before you finish
Every command was run. Every path exists. Versions match `package_info` or the lock file. The README opens with what the project is, not with a logo or a badge row.

## Good and bad examples

### 1. The opening
Bad: "A powerful, next-generation toolkit that supercharges your workflow!"
Good: "notes is a command-line notebook. It stores plain text files in `~/notes` and finds them by keyword."

### 2. Quick start
Bad: "Just install it and go." (no commands)
Good:
```bash
pip install notes
notes add "buy milk"
notes find milk
```
with the real output shown under the last command.

### 3. Error messages
Bad: "Error 500" or "Something went wrong."
Good: "Could not save: the disk is full. Free some space and try again."

### 4. Buttons and empty states
Bad: a button labeled "Submit", and an empty list with no text.
Good: "Save changes", and "No notes yet. Add your first one with the button above."

### 5. Code comments
Bad: `i += 1  # add one to i`
Good: `# The API counts pages from 1, but our list starts at 0.`

### 6. Changelog
Bad: "Fixed stuff and improved performance."
Good: "Fixed: `notes find` no longer crashes when a note has no title. Changed: search is about 3x faster on 10,000 notes (measured on a laptop)." (only if you measured it)

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Instructions that were never run | Run them in a clean folder and paste what happened |
| One huge README | Quick start first; put details in sections or separate files |
| Out-of-date examples | Keep examples next to tests, or re-run them before release |
| Passive, vague steps | "Run `make test`", not "The tests may be run" |
| No requirements listed | State the language version and the operating systems you tried |
| Unexplained jargon | Define a word the first time, or use a plainer one |

## Check before you finish
- [ ] A new reader can run the quick start from top to bottom.
- [ ] Every command and output in the docs is real.
- [ ] No hype words, no invented numbers or customers.
- [ ] Errors and buttons tell people what to do.
- [ ] The changelog lists what changed for users.
