# Changelog

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
- The startup banner is a plain header; `/abilities` is now `What Axion Code can do`.
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
