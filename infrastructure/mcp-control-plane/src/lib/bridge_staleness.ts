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
 *
 * #3487 upgrade (2026-10-30, fail-closed CAS gate — RFC 9110 If-Match
 * pattern): the opt-in checkpoint above left the destructive class open — a
 * full_file payload computed against a stale base WITHOUT declaring baseSha
 * sailed through unchecked (witness: #3404's landing silently wiped
 * co-landed pick-plane guards; the same-day restoration trail #3439/#3451,
 * #3465, #3438, #3409 burned 4 PRs + 1 open WO in ~6 hours). The gate below
 * (`evaluateFullFileGate`) subsumes the opt-in checkpoint:
 * - full_file on a path that EXISTS on main with NO declared baseSha
 *   -> reject `STALE_BASE_MISSING` (the write carries no precondition).
 * - main blob unreadable (non-404 API failure) -> reject
 *   `STALE_BASE_UNVERIFIED` (fail-closed: the PUT itself needs the same API,
 *   so a GET-fails/PUT-works partial failure is exactly the unguarded window).
 * - declared base drifted -> reject `STALE_BASE_ERROR` (unchanged).
 * - brand-new path (absent on main) with no declared baseSha -> allow
 *   (`new-file-no-base`): the new-file lane stays open, zero behavior change;
 *   a declared baseSha on an absent path still rejects via the resurrection
 *   guard (unchanged).
 * The unified_diff lane is untouched (already fail-closed per #539).
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

/**
 * #3487 — the fail-closed CAS gate for EVERY full_file landing (RFC 9110
 * If-Match / compare-and-swap pattern: a write carries its precondition; the
 * server rejects a stale or precondition-less write instead of silently
 * overwriting). Subsumes the #2333 opt-in checkpoint, which stays exported
 * and unchanged for its existing callers and regression battery.
 */

export const STALE_BASE_MISSING_PREFIX = "STALE_BASE_MISSING";
export const STALE_BASE_UNVERIFIED_PREFIX = "STALE_BASE_UNVERIFIED";

export function staleBaseMissingErrorText(path: string): string {
  return (
    `${STALE_BASE_MISSING_PREFIX}: '${path}' exists on main but the payload declares no ` +
    `baseSha — a full_file overwrite without a base precondition is the stale-base ` +
    `silent-overwrite class (#3487; the #3404 clobber family). Re-read the file from main, ` +
    `declare files[].baseSha = its live blob sha (40-hex, e.g. git rev-parse main:<path>), ` +
    `and resubmit. Brand-new files must omit baseSha instead.`
  );
}

export function staleBaseUnverifiedErrorText(path: string, mainReadStatus: number): string {
  return (
    `${STALE_BASE_UNVERIFIED_PREFIX}: '${path}' could not be staleness-verified before ` +
    `landing — main blob read returned HTTP ${mainReadStatus} (#3487 fail-closed: the write ` +
    `itself needs the same API, so landing unverified is exactly the unguarded window). ` +
    `Retry the submission; if main stays unreadable the bridge stays closed — never silent.`
  );
}

/**
 * Decision of the fail-closed gate for one full_file ingress. Pure and offline
 * so the regression battery replays every rejection deterministically.
 *
 * - `mainBlob === undefined` (main read failed with a non-404 status) ->
 *   reject STALE_BASE_UNVERIFIED.
 * - path exists on main + no declared baseSha -> reject STALE_BASE_MISSING.
 * - declared baseSha -> delegate to the #2333 checkpoint (fresh -> allow,
 *   stale -> reject STALE_BASE_ERROR, which also keeps the resurrection
 *   guard for a declared base on an absent path).
 * - brand-new path + no declared baseSha -> allow `new-file-no-base`.
 */
export type FullFileGateVerdict =
  | { verdict: "reject"; error: string }
  | { verdict: "allow"; disclosure: "checked-fresh" | "new-file-no-base" };

export function evaluateFullFileGate(
  path: string,
  declaredBaseSha: string | undefined | null,
  mainBlob: MainBlobState | undefined,
  mainReadStatus: number
): FullFileGateVerdict {
  if (!mainBlob) {
    return { verdict: "reject", error: staleBaseUnverifiedErrorText(path, mainReadStatus) };
  }
  if (mainBlob.exists && !declaredBaseSha) {
    return { verdict: "reject", error: staleBaseMissingErrorText(path) };
  }
  if (declaredBaseSha) {
    const staleness = evaluateBaseStaleness(declaredBaseSha, mainBlob);
    if (staleness.verdict === "stale") {
      return { verdict: "reject", error: staleBaseErrorText(path, staleness) };
    }
    return { verdict: "allow", disclosure: "checked-fresh" };
  }
  return { verdict: "allow", disclosure: "new-file-no-base" };
}
