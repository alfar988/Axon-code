---
name: frontend-skill
description: Build web apps with plain HTML/CSS/JS: state and render pattern, events, forms, fetch, storage, dialogs, accessibility, performance, debugging, with code.
---
# Frontend skill (vanilla HTML, CSS, JavaScript)

For calculators, trackers, dashboards, quizzes, small tools. One self-contained file unless the user wants a project. **Start from the template:** `use_template(name="web-app", path="index.html", vars={"TITLE": "..."})`, then adapt it. It already contains everything below, tested.

## Quick rules (read first)
1. Keep one `state` object. A `render()` function draws the page from it. Events change the state and call `render()`.
2. Put user text on the page with `textContent`, never `innerHTML`.
3. Wrap `localStorage` in `try/catch`: it can be blocked or full, and the page must still work.
4. Every input has a `<label>`. Every button has text or an `aria-label`. Everything works with the keyboard.
5. Show all four states of anything that loads: loading, empty, error, success.
6. Put the script at the end of the body or use `defer`. Do not use a library for something three lines of code can do.

## Safety in this skill
- Do not build pages that copy what people type into a form to a third party, imitate a login page of another service, fingerprint visitors, run hidden code such as a cryptominer, or load scripts you cannot name and justify.
- Always treat text from users, URLs and APIs as untrusted: no `innerHTML`, `eval` or `document.write` with it.

## The pattern: state -> render -> events
```javascript
const state = { items: [], filter: "all" };            // the only source of truth
function render() {                                    // rebuild the view from state, nothing else
  const list = document.getElementById("list");
  list.textContent = "";
  for (const it of visible()) {
    const li = document.createElement("li");
    li.dataset.id = it.id;
    li.textContent = it.title;                         // textContent: user text is never parsed as HTML
    list.appendChild(li);
  }
}
function add(title) { state.items.push({ id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()), title }); save(); render(); }
list.addEventListener("click", (e) => {                // one listener on the container (event delegation)
  const li = e.target.closest("li[data-id]"); if (li) toggle(li.dataset.id);
});
```
Rules: handlers change state, then call `render()`. No scattered DOM mutation. IDs, not array indexes, identify items.

## Storage that cannot crash the page
```javascript
const Store = {
  get(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(key, value)    { try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; } }
};
```
Private mode and full storage throw; wrap every access. Version the saved shape (`app:v1`).

## Forms and validation
```html
<form id="f" novalidate>
  <label for="email">Email</label>
  <input id="email" type="email" autocomplete="email" required aria-describedby="email-err">
  <p id="email-err" class="error" role="alert"></p>
  <button type="submit">Save</button>
</form>
```
```javascript
f.addEventListener("submit", (e) => {
  e.preventDefault();
  const email = f.email.value.trim();
  const ok = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  document.getElementById("email-err").textContent = ok ? "" : "Enter a valid email address.";
  f.email.toggleAttribute("aria-invalid", !ok);
  if (ok) submit(email);
});
```
Every input has a `<label>`; errors appear next to the field; keep the user's input on failure.

## Network calls
Use the `getJSON` helper from the code-quality skill: timeout, status check, clear error. Show three states in the UI: loading, error (with a retry button), data. Never leave the user staring at an empty screen.

## Common building blocks
```javascript
const debounce = (fn, ms = 200) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const fmtMoney = (n) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(n);
const fmtDate  = (d) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(d));
```
Dialog: use the native `<dialog>` with `showModal()` (focus trap and Escape for free). Toast with Undo: keep the removed item in state and restore it. Live regions: `<p role="status" aria-live="polite">` announces changes to screen readers.

## Accessibility minimum
Semantic elements (`header nav main footer button a`), visible focus (`:focus-visible`), labels, alt text, color contrast >= 4.5:1, everything usable by keyboard, tap targets >= 44px. Run `review_ui` to check.

## Performance
Do not re-render the whole list for a counter change; update only the text node. Batch DOM writes. Use `requestAnimationFrame` for animation, `IntersectionObserver` for reveal-on-scroll, `loading="lazy"` for images below the fold.

## Debugging in the browser
| Symptom | Likely cause | Fix |
|---|---|---|
| Blank page | Exception in the script before render | Look at the first error; run verify_files; check script order |
| `Cannot read properties of null` | `getElementById` ran before the element existed or the id is misspelled | Put `<script>` at the end of body; check the id |
| Click does nothing | Listener attached to an element that was re-rendered | Use event delegation on a stable parent |
| Works once, then stale | State changed but `render()` not called | Call render after every state change |
| Saved data gone | localStorage blocked or key changed | Wrap in try/catch, version the key |
| Layout breaks on phone | Fixed widths, missing viewport meta | `meta viewport`, `max-width`, `clamp()`, grid `auto-fit` |

## Finish
`verify_files`, `review_ui` (fix HIGH and MEDIUM), then `preview_web` and tell the user how to open it.

## Good and bad examples

### 1. Showing user text
Bad: a comment containing `<img src=x onerror=...>` runs code.
```js
list.innerHTML += "<li>" + comment + "</li>";
```
Good:
```js
// check: syntax
function addComment(list, comment) {
  const li = document.createElement("li");
  li.textContent = comment;
  list.appendChild(li);
}
```

### 2. Saving data
Bad: `localStorage.setItem("score", n)` throws in private mode and the page stops.
Good:
```js
// check: syntax
function saveScore(n) {
  try { localStorage.setItem("score", String(n)); } catch (e) { /* storage unavailable: keep playing */ }
}
function loadScore() {
  try { return Number(localStorage.getItem("score")) || 0; } catch (e) { return 0; }
}
```

### 3. Loading data
Bad: assume the request works.
```js
const items = await (await fetch("/api/items")).json();
render(items);
```
Good: handle failure and empty results.
```js
// check: syntax
async function loadItems(state, render) {
  state.status = "loading"; render();
  try {
    const res = await fetch("/api/items");
    if (!res.ok) throw new Error("HTTP " + res.status);
    state.items = await res.json();
    state.status = state.items.length ? "ready" : "empty";
  } catch (e) {
    state.status = "error"; state.message = "Could not load items. Check your connection and try again.";
  }
  render();
}
```

### 4. Forms
Bad: a placeholder used as the only label, and an error that only turns the border red.
Good: `<label for="email">Email</label>` and a message under the field: "Enter an address like name@example.com."

### 5. Buttons
Bad: `<div onclick="save()">Save</div>`. Good: `<button type="button">Save</button>` (focusable, keyboard-friendly, announced as a button).

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Script runs before the element exists | Use `defer` or put the script at the end of `<body>` |
| Handlers lost after re-render | Put one listener on the parent and check `event.target` |
| Page jumps while loading | Reserve space with `min-height` or a skeleton |
| Mobile keyboard covers the input | Use `scrollIntoView({block: "center"})` on focus |
| Huge list freezes the page | Render a page at a time, or use a simple virtual list |
| Works only with the mouse | Test Tab, Enter and Escape |

## Checklist before you finish
- [ ] State, render and events are separate and easy to follow.
- [ ] No `innerHTML` with outside text; storage is wrapped in `try/catch`.
- [ ] Loading, empty, error and success states all exist.
- [ ] Labels, focus and keyboard use work; it fits a 360px screen.
- [ ] I opened the page (or ran `page_check`) and there are no console errors.
