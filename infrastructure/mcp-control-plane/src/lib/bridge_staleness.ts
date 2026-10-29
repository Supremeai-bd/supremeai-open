/**
 * #2333 — bridge.submit_patch staleness checkpoint: pre-land base verification.
 *
 * Pure, offline helpers (no network, no env) so the regression battery
 * (test_bridge_staleness.ts) can replay the live failure deterministically —
 * same discipline as bridge_dedup.ts (#2136/#2227).
 *
 * Failure being fixed (live witness 2026-10-28 23:00Z, issue #2333):
 * `bridge_submit_patch` accepts full file contents (`mode: full_file`) and lands
 * them atomically with NO comparison against the current state of main for the
 * touched paths. A filer whose branch goes stale between branch-cut and land
 * overwrites the registry/code blind — whatever main gained in that window on
 * those paths is silently reverted. Witness: #2322 (R61 registration) cut its
 * branch before #2314 landed the R62 row + pointer advance (93aa098); #2322's
 * whole-file index overwrite landed after (ebe630c) and silently evicted the
 * landed R62 row and regressed the pointer. Four same-day landings (R59 ghost
 * red, #2295 dead-import red, #2302 comment-invariant red, the R62 eviction)
 * that no landing-path check caught (push-CI dark, #2111).
 *
 * Contract (pure decision, wiring in bridge.tools.ts Step C):
 * - The filer MAY declare `baseSha` per file: the blob sha of the file as read
 *   from main at branch-cut time (public blob id — zero-credential unchanged).
 * - No declared baseSha -> SKIP (backward compatible: legacy filers and
 *   brand-new files have nothing to declare; no behavior change for them).
 * - Declared baseSha + main blob sha EQUALS it -> FRESH (file untouched on
 *   main since the cut; full_file overwrite cannot regress anything).
 * - Declared baseSha + main blob sha DIFFERS -> STALE (main advanced since the
 *   cut; the overwrite would silently revert main's increment).
 * - Declared baseSha + file ABSENT on main -> STALE (file deleted on main
 *   since the cut; the overwrite would resurrect a deleted file).
 *
 * The rejection is fail-closed with a structured, re-readable error:
 * `STALE_BASE_ERROR` names the path, the declared sha, and the current sha so
 * the filer re-reads, re-applies, and resubmits — the same re-read contract as
 * STALE_TEMPLATE_ERROR.
 */

/** The file's current state on main, as observed by the caller (GET /contents). */
export type MainBlobState = { exists: boolean; sha?: string };

/**
 * Staleness verdict for one file:
 * - `skip`   — no baseSha declared (legacy filers / brand-new files): no check.
 * - `fresh`  — declared base still matches main: safe to overwrite.
 * - `stale`  — main moved under the filer: landing would silently regress it.
 */
export type StalenessVerdict =
  | { verdict: "skip"; note: "no-declared-base" }
  | { verdict: "fresh"; note: "base-matches-main" }
  | { verdict: "stale"; reason: "main-advanced-since-cut"; declaredBaseSha: string; currentMainSha: string }
  | { verdict: "stale"; reason: "file-deleted-on-main-since-cut"; declaredBaseSha: string };

export function evaluateBaseStaleness(
  declaredBaseSha: string | undefined | null,
  mainBlob: MainBlobState
): StalenessVerdict {
  // No declared base: legacy filers and new files skip the check entirely —
  // the checkpoint is opt-in so the zero-credential contract and every
  // existing caller keep working unchanged.
  if (!declaredBaseSha) return { verdict: "skip", note: "no-declared-base" };
  // Declared a base but main no longer has the file: it was deleted since the
  // cut — a full_file (re)creation would silently resurrect it.
  if (!mainBlob.exists) {
    return { verdict: "stale", reason: "file-deleted-on-main-since-cut", declaredBaseSha };
  }
  // Main has the file: fresh only when its blob is bit-identical to what the
  // filer cut against.
  const current = mainBlob.sha ?? "";
  if (current === declaredBaseSha) return { verdict: "fresh", note: "base-matches-main" };
  return {
    verdict: "stale",
    reason: "main-advanced-since-cut",
    declaredBaseSha,
    currentMainSha: current,
  };
}

/**
 * Machine-readable rejection prefix (mirrors STALE_TEMPLATE_ERROR). The full
 * error text names the path, both shas, and the re-read contract, so a filer
 * can recover without human help.
 */
export const STALE_BASE_ERROR_PREFIX = "STALE_BASE_ERROR";

export function staleBaseErrorText(path: string, v: Extract<StalenessVerdict, { verdict: "stale" }>): string {
  const current =
    v.reason === "main-advanced-since-cut"
      ? `current main blob ${v.currentMainSha}`
      : "file is ABSENT on main (deleted since your branch cut)";
  return (
    `${STALE_BASE_ERROR_PREFIX}: '${path}' is stale — you declared base ${v.declaredBaseSha} ` +
    `(${v.reason.replace(/-/g, " ")}), but ${current}. Landing this full_file submission would ` +
    `silently revert main's increment (#2333). Re-read the file from main, re-apply your change, ` +
    `and resubmit with the fresh baseSha.`
  );
}
