// Runs the <script> of an HTML template in a stubbed browser (no real DOM) and drives it with scripted scenarios.
// Usage: node tests/dom_harness.js <template.html> [vars-json]
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");

const file = process.argv[2];
const vars = Object.assign({ TITLE: "Test", ACCENT: "#35c48f", LANG: "en" }, JSON.parse(process.argv[3] || "{}"));
let html = fs.readFileSync(file, "utf8").replace(/__([A-Z][A-Z0-9_]*)__/g, (m, k) => (k in vars ? vars[k] : m));
const scripts = [];
html.replace(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi, (m, attrs, body) => { if (!/\bsrc\s*=/.test(attrs) && body.trim()) scripts.push(body); return m; });

const listeners = new Map();                       // stub name -> {type: [fn]}
function on(name, type, fn) { const m = listeners.get(name) || {}; (m[type] = m[type] || []).push(fn); listeners.set(name, m); }
function emit(name, type, evt) { const m = listeners.get(name) || {}; (m[type] || []).slice().forEach((fn) => fn(Object.assign({ preventDefault() {}, stopPropagation() {}, target: { closest() { return null; } } }, evt || {}))); }

const cache = new Map();
function stub(name, props) {
  if (cache.has(name)) return cache.get(name);
  const store = Object.assign({ hidden: false, value: "", checked: false, textContent: "", innerHTML: "", length: 0 }, props || {});
  const p = new Proxy(function () {}, {
    get(t, k) {
      if (k === Symbol.toPrimitive) return () => 0;
      if (k === "then") return undefined;
      if (k in store) return store[k];
      if (k === "addEventListener") return (type, fn) => on(name, type, fn);
      if (k === "removeEventListener") return () => {};
      if (k === "style") return (store.style = store.style || {});
      if (k === "dataset") return (store.dataset = store.dataset || {});
      if (k === "classList") return { add() {}, remove() {}, toggle() { return false; }, contains() { return false; } };
      if (k === "getBoundingClientRect") return () => ({ left: 0, top: 0, width: 360, height: 640, right: 360, bottom: 640 });
      if (k === "getContext") return () => ctx2d;
      if (k === "measureText") return () => ({ width: 10 });
      if (k === "querySelectorAll" || k === "getElementsByClassName" || k === "getElementsByTagName") return () => [];
      if (k === "children" || k === "childNodes") return [];
      if (k === "getAttribute") return () => null;
      return stub(name + "." + String(k));
    },
    set(t, k, v) { store[k] = v; return true; },
    apply() { return stub(name + "()"); },
    construct() { return stub("new " + name); }
  });
  cache.set(name, p);
  return p;
}
const CTX_PROPS = new Set(["fillStyle", "strokeStyle", "font", "textAlign", "textBaseline", "globalAlpha", "lineWidth", "lineCap", "lineJoin",
  "shadowBlur", "shadowColor", "shadowOffsetX", "shadowOffsetY", "imageSmoothingEnabled", "globalCompositeOperation", "filter", "canvas"]);
const ctx2dStore = {};
const ctx2d = new Proxy({}, {
  get(t, k) {
    if (k === "measureText") return () => ({ width: 10 });
    if (k === "createLinearGradient" || k === "createRadialGradient" || k === "createPattern") return () => ({ addColorStop() {} });
    if (CTX_PROPS.has(k)) return ctx2dStore[k];
    return () => {};
  },
  set(t, k, v) { ctx2dStore[k] = v; return true; }
});

const rafQueue = [];
const store = {};
const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } };
const win = stub("window", { innerWidth: 390, innerHeight: 780, devicePixelRatio: 2, localStorage });
const doc = stub("document", { hidden: false, readyState: "complete", documentElement: stub("html"), body: stub("body") });
const sandbox = {
  window: win, document: doc, localStorage, navigator: { userAgent: "node", vibrate() {} }, console,
  requestAnimationFrame: (cb) => { rafQueue.push(cb); return rafQueue.length; }, cancelAnimationFrame() {},
  setTimeout: (fn) => { try { fn(); } catch (e) { errors.push(e); } return 1; }, clearTimeout() {}, setInterval: () => 1, clearInterval() {},
  performance: { now: () => Date.now() }, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  AudioContext: function () { return stub("ac"); }, getComputedStyle: () => ({ getPropertyValue: () => "" }), Intl,
  IntersectionObserver: function () { return { observe() {}, unobserve() {}, disconnect() {} }; },
  ResizeObserver: function () { return { observe() {}, disconnect() {} }; }, URL, Blob: function () {}, FormData: function () {}
};
doc.getElementById = (id) => stub("#" + id);
doc.querySelector = (sel) => stub("q:" + sel);
doc.createElement = (tag) => { const s = stub("el:" + tag + ":" + Math.random()); return s; };
doc.createElementNS = doc.createElement;
doc.createTextNode = (t) => ({ textContent: t });
if (/three\.min\.js/.test(html)) sandbox.THREE = require("./three_mock.js");
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
const errors = [];
for (const code of scripts) { try { vm.runInContext(code, sandbox, { filename: path.basename(file) }); } catch (e) { errors.push(e); } }
emit("document", "DOMContentLoaded"); emit("window", "load");

function frames(n, dtMs) { let t = frames.t || 0; for (let i = 0; i < n; i++) { const cbs = rafQueue.splice(0); t += dtMs || 16.7; for (const cb of cbs) { try { cb(t); } catch (e) { errors.push(e); } } } frames.t = t; }
function check(name, cond) { console.log((cond ? "  ok   " : "  FAIL ") + name); if (!cond) errors.push(new Error("check failed: " + name)); }

const base = path.basename(file);
const g = () => sandbox.window.game || vm.runInContext("typeof game !== 'undefined' ? game : undefined", sandbox);
console.log("harness:", base, "| scripts:", scripts.length);
if (/game-2d/.test(base)) {
  const game = vm.runInContext("window.game", sandbox);
  check("window.game exposed", !!game);
  frames(30);
  emit("#ov-btn", "click");
  check("state is play after Play click", game.G.state === "play");
  const x0 = game.G.player.x;
  emit("window", "keydown", { key: "ArrowRight", repeat: false }); frames(60);
  check("player moves right with ArrowRight", game.G.player.x > x0 + 30);
  emit("window", "keyup", { key: "ArrowRight" });
  game.G.orbs.push({ x: game.G.player.x, y: game.G.player.y, r: 10, value: 10, bonus: false, life: 5, age: 0 }); const s0 = game.G.score; frames(3);
  check("collecting an orb raises the score", game.G.score > s0);
  game.G.hazards.push({ x: game.G.player.x, y: game.G.player.y, vx: 0, vy: 0, r: 13, spin: 0, rot: 0, bounces: 0 }); game.G.player.inv = 0; game.G.player.dashT = 0; const l0 = game.G.lives; frames(3);
  check("hazard costs a life", game.G.lives === l0 - 1);
  emit("window", "keydown", { key: "Escape", repeat: false }); check("Escape pauses", game.G.state === "pause");
  emit("window", "keydown", { key: "Escape", repeat: false }); check("Escape resumes", game.G.state === "play");
  emit("window", "keydown", { key: " ", repeat: false }); frames(5); check("dash does not crash", true);
  const canvas = "#game";
  emit(canvas, "pointerdown", { clientX: 40, clientY: 400, pointerId: 1 }); emit(canvas, "pointermove", { clientX: 90, clientY: 380, pointerId: 1 }); frames(20); emit(canvas, "pointerup", { pointerId: 1 });
  for (let i = 0; i < 1500; i++) { // fuzz: random input for ~25 simulated seconds
    const keys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "w", "a", "s", "d", " "], k = keys[Math.floor(Math.random() * keys.length)];
    if (i % 7 === 0) emit("window", "keydown", { key: k, repeat: false }); if (i % 11 === 0) emit("window", "keyup", { key: k });
    if (game.G.state === "over") emit("#ov-btn", "click"); frames(1);
  }
  check("fuzz run finished without exceptions", errors.length === 0);
}
if (/game-3d/.test(base)) {
  const game = vm.runInContext("window.game", sandbox);
  check("window.game exposed", !!game);
  frames(10);
  emit("#ov-btn", "click"); check("state is play", game.G.state === "play");
  emit("window", "keydown", { key: "w", repeat: false }); frames(60); emit("window", "keyup", { key: "w" });
  check("player moved", Math.abs(game.player.position.x) + Math.abs(game.player.position.z) > 0.5);
  game.collectNearest && game.collectNearest(); frames(2);
  for (let i = 0; i < 1200; i++) { if (i % 9 === 0) emit("window", "keydown", { key: ["w", "a", "s", "d"][i % 4], repeat: false }); if (i % 13 === 0) emit("window", "keyup", { key: ["w", "a", "s", "d"][(i + 1) % 4] });
    if (game.G.state === "over") emit("#ov-btn", "click"); frames(1); }
  check("fuzz run finished without exceptions", errors.length === 0);
}
if (/web-app/.test(base)) {
  const app = vm.runInContext("window.app", sandbox);
  check("window.app exposed", !!app);
  const n0 = app.state.items.length;
  app.add("Write tests", "high"); check("add item", app.state.items.length === n0 + 1);
  const id = app.state.items[app.state.items.length - 1].id;
  app.toggle(id); check("toggle item", app.state.items.find((i) => i.id === id).done === true);
  app.setFilter("done"); check("filter applied", app.visible().every((i) => i.done));
  app.setFilter("all"); app.update(id, { title: "Write more tests" }); check("update item", app.state.items.find((i) => i.id === id).title === "Write more tests");
  app.remove(id); check("remove item", !app.state.items.some((i) => i.id === id));
  app.undo && app.undo(); check("undo restores item", app.state.items.some((i) => i.id === id));
  check("empty title rejected", app.add("   ", "low") === null);
}
if (/web-landing/.test(base)) {
  emit("#nav-toggle", "click"); emit("#theme-toggle", "click"); emit("#contact-form", "submit");
  check("landing handlers ran", true);
}
if (errors.length) { console.log("ERRORS:"); errors.slice(0, 5).forEach((e) => console.log("  " + (e && e.stack ? e.stack.split("\n").slice(0, 3).join(" | ") : e))); process.exit(1); }
console.log("PASS");
