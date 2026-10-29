/**
 * #2195 — Bridge title length clamps (Failure 1 root cause).
 *
 * GitHub began enforcing a ~256-char cap on issue titles (live-proven
 * 2026-10-28 23:55Z: a 938-char summary submitted fine at ~22:50Z, then 422'd
 * deterministically at 23:55Z+ with the same code; a 185-char title passed).
 * Both bridge planes derive titles by interpolating the raw agent-supplied
 * summary:
 *   Step D (issue):  `🌉 Bridge Work Order — ${summary} (${taskId})`
 *   Step E (PR):     `feat(bridge): ${summary} (${taskId})`
 * A 980-char summary therefore yields a ~1050-char title and a deterministic
 * HTTP 422 that strands the already-pushed patch branch.
 *
 * The clamp preserves the ` (${taskId})` TAIL verbatim: #2136's dedup fix
 * (bridge_dedup.ts isWorkOrderForTaskId) treats the title tail `(taskId)` as
 * an AUTHORITATIVE position — a clamp that could eat the suffix would break
 * idempotency matching for every resubmitted round. The summary is truncated
 * with an ellipsis only when the assembled title exceeds the cap; short
 * titles pass through byte-identical.
 *
 * Cap is measured in UTF-16 code units (JS .length), set at 240 — a strict
 * subset of GitHub's ~256-char server-side cap under any unit convention
 * (code units >= unicode scalar chars, so 240 units can never exceed 256
 * chars), leaving headroom for server-side counting differences.
 */

export const BRIDGE_TITLE_CAP = 240;
const ELLIPSIS = "…";

/**
 * Assemble a bridge plane title with a hard length guarantee.
 *
 * buildBridgeTitle(prefix, summary, taskId) ->
 *   `${prefix}${summary} (${taskId})`            (when it fits)
 *   `${prefix}${clipped}${ELLIPSIS} (${taskId})` (when it does not)
 *
 * The ` (${taskId})` suffix is always present and never clipped. Degenerate
 * inputs (empty summary) produce `${prefix} (${taskId})` — the caller's
 * zod validation already floors summary length, this is fail-safe only.
 */
export function buildBridgeTitle(prefix: string, summary: string, taskId: string): string {
  const suffix = ` (${taskId})`;
  const fitted = summary.length > 0 ? summary : "(no summary)";
  const full = `${prefix}${fitted}${suffix}`;
  if (full.length <= BRIDGE_TITLE_CAP) return full;

  const budget = BRIDGE_TITLE_CAP - prefix.length - suffix.length - ELLIPSIS.length;
  const clipped = budget > 0 ? fitted.slice(0, budget) : "";
  const body = clipped.length > 0 ? `${clipped}${ELLIPSIS}` : ELLIPSIS;
  const assembled = `${prefix}${body}${suffix}`;
  // Fail-closed guard: the assembled title must NEVER exceed the cap, and the
  // suffix must always survive. If the caller's prefix/suffix alone blow the
  // cap (misuse), the honest move is to hard-truncate the tail rather than
  // emit a title that would deterministically 422 and strand the branch.
  if (assembled.length <= BRIDGE_TITLE_CAP) return assembled;
  return `${assembled.slice(0, BRIDGE_TITLE_CAP - ELLIPSIS.length)}${ELLIPSIS}`;
}

/** Step D (work-order issue) title, clamped. Prefix mirrors the deployed template. */
export function issueTitleFor(summary: string, taskId: string): string {
  return buildBridgeTitle(`🌉 Bridge Work Order — `, summary, taskId);
}

/** Step E (patch PR) title, clamped. Prefix mirrors the deployed template. */
export function prTitleFor(summary: string, taskId: string): string {
  return buildBridgeTitle(`feat(bridge): `, summary, taskId);
}

/**
 * #2195 — Step-E PR-failure surfacing (Failure 2/3 amplifier).
 *
 * The deployed Step-E ran `if (prRes.ok && prRes.data) {...}` with no else:
 * a failed PR creation (422 head-not-found, validation, caps) was swallowed
 * and the round returned ok:true/bridge:queued with prNumber undefined —
 * branches stranded with zero diagnostics, contra Invariant #514 (zero
 * stranded branches). The intake verifier that saved the r1/r2 diagnosis was
 * manual git forensics; this helper makes the tower return the reason.
 *
 * Pure extraction so the shape mapping is unit-testable offline: GitHub's
 * POST /pulls failure body is `{message, errors?: [{message}]}`; network
 * failures throw before any response exists.
 */
export interface PrFailure {
  status: number; // HTTP status, 0 when the call threw (transport-level)
  message: string; // GitHub's message plus a compact errors[] digest when present
}

export function prFailureFromHttp(
  status: number,
  data: { message?: string; errors?: Array<{ message?: string }> } | undefined
): PrFailure {
  const ghMessage = data?.message || "";
  const errList = Array.isArray(data?.errors) ? data.errors : [];
  const digest = errList
    .map((e) => (e && typeof e.message === "string" ? e.message : ""))
    .filter((m) => m.length > 0)
    .slice(0, 3)
    .join("; ");
  const message = digest ? `${ghMessage} (${digest})` : ghMessage || `HTTP ${status}`;
  return { status, message: message.slice(0, 300) };
}
