---
name: design-skill
description: Design clean, professional UIs with CSS: direction, tokens, type scale, spacing, layout, components, dark mode, motion, accessibility and the review loop, with ready CSS.
---
# Design skill (UI, GUI, CSS)

Good design here means: one clear direction, a small token system, generous spacing, readable type, honest content. **Start from a template** (`use_template("web-landing")` for sites, `"web-app"` for tools) and adapt it; both score 100/100 on `review_ui`.

## 1. Decide the direction (write it in a CSS comment)
Pick ONE: editorial, warm minimal, soft neutral, technical/terminal, bold brutalist, playful (kids/games). Everything follows from it: color, type, radius, density. If the user gave no style, choose warm minimal or soft neutral. For games choose a dark, high-contrast palette with one bright accent.

## 2. Tokens first
```css
:root {
  /* color: neutrals tinted toward the accent hue, one accent */
  --bg: #f6f4ef;  --surface: #ffffff;  --ink: #1c2024;  --muted: #565d66;  --line: #dcd8cf;
  --accent: #1b6e50;  --accent-ink: #ffffff;  --accent-soft: #eef5f1;
  /* shape and depth */
  --radius: 14px;  --shadow: 0 1px 2px rgba(20,24,28,.06), 0 8px 24px rgba(20,24,28,.06);
  /* spacing scale: use only these */
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px; --space-5: 24px; --space-6: 32px; --space-7: 48px; --space-8: 72px;
  --font: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #14171a; --surface: #1b1f23; --ink: #eef0f2; --muted: #a2abb5; --line: #2c333a; --accent-soft: #1d2b25; }
}
```
Never write a literal color or pixel value in a component; use a token.

## 3. Color rules
- One accent. Neutrals do the rest. Semantic colors (error, success) only for states.
- Text contrast >= 4.5:1 (large text >= 3:1). Check the accent button text and the dark theme too; `review_ui` calculates it.
- Avoid pure `#000` on pure `#fff`; avoid saturated backgrounds behind long text.
- On dark surfaces lighten the accent used as text: `color-mix(in srgb, var(--accent) 45%, white)`.

## 4. Typography
```css
body { font: 1rem/1.6 var(--font); }
h1 { font-size: clamp(2.1rem, 5.6vw, 3.6rem); line-height: 1.1; letter-spacing: -.02em; }
h2 { font-size: clamp(1.6rem, 3.6vw, 2.25rem); line-height: 1.15; letter-spacing: -.02em; }
p  { max-width: 66ch; }
```
Scale of 6 to 8 sizes. Body 16px minimum. Headings tight, body loose. Line length 55 to 75 characters. Use weight and size for hierarchy, not color alone.

## 5. Layout recipes
```css
.wrap  { width: min(100% - 48px, 1080px); margin-inline: auto; }              /* container */
.grid  { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr)); }   /* responsive cards, no media query */
.stack > * + * { margin-top: var(--space-4); }                                  /* vertical rhythm */
.row   { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }
section { padding-block: clamp(48px, 9vw, 72px); }
```
Design at 360px wide first, then enhance with `@media (min-width: ...)`. Full height: `min-height: 100vh; min-height: 100dvh;`. No horizontal scroll, ever.

## 6. Components that feel finished
```css
.btn { min-height: 46px; padding: 0 24px; border-radius: 999px; border: 1px solid transparent; background: var(--accent); color: var(--accent-ink);
       font: 600 1rem var(--font); cursor: pointer; transition: transform .15s ease, box-shadow .15s ease; }
.btn:hover { box-shadow: var(--shadow); transform: translateY(-1px); }
.btn:active { transform: none; }
:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: var(--space-5); }
input, textarea { font: inherit; min-height: 46px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); color: inherit; }
input:hover { border-color: var(--muted); }
[aria-invalid="true"] { border-color: #c4352c; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
```
Every interactive element needs hover, `:focus-visible`, active and disabled states. Icons are inline SVG (`stroke: currentColor`), never emoji.

## 7. Content is design
Real, specific copy beats lorem ipsum. Headline says what it is; subhead says for whom; button says what happens ("Start free trial", not "Submit"). No fake stats, fake testimonials, or invented logos.

## 8. Avoid the generic-AI look
Purple/indigo-to-pink gradients, gradient text, glow and glassmorphism everywhere, three identical centered cards under a centered hero, emoji icons, "Welcome to my website", stock-photo placeholders, heavy drop shadows. Use whitespace, alignment and one accent instead.

## 9. Make it yours (a template is a start, not the result)
Axion compares your page with the template and sends you back when it is too similar. Changing the accent and the title is not design. Do all of these:
- **Identity:** a palette of 3 to 4 tokens (surface, ink, accent, one secondary tone), a deliberate type pairing, one shape language (sharp, soft, pill).
- **Real content and structure:** write the copy for THIS subject; remove sections that do not apply, add ones that do (gallery, timeline, comparison table, case studies, team, location, menu, schedule).
- **A custom hero visual** drawn with inline SVG or CSS, not the generic preview card.
- **A different layout rhythm:** split sections, a bento grid, large type, alternating rows.
```css
/* type pairing from system fonts: expressive headings, neutral body */
:root { --display: ui-serif, Georgia, "Times New Roman", serif; --accent-2: #c9772b; }
h1, h2 { font-family: var(--display); font-weight: 700; letter-spacing: -.01em; }
/* bento grid: uneven cards look designed */
.bento { display: grid; gap: 14px; grid-template-columns: repeat(6, 1fr); }
.bento > :nth-child(1) { grid-column: span 4; grid-row: span 2; }
.bento > :nth-child(2), .bento > :nth-child(3) { grid-column: span 2; }
.bento > :nth-child(n+4) { grid-column: span 2; }
@media (max-width: 760px) { .bento { grid-template-columns: 1fr; } .bento > * { grid-column: auto !important; grid-row: auto !important; } }
/* split section that alternates sides */
.split { display: grid; gap: 32px; align-items: center; grid-template-columns: 1fr; }
@media (min-width: 860px) { .split { grid-template-columns: 1fr 1fr; } .split:nth-of-type(even) > :first-child { order: 2; } }
```
```html
<!-- hero illustration: simple shapes in the brand colors, no image file needed -->
<svg viewBox="0 0 320 240" role="img" aria-label="Illustration of rising bars with a sun">
  <circle cx="250" cy="52" r="26" fill="var(--accent-2)"/>
  <rect x="40" y="130" width="46" height="80" rx="10" fill="var(--accent)" opacity=".35"/>
  <rect x="104" y="96" width="46" height="114" rx="10" fill="var(--accent)" opacity=".6"/>
  <rect x="168" y="58" width="46" height="152" rx="10" fill="var(--accent)"/>
  <path d="M20 214h280" stroke="var(--line)" stroke-width="3" stroke-linecap="round"/>
</svg>
```

## 10. The review loop (do it every time)
1. Build with tokens. 2. `verify_files`. 3. `review_ui`. 4. Fix every HIGH and MEDIUM finding with `edit_file`. 5. `review_ui` again until the score is >= 85. 6. `preview_web` and describe how to open it.

## Troubleshooting
| Problem | Fix |
|---|---|
| Looks cramped | Increase spacing tokens, line-height, section padding |
| Looks flat and boring | One bolder heading size, one accent block, consistent radius, real content |
| Mobile overflow | Find the element wider than the viewport (fixed px width, long word): `max-width: 100%`, `overflow-wrap: anywhere` |
| Low contrast flagged | Darken text or the accent, or switch to dark text on a light accent |
| Dark mode unreadable | Redefine tokens in the dark block, never hard-code colors in components |
