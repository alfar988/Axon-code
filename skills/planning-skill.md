---
name: planning-skill
description: Plan a project before building it: goal, testable features, architecture, ordered small steps, risks and a verification plan.
---
# Planning skill

Use it for anything with more than one part: a game, an app, a website, an API, a bot, a refactor.

## Method
1. **Goal in one sentence**, then constraints: where it runs (phone browser, Termux, PC), one file or many, offline or online, language, size limits.
2. **Features as checks, not adjectives.** "The player loses a life when a hazard touches them", not "fun gameplay". 8 to 20 items, each something you can verify.
3. **Assumptions.** Pick a sensible default for everything the user did not say and write it down. Ask (ask_user) only when a wrong guess would waste the whole build, and ask once.
4. **Start from what exists.** Run `use_template(name="list")`. If a template fits (game-2d, game-3d, web-landing, web-app) the plan becomes "adapt the template", which removes the riskiest 70% of the work. Also look at the workspace first (project_overview).
5. **Architecture in 5 to 10 lines:** the files and what each owns, and the data flow (input -> state -> update -> render, or request -> validate -> store -> respond).
6. **Risk first.** Find the hardest or least certain part (a library API, physics, auth, touch input, a data source). Schedule it in the first third and prove it alone before building on top of it.
7. **Steps: 6 to 14.** Each is small (one write_file part within the current line limit, or one command) and ends with a visible result. The last step is verification.
8. **Verification plan.** For every important feature, how you will prove it: verify_files, a command, review_ui, a curl call, preview_web.

## Example: the argument shape for submit_plan
```json
{
  "title": "Bunny Garden",
  "summary": "Single-file 2D game for phones. Assumptions: portrait layout, no external assets, best score kept in localStorage.",
  "features": [
    "Bunny moves with a touch joystick (left) and keyboard (WASD/arrows)",
    "Carrots (10 pts), strawberries (20), flowers (30) spawn and expire",
    "Bees drift across the screen; touching one costs a life and shakes the screen",
    "Combo multiplier rises when pickups are chained within 2 seconds",
    "Difficulty ramps: faster bees and more spawns every 40 seconds",
    "Menu, pause, game over with best score; one tap to restart"
  ],
  "architecture": "index.html only. Engine from the game-2d template (loop, input, audio, particles). Game content is data in CONFIG plus draw functions for bunny, items and bees.",
  "files": [{"path": "index.html", "purpose": "whole game"}],
  "steps": [
    "use_template game-2d as index.html and set title and accent",
    "Re-theme CONFIG and colors; rename entities (orb -> carrot, hazard -> bee)",
    "Write drawBunny/drawCarrot/drawBee with canvas paths",
    "Add strawberry and flower types with different values and lifetimes",
    "Tune spawn rates and the difficulty ramp",
    "verify_files, review_ui, then preview_web and fix what they report"
  ],
  "research_notes": "Template engine already handles resize, DPR, touch, audio unlock and pause on tab hide.",
  "verification": "verify_files clean; review_ui score >= 85; manual: collect each item type, get hit, pause, restart."
}
```

## Plan quality checklist
- Every feature maps to at least one step, every step to a file.
- No step depends on something built later.
- Research notes hold exact versions and URLs, not vague advice.
- Scope matches the request: no accounts, databases, frameworks or build tools nobody asked for.
- The riskiest assumption is tested early.

## Estimating and scope
- One write_file/append_file part of about 100 lines is one step. A 600-line app is 6 to 8 steps plus checks.
- When the request is large, build a thin vertical slice first (it runs end to end), then widen it. A game that starts, plays and ends beats a game with ten half-written features.
- Cut, do not stretch: if something is not in the request and not needed for it, leave it out and mention it as an option at the end.

## While building
- Keep `todo` identical to the plan steps; exactly one item `in_progress`.
- If reality contradicts the plan (an API is missing, a device limit appears) say so in one line, change the affected steps, continue. Do not silently drop features.
- When all steps are done, run the verification plan and report: what exists, how to run it, what was left out and why.

## Troubleshooting a plan
| Symptom | Fix |
|---|---|
| Steps are vague ("implement the game") | Split until each step produces one visible change |
| Everything depends on one uncertain part | Move it first and test it in isolation |
| The plan keeps growing | Freeze features, move extras to a "later" list |
| Research gives conflicting advice | Prefer the official docs for the exact version you load, note the source in research_notes |
