#!/usr/bin/env node
// Loads an HTML page in a stub browser (no real DOM, no network) and reports what a visitor would hit first:
// uncaught exceptions, canvas size and how many canvas draw calls each frame makes.
//   node scripts/page_check.js page.html [--frames 120] [--sizes 390x780,844x390]
// Exit code 0 = no problems found, 1 = problems found, 2 = bad usage. It cannot judge looks; it catches blank
// screens, dead animation loops and crashes. Pages that need a CDN library other than Three.js are only partly checked.
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");

const args = process.argv.slice(2);
const file = args.find((a, i) => !a.startsWith("--") && !(i > 0 && args[i - 1].startsWith("--")));
const opt = (name, def) => { const i = args.indexOf("--" + name); return i >= 0 && args[i + 1] ? args[i + 1] : def; };
if (!file) { console.error("usage: node page_check.js page.html [--frames 120] [--sizes 390x780,844x390]"); process.exit(2); }
const FRAMES = Math.max(2, parseInt(opt("frames", "120"), 10) || 120);
const SIZES = opt("sizes", "390x780,844x390").split(",").map((s) => s.split("x").map(Number)).filter((p) => p[0] > 0 && p[1] > 0);
let html;
try { html = fs.readFileSync(file, "utf8"); } catch (e) { console.error("cannot read " + file + ": " + e.message); process.exit(2); }
html = html.replace(/__([A-Z][A-Z0-9_]*)__/g, (m, k) => ({ TITLE: "Test", ACCENT: "#35c48f", LANG: "en" }[k] || m));
process.on("unhandledRejection", () => {});

const scripts = [], external = [];
for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
  const attrs = m[1], src = /\bsrc\s*=\s*["']?([^"'\s>]+)/i.exec(attrs);
  if (src) { external.push(src[1]); continue; }
  const type = /\btype\s*=\s*["']?([^"'\s>]+)/i.exec(attrs);
  if (type && !/javascript|ecmascript/i.test(type[1])) continue;          // json, importmap, module graphs
  if (!m[2].trim()) continue;
  const bodyStart = m.index + m[0].indexOf(">") + 1;
  scripts.push({ code: m[2], lineOffset: html.slice(0, bodyStart).split("\n").length - 1 });
}
const needsThree = external.some((s) => /three(\.min)?\.js/i.test(s));
const OTHER_LIBS = /\b(Phaser|PIXI|Chart|d3|jQuery|Matter|p5|Howl|gsap|\$)\b/;
let threeMock = null;
if (needsThree) { try { threeMock = require(path.join(__dirname, "..", "tests", "three_mock.js")); } catch (e) { threeMock = null; } }

const base = path.basename(file);
const where = (e) => { const m = new RegExp(base.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ":(\\d+)").exec(String(e && e.stack || "")); return m ? " (line " + m[1] + ")" : ""; };
const describe = (e) => (e && e.name ? e.name + ": " + e.message : String(e)) + where(e);

function run(vw, vh) {
  const problems = [], notes = [], listeners = {}, meta = new WeakMap(), cache = {}, raf = [];
  let paint = 0, clock = 0, timers = [], timerId = 0, canvasUsed = false, counter = 0;
  const on = (name, type, fn) => { const m = (listeners[name] = listeners[name] || {}); (m[type] = m[type] || []).push(fn); };
  const guard = (fn, label) => { try { return fn(); } catch (e) { problems.push((label ? label + ": " : "") + describe(e)); } };
  const emit = (name, type, evt) => (((listeners[name] || {})[type]) || []).slice().forEach((fn) =>
    guard(() => fn(Object.assign({ type, key: "", code: "", preventDefault() {}, stopPropagation() {}, target: {}, touches: [], changedTouches: [] }, evt || {})), type + " handler"));

  const PAINT = new Set(["fill", "stroke", "fillRect", "strokeRect", "fillText", "strokeText", "drawImage", "putImageData"]);
  const loose = () => new Proxy(function () {}, { get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : k === "then" ? undefined : loose()), apply: () => loose() });
  function makeCtx(el) {
    const props = { canvas: el, fillStyle: "#000", strokeStyle: "#000", globalAlpha: 1, font: "10px sans-serif", lineWidth: 1, textAlign: "start", textBaseline: "alphabetic",
      globalCompositeOperation: "source-over", shadowBlur: 0, shadowColor: "rgba(0,0,0,0)", lineCap: "butt", lineJoin: "miter", imageSmoothingEnabled: true, filter: "none" };
    return new Proxy({}, {
      get(_, k) {
        if (k in props) return props[k];
        if (typeof k === "symbol") return undefined;
        if (k === "measureText") return (t) => ({ width: String(t).length * 6 });
        if (/^create(Linear|Radial|Conic)Gradient$/.test(k)) return () => ({ addColorStop() {} });
        if (k === "createPattern") return () => ({});
        if (k === "getImageData" || k === "createImageData") return (x, y, w, h) => { const W = k === "createImageData" ? x : w, H = k === "createImageData" ? y : h; return { data: new Uint8ClampedArray(Math.max(0, W * H * 4)), width: W, height: H }; };
        if (k === "isPointInPath" || k === "isPointInStroke") return () => false;
        if (k === "getTransform") return () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 });
        return () => { if (PAINT.has(k) && meta.get(el).visible) paint++; };
      },
      set(_, k, v) { props[k] = v; return true; }
    });
  }
  function element(name, tag, visible) {
    if (cache[name]) return cache[name];
    const store = { tagName: String(tag || "div").toUpperCase(), hidden: false, value: "", checked: false, textContent: "", innerHTML: "", innerText: "", className: "", disabled: false,
      clientWidth: vw, offsetWidth: vw, scrollWidth: vw, clientHeight: vh, offsetHeight: vh, scrollHeight: vh, width: 300, height: 150, length: 0, dataset: {}, style: {} };
    const info = { name, visible: visible !== false, ctx: null, store };
    const mark = (n) => { const m = n && meta.get(n); if (m) m.visible = true; return n; };
    const p = new Proxy(function () {}, {
      get(t, k) {
        if (k === Symbol.toPrimitive) return () => 0;
        if (k === "then") return undefined;
        if (k in store) return store[k];
        switch (k) {
          case "addEventListener": return (type, fn) => on(name, type, fn);
          case "removeEventListener": case "setAttribute": case "removeAttribute": case "focus": case "blur": case "click": case "scrollIntoView": case "remove": case "replaceChildren": return () => {};
          case "getContext": return (kind) => { if (kind === "2d") { canvasUsed = true; return (info.ctx = info.ctx || makeCtx(p)); } info.webgl = true; return loose(); };
          case "getBoundingClientRect": return () => ({ left: 0, top: 0, x: 0, y: 0, right: store.clientWidth, bottom: store.clientHeight, width: store.clientWidth, height: store.clientHeight });
          case "classList": return { add() {}, remove() {}, toggle() { return false; }, contains() { return false; } };
          case "querySelectorAll": case "getElementsByClassName": case "getElementsByTagName": return () => [];
          case "querySelector": return (s) => element(name + ">" + s, "div", info.visible);
          case "children": case "childNodes": return [];
          case "getAttribute": case "closest": return () => null;
          case "contains": return () => false;
          case "appendChild": case "insertBefore": return (n) => mark(n);
          case "append": case "prepend": return (...ns) => ns.forEach(mark);
          case "parentElement": case "parentNode": return element(name + "^", "div", info.visible);
          case "toDataURL": return () => "data:,";
          default: return element(name + "." + String(k), "div", info.visible);
        }
      },
      set(t, k, v) { store[k] = v; return true; },
      apply() { return loose(); }
    });
    meta.set(p, info);
    cache[name] = p;
    return p;
  }

  const store = {}, localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; }, clear() {}, key: () => null, length: 0 };
  const doc = {
    getElementById: (id) => element("#" + id), querySelector: (s) => element("q:" + s), querySelectorAll: () => [], getElementsByClassName: () => [], getElementsByTagName: () => [],
    createElement: (tag) => element("el" + (++counter) + ":" + tag, tag, false), createElementNS: (ns, tag) => element("el" + (++counter) + ":" + tag, tag, false),
    createTextNode: (t) => ({ textContent: t }), createDocumentFragment: () => element("frag" + (++counter), "div", false),
    addEventListener: (type, fn) => on("document", type, fn), removeEventListener() {}, hidden: false, visibilityState: "visible", readyState: "complete", title: "",
    body: element("body"), documentElement: element("html"), head: element("head"), fonts: { ready: Promise.resolve(), load: () => Promise.resolve() }, activeElement: null
  };
  const sandbox = {
    document: doc, localStorage, sessionStorage: localStorage, navigator: { userAgent: "page_check", language: "en", vibrate() {}, maxTouchPoints: 1, onLine: true, clipboard: {} },
    location: { hash: "", href: "http://localhost/", search: "", pathname: "/", reload() {} }, history: { pushState() {}, replaceState() {} },
    innerWidth: vw, innerHeight: vh, devicePixelRatio: 2, outerWidth: vw, outerHeight: vh, screen: { width: vw, height: vh, orientation: { type: vw > vh ? "landscape-primary" : "portrait-primary", addEventListener() {} } },
    addEventListener: (type, fn) => on("window", type, fn), removeEventListener() {}, dispatchEvent() { return true; },
    requestAnimationFrame: (cb) => { raf.push(cb); return raf.length; }, cancelAnimationFrame() {},
    setTimeout: (fn, ms) => timers.push({ id: ++timerId, at: clock + Math.max(0, Number(ms) || 0), fn, every: 0 }) && timerId,
    setInterval: (fn, ms) => timers.push({ id: ++timerId, at: clock + Math.max(1, Number(ms) || 1), fn, every: Math.max(1, Number(ms) || 1) }) && timerId,
    clearTimeout: (id) => { timers = timers.filter((t) => t.id !== id); }, clearInterval: (id) => { timers = timers.filter((t) => t.id !== id); },
    performance: { now: () => clock }, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {}, removeEventListener() {} }),
    getComputedStyle: () => ({ getPropertyValue: () => "" }), scrollTo() {}, alert() {}, confirm: () => true, prompt: () => null, open() {}, focus() {},
    AudioContext: function () { return loose(); }, webkitAudioContext: function () { return loose(); }, Audio: function () { return loose(); }, Image: function () { return element("img" + (++counter), "img", false); },
    IntersectionObserver: function () { return { observe() {}, unobserve() {}, disconnect() {} }; }, ResizeObserver: function () { return { observe() {}, unobserve() {}, disconnect() {} }; },
    MutationObserver: function () { return { observe() {}, disconnect() {} }; }, Event: function (type, init) { Object.assign(this, { type }, init || {}); }, CustomEvent: function (type, init) { Object.assign(this, { type }, init || {}); },
    fetch: () => Promise.reject(new Error("network is disabled in page_check")), URL, Blob: function () {}, FormData: function () {}, TextEncoder, TextDecoder,
    console: { log() {}, info() {}, debug() {}, warn() {}, error: (...a) => notes.push("console.error: " + a.map(String).join(" ").slice(0, 160)) }
  };
  sandbox.window = sandbox; sandbox.self = sandbox; sandbox.globalThis = sandbox;
  if (threeMock) sandbox.THREE = threeMock;
  vm.createContext(sandbox);

  function tick(dt) {
    clock += dt;
    for (const t of timers.filter((x) => x.at <= clock)) { if (t.every) t.at = clock + t.every; else timers = timers.filter((x) => x !== t); guard(() => (typeof t.fn === "function" ? t.fn() : 0), "timer"); }
    for (const cb of raf.splice(0)) guard(() => cb(clock), "animation frame");
  }

  for (const s of scripts) {
    try { new vm.Script(s.code, { filename: path.basename(file), lineOffset: s.lineOffset }).runInContext(sandbox); }
    catch (e) {
      if (e && e.name === "ReferenceError" && (needsThree && !threeMock && /THREE/.test(e.message) || OTHER_LIBS.test(e.message))) { notes.push("needs a CDN library that is not loaded offline (" + e.message + "): draw check skipped"); sandbox.__skip = true; }
      else problems.push("script error: " + describe(e));
    }
  }
  if (sandbox.__skip) return { problems, notes, skipped: true };
  emit("document", "DOMContentLoaded"); emit("window", "load");

  const perFrame = [];
  const before = problems.length;
  for (let i = 0; i < FRAMES; i++) {
    const p0 = paint, queued = raf.length;
    tick(16.7);
    perFrame.push(paint - p0);
    if (i === 0 && queued === 0 && canvasUsed && timers.length === 0) notes.push("no requestAnimationFrame or timer loop was started");
  }
  const menuPaint = perFrame.reduce((a, b) => a + b, 0);
  // press anything that looks like a start control, then run more frames
  for (const name of Object.keys(listeners)) if (/start|play|begin|mulai|main|ov-btn|new/i.test(name) && (listeners[name].click || listeners[name].pointerdown)) { emit(name, "click"); emit(name, "pointerdown"); emit(name, "pointerup"); }
  for (const key of ["Enter", " ", "ArrowRight", "ArrowUp"]) { emit("window", "keydown", { key }); emit("document", "keydown", { key }); }
  let playPaint = 0;
  for (let i = 0; i < 60; i++) { const p0 = paint; tick(16.7); playPaint += paint - p0; }

  const visible = Object.values(cache).filter((p) => { const m = meta.get(p); return m.ctx && m.visible; });
  for (const p of visible) { const st = meta.get(p).store; if (!(st.width > 0 && st.height > 0)) problems.push("canvas " + meta.get(p).name + " has size " + st.width + "x" + st.height + ": nothing can be drawn"); }
  if (canvasUsed && visible.length && menuPaint + playPaint === 0) problems.push("no canvas draw calls in " + (FRAMES + 60) + " frames: the screen stays blank");
  else if (canvasUsed && visible.length && perFrame[0] === 0) notes.push("the first frame draws nothing (first paint at frame " + (perFrame.findIndex((n) => n > 0) + 1 || "after start") + ")");
  if (canvasUsed && visible.length && playPaint > 0 && perFrame.slice(-30).every((n) => n === 0) && raf.length === 0 && problems.length === before) notes.push("the animation loop stopped before the end of the run");
  if (!canvasUsed) notes.push("no 2D canvas used: draw check skipped");
  return { problems, notes, first: perFrame[0], avg: Math.round(menuPaint / FRAMES), playAvg: Math.round(playPaint / 60), canvases: visible.map((p) => meta.get(p).store.width + "x" + meta.get(p).store.height) };
}

let bad = 0;
console.log("page_check: " + path.basename(file) + " | inline scripts: " + scripts.length + (external.length ? " | external: " + external.length : "") + (needsThree ? (threeMock ? " | Three.js: stub" : " | Three.js: not available") : ""));
for (const [w, h] of SIZES) {
  const r = run(w, h), uniq = Array.from(new Set(r.problems)).slice(0, 6);
  bad += uniq.length;
  console.log("  " + w + "x" + h + ": " + (uniq.length ? "PROBLEM" : "ok") + (r.skipped ? "" : " | draw calls: first frame " + r.first + ", menu avg " + r.avg + "/frame, after start avg " + r.playAvg + "/frame | canvas " + (r.canvases.join(", ") || "none")));
  uniq.forEach((p) => console.log("    PROBLEM: " + p));
  Array.from(new Set(r.notes)).slice(0, 4).forEach((n) => console.log("    note: " + n));
}
console.log(bad ? "RESULT: " + bad + " problem(s) found" : "RESULT: ok");
process.exit(bad ? 1 : 0);
