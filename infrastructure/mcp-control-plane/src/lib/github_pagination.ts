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
