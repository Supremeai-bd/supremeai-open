/**
 * PR Guardian — Evidence → Metric extraction.
 *
 * Turns raw GitHub evidence (patch hunks, file list, check runs) into objective
 * metric samples that the improvement engine can compare. Everything here is
 * deterministic: no LLM, no heuristic that cannot be reproduced from the diff.
 */

import type { MetricSample } from "./improvement.js";
import type {
  CheckRunEvidence,
  PullRequestEvidence,
  PullRequestFileEvidence,
} from "./github-api.js";

export interface SignalRule {
  name: string;
  /** Matched against a single added or removed source line. */
  pattern: RegExp;
  /** Larger = more damaging when it regresses. */
  criticality: number;
  /** Larger = more influence on the improvement score. */
  weight: number;
}

/**
 * Code-quality signals. Each metric is compared as
 * `added occurrences` (candidate) vs `removed occurrences` (baseline), which is
 * exactly what the PR does to the repository — regardless of CI status.
 */
export const SIGNAL_RULES: SignalRule[] = [
  {
    name: "debug_artifacts",
    pattern: /(console\.(log|debug)\s*\(|(^|\s)debugger;?\s*$|(^|\s)print\s*\(|pdb\.set_trace\s*\(|binding\.pry)/,
    criticality: 1,
    weight: 1,
  },
  {
    name: "code_markers",
    pattern: /(\bTODO\b|\bFIXME\b|\bHACK\b|\bXXX\b)/,
    criticality: 1,
    weight: 1,
  },
  {
    name: "hardcoded_secrets",
    pattern: /(password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)\s*[:=]\s*["'][^"']{6,}["']/i,
    criticality: 5,
    weight: 2,
  },
  {
    name: "localhost_refs",
    pattern: /(localhost:\d+|\b127\.0\.0\.1\b)/,
    criticality: 1.5,
    weight: 1,
  },
  {
    name: "swallowed_errors",
    pattern: /(except\s*:\s*$|except\s+Exception\s*:\s*pass|catch\s*\([^)]*\)\s*\{\s*\})/,
    criticality: 2,
    weight: 1.5,
  },
  {
    name: "disabled_tests",
    pattern: /(@Ignore\b|@pytest\.mark\.skip|(?:it|test|describe)\.(?:skip|todo)\s*\(|xit\s*\(|xdescribe\s*\()/,
    criticality: 3,
    weight: 2,
  },
  {
    name: "type_suppressions",
    pattern: /(@ts-ignore|@ts-nocheck|#\s*type:\s*ignore|#\s*noqa\b|eslint-disable)/,
    criticality: 2,
    weight: 1.5,
  },
];

const TEST_FILE_PATTERN = /(^|\/)(tests?|spec|__tests__)\/|\.(test|spec)\./i;

export interface SignalCounts {
  [signal: string]: { added: number; removed: number };
}

export interface CiSummary {
  total: number;
  passed: number;
  failed: number;
  pending: number;
  /** Average wall-clock duration (seconds) of completed check runs. */
  avgDurationSec: number | null;
}

export interface MetricBuildResult {
  metrics: MetricSample[];
  signals: SignalCounts;
  ci: { candidate: CiSummary; baseline: CiSummary | null };
  /** Signals/metrics deliberately not evaluated, with the reason. */
  skipped: string[];
}

/** Count every signal rule across the diff hunks of all changed files. */
export function countDiffSignals(files: PullRequestFileEvidence[]): SignalCounts {
  const counts: SignalCounts = {};
  for (const rule of SIGNAL_RULES) counts[rule.name] = { added: 0, removed: 0 };

  for (const file of files) {
    const patch = file.patch;
    if (!patch) continue;
    for (const line of patch.split("\n")) {
      // Skip hunk headers and file markers — only real content lines count.
      if (line.startsWith("+++") || line.startsWith("---")) continue;
      const isAdded = line.startsWith("+");
      const isRemoved = line.startsWith("-");
      if (!isAdded && !isRemoved) continue;
      const body = line.slice(1);
      for (const rule of SIGNAL_RULES) {
        if (rule.pattern.test(body)) {
          if (isAdded) counts[rule.name].added += 1;
          else counts[rule.name].removed += 1;
        }
      }
    }
  }
  return counts;
}

function durationSeconds(run: CheckRunEvidence): number | null {
  if (!run.startedAt || !run.completedAt) return null;
  const start = Date.parse(run.startedAt);
  const end = Date.parse(run.completedAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  return Math.round(((end - start) / 1000) * 10) / 10;
}

export function summarizeChecks(runs: CheckRunEvidence[]): CiSummary {
  let passed = 0;
  let failed = 0;
  let pending = 0;
  const durations: number[] = [];

  for (const run of runs) {
    if (run.status !== "completed") {
      pending += 1;
      continue;
    }
    const conclusion = (run.conclusion ?? "").toLowerCase();
    if (conclusion === "success" || conclusion === "neutral" || conclusion === "skipped") passed += 1;
    else failed += 1;

    const seconds = durationSeconds(run);
    if (seconds !== null) durations.push(seconds);
  }

  const avg = durations.length
    ? Math.round((durations.reduce((a, b) => a + b, 0) / durations.length) * 10) / 10
    : null;

  return { total: runs.length, passed, failed, pending, avgDurationSec: avg };
}

/** Test/spec files deleted by the PR — an unconditional coverage regression. */
export function countRemovedTestFiles(files: PullRequestFileEvidence[]): number {
  return files.filter((f) => f.status === "removed" && TEST_FILE_PATTERN.test(f.filename)).length;
}

export function countOutOfScopeFiles(files: PullRequestFileEvidence[], scopePrefixes: string[]): number {
  if (scopePrefixes.length === 0) return 0;
  return files.filter((f) => !scopePrefixes.some((p) => f.filename.startsWith(p))).length;
}

export interface EvidenceBundle {
  pr: PullRequestEvidence;
  files: PullRequestFileEvidence[];
  candidateChecks: CheckRunEvidence[];
  baselineChecks: CheckRunEvidence[];
  /** Optional declared scope; empty array means "scope not asserted". */
  scopePrefixes?: string[];
}

/**
 * Build the full metric set. Candidate values describe the PR head; baseline
 * values describe what already exists (removed lines / base branch checks).
 */
export function buildMetricsFromEvidence(bundle: EvidenceBundle): MetricBuildResult {
  const { pr, files, candidateChecks, baselineChecks } = bundle;
  const scopePrefixes = bundle.scopePrefixes ?? [];
  const signals = countDiffSignals(files);
  const skipped: string[] = [];
  const metrics: MetricSample[] = [];

  for (const rule of SIGNAL_RULES) {
    const counts = signals[rule.name];
    // A signal the diff neither adds nor removes carries no information.
    if (counts.added === 0 && counts.removed === 0) continue;
    metrics.push({
      name: rule.name,
      candidate: counts.added,
      baseline: counts.removed,
      direction: "lower_is_better",
      criticality: rule.criticality,
      weight: rule.weight,
    });
  }

  const removedTests = countRemovedTestFiles(files);
  if (removedTests > 0) {
    metrics.push({
      name: "removed_test_files",
      candidate: removedTests,
      baseline: 0,
      direction: "lower_is_better",
      criticality: 4,
      weight: 2,
    });
  }

  const outOfScope = countOutOfScopeFiles(files, scopePrefixes);
  if (scopePrefixes.length > 0 && outOfScope > 0) {
    metrics.push({
      name: "out_of_scope_files",
      candidate: outOfScope,
      baseline: 0,
      direction: "lower_is_better",
      criticality: 2,
      weight: 1,
    });
  }

  // Merge conflicts are a hard structural regression: the branch no longer
  // integrates cleanly with its base.
  if (pr.mergeable === false) {
    metrics.push({
      name: "merge_conflicts",
      candidate: 1,
      baseline: 0,
      direction: "lower_is_better",
      criticality: 5,
      weight: 3,
    });
  }

  const candidateCi = summarizeChecks(candidateChecks);
  const baselineCi = baselineChecks.length > 0 ? summarizeChecks(baselineChecks) : null;

  if (baselineCi) {
    if (candidateCi.failed > 0 || baselineCi.failed > 0) {
      metrics.push({
        name: "failing_checks",
        candidate: candidateCi.failed,
        baseline: baselineCi.failed,
        direction: "lower_is_better",
        criticality: 3,
        weight: 1.5,
      });
    }
    if (candidateCi.passed > 0 || baselineCi.passed > 0) {
      metrics.push({
        name: "passing_checks",
        candidate: candidateCi.passed,
        baseline: baselineCi.passed,
        direction: "higher_is_better",
        criticality: 1,
        weight: 1.5,
      });
    }
    if (candidateCi.avgDurationSec !== null && baselineCi.avgDurationSec !== null) {
      metrics.push({
        name: "check_duration_seconds",
        candidate: candidateCi.avgDurationSec,
        baseline: baselineCi.avgDurationSec,
        direction: "lower_is_better",
        tolerancePct: 20,
        criticality: 1,
        weight: 1,
      });
    }
  } else {
    skipped.push("check_based_metrics: no baseline check runs available for the base commit");
  }

  return { metrics, signals, ci: { candidate: candidateCi, baseline: baselineCi }, skipped };
}