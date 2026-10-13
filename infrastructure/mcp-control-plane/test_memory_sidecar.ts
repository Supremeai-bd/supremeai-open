/**
 * #2612 — Memory sidecar backend-dir resolution + honest diagnostics.
 *
 * বাংলা মন্তব্য: লাইভ Render-এ ৮১ বার start attempt ব্যর্থ হয়েছিল —
 * `spawn uv ENOENT` যদিও uv ইমেজে ছিল; আসল কারণ: SUPREMEAI_BACKEND_DIR
 * unset → defaultBackendDir() 5-up → /backend (অস্তিত্বহীন) → Node spawn-এর
 * cwd অস্তিত্বহীন হলে ENOENT কমান্ডের ঘাড়ে চাপানো হয়। ফিক্স:
 *   (1) resolveBackendDir — env-পাথে sidecar-ইন্ট্রি না থাকলে layout-default
 *       fallback; (2) doStart — fallback-ও না থাকলে সৎ এরর, spawn চেষ্টাই নয়।
 * Hermetic: existsCheck constructor-ইনজেকশন — কোনো আসল spawn/fs-mock নয়।
 */

import assert from "node:assert/strict";
import * as os from "node:os";
import * as path from "node:path";
import { mkdtempSync, rmSync } from "node:fs";
import { MemorySubAdapter, resolveBackendDir, sidecarEntryExists } from "./src/adapters/memory/index.js";

// ── helpers: fallback matrix (existsFn injected — hermetic) ──────────────
const repoDefault = resolveBackendDir(undefined).backendDir; // layout default = repo backend/
assert.equal(resolveBackendDir(undefined, () => false).backendDir, repoDefault);
assert.equal(resolveBackendDir("", () => false).backendDir, repoDefault);

// env পাথ বৈধ → সেটাই থাকে, fallback নয়
assert.deepEqual(resolveBackendDir("/some/env/dir", () => true), {
  backendDir: "/some/env/dir",
  fellBack: false,
});

// env পাথে ইন্ট্রি নেই + default-এ আছে → fallback, fellBack=true (#2612-ক্লাস মিসকনফিগ স্বয়ং-সংশোধন)
assert.deepEqual(resolveBackendDir("/backend", (d) => d === repoDefault), {
  backendDir: repoDefault,
  fellBack: true,
});

// env পাথ ভাঙা + default-ও নেই → env রেখে দেওয়া (caller সৎ এরর দেখাবে)
assert.deepEqual(resolveBackendDir("/backend", () => false), {
  backendDir: "/backend",
  fellBack: false,
});

// ── sidecarEntryExists: real filesystem ────────────────────────────────────
assert.equal(sidecarEntryExists(repoDefault), true); // repo checkout has backend/memory/mcp_server.py
const tmp = mkdtempSync(path.join(os.tmpdir(), "2612-sidecar-"));
assert.equal(sidecarEntryExists(tmp), false);
assert.equal(sidecarEntryExists("/backend"), false); // লাইভ প্রমাণের ভুল পাথ

// ── doStart honest-error path: existsCheck injection → কোনো আসল spawn নয় ──
// সব পাথ "missing" — ঠিক লাইভের মতো অবস্থা, কিন্তু এররটা এখন সৎ হতে হবে
const adapter = new MemorySubAdapter(() => false);
process.env["SUPREMEAI_BACKEND_DIR"] = "/backend"; // লাইভে যে পাথ হতো
try {
  await adapter.start();
  assert.equal(adapter.isReady, false);
  assert.ok(adapter.lastError !== null);
  assert.ok(
    adapter.lastError!.includes("memory sidecar backend not found"),
    `honest error expected, got: ${adapter.lastError}`,
  );
  assert.ok(adapter.lastError!.includes("/backend"), "এররে ভাঙা পাথের নাম থাকতে হবে");
  assert.ok(adapter.lastError!.includes("SUPREMEAI_BACKEND_DIR"), "এররে env-নাম + প্রস্তাবিত ফিক্স থাকতে হবে");
  assert.ok(!adapter.lastError!.includes("spawn uv ENOENT"), "ভুয়া ENOENT আর নয়");
} finally {
  delete process.env["SUPREMEAI_BACKEND_DIR"];
  rmSync(tmp, { recursive: true, force: true });
}

console.log("✅ test_memory_sidecar: #2612 resolution + honest diagnostics — all assertions passed");
