/**
 * PR Guardian — Change-risk classification & remediation feasibility.
 *
 * This is where the Guardian's autonomy is bounded. The Guardian may decide on
 * *quality* (improvement vs regression) entirely from evidence, but the
 * *authority* to merge is derived from the blast radius of the touched files,
 * following the AGENTS.md risk-tiered autonomy matrix (Tier 1/2/3).
 */

import type { MetricOutcome } from "./improvement.js";

export type ChangeTier = "TIER1" | "TIER2" | "TIER3";

/** Tier 1 = low-risk/self-certifying, Tier 2 = staged/canary, Tier 3 = HITL. */
export type MergeAuthority = "AUTONOMOUS" | "CANARY_GATED" | "HITL_REQUIRED";

export interface TierRule {
  name: string;
  tier: ChangeTier;
  /** Matched against changed file paths. */
  pattern: RegExp;
}

/**
 * Ordered from most consequential to least, so the first matching rule for a
 * file is already its highest-severity classification (a PR touching both docs
 * and auth is classified as high-risk).
 */
export const TIER_RULES: TierRule[] = [
  { name: "auth_or_rbac", tier: "TIER3", pattern: /(auth|rbac|permission|acl|session|jwt|totp|oauth|login)/i },
  { name: "tenant_isolation", tier: "TIER3", pattern: /(tenant|row[_/-]?level|rls|isolation|multi[_/-]?tenant)/i },
  { name: "payments_or_billing", tier: "TIER3", pattern: /(stripe|payment|billing|invoice|checkout|subscription)/i },
  { name: "database_migration", tier: "TIER3", pattern: /(migration|migrations\/|schema\.sql|\.sql$|ddl)/i },
  { name: "infra_or_pipeline", tier: "TIER3", pattern: /(^|\/)(infrastructure|deploy|\.github\/workflows|dockerfile|render\.ya?ml|terraform|k8s|helm)(\/|$|\.)/i },
  { name: "secrets_or_credentials", tier: "TIER3", pattern: /(secret|credential|\.env|vault|infisical|service[_/-]?role|keychain)/i },
  { name: "public_api_contract", tier: "TIER2", pattern: /(^|\/)(routes?|api|controllers?|openapi|swagger|schema|contracts?)(\/|\.)/i },
  { name: "mcp_tool_contract", tier: "TIER2", pattern: /(^|\/)tools\/|(^|\/)mcp\.contracts\.ts$/i },
  { name: "runtime_logic", tier: "TIER2", pattern: /\.(ts|tsx|js|jsx|py|go|rs|java|rb)$/i },
  { name: "docs_and_tests", tier: "TIER1", pattern: /(^|\/)(docs?|tests?|__tests__|spec)(\/|\.)|\.(md|mdx|txt)$|\.(test|spec)\./i },
];

export const TIER_AUTHORITY: Record<ChangeTier, MergeAuthority> = {
  TIER1: "AUTONOMOUS",
  TIER2: "CANARY_GATED",
  TIER3: "HITL_REQUIRED",
};

const TIER_RANK: Record<ChangeTier, number> = { TIER1: 1, TIER2: 2, TIER3: 3 };

export interface TierClassification {
  tier: ChangeTier;
  authority: MergeAuthority;
  /** The rule that determined the tier (null when nothing matched). */
  matchedRule: string | null;
  /** Files that carried the highest-risk classification. */
  matchedFiles: string[];
}

/**
 * Classify a PR by blast radius. Files that no rule recognises still classify as
 * Tier 2 (reviewable) rather than being treated as harmless documentation.
 */
export function classifyChangeTier(files: string[]): TierClassification {
  let tier: ChangeTier = "TIER1";
  let matchedRule: string | null = null;
  const matchedFiles: string[] = [];

  for (const file of files) {
    const rule = TIER_RULES.find((candidate) => candidate.pattern.test(file));
    if (!rule) continue;
    // The PR's tier is the most consequential tier among all matched files, so
    // the first match always establishes the baseline and later matches can only
    // raise it (never lower it).
    if (matchedRule === null || TIER_RANK[rule.tier] > TIER_RANK[tier]) {
      tier = rule.tier;
      matchedRule = rule.name;
      matchedFiles.length = 0;
    }
    if (TIER_RANK[rule.tier] === TIER_RANK[tier]) matchedFiles.push(file);
  }

  if (matchedRule === null) {
    return { tier: "TIER2", authority: TIER_AUTHORITY.TIER2, matchedRule: null, matchedFiles: [] };
  }

  return { tier, authority: TIER_AUTHORITY[tier], matchedRule, matchedFiles };
}
export interface RemediationAssessment {
  available: boolean;
  /** Concrete fixes the Guardian may attempt inside the PR scope. */
  strategies: string[];
  /** Regressions the Guardian must NOT attempt to auto-fix. */
  blockers: string[];
}

/**
 * Whether each regression metric can be remedied mechanically and safely inside
 * the PR branch. Anything requiring product intent, security response, or new
 * test design is deliberately a blocker so the Guardian escalates instead of
 * guessing.
 */
export const REMEDIATION_PLAYBOOK: Record<string, { fixable: boolean; strategy: string }> = {
  debug_artifacts: { fixable: true, strategy: "Remove the debug logging artifacts the PR introduced." },
  code_markers: { fixable: true, strategy: "Resolve or remove the TODO/FIXME markers the PR introduced." },
  localhost_refs: { fixable: true, strategy: "Move the hardcoded localhost references into configuration." },
  type_suppressions: { fixable: true, strategy: "Replace the type suppression with a real type fix." },
  merge_conflicts: { fixable: true, strategy: "Rebase the PR branch onto the base branch and resolve conflicts." },
  check_duration_seconds: { fixable: true, strategy: "Optimize or revert the change responsible for the slowdown." },
  out_of_scope_files: { fixable: true, strategy: "Revert the files that fall outside the PR's declared scope." },
  swallowed_errors: { fixable: false, strategy: "Swallowed exceptions need intent the Guardian cannot infer." },
  disabled_tests: { fixable: false, strategy: "Re-enabling tests may expose real failures; requires diagnosis." },
  hardcoded_secrets: { fixable: false, strategy: "A committed secret is a security incident requiring rotation." },
  removed_test_files: { fixable: false, strategy: "Deleted coverage cannot be recreated safely by the Guardian." },
  failing_checks: { fixable: false, strategy: "Failing checks need root-cause diagnosis before merge." },
  passing_checks: { fixable: false, strategy: "Lost passing checks indicate a real behavioural break." },
};

/**
 * A remediation is only "available" when *every* detected regression has a safe
 * mechanical fix. One unfixable regression makes the whole PR an escalation —
 * the Guardian never half-fixes a change and merges it anyway.
 */
export function assessRemediation(regressed: MetricOutcome[]): RemediationAssessment {
  const strategies: string[] = [];
  const blockers: string[] = [];

  for (const metric of regressed) {
    const play = REMEDIATION_PLAYBOOK[metric.name];
    if (play?.fixable) strategies.push(`${metric.name}: ${play.strategy}`);
    else if (play) blockers.push(`${metric.name}: ${play.strategy}`);
    else blockers.push(`${metric.name}: no known safe remediation for this metric.`);
  }

  return { available: regressed.length > 0 && blockers.length === 0, strategies, blockers };
}