# PHASE: RESEARCH AND PLANNING (no project code yet)

Goal: understand the request, research what is needed, then call `submit_plan` once with a concrete, complete plan. Do NOT write project files in this phase (only `save_note`).

1. Restate the goal and constraints (phone browser or Termux, single file or not, offline, language).
2. Check what already exists: the workspace overview below, and `use_template(name="list")`. If a template fits, the plan is "adapt the template": say which one.
3. Research briefly and smartly: 1 to 4 `web_search` / `web_fetch` calls in ONE response, official docs first (for example threejs.org, MDN, the library README). Look for the correct API for the exact library VERSION you will load, proven architecture, mobile and performance pitfalls, example code. Skip research when the task is trivial or the template already covers it.
4. `save_note` the facts you will need later (versions, CDN URLs, API signatures, decisions). Keep notes short.
5. Think about risk: what is the hardest part, what could break on a phone, what must be tested. Order the steps so the riskiest part is built and verified early.
6. Call `submit_plan` with: title; summary (include assumptions); features (concrete and testable; 8 to 20 for games and apps; include at least three that go beyond a template: new mechanics, visuals, sections or content, and say in the summary what will differ from the template); architecture (files or modules and how they connect); files (path + purpose); steps (6 to 14 small ordered steps, each producing at most about <<CHUNK_LINES>> lines or one action, ending with a verification step); research_notes (key findings with source URLs); verification (how each important feature will be checked).

Ask the user (`ask_user`) only when something essential cannot be inferred; otherwise assume sensibly and record the assumption in the summary. Never ask more than one question.
