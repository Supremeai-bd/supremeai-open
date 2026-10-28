/**
 * #2136 — bridge.submit_patch ingress idempotency: exact-taskId duplicate authority.
 *
 * Pure, offline helpers (no network, no env) so the regression battery
 * (test_bridge_dedup.ts) can replay the live false positive deterministically.
 *
 * Failure being fixed (live evidence 2026-10-28, #2136 probes P1–P3): the Step-0
 * idempotency check searched `is:issue is:open <taskId> in:title` with the taskId
 * unquoted. GitHub issue search ANDs hyphen-split tokens, so a NOVEL taskId whose
 * slug shares vocabulary with an unrelated open work order resolved to that WO and
 * returned `bridge:idempotent-noop` — silently blocking the legitimate rescue
 * round. Probe P2: novel `bridge-20261028-radar-index-freshness-r2` resolved to WO
 * #2094, whose title contains bridge/20261028/radar/index/freshness/r2 as separate
 * tokens (P3, with a non-overlapping slug, created normally — evidence-separated).
 *
 * A quoted-phrase query alone is still not sufficient: open issues that merely
 * QUOTE a taskId in prose surface as hits too (the #2136 report itself quotes the
 * probe taskIds; probe B reproduced this live — total=1 -> #2136). Precision
 * therefore requires verifying the hit in an AUTHORITATIVE position that only a
 * work order for exactly this taskId can have. Both positions are emitted
 * verbatim by the Step-D work-order writer in bridge.tools.ts:
 *   - title tail:  `(${taskId})`          — `🌉 Bridge Work Order — <summary> (${taskId})`
 *   - body field:  `### Task ID\n<taskId>` — first line after the heading, exact match
 */

/**
 * True when `title`/`body` identify a bridge work order FOR exactly `taskId`.
 *
 * - Title: the parenthesized tail `(${taskId})` is format-anchored (the Step-D
 *   writer appends it; GitHub 422s over-long titles instead of truncating, so a
 *   successfully created WO always carries the full tail).
 * - Body: the `### Task ID` field value must EQUAL the taskId — prose quotations
 *   of a taskId elsewhere in the body do not count.
 */
export function isWorkOrderForTaskId(
  title: string,
  body: string | undefined | null,
  taskId: string
): boolean {
  if (typeof title === "string" && title.includes(`(${taskId})`)) return true;
  const b = typeof body === "string" ? body : "";
  const m = /###\s*Task\s*ID[^\S\n]*\n+([^\n]*)/.exec(b);
  return !!m && m[1].trim() === taskId;
}

/**
 * Step-0 idempotency search query: quoted-phrase (exact token sequence, immune
 * to the hyphen-split token-AND behavior), full-text over title+body (the body
 * `### Task ID` field is the authoritative key even if a future title format
 * changes), scoped to open issues. Callers must still verify hits with
 * isWorkOrderForTaskId — phrase search narrows, the authority check decides.
 */
export function taskIdSearchQuery(repo: string, taskId: string): string {
  return `repo:${repo}+is:issue+is:open+%22${encodeURIComponent(taskId)}%22`;
}
