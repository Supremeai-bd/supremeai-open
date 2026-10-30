/**
 * Resolve the effective page size for the GitHub list tools.
 *
 * #2311 / R62: the list-tool schemas exposed `limit` only, while GitHub-
 * REST-conventional callers send `per_page` — zod strips unknown keys, so
 * the per_page value was silently discarded and the call degraded to the
 * default 5-row window with zero truncation signal (probe discriminator:
 * per_page=1 still returned 5 rows — the argument was discarded, not
 * clamped). Precedence: per_page ?? limit ?? fallback, clamped to GitHub's
 * documented 1..100 per_page envelope; junk input falls back rather than
 * throwing (page size is a window preference, never a hard failure).
 */
export function resolvePerPage(perPage: unknown, limit: unknown, fallback = 5): number {
  const raw = perPage ?? limit;
  if (raw === undefined || raw === null || raw === "") return fallback;
  const n = Number(raw);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(Math.max(Math.trunc(n), 1), 100);
}

/**
 * #3368 / R81 — single-PR addressability + window re-sorting for the PR
 * read plane. Root cause it prevents: github.list_prs exposed only
 * (state, per_page, limit) over a creation-desc window, so "what is the
 * state of PR N?" was unanswerable for any PR outside the newest ~100
 * creation ranks (audit re-verification class #2547/#2567 fell back to
 * the 403-budget anon REST). GitHub-REST already guarantees both
 * capabilities server-side — the adapter merely surfaces them:
 *   - GET /pulls/{number} answers single-PR state (state/merged/
 *     merged_at/closed_at) at any creation rank;
 *   - sort=created|updated|long-running + direction=asc|desc re-sorts
 *     the window (updated-desc reaches recently-touched old PRs).
 * Pure helpers here (no fetch) so the offline battery can pin the URL
 * contract; the adapter wires them into listPullRequests.
 */
export function pullsEndpoint(baseUrl: string, pullNumber?: number | null): string {
  if (pullNumber !== undefined && pullNumber !== null) {
    const n = Number(pullNumber);
    if (Number.isFinite(n) && n >= 1) return `${baseUrl}/pulls/${Math.trunc(n)}`;
    // junk pull_number falls through to the list plane (a window
    // preference is never a hard failure — same honesty rule as
    // resolvePerPage's junk fallback)
  }
  return `${baseUrl}/pulls`;
}

export function pullsQuery(
  state: string,
  perPage: number,
  sort?: string,
  direction?: string,
): string {
  const params = new URLSearchParams({ state, per_page: String(perPage) });
  if (sort) params.set("sort", sort);
  if (direction) params.set("direction", direction);
  return params.toString();
}
