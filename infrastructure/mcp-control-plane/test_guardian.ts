/**
 * PR Guardian — unit tests.
 *
 * Covers the merge gate policy: an improvement with zero regressions merges,
 * a regression blocks the merge and routes to fix-or-close-or-escalate, and CI
 * status is evidence rather than the gate.
 *
 * Pure/deterministic: no network, no GitHub token required.
 */

import "dotenv/config";
import { evaluateEvidence, bestCandidate, type EvidenceBundle, type GuardianEvaluation } from "./src/guardian/engine.js";
import { countDiffSignals, buildMetricsFromEvidence } from "./src/guardian/signals.js";
import { classifyChangeTier } from "./src/guardian/policy.js";
import type { CheckRunEvidence, PullRequestEvidence, PullRequestFileEvidence } from "./src/guardian/github-api.js";

let passed = 0;
let failed = 0;

function assert(condition: boolean, label: string, detail = ""): void {
  if (condition) {
    passed += 1;
    console.log(`  ✅ ${label}`);
  } else {
    failed += 1;
    console.error(`  ❌ ${label}${detail ? ` — ${detail}` : ""}`);
  }
}

function assertEqual<T>(actual: T, expected: T, label: string): void {
  assert(actual === expected, label, `expected ${String(expected)}, got ${String(actual)}`);
}

function basePr(overrides: Partial<PullRequestEvidence> = {}): PullRequestEvidence {
  return {
    number: 101,
    title: "test pr",
    body: null,
    author: "tester",
    state: "open",
    draft: false,
    htmlUrl: "https://example.invalid/pr/101",
    headRef: "fix/thing",
    headSha: "headsha",
    baseRef: "main",
    baseSha: "basesha",
    mergeableState: "clean",
    mergeable: true,
    changedFiles: 1,
    additions: 1,
    deletions: 1,
    labels: [],
    ...overrides,
  };
}

function file(patch: string, filename = "backend/app.ts", status = "modified"): PullRequestFileEvidence {
  return { filename, status, additions: 1, deletions: 1, patch };
}

function check(name: string, conclusion: string | null, status = "completed"): CheckRunEvidence {
  return { name, status, conclusion, startedAt: null, completedAt: null, htmlUrl: null };
}

function bundle(files: PullRequestFileEvidence[], overrides: Partial<EvidenceBundle> = {}): EvidenceBundle {
  return {
    pr: basePr({ changedFiles: files.length }),
    files,
    candidateChecks: [],
    baselineChecks: [],
    scopePrefixes: [],
    ...overrides,
  };
}

/** A patch that only removes debug logging — a clean, measurable improvement. */
const CLEANUP_PATCH = [
  "@@ -10,3 +10,1 @@",
  '-  console.log("debug a");',
  '-  console.log("debug b");',
  "+  return result;",
].join("\n");

/** A patch that introduces debug logging — a bounded regression. */
const DEBUG_ADDED_PATCH = ["@@ -10,1 +10,3 @@", "+  console.log(\"debug a\");", "+  console.log(\"debug b\");", "   return result;"].join("\n");

/** A patch that commits a credential — a severe, non-auto-fixable regression. */
const SECRET_PATCH = ["@@ -1,1 +1,2 @@", '+const api_key = "abcdef123456";'].join("\n");

/** A patch that disables a test — a coverage regression the Guardian must not silently accept. */
const DISABLED_TEST_PATCH = ["@@ -1,1 +1,2 @@", "+  test.skip(\"important behaviour\", () => {});"].join("\n");

/** A patch with no trackable signal at all. */
const NEUTRAL_PATCH = ["@@ -1,1 +1,1 @@", "-  const a = 1;", "+  const a = 2;"].join("\n");
console.log("=== PR Guardian — improvement-gated merge policy ===\n");

// ── 1. A clean, measurable improvement merges ────────────────────────────────
console.log("[1] cleanup PR (removes debug artifacts)");
{
  const result = evaluateEvidence(bundle([file(CLEANUP_PATCH)]));
  assertEqual(result.decision.verdict, "MERGE", "verdict is MERGE");
  assert(result.decision.isImprovement, "flagged as an improvement");
  assertEqual(result.score >= 1, true, `score ${result.score} meets the minimum`);
  assertEqual(result.regressedMetrics.length, 0, "zero regressions");
  assertEqual(result.improvedMetrics.includes("debug_artifacts"), true, "improvement metric is debug_artifacts");
}

// ── 2. Bounded regression routes to fix-then-merge ───────────────────────────
console.log("[2] PR that adds debug logging");
{
  const result = evaluateEvidence(bundle([file(DEBUG_ADDED_PATCH)]));
  assertEqual(result.decision.verdict, "FIX_REGRESSION_THEN_MERGE", "verdict is FIX_REGRESSION_THEN_MERGE");
  assert(result.regressedMetrics.includes("debug_artifacts"), "debug_artifacts regressed");
  assertEqual(result.remediation.available, true, "a bounded fix exists for this regression");
  assert(result.remediation.strategies.length > 0, "fix strategy was published");
}

// ── 3. Security regression escalates instead of auto-fixing ──────────────────
console.log("[3] PR that commits a credential");
{
  const result = evaluateEvidence(bundle([file(SECRET_PATCH)]));
  assertEqual(result.decision.verdict, "ESCALATE_TO_ADMIN", "verdict is ESCALATE_TO_ADMIN");
  assertEqual(result.severity, "high", "severity is high");
  assertEqual(result.remediation.available, false, "the Guardian refuses to auto-fix a leaked secret");
  assert(result.remediation.blockers.some((b) => b.startsWith("hardcoded_secrets")), "blocker names the metric");
}

// ── 4. Disabled tests are a coverage regression ──────────────────────────────
console.log("[4] PR that disables a test");
{
  const result = evaluateEvidence(bundle([file(DISABLED_TEST_PATCH)]));
  assertEqual(result.decision.verdict, "ESCALATE_TO_ADMIN", "verdict is ESCALATE_TO_ADMIN");
  assert(result.regressedMetrics.includes("disabled_tests"), "disabled_tests regressed");
}

// ── 5. A neutral PR with no measurable improvement is not merged ─────────────
console.log("[5] PR with no measurable improvement");
{
  const result = evaluateEvidence(bundle([file(NEUTRAL_PATCH)]));
  assertEqual(result.decision.verdict, "CLOSE_PR", "verdict is CLOSE_PR");
  assertEqual(result.decision.isImprovement, false, "not flagged as an improvement");
  assertEqual(result.severity, "none", "no regression either");
}
// ── 6. Merge conflicts block the merge ───────────────────────────────────────
console.log("[6] PR with merge conflicts");
{
  const result = evaluateEvidence(bundle([file(CLEANUP_PATCH)], { pr: basePr({ mergeable: false }) }));
  assertEqual(result.decision.verdict, "CLOSE_PR", "conflicting PR cannot merge");
  assert(result.regressedMetrics.includes("merge_conflicts"), "merge_conflicts metric fired");
}

// ── 7. Deleting tests is a severe regression ─────────────────────────────────
console.log("[7] PR that deletes a test file");
{
  const result = evaluateEvidence(bundle([file("", "tests/unit/app.test.ts", "removed")]));
  assertEqual(result.decision.verdict, "ESCALATE_TO_ADMIN", "verdict is ESCALATE_TO_ADMIN");
  assert(result.regressedMetrics.includes("removed_test_files"), "removed_test_files metric fired");
}

// ── 8. Out-of-scope files are a bounded regression ───────────────────────────
console.log("[8] PR touching files outside its declared scope");
{
  const result = evaluateEvidence(
    bundle([file(CLEANUP_PATCH, "frontend/extra.ts")], { scopePrefixes: ["backend/"] }),
  );
  assert(result.regressedMetrics.includes("out_of_scope_files"), "out_of_scope_files metric fired");
  assertEqual(result.decision.verdict, "FIX_REGRESSION_THEN_MERGE", "verdict is FIX_REGRESSION_THEN_MERGE");
}
// ── 9. CI status is evidence, NOT the merge gate ─────────────────────────────
console.log("[9] CI failing at the same rate as main, with a real improvement");
{
  const candidate = [check("build", "failure"), check("test", "success")];
  const baseline = [check("build", "failure"), check("test", "success")];
  const result = evaluateEvidence(
    bundle([file(CLEANUP_PATCH)], { candidateChecks: candidate, baselineChecks: baseline }),
  );
  assertEqual(result.ci.candidate.failed, 1, "CI evidence records the failing check");
  assertEqual(result.decision.verdict, "MERGE", "verdict is still MERGE (CI is not the gate)");
}

console.log("[9b] CI regressions are still caught");
{
  const candidate = [check("build", "failure"), check("build2", "failure"), check("test", "success")];
  const baseline = [check("build", "failure"), check("test", "success")];
  const result = evaluateEvidence(
    bundle([file(CLEANUP_PATCH)], { candidateChecks: candidate, baselineChecks: baseline }),
  );
  assert(result.regressedMetrics.includes("failing_checks"), "failing_checks regressed");
  assertEqual(result.decision.verdict, "ESCALATE_TO_ADMIN", "a real CI regression escalates");
}

// ── 10. Blast-radius tiers ───────────────────────────────────────────────────
console.log("[10] change-tier classification");
{
  assertEqual(classifyChangeTier(["docs/readme.md"]).tier, "TIER1", "docs are Tier 1");
  assertEqual(classifyChangeTier(["backend/policy/auth/session.ts"]).tier, "TIER3", "auth changes are Tier 3");
  assertEqual(classifyChangeTier(["backend/payments/stripe.ts"]).tier, "TIER3", "payments are Tier 3");
  assertEqual(classifyChangeTier(["src/thing.custom"]).tier, "TIER2", "unrecognised files default to Tier 2");
}
// ── 11. Competing PRs: the best improvement wins ─────────────────────────────
console.log("[11] best-candidate ranking");
{
  const good = evaluateEvidence(bundle([file(CLEANUP_PATCH)], { pr: basePr({ number: 1 }) }));
  const bad = evaluateEvidence(bundle([file(DEBUG_ADDED_PATCH)], { pr: basePr({ number: 2 }) }));
  assertEqual(bestCandidate([bad, good])?.pr.number, 1, "higher score wins");
  assertEqual(bestCandidate([]), undefined, "empty candidate list yields undefined");
}

// ── 12. The evidence report is human-auditable ───────────────────────────────
console.log("[12] report rendering");
{
  const { renderGuardianReport } = await import("./src/tools/guardian.tools.js");
  const evaluation: GuardianEvaluation = evaluateEvidence(bundle([file(CLEANUP_PATCH)]));
  const report = renderGuardianReport(evaluation);
  assertEqual(report.verdict, "MERGE", "report verdict matches the decision");
  assert(report.markdown.includes("PR Guardian"), "report has a Guardian heading");
  assert(report.markdown.includes("debug_artifacts"), "report lists the metric");
  assert(report.markdown.includes("CI evidence"), "report records CI as evidence");
}
// ── 13. Signal counting is deterministic ─────────────────────────────────────
console.log("[13] diff signal counting");
{
  const mixed = ["@@ -1,2 +1,2 @@", "-// TODO: fix later", '+console.log("x");'].join("\n");
  const counts = countDiffSignals([file(mixed)]);
  assertEqual(counts.debug_artifacts.added, 1, "added debug artifact counted");
  assertEqual(counts.debug_artifacts.removed, 0, "no removed debug artifact");
  assertEqual(counts.code_markers.removed, 1, "removed TODO counted");
  assertEqual(counts.code_markers.added, 0, "no added TODO");
}

// ── 14. Honest limitations when baseline evidence is unavailable ─────────────
console.log("[14] skipped metrics are disclosed");
{
  const built = buildMetricsFromEvidence(bundle([file(CLEANUP_PATCH)]));
  assert(built.skipped.length > 0, "missing baseline evidence is disclosed");
  assertEqual(
    built.metrics.some((m) => m.name === "failing_checks"),
    false,
    "no check-based metric invented without a baseline",
  );
}

console.log(`\n=== Guardian tests complete: ${passed} passed, ${failed} failed ===`);
if (failed > 0) process.exit(1);