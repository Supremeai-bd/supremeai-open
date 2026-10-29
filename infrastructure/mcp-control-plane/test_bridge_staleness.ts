/**
 * #2333 — bridge.submit_patch staleness checkpoint regression battery (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 *
 * Replays the live failure (2026-10-28 23:00Z): #2322 (R61 registration) cut its
 * branch from a pre-#2314 base; its whole-file SCOUT_RADAR_INDEX.md overwrite
 * landed after #2314 (93aa098) and silently evicted the landed R62 row and
 * regressed the pointer (ebe630c). The suite's pointer-pin test stayed GREEN
 * because the pointer regressed together with the row — co-regression is
 * invisible to value-pins. The fix: per-file opt-in baseSha declared at
 * branch-cut time; the Tower re-reads main pre-land and rejects with
 * STALE_BASE_ERROR on any drift (main-advanced / file-deleted).
 */
import {
  evaluateBaseStaleness,
  staleBaseErrorText,
  STALE_BASE_ERROR_PREFIX,
  type MainBlobState,
} from "./src/lib/bridge_staleness.js";

let failures = 0;
function check(name: string, cond: boolean, detail?: string): void {
  if (cond) {
    console.log(`  ✓ ${name}`);
  } else {
    failures += 1;
    console.error(`  ✗ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}
function section(title: string): void {
  console.log(`\n=== ${title} ===`);
}

// The R62 eviction replay shapes: #2314 landed row bytes (what main gained) vs
// #2322's stale pre-#2314 declaration.
const CUT_SHA_2314_BASE = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"; // filer's cut-time blob
const MAIN_ADVANCED_SHA = "f9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0"; // main after #2314 landed

// ─── 1. Skip semantics (backward compatibility) ─────────────────────────────
section("1. No declared base -> skip (legacy filers / brand-new files unchanged)");
const noBase = evaluateBaseStaleness(undefined, { exists: true, sha: MAIN_ADVANCED_SHA });
check("undefined baseSha skips even when main moved", noBase.verdict === "skip");
check("skip carries the no-declared-base note", noBase.verdict === "skip" && noBase.note === "no-declared-base");
const nullBase = evaluateBaseStaleness(null, { exists: false });
check("null baseSha skips too", nullBase.verdict === "skip");
const emptyBase = evaluateBaseStaleness("", { exists: true, sha: MAIN_ADVANCED_SHA });
check("empty-string baseSha skips (falsy = undeclared)", emptyBase.verdict === "skip");

// ─── 2. Fresh path (base still matches main) ────────────────────────────────
section("2. Declared base matches main -> fresh (safe overwrite)");
const fresh = evaluateBaseStaleness(CUT_SHA_2314_BASE, { exists: true, sha: CUT_SHA_2314_BASE });
check("bit-identical blob -> fresh", fresh.verdict === "fresh");
check("fresh carries the base-matches-main note", fresh.verdict === "fresh" && fresh.note === "base-matches-main");

// ─── 3. Stale path A: main advanced (the #2322 witness) ─────────────────────
section("3. Main advanced since the cut -> stale (the R62 eviction replay)");
const advanced = evaluateBaseStaleness(CUT_SHA_2314_BASE, { exists: true, sha: MAIN_ADVANCED_SHA });
check("moved blob -> stale", advanced.verdict === "stale");
check(
  "stale names the main-advanced-since-cut reason",
  advanced.verdict === "stale" && advanced.reason === "main-advanced-since-cut"
);
check(
  "stale carries both shas for the re-read contract",
  advanced.verdict === "stale" &&
    advanced.declaredBaseSha === CUT_SHA_2314_BASE &&
    advanced.currentMainSha === MAIN_ADVANCED_SHA
);

// ─── 4. Stale path B: file deleted on main since the cut ────────────────────
section("4. File deleted on main since the cut -> stale (no silent resurrection)");
const deleted = evaluateBaseStaleness(CUT_SHA_2314_BASE, { exists: false });
check("absent blob -> stale", deleted.verdict === "stale");
check(
  "stale names the file-deleted-on-main-since-cut reason",
  deleted.verdict === "stale" && deleted.reason === "file-deleted-on-main-since-cut"
);
check("deleted-stale carries the declared sha", deleted.verdict === "stale" && deleted.declaredBaseSha === CUT_SHA_2314_BASE);

// ─── 5. Error text contract (machine-readable, re-readable) ─────────────────
section("5. STALE_BASE_ERROR text contract");
const advText = staleBaseErrorText("docs/SCOUT_RADAR_INDEX.md", advanced as Extract<typeof advanced, { verdict: "stale" }>);
check("error carries the STALE_BASE_ERROR prefix", advText.startsWith(STALE_BASE_ERROR_PREFIX));
check("error names the offending path", advText.includes("docs/SCOUT_RADAR_INDEX.md"));
check("error names the declared base sha", advText.includes(CUT_SHA_2314_BASE));
check("error names the current main sha", advText.includes(MAIN_ADVANCED_SHA));
check("error cites the #2333 rationale", advText.includes("#2333"));
check("error instructs the re-read contract", advText.includes("Re-read the file from main"));
check("error does NOT teach bypassing the checkpoint", !advText.includes("omit baseSha"));
const delText = staleBaseErrorText("docs/ledger/x.md", deleted as Extract<typeof deleted, { verdict: "stale" }>);
check("deleted-variant error states absence on main", delText.includes("ABSENT on main"));

// ─── 6. Discriminant shape (exhaustive decision surface) ────────────────────
section("6. Verdict discriminant shape");
const all: Array<ReturnType<typeof evaluateBaseStaleness>> = [noBase, fresh, advanced, deleted];
check("skip verdicts exclude reason fields", noBase.verdict === "skip" && !("reason" in noBase));
check("fresh verdicts exclude reason fields", fresh.verdict === "fresh" && !("reason" in fresh));
check("stale verdicts always carry reason", all.filter((v) => v.verdict === "stale").every((v) => "reason" in v && !!v.declaredBaseSha));
check("verdicts partition into exactly the three actions", new Set(all.map((v) => v.verdict)).size === 3);
const blob: MainBlobState = { exists: true };
check("MainBlobState tolerates missing sha field (defensive)", evaluateBaseStaleness(CUT_SHA_2314_BASE, blob).verdict === "stale");

// ─── Verdict ────────────────────────────────────────────────────────────────
console.log("\n=============================================");
if (failures === 0) {
  console.log("ALL BRIDGE STALENESS TESTS PASSED (#2333)");
} else {
  console.error(`${failures} TEST(S) FAILED (#2333)`);
}
process.exit(failures === 0 ? 0 : 1);
