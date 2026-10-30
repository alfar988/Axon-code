---
name: docs-skill
description: Write READMEs, changelogs, docstrings and interface text in plain, professional English without hype: structure, wording rules, before and after rewrites, what to leave out.
---
# Docs skill

Documentation exists so a stranger can install, run and understand the project in a few minutes. Write it the way a careful colleague would explain it: concrete, short, honest about limits.

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
