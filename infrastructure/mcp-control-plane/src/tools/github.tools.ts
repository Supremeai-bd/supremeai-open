import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { getWorkflowRuns, getFailedLogs, listSecrets, readFile, listPullRequests } from "../adapters/github/index.js";
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
  "supremeai-api",
  "supremeai-open",
  "supremeai-sdk",
  "supremeai-archive",
  "supremeai-core",
  "supremeai-studio",
  "supremeai-infrastructure",
  "supremeai-mcp-control-plane",
  "supremeai-command",
  "supremeai-skills",
  "supremeai-vscode",
  "supremeai-agents",
  "supremeai-browser",
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
export function assertRepoReadAccess(toolName: string, accountId: string, accountRepoUrl: string): string | null {
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
  if (access === "satellite-readonly" && (shortName === "supremeai" || !isSatelliteRepo(shortName))) {
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

export async function registerGitHubTools(server: McpServer): Promise<void> {
  server.tool(
    "github.workflow_runs",
    "List recent GitHub Actions workflow runs for any repository across Supremeai-bd.",
    {
      accountId: z.string().optional().describe("The account ID (e.g. 'github-primary')"),
      repo: z.string().optional().describe("Target repository name (e.g. 'supremeai-open', 'supremeai-skills') or 'Supremeai-bd/<repo>'"),
      limit: z.number().optional().describe("Number of runs to fetch (default: 5)"),
    },
    async ({ accountId, repo, limit }) => {
      const target = repo || accountId || "github-primary";
      const targetUrl = repoUrlFor(accountId, repo);
      const deny = assertRepoReadAccess("github.workflow_runs", target, targetUrl);
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const runs = await getWorkflowRuns(target, limit || 5);
        return {
          content: [{ type: "text", text: JSON.stringify(runs, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "github.get_failed_logs",
    "Get trailing logs for failed jobs in a workflow run for any repository across Supremeai-bd.",
    {
      accountId: z.string().optional().describe("The account ID (e.g. 'github-primary')"),
      repo: z.string().optional().describe("Target repository name (e.g. 'supremeai-open', 'supremeai-skills') or 'Supremeai-bd/<repo>'"),
      runId: z.string().describe("The GitHub Actions run ID"),
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
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "github.list_secrets",
    "List GitHub Actions secret names for any repository across Supremeai-bd (names only).",
    {
      accountId: z.string().optional().describe("The account ID (e.g. 'github-primary')"),
      repo: z.string().optional().describe("Target repository name (e.g. 'supremeai-open', 'supremeai-skills') or 'Supremeai-bd/<repo>'"),
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
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "github.read_file",
    "Read the content of any file from any repository across the organization (Read-Only).",
    {
      accountId: z.string().optional().describe("The account ID (e.g. 'github-primary')"),
      repo: z.string().optional().describe("Target repository name (e.g. 'supremeai-open', 'supremeai-skills', 'supremeai-command') or 'Supremeai-bd/<repo>'"),
      path: z.string().describe("Relative path to the file (e.g. 'package.json', 'backend/main.py')"),
      ref: z.string().optional().describe("Branch, tag or commit SHA (default: 'main')"),
    },
    async ({ accountId, repo, path, ref }) => {
      const target = repo || accountId || "github-primary";
      const targetUrl = repoUrlFor(accountId, repo);
      const deny = assertRepoReadAccess("github.read_file", target, targetUrl);
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const fileData = await readFile(target, path, ref ?? "main");
        return {
          content: [{ type: "text", text: JSON.stringify(fileData, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "github.list_prs",
    "List pull requests for any repository across Supremeai-bd (Read-Only).",
    {
      accountId: z.string().optional().describe("The account ID (e.g. 'github-primary')"),
      repo: z.string().optional().describe("Target repository name (e.g. 'supremeai-open', 'supremeai-skills') or 'Supremeai-bd/<repo>'"),
      state: z.enum(["open", "closed", "all"]).optional().describe("PR state (default: 'open')"),
      limit: z.number().optional().describe("Max number of PRs (default: 5)"),
    },
    async ({ accountId, repo, state, limit }) => {
      const target = repo || accountId || "github-primary";
      const targetUrl = repoUrlFor(accountId, repo);
      const deny = assertRepoReadAccess("github.list_prs", target, targetUrl);
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const prs = await listPullRequests(target, state ?? "open", limit ?? 5);
        return {
          content: [{ type: "text", text: JSON.stringify(prs, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );
}

