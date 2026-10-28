---
name: Axion AI Skill
developer: Alfar
name: Game Development Implementation Templates
version: 2.0
language: English
description: Concrete starter implementations and engine-specific rules for game loops, input, collision, physics, and multiplayer validation.
---

# Game Development Implementation Templates

## 1. Mission

When asked to implement a game mechanic, provide a concrete implementation matched to the real engine and project. “Add a game loop,” “support touch,” or “implement collision” is not a sufficient deliverable. Identify the runtime, script location, object hierarchy, update lifecycle, coordinate system, and expected result.

The templates below are working starting points, not universal drop-in replacements. Adapt them to the project and test in the actual runtime. Never mix browser Canvas APIs with Roblox APIs or assume a client script has server authority.

## 2. Pre-implementation inspection

Determine:
- engine and version;
- language and entry point;
- scene hierarchy or DOM structure;
- existing input/controller system;
- coordinate system and units;
- physics and collision architecture;
- update lifecycle and time-step behavior;
- multiplayer ownership and authority;
- target devices and accessibility requirements;
- available assets and dependencies.

For an existing project, inspect the relevant files before replacing them. Preserve the project's working camera, input, animation, physics, and networking architecture unless the requested change requires altering it.

## 3. Browser Canvas: complete game loop

Save this as `index.html` and open it in a modern browser. It includes a canvas, keyboard movement, delta time, clamping, and rendering. It is a small baseline, not a complete game engine.

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Canvas Movement Demo</title>
  <style>
    html, body {
      margin: 0;
      background: #101522;
      color: #f4f7ff;
      font: 16px system-ui, sans-serif;
    }
    main { max-width: 800px; margin: 0 auto; padding: 12px; }
    canvas {
      display: block;
      width: 100%;
      height: auto;
      border: 1px solid #39435b;
      touch-action: none;
    }
  </style>
</head>
<body>
  <main>
    <h1>Movement Demo</h1>
    <p>Move with WASD or the arrow keys.</p>
    <canvas id="game" width="800" height="450" aria-label="Movement game area"></canvas>
  </main>
  <script>
    const canvas = document.querySelector("#game");
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas 2D context is unavailable");

    const keys = new Set();
    const player = { x: 60, y: 60, w: 30, h: 30, speed: 220 };
    let previousTime = null;

    addEventListener("keydown", (event) => {
      const key = event.key.toLowerCase();
      if (["arrowup", "arrowdown", "arrowleft", "arrowright", " "].includes(key)) {
        event.preventDefault();
      }
      keys.add(key);
    });

    addEventListener("keyup", (event) => keys.delete(event.key.toLowerCase()));
    addEventListener("blur", () => keys.clear());

    function update(dt) {
      let dx =
        Number(keys.has("d") || keys.has("arrowright")) -
        Number(keys.has("a") || keys.has("arrowleft"));
      let dy =
        Number(keys.has("s") || keys.has("arrowdown")) -
        Number(keys.has("w") || keys.has("arrowup"));

      const magnitude = Math.hypot(dx, dy);
      if (magnitude > 0) {
        dx /= magnitude;
        dy /= magnitude;
      }

      player.x += dx * player.speed * dt;
      player.y += dy * player.speed * dt;

      player.x = Math.max(0, Math.min(canvas.width - player.w, player.x));
      player.y = Math.max(0, Math.min(canvas.height - player.h, player.y));
    }

    function render() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#202b42";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.fillStyle = "#7c6cff";
      ctx.fillRect(player.x, player.y, player.w, player.h);
    }

    function frame(timestamp) {
      const dt = previousTime === null
        ? 0
        : Math.min((timestamp - previousTime) / 1000, 0.05);

      previousTime = timestamp;
      update(dt);
      render();
      requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);
  </script>
</body>
</html>
```

Implementation rules:
- Use seconds for `dt`, not milliseconds.
- Multiply velocity by `dt` so movement is not directly tied to frame rate.
- Clamp large time steps after tab suspension.
- Do not create event listeners inside `frame`.
- Keep update and render logic separate.
- Use a fixed timestep for simulation that requires stable physics or deterministic stepping.
- Handle window blur so stuck movement keys do not persist.

## 4. Fixed timestep pattern for physics

A variable render frame can be fine for a simple demo, but some simulations need a fixed update interval. Use an accumulator and a maximum number of catch-up steps.

```js
const FIXED_DT = 1 / 60;
const MAX_STEPS_PER_FRAME = 5;
let accumulator = 0;
let lastTime = null;

function fixedUpdate(dt) {
  // Update physics and gameplay state using exactly dt seconds.
}

function render(alpha) {
  // Draw interpolated state if previous/current snapshots are available.
}

function frame(timestampMs) {
  const now = timestampMs / 1000;
  const frameDt = lastTime === null ? 0 : Math.min(now - lastTime, 0.1);
  lastTime = now;
  accumulator += frameDt;

  let steps = 0;
  while (accumulator >= FIXED_DT && steps < MAX_STEPS_PER_FRAME) {
    fixedUpdate(FIXED_DT);
    accumulator -= FIXED_DT;
    steps += 1;
  }

  if (steps === MAX_STEPS_PER_FRAME && accumulator >= FIXED_DT) {
    // Drop excess backlog to avoid an endless catch-up spiral.
    accumulator = 0;
  }

  render(accumulator / FIXED_DT);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
```

Do not blindly use fixed stepping for every game. Use the engine's built-in physics timing when available. Avoid simulating the same physics both manually and through the engine.

## 5. Browser Canvas: touch and pointer input

Pointer Events unify touch, mouse, and pen input. Convert viewport coordinates to canvas coordinates because CSS scaling may make the displayed canvas size differ from its internal resolution.

```js
const canvas = document.querySelector("#game");
const pointer = { x: 0, y: 0, down: false, pointerId: null };

function toCanvasCoordinates(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left) * (canvas.width / rect.width),
    y: (event.clientY - rect.top) * (canvas.height / rect.height)
  };
}

canvas.addEventListener("pointerdown", (event) => {
  if (pointer.pointerId !== null) return;
  pointer.pointerId = event.pointerId;
  canvas.setPointerCapture(event.pointerId);
  Object.assign(pointer, toCanvasCoordinates(event), { down: true });
});

canvas.addEventListener("pointermove", (event) => {
  if (pointer.pointerId !== event.pointerId) return;
  Object.assign(pointer, toCanvasCoordinates(event));
});

function finishPointer(event) {
  if (pointer.pointerId !== event.pointerId) return;
  pointer.down = false;
  pointer.pointerId = null;
  if (canvas.hasPointerCapture(event.pointerId)) {
    canvas.releasePointerCapture(event.pointerId);
  }
}

canvas.addEventListener("pointerup", finishPointer);
canvas.addEventListener("pointercancel", finishPointer);
```

Add this CSS to the canvas to reduce browser gesture interference inside the game area:

```css
canvas {
  touch-action: none;
  user-select: none;
}
```

Do not disable page scrolling across the whole page unnecessarily. Restrict `touch-action: none` to the actual game surface.

## 6. Virtual joystick vector

A virtual joystick stores a touch origin, computes displacement, clamps it to a radius, and normalizes the result. This helper calculates the direction; rendering the joystick ring is a separate visual step.

```js
function joystickVector(origin, current, maxRadius) {
  const dx = current.x - origin.x;
  const dy = current.y - origin.y;
  const distance = Math.hypot(dx, dy);

  if (distance === 0) return { x: 0, y: 0 };

  const clampedDistance = Math.min(distance, maxRadius);
  const scale = clampedDistance / distance;

  return {
    x: (dx * scale) / maxRadius,
    y: (dy * scale) / maxRadius
  };
}

// Example:
// const move = joystickVector({x: 100, y: 300}, {x: 130, y: 310}, 60);
// player.x += move.x * player.speed * dt;
// player.y += move.y * player.speed * dt;
```

Production rules:
- Track the owning `pointerId` for each joystick.
- Do not let a second finger unexpectedly take over the first joystick.
- Handle `pointercancel`, release, focus loss, and app suspension.
- Clamp output to the expected range.
- Apply a dead zone only if it improves control feel.
- Test in portrait and landscape.
- Keep joystick UI away from system gesture edges where possible.
- Provide accessible alternatives when the game supports keyboard/controller.

## 7. AABB collision detection

Axis-aligned bounding boxes are suitable for non-rotated rectangles. They are not suitable for arbitrary rotated shapes, circles, or polygonal collision unless adapted.

```js
function intersectsAABB(a, b) {
  return (
    a.x < b.x + b.w &&
    a.x + a.w > b.x &&
    a.y < b.y + b.h &&
    a.y + a.h > b.y
  );
}

const playerBox = { x: 40, y: 40, w: 32, h: 32 };
const hazardBox = { x: 60, y: 50, w: 24, h: 24 };

if (intersectsAABB(playerBox, hazardBox)) {
  console.log("Collision detected");
}
```

This function detects overlap only. It does not push objects apart, prevent penetration, determine collision normals, or handle fast objects that move through an obstacle between frames.

## 8. Resolve a simple horizontal/vertical AABB collision

For a simple top-down game, move one axis at a time and resolve against static obstacles. This is a minimal approach; complex platformers need more careful collision resolution, slopes, one-way platforms, and velocity handling.

```js
function moveAndCollideAABB(body, dx, dy, obstacles) {
  body.x += dx;

  for (const obstacle of obstacles) {
    if (!intersectsAABB(body, obstacle)) continue;

    if (dx > 0) body.x = obstacle.x - body.w;
    else if (dx < 0) body.x = obstacle.x + obstacle.w;
  }

  body.y += dy;

  for (const obstacle of obstacles) {
    if (!intersectsAABB(body, obstacle)) continue;

    if (dy > 0) body.y = obstacle.y - body.h;
    else if (dy < 0) body.y = obstacle.y + obstacle.h;
  }
}

const playerBody = { x: 20, y: 20, w: 28, h: 28 };
const walls = [
  { x: 100, y: 0, w: 20, h: 180 },
  { x: 0, y: 180, w: 250, h: 20 }
];

// Call with velocity * dt:
// moveAndCollideAABB(playerBody, vx * dt, vy * dt, walls);
```

This assumes obstacles are static and movement per step is small. For high-speed objects, use swept collision or the engine's continuous collision detection. For a platformer, preserve velocity and resolve floor/ceiling/wall contacts deliberately.

## 9. Collision test cases

```js
console.assert(
  intersectsAABB({ x: 0, y: 0, w: 10, h: 10 }, { x: 5, y: 5, w: 10, h: 10 }),
  "Overlapping boxes should collide"
);

console.assert(
  !intersectsAABB({ x: 0, y: 0, w: 10, h: 10 }, { x: 10, y: 0, w: 10, h: 10 }),
  "Edge-touching boxes are not overlapping under strict inequalities"
);

console.assert(
  !intersectsAABB({ x: 0, y: 0, w: 10, h: 10 }, { x: 20, y: 0, w: 10, h: 10 }),
  "Separated boxes should not collide"
);
```

Test exact edge contact, overlap, separation, negative coordinates if supported, zero-size boxes if allowed, and high-speed motion.

## 10. Roblox Luau: per-frame input and movement

Place this **LocalScript** in `StarterPlayer > StarterPlayerScripts`. Roblox's default character controller already handles keyboard, touch, and gamepad. Prefer the built-in controller unless custom movement is explicitly requested.

```lua
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local player = Players.LocalPlayer
local keysDown = {}

UserInputService.InputBegan:Connect(function(input, gameProcessed)
    if gameProcessed then return end
    if input.UserInputType == Enum.UserInputType.Keyboard then
        keysDown[input.KeyCode] = true
    end
end)

UserInputService.InputEnded:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.Keyboard then
        keysDown[input.KeyCode] = nil
    end
end)

local function update(_dt)
    local character = player.Character
    local humanoid = character and character:FindFirstChildOfClass("Humanoid")
    if not humanoid then return end

    local x, z = 0, 0
    if keysDown[Enum.KeyCode.A] or keysDown[Enum.KeyCode.Left] then x -= 1 end
    if keysDown[Enum.KeyCode.D] or keysDown[Enum.KeyCode.Right] then x += 1 end
    if keysDown[Enum.KeyCode.W] or keysDown[Enum.KeyCode.Up] then z -= 1 end
    if keysDown[Enum.KeyCode.S] or keysDown[Enum.KeyCode.Down] then z += 1 end

    local direction = Vector3.new(x, 0, z)
    if direction.Magnitude > 1 then direction = direction.Unit end
    humanoid:Move(direction, true)
end

RunService.RenderStepped:Connect(update)
```

This is a custom keyboard input example, not a recommendation to override default controls in every game. If custom mobile input is required, integrate it with the existing control system rather than creating competing controllers. Disconnect event connections when their owning object is destroyed if the script's lifecycle requires it.

## 11. Roblox Luau: touch action button

Place this **LocalScript** beneath a `TextButton` or `ImageButton` inside a `ScreenGui`. Configure the button's size, position, text/image, and visibility in Studio.

```lua
local button = script.Parent
assert(button:IsA("GuiButton"), "Parent must be a TextButton or ImageButton")

local held = false

button.Activated:Connect(function()
    -- Activated supports common click/tap activation.
    -- Replace with a local UI action or a validated server request.
    print("Ability button activated")
end)

button.InputBegan:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.Touch
        or input.UserInputType == Enum.UserInputType.MouseButton1 then
        held = true
    end
end)

button.InputEnded:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.Touch
        or input.UserInputType == Enum.UserInputType.MouseButton1 then
        held = false
    end
end)
```

Do not assume a held state always receives `InputEnded` in every lifecycle situation. Consider touch cancellation, UI destruction, focus changes, and character respawn. For a one-shot action, `Activated` is usually the simpler choice.

## 12. Roblox collision: server-side damage

For damage, currency, inventory, team logic, and other authoritative state, use a server Script. `Touched` can fire multiple times for body parts and should not be treated as a one-call-per-character event.

Place a `Script` under `ServerScriptService` or in the appropriate server-owned object:

```lua
local Players = game:GetService("Players")
local hazard = workspace:WaitForChild("Hazard")
assert(hazard:IsA("BasePart"), "Hazard must be a BasePart")

local lastHitAt = {}
local DAMAGE = 10
local COOLDOWN = 1

hazard.Touched:Connect(function(otherPart)
    local character = otherPart:FindFirstAncestorOfClass("Model")
    if not character then return end

    local humanoid = character:FindFirstChildOfClass("Humanoid")
    if not humanoid or humanoid.Health <= 0 then return end

    local player = Players:GetPlayerFromCharacter(character)
    local key = player or character
    local now = os.clock()

    if lastHitAt[key] and now - lastHitAt[key] < COOLDOWN then
        return
    end

    lastHitAt[key] = now
    humanoid:TakeDamage(DAMAGE)
end)

Players.PlayerRemoving:Connect(function(player)
    lastHitAt[player] = nil
end)
```

Production considerations:
- Check whether the character is immune, protected, on the same team, or already dead.
- Clear per-character state on respawn or destruction where necessary.
- Decide whether cooldown is per player, character, or hazard.
- Confirm the hazard is anchored/configured correctly.
- Test whether `CanTouch` and collision settings allow the event.
- Use server-side validation for all meaningful game effects.

## 13. Roblox overlap queries and raycasts

Use engine query APIs when they fit better than custom rectangle math. Example area query:

```lua
local Workspace = game:GetService("Workspace")

local overlapParams = OverlapParams.new()
overlapParams.FilterType = Enum.RaycastFilterType.Exclude
overlapParams.FilterDescendantsInstances = {}

local parts = Workspace:GetPartBoundsInBox(
    CFrame.new(0, 5, 0),
    Vector3.new(12, 8, 12),
    overlapParams
)

for _, part in ipairs(parts) do
    print("Part inside query bounds:", part:GetFullName())
end
```

This is a bounding-box query; it does not mean every returned part's exact mesh geometry lies fully inside the box. Filter out irrelevant parts and deduplicate characters before applying effects.

Example raycast:

```lua
local Workspace = game:GetService("Workspace")

local origin = Vector3.new(0, 5, 0)
local direction = Vector3.new(0, -20, 0)

local params = RaycastParams.new()
params.FilterType = Enum.RaycastFilterType.Exclude
params.FilterDescendantsInstances = {}

local result = Workspace:Raycast(origin, direction, params)
if result then
    print("Hit:", result.Instance:GetFullName(), "at", result.Position)
end
```

Use raycasts for line-of-sight, ground checks, and projectile queries when suitable. Verify filter behavior against the current Roblox API version.

## 14. Roblox RemoteEvent: client request, server validation

Create a `RemoteEvent` named `UseAbility` in `ReplicatedStorage`. The client may request an action, but the server must decide whether it is valid.

Client **LocalScript**:

```lua
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local useAbility = ReplicatedStorage:WaitForChild("UseAbility")

local function requestDash()
    useAbility:FireServer("Dash")
end

-- Connect requestDash to the actual button or input action.
```

Server **Script** in `ServerScriptService`:

```lua
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local useAbility = ReplicatedStorage:WaitForChild("UseAbility")
local lastUseAt = {}
local COOLDOWN = 1.0

useAbility.OnServerEvent:Connect(function(player, abilityName)
    if typeof(abilityName) ~= "string" then return end
    if abilityName ~= "Dash" then return end

    local now = os.clock()
    if lastUseAt[player] and now - lastUseAt[player] < COOLDOWN then
        return
    end

    local character = player.Character
    local humanoid = character and character:FindFirstChildOfClass("Humanoid")
    local root = character and character:FindFirstChild("HumanoidRootPart")

    if not humanoid or humanoid.Health <= 0 or not root then return end

    -- Validate stamina, state, distance, cooldown, and game rules here.
    lastUseAt[player] = now

    -- Apply the authoritative effect here.
    -- Do not trust the client to supply damage, currency, target ownership,
    -- cooldown completion, or permission state.
end)

Players.PlayerRemoving:Connect(function(player)
    lastUseAt[player] = nil
end)
```

Do not leave the event handler as a security boundary without validation. Rate-limit requests, validate every argument, verify the player's state, and prevent replay or spam where relevant.

## 15. Common implementation mistakes

- Using frame count instead of elapsed time for movement.
- Forgetting that browser CSS dimensions differ from canvas pixel dimensions.
- Failing to clear keys after focus loss.
- Registering event listeners every frame.
- Treating collision detection as collision resolution.
- Ignoring tunneling for fast-moving objects.
- Applying gameplay damage only on the client.
- Letting multiple touch points control the same input accidentally.
- Creating a custom Roblox movement controller that fights default controls.
- Treating `Touched` as exactly one event per character.
- Failing to debounce or clean up state.
- Assuming a code snippet is tested in an engine when it was not run.

## 16. Test plan

```text
Setup:
- [engine version and required objects]

Happy path:
- [input/action] produces [expected result]

Input edge cases:
- rapid taps
- held input
- release outside control
- pointer/touch cancellation
- two simultaneous touches where supported
- focus loss or character respawn

Collision edge cases:
- no contact
- edge contact
- overlapping contact
- repeated contact
- high-speed movement
- ignored/excluded objects

Multiplayer:
- client cannot grant itself authority
- invalid arguments are rejected
- spam/cooldown is enforced
- server validates state

Performance:
- no per-frame listener creation
- no unbounded loop
- no unnecessary per-frame allocations where avoidable

Evidence:
- [actual tests run and results]
```

## 17. Required implementation response

When asked to build a mechanic, include:
1. exact file/script placement;
2. complete relevant code, not disconnected fragments;
3. required object hierarchy and setup;
4. explanation of key variables, events, and state transitions;
5. reproducible test steps;
6. security notes for multiplayer;
7. limitations and what was not tested.

If engine choice materially changes the code and is unknown, ask one focused question before writing an engine-specific solution.


---

# Advanced Operating Specification — v4 Expansion

## 16. Browser Game Architecture: Separate Simulation from Rendering

A small game becomes easier to reason about when simulation state is independent from drawing. The simulation owns position, velocity, health, collision, and game state. Rendering reads that state and draws it. Input updates intent, not arbitrary world state.

```html
<canvas id="game" width="800" height="450" aria-label="Game area"></canvas>
<script>
const canvas = document.querySelector("#game");
const ctx = canvas.getContext("2d");
const world = { width: 800, height: 450 };
const player = { x: 80, y: 80, w: 28, h: 28, speed: 220 };
const input = { left: false, right: false, up: false, down: false };
let previousTime = 0;

window.addEventListener("keydown", (event) => {
  const map = { ArrowLeft: "left", ArrowRight: "right",
                ArrowUp: "up", ArrowDown: "down",
                a: "left", d: "right", w: "up", s: "down" };
  const key = map[event.key];
  if (key) {
    input[key] = true;
    if (event.key.startsWith("Arrow")) event.preventDefault();
  }
});

window.addEventListener("keyup", (event) => {
  const map = { ArrowLeft: "left", ArrowRight: "right",
                ArrowUp: "up", ArrowDown: "down",
                a: "left", d: "right", w: "up", s: "down" };
  if (map[event.key]) input[map[event.key]] = false;
});

window.addEventListener("blur", () => {
  for (const key of Object.keys(input)) input[key] = false;
});

function update(dt) {
  let dx = Number(input.right) - Number(input.left);
  let dy = Number(input.down) - Number(input.up);
  const magnitude = Math.hypot(dx, dy);
  if (magnitude > 0) { dx /= magnitude; dy /= magnitude; }

  player.x += dx * player.speed * dt;
  player.y += dy * player.speed * dt;
  player.x = Math.max(0, Math.min(world.width - player.w, player.x));
  player.y = Math.max(0, Math.min(world.height - player.h, player.y));
}

function render() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#101827";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#9b8cff";
  ctx.fillRect(player.x, player.y, player.w, player.h);
}

function frame(now) {
  const dt = Math.min((now - previousTime) / 1000 || 0, 0.05);
  previousTime = now;
  update(dt);
  render();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script>
```

The example is a runnable movement baseline, not a complete game. It intentionally clamps large frame deltas to avoid a long simulation jump after a tab suspension. A physics-heavy game should consider a fixed timestep and a bounded accumulator.

## 17. Fixed-Timestep Simulation

A variable frame delta can make physics behavior depend on frame rate. Use a fixed simulation interval for systems that require consistent physics, while rendering as often as practical.

```javascript
const FIXED_DT = 1 / 60;
const MAX_FRAME = 0.25;
let accumulator = 0;
let last = 0;

function frame(timestampMs) {
  const now = timestampMs / 1000;
  const elapsed = last === 0 ? 0 : Math.min(now - last, MAX_FRAME);
  last = now;
  accumulator += elapsed;

  while (accumulator >= FIXED_DT) {
    updatePhysics(FIXED_DT);
    accumulator -= FIXED_DT;
  }

  const alpha = accumulator / FIXED_DT;
  renderInterpolated(alpha);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
```

Define `updatePhysics` and `renderInterpolated` for the actual game state before using this template. Do not paste a function skeleton and claim the game is complete. Cap catch-up work to avoid the “spiral of death,” where slow simulation causes ever more accumulated work.

## 18. AABB Collision and Resolution

For axis-aligned rectangles, collision detection is simple. Use consistent edge conventions: touching edges are often treated as non-overlapping for movement collision, but a game may intentionally treat contact as a hit.

```javascript
function overlapsAABB(a, b) {
  return a.x < b.x + b.w &&
         a.x + a.w > b.x &&
         a.y < b.y + b.h &&
         a.y + a.h > b.y;
}

function resolveAABB(moving, solid, previousX, previousY) {
  if (!overlapsAABB(moving, solid)) return false;

  const wasLeft = previousX + moving.w <= solid.x;
  const wasRight = previousX >= solid.x + solid.w;
  const wasAbove = previousY + moving.h <= solid.y;
  const wasBelow = previousY >= solid.y + solid.h;

  if (wasLeft) moving.x = solid.x - moving.w;
  else if (wasRight) moving.x = solid.x + solid.w;
  else if (wasAbove) moving.y = solid.y - moving.h;
  else if (wasBelow) moving.y = solid.y + solid.h;
  else {
    // Previous position was already overlapping: use minimum penetration.
    const left = moving.x + moving.w - solid.x;
    const right = solid.x + solid.w - moving.x;
    const top = moving.y + moving.h - solid.y;
    const bottom = solid.y + solid.h - moving.y;
    const minimum = Math.min(left, right, top, bottom);
    if (minimum === left) moving.x = solid.x - moving.w;
    else if (minimum === right) moving.x = solid.x + solid.w;
    else if (minimum === top) moving.y = solid.y - moving.h;
    else moving.y = solid.y + solid.h;
  }
  return true;
}
```

This is a teaching implementation for one moving rectangle against one solid rectangle. For reliable platformer movement, resolve X and Y separately, retain previous coordinates, account for velocity direction, and test high-speed movement. Discrete overlap checks can tunnel through thin obstacles when an object travels farther than the obstacle thickness in one step; use substeps or swept collision when required.

## 19. Touch Input: Pointer Events and Virtual Joystick

Use Pointer Events when the same control should support mouse, pen, and touch. For a virtual joystick, normalize the displacement and clamp its magnitude to one. Capture the pointer so movement continues while the finger moves outside the visual knob.

```javascript
const stick = document.querySelector("#stick");
const knob = document.querySelector("#stick-knob");
const axis = { x: 0, y: 0 };
let activePointer = null;

function updateStick(event) {
  const rect = stick.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const radius = Math.min(rect.width, rect.height) * 0.35;
  let x = (event.clientX - cx) / radius;
  let y = (event.clientY - cy) / radius;
  const length = Math.hypot(x, y);
  if (length > 1) { x /= length; y /= length; }

  axis.x = x;
  axis.y = y;
  knob.style.transform = `translate(${x * radius}px, ${y * radius}px)`;
}

stick.addEventListener("pointerdown", (event) => {
  if (activePointer !== null) return;
  activePointer = event.pointerId;
  stick.setPointerCapture(event.pointerId);
  updateStick(event);
});

stick.addEventListener("pointermove", (event) => {
  if (event.pointerId === activePointer) updateStick(event);
});

function releaseStick(event) {
  if (event.pointerId !== activePointer) return;
  activePointer = null;
  axis.x = 0;
  axis.y = 0;
  knob.style.transform = "translate(0px, 0px)";
}
stick.addEventListener("pointerup", releaseStick);
stick.addEventListener("pointercancel", releaseStick);
```

Expected markup needs an element with `id="stick"` and a child with `id="stick-knob"`, with a circular track and centered knob. Apply `touch-action: none` to the joystick surface only if needed to prevent browser gestures from interrupting the control. Do not disable page zoom globally.

## 20. Roblox Luau: Server Authority and RemoteEvent Validation

In Roblox, the client should request actions, while the server validates and applies authoritative changes. Never trust client-supplied currency, damage, target ownership, cooldown completion, or reward amounts.

```lua
-- ServerScriptService/RequestPurchase.server.lua
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")

local purchaseEvent = ReplicatedStorage:WaitForChild("RequestPurchase")
local prices = {
    SpeedUpgrade = 100,
    JumpUpgrade = 150,
}
local lastRequestAt = {}

local function canPurchase(player, itemName)
    if typeof(itemName) ~= "string" then
        return false, "Invalid item"
    end

    local price = prices[itemName]
    if not price then
        return false, "Unknown item"
    end

    local now = os.clock()
    local previous = lastRequestAt[player] or 0
    if now - previous < 0.25 then
        return false, "Too many requests"
    end
    lastRequestAt[player] = now

    local leaderstats = player:FindFirstChild("leaderstats")
    local coins = leaderstats and leaderstats:FindFirstChild("Coins")
    if not coins or not coins:IsA("IntValue") then
        return false, "Currency unavailable"
    end
    if coins.Value < price then
        return false, "Not enough currency"
    end

    return true, price
end

purchaseEvent.OnServerEvent:Connect(function(player, itemName)
    local allowed, result = canPurchase(player, itemName)
    if not allowed then
        warn(("Rejected purchase request from %s: %s")
            :format(player.Name, tostring(result)))
        return
    end

    local price = result
    local leaderstats = player:FindFirstChild("leaderstats")
    local coins = leaderstats and leaderstats:FindFirstChild("Coins")
    if not coins or coins.Value < price then return end

    -- Re-check and mutate server-owned state in the same handler.
    coins.Value -= price

    if itemName == "SpeedUpgrade" then
        local character = player.Character
        local humanoid = character and character:FindFirstChildOfClass("Humanoid")
        if humanoid then humanoid.WalkSpeed = 20 end
    elseif itemName == "JumpUpgrade" then
        local character = player.Character
        local humanoid = character and character:FindFirstChildOfClass("Humanoid")
        if humanoid then humanoid.JumpPower = 60 end
    end
end)

Players.PlayerRemoving:Connect(function(player)
    lastRequestAt[player] = nil
end)
```

This example requires a `RemoteEvent` named `RequestPurchase`, a server-created `leaderstats.Coins` `IntValue`, and a deliberate product policy. Production systems should make purchases atomic with the authoritative data model, handle character respawn, persist progression safely, and avoid trusting client UI as evidence that a purchase succeeded.

## 21. Roblox Collision: Choose the Correct Query

Use the mechanism that matches the gameplay question:
- `BasePart.Touched`: event-driven physical contact; can fire multiple times and should be debounced when the action must happen once.
- `Workspace:Raycast()`: line or directional query for visibility, aiming, and ground checks.
- `GetPartBoundsInBox()` / overlap queries: spatial region queries for hitboxes and nearby objects.
- Physics constraints and collisions: physical response between parts.
- Server-side validation: authority for rewards, damage, and competitive outcomes.

Example raycast:

```lua
local Workspace = game:GetService("Workspace")

local function castFrom(origin, direction, character)
    local params = RaycastParams.new()
    params.FilterType = Enum.RaycastFilterType.Exclude
    params.FilterDescendantsInstances = { character }
    params.IgnoreWater = true

    return Workspace:Raycast(origin, direction, params)
end
```

The returned result may be `nil`. Always branch accordingly. Choose filter behavior that matches the current Roblox API version and the intended inclusion/exclusion semantics. A client raycast can improve responsiveness, but the server must independently validate consequential actions.

## 22. Roblox Touch Events and Debouncing

```lua
local Players = game:GetService("Players")
local checkpoint = script.Parent
local recentlyTriggered = {}

checkpoint.Touched:Connect(function(hit)
    local character = hit:FindFirstAncestorOfClass("Model")
    if not character then return end

    local player = Players:GetPlayerFromCharacter(character)
    if not player or recentlyTriggered[player] then return end

    recentlyTriggered[player] = true
    -- Apply a server-authoritative checkpoint update here.

    task.delay(1, function()
        recentlyTriggered[player] = nil
    end)
end)

Players.PlayerRemoving:Connect(function(player)
    recentlyTriggered[player] = nil
end)
```

This debounce is per player, not per individual limb. Decide whether the intended policy is one trigger per player, character, checkpoint, or cooldown window. If multiple checkpoints exist, store debounce state at the correct scope and clean it up. Do not use a debounce to conceal a fundamentally incorrect collision condition.

## 23. Game State Machines

Use explicit states for menu, loading, active play, paused, failed, and completed states. State transitions should have a defined trigger and allowed actions.

```javascript
const allowedTransitions = {
  menu: new Set(["loading"]),
  loading: new Set(["playing", "menu"]),
  playing: new Set(["paused", "failed", "completed"]),
  paused: new Set(["playing", "menu"]),
  failed: new Set(["loading", "menu"]),
  completed: new Set(["loading", "menu"])
};

let gameState = "menu";

function transitionTo(next) {
  if (!allowedTransitions[gameState]?.has(next)) {
    throw new Error(`Invalid game state transition: ${gameState} -> ${next}`);
  }
  gameState = next;
}
```

Do not let pause, death, reset, and scene transitions independently mutate unrelated flags that can enter contradictory combinations. If a game genuinely supports overlapping modes, model them explicitly rather than forcing them into one state variable.

## 24. Performance and Device Budgets

Measure before optimizing, then prioritize the most expensive verified bottleneck. Common areas include per-frame allocations, excessive physics queries, too many active particles, overdraw, unbounded object creation, and network replication.

For low-end mobile devices:
- Pool frequently reused objects when allocation churn is measured to matter.
- Cap particles and expensive post-processing.
- Avoid unnecessary per-frame hierarchy searches.
- Cache references to stable objects.
- Avoid sending remote events every frame when a lower update rate is sufficient.
- Keep authoritative server checks bounded.
- Test realistic player counts and scene complexity.
- Do not raise FPS targets without checking thermal, battery, and frame-time stability.

An FPS counter is not enough. Inspect frame-time spikes, memory growth, server simulation load, and behavior over a sustained session.

## 25. Game Test Matrix

Test at least:
- Minimum and maximum supported screen sizes.
- Mouse/keyboard and touch when both are supported.
- Focus loss and regain.
- Pause/resume.
- Restart after failure.
- Collision at low and high speed.
- Edge contact and overlapping spawn positions.
- Missing or destroyed target objects.
- Network delay and duplicate requests in multiplayer.
- Player leaving during a delayed operation.
- Low frame rate and large frame-time spikes.
- Invalid client requests for server-authoritative actions.

Record actual results rather than writing “passed” by assumption. A test matrix is valuable only when it is executed.

## 26. Common Game Implementation Defects

- **Frame-rate-dependent movement:** use elapsed time or fixed simulation steps.
- **Diagonal speed boost:** normalize the input vector.
- **Stuck input after focus loss:** clear pressed-state flags on blur/cancel.
- **Touch control drift:** use pointer capture and clamp joystick magnitude.
- **Tunneling:** use substeps or swept collision for fast objects.
- **Double-triggered pickup:** use correct debounce scope and authoritative state.
- **Client reward exploit:** validate and award on the server.
- **Respawn bug:** reacquire character and humanoid references after respawn.
- **Unbounded object creation:** remove, reuse, or cap transient entities.
- **False “complete” claim:** run the actual target environment and test the acceptance path.

## 27. Game Delivery Contract

A game implementation is ready for handoff only when the following are explicit:
- Engine and target platform.
- Entry point and required scene/object hierarchy.
- Scripts and where each belongs.
- Required assets, remotes, tags, and configuration.
- Controls and intended gameplay.
- Setup and run instructions.
- Tests executed and results.
- Known limitations and untested behavior.
- Security assumptions, especially client/server authority.

Never present a snippet as a complete project when it requires unprovided objects, assets, services, or setup. Label snippets as standalone, partial, or dependent on a specified hierarchy.
