/**
 * PR Guardian MCP tools.
 *
 * The merge gate is *evidence of improvement with zero regressions* — CI status
 * is reported as evidence but is deliberately not the gate.
 *
 *   guardian.evaluate_pr  (viewer) — evaluate one PR and return the verdict
 *   guardian.sweep        (viewer) — evaluate all open PRs, best candidate wins
 *   guardian.act          (agent)  — enact the verdict (merge / close / escalate)
 *
 * Authority still comes from the blast-radius tier, so a Tier-3 PR can never be
 * merged autonomously: it is routed through the governed HITL approval path.
 */

import { randomUUID } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { GuardianService, type GuardianEvaluation } from "../guardian/engine.js";
import type { GuardianVerdict } from "../guardian/improvement.js";
import { globalApprovalManager } from "../policy/approvals/lifecycle.js";
import { globalHITLManager } from "../policy/approvals/hitl.js";
import { globalAuditLogger } from "../audit/audit.js";
import { globalRiskEngine } from "../policy/risk.engine.js";
import { RequestContextStore } from "../policy/auth.context.js";

const DEFAULT_ACCOUNT = "github-primary";

function accessError(required: "viewer" | "agent"): string | undefined {
  const role = RequestContextStore.getRole();
  if (required === "viewer") return role ? undefined : "Authentication required";
  if (role !== "agent" && role !== "admin") {
    return `Forbidden: agent scope required (current role: ${role})`;
  }
  return undefined;
}

function ok(payload: unknown) {
  return {
    content: [
      {
        type: "text" as const,
        text: typeof payload === "string" ? payload : JSON.stringify(payload, null, 2),
      },
    ],
  };
}

function failure(message: string) {
  return { isError: true, content: [{ type: "text" as const, text: message }] };
}

/**
 * Render the audit-grade evidence block. Reused verbatim as the PR comment and
 * as the HITL escalation body so the human sees exactly what the Guardian saw.
 */
export function renderGuardianReport(
  evaluation: GuardianEvaluation,
  headline?: string,
): { markdown: string; verdict: GuardianVerdict } {
  const { pr, decision } = evaluation;
  const lines: string[] = [];

  lines.push(`## PR Guardian — ${headline ?? decision.verdict}`);
  lines.push("");
  lines.push(`**PR #${pr.number}** — ${pr.title}`);
  lines.push(`\`${pr.headRef}\` → \`${pr.baseRef}\` · ${pr.changedFiles} file(s) · +${pr.additions}/-${pr.deletions}`);
  lines.push("");
  lines.push(`| Field | Value |`);
  lines.push(`| --- | --- |`);
  lines.push(`| Verdict | \`${decision.verdict}\` |`);
  lines.push(`| Improvement score | \`${evaluation.score}\` |`);
  lines.push(`| Regression severity | \`${evaluation.severity}\` |`);
  lines.push(`| Blast-radius tier | \`${evaluation.tier.tier}\` (${evaluation.authority}) |`);
  lines.push(
    `| CI evidence (not a gate) | ${evaluation.ci.candidate.passed} passed / ${evaluation.ci.candidate.failed} failed / ${evaluation.ci.candidate.pending} pending |`,
  );
  lines.push("");

  if (evaluation.improvedMetrics.length > 0) {
    lines.push(`**Improvements detected:** ${evaluation.improvedMetrics.map((m) => `\`${m}\``).join(", ")}`);
  } else {
    lines.push("**Improvements detected:** none measurable from the diff.");
  }
  if (evaluation.regressedMetrics.length > 0) {
    lines.push(`**Regressions detected:** ${evaluation.regressedMetrics.map((m) => `\`${m}\``).join(", ")}`);
  } else {
    lines.push("**Regressions detected:** none.");
  }
  lines.push("");

  if (evaluation.metrics.length > 0) {
    lines.push("| Metric | Candidate | Baseline | Δ% | Outcome |");
    lines.push("| --- | --- | --- | --- | --- |");
    for (const metric of evaluation.metrics) {
      const outcome = metric.regressed ? "🔴 regression" : metric.improved ? "🟢 improvement" : "⚪ neutral";
      lines.push(
        `| \`${metric.name}\` | ${metric.candidate} | ${metric.baseline} | ${metric.deltaPct.toFixed(1)}% | ${outcome} |`,
      );
    }
    lines.push("");
  }

  if (evaluation.remediation.strategies.length > 0) {
    lines.push("**Bounded fixes available:**");
    for (const strategy of evaluation.remediation.strategies) lines.push(`- ${strategy}`);
    lines.push("");
  }
  if (evaluation.remediation.blockers.length > 0) {
    lines.push("**Fixes the Guardian will NOT attempt (needs human intent):**");
    for (const blocker of evaluation.remediation.blockers) lines.push(`- ${blocker}`);
    lines.push("");
  }

  if (evaluation.skipped.length > 0) {
    lines.push(`**Not evaluated:** ${evaluation.skipped.join("; ")}`);
    lines.push("");
  }

  lines.push("<details><summary>Decision rationale</summary>");
  lines.push("");
  for (const reason of decision.reasons) lines.push(`- ${reason}`);
  lines.push("");
  for (const action of decision.nextActions) lines.push(`- ️ ${action}`);
  lines.push("");
  lines.push(`</details>`);
  lines.push("");
  lines.push(`_Evaluated at ${evaluation.evaluatedAt} (diff-derived metrics; no LLM inference)._`);

  return { markdown: lines.join("\n"), verdict: decision.verdict };
}
export async function registerGuardianTools(server: McpServer): Promise<void> {
  const scopeSchema = z
    .array(z.string())
    .max(32)
    .optional()
    .describe(
      "Declared path prefixes this PR is allowed to touch (e.g. ['backend/', 'docs/']). Files outside them count as a regression.",
    );

  server.tool(
    "guardian.evaluate_pr",
    "Evaluate a pull request for measurable improvement with zero regressions. CI status is reported as evidence but is NOT the merge gate.",
    {
      accountId: z.string().optional().describe("GitHub account ID (default: github-primary)"),
      prNumber: z.number().int().positive().describe("Pull request number"),
      scopePrefixes: scopeSchema,
    },
    async ({ accountId, prNumber, scopePrefixes }) => {
      try {
        const denied = accessError("viewer");
        if (denied) return failure(denied);

        const service = new GuardianService(accountId ?? DEFAULT_ACCOUNT);
        const evaluation = await service.evaluatePullRequest(prNumber, { scopePrefixes });
        const report = renderGuardianReport(evaluation);

        return ok({
          repo: service.repo(),
          verdict: evaluation.decision.verdict,
          isImprovement: evaluation.decision.isImprovement,
          improvementScore: evaluation.score,
          regressionSeverity: evaluation.severity,
          blastRadius: { tier: evaluation.tier.tier, authority: evaluation.authority, matchedRule: evaluation.tier.matchedRule },
          regressedMetrics: evaluation.regressedMetrics,
          improvedMetrics: evaluation.improvedMetrics,
          remediation: evaluation.remediation,
          ciEvidence: evaluation.ci,
          signals: evaluation.signals,
          skipped: evaluation.skipped,
          reasons: evaluation.decision.reasons,
          nextActions: evaluation.decision.nextActions,
          report: report.markdown,
        });
      } catch (err) {
        return failure(`Error: ${(err as Error).message}`);
      }
    },
  );

  server.tool(
    "guardian.sweep",
    "Sweep all open pull requests: evaluate each on evidence, then pick the strongest candidate per problem and report its verdict.",
    {
      accountId: z.string().optional().describe("GitHub account ID (default: github-primary)"),
      limit: z.number().int().min(1).max(50).optional().describe("Max open PRs to evaluate (default: 20)"),
      scopePrefixes: scopeSchema,
    },
    async ({ accountId, limit, scopePrefixes }) => {
      try {
        const denied = accessError("viewer");
        if (denied) return failure(denied);

        const service = new GuardianService(accountId ?? DEFAULT_ACCOUNT);
        const { summary, evaluations } = await service.sweep({ limit, scopePrefixes });

        const compact = evaluations.map((evaluation) => ({
          prNumber: evaluation.pr.number,
          title: evaluation.pr.title,
          url: evaluation.pr.url,
          verdict: evaluation.decision.verdict,
          improvementScore: evaluation.score,
          regressionSeverity: evaluation.severity,
          blastRadiusTier: evaluation.tier.tier,
          authority: evaluation.authority,
          regressedMetrics: evaluation.regressedMetrics,
          improvedMetrics: evaluation.improvedMetrics,
        }));

        return ok({
          repo: summary.repo,
          total: summary.total,
          verdictCounts: summary.counts,
          failures: summary.failures,
          bestCandidates: summary.bestCandidates.map((evaluation) => ({
            prNumber: evaluation.pr.number,
            title: evaluation.pr.title,
            url: evaluation.pr.url,
            verdict: evaluation.decision.verdict,
            improvementScore: evaluation.score,
            reasons: evaluation.decision.reasons,
            nextActions: evaluation.decision.nextActions,
            report: renderGuardianReport(evaluation).markdown,
          })),
          evaluations: compact,
          evaluatedAt: summary.evaluatedAt,
        });
      } catch (err) {
        return failure(`Error: ${(err as Error).message}`);
      }
    },
  );

  server.tool(
    "guardian.act",
    "Enact the PR Guardian verdict on a pull request: merge a verified improvement with zero regressions, close a non-improvement, fix a bounded regression, or escalate to governed HITL approval. A PR with a detected regression is never merged.",
    {
      accountId: z.string().optional().describe("GitHub account ID (default: github-primary)"),
      prNumber: z.number().int().positive().describe("Pull request number"),
      decision: z
        .enum(["auto", "merge", "close"])
        .default("auto")
        .describe("'auto' follows the evaluated verdict; 'merge'/'close' force that outcome if the evidence permits it."),
      mergeMethod: z.enum(["merge", "squash", "rebase"]).default("squash").describe("Merge strategy"),
      allowCanary: z
        .boolean()
        .optional()
        .describe("Allow merging a Tier-2 (canary-gated) PR. Tier-3 PRs always require human approval."),
      scopePrefixes: scopeSchema,
    },
    async ({ accountId, prNumber, decision, mergeMethod, allowCanary, scopePrefixes }) => {
      try {
        const denied = accessError("agent");
        if (denied) return failure(denied);

        const service = new GuardianService(accountId ?? DEFAULT_ACCOUNT);
        const evaluation = await service.evaluatePullRequest(prNumber, { scopePrefixes });
        const verdict = evaluation.decision.verdict;
        const authority = evaluation.authority;
        const correlationId = RequestContextStore.get()?.requestId ?? randomUUID();

        const audit = (action: string, details: unknown) =>
          globalAuditLogger.log({ correlationId, provider: "github", action, status: "SUCCESS", details });

        // ── Hard safety invariant ───────────────────────────────────────────
        // A regression is never merged away, regardless of what the caller asks.
        if (decision !== "close" && evaluation.regressedMetrics.length > 0) {
          return failure(
            `Refusing to merge PR #${prNumber}: ${evaluation.regressedMetrics.length} regression(s) detected (${evaluation.regressedMetrics.join(", ")}). Evaluated verdict: ${verdict}.`,
          );
        }

        if (decision === "merge" && verdict !== "MERGE") {
          return failure(
            `Refusing to merge PR #${prNumber}: the evidence does not support a merge (verdict: ${verdict}, score: ${evaluation.score}).`,
          );
        }

        // ── Close: not an improvement, or explicitly requested ───────────────
        if (decision === "close" || verdict === "CLOSE_PR") {
          await service.comment(prNumber, renderGuardianReport(evaluation, "Closed by PR Guardian — no verified improvement").markdown);
          await service.close(prNumber);
          audit("close_pr", { prNumber, verdict, score: evaluation.score, severity: evaluation.severity });
          return ok({
            action: "CLOSED",
            prNumber,
            url: evaluation.pr.url,
            verdict,
            improvementScore: evaluation.score,
            reasons: evaluation.decision.reasons,
            note: "The PR was closed without merging. Its branch is preserved on GitHub, so this is fully reversible.",
          });
        }

        // ── Fix the regression, then merge ───────────────────────────────────
        if (verdict === "FIX_REGRESSION_THEN_MERGE") {
          const report = renderGuardianReport(evaluation, "Regression must be fixed before merge");
          await service.comment(prNumber, report.markdown);
          audit("request_regression_fix", {
            prNumber,
            regressions: evaluation.regressedMetrics,
            strategies: evaluation.remediation.strategies,
          });
          return ok({
            action: "FIX_PLAN_ISSUED",
            prNumber,
            url: evaluation.pr.url,
            regressions: evaluation.regressedMetrics,
            strategies: evaluation.remediation.strategies,
            note: "Bounded fixes were published on the PR. Re-run guardian.act after they are applied to merge.",
          });
        }

        // ── Governed escalation: no safe automatic action exists ─────────────
        if (verdict === "ESCALATE_TO_ADMIN" || authority === "HITL_REQUIRED") {
          const request = globalApprovalManager.createRequest(
            { provider: "github", action: "merge_pr" },
            {
              prNumber,
              prUrl: evaluation.pr.url,
              verdict,
              improvementScore: evaluation.score,
              severity: evaluation.severity,
              tier: evaluation.tier.tier,
              regressions: evaluation.regressedMetrics,
              repository: service.repo(),
            },
          );
          await globalHITLManager.requestApproval(request, globalRiskEngine.evaluate({ provider: "github", action: "merge_pr" }));
          await service.comment(
            prNumber,
            `${renderGuardianReport(evaluation, "Awaiting human approval").markdown}\n\n**Approval request:** \`${request.id}\`\n\nApprove with \`policy.approve\` (admin) then re-run \`guardian.act\`. Approval is not treated as proof — conditions are re-validated first.`,
          );
          audit("escalate_for_approval", { prNumber, requestId: request.id, tier: evaluation.tier.tier, verdict });
          return ok({
            action: "ESCALATED",
            prNumber,
            url: evaluation.pr.url,
            requestId: request.id,
            approvalRisk: globalRiskEngine.evaluate({ provider: "github", action: "merge_pr" }),
            tier: evaluation.tier.tier,
            authority,
            reasons: evaluation.decision.reasons,
          });
        }
        // ── Tier-2 canary gate: staged rollout needs explicit permission ─────
        if (authority === "CANARY_GATED" && !allowCanary) {
          const report = renderGuardianReport(evaluation, "Verified improvement — awaiting canary authorisation");
          await service.comment(prNumber, report.markdown);
          audit("pending_canary", { prNumber, tier: evaluation.tier.tier, matchedRule: evaluation.tier.matchedRule });
          return ok({
            action: "PENDING_CANARY",
            prNumber,
            url: evaluation.pr.url,
            tier: evaluation.tier.tier,
            matchedRule: evaluation.tier.matchedRule,
            note: "Tier-2 changes require a staged rollout. Re-run with allowCanary=true to merge, then watch post-merge telemetry for 5 minutes.",
          });
        }

        // ── Merge: verified improvement, zero regressions, authority granted ──
        await service.comment(
          prNumber,
          renderGuardianReport(evaluation, "Verified improvement with zero regressions — merging").markdown,
        );
        const mergeResult = await service.merge(prNumber, mergeMethod, `${evaluation.pr.title} (#${prNumber})`);
        if (!mergeResult.merged) {
          return failure(`Merge was refused by GitHub for PR #${prNumber}: ${mergeResult.message}`);
        }
        audit("merge_pr", {
          prNumber,
          mergeMethod,
          sha: mergeResult.sha,
          score: evaluation.score,
          tier: evaluation.tier.tier,
        });
        return ok({
          action: "MERGED",
          prNumber,
          url: evaluation.pr.url,
          mergeMethod,
          commitSha: mergeResult.sha,
          verdict,
          improvementScore: evaluation.score,
          tier: evaluation.tier.tier,
          authority,
          improvements: evaluation.improvedMetrics,
          note: "Post-merge canary telemetry should be watched for 5 minutes; revert with `git revert` if 5xx errors spike.",
        });
      } catch (err) {
        return failure(`Error: ${(err as Error).message}`);
      }
    },
  );
}