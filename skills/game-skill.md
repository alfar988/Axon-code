---
name: game-skill
description: Build complete browser games (2D canvas and 3D Three.js) as one HTML file: start from a tested template, re-theme it, add entities, polish game feel, and fix common problems.
---
# Game skill (browser games, single HTML file)

The goal is a game that starts, is fun in the first 20 seconds, runs smoothly on a phone, and never crashes. **Do not write the engine from scratch.** Two templates already contain a tested engine (fixed timestep, resize and DPR, touch joystick, keyboard, sound, particles, shake, states, best score):

```
use_template(name="game-2d", path="index.html", vars={"TITLE": "Parcel Run", "ACCENT": "#35c48f"})   # canvas 2D
use_template(name="game-3d", path="index.html", vars={"TITLE": "Gem Arena",   "ACCENT": "#35c48f"})   # Three.js r128
```
For a small change to an existing game (a color, a speed, a bug) edit only that and leave the rest alone. Otherwise pick 2D unless the user asks for 3D, then adapt the template, in this order, with `edit_file` / `append_file` (small edits, never a full rewrite). Keep the engine, replace and extend the content:

## Quick rules (read first)
1. Start from the template and adapt it to what the user described. Do not build an engine from scratch, and do not add mechanics nobody asked for.
2. Draw something on the very first frame: the title, the player, a "Tap to start". Never ship a black screen.
3. Use a game loop with a clamped time step: `dt = Math.min(ms, 50) / 1000`.
4. Support touch and keyboard. A start, a pause and a one-tap restart always exist.
5. Keep game state in one object, so restarting means creating a fresh one.
6. Size the canvas for the screen and `devicePixelRatio`. Pause when the tab is hidden.
7. Start easy and ramp up. Give instant feedback on every action (a sound, a flash, a shake).
8. Save the best score inside `try/catch`.

## Safety in this skill
- Games with violence in fiction are fine. Do not add real-money gambling, loot-box or pay-to-win tricks aimed at children, fake "reward" buttons that open ads, hidden redirects or trackers, or content that harasses real people or groups.
- Do not collect personal data from players. Keep scores on the device unless the user asks for an online board and says where the data goes.

## Adapting the 2D template (worked example: "Parcel Run")
1. **CONFIG**: world size, speeds, lives, spawn rates, colors. Rename the theme in the overlay texts.
2. **Rename entities** in names and texts: orb -> parcel, hazard -> drone, player -> courier.
3. **Draw functions**: replace `drawPlayer`, `drawOrb`, `drawHazard` with canvas paths for the new look. Keep the same signature, collision uses the circle radius, not the drawing.
```javascript
function drawOrb(o) {                     // a parcel: brown box with a lighter tape stripe, drawn around (o.x, o.y)
  ctx.save(); ctx.translate(o.x, o.y); ctx.rotate(Math.sin(o.age * 3) * 0.15);
  ctx.fillStyle = "#b9824a"; ctx.fillRect(-o.r, -o.r * 0.8, o.r * 2, o.r * 1.6);          // the box
  ctx.fillStyle = "#e8c48f"; ctx.fillRect(-o.r * 0.18, -o.r * 0.8, o.r * 0.36, o.r * 1.6);  // the tape
  ctx.restore();
}
```
4. **New item types**: add a `kind` field in `spawnOrb()` with its own value, radius, lifetime and color (envelope 20, crate 30). Pick a kind with weighted random: `const r = Math.random(); kind = r < 0.6 ? "parcel" : r < 0.9 ? "envelope" : "crate";`.
5. **New enemy behavior**: in the hazard loop add a `type`: `drifter` (straight), `chaser` (steers toward the player: `h.vx += (P.x - h.x) * 0.4 * dt`), `zigzag` (`h.vx = Math.sin(h.t * 3) * speed`). Cap speeds.
6. **Tune** `rampSeconds`, `spawn.*`, `comboWindow` by playing the first minute in your head: easy start, then steady pressure.
7. `verify_files`, `review_ui`, `preview_web`.

## Fit it to the request (what "done" means for a template)
A recolored template is a failed job, and so is a template stuffed with features nobody asked for. Lumo sends the file back when it is still the starter with different paint, so adapt it to what the user described:
1. **Their game:** theme, entities, goal, rules and wording come from the request. Remove template mechanics that do not belong; add only mechanics the request names or clearly implies.
2. **Their art:** redraw every entity for the theme with canvas paths (a parcel, a drone, a courier with a cap) and give the field a matching background, not circles on dots.
3. **Their screens:** a themed menu, HUD and game-over screen with a real title and real instructions in the user's language.
4. **Feedback that fits:** a sound and a visual response for each event that exists in the game, tuned to the theme.
5. **Extras only on request.** Power-ups, bosses, waves, levels, shops and upgrades are recipes below. Use one only when the user asked for it or the request cannot work without it. When in doubt leave it out and polish what was asked.

## First frame guarantee (never ship a black screen)
Before you say "done" the first frame must show the playfield, the player and the HUD at a readable size, in portrait and in landscape. Check it, do not assume it:
- `resize()` runs before the first `draw()`, reads the container with `getBoundingClientRect()` and clamps width and height to at least 1. Landscape phones are short: never subtract fixed heights from `innerHeight` without a lower bound.
- The loop starts in the menu state too, and the menu draws the world behind its overlay.
- Entities spawn inside the visible area. Log the player's x, y and the canvas size once: all positive, the player inside the canvas.
- Entity colors differ from the background (a dark ship on a dark sky is invisible). HUD numbers stay crisp: no `filter: blur`, no big `text-shadow`, no `backdrop-filter` behind text.
- One exception in `update()` or `draw()` stops `requestAnimationFrame` for good, so the screen freezes or stays empty. Read the first console error and fix it.
- With node installed run `node scripts/page_check.js index.html`: it loads the page in a stub browser at portrait and landscape sizes, runs 120 frames and reports exceptions and the number of canvas draw calls per frame. "0 draw calls" means a blank screen.

## Enhancement recipes (optional: use one only when the request calls for it)
```javascript
// 1) Floating score text. In update(dt): age and drift them. In render(): draw them.
const floaters = [];
function floatText(x, y, text, color) { floaters.push({ x, y, text, color, age: 0 }); }
function updateFloaters(dt) { for (let i = floaters.length - 1; i >= 0; i--) { const f = floaters[i]; f.age += dt; f.y -= 28 * dt; if (f.age > 0.8) floaters.splice(i, 1); } }
function drawFloaters() { for (const f of floaters) { ctx.globalAlpha = 1 - f.age / 0.8; ctx.fillStyle = f.color; ctx.font = "700 14px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.fillText(f.text, f.x, f.y); } ctx.globalAlpha = 1; }
```
```javascript
// 2) Power-ups: shield (absorbs one hit), magnet (pulls orbs), slow-mo (slows hazards).
const POWERUPS = { shield: { color: "#6ec1ff", time: 6 }, magnet: { color: "#ffd166", time: 7 }, slow: { color: "#c792ea", time: 5 } };
G.power = {};
function givePower(kind) { G.power[kind] = POWERUPS[kind].time; Sound.play("combo"); floatText(G.player.x, G.player.y - 20, kind.toUpperCase(), POWERUPS[kind].color); }
function updatePowers(dt, P) {
  for (const k in G.power) { G.power[k] -= dt; if (G.power[k] <= 0) delete G.power[k]; }
  if (G.power.magnet) for (const o of G.orbs) { const dx = P.x - o.x, dy = P.y - o.y, d = Math.hypot(dx, dy) || 1; if (d < 140) { o.x += dx / d * 180 * dt; o.y += dy / d * 180 * dt; } }
}
// shield: in the hazard-hit branch use `if (G.power.shield) { delete G.power.shield; burst(P.x, P.y, "#6ec1ff", 16); G.hazards.splice(i, 1); continue; }`
// slow-mo: multiply hazard motion by `G.power.slow ? 0.45 : 1`
```
```javascript
// 3) Waves: change what spawns over time, not just how fast.
const WAVES = [{ t: 0, kind: "drifter", every: 1.8 }, { t: 25, kind: "chaser", every: 2.4 }, { t: 55, kind: "zigzag", every: 1.6 }];
function currentWave() { let w = WAVES[0]; for (const x of WAVES) if (G.t >= x.t) w = x; return w; }
// in spawnHazard(): const w = currentWave(); h.kind = w.kind; and steer by kind in the hazard loop
// (chaser: h.vx += (P.x - h.x) * 0.4 * dt;  zigzag: h.vx = Math.sin(G.t * 3 + h.y) * speed).
```
```javascript
// 4) Parallax background: three star layers moving at different speeds.
const LAYERS = [{ speed: 8, size: 1.2, count: 40, color: "#1c2733" }, { speed: 20, size: 1.8, count: 26, color: "#26364a" }, { speed: 40, size: 2.4, count: 14, color: "#33485f" }];
LAYERS.forEach((L) => { L.pts = Array.from({ length: L.count }, () => ({ x: Math.random() * CONFIG.world.w, y: Math.random() * CONFIG.world.h })); });
function drawParallax(dt) {
  for (const L of LAYERS) { ctx.fillStyle = L.color; for (const p of L.pts) { p.y += L.speed * dt; if (p.y > CONFIG.world.h) { p.y = -4; p.x = Math.random() * CONFIG.world.w; } ctx.beginPath(); ctx.arc(p.x, p.y, L.size, 0, 6.283); ctx.fill(); } }
}
```
```javascript
// 5) Tiny procedural music loop. Put it inside the Sound IIFE (before `return {`), expose `music`, call Sound.music(true) in startGame and Sound.music(false) in endGame.
let musicTimer = null;
function music(on) {
  clearInterval(musicTimer); if (!on) return;
  const notes = [262, 330, 392, 330, 294, 370, 440, 370]; let i = 0;
  musicTimer = setInterval(() => { if (G.state === "play") tone(notes[i++ % notes.length] / 2, 0.22, "triangle", 0.035, 1); }, 280);
}
```

## Game feel checklist (what makes it feel good, not just work)
- Instant feedback for every action: a sound, particles, a flash or shake. Use `Sound.play(name)`, `burst(x, y, color, n)`, `G.shake`, `G.hitstop`.
- Easy for the first 20 seconds, then a smooth ramp. Never a sudden wall.
- Fail and retry in one tap; show score and best.
- Readable at phone size: touch targets >= 48px, HUD text >= 16px, high contrast.
- Short forgiving hitboxes (collision radius slightly smaller than the drawing).

## Engine snippets (when you must write or extend one)
```javascript
// Fixed timestep: physics stays stable at any frame rate
const STEP = 1 / 60; let last = 0, acc = 0;
function frame(ts) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, (ts - last) / 1000 || 0); last = ts; acc += dt;
  for (let n = 0; acc >= STEP && n < 5; n++) { update(STEP); acc -= STEP; }
  render();
}
```
```javascript
// Circle collision without sqrt
const hit = (a, b) => { const dx = a.x - b.x, dy = a.y - b.y, r = a.r + b.r; return dx * dx + dy * dy < r * r; };
```
```javascript
// Remove while iterating: go backwards
for (let i = list.length - 1; i >= 0; i--) { if (list[i].dead) list.splice(i, 1); }
```
```javascript
// Canvas that is sharp on phones and fits any screen
function resize() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2), s = Math.min(innerWidth / W, innerHeight / H);
  canvas.style.width = W * s + "px"; canvas.style.height = H * s + "px";
  canvas.width = W * s * dpr; canvas.height = H * s * dpr; ctx.setTransform(s * dpr, 0, 0, s * dpr, 0, 0);
}
```
```javascript
// Sound without files: unlock on the first user gesture
let ac; function unlock() { ac = ac || new (window.AudioContext || window.webkitAudioContext)(); if (ac.state === "suspended") ac.resume(); }
function blip(freq, dur) { const o = ac.createOscillator(), g = ac.createGain(); o.frequency.value = freq; g.gain.setValueAtTime(.12, ac.currentTime);
  g.gain.exponentialRampToValueAtTime(.0001, ac.currentTime + dur); o.connect(g); g.connect(ac.destination); o.start(); o.stop(ac.currentTime + dur); }
```

## 3D specifics (Three.js r128 only)
- Load with `<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>` BEFORE your code.
- Not available in r128: `CapsuleGeometry`, `THREE.OrbitControls` from the main bundle, `outputColorSpace`. Build characters from `CylinderGeometry` + `SphereGeometry` groups.
- Create geometries and materials ONCE and share them; never inside `update()`. Cap `setPixelRatio(Math.min(devicePixelRatio, 2))`. Avoid shadows on phones; use fog to hide the far plane.
- Use `MeshStandardMaterial` with lights, or `MeshBasicMaterial` for flat/UI-like objects. Remove objects with `scene.remove(mesh)`; shared geometry needs no `dispose()`.
- Move on the XZ plane, camera follows with `lerp`. Collision in 3D arena games: distance on x/z, ignore y.

## Pitfalls and fixes
| Symptom | Cause | Fix |
|---|---|---|
| Game runs twice as fast on 120 Hz phones | Movement uses frames, not time | Multiply by `dt`; use the fixed-step loop |
| Touch scrolls or zooms the page | Missing `touch-action: none` / `preventDefault` | CSS `touch-action: none` on body and canvas; `viewport user-scalable=no` |
| Blurry canvas on phone | Ignored devicePixelRatio | Use the `resize()` above |
| No sound on mobile | AudioContext not unlocked | Call `unlock()` in the first `pointerdown`/`keydown` |
| Game keeps running in a background tab | No visibility handling | Pause on `visibilitychange` (template does) |
| Frame drops after a minute | Allocation in the loop, arrays growing | Reuse objects, cap particles and entities, remove expired ones |
| Items spawn on top of the player | Random position unchecked | Re-roll if closer than ~80px to the player |
| `THREE is not defined` | Library script missing or after your code | Load the CDN script first; check the URL |
| Black 3D screen | No lights, camera inside the object, wrong `lookAt` | Add a HemisphereLight, set `camera.position`, call `lookAt` |

## Done means
`verify_files` clean, `review_ui` >= 85, the first frame checked in portrait and landscape, the game starts from the menu, scores, ends and restarts, every requirement the user gave is met and nothing they did not ask for was added. Then tell the user how to open it (`preview_web`, or open the file in a browser). For big games also load the reference skill `skill-game-development-implementation` part by part.

## Good and bad examples

### 1. Time step
Bad: movement tied to the frame rate, so a slow phone plays slowly and a resumed tab jumps.
```js
player.x += 5;
```
Good: speed in pixels per second, with a clamped step.
```js
// check: runs
import assert from "node:assert/strict";

const MAX_STEP_MS = 50;
const stepSeconds = (ms) => Math.min(ms, MAX_STEP_MS) / 1000;
assert.equal(stepSeconds(16), 0.016);
assert.equal(stepSeconds(5000), 0.05);      // a tab that slept does not teleport the player

const player = { x: 0, speed: 200 };        // pixels per second
player.x += player.speed * stepSeconds(16);
assert.ok(Math.abs(player.x - 3.2) < 1e-9);
```

### 2. Hit tests
Bad: compare centers only, so large objects pass through each other.
Good: circles hit when the distance is at most the sum of the radii (compare squares, no square root).
```js
// check: runs
import assert from "node:assert/strict";

const hit = (a, b) => {
  const dx = a.x - b.x, dy = a.y - b.y, r = a.r + b.r;
  return dx * dx + dy * dy <= r * r;
};
assert.equal(hit({ x: 0, y: 0, r: 5 }, { x: 8, y: 0, r: 5 }), true);
assert.equal(hit({ x: 0, y: 0, r: 5 }, { x: 11, y: 0, r: 5 }), false);
```

### 3. Restarting
Bad: reset fields one by one and forget one, so the second round starts with old enemies.
Good: build the whole state from a function.
```js
// check: syntax
function newGame() {
  return { phase: "ready", score: 0, lives: 3, time: 0, player: { x: 0, y: 0 }, items: [], hazards: [] };
}
let game = newGame();
function restart() { game = newGame(); game.phase = "playing"; }
```

### 4. The first screen
Bad: the canvas stays blank until the player taps.
Good: draw the title, the player and "Tap or press Space to start" on the first frame, and run `page_check` to confirm that draw calls happen.

### 5. Difficulty
Bad: full speed from the first second, or no change at all.
Good: a slow start, then a small increase every 20 to 30 seconds, with a cap so it stays fair.

### 6. Feedback
Bad: collecting an item changes a number silently.
Good: the item pops, the score ticks up, a short tone plays (after the first tap, because browsers block sound before it).

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Blurry canvas on phones | Set canvas size to `cssSize * devicePixelRatio` and scale the context |
| Touch scrolls the page | `touch-action: none` on the canvas and `preventDefault` on touch events |
| Game keeps running in another tab | Pause on `visibilitychange` |
| Memory grows | Remove dead objects from arrays; reuse particles |
| Sound does nothing | Create or resume the `AudioContext` inside a tap handler |
| Controls too small | Make touch buttons at least 56px and keep them out of the play area |
| Unfair spawns | Do not spawn a hazard on top of the player; give a safe radius |

## Checklist before you finish
- [ ] The result is built for the user's request, not the starter with new paint.
- [ ] The first frame shows something; start, pause and restart work with touch and keyboard.
- [ ] Time step is clamped; a fresh state is created on restart.
- [ ] It runs at 60 frames per second on a phone-sized canvas in portrait and landscape.
- [ ] `page_check` ran without errors and best score saving cannot crash the page.
