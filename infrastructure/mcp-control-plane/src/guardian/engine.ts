/**
 * PR Guardian — Orchestration layer.
 *
 * Reads real GitHub evidence (diff hunks, changed files, check runs), converts it
 * into objective metrics, and produces an evidence-backed verdict:
 *
 *   improvement + zero regressions             -> MERGE
 *   regression, bounded & mechanically fixable -> FIX_REGRESSION_THEN_MERGE
 *   regression, too severe to fix safely       -> CLOSE_PR
 *   regression, remediation uncertain          -> ESCALATE_TO_ADMIN
 *   clean but no measurable improvement        -> CLOSE_PR (never merge busywork)
 *
 * CI pass/fail is captured as *evidence* (`ci`), never as the merge gate.
 */

import {
  GitHubGuardianClient,
  type CheckRunEvidence,
  type PullRequestEvidence,
  type PullRequestFileEvidence,
} from "./github-api.js";
import {
  buildMetricsFromEvidence,
  type CiSummary,
  type MetricBuildResult,
  type SignalCounts,
} from "./signals.js";
import {
  DEFAULT_IMPROVEMENT_POLICY,
  buildRegressionReport,
  chooseBetterCandidate,
  computeImprovementScore,
  decideVerdict,
  evaluateMetrics,
  type GuardianDecision,
  type GuardianVerdict,
  type ImprovementPolicy,
  type MetricOutcome,
  type RegressionSeverity,
  type SourceDelta,
} from "./improvement.js";
import {
  assessRemediation,
  classifyChangeTier,
  type MergeAuthority,
  type RemediationAssessment,
  type TierClassification,
} from "./policy.js";
import { nowTimestamp } from "../lib/timestamps.js";

export interface GuardianPrRef {
  number: number;
  title: string;
  author: string;
  url: string;
  headRef: string;
  headSha: string;
  baseRef: string;
  draft: boolean;
  changedFiles: number;
  additions: number;
  deletions: number;
  labels: string[];
}

export interface GuardianEvaluation {
  pr: GuardianPrRef;
  tier: TierClassification;
  /** Authority derived from blast radius (Tier1 autonomous / Tier2 canary / Tier3 HITL). */
  authority: MergeAuthority;
  delta: SourceDelta;
  metrics: MetricOutcome[];
  regressedMetrics: string[];
  improvedMetrics: string[];
  severity: RegressionSeverity;
  score: number;
  /** CI is recorded as evidence; it is deliberately not the merge gate. */
  ci: { candidate: CiSummary; baseline: CiSummary | null };
  signals: SignalCounts;
  remediation: RemediationAssessment;
  decision: GuardianDecision;
  /** Metrics intentionally not evaluated, with the reason (honest limitations). */
  skipped: string[];
  evaluatedAt: string;
}

export interface EvidenceBundle {
  pr: PullRequestEvidence;
  files: PullRequestFileEvidence[];
  candidateChecks: CheckRunEvidence[];
  baselineChecks: CheckRunEvidence[];
  scopePrefixes?: string[];
}

function deltaFrom(files: PullRequestFileEvidence[], scopePrefixes: string[]): SourceDelta {
  const filenames = files.map((f) => f.filename);
  return {
    filesChanged: files.length,
    additions: files.reduce((sum, f) => sum + f.additions, 0),
    deletions: files.reduce((sum, f) => sum + f.deletions, 0),
    outOfScopeFiles:
      scopePrefixes.length === 0
        ? []
        : filenames.filter((f) => !scopePrefixes.some((p) => f.startsWith(p))),
  };
}
/**
 * Pure evaluation: no network, no persistence. Deterministic and unit-testable.
 */
export function evaluateEvidence(
  bundle: EvidenceBundle,
  policy: ImprovementPolicy = DEFAULT_IMPROVEMENT_POLICY,
): GuardianEvaluation {
  const { pr, files } = bundle;
  const scopePrefixes = bundle.scopePrefixes ?? [];
  const built: MetricBuildResult = buildMetricsFromEvidence(bundle);

  const outcomes = evaluateMetrics(built.metrics);
  const report = buildRegressionReport(outcomes, policy);
  const score = computeImprovementScore(outcomes, policy);
  const remediation = assessRemediation(report.regressedMetrics);
  const tier = classifyChangeTier(files.map((f) => f.filename));

  const reasons: string[] = [
    `Evaluated ${files.length} changed file(s): +${pr.additions}/-${pr.deletions} lines; metrics derived from the diff only.`,
    `CI evidence (not a merge gate): ${built.ci.candidate.passed} passed, ${built.ci.candidate.failed} failed, ${built.ci.candidate.pending} pending.`,
    `Blast-radius classification: ${tier.tier} (${tier.matchedRule ?? "no matching rule"}).`,
  ];
  if (built.skipped.length > 0) reasons.push(`Unevaluated evidence: ${built.skipped.join("; ")}.`);

  const decision = decideVerdict({
    score,
    report,
    policy,
    remediationAvailable: remediation.available,
    reasons,
  });

  return {
    pr: {
      number: pr.number,
      title: pr.title,
      author: pr.author,
      url: pr.htmlUrl,
      headRef: pr.headRef,
      headSha: pr.headSha,
      baseRef: pr.baseRef,
      draft: pr.draft,
      changedFiles: pr.changedFiles,
      additions: pr.additions,
      deletions: pr.deletions,
      labels: pr.labels,
    },
    tier,
    authority: tier.authority,
    delta: deltaFrom(files, scopePrefixes),
    metrics: outcomes,
    regressedMetrics: report.regressedMetrics.map((m) => m.name),
    improvedMetrics: report.improvedMetrics.map((m) => m.name),
    severity: report.severity,
    score,
    ci: built.ci,
    signals: built.signals,
    remediation,
    decision,
    skipped: built.skipped,
    evaluatedAt: nowTimestamp().timestamp,
  };
}
export interface EvaluateOptions {
  /** Declared scope of the change; files outside it become a regression metric. */
  scopePrefixes?: string[];
  policy?: ImprovementPolicy;
  /** Fetch check runs for the base branch too (extra API call, richer CI evidence). */
  includeBaselineChecks?: boolean;
}

export interface GuardianSweepSummary {
  repo: string;
  total: number;
  counts: Record<GuardianVerdict, number>;
  /** Strongest candidate per problem group, chosen by the improvement rule. */
  bestCandidates: GuardianEvaluation[];
  /** PRs that could not be evaluated, with the reason (never silently dropped). */
  failures: string[];
  evaluatedAt: string;
}

export interface GuardianSweepResult {
  summary: GuardianSweepSummary;
  evaluations: GuardianEvaluation[];
}

/** Groups PRs that appear to address the same problem so the best one can win. */
function problemKey(evaluation: GuardianEvaluation): string {
  const labels = [...evaluation.pr.labels].map((l) => l.toLowerCase()).sort();
  if (labels.length > 0) return labels.join("|");
  return `${evaluation.pr.baseRef}:unlabeled`;
}

function wrapForRanking(evaluation: GuardianEvaluation) {
  return {
    score: evaluation.score,
    regressions: evaluation.regressedMetrics.length,
    delta: evaluation.delta,
    evaluation,
  };
}

/**
 * Pick the single best PR out of competing candidates using the shared ranking
 * rule from the improvement engine (score, then fewest regressions, then the
 * smallest blast radius).
 */
export function bestCandidate(evaluations: GuardianEvaluation[]): GuardianEvaluation | undefined {
  return chooseBetterCandidate(evaluations.map(wrapForRanking))?.evaluation;
}

/**
 * Fetches evidence and evaluates pull requests. Stateless apart from the
 * injected GitHub account, so it is safe to instantiate per request.
 */
export class GuardianService {
  private readonly client: GitHubGuardianClient;

  constructor(accountId: string) {
    this.client = new GitHubGuardianClient(accountId);
  }

  public repo(): string {
    return this.client.repo();
  }

  /** Collect every piece of evidence needed for a verdict (best-effort per source). */
  async gatherEvidence(prNumber: number, opts: EvaluateOptions = {}): Promise<EvidenceBundle> {
    const pr = await this.client.getPullRequest(prNumber);
    const files = await this.client.getPullRequestFiles(prNumber);
    const candidateChecks = await this.safeChecks(pr.headSha || pr.headRef);

    let baselineChecks: CheckRunEvidence[] = [];
    if (opts.includeBaselineChecks !== false && pr.baseRef) {
      baselineChecks = await this.safeChecks(pr.baseRef);
    }

    return { pr, files, candidateChecks, baselineChecks, scopePrefixes: opts.scopePrefixes ?? [] };
  }

  /** Check runs are evidence, not a gate — a lookup failure must not fail the verdict. */
  private async safeChecks(ref: string): Promise<CheckRunEvidence[]> {
    if (!ref) return [];
    try {
      return await this.client.getCheckRuns(ref);
    } catch {
      return [];
    }
  }

  async evaluatePullRequest(prNumber: number, opts: EvaluateOptions = {}): Promise<GuardianEvaluation> {
    const bundle = await this.gatherEvidence(prNumber, opts);
    return evaluateEvidence(bundle, opts.policy ?? DEFAULT_IMPROVEMENT_POLICY);
  }

  /**
   * Evaluate every open PR, then pick the strongest candidate per problem group.
   * A single bad PR is reported in `failures`, never swallowed.
   */
  async sweep(opts: EvaluateOptions & { limit?: number } = {}): Promise<GuardianSweepResult> {
    const limit = Math.min(50, Math.max(1, opts.limit ?? 20));
    const prs = await this.client.listOpenPullRequests(limit);
    const evaluations: GuardianEvaluation[] = [];
    const failures: string[] = [];

    for (const pr of prs) {
      try {
        evaluations.push(await this.evaluatePullRequest(pr.number, opts));
      } catch (err) {
        failures.push(`PR #${pr.number}: ${(err as Error).message}`);
      }
    }

    const counts: Record<GuardianVerdict, number> = {
      MERGE: 0,
      FIX_REGRESSION_THEN_MERGE: 0,
      CLOSE_PR: 0,
      ESCALATE_TO_ADMIN: 0,
    };
    for (const evaluation of evaluations) counts[evaluation.decision.verdict] += 1;

    const groups = new Map<string, GuardianEvaluation[]>();
    for (const evaluation of evaluations) {
      const key = problemKey(evaluation);
      const bucket = groups.get(key) ?? [];
      bucket.push(evaluation);
      groups.set(key, bucket);
    }

    const bestCandidates: GuardianEvaluation[] = [];
    for (const bucket of groups.values()) {
      const best = bestCandidate(bucket);
      if (best) bestCandidates.push(best);
    }

    return {
      summary: {
        repo: this.client.repo(),
        total: evaluations.length,
        counts,
        bestCandidates,
        failures,
        evaluatedAt: nowTimestamp().timestamp,
      },
      evaluations,
    };
  }

  async merge(prNumber: number, method: "merge" | "squash" | "rebase" = "squash", commitTitle?: string) {
    return this.client.mergePullRequest(prNumber, method, commitTitle);
  }

  async close(prNumber: number): Promise<void> {
    return this.client.closePullRequest(prNumber);
  }

  async comment(prNumber: number, body: string) {
    return this.client.comment(prNumber, body);
  }
}
