import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import * as fs from "node:fs";
import * as path from "node:path";
import { getGitHubAppInstallationToken } from "../adapters/github/app_token.js";
import { httpRequest } from "../lib/http.js";
import { env } from "../lib/env.js";
import { applyUnifiedDiff, parseUnifiedDiff, resolveFileContent } from "../lib/unified_diff.js";
import { isWorkOrderForTaskId, taskIdSearchQuery } from "../lib/bridge_dedup.js";
import { issueTitleFor, prTitleFor, prFailureFromHttp, PrFailure } from "../lib/bridge_titles.js"; // #2195
import { RequestContextStore } from "../policy/auth.context.js";

export const REFLECTION_EVIDENCE_SECTION = "## Reflection Evidence (why + alternatives_rejected)";
export const REQUIRED_REFLECTION_FIELDS = ["why", "alternatives_rejected"] as const;
export const STALE_TEMPLATE_ERROR_PREFIX = "STALE_TEMPLATE_ERROR";

export function extractRequiredReflectionFields(templateContent: string): string[] {
  if (!templateContent.includes("## Reflection Evidence")) {
    return [];
  }
  const fields: string[] = [];
  if (/-\s+\*\*why:\*\*/.test(templateContent)) {
    fields.push("why");
  }
  if (/-\s+\*\*alternatives_rejected:\*\*/.test(templateContent)) {
    fields.push("alternatives_rejected");
  }
  return fields;
}

export function readPullRequestTemplate(reader?: (path: string) => string | null): {
  source: "live" | "fallback";
  templatePath: string | null;
  requiredFields: readonly string[];
  ruleP7Sizing: { maxFiles: number; maxDiffBytes: number };
} {
  const defaultPath = "../../.github/PULL_REQUEST_TEMPLATE.md";
  let content: string | null = null;
  if (reader) {
    content = reader(defaultPath);
  } else {
    try {
      const resolved = path.resolve(process.cwd(), defaultPath);
      if (fs.existsSync(resolved)) {
        content = fs.readFileSync(resolved, "utf-8");
      }
    } catch {
      content = null;
    }
  }

  const ruleP7Sizing = { maxFiles: 30, maxDiffBytes: 200 * 1024 };

  if (content !== null) {
    const extracted = extractRequiredReflectionFields(content);
    return {
      source: "live",
      templatePath: defaultPath,
      requiredFields: extracted.length > 0 ? extracted : ["why", "alternatives_rejected"],
      ruleP7Sizing,
    };
  }

  return {
    source: "fallback",
    templatePath: null,
    requiredFields: ["why", "alternatives_rejected"],
    ruleP7Sizing,
  };
}

export function validateReflectionEvidence(body: string): string[] {
  const missing: string[] = [];
  const h2Regex = /^## Reflection Evidence/m;
  if (!h2Regex.test(body)) {
    return ["why", "alternatives_rejected"];
  }

  // Check why
  const whyMatch = body.match(/^[ \t]*-[ \t]+\*\*why:\*\*[ \t]*(.*)$/m);
  if (!whyMatch || !whyMatch[1] || whyMatch[1].trim() === "" || /^<.*>$/.test(whyMatch[1].trim())) {
    missing.push("why");
  }

  // Check alternatives_rejected
  const altIndex = body.search(h2Regex);
  const altSection = body.slice(altIndex);
  const altHeaderMatch = altSection.match(/^[ \t]*-[ \t]+\*\*alternatives_rejected:\*\*[ \t]*(.*)$/m);

  let hasValidAlt = false;
  if (altHeaderMatch && altHeaderMatch[1] && altHeaderMatch[1].trim() !== "" && !/^<.*>$/.test(altHeaderMatch[1].trim())) {
    hasValidAlt = true;
  } else if (altHeaderMatch) {
    const afterAlt = altSection.slice(altSection.indexOf(altHeaderMatch[0]) + altHeaderMatch[0].length);
    const lines = afterAlt.split("\n");
    for (const line of lines) {
      if (/^[ \t]*##/.test(line)) break;
      if (/^[ \t]*-[ \t]+\*\*/.test(line)) break;
      const bulletMatch = line.match(/^[ \t]+-[ \t]+(.+)$/);
      if (bulletMatch && bulletMatch[1].trim() !== "" && !/^<.*>$/.test(bulletMatch[1].trim())) {
        hasValidAlt = true;
        break;
      }
    }
  }

  if (!hasValidAlt) {
    missing.push("alternatives_rejected");
  }

  return missing;
}

export function reflectionFixSnippet(): string {
  return [
    REFLECTION_EVIDENCE_SECTION,
    "- **why:** <rationale explaining why this change was made>",
    "- **alternatives_rejected:**",
    "  - <alternative 1 and why it was rejected>",
  ].join("\n");
}

export interface BridgePrBodyOptions {
  taskId: string;
  summary: string;
  issueNumber?: number;
  originalIssueNumber?: number;
  scopePaths: string[];
  testsEvidence: string;
  reflectionWhy?: string;
  alternativesRejected?: string;
  rollbackPath?: string;
}

export function buildBridgePrBody(opts: BridgePrBodyOptions): string {
  const lines: string[] = [
    "## Summary",
    `Autonomous bridge contribution for ${opts.taskId}: ${opts.summary}`,
    "",
  ];

  const linkedIssues: string[] = [];
  const isSpecOnly = opts.scopePaths.length > 0 && opts.scopePaths.every((p) =>
    p.startsWith("docs/") || p.startsWith("docs/bridge/") || p.startsWith("docs/work-orders/")
  );

  // Auto-close original issue if provided (e.g. #1519, #1520)
  if (opts.originalIssueNumber) {
    if (isSpecOnly) {
      linkedIssues.push(`Refs #${opts.originalIssueNumber}`);
    } else {
      linkedIssues.push(`Closes #${opts.originalIssueNumber}`, `Refs #${opts.originalIssueNumber}`);
    }
  }

  // Also close/ref the bridge work order issue
  if (opts.issueNumber && opts.issueNumber !== opts.originalIssueNumber) {
    if (isSpecOnly) {
      linkedIssues.push(`Refs #${opts.issueNumber}`, `<!-- spec-only: keeps #${opts.issueNumber} open until code implementation -->`);
    } else {
      linkedIssues.push(`Closes #${opts.issueNumber}`, `Refs #${opts.issueNumber}`);
    }
  }

  if (linkedIssues.length > 0) {
    lines.push("## Linked Work Order", ...linkedIssues, "");
  }

  lines.push(
    REFLECTION_EVIDENCE_SECTION,
    `- **why:** ${opts.reflectionWhy || ""}`,
    "- **alternatives_rejected:**"
  );

  const rawAlts = (opts.alternativesRejected || "").trim();
  if (rawAlts) {
    const altLines = rawAlts.split("\n").map((l) => l.trim()).filter(Boolean);
    for (const altLine of altLines) {
      const clean = altLine.replace(/^-\s*/, "");
      lines.push(`  - ${clean}`);
    }
  }

  lines.push(
    "",
    "## Scope Paths",
    ...opts.scopePaths.map((p) => `- \`${p}\``),
    "",
    "## Test Evidence (3-tier contract)",
    opts.testsEvidence,
    "",
    "## Rollback Path",
    opts.rollbackPath || "- [x] git revert-safe (pure code change; zero migration/config side effects)"
  );

  return lines.join("\n");
}

/**
 * Bridge onboarding tools — the zero-credential front door for external agents.
 *
 * বাংলা মন্তব্য (#123): `Supremeai-bd/supremeai-open`-এ ঢুকা যেকোনো
 * এজেন্ট (ChatGPT Web, Claude Web, Mistral, Cursor, community) — কোনো প্রাইভেট
 * টোকেন ছাড়াই — টাওয়ারে সংযোগ করে সরাসরি দুটি জিনিস জানতে পারে:
 *   ১. কীভাবে কাজ করতে হবে (canonical onboarding contract — `bridge.guide`)
 *   ২. এখন কী কাজ আছে (public work-order queue — `bridge.work_queue` /
 *      `bridge.work_order`)
 *
 * নিরাপত্তা সীমানা (fail-closed, default-deny অপরিবর্তিত):
 *   - তিনটি tool-ই READ-ONLY ও public-classified (policy/mcp-access.ts)।
 *     কোনো write/destructive/submit capability এখানে নেই — submission সবসময়
 *     GitHub-এ fork → branch → work-order issue/PR পথে (zero-credential by
 *     design), আর landing শুধু constitutional gates।
 *   - public repo-এর পাবলিক কনটেন্টের বাইরে কিছুই ফেরানো যায় না; কোনো টোকেন,
 *     মান বা প্রাইভেট রেপো ডেটা আউটপুটে যায় না।
 *   - GitHub API অথেন্টিকেটেড কল তখনই করা হয় যখন টাওয়ারে টোকেন কনফিগার করা
 *     আছে (unauthenticated public read চালু থাকে — token না থাকলেও কাজ করে)।
 */

/** The public front-door repository (env-overridable for tests/staging). */
export function bridgeOpenRepo(): string {
  return (process.env["BRIDGE_OPEN_REPO"] || "Supremeai-bd/supremeai-open").trim();
}

/** The queue label upstream work orders carry in the open repo. */
export const BRIDGE_QUEUE_LABEL = "bridge:queued";
/**
 * #621 — Bridge hardening: satellite routing, queue scoping, claim lease
 * lifecycle and machine-readable feedback.
 *
 * বাংলা মন্তব্য: এই ব্লক #621-এর চারটি শোধন —
 *   ১. Target Repo আর হার্ডকোড নয় — scope paths থেকে satellite নাম নেওয়া
 *      হয় (bridge.submit_patch-এর WO body-তে সঠিক satellite repository
 *      দেখায়; mixed/unknown anchor থাকলে conservative monorepo default)।
 *   ২. অজানা (anonymous) caller-দের জন্য public-open queue partition —
 *      প্রাইভেট রিপোর CI-failure ইস্যু (repo:infrastructure, repo:api, …)
 *      তাদের queue থেকে বাদ যায় (Rule U2: evidence before action —
 *      anonymous এজেন্ট প্রাইভেট রিপো দেখতেও পারে না, সমাধানও করতে পারে না)।
 *   ৩. Claim lease lifecycle — bridge.work.renew (lease বাড়ানো, মোট সীমা
 *      180m) এবং bridge.work.release (নিজের claim ছেড়ে দেওয়া) — দুটোই
 *      fail-closed, owner-only।
 *   ৪. bridge.read_feedback — intake bot-এর verdict/reason machine-readable
 *      আকারে (bridge:rejected WO-র অন্ধত্ব দূর হয়)।
 *
 * সব pure helpers exported — অফলাইন ব্যাটারিতে যাচাই হয়।
 */

/** Known satellite anchors → private satellite repos (single-target rule per Golden 8 topology). */
const SATELLITE_REPO_MAP: ReadonlyArray<{ anchor: string; repo: string }> = [
  { anchor: "infrastructure/mcp-control-plane/", repo: "Supremeai-bd/supremeai-api" },
  { anchor: "gateway/", repo: "Supremeai-bd/supremeai-api" },
  { anchor: "studio/", repo: "Supremeai-bd/supremeai-studio" },
  { anchor: "browser/", repo: "Supremeai-bd/supremeai-browser" },
  { anchor: "vscode/", repo: "Supremeai-bd/supremeai-vscode" },
  { anchor: "core/", repo: "Supremeai-bd/supremeai-core" },
];

/** The monorepo trunk — the conservative default when no single anchor covers all paths. */
const MONOREPO_TARGET = "Supremeai-bd/supremeai";

export interface TargetRepoResolution {
  repo: string;
  anchor: string | null;
  mode: "satellite" | "monorepo";
}

/**
 * Derive the target repository from the patch's file anchors (#621 Phase 1.3).
 * Satellite ONLY when every scope path shares the same anchor prefix;
 * anything mixed, unknown or empty stays on the monorepo default — the
 * intake bot's single-target-per-order rule cannot split a patch.
 */
export function resolveTargetRepo(scopePaths: readonly string[]): TargetRepoResolution {
  const paths = (scopePaths ?? []).filter((p) => typeof p === "string" && p.length > 0);
  if (paths.length === 0) return { repo: MONOREPO_TARGET, anchor: null, mode: "monorepo" };
  // Longest anchors first so "infrastructure/mcp-control-plane/" wins over any shorter prefix.
  const ordered = [...SATELLITE_REPO_MAP].sort((a, b) => b.anchor.length - a.anchor.length);
  for (const { anchor, repo } of ordered) {
    if (paths.every((p) => p.startsWith(anchor))) {
      return { repo, anchor, mode: "satellite" };
    }
  }
  return { repo: MONOREPO_TARGET, anchor: null, mode: "monorepo" };
}

/**
 * Queue partitioning (#621 Phase 2): an issue is PRIVATE when it carries a
 * `repo:<area>` label whose area is anything other than `open`
 * (repo:infrastructure, repo:api, repo:studio, …). Issues with no repo:*
 * label at all (plain bridge WOs) stay public.
 */
export function isPrivateRepoLabel(label: string): boolean {
  const match = /^repo:([a-z0-9_-]+)$/.exec(label.trim().toLowerCase());
  return match !== null && match[1] !== "open";
}

export function filterPublicQueue<T extends { labels: readonly string[] }>(items: readonly T[]): { kept: T[]; filtered: number } {
  const kept = items.filter((item) => !item.labels.some(isPrivateRepoLabel));
  return { kept, filtered: items.length - kept.length };
}

/** One atomic-claim marker (label plane + comment plane, Invariant #430). */
export interface ParsedClaimMarker {
  agent: string;
  issueNumber: number;
  ts: Date;
  ttlMinutes: number;
}

export interface ClaimMarkerView {
  first: ParsedClaimMarker | null;
  latest: ParsedClaimMarker | null;
}

const ATOMIC_CLAIM_RE = /<!--\s*atomic-claim:issue=(\d+),agent=([A-Za-z0-9_.:-]+),ts=([^,]+),ttl=(\d+)m\s*-->/;

/**
 * Parse ALL atomic-claim markers from an issue's comments — the SAME regex
 * and legacy-JSON fallback the live work.claim handler uses (latest ts wins,
 * first ts = original claim for the total-lease budget). Pure + offline.
 */
export function parseClaimMarkers(comments: ReadonlyArray<{ body?: unknown }>): ClaimMarkerView {
  let first: ParsedClaimMarker | null = null;
  let latest: ParsedClaimMarker | null = null;
  for (const c of comments ?? []) {
    const body = typeof c?.body === "string" ? c.body : "";
    if (!body) continue;
    let marker: ParsedClaimMarker | null = null;
    const match = ATOMIC_CLAIM_RE.exec(body);
    if (match) {
      const ts = new Date(match[3] ?? "");
      if (!isNaN(ts.getTime())) {
        marker = {
          issueNumber: parseInt(match[1] ?? "0", 10),
          agent: match[2] ?? "unknown",
          ts,
          ttlMinutes: parseInt(match[4] ?? "30", 10) || 30,
        };
      }
    } else if (body.includes("<!-- atomic-claim -->") && body.includes('"claimedAt"')) {
      // Legacy JSON marker fallback (same shape the live handler accepts).
      try {
        const jsonMatch = /```json\s*(\{[\s\S]*?\})\s*```/.exec(body);
        const parsed = jsonMatch ? JSON.parse(jsonMatch[1]) : null;
        const ts = parsed?.claimedAt ? new Date(parsed.claimedAt) : null;
        if (ts && !isNaN(ts.getTime())) {
          marker = {
            issueNumber: typeof parsed.issueNumber === "number" ? parsed.issueNumber : 0,
            agent: typeof parsed.claimedBy === "string" ? parsed.claimedBy : "legacy-agent",
            ts,
            ttlMinutes: typeof parsed.leaseMinutes === "number" ? parsed.leaseMinutes : 30,
          };
        }
      } catch { /* malformed legacy marker — ignore */ }
    }
    if (marker) {
      if (!latest || marker.ts > latest.ts) latest = marker;
      if (!first || marker.ts < first.ts) first = marker;
    }
  }
  return { first, latest };
}

export const CLAIM_LEASE_MINUTES = 30;
export const MAX_TOTAL_LEASE_MINUTES = 180;

export type RenewalDecision =
  | { ok: true; grantMinutes: number; expiresAt: Date; totalLeaseMinutes: number }
  | { ok: false; error: "CLAIM_NOT_ACTIVE" | "CLAIM_CONFLICT_OTHER" | "CLAIM_EXPIRED" | "CLAIM_LEASE_EXHAUSTED"; detail: string };

/**
 * Lease-renewal decision (#621 Phase 1.2) — fail-closed:
 *   • only the claiming agent may renew its OWN live claim;
 *   • each renewal grants min(30m, remaining budget);
 *   • the TOTAL lease from the FIRST marker is capped at 180m so anonymous
 *     claims cannot squat forever — after exhaustion, release + re-claim is
 *     the honest path.
 */
export function renewalDecision(
  markers: ClaimMarkerView,
  agent: string,
  now: Date,
  maxTotalLeaseMinutes: number = MAX_TOTAL_LEASE_MINUTES,
): RenewalDecision {
  const latest = markers.latest;
  if (!latest) return { ok: false, error: "CLAIM_NOT_ACTIVE", detail: "Issue has no atomic-claim marker." };
  const first = markers.first ?? latest;
  if (latest.agent !== agent) {
    const live = now.getTime() - latest.ts.getTime() < latest.ttlMinutes * 60_000;
    return live
      ? { ok: false, error: "CLAIM_CONFLICT_OTHER", detail: `Actively claimed by '${latest.agent}'.` }
      : { ok: false, error: "CLAIM_NOT_ACTIVE", detail: `Latest claim belongs to '${latest.agent}' and is expired.` };
  }
  const live = now.getTime() - latest.ts.getTime() < latest.ttlMinutes * 60_000;
  if (!live) return { ok: false, error: "CLAIM_EXPIRED", detail: "Lease already expired — re-claim via work.claim." };
  const remainingMs = maxTotalLeaseMinutes * 60_000 - (now.getTime() - first.ts.getTime());
  if (remainingMs <= 0) {
    return { ok: false, error: "CLAIM_LEASE_EXHAUSTED", detail: `Total lease budget (${maxTotalLeaseMinutes}m) exhausted — release and re-claim.` };
  }
  const grantMinutes = Math.max(1, Math.min(CLAIM_LEASE_MINUTES, Math.ceil(remainingMs / 60_000)));
  return {
    ok: true,
    grantMinutes,
    expiresAt: new Date(now.getTime() + grantMinutes * 60_000),
    totalLeaseMinutes: Math.ceil((now.getTime() - first.ts.getTime()) / 60_000) + grantMinutes,
  };
}

export type ReleaseDecision =
  | { ok: true; stale: boolean; agent: string }
  | { ok: false; error: "CLAIM_NOT_ACTIVE" | "RELEASE_NOT_OWNER"; detail: string };

/**
 * Release decision (#621 Phase 1.2) — fail-closed: only the owning agent may
 * release. Releasing one's own EXPIRED claim is allowed (stale cleanup is
 * good hygiene); touching another agent's claim is refused outright — expired
 * foreign claims free up via work.claim GRANT_TAKEOVER instead.
 */
export function releaseDecision(markers: ClaimMarkerView, agent: string, now: Date): ReleaseDecision {
  const latest = markers.latest;
  if (!latest) return { ok: false, error: "CLAIM_NOT_ACTIVE", detail: "No atomic-claim marker on the issue." };
  if (latest.agent !== agent) {
    return { ok: false, error: "RELEASE_NOT_OWNER", detail: `Claim belongs to '${latest.agent}' — only the owner may release.` };
  }
  const stale = now.getTime() - latest.ts.getTime() >= latest.ttlMinutes * 60_000;
  return { ok: true, stale, agent };
}

export interface IntakeVerdict {
  verdict: string;
  task: string | null;
  reason: string | null;
  repo: string | null;
  pr: string | null;
  at: string | null;
}

export interface IssueFeedback {
  issueNumber: number | null;
  state: string;
  labels: string[];
  latestVerdict: IntakeVerdict | null;
  verdictHistory: IntakeVerdict[];
  latestClaim: { agent: string; at: string; ttlMinutes: number } | null;
  commentCount: number;
}

const INTAKE_VERDICT_RE = /Bridge Intake\s*—\s*([A-Za-z ]+)/;

/**
 * Machine-readable feedback extraction (#621 Phase 1.1). Parses intake-bot
 * verdicts ("Bridge Intake — APPLIED/REJECTED", task/reason/repo/PR lines)
 * and the latest atomic-claim marker out of an issue's comments — the
 * rejection-inspection blindness (`bridge:rejected` with no readable why)
 * is the exact gap this closes. Pure + offline-testable; sanitizes by only
 * reading the structured lines, never echoing raw bodies.
 */
export function parseIntakeFeedback(
  issueNumber: number | null,
  state: string,
  labels: readonly string[],
  comments: ReadonlyArray<{ body?: unknown; created_at?: unknown }>,
): IssueFeedback {
  const history: IntakeVerdict[] = [];
  for (const c of comments ?? []) {
    const body = typeof c?.body === "string" ? c.body : "";
    if (!body) continue;
    const verdictMatch = INTAKE_VERDICT_RE.exec(body);
    if (!verdictMatch) continue;
    const verdict = (verdictMatch[1] ?? "").trim();
    const line = (needle: string): string | null => {
      const m = new RegExp(`${needle}:\\s*([^\\n]+)`).exec(body);
      return m ? (m[1] ?? "").trim() || null : null;
    };
    const prLine = /PR:\s*([^\n]*)/.exec(body);
    const prIds = prLine ? (prLine[1] ?? "").match(/#([0-9]+)/g) : null;
    history.push({
      verdict,
      task: line("task"),
      reason: line("reason"),
      repo: line("landed repo"),
      pr: prIds && prIds.length > 0 ? prIds[prIds.length - 1]! : null,
      at: typeof c.created_at === "string" ? c.created_at : null,
    });
  }
  const markers = parseClaimMarkers(comments);
  return {
    issueNumber,
    state,
    labels: [...labels],
    latestVerdict: history.length > 0 ? history[history.length - 1]! : null,
    verdictHistory: history,
    latestClaim: markers.latest
      ? { agent: markers.latest.agent, at: markers.latest.ts.toISOString(), ttlMinutes: markers.latest.ttlMinutes }
      : null,
    commentCount: (comments ?? []).length,
  };
}


/**
 * Secret scan patterns for the bridge intake gate (U6: fail-closed).
 *
 * Replaces the naive substring check (file.content.includes(secretFamily))
 * with anchored, structure-aware regexes. Each pattern requires a word
 * boundary before the known prefix and sufficient high-entropy characters
 * after, so common English substrings that merely contain the prefix
 * (e.g. "task-" containing "sk-") do not trigger false positives.
 */
const SECRET_SCAN_PATTERNS: ReadonlyArray<{ family: string; pattern: RegExp }> = [
  { family: "ghs_",          pattern: /(?:^|[^A-Za-z0-9])ghs_[A-Za-z0-9]{36}/ },
  { family: "ghp_",          pattern: /(?:^|[^A-Za-z0-9])ghp_[A-Za-z0-9]{36}/ },
  { family: "github_pat_",   pattern: /(?:^|[^A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}/ },
  { family: "sk-",           pattern: /(?:^|[^A-Za-z0-9])sk(?:[-_])[A-Za-z0-9_-]{16,}/ },
  { family: "AKIA",          pattern: /(?:^|[^A-Za-z0-9])AKIA[0-9A-Z]{16}/ },
  { family: "xox",           pattern: /(?:^|[^A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}/ },
  { family: "AIza",          pattern: /(?:^|[^A-Za-z0-9])AIza[0-9A-Za-z_-]{20,}/ },
  { family: "PEM",           pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----/ },
  // Self-scan immunity (#539): these two family needles are assembled at
  // runtime so the scanner source never contains the raw literals it scans
  // for — submissions carrying this file pass the scan they implement.
  { family: "literal" + "-secret", pattern: new RegExp("(?:^|[^A-Za-z0-9])" + "literal" + "-secret") },
  { family: "redis" + "-url",     pattern: new RegExp("(?:^|[^A-Za-z0-9])" + "redis" + "-url") },
];

/**
 * Scan file content for known secret shapes. Returns the family name of the
 * first match, or null if the content is clean. Exported for testability.
 */
export function scanFileForSecrets(content: string): string | null {
  for (const { family, pattern } of SECRET_SCAN_PATTERNS) {
    if (pattern.test(content)) return family;
  }
  return null;
}

/** Operator-contract numbers — single source of truth for the guide payload. */
const BRIDGE_CONTRACT = {
  taskIdFormat: "bridge-YYYYMMDD-<slug>",
  branchFormat: "bridge/<task-id>",
  maxDiffBytes: 200 * 1024,
  maxFiles: 30,
  secretScanFamilies: SECRET_SCAN_PATTERNS.map((p) => p.family),
  protectedPaths: [
    ".github/", "docs/ledger/", "docs/master_docs/", "prisma/", "*credential*", "*.pem", "*.key", "*.p12", ".env*",
  ],
} as const;

const MAX_BODY_CHARS = 8_000;

/** Structured onboarding contract for a zero-credential external agent. */
export function bridgeGuide() {
  return {
    mission:
      "You are an external agent working from the PUBLIC repo Supremeai-bd/supremeai-open. " +
      "Find work with bridge.work_queue, read the contract below, implement the smallest safe change, " +
      "and submit a Bridge Work Order. The tower lands approved work into the private repos through the " +
      "fail-closed bridge pipeline — you never need private credentials.",
    entrypoints: {
      openRepo: bridgeOpenRepo(),
      guide: `https://github.com/${bridgeOpenRepo()}#readme`,
      architectureSpec: "docs/architecture/AGENT_PORTAL_AND_FEDERATION_BRIDGE.md",
      operatorContract: "scripts/bridge/README.md",
    },
    lifecycle: [
      `1. Read the assigned work-order issue (bridge.work_order) — target subsystem, scope, acceptance criteria.`,
      `2. Fork/clone ${bridgeOpenRepo()} and create branch \`${BRIDGE_CONTRACT.branchFormat}\` (task id format \`${BRIDGE_CONTRACT.taskIdFormat}\`).`,
      `3. Implement the SMALLEST safe change strictly inside the declared scope; run verification and capture test evidence.`,
      `4. Push the branch and file/submit the Bridge Work Order (issue or PR labelled \`${BRIDGE_QUEUE_LABEL}\`) with test evidence.`,
      `5. The bridge intake validates (dedup, caps, secret scan, protected-path check), lands a gated PR inside the private repo, and posts a sanitized status back to your public issue.`,
      `6. Claim the task issue with work.claim (zero-credential, 30-minute lease); extend with bridge.work.renew, release with bridge.work.release, and inspect intake verdicts with bridge.read_feedback.`,
    ],
    contract: {
      diffCaps: { maxBytes: BRIDGE_CONTRACT.maxDiffBytes, maxFiles: BRIDGE_CONTRACT.maxFiles },
      secretScanFamilies: BRIDGE_CONTRACT.secretScanFamilies,
      protectedPathsToAdminReview: BRIDGE_CONTRACT.protectedPaths,
      ingressModes: {
        full_file: "default — content is the whole file (new or existing files)",
        unified_diff: "existing files only — git unified diff applied against the branch tip in memory; fail-closed context matching, CRLF-safe, small payloads (#539)",
      },      claimLease: {
        ttlMinutes: CLAIM_LEASE_MINUTES,
        maxTotalLeaseMinutes: MAX_TOTAL_LEASE_MINUTES,
        renewTool: "bridge.work.renew",
        releaseTool: "bridge.work.release",
      },
      queueScope: "anonymous callers see the public-open partition (repo:open / unlabeled); authenticated callers see the full queue (#621)",
      feedbackTool: "bridge.read_feedback — machine-readable intake verdicts (APPLIED/REJECTED + reason) for any open-repo work order (#621)",
      externalAgentsNeverWriteToMain: true,
      landingAuthority: "constitutional gates only — the bridge never merges",
    },
    constitutionFreshness: {
      prTemplateSource: readPullRequestTemplate().source,
      mandatoryReflectionFields: [...REQUIRED_REFLECTION_FIELDS],
      requiredReflectionSection: REFLECTION_EVIDENCE_SECTION,
      ruleP7DomainSizing: "Cohesive task sizing ceiling: 30 files / 200 KB diff (bridge diff caps)",
      preValidation: "Submissions missing reflection evidence fail pre-push with STALE_TEMPLATE_ERROR",
    },
    escalation: {
      selfServeClaiming:
        "Task claims are zero-credential self-serve: work.claim grants a 30-minute lease, " +
        "bridge.work.renew extends it (180m total budget), bridge.work.release frees it. " +
        "bridge.read_feedback returns machine-readable intake verdicts for your submissions.",
      elevatedAccess:
        "This anonymous surface stays inside the public bridge lane. Bearer tokens are only " +
        "needed for elevated capabilities (agent-slot heartbeat, client lifecycle, admin routes) — " +
        "an operator issues them via the admin-protected /clients endpoint — see " +
        "infrastructure/mcp-control-plane/PROVIDER_NEUTRAL_CONNECTIONS.md.",
    },
  };
}

interface RawIssue {
  number?: unknown;
  title?: unknown;
  state?: unknown;
  html_url?: unknown;
  created_at?: unknown;
  updated_at?: unknown;
  labels?: unknown;
  body?: unknown;
  pull_request?: unknown;
  comments?: unknown;
  state_reason?: unknown;
}

/** Sanitized queue entry — public content only, no credentials, no raw trust. */
export function normalizeQueueItem(raw: RawIssue) {
  const labels = Array.isArray(raw.labels)
    ? raw.labels
      .map((label) => {
        if (typeof label === "string") return label;
        const name = (label as { name?: unknown })?.name;
        return typeof name === "string" ? name : null;
      })
      .filter((name): name is string => Boolean(name))
    : [];
  return {
    number: typeof raw.number === "number" ? raw.number : null,
    title: typeof raw.title === "string" ? raw.title : "",
    state: typeof raw.state === "string" ? raw.state : "",
    stateReason: typeof raw.state_reason === "string" ? raw.state_reason : null,
    url: typeof raw.html_url === "string" ? raw.html_url : "",
    createdAt: typeof raw.created_at === "string" ? raw.created_at : "",
    updatedAt: typeof raw.updated_at === "string" ? raw.updated_at : "",
    labels,
    comments: typeof raw.comments === "number" ? raw.comments : 0,
  };
}

export function isIssueNotPullRequest(raw: RawIssue): boolean {
  return !raw.pull_request;
}

export function isAnchorHubOrGovernance(raw: RawIssue): boolean {
  const title = typeof raw.title === "string" ? raw.title : "";
  if (/^\[(Anchor|Federation)\s+Hub\]/i.test(title)) return true;
  const labels = Array.isArray(raw.labels)
    ? raw.labels.map((l) => (typeof l === "string" ? l : (l as { name?: string })?.name || ""))
    : [];
  return labels.some((l) => l.toLowerCase() === "area:governance");
}

export function isRejectedOrLanded(raw: RawIssue): boolean {
  const labels = Array.isArray(raw.labels)
    ? raw.labels.map((l) => (typeof l === "string" ? l : (l as { name?: string })?.name || ""))
    : [];
  return labels.some((l) => l.toLowerCase() === "bridge:rejected" || l.toLowerCase() === "bridge:landed");
}

/** Open issues only (defense in depth: the API query filters, we verify). */
function isOpenIssue(raw: RawIssue): boolean {
  return typeof raw.state !== "string" || raw.state.toLowerCase() === "open";
}

/**
 * Queue fetch paging contract (#2115/#2123): the board must be enumerated
 * completely, not sampled from one page. A single fetch of the newest
 * creations (issues + PRs mixed) makes the queue a creation-rank window
 * that silently drops open work as traffic flows (observed window shrank
 * to ~2.5h during fleet storms and read 20–35 rows vs 98 open issues).
 */
export const QUEUE_PAGE_SIZE = 100;
export const QUEUE_MAX_PAGES = 5;
export const QUEUE_LIMIT_MAX = 200;

/** Pure URL builder for one queue page (label optional, page is 1-based). */
export function buildQueueQueryUrl(repo: string, label: string | null, page: number): string {
  const params = new URLSearchParams({
    state: "open",
    per_page: String(QUEUE_PAGE_SIZE),
    sort: "created",
    direction: "desc",
    page: String(Math.max(1, page)),
  });
  if (label) params.set("labels", label);
  return `https://api.github.com/repos/${repo}/issues?${params.toString()}`;
}

/** Pure page merge: flatten + dedupe by issue number (first occurrence wins). */
export function mergeIssuePages(pages: RawIssue[][]): RawIssue[] {
  const seen = new Set<number>();
  const out: RawIssue[] = [];
  for (const page of Array.isArray(pages) ? pages : []) {
    for (const item of Array.isArray(page) ? page : []) {
      if (!item || typeof item !== "object") continue;
      const num = (item as { number?: unknown }).number;
      if (typeof num === "number" && Number.isFinite(num)) {
        if (seen.has(num)) continue;
        seen.add(num);
      }
      out.push(item as RawIssue);
    }
  }
  return out;
}

/** Pure queue builder: GitHub issues payload → sanitized work-order list. */
export function queueFromIssues(rawIssues: unknown, limit = 20) {
  const items = Array.isArray(rawIssues) ? rawIssues : [];
  return items
    .filter((item): item is RawIssue => Boolean(item) && typeof item === "object")
    .filter(isIssueNotPullRequest)
    .filter(isOpenIssue)
    .filter((item) => !isAnchorHubOrGovernance(item))
    .filter((item) => !isRejectedOrLanded(item))
    .map(normalizeQueueItem)
    .sort((a, b) => (b.number ?? 0) - (a.number ?? 0))
    .slice(0, Math.min(Math.max(1, limit), QUEUE_LIMIT_MAX));
}

async function githubHeaders(withAuth = true): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "SupremeAI-MCP-Control-Tower-Bridge",
  };
  if (withAuth) {
    const token = env.github.token || process.env["GH_TOKEN"] || (await getGitHubAppInstallationToken()) || "";
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

function clipBody(body: unknown): string {
  if (typeof body !== "string") return "";
  return body.length > MAX_BODY_CHARS ? `${body.slice(0, MAX_BODY_CHARS)}\n... [truncated ${body.length - MAX_BODY_CHARS} chars]` : body;
}

export async function registerBridgeTools(server: McpServer): Promise<void> {
  server.tool(
    "bridge.guide",
    "Zero-credential onboarding contract for external agents working from the public open-source repo: lifecycle, branch convention, diff caps, protected paths and the submission flow. No network required.",
    {},
    async () => {
      return { content: [{ type: "text", text: JSON.stringify(bridgeGuide(), null, 2) }] };
    }
  );

  server.tool(
    "bridge.work_queue",
    "List OPEN work-order issues awaiting an agent in the public open-source repo (defaults to all open issues, or filter by optional label). Read-only, public data only.",
    {
      limit: z.number().int().min(1).max(QUEUE_LIMIT_MAX).optional().describe("Max work orders to return (default 20; up to 200 for full-board reconciliation)"),
      label: z.string().optional().describe("Optional label filter; omit or empty = all open issues"),
    },
    async ({ limit, label }) => {
      const repo = bridgeOpenRepo();
      const appliedLabel = typeof label === "string" && label.trim().length > 0 ? label.trim() : null;
      try {
        // Complete enumeration: walk pages until a short page (or cap).
        // Fixes #2115/#2123 — a single per_page=50 fetch turned the queue
        // into a creation-rank window that dropped open work (98 open
        // issues read as 20–35 rows) while bridge_read_feedback still
        // resolved the dropped rows.
        const pages: RawIssue[][] = [];
        let page = 1;
        while (page <= QUEUE_MAX_PAGES) {
          const url = buildQueueQueryUrl(repo, appliedLabel, page);
          let res = await httpRequest<RawIssue[]>(
            url,
            { headers: await githubHeaders(true), timeoutMs: 15_000 }
          );
          // Fallback to unauthenticated public read if token is rejected (e.g. 401/403)
          if (!res.ok && (res.status === 401 || res.status === 403)) {
            res = await httpRequest<RawIssue[]>(
              url,
              { headers: await githubHeaders(false), timeoutMs: 15_000 }
            );
          }
          if (!res.ok) {
            const message = (res.data as { message?: unknown })?.message ?? res.status;
            return {
              isError: true,
              content: [{ type: "text", text: `Bridge work queue unavailable from ${repo} (HTTP ${res.status}: ${String(message)}). Retry shortly; the queue is public and needs no credentials.` }],
            };
          }
          const rows = Array.isArray(res.data) ? res.data : [];
          pages.push(rows);
          if (rows.length < QUEUE_PAGE_SIZE) break;
          page += 1;
        }
        const queued = queueFromIssues(mergeIssuePages(pages), limit ?? 20);
        // Expose all active open issues so agents discover claimable federation work
        const anonymous = RequestContextStore.get()?.authenticated !== true;
        const workOrders = queued;
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              repo,
              label: appliedLabel,
              scope: "all-open",
              authenticatedRead: Boolean(env.github.token || process.env["GH_TOKEN"]),
              callerAuthenticated: !anonymous,
              count: workOrders.length,
              workOrders,
              nextStep: "Call bridge.work_order with a number, then follow bridge.guide.",
            }, null, 2),
          }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Bridge work queue fetch failed: ${(err as Error).message}. The public queue needs no credentials — verify network access to api.github.com and retry.` }],
        };
      }
    }
  );

  server.tool(
    "bridge.work_order",
    "Fetch one Bridge Work Order from the public open-source repo by issue number: title, labels, sanitized body and URL. Read-only, public data only.",
    {
      number: z.number().int().positive().describe("Work-order issue number in the public open-source repo"),
    },
    async ({ number }) => {
      const repo = bridgeOpenRepo();
      try {
        let res = await httpRequest<RawIssue>(
          `https://api.github.com/repos/${repo}/issues/${number}`,
          { headers: await githubHeaders(true), timeoutMs: 15_000 }
        );
        // Fallback to unauthenticated public read if token is rejected (e.g. 401/403)
        if (!res.ok && (res.status === 401 || res.status === 403)) {
          res = await httpRequest<RawIssue>(
            `https://api.github.com/repos/${repo}/issues/${number}`,
            { headers: await githubHeaders(false), timeoutMs: 15_000 }
          );
        }
        if (!res.ok) {
          const message = (res.data as { message?: unknown })?.message ?? res.status;
          return {
            isError: true,
            content: [{ type: "text", text: `Work order #${number} unavailable from ${repo} (HTTP ${res.status}: ${String(message)}).` }],
          };
        }
        if (!isIssueNotPullRequest(res.data)) {
          return {
            isError: true,
            content: [{ type: "text", text: `#${number} is a pull request, not a work-order issue. Use bridge.work_queue to list open work orders.` }],
          };
        }
        const item = normalizeQueueItem(res.data);
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              ...item,
              body: clipBody(res.data.body),
              contract: bridgeGuide().contract,
            }, null, 2),
          }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Work order #${number} fetch failed: ${(err as Error).message}` }],
        };
      }
    }
  );

  // S0.4 Tool Consolidation: bridge.work (Unified work queue / order viewer)
  server.tool(
    "bridge.work",
    "Unified Bridge work hub (S0.4). View available work orders (view='queue'), inspect a specific task (taskId=number), or read onboarding contracts (view='guide').",
    {
      view: z.enum(["queue", "order", "guide"]).default("queue").describe("Operation view: 'queue' to browse tasks, 'order' to view a specific task, 'guide' for contract."),
      taskId: z.number().int().positive().optional().describe("Task issue number when viewing a specific order (view='order' or when taskId is supplied)."),
      limit: z.number().int().min(1).max(50).optional().describe("Max work orders to return when viewing queue (default: 20)."),
      label: z.string().optional().describe("Optional label filter for queue."),
    },
    async ({ view, taskId, limit, label }) => {
      const repo = bridgeOpenRepo();
      if (view === "guide") {
        return { content: [{ type: "text", text: JSON.stringify(bridgeGuide(), null, 2) }] };
      }
      if (taskId !== undefined || view === "order") {
        if (!taskId) {
          return { isError: true, content: [{ type: "text", text: "taskId (issue number) is required when view='order'." }] };
        }
        try {
          let res = await httpRequest<RawIssue>(
            `https://api.github.com/repos/${repo}/issues/${taskId}`,
            { headers: await githubHeaders(true), timeoutMs: 15_000 }
          );
          if (!res.ok && (res.status === 401 || res.status === 403)) {
            res = await httpRequest<RawIssue>(
              `https://api.github.com/repos/${repo}/issues/${taskId}`,
              { headers: await githubHeaders(false), timeoutMs: 15_000 }
            );
          }
          if (!res.ok) {
            return { isError: true, content: [{ type: "text", text: `Work order #${taskId} unavailable from ${repo} (HTTP ${res.status}).` }] };
          }
          if (!isIssueNotPullRequest(res.data)) {
            return { isError: true, content: [{ type: "text", text: `#${taskId} is a pull request, not a work order issue.` }] };
          }
          const item = normalizeQueueItem(res.data);
          return {
            content: [{
              type: "text",
              text: JSON.stringify({ ...item, body: clipBody(res.data.body), contract: bridgeGuide().contract }, null, 2),
            }],
          };
        } catch (err) {
          return { isError: true, content: [{ type: "text", text: `Work order #${taskId} fetch failed: ${(err as Error).message}` }] };
        }
      }

      // Default: view='queue'
      const appliedLabel = typeof label === "string" && label.trim().length > 0 ? label.trim() : null;
      const queryParams = new URLSearchParams({ state: "open", per_page: "50", sort: "created", direction: "desc" });
      if (appliedLabel) queryParams.set("labels", appliedLabel);
      try {
        let res = await httpRequest<RawIssue[]>(
          `https://api.github.com/repos/${repo}/issues?${queryParams.toString()}`,
          { headers: await githubHeaders(true), timeoutMs: 15_000 }
        );
        if (!res.ok && (res.status === 401 || res.status === 403)) {
          res = await httpRequest<RawIssue[]>(
            `https://api.github.com/repos/${repo}/issues?${queryParams.toString()}`,
            { headers: await githubHeaders(false), timeoutMs: 15_000 }
          );
        }
        if (!res.ok) {
          return { isError: true, content: [{ type: "text", text: `Bridge work queue unavailable from ${repo} (HTTP ${res.status}).` }] };
        }
        const queued = queueFromIssues(res.data, limit ?? 20);
        return {
          content: [{
            type: "text",
            text: JSON.stringify({ repo, label: appliedLabel, count: queued.length, workOrders: queued }, null, 2),
          }],
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Bridge work queue fetch failed: ${(err as Error).message}` }] };
      }
    }
  );

  const submitPatchHandler = async ({
    taskId,
    summary,
    originalIssueNumber,
    scopePaths,
    testsEvidence,
    files,
    rollbackPath,
    agentIdentity,
    reflectionWhy,
    alternativesRejected,
  }: {
    taskId: string;
    summary: string;
    originalIssueNumber?: number;
    scopePaths: string[];
    testsEvidence: string;
    files: Array<{ path: string; content?: string; mode?: "full_file" | "unified_diff"; diff?: string }>;
    rollbackPath?: string;
    agentIdentity?: string;
    reflectionWhy?: string;
    alternativesRejected?: string;
  }) => {
    // If not explicitly passed, detect original issue reference from summary e.g. "fix #1519" or "(#1519)"
    const detectedIssueNum = originalIssueNumber ?? (() => {
      const match = summary.match(/(?:close[s]?|fix(?:es)?|resolve[s]?|issue|\#)\s*#?([0-9]{2,6})\b/i);
      return match ? parseInt(match[1], 10) : undefined;
    })();
    // 0. Pre-validate reflection evidence (#567) — fail-closed pre-push before any network or token.
    const candidateBody = [
      REFLECTION_EVIDENCE_SECTION,
      `- **why:** ${reflectionWhy || ""}`,
        `- **alternatives_rejected:** ${alternativesRejected || ""}`,
      ].join("\n");
      const missingReflection = validateReflectionEvidence(candidateBody);
      if (missingReflection.length > 0) {
        return {
          isError: true,
          content: [{
            type: "text",
            text: `${STALE_TEMPLATE_ERROR_PREFIX}: PR reflection evidence incomplete. Missing: ${missingReflection.join(", ")}. Re-read bridge.guide and provide reflectionWhy (- **why:**) and alternativesRejected (alternatives_rejected) to satisfy AGENTS.md §2.\n\n${reflectionFixSnippet()}`,
          }],
        };
      }

      // 0.5. Dual-mode ingress validation (#539) — fail-closed before any network.
      for (const file of files) {
        const ingressMode = file.mode ?? "full_file";
        if (ingressMode === "unified_diff") {
          if (!file.diff) {
            return { isError: true, content: [{ type: "text", text: `File '${file.path}' declares mode unified_diff but carries no diff.` }] };
          }
          if (file.content !== undefined) {
            return { isError: true, content: [{ type: "text", text: `File '${file.path}' declares mode unified_diff but also carries full content; send exactly one of the two.` }] };
          }
          try {
            parseUnifiedDiff(file.diff);
          } catch (err) {
            return { isError: true, content: [{ type: "text", text: `File '${file.path}' diff failed to parse: ${(err as Error).message}` }] };
          }
        } else if (file.content === undefined) {
          return { isError: true, content: [{ type: "text", text: `File '${file.path}' has no content (mode full_file requires content).` }] };
        }
      }

      // 1. Validation: size caps
      let totalBytes = 0;
      for (const file of files) {
        totalBytes += Buffer.byteLength(file.content ?? file.diff ?? "", "utf-8");
        // Path validation: no traversal
        if (file.path.startsWith("/") || file.path.includes("..") || file.path.includes("\\")) {
          return { isError: true, content: [{ type: "text", text: `Invalid file path: ${file.path}` }] };
        }
        // Protected path check
        for (const protectedPath of BRIDGE_CONTRACT.protectedPaths) {
          const cleanPattern = protectedPath.replace(/\*/g, "");
          if (file.path.startsWith(cleanPattern) || file.path.includes(cleanPattern)) {
            return {
              isError: true,
              content: [{ type: "text", text: `Path '${file.path}' is protected (${protectedPath}). Bridge lane does not accept automatic writes to protected paths.` }],
            };
          }
        }
      }
      if (totalBytes > BRIDGE_CONTRACT.maxDiffBytes) {
        return {
          isError: true,
          content: [{ type: "text", text: `Total patch size (${totalBytes} bytes) exceeds maximum allowed (${BRIDGE_CONTRACT.maxDiffBytes} bytes).` }],
        };
      }

      // 2. Secret scanning (structure-aware regex; rejects "task-" false positives)
      for (const file of files) {
        const hit = scanFileForSecrets(file.content ?? file.diff ?? "");
        if (hit) {
          return {
            isError: true,
            content: [{ type: "text", text: `Secret scan violation: pattern '${hit}' found in '${file.path}'. Remove secrets and retry.` }],
          };
        }
      }

      // 3. Resolve GitHub token (App installation token or PAT)
      const token = env.github.token || process.env["GH_TOKEN"] || (await getGitHubAppInstallationToken()) || "";
      if (!token) {
        return {
          isError: true,
          content: [{ type: "text", text: "GitHub App token minting unavailable on the server. Please check Tower credentials." }],
        };
      }

      const repo = bridgeOpenRepo();
      // #621 Phase 1.3 — dynamic target repo resolution from file anchors.
      const targetRepoResolution = resolveTargetRepo(scopePaths);
      const headers: Record<string, string> = {
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SupremeAI-MCP-Control-Tower-Bridge",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      };

      try {
        // Step 0: Ingress Idempotency Check (Zero-Duplicate Invariant, #155, #1692)
        // If an open work order already exists for this taskId, return idempotent success
        // without generating duplicate issues or competing PRs across asynchronous agents.
        // #2136: GitHub issue search ANDs hyphen-split tokens, so an unquoted taskId
        // matched unrelated open WOs whose titles share vocabulary (live false positive:
        // novel `bridge-20261028-radar-index-freshness-r2` resolved to WO #2094), and
        // even quoted-phrase search surfaces issues that merely QUOTE a taskId in prose.
        // The query is therefore a quoted phrase over title+body, and every hit must
        // still verify as a work order FOR exactly this taskId (title tail `(taskId)`
        // or body `### Task ID` field equality) before the idempotent-noop fires.
        const searchRes = await httpRequest<{ items?: Array<{ number: number; html_url: string; title: string; body?: string }> }>(
          `https://api.github.com/search/issues?q=${taskIdSearchQuery(repo, taskId)}`,
          { headers, timeoutMs: 10_000 }
        );
        const existing = searchRes.ok
          ? (searchRes.data?.items ?? []).find((it) => isWorkOrderForTaskId(it.title ?? "", it.body, taskId))
          : undefined;
        if (existing) {
          return {
            content: [{
              type: "text",
              text: JSON.stringify({
                ok: true,
                taskId,
                targetRepo: targetRepoResolution.repo,
                targetAnchor: targetRepoResolution.anchor,
                targetMode: targetRepoResolution.mode,
                issueNumber: existing.number,
                issueUrl: existing.html_url,
                status: "bridge:idempotent-noop",
                message: `Work order for task '${taskId}' is already active (#${existing.number}). Duplicate generation prevented.`,
              }, null, 2),
            }],
          };
        }

        // Step A: Get main branch SHA
        const mainRes = await httpRequest<{ object?: { sha?: string } }>(
          `https://api.github.com/repos/${repo}/git/ref/heads/main`,
          { headers, timeoutMs: 15_000 }
        );
        if (!mainRes.ok || !mainRes.data?.object?.sha) {
          return { isError: true, content: [{ type: "text", text: `Failed to resolve main branch on ${repo}: HTTP ${mainRes.status}` }] };
        }
        const mainSha = mainRes.data.object.sha;

        // Step B: Create branch bridge/<taskId> if not exists
        const branchName = `bridge/${taskId}`;
        const refRes = await httpRequest<{ ref?: string }>(
          `https://api.github.com/repos/${repo}/git/ref/heads/${branchName}`,
          { headers, timeoutMs: 15_000 }
        );

        if (!refRes.ok) {
          const createRefRes = await httpRequest<{ message?: string }>(
            `https://api.github.com/repos/${repo}/git/refs`,
            {
              method: "POST",
              headers,
              body: {
                ref: `refs/heads/${branchName}`,
                sha: mainSha,
              },
              timeoutMs: 15_000,
            }
          );
          if (!createRefRes.ok) {
            const msg = createRefRes.data?.message ? `: ${createRefRes.data.message}` : "";
            return { isError: true, content: [{ type: "text", text: `Failed to create branch ${branchName}: HTTP ${createRefRes.status}${msg}` }] };
          }
        }

        // Step C: Commit files to the branch (dual-mode ingress, #539)
        const fileResults: Array<{ path: string; mode: string; hunksApplied?: number; offsets?: number[] }> = [];
        for (const file of files) {
          const ingressMode = file.mode ?? "full_file";
          const getFileRes = await httpRequest<{ sha?: string; content?: string; encoding?: string }>(
            `https://api.github.com/repos/${repo}/contents/${file.path}?ref=${branchName}`,
            { headers, timeoutMs: 15_000 }
          );
          const fileSha = getFileRes.ok ? getFileRes.data?.sha : undefined;

          let finalContent: string;
          if (ingressMode === "unified_diff") {
            // Stateless in-memory apply against the branch tip: exact context
            // matching with bounded offset search; any ambiguity fails closed
            // (no server-side git checkout needed, no silent fuzz).
            if (!getFileRes.ok || !getFileRes.data?.content) {
              return { isError: true, content: [{ type: "text", text: `File '${file.path}' uses mode unified_diff but does not exist on ${branchName}; use mode full_file to create it.` }] };
            }
            const encoding = getFileRes.data?.encoding;
            if (encoding && encoding !== "base64") {
              return { isError: true, content: [{ type: "text", text: `File '${file.path}' returned unsupported content encoding '${encoding}'.` }] };
            }
            const baseContent = Buffer.from(getFileRes.data?.content ?? "", "base64").toString("utf-8");
            try {
              const applied = applyUnifiedDiff(baseContent, file.diff ?? "");
              finalContent = applied.result;
              fileResults.push({ path: file.path, mode: ingressMode, hunksApplied: applied.hunksApplied, offsets: applied.offsets });
            } catch (err) {
              return { isError: true, content: [{ type: "text", text: `Diff for '${file.path}' failed to apply on ${branchName}: ${(err as Error).message}` }] };
            }
          } else {
            finalContent = file.content ?? "";
            fileResults.push({ path: file.path, mode: ingressMode });
          }

          const putFileRes = await httpRequest<{ message?: string }>(
            `https://api.github.com/repos/${repo}/contents/${file.path}`,
            {
              method: "PUT",
              headers,
              body: {
                message: `feat(bridge): ${taskId} — update ${file.path}`,
                content: Buffer.from(finalContent, "utf-8").toString("base64"),
                branch: branchName,
                ...(fileSha ? { sha: fileSha } : {}),
              },
              timeoutMs: 15_000,
            }
          );
          if (!putFileRes.ok) {
            const msg = putFileRes.data?.message ? `: ${putFileRes.data.message}` : "";
            return { isError: true, content: [{ type: "text", text: `Failed to commit ${file.path} to ${branchName}: HTTP ${putFileRes.status}${msg}` }] };
          }
        }

        // Step D: Create Bridge Work Order Issue
        const issueBody = [
          "### Task ID",
          taskId,
          "",
          "### Patch Branch",
          branchName,
          "",
          "### Target Repo",
          targetRepoResolution.repo,
          "",
          "### Agent Identity",
          agentIdentity || "zero-credential-mcp-agent",
          "",
          "### Summary (what + why)",
          summary,
          "",
          "### Scope Paths",
          scopePaths.map((p) => `- ${p}`).join("\n"),
          "",
          "### Test Evidence (3-tier contract)",
          testsEvidence,
          "",
          "### Rollback Path",
          rollbackPath || "- [x] git revert-safe (pure code change; zero migration/config side effects)",
        ].join("\n");

        const issueRes = await httpRequest<{ number?: number; html_url?: string; message?: string }>(
          `https://api.github.com/repos/${repo}/issues`,
          {
            method: "POST",
            headers,
            body: {
              // #2195 Failure 1: GitHub now caps issue titles at ~256 chars;
              // an unclamped 980-char summary 422'd deterministically and
              // stranded the pushed branch. Clamp preserves the (taskId) tail
              // (authoritative for #2136 dedup).
              title: issueTitleFor(summary, taskId),
              labels: [BRIDGE_QUEUE_LABEL],
              body: issueBody,
            },
            timeoutMs: 15_000,
          }
        );

        if (!issueRes.ok) {
          const msg = issueRes.data?.message ? `: ${issueRes.data.message}` : "";
          return {
            isError: true,
            content: [{ type: "text", text: `Files committed to ${branchName}, but issue creation failed: HTTP ${issueRes.status}${msg}` }],
          };
        }

        // Step E: Atomic PR Pairing (Invariant #514 — Zero Stranded Branches)
        const prBody = buildBridgePrBody({
          taskId,
          summary,
          issueNumber: issueRes.data?.number,
          originalIssueNumber: detectedIssueNum,
          scopePaths,
          testsEvidence,
          reflectionWhy,
          alternativesRejected,
          rollbackPath,
        });

        let prNumber: number | undefined;
        let prUrl: string | undefined;
        // #2195 Failure 2/3: the deployed plane ran `if (prRes.ok && prRes.data)`
        // with NO else — a failed PR creation (validation, head-not-found, the
        // new ~256-char title cap) was silently swallowed and the round returned
        // ok:true/bridge:queued with prNumber undefined, stranding branches with
        // zero diagnostics (contra Invariant #514). Surface the failure as
        // prError while keeping the bridge:queued state machine unchanged: the
        // branch and work-order issue already exist, so the round is still a
        // recoverable queued state — but now the agent and the admin can see WHY.
        let prError: PrFailure | undefined;
        try {
          const prRes = await httpRequest<{ number?: number; html_url?: string; message?: string; errors?: Array<{ message?: string }> }>(
            `https://api.github.com/repos/${repo}/pulls`,
            {
              method: "POST",
              headers,
              body: {
                // #2195 Failure 1 twin: same GitHub ~256-char cap applies to PR
                // titles; clamp with the (taskId) tail preserved.
                title: prTitleFor(summary, taskId),
                head: branchName,
                base: "main",
                body: prBody,
              },
              timeoutMs: 15_000,
            }
          );
          if (prRes.ok && prRes.data) {
            prNumber = prRes.data.number;
            prUrl = prRes.data.html_url;
          } else if (!prRes.ok) {
            prError = prFailureFromHttp(prRes.status, prRes.data);
          }
        } catch (prErr) {
          // Transport-level throw (timeout/DNS): keep the round's existing
          // artifacts visible instead of letting the outer catch discard
          // fileResults + issueNumber behind a generic isError.
          prError = { status: 0, message: (prErr as Error).message };
        }

        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              ok: true,
              taskId,
              targetRepo: targetRepoResolution.repo,
              targetAnchor: targetRepoResolution.anchor,
              targetMode: targetRepoResolution.mode,
              files: fileResults,
              branch: branchName,
              branchUrl: `https://github.com/${repo}/tree/${branchName}`,
              issueNumber: issueRes.data?.number,
              issueUrl: issueRes.data?.html_url,
              prNumber,
              prUrl,
              prError,
              status: prNumber ? "bridge:pr-opened" : "bridge:queued",
              message: prNumber
                ? `Work submitted and PR #${prNumber} opened atomically! CI Guardian will evaluate and land via constitutional gates.`
                : prError
                  ? `Branch + work order created, but PR creation FAILED (${prError.status}: ${prError.message}) — branch stranded pending admin pairing or a resubmit; do NOT treat this round as landed.`
                  : "Work submitted successfully! The bridge intake will automatically import, test, and land your PR via constitutional gates.",
            }, null, 2),
          }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Bridge patch submission error: ${(err as Error).message}` }],
        };
      }
  };

  const submitPatchSchema = {
    taskId: z.string().regex(/^bridge-[0-9]{8}-[a-z0-9-]+$/).describe("Task ID format bridge-YYYYMMDD-<slug>"),
    summary: z.string().min(5).max(1000).describe("Summary of what was changed and why"),
    originalIssueNumber: z.number().int().positive().optional().describe("Original GitHub issue number being resolved (e.g. 1519) to ensure root issue closes automatically on PR merge"),
    scopePaths: z.array(z.string()).min(1).max(30).describe("List of relative file paths modified"),
    testsEvidence: z.string().min(10).max(4000).describe("3-tier test evidence: reflection, boot smoke, and tests"),
    files: z.array(z.object({
      path: z.string().min(1),
      content: z.string().optional().describe("Full file content (required for mode full_file, the default)"),
      mode: z.enum(["full_file", "unified_diff"]).optional().describe("Ingress mode; default full_file (#539 dual-mode)"),
      diff: z.string().optional().describe("Git unified diff against the branch-tip content (required for mode unified_diff)"),
    })).min(1).max(30).describe("Files to commit on the patch branch (dual-mode ingress per #539)"),
    rollbackPath: z.string().optional().describe("Rollback instructions (default: git revert-safe)"),
    agentIdentity: z.string().optional().describe("Agent name / session attribution"),
    reflectionWhy: z.string().optional().describe("Rationale explaining why this change was made (Reflection Evidence)"),
    alternativesRejected: z.string().optional().describe("Alternatives considered and rejected with reasons"),
  };

  server.tool(
    "bridge.submit_patch",
    "Submit completed work to the public open repo as a Bridge Work Order branch and issue without needing personal GitHub credentials. Uses the Tower's server-side GitHub App to create the bridge branch, commit files, and file the work order.",
    submitPatchSchema,
    submitPatchHandler as any
  );

  // S0.4 Tool Consolidation: bridge.submit alias (canonical unified name)
  server.tool(
    "bridge.submit",
    "Unified patch submission endpoint (S0.4 canonical alias of bridge.submit_patch). Submits work to the public repo atomically with automatic branch creation, commit, and PR generation.",
    submitPatchSchema,
    submitPatchHandler as any
  );

  const claimHandler = async ({
    issueNumber,
    agentId,
  }: {
    issueNumber: number;
    agentId?: string;
  }): Promise<{ content: Array<{ type: "text"; text: string }>; isError?: boolean }> => {
      const repo = bridgeOpenRepo();
      const agent = (agentId || "contributor-agent").trim().replace(/[^A-Za-z0-9_.:-]/g, "-");
      const headers = await githubHeaders(true);

      if (!headers.Authorization) {
        return {
          isError: true,
          content: [{ type: "text", text: "CLAIM_ERROR: GitHub App credentials unavailable on Tower." }],
        };
      }

      try {
        // Step 1: Fetch target issue
        const issueRes = await httpRequest<{ state?: string; labels?: Array<{ name?: string }>; message?: string }>(
          `https://api.github.com/repos/${repo}/issues/${issueNumber}`,
          { headers, timeoutMs: 15_000 }
        );
        if (!issueRes.ok) {
          if (issueRes.status === 404) {
            return { isError: true, content: [{ type: "text", text: `ISSUE_NOT_FOUND: Issue #${issueNumber} does not exist.` }] };
          }
          return { isError: true, content: [{ type: "text", text: `HTTP ${issueRes.status}: ${issueRes.data?.message || "Failed to inspect issue"}` }] };
        }

        if (issueRes.data?.state === "closed") {
          return { isError: true, content: [{ type: "text", text: `ISSUE_CLOSED: Issue #${issueNumber} is already closed.` }] };
        }

        const labels = (issueRes.data?.labels || []).map((l) => (l.name || "").toLowerCase());
        const hadClaimedLabel = labels.includes("status:claimed") || labels.includes("status:in-progress");

        // Step 2: Fetch comments to parse active marker
        const commentsRes = await httpRequest<Array<{ body?: string; created_at?: string }>>(
          `https://api.github.com/repos/${repo}/issues/${issueNumber}/comments?per_page=100`,
          { headers, timeoutMs: 15_000 }
        );

        let latestClaim: { agent: string; ts: Date; ttlMinutes: number } | null = null;
        if (commentsRes.ok && Array.isArray(commentsRes.data)) {
          for (const c of commentsRes.data) {
            const body = c.body || "";
            // Match <!-- atomic-claim:issue=123,agent=xyz,ts=...,ttl=30m --> or legacy JSON marker
            const match = /<!--\s*atomic-claim:issue=(\d+),agent=([A-Za-z0-9_.:-]+),ts=([^,]+),ttl=(\d+)m\s*-->/.exec(body);
            if (match) {
              const claimTs = new Date(match[3]);
              if (!isNaN(claimTs.getTime())) {
                if (!latestClaim || claimTs > latestClaim.ts) {
                  latestClaim = { agent: match[2], ts: claimTs, ttlMinutes: parseInt(match[4], 10) || 30 };
                }
              }
            } else if (body.includes("<!-- atomic-claim -->") && body.includes('"claimedAt"')) {
              // Legacy JSON marker fallback
              try {
                const jsonMatch = /```json\s*(\{[\s\S]*?\})\s*```/.exec(body);
                if (jsonMatch) {
                  const parsed = JSON.parse(jsonMatch[1]);
                  const claimTs = new Date(parsed.claimedAt);
                  if (!isNaN(claimTs.getTime())) {
                    if (!latestClaim || claimTs > latestClaim.ts) {
                      latestClaim = { agent: parsed.claimedBy || "legacy-agent", ts: claimTs, ttlMinutes: parsed.leaseMinutes || 30 };
                    }
                  }
                }
              } catch {}
            }
          }
        }

        const now = new Date();
        const ttlMs = (latestClaim?.ttlMinutes || 30) * 60 * 1000;
        const isLive = latestClaim ? now.getTime() - latestClaim.ts.getTime() < ttlMs : false;

        let decision = "GRANT_NEW";
        if (latestClaim) {
          if (latestClaim.agent === agent) {
            decision = isLive ? "NOOP_SELF" : "GRANT_RENEW";
          } else {
            if (isLive) {
              return {
                isError: true,
                content: [{ type: "text", text: `CLAIM_CONFLICT_OTHER: Issue #${issueNumber} is actively claimed by '${latestClaim.agent}'. Expires at ${new Date(latestClaim.ts.getTime() + ttlMs).toISOString()}.` }],
              };
            }
            decision = "GRANT_TAKEOVER";
          }
        }

        if (decision === "NOOP_SELF") {
          return {
            content: [{
              type: "text",
              text: JSON.stringify({
                success: true,
                decision: "NOOP_SELF",
                issueNumber,
                agentId: agent,
                message: `Claim is already active for '${agent}' (idempotent no-op).`,
                expiresAt: new Date(latestClaim!.ts.getTime() + ttlMs).toISOString(),
              }, null, 2),
            }],
          };
        }

        // Step 3: Add status:claimed label
        const addLabelRes = await httpRequest(
          `https://api.github.com/repos/${repo}/issues/${issueNumber}/labels`,
          {
            method: "POST",
            headers,
            body: { labels: ["status:claimed"] },
            timeoutMs: 15_000,
          }
        );
        if (!addLabelRes.ok) {
          return {
            isError: true,
            content: [{ type: "text", text: `LABEL_WRITE_FAILED: Failed to add status:claimed to #${issueNumber} (HTTP ${addLabelRes.status}).` }],
          };
        }

        // Step 4: Post marker comment (Rollback label if comment fails)
        const nowIso = now.toISOString().replace(/\.\d{3}Z$/, "Z");
        const marker = [
          `<!-- atomic-claim:issue=${issueNumber},agent=${agent},ts=${nowIso},ttl=30m -->`,
          `**Claimed by Agent (\`${agent}\`)** via Tower \`work.claim\` (${decision}).`,
          "",
          `- Decision: \`${decision}\``,
          `- Claim timestamp: \`${nowIso}\``,
          `- Lease: \`30m\` (expires \`${new Date(now.getTime() + 30 * 60 * 1000).toISOString()}\`)`,
          `- Invariant #430 planes: label (\`status:claimed\`) + marker comment.`,
        ].join("\n");

        const postCommentRes = await httpRequest(
          `https://api.github.com/repos/${repo}/issues/${issueNumber}/comments`,
          {
            method: "POST",
            headers,
            body: { body: marker },
            timeoutMs: 15_000,
          }
        );

        if (!postCommentRes.ok) {
          // Atomic Rollback: remove status:claimed if we added it
          if (!hadClaimedLabel) {
            await httpRequest(
              `https://api.github.com/repos/${repo}/issues/${issueNumber}/labels/status%3Aclaimed`,
              { method: "DELETE", headers, timeoutMs: 10_000 }
            );
          }
          return {
            isError: true,
            content: [{ type: "text", text: `COMMENT_WRITE_FAILED: Failed to post claim comment on #${issueNumber} (HTTP ${postCommentRes.status}). Rolled back label.` }],
          };
        }

        // Step 5: Remove status:unclaimed if present (best-effort)
        if (labels.includes("status:unclaimed")) {
          await httpRequest(
            `https://api.github.com/repos/${repo}/issues/${issueNumber}/labels/status%3Aunclaimed`,
            { method: "DELETE", headers, timeoutMs: 10_000 }
          );
        }

        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              success: true,
              decision,
              issueNumber,
              agentId: agent,
              claimedAt: nowIso,
              ttlMinutes: 30,
              expiresAt: new Date(now.getTime() + 30 * 60 * 1000).toISOString(),
              planes: ["label:status:claimed", "comment:atomic-claim"],
            }, null, 2),
          }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `work.claim execution error: ${(err as Error).message}` }],
        };
      }
  };

  server.tool(
    "work.claim",
    "Atomically claim an open task issue per S0.1 specification (Invariant #430). Adds status:claimed, removes status:unclaimed, and posts an atomic-claim comment with a 30-minute lease. Zero-credential self-serve for all coder agents.",
    {
      issueNumber: z.number().int().positive().describe("Task issue number to claim"),
      agentId: z.string().optional().describe("Optional caller identity (defaults to authenticated client or contributor)"),
    },
    claimHandler
  );

  // ── #621 Phase 1.1: bridge.read_feedback — rejection/gate visibility ───────
  server.tool(
    "bridge.read_feedback",
    "Read machine-readable feedback for a work-order issue in the public open repo: intake verdicts (APPLIED/REJECTED + reason + landed repo + PR), verdict history and the latest claim marker. Closes the one-way feedback blindness where bridge:rejected work orders carried no readable failure reason. Read-only, public data only.",
    {
      number: z.number().int().positive().describe("Work-order issue number in the public open-source repo"),
    },
    async ({ number }) => {
      const repo = bridgeOpenRepo();
      try {
        let res = await httpRequest<RawIssue>(
          `https://api.github.com/repos/${repo}/issues/${number}`,
          { headers: await githubHeaders(true), timeoutMs: 15_000 }
        );
        if (!res.ok && (res.status === 401 || res.status === 403)) {
          res = await httpRequest<RawIssue>(
            `https://api.github.com/repos/${repo}/issues/${number}`,
            { headers: await githubHeaders(false), timeoutMs: 15_000 }
          );
        }
        if (!res.ok) {
          const message = (res.data as { message?: unknown })?.message ?? res.status;
          return { isError: true, content: [{ type: "text", text: `Work order #${number} unavailable from ${repo} (HTTP ${res.status}: ${String(message)}).` }] };
        }
        if (!isIssueNotPullRequest(res.data)) {
          return { isError: true, content: [{ type: "text", text: `#${number} is a pull request, not a work-order issue. Use bridge.work_queue to list open work orders.` }] };
        }
        let comments: Array<{ body?: unknown; created_at?: unknown }> = [];
        let commentsRes = await httpRequest<Array<{ body?: unknown; created_at?: unknown }>>(
          `https://api.github.com/repos/${repo}/issues/${number}/comments?per_page=50`,
          { headers: await githubHeaders(true), timeoutMs: 15_000 }
        );
        if (!commentsRes.ok && (commentsRes.status === 401 || commentsRes.status === 403)) {
          commentsRes = await httpRequest<Array<{ body?: unknown; created_at?: unknown }>>(
            `https://api.github.com/repos/${repo}/issues/${number}/comments?per_page=50`,
            { headers: await githubHeaders(false), timeoutMs: 15_000 }
          );
        }
        if (commentsRes.ok && Array.isArray(commentsRes.data)) comments = commentsRes.data;
        const item = normalizeQueueItem(res.data);
        const feedback = parseIntakeFeedback(item.number, item.state, item.labels, comments);
        return {
          content: [{
            type: "text",
            text: JSON.stringify({ ...feedback, url: item.url, commentsFetchStatus: commentsRes.ok ? 200 : commentsRes.status }, null, 2),
          }],
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Feedback read for #${number} failed: ${(err as Error).message}` }] };
      }
    }
  );

  // ── #621 Phase 1.2: bridge.lease_manage unified tool ─────────────────────
  const resolveIssueAgent = (agentId?: string): string =>
    (agentId || "contributor-agent").trim().replace(/[^A-Za-z0-9_.:-]/g, "-");

  (server as any).tool(
    "bridge.lease_manage",
    "Unified Bridge lease lifecycle and feedback manager (renew lease, release claim, read feedback).",
    {
      action: z.enum(["renew", "release", "feedback"]).describe("Operation: renew claim lease, release claim, or read feedback"),
      issueNumber: z.number().int().positive().describe("Task / Work-order issue number"),
      agentId: z.string().optional().describe("Caller agent identity (required for renew/release)"),
    },
    async ({ action, issueNumber, agentId }: { action: string; issueNumber: number; agentId?: string }) => {
      if (action === "feedback") {
        const repo = bridgeOpenRepo();
        try {
          let res = await httpRequest<RawIssue>(
            `https://api.github.com/repos/${repo}/issues/${issueNumber}`,
            { headers: await githubHeaders(true), timeoutMs: 15_000 }
          );
          if (!res.ok && (res.status === 401 || res.status === 403)) {
            res = await httpRequest<RawIssue>(
              `https://api.github.com/repos/${repo}/issues/${issueNumber}`,
              { headers: await githubHeaders(false), timeoutMs: 15_000 }
            );
          }
          if (!res.ok) {
            const message = (res.data as { message?: unknown })?.message ?? res.status;
            return { isError: true, content: [{ type: "text", text: `Work order #${issueNumber} unavailable from ${repo} (HTTP ${res.status}: ${String(message)}).` }] };
          }
          let comments: Array<{ body?: unknown; created_at?: unknown }> = [];
          let commentsRes = await httpRequest<Array<{ body?: unknown; created_at?: unknown }>>(
            `https://api.github.com/repos/${repo}/issues/${issueNumber}/comments?per_page=50`,
            { headers: await githubHeaders(true), timeoutMs: 15_000 }
          );
          if (commentsRes.ok && Array.isArray(commentsRes.data)) comments = commentsRes.data;
          const item = normalizeQueueItem(res.data);
          const feedback = parseIntakeFeedback(item.number, item.state, item.labels, comments);
          return { content: [{ type: "text", text: JSON.stringify({ ...feedback, url: item.url }, null, 2) }] };
        } catch (err) {
          return { isError: true, content: [{ type: "text", text: `Feedback read error: ${(err as Error).message}` }] };
        }
      }
      return { isError: true, content: [{ type: "text", text: `Action '${action}' can be invoked via bridge.work.${action} directly or handled here.` }] };
    }
  );

  server.tool(
    "bridge.work.renew",
    "Extend the atomic-claim lease on a task issue you currently hold (30-minute grant, capped at a 180-minute total lease from the original claim). Fail-closed: no live claim, a foreign claim, an expired lease or an exhausted budget all refuse with a structured error. Zero-credential self-serve.",
    {
      issueNumber: z.number().int().positive().describe("Claimed task issue number"),
      agentId: z.string().optional().describe("Caller identity — must match the claiming agent"),
    },
    async ({ issueNumber, agentId }) => {
      const repo = bridgeOpenRepo();
      const agent = resolveIssueAgent(agentId);
      const headers = await githubHeaders(true);
      if (!headers.Authorization) {
        return { isError: true, content: [{ type: "text", text: "RENEW_ERROR: GitHub App credentials unavailable on Tower." }] };
      }
      try {
        const commentsRes = await httpRequest<Array<{ body?: string; created_at?: string }>>(
          `https://api.github.com/repos/${repo}/issues/${issueNumber}/comments?per_page=100`,
          { headers, timeoutMs: 15_000 }
        );
        if (!commentsRes.ok) {
          return { isError: true, content: [{ type: "text", text: `RENEW_ERROR: cannot read comments on #${issueNumber} (HTTP ${commentsRes.status}).` }] };
        }
        const markers = parseClaimMarkers(commentsRes.data ?? []);
        const decision = renewalDecision(markers, agent, new Date());
        if (!decision.ok) {
          return { isError: true, content: [{ type: "text", text: `${decision.error}: ${decision.detail}` }] };
        }
        const nowIso = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
        const marker = [
          `<!-- atomic-claim:issue=${issueNumber},agent=${agent},ts=${nowIso},ttl=${decision.grantMinutes}m -->`,
          `**Lease renewed by Agent (\`${agent}\`)** via Tower \`bridge.work.renew\` (#621).`,
          "",
          `- Grant: \`${decision.grantMinutes}m\` (expires \`${decision.expiresAt.toISOString()}\`)`,
          `- Total lease budget: \`${decision.totalLeaseMinutes}m / ${MAX_TOTAL_LEASE_MINUTES}m\``,
        ].join("\n");
        const postRes = await httpRequest(
          `https://api.github.com/repos/${repo}/issues/${issueNumber}/comments`,
          { method: "POST", headers, body: { body: marker }, timeoutMs: 15_000 }
        );
        if (!postRes.ok) {
          return { isError: true, content: [{ type: "text", text: `RENEW_WRITE_FAILED: could not post renewal marker on #${issueNumber} (HTTP ${postRes.status}).` }] };
        }
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              success: true, decision: "RENEWED", issueNumber, agentId: agent,
              grantMinutes: decision.grantMinutes, expiresAt: decision.expiresAt.toISOString(),
              totalLeaseMinutes: decision.totalLeaseMinutes, maxTotalLeaseMinutes: MAX_TOTAL_LEASE_MINUTES,
            }, null, 2),
          }],
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `bridge.work.renew error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "bridge.work.release",
    "Gracefully release your atomic-claim on a task issue: removes status:claimed, restores status:unclaimed and posts a release marker so other agents can pick the task up immediately instead of waiting for lease expiry. Fail-closed: only the owning agent may release.",
    {
      issueNumber: z.number().int().positive().describe("Claimed task issue number"),
      agentId: z.string().optional().describe("Caller identity — must match the claiming agent"),
    },
    async ({ issueNumber, agentId }) => {
      const repo = bridgeOpenRepo();
      const agent = resolveIssueAgent(agentId);
      const headers = await githubHeaders(true);
      if (!headers.Authorization) {
        return { isError: true, content: [{ type: "text", text: "RELEASE_ERROR: GitHub App credentials unavailable on Tower." }] };
      }
      try {
        const commentsRes = await httpRequest<Array<{ body?: string; created_at?: string }>>(
          `https://api.github.com/repos/${repo}/issues/${issueNumber}/comments?per_page=100`,
          { headers, timeoutMs: 15_000 }
        );
        if (!commentsRes.ok) {
          return { isError: true, content: [{ type: "text", text: `RELEASE_ERROR: cannot read comments on #${issueNumber} (HTTP ${commentsRes.status}).` }] };
        }
        const markers = parseClaimMarkers(commentsRes.data ?? []);
        const decision = releaseDecision(markers, agent, new Date());
        if (!decision.ok) {
          return { isError: true, content: [{ type: "text", text: `${decision.error}: ${decision.detail}` }] };
        }
        const removeRes = await httpRequest(
          `https://api.github.com/repos/${repo}/issues/${issueNumber}/labels/status%3Aclaimed`,
          { method: "DELETE", headers, timeoutMs: 15_000 }
        );
        const addUnclaimedRes = await httpRequest(
          `https://api.github.com/repos/${repo}/issues/${issueNumber}/labels`,
          { method: "POST", headers, body: { labels: ["status:unclaimed"] }, timeoutMs: 15_000 }
        );
        const nowIso = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
        const releaseMarker = [
          `<!-- atomic-claim-release:issue=${issueNumber},agent=${agent},ts=${nowIso} -->`,
          `**Claim released by Agent (\`${agent}\`)** via Tower \`bridge.work.release\` (#621)${decision.stale ? " — stale lease cleanup" : ""}.`,
          "",
          "- Status label restored to `status:unclaimed` (best-effort).",
        ].join("\n");
        await httpRequest(
          `https://api.github.com/repos/${repo}/issues/${issueNumber}/comments`,
          { method: "POST", headers, body: { body: releaseMarker }, timeoutMs: 15_000 }
        );
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              success: true, decision: decision.stale ? "RELEASED_STALE" : "RELEASED", issueNumber, agentId: agent,
              labelRemoved: removeRes.ok, unclaimedRestored: addUnclaimedRes.ok,
            }, null, 2),
          }],
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `bridge.work.release error: ${(err as Error).message}` }] };
      }
    }
  );
}
