/**
 * #1359 — Memory knowledge-graph persistence across restarts (P0 acceptance).
 *
 * বাংলা মন্তব্য: P0 #1359 — মেমরি সাইডকারের নলেজ গ্রাফ আগে শুধু প্রসেস-গ্লোবাল
 * ছিল; প্রতিটি রিস্টার্টে graph_nodes আবার ০ হয়ে যেত (AIQ-057/062/098)।
 * এই টেস্ট P0-এর ৩-স্তর ভেরিফিকেশন কনট্র্যাক্টের Smoke স্তর সরাসরি পিন করে:
 *   সেশন A: entity + relation + episode লেখা → প্রসেস বন্ধ
 *   সেশন B: নতুন প্রসেস → সব ফিরে পাওয়া যায়, graph_nodes > 0
 *   সেশন C: wipe_memory-র পরে নতুন বুট → গ্রাফ সত্যিই খালি (GDPR, পুনরুত্থান নেই)
 * সাথে: TTL প্রুনিং (ট্রান্সিয়েন্ট task/topic নোড মারা যায়, durable থাকে),
 * fail-open (ভাঙা স্টোর পাথেও সাইডকার বেঁচে থাকে), এবং লেগাসি in-memory আচরণ।
 *
 * Hermetic: সব ডেটা tmpdir-এ (MEMORY_GRAPH_DB_PATH) — রিপো ওয়ার্কিং ট্রি
 * কখনো পলিউট হয় না। python3 না থাকলে সৎ SKIP (sidecar নিজেই Python-only,
 * লুপের honest-gh স্কিপ-উইথ-এভিডেন্স প্যাটার্ন)।
 */

import assert from "node:assert/strict";
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const sidecarDir = path.resolve(process.cwd(), "sidecars", "memory");
const serverScript = path.join(sidecarDir, "mcp_server.py");

const pyCheck = spawnSync("python3", ["--version"], { encoding: "utf8" });
if (pyCheck.error || pyCheck.status !== 0) {
  console.log("SKIP: python3 not found — memory sidecar restart smoke needs the Python runtime");
  process.exit(0);
}
assert.equal(fs.existsSync(serverScript), true, `sidecar entry missing: ${serverScript}`);

type JsonRpcResponse = {
  id: number;
  result?: { content?: Array<{ type: string; text: string }>; isError?: boolean };
  error?: { code: number; message: string };
};

function startServer(dbPath: string, extraEnv: Record<string, string> = {}): ChildProcess {
  return spawn("python3", [serverScript], {
    cwd: sidecarDir,
    env: { ...process.env, MEMORY_GRAPH_DB_PATH: dbPath, ...extraEnv },
    stdio: ["pipe", "pipe", "pipe"],
  });
}

async function rpc(proc: ChildProcess, id: number, method: string, params: unknown = {}): Promise<JsonRpcResponse> {
  const line = JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n";
  await new Promise<void>((resolve, reject) => {
    if (!proc.stdin) return reject(new Error("stdin closed"));
    proc.stdin.write(line, (err) => (err ? reject(err) : resolve()));
  });
  const raw = await new Promise<string>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`timeout waiting for response id=${id} (${method})`)), 15000);
    proc.stdout!.once("data", (chunk: Buffer) => {
      clearTimeout(timer);
      resolve(chunk.toString());
    });
  });
  const res = JSON.parse(raw.trim()) as JsonRpcResponse;
  assert.ok(!res.error, `rpc ${method} failed: ${JSON.stringify(res.error)}`);
  return res;
}

function resultJson(res: JsonRpcResponse): any {
  assert.ok(res.result, "missing result envelope");
  assert.ok(!res.result!.isError, `tool reported isError: ${res.result!.content?.[0]?.text}`);
  const text = res.result!.content?.[0]?.text ?? "";
  return JSON.parse(text);
}

async function close(proc: ChildProcess): Promise<void> {
  await new Promise<void>((resolve) => {
    if (proc.stdin && proc.stdin.writable) proc.stdin.end();
    proc.once("exit", () => resolve());
    setTimeout(() => resolve(), 3000); // never hang the suite on a stuck child
  });
}

const tmp = mkdtemp();
function mkdtemp(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), "1359-graph-"));
}
try {
  // ── Session A: write entity + relation + episode, then die ──────────────
  const db = path.join(tmp, "graph.db");
  const a = startServer(db);
  const created = resultJson(await rpc(a, 1, "tools/call", {
    name: "create_entities",
    arguments: { entities: [{ name: "user:alice", entityType: "person", observations: ["likes chai"] }] },
  }));
  assert.equal(created.count, 1, "entity creation count");
  const related = resultJson(await rpc(a, 2, "tools/call", {
    name: "create_relations",
    arguments: { relations: [{ from: "user:alice", to: "user:bob", relationType: "knows" }] },
  }));
  assert.equal(related.count, 1, "relation creation count");
  const task = resultJson(await rpc(a, 3, "tools/call", {
    name: "record_task",
    arguments: { task_id: "t-restart", tenant_id: "tenant_test", description: "deployed postgres_indexes", result: "ok" },
  }));
  assert.ok(task.graph_nodes_written >= 1, "record_task writes graph nodes");
  await close(a);

  // ── Session B: RESTART → everything must come back (P0 acceptance) ──────
  const b = startServer(db);
  const graphB = resultJson(await rpc(b, 1, "tools/call", { name: "read_graph", arguments: {} }));
  const names = graphB.entities.map((e: any) => e.name);
  assert.ok(names.includes("user:alice"), `entity survives restart, got: ${JSON.stringify(names)}`);
  assert.ok(
    graphB.relations.some((r: any) => r.from === "user:alice" && r.relationType === "knows" && r.to === "user:bob"),
    "relation survives restart",
  );
  assert.ok(names.some((n: string) => n.endsWith(":task:t-restart")), "task entity survives restart");
  const statsB = resultJson(await rpc(b, 2, "tools/call", { name: "get_session_stats", arguments: {} }));
  assert.ok(statsB.graph_nodes > 0, `graph_nodes must be nonzero after restart (acceptance), got ${statsB.graph_nodes}`);
  const exported = resultJson(await rpc(b, 3, "tools/call", { name: "export_memory", arguments: {} }));
  assert.ok(exported.graph.entities.some((e: any) => e.name === "user:alice"), "export_memory returns durable entity");
  assert.ok(Array.isArray(exported.episodes) && exported.episodes.length >= 0, "export carries episodes lane");
  const wiped = resultJson(await rpc(b, 4, "tools/call", { name: "wipe_memory", arguments: {} }));
  assert.equal(wiped.status, "wiped", "wipe acknowledges");
  await close(b);

  // ── Session C: post-wipe boot → graph must stay empty (no resurrection) ─
  const c = startServer(db);
  const graphC = resultJson(await rpc(c, 1, "tools/call", { name: "read_graph", arguments: {} }));
  assert.equal(graphC.entities.length, 0, "wiped graph stays empty across restart");
  assert.equal(graphC.relations.length, 0, "wiped relations stay empty across restart");
  const statsC = resultJson(await rpc(c, 2, "tools/call", { name: "get_session_stats", arguments: {} }));
  assert.equal(statsC.graph_nodes, 0, "post-wipe graph_nodes is 0");
  await close(c);

  // ── TTL: transient (task/topic) nodes age out, durable nodes survive ────
  const ttlDb = path.join(tmp, "ttl.db");
  const t = startServer(ttlDb, { MEMORY_GRAPH_TTL_MS: "400" });
  resultJson(await rpc(t, 1, "tools/call", {
    name: "create_entities",
    arguments: { entities: [{ name: "durable:fact", entityType: "preference", observations: ["permanent"] }] },
  }));
  resultJson(await rpc(t, 2, "tools/call", {
    name: "record_task",
    arguments: { task_id: "t-ttl", tenant_id: "tenant_test", description: "discussed qdrant_scaling", result: "ok" },
  }));
  await new Promise((r) => setTimeout(r, 600)); // past the 400ms TTL
  const ttlStats = resultJson(await rpc(t, 3, "tools/call", { name: "get_session_stats", arguments: {} }));
  assert.equal(ttlStats.graph_nodes, 1, "only the durable node survives TTL");
  const ttlGraph = resultJson(await rpc(t, 4, "tools/call", { name: "read_graph", arguments: {} }));
  assert.deepEqual(ttlGraph.entities.map((e: any) => e.name), ["durable:fact"], "durable node survives TTL");
  await close(t);

  // ── Fail-open: broken store path must NOT kill the sidecar ──────────────
  const brokenDb = path.join(tmp, "no-such-dir", "sub", "x.db");
  fs.writeFileSync(path.join(tmp, "not-a-dir"), "occupied"); // force makedirs failure
  const broken = startServer(path.join(tmp, "not-a-dir", "inner.db"));
  const bGraph = resultJson(await rpc(broken, 1, "tools/call", {
    name: "create_entities",
    arguments: { entities: [{ name: "mem-only", entityType: "concept", observations: [] }] },
  }));
  assert.equal(bGraph.count, 1, "fail-open: entity still created in memory");
  const bRead = resultJson(await rpc(broken, 2, "tools/call", { name: "read_graph", arguments: {} }));
  assert.equal(bRead.entities.length, 1, "fail-open: in-memory graph serves reads");
  await close(broken);

  console.log("✅ test_memory_graph_persistence: #1359 restart + wipe + TTL + fail-open — all assertions passed");
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
