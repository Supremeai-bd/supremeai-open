import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { getWorkflowRuns, getFailedLogs, listSecrets, readFile, listPullRequests, searchCode, createIssue } from "../adapters/github/index.js";
import { resolvePerPage } from "../lib/github_pagination.js"; // #2311/R62 per_page alias
import { RequestContextStore, roleRank, type UserRole } from "../policy/auth.context.js";
import { scopeAllows } from "../policy/client-registry.js";
import { buildAccountRegistry } from "../registry/account.registry.js";

/**
 * #110 Part 1.2 — Repository isolation policy for GitHub read tools.
 *
 * বাংলা মন্তব্য: রিপো-আইসোলেশন মিডলওয়্যার — restricted_viewer শুধুমাত্র
 * স্যাটেলাইট রিপো (supremeai-api/open/sdk/...) পড়তে পারবে, কোর প্রাইভেট রিপো
 * (supremeai) কঠোরভাবে ব্লকড; repo_viewer সব রিপো রিড-অনলি পাবে; agent ও
 * উর্ধ্বতন স্তর আগের মতোই read/write (টাস্ক স্কোপের মধ্যে)।
 */
export const SATELLITE_REPOS: ReadonlySet<string> = new Set([
  "supremeai-open",
  "supremeai-api",
  "supremeai-core",
  "supremeai-studio",
  "supremeai-vscode",
  "supremeai-browser",
  "supremeai-archive",
]);

export function isSatelliteRepo(repoName: string): boolean {
  const clean = repoName.replace(/^Supremeai-bd\//i, "").toLowerCase();
  if (clean === "supremeai") return false;
  return SATELLITE_REPOS.has(clean) || clean.startsWith("supremeai-");
}

export type RepoAccess = "none" | "satellite-readonly" | "all-readonly" | "read-write";

export function repoAccessFor(role: UserRole): RepoAccess {
  const rank = roleRank(role);
  if (rank >= 3) return "read-write"; // agent / admin / supremeadmin
  if (rank >= 2) return "all-readonly"; // repo_viewer (auditor)
  if (rank >= 1) return "satellite-readonly"; // restricted_viewer
  return "none"; // viewer / public
}

/**
 * Default-deny read gate for GitHub tools. Returns `null` when the caller may
 * proceed, or a denial message. Resolves the target repo from the account's
 * baseUrl (`.../repos/<owner>/<repo>`), enforces the satellite allowlist for
 * restricted_viewer, and requires an explicit repo-read scope for the new
 * read-only tiers (fail-closed — legacy pre-#110 records cannot exist for
 * these roles, so no behavior regression is possible for old tiers).
 */
export const CONTRACT_FILE_PATTERNS: readonly RegExp[] = [
  /\.d\.ts$/i,
  /(^|\/)schema\.prisma$/i,
  /(^|\/)openapi\.(json|ya?ml)$/i,
  /(^|\/)swagger\.(json|ya?ml)$/i,
  /\.graphqls?$/i,
  /(^|\/)types?\.json$/i,
];

export function isContractFile(path: string): boolean {
  if (typeof path !== "string" || path.trim() === "") return false;
  const normalized = path.replace(/\\/g, "/");
  return CONTRACT_FILE_PATTERNS.some((pattern) => pattern.test(normalized));
}

export function assertRepoReadAccess(toolName: string, accountId: string, accountRepoUrl: string, path?: string): string | null {
  const store = RequestContextStore.get();
  if (!store) {
    return `Forbidden: tool '${toolName}' requires an authenticated request context (default-deny).`;
  }
  const access = repoAccessFor(store.role);
  if (access === "none") {
    return `Forbidden: role '${store.role}' has no repository read access for '${toolName}'.`;
  }
  // রিপো নির্ণয়: অ্যাকাউন্ট baseUrl থেকে <owner>/<repo> বের করা হয়।
  const match = /\/repos\/([^/]+)\/([^/?#]+)/.exec(accountRepoUrl);
  const fullName = match ? `${match[1]}/${match[2].replace(/\.git$/, "")}` : accountId;
  const shortName = fullName.split("/").pop() ?? fullName;

  // Organization-level access restriction: only admin and supremeadmin can query org-wide resources
  if ((shortName.startsWith("github-org-") || accountRepoUrl.includes("/orgs/")) && roleRank(store.role) < 4) {
    return `Forbidden: organization-level resources are strictly restricted to admin and supremeadmin roles (current role: '${store.role}').`;
  }

  // Ghost Cloaking Policy: 'supremeai-api' is accessible to agent and admin roles (rank >= 3),
  // but cloaked for restricted viewers / public viewers (rank < 3) except for contract files.
  const contract = isContractFile(path ?? "");
  if (shortName === "supremeai-api" && roleRank(store.role) < 3 && !contract) {
    return `Repository not found: '${shortName}'.`;
  }
  // কোর মোনোরিপো সার্বভৌম সিকিউরিটি: 'supremeai' শুধুমাত্র admin ও supremeadmin
  // রোলের জন্য উন্মুক্ত — তবে contract ফাইলগুলো non-admin-ও read-only পড়তে পারবে।
  if (shortName === "supremeai" && roleRank(store.role) < 4 && !contract) {
    return `Forbidden: core monorepo 'supremeai' is strictly restricted to admin and supremeadmin roles; non-admin roles are limited to satellite repos (current role: '${store.role}').`;
  }
  if (access === "satellite-readonly" && !contract && (shortName === "supremeai" || !isSatelliteRepo(shortName))) {
    return `Forbidden: restricted_viewer is limited to satellite repos; '${shortName}' is outside the allowlist (core repo is blocked).`;
  }
  const scopes = store.scopes ?? [];
  if (access !== "read-write") {
    // রিড-অনলি স্তরের জন্য সুস্পষ্ট repo-read স্কোপ আবশ্যক (fail-closed)।
    const hasSatellite = scopeAllows(scopes, "repos:satellite:read");
    const hasAll = scopeAllows(scopes, "repos:all:read");
    const ok = access === "all-readonly" ? hasAll || hasSatellite : hasSatellite;
    if (!ok) {
      return `Forbidden: '${toolName}' requires a repo-read scope — ask an admin to re-apply your role (scopes refresh on role change).`;
    }
  }
  return null;
}

/** Resolves the account or target repo base URL exactly as the adapter does (no I/O). */
export function repoUrlFor(accountId?: string, repo?: string): string {
  if (repo) {
    const cleanRepo = repo.replace(/^Supremeai-bd\//i, "");
    return `https://api.github.com/repos/Supremeai-bd/${cleanRepo}`;
  }
  const id = accountId || "github-primary";
  try {
    const account = buildAccountRegistry().find(
      (a) => (a.id === id || a.displayName.includes(`/${id})`)) && a.provider === "github"
    );
    if (account?.url) return account.url;
  } catch {
    // fallback
  }
  const clean = id.replace(/^github-pay-/, "").replace(/^Supremeai-bd\//i, "");
  return `https://api.github.com/repos/Supremeai-bd/${clean}`;
}

/** R66 option A — derive the honest target echo from the resolved URL.
 * The value repoUrlFor already computes; parsing it here keeps the echo and
 * the actual request target from ever drifting apart (single producer). */
export function describeTarget(targetUrl: string): { targetRepo: string; targetUrl: string } {
  const m = /\/repos\/([^/]+)\/([^/?#]+)/.exec(targetUrl);
  if (m) return { targetRepo: `${m[1]}/${m[2].replace(/\.git$/, "")}`, targetUrl };
  return { targetRepo: targetUrl, targetUrl };
}

/** #2469/#2452 (R66 default-repo drift, disclosure slice) — the no-repo
 * fallback is real runtime behavior (the github-primary account URL = the
 * core monorepo 'Supremeai-bd/supremeai'), but it was invisible in
 * tools/list, so callers silently landed on the monorepo and cited run/PR
 * ids without a repo attestation. Deriving the disclosure from repoUrlFor()
 * keeps description and runtime on ONE producer: if the registry default
 * ever moves, the disclosure moves with it — the drift can never re-hide.
 * Registration-time only; repoUrlFor is no-I/O by contract (try/catch kept
 * so schema advertisement can never fail registration). */
export function repoDefaultNote(accountId = "github-primary"): string {
  try {
    const { targetRepo } = describeTarget(repoUrlFor(accountId, undefined));
    return ` When 'repo' is omitted the call silently targets the account default '${targetRepo}' (R66 drift class, #2452/#2469) — always pass repo explicitly and verify rows via the targetRepo/targetUrl echo.`;
  } catch {
    return " When 'repo' is omitted the call silently targets the account default repo (R66 drift class, #2452/#2469) — always pass repo explicitly and verify rows via the targetRepo/targetUrl echo.";
  }
}

/** R66 echo schemas: repo-targeted tools always resolve a repo; the search
 * pair resolves org-wide when repo is omitted (null = org-wide, honest). */
const targetEchoSchema = {
  targetRepo: z.string(),
  targetUrl: z.string(),
};
const targetEchoSearchSchema = {
  targetRepo: z.string().nullable(),
  targetUrl: z.string().nullable(),
};

export async function registerGitHubTools(server: McpServer): Promise<void> {
  // ── Unified GitHub Actions Tool ──
  // R66 option A (radar): every github_* result echoes its resolved target —
  // targetRepo/targetUrl ride in structuredContent (schema-required), the
  // TextContent block stays byte-identical (R65 dual-emission discipline).
  server.registerTool(
    "github.actions_op",
    {
      description: "Unified GitHub Actions diagnostic tool (list workflow runs or fetch failed job logs).",
      annotations: { readOnlyHint: true, idempotentHint: true },
      inputSchema: {
        action: z.enum(["list_runs", "get_failed_logs"]).describe("Action to perform"),
        accountId: z.string().optional().describe("The account ID (e.g. 'github-primary')"),
        repo: z.string().optional().describe("Target repository name" + repoDefaultNote()),
        per_page: z.number().int().min(1).max(100).optional().describe(
          "GitHub-REST page-size, fully honored (#2614 live-verified): precedence per_page ?? limit ?? default 5, clamped to GitHub's 1..100 envelope. A 5-row response means params were dropped (e.g. camelCase perPage), not a page-lock — re-probe with per_page=100 before filing an outage"),
        limit: z.number().optional().describe("Number of runs to fetch (default: 5)"),
        runId: z.string().optional().describe("Run ID (required for get_failed_logs)"),
      },
      outputSchema: targetEchoSchema,
    },
    async ({ action, accountId, repo, per_page, limit, runId }: { action: string; accountId?: string; repo?: string; per_page?: number; limit?: number; runId?: string }) => {
      const target = repo || accountId || "github-primary";
      const targetUrl = repoUrlFor(accountId, repo);
      const deny = assertRepoReadAccess("github.actions_op", target, targetUrl);
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };

      try {
        if (action === "list_runs") {
          const runs = await getWorkflowRuns(target, resolvePerPage(per_page, limit));
          return { content: [{ type: "text", text: JSON.stringify(runs, null, 2) }], structuredContent: describeTarget(targetUrl) };
        }
        if (action === "get_failed_logs") {
          if (!runId) {
            return { isError: true, content: [{ type: "text", text: "Error: 'runId' is required for get_failed_logs" }] };
          }
          const logs = await getFailedLogs(target, runId);
          return { content: [{ type: "text", text: JSON.stringify(logs, null, 2) }], structuredContent: describeTarget(targetUrl) };
        }
        return { isError: true, content: [{ type: "text", text: `Unknown action: ${action}` }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.registerTool(
    "github.workflow_runs",
    {
      description: "List recent GitHub Actions workflow runs for any repository across Supremeai-bd.",
      annotations: { readOnlyHint: true, idempotentHint: true },
      inputSchema: {
        accountId: z.string().optional().describe("The account ID (e.g. 'github-primary')"),
        repo: z.string().optional().describe("Target repository name (e.g. 'supremeai-open', 'supremeai-skills') or 'Supremeai-bd/<repo>'" + repoDefaultNote()),
        per_page: z.number().int().min(1).max(100).optional().describe(
          "GitHub-REST page-size, fully honored (#2614 live-verified): precedence per_page ?? limit ?? default 5, clamped to GitHub's 1..100 envelope. A 5-row response means params were dropped (e.g. camelCase perPage), not a page-lock — re-probe with per_page=100 before filing an outage"),
        limit: z.number().optional().describe("Number of runs to fetch (default: 5)"),
      },
      outputSchema: targetEchoSchema,
    },
    async ({ accountId, repo, per_page, limit }) => {
      const target = repo || accountId || "github-primary";
      const targetUrl = repoUrlFor(accountId, repo);
      const deny = assertRepoReadAccess("github.workflow_runs", target, targetUrl);
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const runs = await getWorkflowRuns(target, resolvePerPage(per_page, limit));
        return {
          content: [{ type: "text", text: JSON.stringify(runs, null, 2) }],
          structuredContent: describeTarget(targetUrl),
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.registerTool(
    "github.get_failed_logs",
    {
      description: "Get trailing logs for failed jobs in a workflow run for any repository across Supremeai-bd.",
      annotations: { readOnlyHint: true, idempotentHint: true },
      inputSchema: {
        accountId: z.string().optional().describe("The account ID (e.g. 'github-primary')"),
        repo: z.string().optional().describe("Target repository name (e.g. 'supremeai-open', 'supremeai-skills') or 'Supremeai-bd/<repo>'" + repoDefaultNote()),
        runId: z.string().describe("The GitHub Actions run ID"),
      },
      outputSchema: targetEchoSchema,
    },
    async ({ accountId, repo, runId }) => {
      const target = repo || accountId || "github-primary";
      const targetUrl = repoUrlFor(accountId, repo);
      const deny = assertRepoReadAccess("github.get_failed_logs", target, targetUrl);
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const logs = await getFailedLogs(target, runId);
        return {
          content: [{ type: "text", text: JSON.stringify(logs, null, 2) }],
          structuredContent: describeTarget(targetUrl),
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.registerTool(
    "github.list_secrets",
    {
      description: "List GitHub Actions secret names for any repository across Supremeai-bd (names only).",
      annotations: { readOnlyHint: true, idempotentHint: true },
      inputSchema: {
        accountId: z.string().optional().describe("The account ID (e.g. 'github-primary')"),
        repo: z.string().optional().describe("Target repository name (e.g. 'supremeai-open', 'supremeai-skills') or 'Supremeai-bd/<repo>'" + repoDefaultNote()),
      },
      outputSchema: targetEchoSchema,
    },
    async ({ accountId, repo }) => {
      const target = repo || accountId || "github-primary";
      const targetUrl = repoUrlFor(accountId, repo);
      const deny = assertRepoReadAccess("github.list_secrets", target, targetUrl);
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const secrets = await listSecrets(target);
        return {
          content: [{ type: "text", text: JSON.stringify(secrets, null, 2) }],
          structuredContent: describeTarget(targetUrl),
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.registerTool(
    "github.read_file",
    {
      description: "Read the content of any file from any repository across the organization (Read-Only).",
      annotations: { readOnlyHint: true, idempotentHint: true },
      inputSchema: {
        accountId: z.string().optional().describe("The account ID (e.g. 'github-primary')"),
        repo: z.string().optional().describe("Target repository name (e.g. 'supremeai-open', 'supremeai-skills', 'supremeai-command') or 'Supremeai-bd/<repo>'" + repoDefaultNote()),
        path: z.string().describe("Relative path to the file (e.g. 'package.json', 'backend/main.py')"),
        ref: z.string().optional().describe("Branch, tag or commit SHA (default: 'main')"),
      },
      outputSchema: targetEchoSchema,
    },
    async ({ accountId, repo, path, ref }) => {
      const target = repo || accountId || "github-primary";
      const targetUrl = repoUrlFor(accountId, repo);
      const deny = assertRepoReadAccess("github.read_file", target, targetUrl, path);
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const fileData = await readFile(target, path, ref ?? "main");
        return {
          content: [{ type: "text", text: JSON.stringify(fileData, null, 2) }],
          structuredContent: describeTarget(targetUrl),
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.registerTool(
    "github.list_prs",
    {
      description: "List pull requests for any repository across Supremeai-bd (Read-Only).",
      annotations: { readOnlyHint: true, idempotentHint: true },
      inputSchema: {
        accountId: z.string().optional().describe("The account ID (e.g. 'github-primary')"),
        repo: z.string().optional().describe("Target repository name (e.g. 'supremeai-open', 'supremeai-skills') or 'Supremeai-bd/<repo>'" + repoDefaultNote()),
        state: z.enum(["open", "closed", "all"]).optional().describe("PR state (default: 'open')"),
        per_page: z.number().int().min(1).max(100).optional().describe(
          "GitHub-REST page-size, fully honored (#2614 live-verified): precedence per_page ?? limit ?? default 5, clamped to GitHub's 1..100 envelope. A 5-row response means params were dropped (e.g. camelCase perPage), not a page-lock — re-probe with per_page=100 before filing an outage"),
        limit: z.number().optional().describe("Max number of PRs (default: 5)"),
      },
      outputSchema: targetEchoSchema,
    },
    async ({ accountId, repo, state, per_page, limit }) => {
      const target = repo || accountId || "github-primary";
      const targetUrl = repoUrlFor(accountId, repo);
      const deny = assertRepoReadAccess("github.list_prs", target, targetUrl);
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const prs = await listPullRequests(target, state ?? "open", resolvePerPage(per_page, limit));
        return {
          content: [{ type: "text", text: JSON.stringify(prs, null, 2) }],
          structuredContent: describeTarget(targetUrl),
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.registerTool(
    "github.code_search",
    {
      description: "Search code across Supremeai-bd repositories (Read-Only). Useful for finding method/type references without manual tree traversal.",
      annotations: { readOnlyHint: true, idempotentHint: true },
      inputSchema: {
        query: z.string().describe("Search query (code terms, symbol names, etc.)"),
        repo: z.string().optional().describe("Optional target repo (e.g. 'supremeai-open'); omit to search the whole org"),
        limit: z.number().int().min(1).max(30).optional().describe("Max results (default: 10)"),
      },
      outputSchema: targetEchoSearchSchema,
    },
    async ({ query, repo, limit }) => {
      let echo: { targetRepo: string | null; targetUrl: string | null } = { targetRepo: null, targetUrl: null };
      if (repo) {
        const targetUrl = repoUrlFor(undefined, repo);
        const deny = assertRepoReadAccess("github.code_search", repo, targetUrl);
        if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
        echo = describeTarget(targetUrl);
      }
      try {
        const results = await searchCode(query, repo, limit ?? 10);
        return { content: [{ type: "text", text: JSON.stringify(results, null, 2) }], structuredContent: echo };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  // Alias for clients expecting the alternate name.
  server.registerTool(
    "github.search_code",
    {
      description: "Alias of github.code_search — search code across Supremeai-bd repositories (Read-Only).",
      annotations: { readOnlyHint: true, idempotentHint: true },
      inputSchema: {
        query: z.string().describe("Search query (code terms, symbol names, etc.)"),
        repo: z.string().optional().describe("Optional target repo (e.g. 'supremeai-open'); omit to search the whole org"),
        limit: z.number().int().min(1).max(30).optional().describe("Max results (default: 10)"),
      },
      outputSchema: targetEchoSearchSchema,
    },
    async ({ query, repo, limit }) => {
      let echo: { targetRepo: string | null; targetUrl: string | null } = { targetRepo: null, targetUrl: null };
      if (repo) {
        const targetUrl = repoUrlFor(undefined, repo);
        const deny = assertRepoReadAccess("github.search_code", repo, targetUrl);
        if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
        echo = describeTarget(targetUrl);
      }
      try {
        const results = await searchCode(query, repo, limit ?? 10);
        return { content: [{ type: "text", text: JSON.stringify(results, null, 2) }], structuredContent: echo };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.registerTool(
    "github.create_issue",
    {
      description: "Create a new issue in a SupremeAI repository (e.g. supremeai-open). Zero-credential self-serve for autonomous auditor/scout agents.",
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
      inputSchema: {
        title: z.string().min(5).max(250).describe("Issue title"),
        body: z.string().min(10).describe("Issue description / markdown body"),
        repo: z.string().optional().describe("Repository name (default: supremeai-open)"),
        labels: z.array(z.string()).optional().describe("Labels to apply (e.g. ['audit:finding', 'P1-major', 'status:unclaimed'])"),
      },
      outputSchema: targetEchoSchema,
    },
    async ({ title, body, repo, labels }) => {
      const targetRepo = repo || "supremeai-open";
      try {
        const result = await createIssue(targetRepo, title, body, labels);
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  success: true,
                  number: result.number,
                  url: result.htmlUrl,
                  title: result.title,
                  repo: targetRepo,
                },
                null,
                2
              ),
            },
          ],
          structuredContent: describeTarget(repoUrlFor(undefined, targetRepo)),
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );
}

