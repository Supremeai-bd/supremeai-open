/**
 * sdk.test.mjs — @supremeai/sdk offline harness (issue #338 AC3).
 *
 * Zero test-runtime dependencies: node:test + node:http only. Runs against
 * the BUILT package (dist/esm) so the dual-build output is what's verified:
 *   1. SSE parsing  — streamStatusFetch over a local mock /sse endpoint
 *  2. Tool serialization — JSON-RPC envelope shape + invocation_id correlation
 *  3. Error translation — 429→SdkRateLimited(Retry-After), 403→SdkForbidden,
 *     JSON-RPC error → honest envelope, transport failure → retryable
 *  4. Packaging contract — dual CJS/ESM resolvable, declaration maps shipped
 */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const pkgRoot = join(here, "..");
const esmEntry = join(pkgRoot, "dist", "esm", "index.js");
const cjsEntry = join(pkgRoot, "dist", "cjs", "index.js");

const sdk = await import(pathToFileURL(esmEntry).href);

// ---------------------------------------------------------------------------
// Mock tower: /health, /sse, /mcp (JSON-RPC), /private 401, /gated 403,
// /throttled 429 (+Retry-After). Mirrors the Python harness surface.
// ---------------------------------------------------------------------------

function startMock(port = 0) {
  const server = createServer((req, res) => {
    const url = new URL(req.url, "http://x");
    const send = (status, obj, headers = {}) => {
      const raw = JSON.stringify(obj);
      res.writeHead(status, { "Content-Type": "application/json", ...headers });
      res.end(raw);
    };
    if (url.pathname === "/health") {
      send(200, { status: "ok", mock: true });
    } else if (url.pathname === "/sse") {
      res.writeHead(200, { "Content-Type": "text/event-stream" });
      const frames = [
        { frame_type: "event", seq: 1, timestamp: "2026-02-14T09:30:00Z", event: "agent:started", task_id: "task-338", agent_id: "agent-1", payload: { goal: "harness" } },
        { frame_type: "heartbeat", seq: 2, timestamp: "2026-02-14T09:30:05Z", heartbeat: { kind: "ping", interval_seconds: 30 } },
        { frame_type: "event", seq: 3, timestamp: "2026-02-14T09:30:10Z", event: "agent:done", task_id: "task-338", agent_id: "agent-1", payload: { summary: "harness complete" } },
      ];
      for (const f of frames) res.write(`data: ${JSON.stringify(f)}\n\n`);
      res.end();
    } else if (url.pathname === "/mcp" && req.method === "POST") {
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        const rpc = JSON.parse(body);
        if (rpc.params.name === "boom") {
          send(200, { jsonrpc: "2.0", id: rpc.id, error: { code: -32601, message: "unknown tool: boom" } });
        } else if (rpc.params.name === "forbidden-probe") {
          send(403, { error: "forbidden" });
        } else {
          send(200, { jsonrpc: "2.0", id: rpc.id, result: { tool: rpc.params.name, echo: rpc.params.arguments } });
        }
      });
    } else if (url.pathname === "/tasks/dispatch" && req.method === "POST") {
      // throttled dispatch — the happy-path dispatch test uses its own echo
      // server, so the shared mock's dispatch route exercises the 429 path
      // (Retry-After carried, matching the Python harness's /throttled GET).
      send(429, { error: "rate limit exceeded" }, { "Retry-After": "2" });
    } else if (url.pathname === "/private") {
      send(401, { error: "unauthorized" });
    } else if (url.pathname === "/gated") {
      send(403, { error: "forbidden" });
    } else if (url.pathname === "/throttled") {
      send(429, { error: "rate limit exceeded" }, { "Retry-After": "2" });
    } else {
      send(404, { error: "not found" });
    }
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve({ server, port: server.address().port })));
}

const { server, port } = await startMock();
const base = `http://127.0.0.1:${port}`;

test.after(() => new Promise((r) => server.close(r)));

// ---------------------------------------------------------------------------
// 1. Health + SSE parsing
// ---------------------------------------------------------------------------

test("health probe round-trip", async () => {
  const client = sdk.createClient({ baseUrl: base, clientName: "ts-harness" });
  const health = await client.health();
  assert.equal(health.status, "ok");
  assert.equal(health.mock, true);
});

test("SSE: 3 frames parsed, seq monotonic, heartbeat typed, terminal ends", async () => {
  const client = sdk.createClient({ baseUrl: base, clientName: "ts-harness" });
  const frames = [];
  for await (const frame of client.streamStatusFetch("task-338")) frames.push(frame);
  assert.equal(frames.length, 3);
  assert.deepEqual(frames.map((f) => f.seq), [1, 2, 3]);
  assert.equal(frames[0].event, "agent:started");
  assert.equal(frames[1].heartbeat.kind, "ping");
  assert.equal(frames[2].event, "agent:done");
});

// ---------------------------------------------------------------------------
// 2. Tool serialization (JSON-RPC envelope + correlation)
// ---------------------------------------------------------------------------

test("invokeTool serializes JSON-RPC tools/call and correlates invocation_id", async () => {
  const client = sdk.createClient({ baseUrl: base, clientName: "ts-harness" });
  const result = await client.invokeTool({
    tool: "repo_read",
    arguments: { path: "docs/" },
    invocation_id: "inv-fixed-1",
  });
  assert.equal(result.status, "ok");
  assert.equal(result.invocation_id, "inv-fixed-1");
  assert.equal(result.result.tool, "repo_read");
  assert.equal(result.result.echo.path, "docs/");
  assert.ok(typeof result.duration_ms === "number");
});

test("dispatchTask posts the task-router aligned envelope", async () => {
  // reuse the mock's /tasks/dispatch? mock lacks it here; assert envelope via
  // a one-shot server that echoes the received body back as the result.
  const echo = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      const received = JSON.parse(body);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        task_id: received.task_id,
        tier: "coding_reasoning",
        route: [{ provider: "anthropic", model: "claude-sonnet-4-5" }],
        accepted: true,
        _received: received,
      }));
    });
  });
  await new Promise((r) => echo.listen(0, "127.0.0.1", r));
  const echoPort = echo.address().port;
  try {
    const client = sdk.createClient({ baseUrl: `http://127.0.0.1:${echoPort}`, clientName: "ts-harness" });
    const out = await client.dispatchTask({
      task_id: "task-338",
      issue: "338",
      objective: "harness",
      touching_files: ["sdk/typescript/src/index.ts"],
    });
    assert.equal(out.accepted, true);
    assert.equal(out.tier, "coding_reasoning");
    assert.equal(out.route[0].provider, "anthropic");
    assert.equal(out._received.touching_files[0], "sdk/typescript/src/index.ts");
  } finally {
    await new Promise((r) => echo.close(r));
  }
});

// ---------------------------------------------------------------------------
// 3. Error translation (honest taxonomy)
// ---------------------------------------------------------------------------

test("JSON-RPC tool error → honest non-retryable envelope", async () => {
  const client = sdk.createClient({ baseUrl: base, clientName: "ts-harness" });
  const result = await client.invokeTool({ tool: "boom", arguments: {}, invocation_id: "inv-boom" });
  assert.equal(result.status, "error");
  assert.equal(result.error.code, "tool_failed");
  assert.equal(result.error.retryable, false);
  assert.match(result.error.message, /unknown tool: boom/);
});

test("429 → SdkRateLimited carrying Retry-After", async () => {
  const client = sdk.createClient({ baseUrl: base, clientName: "ts-harness" });
  await assert.rejects(
    () => client.dispatchTask({ task_id: "t", issue: "1", objective: "x", touching_files: ["a"] }),
    (err) => {
      assert.equal(err.name, "SdkRateLimited");
      assert.equal(err.statusCode, 429);
      assert.equal(err.retryAfterMs, 2000);
      assert.match(err.message, /Retry-After/);
      return true;
    },
  );
});

test("403 → honest forbidden envelope + SdkForbidden taxonomy", async () => {
  const client = sdk.createClient({ baseUrl: base, clientName: "ts-harness" });
  // invokeTool never rejects — it translates every failure into an envelope
  const env = await client.invokeTool({ tool: "forbidden-probe", arguments: {}, invocation_id: "inv-403" });
  assert.equal(env.status, "error");
  assert.equal(env.error.code, "forbidden");
  assert.equal(env.error.retryable, false);
  // the thrown class carries the status code for direct-call consumers
  const f = new sdk.SdkForbidden("403 default-deny RBAC — probe");
  assert.equal(f.statusCode, 403);
  assert.equal(f.name, "SdkForbidden");
});

test("transport failure → retryable envelope (connection refused)", async () => {
  const bad = sdk.createClient({ baseUrl: "http://127.0.0.1:1", clientName: "ts-harness" });
  const env = await bad.invokeTool({ tool: "x", arguments: {}, invocation_id: "inv-refused" });
  assert.equal(env.status, "error");
  assert.equal(env.error.retryable, true);
});

// ---------------------------------------------------------------------------
// 4. Packaging contract (AC2: dual CJS/ESM + declaration maps)
// ---------------------------------------------------------------------------

test("dual build outputs exist and are marked", async () => {
  for (const [entry, type] of [[esmEntry, "module"], [cjsEntry, "commonjs"]]) {
    assert.ok(existsSync(entry), `missing ${entry}`);
    const marker = JSON.parse(existsSync(join(dirname(entry), "package.json"))
      ? await import("node:fs").then((fs) => fs.readFileSync(join(dirname(entry), "package.json"), "utf8"))
      : "{}");
    assert.equal(marker.type, type, `${entry} must be stamped ${type}`);
    assert.ok(existsSync(join(dirname(entry), "index.d.ts")), `missing declarations for ${entry}`);
    assert.ok(existsSync(join(dirname(entry), "index.d.ts.map")), `missing declaration map for ${entry}`);
  }
});

test("CJS build is require()-able", async () => {
  const { createRequire } = await import("node:module");
  const require = createRequire(import.meta.url);
  const cjs = require(cjsEntry);
  assert.equal(typeof cjs.SupremeAIClient, "function");
  assert.equal(typeof cjs.createClient, "function");
  assert.ok(typeof sdk.SdkRateLimited === "function");
});
