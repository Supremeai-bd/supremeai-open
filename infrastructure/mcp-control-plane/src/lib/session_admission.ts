/**
 * Pressure-eviction admission policy for the bounded /mcp session table
 * (session-saturation incident 2026-10-28, finding #1886).
 *
 * Defect class: the bounded session table (#109) only frees slots through
 * the idle reaper (`reapIdleHttpSessions`, default 1 h idle TTL). Under
 * sustained short-lived client churn — the zero-credential cron agent fleet
 * reconnecting every dispatch, plus tokenless AI crawlers — more than
 * `MCP_MAX_HTTP_SESSIONS` distinct sessions initialize per hour, so the
 * table saturates into a STEADY-STATE lockout: every fresh `initialize`
 * is refused with 503 while stale-but-idle (< 1 h) occupants hold their
 * slots. Live evidence: 01:16-01:27Z 2026-10-28, five consecutive 503
 * `activeSessions:100` handshakes while the /sse door stayed open.
 *
 * Policy: when the table is full, admit a fresh initialize by evicting the
 * SINGLE least-recently-active session — but only if that session has been
 * idle for at least the admission idle floor. A victim receives the exact
 * structured recovery contract the table already defines for redeploys and
 * spin-downs (404 / -32001, `session_not_found`, `recoverable`,
 * `action:"send-initialize"`), so no new client-visible failure mode is
 * introduced. When every occupant is fresher than the floor, the caller
 * falls back to the historical refuse-only behavior.
 *
 * Pure logic, no I/O, no clock reads — mirrors the house test pattern
 * (test_mcp_presence.ts, test_http_retry.ts): decisions are computed from
 * injected inputs so the admission path is testable offline for the first
 * time. `idleFloorMs <= 0` disables pressure eviction entirely (operators
 * who want the historical refuse-only semantics keep it verbatim).
 */

/** Minimal shape the admission decision needs from a session-table entry. */
export interface SessionAdmissionEntry {
  sessionId: string;
  /** Sliding-expiry signal shared with the reaper (#621 Phase 3). */
  lastActivityMs: number;
}

/**
 * Pick the session to evict when the table is full, or `null` to refuse.
 *
 * Contract:
 * - `idleFloorMs <= 0` → always `null` (pressure eviction disabled).
 * - A session is eligible iff `lastActivityMs <= nowMs - idleFloorMs`
 *   (i.e. idle for at least the floor). Fresher sessions are protected.
 * - Among eligible sessions the OLDEST `lastActivityMs` wins; ties resolve
 *   to the FIRST occurrence in input order, so feeding entries in Map
 *   iteration order (insertion order) makes the decision deterministic.
 * - Future-dated `lastActivityMs` (clock skew) is "too fresh" → protected.
 * - Empty input → `null`.
 */
export function pickPressureEvictionSessionId(
  entries: readonly SessionAdmissionEntry[],
  nowMs: number,
  idleFloorMs: number,
): string | null {
  if (idleFloorMs <= 0 || entries.length === 0) return null;
  const eligibleBefore = nowMs - idleFloorMs;
  let oldest: SessionAdmissionEntry | null = null;
  for (const entry of entries) {
    if (entry.lastActivityMs > eligibleBefore) continue;
    if (oldest === null || entry.lastActivityMs < oldest.lastActivityMs) {
      oldest = entry;
    }
  }
  return oldest ? oldest.sessionId : null;
}
