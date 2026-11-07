---
name: planning-skill
description: Plan a project before building it: goal, testable features, architecture, ordered small steps, risks and a verification plan.
---
# Planning skill

Use it for anything with more than one part: a game, an app, a website, an API, a bot, a refactor.

## Quick rules (read first)
1. Plan before you build anything that needs more than a few files or steps. For a small edit, just do it.
2. Write features as checks someone can test ("the player loses a life when a hazard touches them"), not adjectives ("fun gameplay").
3. Take features only from what the user asked for or clearly needs. List the rest under "not building".
4. Steps are small and ordered. Each step has a check that shows it worked.
5. Write down assumptions and the risks that could change the plan.
6. If reality differs from the plan, update the plan and say so. Do not keep following a plan that no longer fits.

## Safety in this skill
- A plan is only for work you would do. If the request is harmful or illegal, say so plainly instead of planning it.
- A plan never widens your permissions: no step that disables security, reads files outside the workspace or sends data away unless the user asked for exactly that.

## Method
1. **Goal in one sentence**, then constraints: where it runs (phone browser, Termux, PC), one file or many, offline or online, language, size limits.
2. **Features as checks, not adjectives.** "The player loses a life when a hazard touches them", not "fun gameplay". 6 to 15 items taken from the request, each something you can verify.
3. **Assumptions.** Pick a sensible default for everything the user did not say and write it down. Ask (ask_user) only when a wrong guess would waste the whole build, and ask once.
4. **Start from what exists.** Run `use_template(name="list")`. If a template fits (game-2d, game-3d, web-landing, web-app) the plan becomes "adapt the template", which removes the riskiest 70% of the work. Also look at the workspace first (project_overview).
5. **Architecture in 5 to 10 lines:** the files and what each owns, and the data flow (input -> state -> update -> render, or request -> validate -> store -> respond).
6. **Risk first.** Find the hardest or least certain part (a library API, physics, auth, touch input, a data source). Schedule it in the first third and prove it alone before building on top of it.
7. **Steps: 5 to 12.** Each is small (one write_file part within the current line limit, or one command), ends with a visible result and has a `verify`: the command or observation that proves it. The last step is the final verification.
9. **Acceptance, scope, risks.** `acceptance`: one observable check per requirement. `out_of_scope`: what you will not build because nobody asked. `risks`: the hardest parts and how you handle them (their step comes first). `assumptions`: few and sensible.
8. **Verification plan.** For every important feature, how you will prove it: verify_files, a command, review_ui, a curl call, preview_web.

## Example: the argument shape for submit_plan
```json
{
  "title": "Parcel Run",
  "summary": "Single-file 2D game for phones. Assumptions: portrait layout, no external assets, best score kept in localStorage.",
  "features": [
    "Courier moves with a touch joystick (left) and keyboard (WASD/arrows)",
    "Parcels (10 pts), envelopes (20), crates (30) spawn and expire",
    "Drones drift across the screen; touching one costs a life and shakes the screen",
    "Combo multiplier rises when pickups are chained within 2 seconds",
    "Difficulty ramps: faster drones and more spawns every 40 seconds",
    "Menu, pause, game over with best score; one tap to restart"
  ],
  "architecture": "index.html only. Engine from the game-2d template (loop, input, audio, particles). Game content is data in CONFIG plus draw functions for the courier, items and drones.",
  "files": [{"path": "index.html", "purpose": "whole game"}],
  "steps": [
    {"title": "use_template game-2d as index.html and set title and accent", "verify": "node scripts/page_check.js index.html reports draw calls in both sizes"},
    {"title": "Re-theme CONFIG and colors; rename entities (orb -> parcel, hazard -> drone)", "verify": "verify_files clean; the page still starts"},
    {"title": "Write drawCourier/drawParcel/drawDrone with canvas paths", "verify": "page_check shows the entities are drawn (draw calls up)"},
    {"title": "Add envelope and crate types with different values and lifetimes", "verify": "play: each pickup type scores its own value"},
    {"title": "Tune spawn rates and the difficulty ramp", "verify": "play 60 seconds: pressure rises, restart works"},
    {"title": "verify_files, review_ui, then preview_web and fix what they report", "verify": "no errors, review_ui score >= 85"}
  ],
  "acceptance": [
    "Opening index.html shows the street, the courier and the score at start, in portrait and landscape",
    "Each pickup type adds its own points and a drone hit costs a life",
    "Game over shows the best score and one tap restarts"
  ],
  "risks": ["Touch joystick on small screens: test it first with page_check and by hand"],
  "assumptions": ["Portrait layout, no external assets, best score kept in localStorage"],
  "out_of_scope": ["Online leaderboard", "Accounts", "Level editor"],
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

## Good and bad examples

### 1. Features
Bad: "Fun and addictive gameplay", "modern, beautiful UI".
Good: "Tapping a tile slides it; two equal tiles merge and add to the score", "The page fits a 360px screen without sideways scrolling".

### 2. Steps
Bad: "Build the app." (one giant step, no check)
Good: three small steps, each with a check.
```text
1. Add the board and the move rules   check: unit checks for slide() pass
2. Draw the board and handle swipes   check: page_check shows draw calls; a swipe moves tiles
3. Add score and best score           check: the best score survives a reload
```

### 3. Scope
Bad: the user asked for a to-do list and the plan includes accounts, sharing and a mobile app.
Good: the to-do list, with the polish it needs, and a short "not building" list: accounts, sharing.

### 4. Assumptions
Bad: silently guess "they want it in React".
Good: "Assumption: a single HTML file with no build step, because they did not name a framework."

### 5. Replanning
Bad: step 2 fails because the library has no such function, and you keep going.
Good: stop, note "the library has no X; using Y instead", change the later steps that depended on X.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Plan is longer than the work | Keep it to the steps you will really do, 3 to 12 |
| Steps depend on each other in a loop | Reorder so each step builds on finished ones |
| No check for a step | Add what you will run or open to prove it |
| Risks not written | Name the two most likely failures and how you will notice them |
| Everything is "high priority" | Put the must-haves first; the rest is "not building" |

## Checklist before you finish
- [ ] Every feature is a testable statement taken from the request.
- [ ] Every step is small and has a check.
- [ ] Assumptions, risks and "not building" are written.
- [ ] The plan was updated when something changed.
- [ ] At the end, each feature was checked against evidence.
