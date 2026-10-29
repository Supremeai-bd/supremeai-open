/**
 * #2344 — intake-verdict read-side fallback regression battery (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 *
 * Replays the live cohort (2026-10-28 ~23:3xZ): 7 anonymous-bridge WOs across
 * 5 cycles all showed latestVerdict=null + verdictHistory=[] in fresh
 * bridge_read_feedback probes — 5 with stale bridge:queued labels despite
 * byte-verified landings, 2 correctly landed-labeled yet still verdict-null.
 * The feedbackTool contract promises "machine-readable intake verdicts
 * (APPLIED/REJECTED + reason)" the plane never produces for exactly the WOs
 * the bridge creates. Option A: derive the landed-class verdict read-side
 * (bridge:landed + closed -> APPLIED_LABEL_DERIVED, verdictSource=
 * "label-fallback", raw null preserved as intakeVerdict).
 */
import {
  applyLabelFallback,
  LABEL_DERIVED_VERDICT,
  LABEL_DERIVED_REASON,
  type IntakeVerdictLike,
} from "./src/lib/bridge_verdicts.js";

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

// A real intake-bot verdict shape (what the plane writes when it DOES fire).
const BOT_VERDICT: IntakeVerdictLike = {
  verdict: "APPLIED",
  task: "bridge-20261028-dedup-exact-key-r1",
  reason: "landed via PR #2149",
  repo: "Supremeai-bd/supremeai-open",
  pr: "#2149",
  at: "2026-10-28T19:04:11Z",
};

// ─── 1. Pass-through: plane-served WOs unchanged ────────────────────────────
section("1. Raw verdict present -> pass through, source intake-bot");
const served = applyLabelFallback("closed", ["bridge:landed"], BOT_VERDICT);
check("latestVerdict is the bot verdict verbatim", served.latestVerdict === BOT_VERDICT);
check("intakeVerdict mirrors the bot verdict", served.intakeVerdict === BOT_VERDICT);
check("verdictSource = intake-bot", served.verdictSource === "intake-bot");
const servedOpen = applyLabelFallback("open", ["bridge:queued"], BOT_VERDICT);
check("bot verdict passes through even on open WOs", servedOpen.verdictSource === "intake-bot" && servedOpen.latestVerdict === BOT_VERDICT);

// ─── 2. The live cohort: landed + closed + verdict-null ─────────────────────
section("2. Landed + closed + no record -> APPLIED_LABEL_DERIVED (the #2344 cohort)");
const cohort = applyLabelFallback("closed", ["bridge:landed"], null);
check("latestVerdict derived", cohort.latestVerdict !== null && cohort.latestVerdict.verdict === LABEL_DERIVED_VERDICT);
check("derived verdict carries the #2344 reason", cohort.latestVerdict?.reason === LABEL_DERIVED_REASON);
check("raw absence preserved: intakeVerdict = null", cohort.intakeVerdict === null);
check("verdictSource = label-fallback", cohort.verdictSource === "label-fallback");
check("derived fields are null (task/repo/pr/at — nothing invented)", cohort.latestVerdict?.task === null && cohort.latestVerdict?.repo === null && cohort.latestVerdict?.pr === null && cohort.latestVerdict?.at === null);

// ─── 3. Landed but still open (label lag) -> no derivation ──────────────────
section("3. bridge:landed but state open -> no derivation (stale-label honesty)");
const landedOpen = applyLabelFallback("open", ["bridge:landed"], null);
check("open state blocks derivation", landedOpen.verdictSource === null);
check("latestVerdict stays null", landedOpen.latestVerdict === null);
check("intakeVerdict stays null", landedOpen.intakeVerdict === null);

// ─── 4. Closed but queued-labeled (the 5-WO sub-class) ──────────────────────
section("4. Closed + bridge:queued (stale label) -> no derivation from wrong label");
const queuedClosed = applyLabelFallback("closed", ["bridge:queued"], null);
check("queued label never derives APPLIED", queuedClosed.verdictSource === null && queuedClosed.latestVerdict === null);

// ─── 5. bridge:rejected without record stays null (false-rejection hygiene) ─
section("5. bridge:rejected + closed + no record -> null (no #2275-class laundering)");
const rejected = applyLabelFallback("closed", ["bridge:rejected"], null);
check("rejected class NOT derived", rejected.verdictSource === null && rejected.latestVerdict === null);
check("rejected class intakeVerdict stays null", rejected.intakeVerdict === null);

// ─── 6. Empty/odd label planes ──────────────────────────────────────────────
section("6. Tolerant label inputs");
const noLabels = applyLabelFallback("closed", [], null);
check("empty labels -> no derivation", noLabels.verdictSource === null);
const mixed = applyLabelFallback("closed", ["platform-guardian", "bridge:landed", "sentry"], null);
check("landed among other labels derives", mixed.verdictSource === "label-fallback" && mixed.latestVerdict?.verdict === LABEL_DERIVED_VERDICT);
const similar = applyLabelFallback("closed", ["bridge:landed-v2"], null);
check("label match is exact (no prefix bleed)", similar.verdictSource === null);

// ─── 7. Contract shape (machine-readability guarantee) ──────────────────────
section("7. Response contract shape");
check("derived verdict always carries a reason string", LABEL_DERIVED_REASON.length > 20);
check("APPLIED_LABEL_DERIVED is APPLIED-prefixed (contract string compatible)", LABEL_DERIVED_VERDICT.startsWith("APPLIED"));
check("all three sources are discriminable", new Set([served.verdictSource, cohort.verdictSource, landedOpen.verdictSource]).size === 3);

// ─── Verdict ────────────────────────────────────────────────────────────────
console.log("\n=============================================");
if (failures === 0) {
  console.log("ALL BRIDGE VERDICT TESTS PASSED (#2344)");
} else {
  console.error(`${failures} TEST(S) FAILED (#2344)`);
}
process.exit(failures === 0 ? 0 : 1);
