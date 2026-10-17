/**
 * AI delegation contract tests (issue #643 — zero-credential control plane).
 *
 * বাংলা মন্তব্য: এই ফাইলটি আগে Gemini adapter-এর key-pool আচরণ পরীক্ষা করত।
 * #643 অনুযায়ী control plane থেকে সরাসরি LLM provider key pool সরানো হয়েছে —
 * ফাইলের নাম ও npm script (test:gemini-adapter) অপরিবর্তিত রাখা হয়েছে, কিন্তু
 * চুক্তিটি এখন উল্টো: tower-এ কোনো provider key থাকবে না, প্রতিটি AI পৃষ্ঠ
 * সৎভাবে delegation জানাবে, এবং কোনো পাবলিক টুল সরাসরি inference করবে না।
 *
 * Run: npm run test:gemini-adapter   (wired into test:unit)
 */
import assert from "node:assert/strict";

import { listProviders, testProvider, getOrInitPool, AI_DELEGATION_NOTICE } from "./src/adapters/ai/index.js";
import { analyzeWithAI, listConfiguredAnalysisProviders, ANALYSIS_DELEGATION_NOTICE } from "./src/adapters/ai/analyze.js";
import { AIKeyPool, KEY_POOL_RETIRED_NOTICE } from "./src/adapters/ai/key-pool.js";

// ── 1. Provider listing is permanently empty (no keys in control plane) ────
const providers = listProviders() as Array<{ provider: string; keyCount: number }>;
assert.ok(Array.isArray(providers), "listProviders returns an array");
assert.equal(providers.length, 0, "control plane must hold ZERO direct LLM provider pools (#643 AC)");

// ── 2. Key pool is a retired tombstone: no storage, honest failures ────────
const pool = new AIKeyPool(["ignored-fake-key-1", "ignored-fake-key-2"]); // deliberately NOT secret-shaped (bridge scan families)
assert.equal(pool.length, 0, "AIKeyPool must not retain any keys (constructor args ignored)");
let nextKeyErr: unknown;
try { pool.getNextKey(); } catch (e) { nextKeyErr = e; }
assert.ok(nextKeyErr instanceof Error && nextKeyErr.message === KEY_POOL_RETIRED_NOTICE,
  "getNextKey fails honestly with the retirement notice");
let execErr: unknown;
try { await pool.execute(async () => "used-a-key", () => false); } catch (e) { execErr = e; }
assert.ok(execErr instanceof Error && execErr.message === KEY_POOL_RETIRED_NOTICE,
  "execute must never run an operation with a key");

// ── 3. getOrInitPool back-compat: always null ───────────────────────────────
assert.equal(getOrInitPool("gemini"), null, "no pool is ever initialized for any provider");

// ── 4. testProvider reports honest delegation, never calls a network ───────
const test = await testProvider("gemini");
assert.equal(test.ok, false, "provider test cannot pass — no keys exist");
assert.equal(test.delegated, true, "delegation flag is explicit (no silent zero-key mode)");
assert.match(test.error, /#643/, "error carries the governing issue marker");

// ── 5. analyzeWithAI delegates without any provider call ───────────────────
const analysis = await analyzeWithAI("review", "some content", "auto");
assert.equal(analysis.provider, "none");
assert.equal(analysis.attempts, 0, "zero attempts — no provider call happened");
assert.equal(analysis.usedFallback, false);
assert.match(analysis.content, /delegated/, "analysis content states the delegation contract");

// ── 6. Configured analysis provider list is empty ──────────────────────────
assert.deepEqual(listConfiguredAnalysisProviders(), [], "no analysis providers are configured in the tower");

// ── 7. env.ai namespace is gone from the env schema ────────────────────────
const { env } = await import("./src/lib/env.js");
assert.equal((env as Record<string, unknown>).ai, undefined, "env.ai key-pool namespace must be removed (#643 AC: no master keys required)");

// ── 8. Delegation notices are stable strings (machine-readable contracts) ──
assert.match(AI_DELEGATION_NOTICE, /#643/);
assert.match(ANALYSIS_DELEGATION_NOTICE, /#643/);

console.log("ALL AI-DELEGATION CONTRACT TESTS PASSED (#643) — 8/8 sections: zero keys, honest delegation");
