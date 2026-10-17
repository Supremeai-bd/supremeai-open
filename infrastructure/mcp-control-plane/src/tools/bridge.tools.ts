import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { getGitHubAppInstallationToken } from "../adapters/github/app_token.js";
import { httpRequest } from "../lib/http.js";
import { env } from "../lib/env.js";

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
  { family: "literal-secret", pattern: /(?:^|[^A-Za-z0-9])literal-secret/ },
  { family: "redis-url",     pattern: /(?:^|[^A-Za-z0-9])redis-url/ },
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
    ],
    contract: {
      diffCaps: { maxBytes: BRIDGE_CONTRACT.maxDiffBytes, maxFiles: BRIDGE_CONTRACT.maxFiles },
      secretScanFamilies: BRIDGE_CONTRACT.secretScanFamilies,
      protectedPathsToAdminReview: BRIDGE_CONTRACT.protectedPaths,
      externalAgentsNeverWriteToMain: true,
      landingAuthority: "constitutional gates only — the bridge never merges",
    },
    escalation: {
      elevatedAccess:
        "This anonymous surface is read-only by design. For task-queue claim/heartbeat/complete " +
        "(agent role) or client lifecycle (admin role), an operator issues a bearer token via the " +
        "admin-protected /clients endpoint — see infrastructure/mcp-control-plane/PROVIDER_NEUTRAL_CONNECTIONS.md.",
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

/** Open issues only (defense in depth: the API query filters, we verify). */
function isOpenIssue(raw: RawIssue): boolean {
  return typeof raw.state !== "string" || raw.state.toLowerCase() === "open";
}

/** Pure queue builder: GitHub issues payload → sanitized work-order list. */
export function queueFromIssues(rawIssues: unknown, limit = 20) {
  const items = Array.isArray(rawIssues) ? rawIssues : [];
  return items
    .filter((item): item is RawIssue => Boolean(item) && typeof item === "object")
    .filter(isIssueNotPullRequest)
    .filter(isOpenIssue)
    .map(normalizeQueueItem)
    .sort((a, b) => (b.number ?? 0) - (a.number ?? 0))
    .slice(0, Math.min(Math.max(1, limit), 50));
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
    "List OPEN Bridge Work Orders awaiting an external agent (issues labelled 'bridge:queued' in the public open-source repo). Read-only, public data only.",
    {
      limit: z.number().int().min(1).max(50).optional().describe("Max work orders to return (default 20)"),
    },
    async ({ limit }) => {
      const repo = bridgeOpenRepo();
      try {
        let res = await httpRequest<RawIssue[]>(
          `https://api.github.com/repos/${repo}/issues?state=open&labels=${encodeURIComponent(BRIDGE_QUEUE_LABEL)}&per_page=50&sort=created&direction=desc`,
          { headers: await githubHeaders(true), timeoutMs: 15_000 }
        );
        // Fallback to unauthenticated public read if token is rejected (e.g. 401/403)
        if (!res.ok && (res.status === 401 || res.status === 403)) {
          res = await httpRequest<RawIssue[]>(
            `https://api.github.com/repos/${repo}/issues?state=open&labels=${encodeURIComponent(BRIDGE_QUEUE_LABEL)}&per_page=50&sort=created&direction=desc`,
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
        const workOrders = queueFromIssues(res.data, limit ?? 20);
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              repo,
              label: BRIDGE_QUEUE_LABEL,
              authenticatedRead: Boolean(env.github.token || process.env["GH_TOKEN"]),
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

  server.tool(
    "bridge.submit_patch",
    "Submit completed work to the public open repo as a Bridge Work Order branch and issue without needing personal GitHub credentials. Uses the Tower's server-side GitHub App to create the bridge branch, commit files, and file the work order.",
    {
      taskId: z.string().regex(/^bridge-[0-9]{8}-[a-z0-9-]+$/).describe("Task ID format bridge-YYYYMMDD-<slug>"),
      summary: z.string().min(5).max(1000).describe("Summary of what was changed and why"),
      scopePaths: z.array(z.string()).min(1).max(30).describe("List of relative file paths modified"),
      testsEvidence: z.string().min(10).max(4000).describe("3-tier test evidence: reflection, boot smoke, and tests"),
      files: z.array(z.object({
        path: z.string().min(1),
        content: z.string(),
      })).min(1).max(30).describe("Files to commit on the patch branch"),
      rollbackPath: z.string().optional().describe("Rollback instructions (default: git revert-safe)"),
      agentIdentity: z.string().optional().describe("Agent name / session attribution"),
    },
    async ({ taskId, summary, scopePaths, testsEvidence, files, rollbackPath, agentIdentity }) => {
      // 1. Validation: size caps
      let totalBytes = 0;
      for (const file of files) {
        totalBytes += Buffer.byteLength(file.content, "utf-8");
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
        const hit = scanFileForSecrets(file.content);
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
      const headers: Record<string, string> = {
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SupremeAI-MCP-Control-Tower-Bridge",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      };

      try {
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

        // Step C: Commit files to the branch
        for (const file of files) {
          const getFileRes = await httpRequest<{ sha?: string }>(
            `https://api.github.com/repos/${repo}/contents/${file.path}?ref=${branchName}`,
            { headers, timeoutMs: 15_000 }
          );
          const fileSha = getFileRes.ok ? getFileRes.data?.sha : undefined;

          const putFileRes = await httpRequest<{ message?: string }>(
            `https://api.github.com/repos/${repo}/contents/${file.path}`,
            {
              method: "PUT",
              headers,
              body: {
                message: `feat(bridge): ${taskId} — update ${file.path}`,
                content: Buffer.from(file.content, "utf-8").toString("base64"),
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
          "Supremeai-bd/supremeai",
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
              title: `🌉 Bridge Work Order — ${summary} (${taskId})`,
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

        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              ok: true,
              taskId,
              branch: branchName,
              branchUrl: `https://github.com/${repo}/tree/${branchName}`,
              issueNumber: issueRes.data?.number,
              issueUrl: issueRes.data?.html_url,
              status: "bridge:queued",
              message: "Work submitted successfully! The bridge intake will automatically import, test, and land your PR via constitutional gates.",
            }, null, 2),
          }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Bridge patch submission error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "work.claim",
    "Atomically claim an open task issue per S0.1 specification (Invariant #430). Adds status:claimed, removes status:unclaimed, and posts an atomic-claim comment with a 30-minute lease. Zero-credential self-serve for all coder agents.",
    {
      issueNumber: z.number().int().positive().describe("Task issue number to claim"),
      agentId: z.string().optional().describe("Optional caller identity (defaults to authenticated client or contributor)"),
    },
    async ({ issueNumber, agentId }) => {
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
    }
  );
}
