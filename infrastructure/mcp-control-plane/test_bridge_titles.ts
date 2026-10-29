/**
 * #2195 — Bridge title clamp + PR-failure surfacing test battery (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 *
 * Live motivation (2026-10-28 23:55Z outage, WO #2195):
 *  - Failure 1: GitHub began enforcing a ~256-char issue-title cap; the
 *    unclamped `🌉 Bridge Work Order — ${summary} (${taskId})` template turned
 *    a 980-char summary into a deterministic 422 that stranded the pushed
 *    branch. Same exposure on the Step-E PR title.
 *  - Failure 2/3: Step-E's `if (prRes.ok && prRes.data)` had no else — PR
 *    creation failures were swallowed (ok:true, prNumber undefined), stranding
 *    branches with zero diagnostics, contra Invariant #514.
 *
 * The clamp MUST preserve the ` (${taskId})` tail verbatim: #2136's
 * isWorkOrderForTaskId treats the title tail `(taskId)` as an authoritative
 * position, so eating the suffix would break idempotency matching.
 */
import {
  buildBridgeTitle,
  issueTitleFor,
  prTitleFor,
  prFailureFromHttp,
  BRIDGE_TITLE_CAP,
} from "./src/lib/bridge_titles.js";

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

const TASK = "bridge-20261028-radar-index-freshness-r2";

// ─── 1. Pass-through (byte-identical when short) ─────────────────────────────
section("1. Short titles pass through byte-identical");
const short = "guard(bridge): fix the thing";
check(
  "short PR title unchanged",
  prTitleFor(short, TASK) === `feat(bridge): ${short} (${TASK})`,
  prTitleFor(short, TASK)
);
check(
  "short issue title unchanged",
  issueTitleFor(short, TASK) === `🌉 Bridge Work Order — ${short} (${TASK})`,
  issueTitleFor(short, TASK)
);

// ─── 2. Clamp (Failure 1 regression) ─────────────────────────────────────────
section("2. Long summaries clamp to the cap, suffix preserved");
const long980 = "x".repeat(980);
const prClamped = prTitleFor(long980, TASK);
check("clamped PR title within cap", prClamped.length <= BRIDGE_TITLE_CAP, `len=${prClamped.length}`);
check("clamped issue title within cap", issueTitleFor(long980, TASK).length <= BRIDGE_TITLE_CAP);
check("taskId tail preserved verbatim", prClamped.endsWith(` (${TASK})`));
check("ellipsis marker present", prClamped.includes("…"));
check("prefix preserved", prClamped.startsWith("feat(bridge): "));

// Tail preservation is a #2136-dedup contract, not a nicety.
section("3. Tail survival is the #2136 dedup contract");
const tailRe = /\(([^()]+)\)$/;
const m = prClamped.match(tailRe);
check("title tail parses as (taskId)", m !== null && m![1] === TASK, prClamped.slice(-70));

// ─── 3. Boundary arithmetic ──────────────────────────────────────────────────
section("4. Boundary arithmetic");
const exact = prTitleFor("y".repeat(BRIDGE_TITLE_CAP), TASK);
check("at-cap-length summary clamps (prefix+suffix counted)", exact.length <= BRIDGE_TITLE_CAP, `len=${exact.length}`);
check("at-cap summary still keeps tail", exact.endsWith(` (${TASK})`));
const fit = prTitleFor("y".repeat(50), TASK);
check("small summary not clipped (no ellipsis)", !fit.includes("…"));
check("cap constant is under GitHub's ~256", BRIDGE_TITLE_CAP <= 250, `cap=${BRIDGE_TITLE_CAP}`);

// Degenerate: huge prefix misuse still fails closed under the cap.
section("5. Fail-closed on caller misuse");
const hugePrefix = "p".repeat(500);
const degenerate = buildBridgeTitle(hugePrefix, "s", TASK);
check("degenerate title still <= cap", degenerate.length <= BRIDGE_TITLE_CAP, `len=${degenerate.length}`);

// Empty summary floor (zod floors upstream; fail-safe here).
section("6. Empty summary fail-safe");
const emptyCase = issueTitleFor("", TASK);
check("empty summary does not produce dangling space", !emptyCase.includes("  "), emptyCase);
check("empty summary keeps tail", emptyCase.endsWith(` (${TASK})`));

// ─── 7. prFailureFromHttp (Failure 2/3 surfacing) ────────────────────────────
section("7. prFailureFromHttp shape mapping");
const f1 = prFailureFromHttp(422, {
  message: "Validation Failed",
  errors: [{ message: "head repository does not exist" }, { message: "invalid code" }],
});
check("status carried", f1.status === 422);
check("gh message carried", f1.message.startsWith("Validation Failed"), f1.message);
check("errors[] digested", f1.message.includes("head repository does not exist"), f1.message);
check("digest capped at 3 entries", f1.message.split(";").length <= 4);

const f2 = prFailureFromHttp(500, { message: "Server Error" });
check("no errors[] -> message only", f2.message === "Server Error");

const f3 = prFailureFromHttp(502, undefined);
check("no body -> honest HTTP fallback", f3.message === "HTTP 502", f3.message);

const f4 = prFailureFromHttp(422, { message: "m", errors: [{}, { message: "" }, { message: "real one" }] });
check("empty error entries filtered", f4.message.includes("real one") && !f4.message.includes(";;"), f4.message);

const long500 = "e".repeat(600);
const f5 = prFailureFromHttp(422, { message: long500 });
check("message capped at 300 units", f5.message.length <= 300, `len=${f5.message.length}`);

// ─── verdict ─────────────────────────────────────────────────────────────────
console.log(`\n${failures === 0 ? "SELF-TEST OK" : `SELF-TEST FAILED: ${failures}`}`);
if (failures > 0) process.exit(1);
