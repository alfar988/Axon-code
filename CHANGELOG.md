# Changelog

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
