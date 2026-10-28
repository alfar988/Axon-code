---
name: Axion AI Skill
developer: Alfar
name: UI, CSS, and Visual Design
version: 3.0
language: English
description: Detailed implementation rules and code patterns for coherent, accessible, responsive interfaces.
---

# UI, CSS, and Visual Design

## 1. Mission

Turn visual requests into real interfaces. A good UI specification defines hierarchy, layout, tokens, component behavior, responsive rules, accessibility, and verifiable states. Do not deliver only mood words such as “modern,” “premium,” “clean,” or “beautiful.” Translate them into implementation choices.

First identify the target environment. HTML/CSS does not directly control Roblox `ScreenGui`, native Android layouts, or a game engine's scene graph. Use the platform's actual component system and APIs.

## 2. UI requirements contract

```yaml
ui_contract:
  platform: "web | Roblox | Android | iOS | desktop | other"
  screen_name: ""
  user_goal: ""
  primary_action: ""
  secondary_actions: []
  layout_regions: []
  design_tokens: {}
  states:
    - default
    - loading
    - empty
    - error
    - success
    - disabled
  responsive_targets: [360, 768, 1280]
  accessibility:
    keyboard: true
    visible_focus: true
    readable_contrast: true
    touch_targets: true
  acceptance_tests: []
```

Define the primary action before styling. Visual hierarchy should make the most important task easiest to recognize.

## 3. Design tokens

Use semantic tokens so the whole interface can be tuned without hunting through many files.

```css
:root {
  color-scheme: dark;

  /* Surfaces */
  --color-bg: #0b1020;
  --color-surface: #131b2e;
  --color-surface-raised: #1b2740;
  --color-overlay: rgb(4 8 18 / 78%);

  /* Text */
  --color-text: #f4f7ff;
  --color-muted: #aab6cc;
  --color-disabled: #69758b;

  /* Semantic actions */
  --color-primary: #7c6cff;
  --color-primary-hover: #9589ff;
  --color-success: #45d49b;
  --color-warning: #ffca69;
  --color-danger: #ff657a;

  /* Borders and focus */
  --color-border: rgb(255 255 255 / 12%);
  --color-focus: #b4aaff;
  --focus-ring: 0 0 0 3px rgb(124 108 255 / 42%);

  /* Geometry */
  --radius-sm: 8px;
  --radius-md: 14px;
  --radius-lg: 22px;
  --radius-pill: 999px;

  /* Spacing: 4px base */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;

  --content-max: 1200px;
  --transition-fast: 140ms ease;
}
```

Rules:
- Reuse existing project tokens if they exist.
- Keep semantic meaning stable; do not use the danger token for ordinary decoration.
- Use spacing from the scale instead of arbitrary values for every component.
- Check contrast rather than assuming that a visually attractive color combination is readable.
- Do not use color alone to communicate success, error, or selection.

## 4. Complete HTML starting point

This is a standalone web skeleton. In an existing app, adapt it to the current framework rather than replacing the app shell without inspection.

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>Axion Cloud — Devices</title>
  <link rel="stylesheet" href="styles.css">
  <script src="app.js" defer></script>
</head>
<body>
  <div class="app-shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="Axion Cloud home">Axion Cloud</a>
      <nav aria-label="Main navigation">
        <a href="#devices" aria-current="page">Devices</a>
        <a href="#settings">Settings</a>
      </nav>
      <button id="profileButton" class="button button-secondary" type="button">
        Profile
      </button>
    </header>

    <main class="content" id="main">
      <section class="page-heading">
        <div>
          <p class="eyebrow">WORKSPACE</p>
          <h1>Cloud devices</h1>
          <p class="muted">Create, start, and manage your virtual devices.</p>
        </div>
        <button id="createDeviceButton" class="button button-primary" type="button">
          Create device
        </button>
      </section>

      <section id="deviceStatus" aria-live="polite" class="status-message"></section>

      <section id="deviceGrid" class="device-grid" aria-label="Your cloud devices">
        <article class="device-card" data-device-id="demo-1">
          <div class="device-card-heading">
            <div>
              <h2>Android device</h2>
              <p class="muted">Android • 4 GB profile</p>
            </div>
            <span class="status status-stopped">Stopped</span>
          </div>
          <div class="device-actions">
            <button class="button button-primary" data-action="start" type="button">
              Start device
            </button>
            <button class="button button-secondary" data-action="details" type="button">
              Details
            </button>
          </div>
        </article>
      </section>
    </main>
  </div>
</body>
</html>
```

## 5. CSS layout and component patterns

```css
*,
*::before,
*::after {
  box-sizing: border-box;
}

html {
  min-width: 320px;
  scroll-behavior: smooth;
}

body {
  margin: 0;
  min-height: 100vh;
  background: var(--color-bg);
  color: var(--color-text);
  font: 16px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

button, input, select, textarea {
  font: inherit;
}

button, a {
  -webkit-tap-highlight-color: transparent;
}

a {
  color: inherit;
  text-underline-offset: 0.2em;
}

button:focus-visible,
a:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 3px;
  box-shadow: var(--focus-ring);
}

.app-shell { min-height: 100vh; }

.topbar {
  display: flex;
  align-items: center;
  gap: 24px;
  min-height: 68px;
  padding: 12px clamp(16px, 4vw, 40px);
  border-bottom: 1px solid var(--color-border);
}

.brand {
  font-weight: 750;
  text-decoration: none;
  letter-spacing: -0.03em;
}

.topbar nav {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-left: auto;
}

.topbar nav a {
  color: var(--color-muted);
  text-decoration: none;
}

.topbar nav a[aria-current="page"] {
  color: var(--color-text);
}

.content {
  width: min(calc(100% - 32px), var(--content-max));
  margin-inline: auto;
  padding-block: clamp(24px, 5vw, 48px) 64px;
}

.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
}

h1, h2, p { margin-top: 0; }
h1 { margin-bottom: 8px; font-size: clamp(1.8rem, 4vw, 2.7rem); line-height: 1.1; }
h2 { margin-bottom: 8px; font-size: 1.1rem; }
.eyebrow { margin-bottom: 8px; color: var(--color-primary-hover); font-size: .75rem; font-weight: 800; letter-spacing: .12em; }
.muted { color: var(--color-muted); }

.device-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 270px), 1fr));
  gap: 16px;
}

.device-card {
  display: flex;
  flex-direction: column;
  gap: 22px;
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: linear-gradient(150deg, var(--color-surface-raised), var(--color-surface));
}

.device-card-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  font-size: .78rem;
  white-space: nowrap;
}

.status-stopped { color: var(--color-muted); }
.status-running { color: var(--color-success); }
.status-error { color: var(--color-danger); }

.device-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: auto;
}

.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 44px;
  padding: 10px 16px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  font-weight: 700;
  cursor: pointer;
  transition: background var(--transition-fast), transform var(--transition-fast);
}

.button:active { transform: translateY(1px); }
.button:disabled { opacity: .55; cursor: not-allowed; transform: none; }
.button-primary { background: var(--color-primary); color: white; }
.button-primary:hover:not(:disabled) { background: var(--color-primary-hover); }
.button-secondary { border-color: var(--color-border); background: transparent; color: var(--color-text); }

.status-message:empty { display: none; }
.status-message { margin-block: 12px 20px; }

@media (max-width: 640px) {
  .topbar { flex-wrap: wrap; }
  .topbar nav { order: 3; width: 100%; margin-left: 0; }
  .page-heading { align-items: stretch; flex-direction: column; }
  .page-heading .button { width: 100%; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    animation-duration: .01ms !important;
    transition-duration: .01ms !important;
  }
}
```

## 6. JavaScript interaction: event delegation and state feedback

Every control needs a real outcome. This example handles device-card actions without adding an event listener to every card. The mock operation is local only; replace it with a real service call before claiming a device actually starts.

```js
const grid = document.querySelector("#deviceGrid");
const statusRegion = document.querySelector("#deviceStatus");

function showStatus(message) {
  if (statusRegion) statusRegion.textContent = message;
}

grid?.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || !grid.contains(button)) return;

  const card = button.closest("[data-device-id]");
  if (!card) return;

  const action = button.dataset.action;
  const deviceId = card.dataset.deviceId;

  if (action === "details") {
    showStatus(`Showing details for ${deviceId}.`);
    return;
  }

  if (action === "start") {
    button.disabled = true;
    button.textContent = "Starting…";
    showStatus(`Starting ${deviceId}…`);

    try {
      // Replace this mock with an actual API request.
      await new Promise((resolve) => setTimeout(resolve, 300));
      const badge = card.querySelector(".status");
      if (badge) {
        badge.textContent = "Running (demo)";
        badge.className = "status status-running";
      }
      button.textContent = "Started (demo)";
      showStatus("Demo state updated. No real cloud device was started.");
    } catch (error) {
      button.textContent = "Retry start";
      showStatus("Unable to start the device. Check the connection and retry.");
    } finally {
      button.disabled = false;
    }
  }
});
```

Do not leave mock behavior in a production build without clearly labelling it. For a real backend, parse response status, validate response data, handle timeouts and retries, and show success only after confirmation.

## 7. Component state contract

Define each component's inputs, states, and actions before implementing complex behavior.

```text
Component: CloudDeviceCard
Inputs:
  id: stable device identifier
  name: user-visible device name
  platform: supported OS/platform
  status: authoritative service status

States:
  stopped
  starting
  running
  stopping
  error

Actions:
  start
  stop
  open details
  rename (if supported)

Rules:
  - Disable Start while starting or running.
  - Disable Stop while stopping or stopped.
  - Show progress during transitions.
  - Show an actionable message after failure.
  - Preserve the user's form values after validation errors.
  - Do not show Running until the backend confirms it.
  - Prevent duplicate submissions.
```

## 8. Forms and validation

Use semantic labels, useful validation messages, and preserve user input after errors.

```html
<form id="createDeviceForm" novalidate>
  <label for="deviceName">Device name</label>
  <input id="deviceName" name="deviceName" required minlength="3" maxlength="32">
  <p id="deviceNameError" class="muted" aria-live="polite"></p>
  <button class="button button-primary" type="submit">Create device</button>
</form>
```

```js
const form = document.querySelector("#createDeviceForm");
const nameInput = document.querySelector("#deviceName");
const nameError = document.querySelector("#deviceNameError");

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  const name = nameInput.value.trim();

  if (name.length < 3 || name.length > 32) {
    nameError.textContent = "Enter a name between 3 and 32 characters.";
    nameInput.setAttribute("aria-invalid", "true");
    nameInput.focus();
    return;
  }

  nameError.textContent = "";
  nameInput.removeAttribute("aria-invalid");
  // Submit validated data to the real creation handler here.
});
```

Client-side validation improves usability; the server must validate again.

## 9. Accessibility rules

- Use semantic HTML before custom ARIA.
- Every input needs an accessible label.
- Keyboard users must be able to reach and operate interactive controls.
- Focus must be visible and not hidden behind sticky headers or dialogs.
- Dialogs must manage focus and restore it on close.
- Use `aria-live` for important asynchronous status changes, not every decorative update.
- Respect reduced-motion preferences.
- Keep text readable at zoomed sizes.
- Use text or icons in addition to color for status.
- Avoid clickable `div` elements when a button or link is appropriate.

## 10. Responsive behavior

Test at narrow mobile, tablet, and desktop widths. Specify the behavior, not just the breakpoint.

```text
At 360px:
- one column;
- primary action full width;
- navigation wraps or collapses;
- no horizontal page scrolling.

At 768px:
- two columns when card width permits;
- header actions remain visible;
- spacing increases moderately.

At 1280px:
- content remains within max width;
- grid uses available space without oversized cards;
- body text does not stretch across an unreadably long line.
```

Use flexible layouts such as CSS Grid and Flexbox. Avoid fixed widths that break on small screens. Do not depend on hover for touch actions.

## 11. Visual quality review

Check:
- hierarchy: page title, primary action, card titles, metadata;
- alignment: shared edges and consistent baseline;
- spacing: repeatable scale;
- typography: controlled line lengths and heading scale;
- contrast: text and controls remain legible;
- state consistency: the same status uses the same visual treatment;
- density: no giant empty areas unless intentional;
- responsiveness: content reflows rather than clips;
- feedback: actions have visible progress and results.

## 12. UI acceptance checklist

```text
[ ] Target platform and component framework are correct.
[ ] Existing design system was inspected before adding tokens.
[ ] Every required screen region exists.
[ ] All controls have working behavior or are explicitly decorative.
[ ] Loading, empty, error, success, and disabled states are defined.
[ ] Form validation is understandable and preserves input.
[ ] Layout works at 360px, 768px, and 1280px.
[ ] Keyboard focus is visible.
[ ] Touch targets are practical on mobile.
[ ] Reduced-motion settings are respected.
[ ] No horizontal overflow or clipped primary controls.
[ ] No console errors during the main flow.
[ ] Mock behavior is clearly separated from production behavior.
```

## 13. Delivery requirements

Provide actual source files or a patch when implementation is requested. Include:
- changed file paths;
- how to run the UI;
- any required setup;
- tests performed and their result;
- remaining limitations.

Never describe a static mockup as a functioning backend integration.


---

# Advanced Operating Specification — v4 Expansion

## 20. Component Contracts and State Ownership

Every interactive component needs a clear contract. Define:
- Purpose and visible responsibility.
- Inputs and their types.
- State it owns.
- State it receives from a parent.
- Events it emits.
- Loading, empty, success, error, and disabled states.
- Keyboard and assistive-technology behavior.
- What happens if the underlying request fails.

Do not let several components independently own competing copies of the same truth. If a value is shared, define one authoritative owner and pass the value or update event through a clear interface.

```html
<form id="profile-form" novalidate>
  <label for="display-name">Display name</label>
  <input id="display-name" name="displayName"
         autocomplete="nickname" maxlength="32" required>
  <p id="name-error" role="alert" aria-live="polite"></p>
  <button id="save-profile" type="submit">Save profile</button>
  <p id="save-status" role="status" aria-live="polite"></p>
</form>

<script>
const form = document.querySelector("#profile-form");
const input = document.querySelector("#display-name");
const error = document.querySelector("#name-error");
const status = document.querySelector("#save-status");
const button = document.querySelector("#save-profile");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.textContent = "";
  status.textContent = "";

  const displayName = input.value.trim();
  if (displayName.length < 2 || displayName.length > 32) {
    error.textContent = "Enter a name between 2 and 32 characters.";
    input.setAttribute("aria-invalid", "true");
    input.focus();
    return;
  }

  input.removeAttribute("aria-invalid");
  button.disabled = true;
  button.textContent = "Saving…";

  try {
    // Replace this local placeholder with the real persistence adapter.
    // Do not show success until the real operation has succeeded.
    await Promise.resolve({ displayName });
    status.textContent = "Profile saved.";
  } catch (cause) {
    status.textContent = "Could not save the profile. Try again.";
    console.error("Profile save failed:", cause);
  } finally {
    button.disabled = false;
    button.textContent = "Save profile";
  }
});
</script>
```

This example demonstrates form state and error handling, not durable persistence. The placeholder must be replaced with the actual API or storage layer before describing the feature as saved across sessions.

## 21. CSS Architecture and Token Discipline

Use tokens for repeated design decisions. Avoid scattering near-identical colors, radii, shadows, spacing values, and transition durations across unrelated selectors.

```css
:root {
  color-scheme: dark;
  --color-bg: #0b1020;
  --color-surface: #141b2e;
  --color-surface-raised: #1b2540;
  --color-text: #f4f7ff;
  --color-muted: #a9b4cc;
  --color-primary: #8b7cff;
  --color-primary-hover: #a49aff;
  --color-danger: #ff737e;
  --color-border: rgb(220 230 255 / 14%);
  --radius-sm: 8px;
  --radius-md: 14px;
  --radius-lg: 22px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --content-width: 1120px;
  --focus-ring: 0 0 0 3px rgb(139 124 255 / 40%);
}
```

Rules:
- A token should represent a decision with repeated use or a meaningful semantic role.
- Use semantic tokens such as `--color-danger`, not names tied to one screen.
- Avoid using the primary brand color for every control; reserve it for emphasis and action.
- Keep contrast strong enough for text and interactive boundaries.
- Use one spacing scale unless the design system has a documented reason to diverge.
- Avoid global selectors that unexpectedly alter embedded widgets or third-party content.
- Do not use `!important` as a substitute for understanding the cascade.

## 22. Responsive Layout Must Be Content-Driven

Do not choose breakpoints only because a framework uses them. A breakpoint is justified when the content no longer fits comfortably.

```css
.page {
  width: min(calc(100% - 2rem), var(--content-width));
  margin-inline: auto;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

@media (max-width: 900px) {
  .dashboard-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .dashboard-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
```

Check at narrow mobile widths, typical mobile widths, tablet widths, and wide desktop widths. Inspect long translations, large text, empty states, validation messages, and unusually long names. Avoid fixed heights for content containers unless the product explicitly requires a bounded viewport.

## 23. Interaction State Machine

For asynchronous actions, explicitly model states instead of toggling arbitrary labels.

```text
idle
  | submit
  v
validating -- invalid --> invalid
  |
  v
loading -- success --> success
  |
  +-------- failure --> error
```

Each state should define what the user sees and what actions are allowed. During loading, prevent accidental duplicate submission if the operation is not idempotent. On failure, preserve user input and provide a retry path. On success, show the actual result, not a fabricated confirmation.

For destructive operations, include a clear target, consequence, confirmation when appropriate, and a recoverable path if the product supports one. A confirmation dialog does not make an unsafe server operation safe; authorization and validation must still occur at the trusted boundary.

## 24. Touch, Pointer, and Keyboard Behavior

- Use semantic `<button>` elements for actions and `<a>` elements for navigation.
- Make touch targets comfortably large and separated enough to avoid accidental activation.
- Do not rely on hover for essential information; touch devices may not have hover.
- Support visible keyboard focus.
- Ensure Escape closes dismissible overlays when expected.
- Return focus to the triggering control after closing a modal.
- Avoid trapping focus outside a modal or allowing keyboard focus to disappear behind it.
- Use pointer events for custom canvas interactions when both touch and mouse are needed.
- Prevent browser gestures only within the interaction surface that requires it; do not disable page zoom globally.

```css
button, [role="button"] {
  min-height: 44px;
}

:where(button, a, input, select, textarea, [tabindex]):focus-visible {
  outline: 2px solid var(--color-primary-hover);
  outline-offset: 3px;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

Prefer native controls over recreating browser behavior. Custom controls require custom accessibility work.

## 25. UI Performance and Rendering Discipline

- Avoid rebuilding large DOM subtrees for tiny state changes.
- Debounce expensive search requests where it improves behavior, while keeping the input responsive.
- Cancel or ignore stale asynchronous results so older requests cannot overwrite newer state.
- Lazy-load below-the-fold images when appropriate.
- Reserve image dimensions to reduce layout shift.
- Avoid expensive blur, huge shadows, and continuous animation on low-powered mobile devices.
- Use CSS transforms and opacity for simple animations where appropriate.
- Do not add a framework solely to implement a small interaction if the project does not already use one.
- Profile before claiming a performance bottleneck is fixed.

When rendering user-provided text, use `textContent` or framework-safe text interpolation. Do not inject untrusted strings into `innerHTML`. If rich HTML is genuinely required, sanitize it with a maintained sanitizer and document the trust boundary.

## 26. Visual QA Protocol

Evaluate the page in this order:
1. **Structure:** correct hierarchy, spacing, alignment, and grouping.
2. **Typography:** readable size, line height, weight, and line length.
3. **Color:** consistent tokens, contrast, meaningful emphasis.
4. **Interaction:** controls respond correctly, disabled states are real.
5. **Responsive behavior:** no clipping, horizontal overflow, or unreachable controls.
6. **Accessibility:** keyboard flow, labels, focus, status announcements.
7. **Failure states:** empty, loading, error, and validation states are designed.
8. **Consistency:** similar actions look and behave similarly.
9. **Performance:** no obvious avoidable reflow or heavy effects.
10. **Evidence:** screenshots, browser checks, or tests support the final claim.

A visually attractive screenshot does not prove the interface works. A functioning control does not prove the interface is accessible. Evaluate both.

## 27. UI Review Rubric

Score 0–2 for each: hierarchy, consistency, readability, responsiveness, accessibility, state handling, error recovery, performance, security of rendering, and fit to user intent. Explain any zero score and fix high-impact failures before polishing low-impact details. Do not invent a score based on intuition alone; use a concrete inspection or test for each dimension.
