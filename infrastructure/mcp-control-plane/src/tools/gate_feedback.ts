/**
 * N3 (docs/COMPLEXITY_REDUCTION_2026-10-16.md, WO #370) — gate feedback
 * extractors for bridge.work_order.
 *
 * Submitters were blind to gate verdicts: bridge.work_order returned labels +
 * body but never the issue comments, so 4 rejection waves were root-caused by
 * differential forensics instead of one tool call. This module holds the pure
 * extraction core as a standalone unit (landable and testable without
 * touching the bridge.tools.ts intake surface).
 *
 * Shape-tolerance note (fail-honest): the intake's status-comment template is
 * owned by the private-side pipeline and is NOT observable from this lane —
 * so instead of classifying comment shapes (false-classification risk), the
 * extractor surfaces the NEWEST non-empty public comment verbatim, clipped.
 * Fail-open: any malformed input -> null.
 */

/** Collapse whitespace and clip a public comment body (600-char bound). */
export function clipCommentExcerpt(body: unknown, maxChars = 600): string | null {
  if (typeof body !== "string") return null;
  const collapsed = body.replace(/\s+/g, " ").trim();
  if (!collapsed) return null;
  return collapsed.length > maxChars
    ? `${collapsed.slice(0, maxChars)}… [clipped ${collapsed.length - maxChars} chars]`
    : collapsed;
}

export interface GateFeedback {
  at: string;
  excerpt: string;
}

/**
 * Newest-wins extractor: picks the newest comment by created_at regardless of
 * the caller's sort order (desc and asc fetches agree). Ties (missing or
 * equal timestamps) resolve to the FIRST entry — deterministic, and matches
 * the desc-ordered fetch the tool performs.
 */
export function extractGateFeedback(rawComments: unknown): GateFeedback | null {
  if (!Array.isArray(rawComments)) return null;
  let best: GateFeedback | null = null;
  let bestAt = "";
  for (const entry of rawComments) {
    if (!entry || typeof entry !== "object") continue;
    const c = entry as { body?: unknown; created_at?: unknown };
    const excerpt = clipCommentExcerpt(c.body);
    if (!excerpt) continue;
    const at = typeof c.created_at === "string" ? c.created_at : "";
    if (!best || at > bestAt) {
      best = { at, excerpt };
      bestAt = at;
    }
  }
  return best;
}

/** Sanitized gate-feedback payload for the work_order response (additive-optional). */
export interface GateFeedbackField {
  commentCount: number;
  latest: GateFeedback | null;
  fetchFailed?: boolean;
}
