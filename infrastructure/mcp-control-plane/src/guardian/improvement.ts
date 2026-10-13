/**
 * PR Guardian — Pure Improvement / Regression Evaluation Engine
 *
 * Intent: a PR is merged only when it is a *measurable improvement* with *zero
 * regressions* — independently of whether CI passed. CI status is recorded as
 * evidence but is NOT the merge gate.
 *
 * This module is intentionally side-effect free (no network, no filesystem) so
 * that the decision logic is deterministic, unit-testable, and auditable.
 */

export type QualityDirection = "higher_is_better" | "lower_is_better";

/** A regression / improvement signal extracted from real PR evidence. */
export interface MetricSample {
  name: string;
  /** Value observed on the PR head branch. */
  candidate: number;
  /** Value observed on the base branch (main) at the PR merge-base. */
  baseline: number;
  /** Relative size of a change considered noise. Defaults to 0. */
  tolerancePct?: number;
  /** Weight used for the weighted improvement score. Defaults to 1. */
  weight?: number;
  /**
   * How damaging a regression in this metric is (1 = cosmetic, 5 = severe).
   * Controls regression severity classification, independently of `weight`.
   */
  criticality?: number;
  /** Whether a rise in the metric is good (default: usefulness is user-defined). */
  direction: QualityDirection;
}

export interface MetricOutcome extends MetricSample {
  /** Signed relative change in percent: candidate vs baseline. */
  deltaPct: number;
  /** Effective tolerance used. */
  tolerancePct: number;
  /** Effective criticality used. */
  criticality: number;
  /** True when the change is beyond tolerance in the undesirable direction. */
  regressed: boolean;
  /** True when the change is beyond tolerance in the desirable direction. */
  improved: boolean;
}

export interface SourceDelta {
  filesChanged: number;
  additions: number;
  deletions: number;
  /** Files touched that are outside the claimed scope of the change. */
  outOfScopeFiles?: string[];
}

export type RegressionSeverity = "none" | "low" | "medium" | "high";

export interface RegressionReport {
  metrics: MetricOutcome[];
  regressedMetrics: MetricOutcome[];
  improvedMetrics: MetricOutcome[];
  severity: RegressionSeverity;
  hasRegressions: boolean;
}

export type GuardianVerdict =
  | "MERGE"
  | "FIX_REGRESSION_THEN_MERGE"
  | "CLOSE_PR"
  | "ESCALATE_TO_ADMIN";

export interface ImprovementPolicy {
  /** Minimum weighted improvement score required to accept the PR. */
  minImprovementScore: number;
  /** Reward for genuinely improved metrics. */
  improveWeight: number;
  /** Penalty multiplier for regressed metrics. */
  regressWeight: number;
  /** Severity at or above which the Guardian refuses to auto-fix and escalates. */
  escalateSeverityAtOrAbove: RegressionSeverity;
}

export const DEFAULT_IMPROVEMENT_POLICY: ImprovementPolicy = {
  minImprovementScore: 1,
  improveWeight: 1,
  regressWeight: 2,
  escalateSeverityAtOrAbove: "high",
};

const SEVERITY_RANK: Record<RegressionSeverity, number> = {
  none: 0,
  low: 1,
  medium: 2,
  high: 3,
};

function relativeDeltaPct(candidate: number, baseline: number): number {
  if (!Number.isFinite(candidate) || !Number.isFinite(baseline)) return 0;
  if (baseline === 0) {
    if (candidate === 0) return 0;
    return candidate > 0 ? 100 : -100;
  }
  return ((candidate - baseline) / Math.abs(baseline)) * 100;
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

/**
 * Compare every metric against its tolerance and classify it as
 * improved / regressed / neutral.
 */
export function evaluateMetrics(samples: MetricSample[]): MetricOutcome[] {
  return samples.map((sample) => {
    const tolerancePct = Math.max(0, sample.tolerancePct ?? 0);
    const criticality = Math.max(0.1, sample.criticality ?? 1);
    const deltaPct = relativeDeltaPct(sample.candidate, sample.baseline);
    const beyondTolerance = Math.abs(deltaPct) > tolerancePct;
    const wantsHigher = sample.direction === "higher_is_better";
    const movedUp = deltaPct > 0;

    let improved = false;
    let regressed = false;
    if (beyondTolerance) {
      const isGoodMove = wantsHigher ? movedUp : !movedUp;
      improved = isGoodMove;
      regressed = !isGoodMove;
    }

    return {
      ...sample,
      deltaPct,
      tolerancePct,
      criticality,
      improved,
      regressed,
    };
  });
}

/** Aggregate metric outcomes into a regression report with a severity verdict. */
export function buildRegressionReport(
  outcomes: MetricOutcome[],
  policy: ImprovementPolicy = DEFAULT_IMPROVEMENT_POLICY,
): RegressionReport {
  const regressedMetrics = outcomes.filter((m) => m.regressed);
  const improvedMetrics = outcomes.filter((m) => m.improved);

  let severity: RegressionSeverity = "none";
  for (const metric of regressedMetrics) {
    // Impact = how critical this metric is x how large the unwanted move was.
    const magnitude = clamp01((Math.abs(metric.deltaPct) - metric.tolerancePct) / 100);
    const impact = metric.criticality * magnitude;
    let candidateSeverity: RegressionSeverity;
    if (impact >= 2.5) candidateSeverity = "high";
    else if (impact >= 1) candidateSeverity = "medium";
    else if (impact > 0) candidateSeverity = "low";
    else candidateSeverity = "none";

    if (SEVERITY_RANK[candidateSeverity] > SEVERITY_RANK[severity]) {
      severity = candidateSeverity;
    }
  }

  void policy;
  return {
    metrics: outcomes,
    regressedMetrics,
    improvedMetrics,
    severity,
    hasRegressions: regressedMetrics.length > 0,
  };
}

/**
 * Weighted fitness score. Positive means net improvement, negative means the PR
 * makes the system worse. Improvement is normalized by how large the move was
 * relative to the tolerance so tiny wins cannot outvote real regressions.
 */
export function computeImprovementScore(
  outcomes: MetricOutcome[],
  policy: ImprovementPolicy = DEFAULT_IMPROVEMENT_POLICY,
): number {
  let score = 0;
  for (const metric of outcomes) {
    const weight = metric.weight ?? 1;
    const magnitude = Math.max(0, Math.abs(metric.deltaPct) - metric.tolerancePct);
    // Diminishing returns: a 100%+ improvement still only counts as 1 unit.
    const normalized = clamp01(magnitude / 100);
    if (metric.improved) score += policy.improveWeight * weight * normalized;
    if (metric.regressed) score -= policy.regressWeight * weight * (0.5 + normalized);
  }
  return Math.round(score * 1000) / 1000;
}
export interface GuardianDecisionInput {
  score: number;
  report: RegressionReport;
  policy: ImprovementPolicy;
  /**
   * Whether the Guardian believes an automated remediation for the detected
   * regression is available (a concrete, bounded fix it can attempt).
   */
  remediationAvailable: boolean;
  /** Human-readable reasons gathered during evaluation. */
  reasons: string[];
}

export interface GuardianDecision {
  verdict: GuardianVerdict;
  isImprovement: boolean;
  score: number;
  severity: RegressionSeverity;
  reasons: string[];
  nextActions: string[];
}

/**
 * The core decision table.
 *
 * 1. No regression + measurable improvement        -> MERGE
 * 2. Regression, bounded + fixable                 -> FIX_REGRESSION_THEN_MERGE
 * 3. Regression, too severe to fix safely          -> CLOSE_PR
 * 4. Regression, remediation uncertain             -> ESCALATE_TO_ADMIN
 * 5. No regression but no measurable improvement   -> CLOSE_PR
 */
export function decideVerdict(input: GuardianDecisionInput): GuardianDecision {
  const { score, report, policy, remediationAvailable, reasons } = input;
  const decisionReasons = [...reasons];
  const nextActions: string[] = [];
  const meetsImprovement = score >= policy.minImprovementScore;

  if (!report.hasRegressions && meetsImprovement) {
    decisionReasons.push(
      `Weighted improvement score ${score} met the minimum ${policy.minImprovementScore} with zero regressions.`,
    );
    nextActions.push("Merge PR into the base branch (squash) and monitor post-merge telemetry.");
    return {
      verdict: "MERGE",
      isImprovement: true,
      score,
      severity: "none",
      reasons: decisionReasons,
      nextActions,
    };
  }

  if (!report.hasRegressions) {
    decisionReasons.push(
      `No regressions detected, but the improvement score ${score} is below the minimum ${policy.minImprovementScore}.`,
    );
    nextActions.push("Close the PR with a comment stating no measurable improvement was evidenced.");
    return {
      verdict: "CLOSE_PR",
      isImprovement: false,
      score,
      severity: "none",
      reasons: decisionReasons,
      nextActions,
    };
  }

  const regressedNames = report.regressedMetrics.map((m) => m.name).join(", ") || "unknown metric";
  decisionReasons.push(`Regressions detected in ${regressedNames}; severity=${report.severity}.`);

  if (!remediationAvailable) {
    decisionReasons.push("No bounded automated remediation is available for these regressions.");
    nextActions.push("Escalate to the tenant admin with regression evidence attached.");
    return {
      verdict: "ESCALATE_TO_ADMIN",
      isImprovement: false,
      score,
      severity: report.severity,
      reasons: decisionReasons,
      nextActions,
    };
  }

  const tooSevere = SEVERITY_RANK[report.severity] >= SEVERITY_RANK[policy.escalateSeverityAtOrAbove];
  if (tooSevere) {
    decisionReasons.push(
      `Regression severity ${report.severity} is at or above the auto-fix ceiling ${policy.escalateSeverityAtOrAbove}.`,
    );
    nextActions.push("Close the PR — the regression is too large to remedy safely inside the PR.");
    return {
      verdict: "CLOSE_PR",
      isImprovement: false,
      score,
      severity: report.severity,
      reasons: decisionReasons,
      nextActions,
    };
  }

  decisionReasons.push("Regression is bounded and a remediation path exists within the PR scope.");
  nextActions.push("Solve the regression on the PR branch, re-run Guardian evaluation, then merge if clean.");
  return {
    verdict: "FIX_REGRESSION_THEN_MERGE",
    isImprovement: false,
    score,
    severity: report.severity,
    reasons: decisionReasons,
    nextActions,
  };
}

/**
 * Choose the better of two competing candidates (used when more than one PR
 * targets the same problem). Higher score wins; ties break on fewer
 * regressions, then on smaller blast radius.
 */
export function chooseBetterCandidate<T extends { score: number; regressions: number; delta: SourceDelta }>(
  candidates: T[],
): T | undefined {
  if (candidates.length === 0) return undefined;
  const ranked = [...candidates].sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    if (a.regressions !== b.regressions) return a.regressions - b.regressions;
    const aSize = a.delta.filesChanged + a.delta.additions;
    const bSize = b.delta.filesChanged + b.delta.additions;
    return aSize - bSize;
  });
  return ranked[0];
}

/** Flag files that fall outside the declared scope of the change. */
export function findOutOfScopeFiles(files: string[], allowedPrefixes: string[]): string[] {
  if (allowedPrefixes.length === 0) return [];
  return files.filter((file) => !allowedPrefixes.some((prefix) => file.startsWith(prefix)));
}

/** Derive a source delta from a raw GitHub files payload. */
export function buildSourceDelta(
  files: Array<{ filename?: string; additions?: number; deletions?: number }> | undefined,
  allowedPrefixes: string[] = [],
): SourceDelta {
  const list = files ?? [];
  const filenames = list
    .map((f) => f.filename)
    .filter((name): name is string => typeof name === "string" && name.length > 0);
  return {
    filesChanged: list.length,
    additions: list.reduce((sum, f) => sum + (f.additions ?? 0), 0),
    deletions: list.reduce((sum, f) => sum + (f.deletions ?? 0), 0),
    outOfScopeFiles: findOutOfScopeFiles(filenames, allowedPrefixes),
  };
}
