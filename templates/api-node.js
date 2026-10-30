#!/usr/bin/env node
/**
 * __TITLE__: a JSON REST API on Node 18+ with no dependencies. Data is kept in a JSON file.
 *
 * Run:        node api.js                    listens on port __PORT__ (override with PORT or --port)
 * Self test:  node api.js --selftest         starts on a free port, calls every route, exits 0 when all pass
 * Try:        curl -s localhost:__PORT__/items
 *             curl -s -X POST localhost:__PORT__/items -H 'Content-Type: application/json' -d '{"name":"First item"}'
 *
 * Routes:     GET /health
 *             GET /items?q=text&limit=20&after=<id>     POST /items
 *             GET /items/<id>     PATCH /items/<id>     DELETE /items/<id>
 * Settings:   DATA_FILE (default data.json), API_KEY (when set, writes need the X-API-Key header), CORS_ORIGIN (default *)
 *
 * EDIT: validate() and the routes for your own resource. For more than a few thousand records or several processes,
 * move the Store class to SQLite (see the database skill); the routes do not change.
 */
import http from "node:http";
import { readFile, writeFile, rename, mkdtemp } from "node:fs/promises";
import { timingSafeEqual } from "node:crypto";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const API_KEY = process.env.API_KEY || "";
const MAX_BODY = 64 * 1024;

class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    Object.assign(this, { status, code, details });
  }
}

/** JSON file store. Writes are queued so two requests can never interleave a save. */
class Store {
  constructor(file) { this.file = file; this.data = null; this.queue = Promise.resolve(); }

  async load() {
    if (this.data) return this.data;
    try { this.data = JSON.parse(await readFile(this.file, "utf8")); }
    catch (err) {
      if (err.code !== "ENOENT") throw err;
      this.data = { nextId: 1, items: [] };
    }
    return this.data;
  }

  save() {
    const run = async () => {
      const tmp = this.file + ".tmp";
      await writeFile(tmp, JSON.stringify(this.data, null, 2));
      await rename(tmp, this.file);                      // atomic: never a half-written file
    };
    this.queue = this.queue.then(run, run);
    return this.queue;
  }
}

/** Check one item sent by a client. Returns the clean fields or throws ApiError 422. */
function validate(body, partial = false) {
  if (typeof body !== "object" || body === null || Array.isArray(body)) throw new ApiError(422, "invalid_body", "The body must be a JSON object");
  const clean = {}, errors = {};
  if ("name" in body || !partial) {
    if (typeof body.name === "string" && body.name.trim().length >= 1 && body.name.trim().length <= 120) clean.name = body.name.trim();
    else errors.name = "required, 1 to 120 characters";
  }
  if ("note" in body) {
    if (typeof body.note === "string" && body.note.length <= 2000) clean.note = body.note;
    else errors.note = "text up to 2000 characters";
  }
  if ("done" in body) {
    if (typeof body.done === "boolean") clean.done = body.done;
    else errors.done = "true or false";
  }
  const extra = Object.keys(body).filter((k) => !["name", "note", "done"].includes(k));
  if (extra.length) errors.unknown = "unexpected field(s): " + extra.sort().join(", ");
  if (Object.keys(errors).length) throw new ApiError(422, "validation_failed", "Some fields are invalid", errors);
  return clean;
}

function intParam(params, name, def, lo, hi) {
  const raw = params.get(name);
  const value = raw === null ? def : Number(raw);
  if (!Number.isInteger(value) || value < lo || value > hi) throw new ApiError(400, "bad_parameter", `${name} must be an integer between ${lo} and ${hi}`);
  return value;
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY) throw new ApiError(413, "too_large", `The body is larger than ${MAX_BODY} bytes`);
    chunks.push(chunk);
  }
  if (!size) throw new ApiError(400, "empty_body", "A JSON body is required");
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8")); }
  catch { throw new ApiError(400, "invalid_json", "The body is not valid JSON"); }
}

function sameKey(given) {
  const a = Buffer.from(given), b = Buffer.from(API_KEY);
  return a.length === b.length && timingSafeEqual(a, b);
}

export function createServer(store) {
  const routes = [];
  const route = (method, pattern, fn) => routes.push({ method, rx: new RegExp(`^${pattern}$`), fn });

  route("GET", "/health", () => [200, { status: "ok", name: "__TITLE__" }]);

  route("GET", "/items", async ({ params }) => {
    const limit = intParam(params, "limit", 20, 1, 100), after = intParam(params, "after", 0, 0, Number.MAX_SAFE_INTEGER);
    const q = (params.get("q") || "").slice(0, 100).toLowerCase();
    const { items } = await store.load();
    const page = items.filter((i) => i.id > after && i.name.toLowerCase().includes(q)).slice(0, limit);
    return [200, { items: page, next_after: page.length === limit ? page[page.length - 1].id : null }];
  });

  route("POST", "/items", async ({ req }) => {
    const clean = validate(await readJson(req));
    const data = await store.load();
    const item = { id: data.nextId++, name: clean.name, note: clean.note ?? "", done: clean.done ?? false, created: Math.floor(Date.now() / 1000) };
    data.items.push(item);
    await store.save();
    return [201, item, { Location: `/items/${item.id}` }];
  });

  const find = async (id) => {
    const item = (await store.load()).items.find((i) => i.id === Number(id));
    if (!item) throw new ApiError(404, "not_found", `No item with id ${id}`);
    return item;
  };
  route("GET", "/items/(\\d+)", async ({ match }) => [200, await find(match[1])]);
  route("PATCH", "/items/(\\d+)", async ({ req, match }) => {
    const item = await find(match[1]);
    Object.assign(item, validate(await readJson(req), true));
    await store.save();
    return [200, item];
  });
  route("DELETE", "/items/(\\d+)", async ({ match }) => {
    const item = await find(match[1]);
    const data = await store.load();
    data.items.splice(data.items.indexOf(item), 1);
    await store.save();
    return [204, null];
  });

  return http.createServer(async (req, res) => {
    const send = (status, payload, headers = {}) => {
      const body = payload === null || payload === undefined ? "" : JSON.stringify(payload);
      res.writeHead(status, {
        "Content-Type": "application/json; charset=utf-8", "Content-Length": Buffer.byteLength(body),
        "Access-Control-Allow-Origin": process.env.CORS_ORIGIN || "*", "Access-Control-Allow-Headers": "Content-Type, X-API-Key",
        "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS", ...headers,
      });
      res.end(body);
    };
    try {
      const url = new URL(req.url, "http://localhost");
      if (req.method === "OPTIONS") return send(204, null);
      let known = false;
      for (const r of routes) {
        const match = r.rx.exec(url.pathname);
        if (!match) continue;
        known = true;
        if (r.method !== req.method) continue;
        if (r.method !== "GET" && API_KEY && !sameKey(req.headers["x-api-key"] || "")) throw new ApiError(401, "unauthorized", "Missing or wrong X-API-Key header");
        const [status, payload, headers] = await r.fn({ req, match, params: url.searchParams });
        return send(status, payload, headers);
      }
      throw known ? new ApiError(405, "method_not_allowed", `This path does not accept ${req.method}`) : new ApiError(404, "not_found", `No such path: ${url.pathname}`);
    } catch (err) {
      if (err instanceof ApiError) return send(err.status, { error: { code: err.code, message: err.message, details: err.details ?? null } });
      console.error(err);
      send(500, { error: { code: "internal", message: "Internal server error" } });
    }
  });
}

async function selftest() {
  const dir = await mkdtemp(join(tmpdir(), "api-selftest-"));
  const server = createServer(new Store(join(dir, "data.json")));
  await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
  const base = `http://127.0.0.1:${server.address().port}`;
  const call = async (method, path, body, raw) => {
    const res = await fetch(base + path, { method, headers: { "Content-Type": "application/json" }, body: raw ?? (body === undefined ? undefined : JSON.stringify(body)) });
    const text = await res.text();
    return [res.status, text ? JSON.parse(text) : null];
  };
  const failures = [];
  const check = (label, got, want) => { if (JSON.stringify(got) !== JSON.stringify(want)) failures.push(`${label}: got ${JSON.stringify(got)}, wanted ${JSON.stringify(want)}`); };
  try {
    check("health", (await call("GET", "/health"))[0], 200);
    const [st, item] = await call("POST", "/items", { name: "  First  ", note: "hello" });
    check("create", [st, item.name], [201, "First"]);
    check("search", (await call("GET", "/items?q=fir"))[1].items.map((i) => i.name), ["First"]);
    check("get", (await call("GET", `/items/${item.id}`))[1].note, "hello");
    const [, changed] = await call("PATCH", `/items/${item.id}`, { done: true });
    check("patch", [changed.done, changed.name], [true, "First"]);
    const [vs, err] = await call("POST", "/items", { name: "", color: "red" });
    check("validation", [vs, Object.keys(err.error.details).sort()], [422, ["name", "unknown"]]);
    check("bad json", (await call("POST", "/items", undefined, "{nope"))[0], 400);
    check("bad limit", (await call("GET", "/items?limit=abc"))[0], 400);
    check("unknown id", (await call("GET", "/items/999"))[0], 404);
    check("unknown path", (await call("GET", "/nothing"))[0], 404);
    check("wrong method", (await call("POST", "/health", {}))[0], 405);
    for (let i = 0; i < 3; i++) await call("POST", "/items", { name: `n${i}` });
    const [, pg] = await call("GET", "/items?limit=2");
    check("next_after", pg.next_after, pg.items[1].id);
    check("delete", (await call("DELETE", `/items/${item.id}`))[0], 204);
    check("deleted is gone", (await call("GET", `/items/${item.id}`))[0], 404);
    const saved = JSON.parse(await readFile(join(dir, "data.json"), "utf8"));
    check("persisted", saved.items.length, 3);
  } finally { server.close(); }
  failures.forEach((f) => console.log("FAIL", f));
  console.log(`selftest: ${failures.length ? failures.length + " check(s) failed" : "all checks passed"}`);
  return failures.length ? 1 : 0;
}

const isMain = Boolean(process.argv[1]) && fileURLToPath(import.meta.url) === resolve(process.argv[1]);
if (isMain) {
  if (process.argv.includes("--selftest")) {
    process.exitCode = await selftest();
  } else {
    const portArg = process.argv.indexOf("--port");
    const port = Number(portArg > 0 ? process.argv[portArg + 1] : process.env.PORT || "__PORT__");
    const server = createServer(new Store(process.env.DATA_FILE || "data.json"));
    server.listen(port, "0.0.0.0", () => console.log(`listening on http://0.0.0.0:${port}`));
    const stop = () => server.close(() => process.exit(0));
    process.on("SIGINT", stop);
    process.on("SIGTERM", stop);
  }
}
