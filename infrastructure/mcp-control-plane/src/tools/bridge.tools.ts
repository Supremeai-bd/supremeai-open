import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { httpRequest } from "../lib/http.js";
import { env } from "../lib/env.js";

/**
 * Bridge onboarding tools — the zero-credential front door for external agents.
 *
 * বাংলা মন্তব্য (#123): `paykaribazaronline/supremeai-open`-এ ঢুকা যেকোনো
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

/** Operator-contract numbers — single source of truth for the guide payload. */
const BRIDGE_CONTRACT = {
  taskIdFormat: "bridge-YYYYMMDD-<slug>",
  branchFormat: "bridge/<task-id>",
  maxDiffBytes: 200 * 1024,
  maxFiles: 30,
  secretScanFamilies: [
    "ghs_", "ghp_", "github_pat_", "sk-", "AKIA", "xox", "AIza", "PEM", "literal-secret", "redis-url",
  ],
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

function githubHeaders(withAuth = true): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "SupremeAI-MCP-Control-Tower-Bridge",
  };
  if (withAuth) {
    const token = env.github.token || process.env["GH_TOKEN"] || "";
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
          { headers: githubHeaders(true), timeoutMs: 15_000 }
        );
        // Fallback to unauthenticated public read if token is rejected (e.g. 401/403)
        if (!res.ok && (res.status === 401 || res.status === 403)) {
          res = await httpRequest<RawIssue[]>(
            `https://api.github.com/repos/${repo}/issues?state=open&labels=${encodeURIComponent(BRIDGE_QUEUE_LABEL)}&per_page=50&sort=created&direction=desc`,
            { headers: githubHeaders(false), timeoutMs: 15_000 }
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
          { headers: githubHeaders(true), timeoutMs: 15_000 }
        );
        // Fallback to unauthenticated public read if token is rejected (e.g. 401/403)
        if (!res.ok && (res.status === 401 || res.status === 403)) {
          res = await httpRequest<RawIssue>(
            `https://api.github.com/repos/${repo}/issues/${number}`,
            { headers: githubHeaders(false), timeoutMs: 15_000 }
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
}
