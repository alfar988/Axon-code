# Changelog

## [1.7.0] - 2026-11-07

### Added
- Four new game templates built on one shared engine kit (canvas scaling, clamped time step, keyboard, pointer and on-screen buttons, HUD, start, pause and game-over screens, guarded best score, optional sound): `game-snake`, `game-breakout`, `game-runner` and `game-flappy`.
- The Node harness now plays every template that uses the kit (presses keys, drags, plays until game over, restarts, pauses) and fails on errors or NaN values, and the page check runs for every shipped HTML template instead of a fixed list.

## [1.6.0] - 2026-11-07

### Added
- A second hidden limit saver for the strictest case. It is not listed in `/help`, in Tab completion or in this README. The existing one keeps its name and its balanced behavior (level 1). The new one is the maximum level (level 2): everything level 1 does, with smaller limits, and it also shortens the skill and template lists in the prompt, cuts notes and project text to under half, shortens tool descriptions, leaves out rarely used tools unless the request mentions what they do, archives old history by itself the way `/compact` does (no model request), plans without web research, and asks the model for short answers and as few tool calls as possible. On a typical build request each request is about 30 percent smaller before any history (measured: 16.4k to 11.2k estimated tokens). Error fixing, automatic verification, the template check and the safety rules stay on at every level.
- The saved choice is `false`, `true` (level 1) or `2` (level 2) in `config.json`; older configs keep working.

## [1.5.0] - 2026-11-07

### Added
- `/compact` now archives the older part of the conversation. Everything except the newest 15 messages is written to `history/archive/compact-<time>.md` and removed from the history that is sent to the model, so every later request is smaller and the key reaches its limit later. Nothing is deleted: the archive holds the full text and `history/transcript.md` keeps the session log. No model request is used, so it works when the key is rate-limited, and if the archive cannot be written nothing is removed. A short note takes the place of the archived messages: it names the archive and repeats the first request, the last request before the cut and the current task.
- `/compact summary` keeps the earlier behavior, where the model writes a summary of the earlier conversation. Automatic compaction is unchanged.

## [1.4.0] - 2026-11-06

### Changed
- The project is now called Lumo Code (it was Axion Code). The Python package is `lumo`, settings live in `~/.lumo`, the project file is `LUMO.md` and the environment variables start with `LUMO_`. Existing installs keep working: `AXION_*` / `AXON_*` variables, `~/.axion` (copied once into `~/.lumo`, the old folder stays) and `AXION.md` are still read.
- Startup shows a new LUMO wordmark with a color gradient (two sizes for narrow phone screens, plain ASCII fallback, no color when `NO_COLOR` is set). `assets/lumo-banner.svg` is the same logo for the README.
- The six imported skills keep their text; only the assistant's name changed from Axion AI to Lumo AI, and their checksums in the tests were updated.
- Example projects in the guides and the README no longer use the playful bunny theme.

### Added
- All 25 built-in guides were extended. Each now opens with "Quick rules (read first)" and a safety note written for that topic, and ends with good and bad examples, common mistakes with fixes, and a checklist. The runnable examples are executed by the test suite.
- A new guide, `safety-skill`, with refusal and jailbreak examples (good and bad answers), prompt-injection handling and a decision test for doubtful requests.
- Safety layers: `prompts/safety-rules.md` is part of every prompt (refusals, jailbreak tricks, prompt injection, secrets), `skills/safety-skill.md` explains how to apply it with good and bad examples, and `lumo/guard.py` refuses blatant requests for malware, fraud tools or weapons before any model request is spent. Defensive and educational wording passes.
- A hidden limit saver for rate-limited keys. It is not listed in `/help`, in Tab completion or in this README.

## [1.3.0] - 2026-11-05

### Added
- More AI providers: Anthropic (native Messages API), xAI (Grok), OpenAI, Google Gemini, Groq, Mistral, DeepSeek, Together, Cerebras, Fireworks, NVIDIA NIM, Ollama, LM Studio and any OpenAI-compatible URL. Each provider has its own key and remembered model. `/provider`, `/key [provider]` and `--provider` manage them.
- `/checklimit` shows the remaining allowance: credits, free daily quota and rate limit for OpenRouter, and rate-limit headers for the other providers. `/checklimit probe` reads them with one small request.
- The model list is refreshed in the background every 12 hours and sorted by estimated capability. Offline, the last list is kept.
- Plans carry acceptance criteria, risks, assumptions, out-of-scope items and a check for every step. A plan check reports features that no step mentions.
- `NOTICE` file.

### Changed
- The AI chooses skills itself with `use_skill` (several names at once). `/skill mode auto` restores automatic selection.
- The license is now Apache-2.0 (was MIT): explicit patent grant, notice preservation and no trademark grant. Copies released earlier under MIT stay under MIT.
- Question-and-answer mode and the planning prompt were rewritten; `PLAN_MAX_STEPS` is 12.
- Models that reject `max_tokens` or `temperature` (newer OpenAI models) are detected once and remembered.
- Fallback models are on by default only for OpenRouter's free models; paid providers switch only when `/rotate` is on.

## [1.2.0] - 2026-11-01

### Added
- `reasoning-skill` for hard questions: restate, choose a method, compute and cross-check instead of guessing, and answer in a short fixed shape. Runnable examples cover exact arithmetic, enumeration and seeded simulation.
- `algorithms-skill`: constraints to complexity target to pattern, brute force first, a stress-test helper that shrinks failing inputs, and reference code for binary search on the answer, sliding window, prefix sums, Dijkstra, BFS, union-find, topological sort, dynamic programming, intervals and backtracking. `tests/test_skill_algorithms.py` cross-checks every function against brute force.
- `scripts/page_check.js` loads an HTML page in a stub browser at portrait and landscape sizes and reports exceptions, canvas size and draw calls per frame, so a blank or frozen screen is found before the user sees it.
- Question-and-answer mode can use `run_python` for calculations and brute-force checks. It asks for approval as usual and is told never to change files.

### Changed
- Skills, templates and prompts no longer demand extra features. The "at least two mechanics beyond the template" lists, the "minimum bar" in `game-skill` and the planning rule for features beyond a template are replaced by rules that follow the request: adapt the template to what the user described and add nothing they did not ask for.
- `code-quality-skill` opens with a work order (read first, list requirements, pick examples, smallest design, small steps, review the diff) and checks every requirement against evidence.
- `debug-skill` covers empty canvases, bugs that appear only in landscape, smeared text, wrong results without errors and regressions.
- `game-skill` has a first-frame checklist. `design-skill` keeps small edits small and keeps text crisp.

## [1.1.1] - 2026-11-01

### Fixed
- The agent no longer works on files outside the current request. The automatic UI review used to fall back to every HTML page in the workspace when the request had changed none, so an unrelated request could end with edits to an old page. Automatic checks now look only at files the request created or changed, and the UI review runs for build requests only.
- The plan, todo list and automatic instructions of earlier work no longer carry over to a new request, and skills picked for earlier work are not reused. `continue`, `lanjut` and `/resume` still resume unfinished work, and `/resume` no longer starts a new plan.
- The type of files in the workspace no longer selects a skill on its own.
- The verification header is not printed when only notes or data files changed.

### Changed
- The prompts state the current request and a scope rule: leave other files alone, create only the files the task needs, keep new files inside the workspace, and report unrelated problems instead of fixing them.
- Saved notes are marked as reference material that may belong to earlier work.

### Added
- `tests/test_scope.py`: regression tests, including a session against a fake server that reproduces the reported behavior.

## [1.1.0] - 2026-10-30

### Added
- Multi-provider web search with automatic fallback, caching and rank fusion (`web_search`), kinds for news, code, Q&A, docs, packages, papers, wiki and discussion, and optional Brave, Tavily, Serper and SearXNG backends.
- `deep_research`: several queries in parallel, pages read in parallel, matching passages returned with dates and source URLs.
- `package_info`: latest version, release date, requirements and install command from PyPI, npm and crates.io.
- `web_fetch` accepts several URLs and reads them in parallel; independent web lookups in one model response run in parallel.
- Lessons that persist between sessions (`learn`, `recall`, `/lessons`) and agent-written skills (`create_skill`, always approved by the user). After a turn that fixed an error the agent is asked once whether anything is worth keeping.
- Commands `/search`, `/dig` and `/lessons`.
- Twelve skills with runnable examples: research, testing, security, database, git, javascript, command-line tools, scraping, bots, performance, documentation, self-improvement.
- Eight templates: game-puzzle, dashboard, docs-site, api-python, api-node, cli-python, bot-telegram, scraper-python.
- Tests for search providers, lessons, learned skills, skill examples and code templates.

### Changed
- Prompts: neutral wording, an explicit research protocol, a debugging protocol and a learning step; the agent no longer adds self-promotion to what it generates.
- The startup banner is a plain header; `/abilities` is now `What Lumo Code can do`.
- Limit per user message raised from 40 to 60 steps.
- Template variables are escaped for string literals in code templates.
- External skills can declare `keywords:` in their front matter for routing.

### Fixed
- Compressed responses are decompressed with an output limit (a small download could expand without bound).
- Page text is decoded with the charset from the `<meta>` tag when the HTTP header has none.
- Timeouts and HTTP 429/5xx responses are retried once for GET requests.
- A search engine answering with an HTTP error was treated as "no results".
- Leftover non-English labels in the website audit output.
- The OpenRouter referer pointed to a repository name that does not exist.

## [1.0.0]

First public version.
