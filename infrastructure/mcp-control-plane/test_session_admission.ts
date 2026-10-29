/**
 * Pressure-eviction admission contract tests (#1886).
 *
 * Pure-logic coverage — no network, no clock, no credentials. The live
 * incident (2026-10-28: /mcp 503 activeSessions:100 while /sse stayed open)
 * proved the bounded /mcp table had NO admission path under churn: the
 * reaper only frees slots after the 1 h idle TTL, so a full table refused
 * every fresh initialize indefinitely. pickPressureEvictionSessionId() is
 * the admission decision, extracted pure so the policy is testable offline
 * (house pattern: test_mcp_presence.ts, test_http_retry.ts).
 *
 * Contract under test:
 *   1. Refuse-only semantics preserved: floor <= 0 → never evict.
 *   2. Floor protection: sessions fresher than the floor are never evicted.
 *   3. Oldest-first: among eligible sessions the least-recently-active wins.
 *   4. Determinism: ties resolve to the first occurrence in input order.
 *   5. Clock skew: future-dated activity is "too fresh" → protected.
 *   6. Empty table → null (caller keeps refuse path).
 *   7. Mixed table: exactly the stale minority is eligible; fresher majority
 *      never influences the choice beyond eligibility.
 *
 * Run: npm run test:session-admission   (wired into test:unit + test:tower-ci)
 */
import assert from "node:assert/strict";

import { pickPressureEvictionSessionId, type SessionAdmissionEntry } from "./src/lib/session_admission.js";

const NOW = 1_800_000_000_000;

function entriesOf(...pairs: Array<[string, number]>): SessionAdmissionEntry[] {
  return pairs.map(([sessionId, lastActivityMs]) => ({ sessionId, lastActivityMs }));
}

// ── 1. floor <= 0 → refuse-only (historical behavior preserved verbatim) ───
assert.equal(pickPressureEvictionSessionId(entriesOf(["a", NOW - 3_600_000]), NOW, 0), null, "floor=0 must disable pressure eviction");
assert.equal(pickPressureEvictionSessionId(entriesOf(["a", NOW - 3_600_000]), NOW, -1), null, "negative floor must disable pressure eviction");

// ── 2. Floor protection: fresher-than-floor occupants are never evicted ────
const floor = 60_000;
assert.equal(
  pickPressureEvictionSessionId(entriesOf(["fresh-59s", NOW - 59_000]), NOW, floor),
  null,
  "session idle 59s < 60s floor must be protected",
);
assert.equal(
  pickPressureEvictionSessionId(entriesOf(["just-active", NOW]), NOW, floor),
  null,
  "just-active session must be protected",
);

// ── 3. Oldest-first among eligible sessions ────────────────────────────────
assert.equal(
  pickPressureEvictionSessionId(
    entriesOf(["b-5min", NOW - 5 * 60_000], ["a-30min", NOW - 30 * 60_000], ["c-2min", NOW - 2 * 60_000]),
    NOW,
    floor,
  ),
  "a-30min",
  "the least-recently-active eligible session must be the eviction pick",
);

// ── 4. Determinism: exact tie resolves to first occurrence in input order ──
assert.equal(
  pickPressureEvictionSessionId(entriesOf(["first", NOW - 120_000], ["second", NOW - 120_000]), NOW, floor),
  "first",
  "tie must resolve deterministically to the first eligible entry",
);

// ── 5. Clock skew: future-dated activity is protected ──────────────────────
assert.equal(
  pickPressureEvictionSessionId(entriesOf(["skewed", NOW + 999_999]), NOW, floor),
  null,
  "future-dated lastActivityMs must never be evicted",
);

// ── 6. Empty table → null ──────────────────────────────────────────────────
assert.equal(pickPressureEvictionSessionId([], NOW, floor), null, "empty table must yield null");

// ── 7. Mixed table: only the stale minority is eligible ────────────────────
const mixed = entriesOf(
  ["live-1", NOW - 1_000],
  ["live-2", NOW - 2_000],
  ["stale-70s", NOW - 70_000],
  ["live-3", NOW - 3_000],
  ["older-stale-10min", NOW - 600_000],
);
assert.equal(
  pickPressureEvictionSessionId(mixed, NOW, floor),
  "older-stale-10min",
  "the oldest eligible session wins even when fresher entries surround it",
);

// ── 8. Boundary: idle exactly at the floor IS eligible (>= semantics) ──────
assert.equal(
  pickPressureEvictionSessionId(entriesOf(["exactly-floor", NOW - floor]), NOW, floor),
  "exactly-floor",
  "a session idle exactly the floor must be eligible (>= floor semantics)",
);

// ── 9. All-fresh table → null (caller falls back to refuse-only 503) ───────
const allFresh = entriesOf(["f1", NOW - 1_000], ["f2", NOW - 30_000], ["f3", NOW - 59_000]);
assert.equal(
  pickPressureEvictionSessionId(allFresh, NOW, floor),
  null,
  "when every occupant is fresher than the floor, admission must refuse",
);

console.log("test_session_admission: 9/9 contract groups PASS (#1886 pressure-eviction admission)");
