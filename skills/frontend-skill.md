---
name: frontend-skill
description: Build web apps with plain HTML/CSS/JS: state and render pattern, events, forms, fetch, storage, dialogs, accessibility, performance, debugging, with code.
---
# Frontend skill (vanilla HTML, CSS, JavaScript)

For calculators, trackers, dashboards, quizzes, small tools. One self-contained file unless the user wants a project. **Start from the template:** `use_template(name="web-app", path="index.html", vars={"TITLE": "..."})`, then adapt it. It already contains everything below, tested.

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
