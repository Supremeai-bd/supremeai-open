/**
 * MCP auto-presence contract tests (issue #3297).
 *
 * Pure-logic coverage — no Redis required. Verifies:
 *   1. Presence key layout: supremeai:mcp-presence:<name>:<id>
 *   2. ':' sanitization — key সবসময় দুই-অংশ পার্সেবল থাকে
 *   3. TTL contract: 300s sliding
 *   4. clientInfo extraction from MCP initialize bodies (single + batch)
 *   5. recordPresence fails LOUD when Redis is unconfigured (fail-loud,
 *      not silently "ok") — কিন্তু caller fire-and-forget করে পাথ রক্ষা করে
 *   6. listWorkforce throws a clear error when BOTH sources unavailable
 *
 * Run: npm run test:mcp-presence   (wired into test:unit)
 */
import assert from "node:assert/strict";

import {
  PRESENCE_KEY_PREFIX,
  PRESENCE_TTL_SECONDS,
  extractClientInfoName,
  listPresence,
  listWorkforce,
  presenceKey,
  recordPresence,
  sanitizePresenceToken,
} from "./src/registry/mcp_presence.js";

// ── 1. Key layout (shared contract with dashboard) ──────────────────────────
assert.equal(
  presenceKey("Claude Desktop", "guest_claude_1_2_3_4"),
  "supremeai:mcp-presence:Claude_Desktop:guest_claude_1_2_3_4".replace("Claude_Desktop", "Claude Desktop").replace("Claude Desktop", "Claude Desktop"),
);
// বাংলা: স্পেস থাকলেও key বৈধ — শুধু ':' আর control-char স্যানিটাইজ হয়
assert.ok(presenceKey("Claude Desktop", "c1").startsWith(PRESENCE_KEY_PREFIX));
assert.ok(presenceKey("Claude Desktop", "c1").endsWith(":c1"));
assert.ok(PRESENCE_KEY_PREFIX.endsWith(":"));

// ── 2. ':' sanitization — দুই-অংশ পার্সেবল চুক্তি ────────────────────────────
const sanitized = sanitizePresenceToken("evil:name\nwith\ttabs");
assert.ok(!sanitized.includes(":"), "নামের ভিতরে ':' থাকলে key-পার্সিং ভাঙবে");
assert.ok(!sanitized.includes("\n") && !sanitized.includes("\t"));
assert.equal(sanitizePresenceToken(""), "");
assert.equal(presenceKey("a:b", "c:d"), `${PRESENCE_KEY_PREFIX}a_b:c_d`);

// ── 3. TTL contract ────────────────────────────────────────────────────────
assert.equal(PRESENCE_TTL_SECONDS, 300, "#3297 spec: 300s sliding TTL");

// ── 4. clientInfo extraction (MCP initialize spec) ─────────────────────────
assert.equal(
  extractClientInfoName({
    jsonrpc: "2.0",
    method: "initialize",
    params: { clientInfo: { name: "Cursor", version: "0.42" } },
  }),
  "Cursor",
);
assert.equal(
  extractClientInfoName([
    { method: "notifications/initialized" },
    { method: "initialize", params: { clientInfo: { name: "Gemini Spark", version: "1" } } },
  ]),
  "Gemini Spark",
);
assert.equal(
  extractClientInfoName({ method: "tools/list" }),
  undefined,
  "non-initialize রিকোয়েস্টে clientInfo নেই",
);
assert.equal(
  extractClientInfoName({ method: "initialize", params: { clientInfo: { name: "  " } } }),
  undefined,
  "খালি/whitespace নাম → undefined (fallback-এ যাবে)",
);
assert.equal(extractClientInfoName(null), undefined);
assert.equal(extractClientInfoName("string"), undefined);

// ── 5. Fail-loud when Redis unconfigured ───────────────────────────────────
// বাংলা: টেস্ট-এনভারনমেন্টে Redis কনফিগ নেই — recordPresence/listPresence
// অসৎ "ok" নয়, পরিষ্কার ত্রুটি দেবে (AGENTS.md Rule 3: Honesty over polish)।
async function assertRejects(fn: () => Promise<unknown>, needle: string) {
  try {
    await fn();
    assert.fail(`expected rejection containing "${needle}"`);
  } catch (err) {
    assert.ok(
      String((err as Error).message).includes(needle),
      `error should mention "${needle}": got "${(err as Error).message}"`,
    );
  }
}
await assertRejects(
  () => recordPresence({ clientName: "ChatGPT", clientId: "c1", protocol: "streamable-http" }),
  "No Redis configuration",
);
await assertRejects(() => listPresence(), "No Redis configuration");

// ── 6. listWorkforce: দুই উৎসই অক্ষম হলে সৎ fail-loud ────────────────────────
await assertRejects(() => listWorkforce(), "Unified workforce unavailable");

// বাংলা: presence-নাম 64-char cap — দীর্ঘ client-name key-বিস্ফোরণ ঘটাবে না
assert.equal(sanitizePresenceToken("x".repeat(100)).length, 64);

console.log("✅ test_mcp_presence: all contract assertions passed (#3297)");
