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
const SATELLITE_REPOS: ReadonlySet<string> = new Set([
  "supremeai-api",
  "supremeai-open",
  "supremeai-sdk",
  "supremeai-archive",
  "supremeai-core",
  "supremeai-studio",
  "supremeai-infrastructure",
  "supremeai-mcp-control-plane",
]);

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
  if (access === "satellite-readonly" && !SATELLITE_REPOS.has(shortName)) {
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

/** Resolves the account's repo base URL exactly as the adapter does (no I/O). */
function repoUrlFor(accountId: string): string {
  try {
    // বাংলা মন্তব্য: অ্যাকাউন্ট রেজিস্ট্রি থেকে baseUrl নেওয়া হয় — অ্যাডাপ্টারের সাথে একই উৎস, কোনো নেটওয়ার্ক I/O নেই।
    const account = buildAccountRegistry().find((a) => a.id === accountId && a.provider === "github");
    return account?.url || "https://api.github.com/repos/Supremeai-bd/supremeai";
  } catch {
    return "https://api.github.com/repos/Supremeai-bd/supremeai";
  }
}

export async function registerGitHubTools(server: McpServer): Promise<void> {
  server.tool(
    "github.workflow_runs",
    "List recent GitHub Actions workflow runs for the repository.",
    {
      accountId: z.string().describe("The account ID (e.g. github-primary)"),
      limit: z.number().optional().describe("Number of runs to fetch (default: 5)"),
    },
    async ({ accountId, limit }) => {
      // #110: repo-isolation gate — read-only tiers respect the allowlist.
      const deny = assertRepoReadAccess("github.workflow_runs", accountId, repoUrlFor(accountId));
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const runs = await getWorkflowRuns(accountId, limit || 5);
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
    "Get the trailing logs for any failed jobs in a specific workflow run.",
    {
      accountId: z.string().describe("The account ID (e.g. github-primary)"),
      runId: z.string().describe("The GitHub Actions run ID"),
    },
    async ({ accountId, runId }) => {
      // #110: repo-isolation gate.
      const deny = assertRepoReadAccess("github.get_failed_logs", accountId, repoUrlFor(accountId));
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const logs = await getFailedLogs(accountId, runId);
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
    "List all GitHub Actions secrets configured for the repository (names only).",
    {
      accountId: z.string().describe("The account ID (e.g. github-primary)"),
    },
    async ({ accountId }) => {
      try {
        const secrets = await listSecrets(accountId);
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
    "Read the content of any file from the GitHub repository (Read-Only).",
    {
      accountId: z.string().describe("The account ID (e.g. github-primary)"),
      path: z.string().describe("Relative path to the file (e.g. 'backend/main.py')"),
      ref: z.string().optional().describe("Branch, tag or commit SHA (default: 'main')"),
    },
    async ({ accountId, path, ref }) => {
      // #110: repo-isolation gate (github.read_file — the issue's named tool).
      const deny = assertRepoReadAccess("github.read_file", accountId, repoUrlFor(accountId));
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const fileData = await readFile(accountId, path, ref ?? "main");
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
    "List pull requests for the repository (Read-Only).",
    {
      accountId: z.string().describe("The account ID (e.g. github-primary)"),
      state: z.enum(["open", "closed", "all"]).optional().describe("PR state (default: 'open')"),
      limit: z.number().optional().describe("Max number of PRs (default: 5)"),
    },
    async ({ accountId, state, limit }) => {
      // #110: repo-isolation gate.
      const deny = assertRepoReadAccess("github.list_prs", accountId, repoUrlFor(accountId));
      if (deny) return { isError: true, content: [{ type: "text", text: deny }] };
      try {
        const prs = await listPullRequests(accountId, state ?? "open", limit ?? 5);
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

