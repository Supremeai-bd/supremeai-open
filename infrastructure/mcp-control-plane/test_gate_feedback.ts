/**
 * N3 (docs/COMPLEXITY_REDUCTION_2026-10-16.md) — gate feedback test suite.
 *
 * bridge.work_order gains an additive-optional `gateFeedback` field so
 * submitters can read gate verdicts with one tool call instead of the
 * differential-forensics dance that consumed 4 rejection waves.
 *
 * House style: tsx script, hard asserts, exit code = verdict.
 * Scope: pure functions (clipCommentExcerpt, extractGateFeedback) — the
 * HTTP fetch path is fail-open by construction and the RBAC/classification
 * surface of bridge_work_order is unchanged (covered by test_bridge_onboarding).
 */
import assert from "node:assert/strict";
import { clipCommentExcerpt, extractGateFeedback } from "./src/tools/gate_feedback.js";

let checks = 0;
function section(title: string): void {
  console.log(`\n=== ${title} ===`);
}

// ─── 1. clipCommentExcerpt: sanitization contract ───────────────────────────
section("clipCommentExcerpt — sanitization contract");
assert.equal(clipCommentExcerpt(null), null, "non-string (null) → null");
assert.equal(clipCommentExcerpt(42), null, "non-string (number) → null");
assert.equal(clipCommentExcerpt(undefined), null, "non-string (undefined) → null");
assert.equal(clipCommentExcerpt({ body: "x" }), null, "object → null");
assert.equal(clipCommentExcerpt(""), null, "empty string → null");
assert.equal(clipCommentExcerpt("   \n\t  "), null, "whitespace-only → null");
assert.equal(clipCommentExcerpt("hello\n  world!"), "hello world!", "whitespace collapsed to single spaces");
assert.equal(clipCommentExcerpt("a".repeat(600)), "a".repeat(600), "exact-fit (600) → no ellipsis");
const clipped = clipCommentExcerpt("b".repeat(601)) as string;
assert.ok(clipped.startsWith("b".repeat(600)), "over-limit → starts with maxChars content");
assert.ok(clipped.endsWith("[clipped 1 chars]"), "over-limit → suffix carries the clipped count");
assert.ok((clipCommentExcerpt("c".repeat(1000), 100) as string).startsWith("c".repeat(100)), "custom maxChars honored");
checks += 13;
console.log("  ✓ 13 sanitization contracts");

// ─── 2. extractGateFeedback: fail-open zoo ─────────────────────────────────
section("extractGateFeedback — fail-open zoo");
assert.equal(extractGateFeedback(null), null, "null input → null");
assert.equal(extractGateFeedback(undefined), null, "undefined input → null");
assert.equal(extractGateFeedback("nope"), null, "non-array input → null");
assert.equal(extractGateFeedback(123), null, "number input → null");
assert.equal(extractGateFeedback([]), null, "empty array → null");
assert.equal(extractGateFeedback([null, 42, "junk"]), null, "malformed entries only → null");
assert.equal(extractGateFeedback([{ created_at: "2026-01-01T00:00:00Z" }]), null, "entry without body → null");
assert.equal(extractGateFeedback([{ body: "   " }]), null, "entry with whitespace-only body → null");
assert.equal(extractGateFeedback([{ body: null }, { body: 7 }, { body: {} }]), null, "non-string bodies → null");
checks += 9;
console.log("  ✓ 9 fail-open contracts");

// ─── 3. extractGateFeedback: newest-wins semantics ─────────────────────────
section("extractGateFeedback — newest-wins semantics");
const desc = extractGateFeedback([
  { body: "older verdict", created_at: "2026-01-01T00:00:00Z" },
  { body: "newer verdict", created_at: "2026-02-02T00:00:00Z" },
]) as { at: string; excerpt: string };
assert.equal(desc.excerpt, "newer verdict", "desc-ordered input → newest picked");
assert.equal(desc.at, "2026-02-02T00:00:00Z", "timestamp carried");

const asc = extractGateFeedback([
  { body: "newer verdict", created_at: "2026-02-02T00:00:00Z" },
  { body: "older verdict", created_at: "2026-01-01T00:00:00Z" },
]) as { at: string; excerpt: string };
assert.equal(asc.excerpt, "newer verdict", "asc-ordered input → SAME newest picked (order-independent)");
assert.equal(asc.at, "2026-02-02T00:00:00Z", "timestamp identical across orders");

const malformedMixed = extractGateFeedback([
  null,
  { body: "   " },
  { body: "real latest", created_at: "2026-03-03T00:00:00Z" },
  { body: "real older", created_at: "2026-01-01T00:00:00Z" },
  7,
]) as { at: string; excerpt: string };
assert.equal(malformedMixed.excerpt, "real latest", "malformed entries skipped, real newest still wins");

const noTimestamp = extractGateFeedback([{ body: "shape-unknown comment" }]) as { at: string; excerpt: string };
assert.equal(noTimestamp.excerpt, "shape-unknown comment", "missing created_at → still surfaced (at: empty string)");
assert.equal(noTimestamp.at, "", "missing created_at → at is empty string, never undefined");

const longBody = extractGateFeedback([{ body: "x".repeat(900), created_at: "2026-01-01T00:00:00Z" }]) as { excerpt: string };
assert.ok(longBody.excerpt.length <= 600 + "… [clipped N chars]".length + 4, "excerpt clipped to bound + suffix");
checks += 10;
console.log("  ✓ 10 newest-wins contracts");

// ─── 4. Invariants ──────────────────────────────────────────────────────────
section("invariants");
const inv = extractGateFeedback([
  { body: "multi\nline\n\tverdict", created_at: "2026-01-01T00:00:00Z" },
]) as { excerpt: string };
assert.ok(!/\n|\t/.test(inv.excerpt), "excerpt never contains raw newlines/tabs (single-line safe for logs)");
assert.equal(extractGateFeedback([{ body: "a" }, { body: "b" }])!.excerpt, "a", "tie on missing created_at → FIRST entry wins deterministic (matches desc fetch order)");
checks += 2;
console.log("  ✓ 2 invariants");

console.log(`\n=============================================\n✅ ALL GATE FEEDBACK TESTS PASSED (${checks} assertions)`);
process.exit(0);
