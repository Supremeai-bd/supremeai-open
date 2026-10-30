import { buildAccountRegistry } from "../../registry/account.registry.js";
import { httpRequest, bearerAuth } from "../../lib/http.js";
import { pullsEndpoint, pullsQuery } from "../../lib/github_pagination.js";

const DEFAULT_BASE_URL = "https://api.github.com/repos/Supremeai-bd/supremeai";

export function getAccountConfig(accountIdOrRepo?: string): { apiKey: string; baseUrl: string } {
  const target = accountIdOrRepo || "github-primary";
  const accounts = buildAccountRegistry();
  const account = accounts.find((a) => (a.id === target || a.displayName.includes(`/${target})`)) && a.provider === "github");

  // বাংলা (Task 35): vault-থেকে-লোড-হওয়া PAT-ও ফলব্যাক-চেইনে রাখা হলো —
  // যাতে মূল personal account-এর (org-migration-এর আগের) প্রতিটি রিপো-অ্যাকাউন্ট GITHUB_PAT_PAYKARIBAZARONLINE
  // দিয়েই সক্রিয় হয় (Infisical pullSecretsIntoProcessEnv() রানটাইমে এটি ভরে)।
  const apiKey =
    (account ? process.env[account.apiKeyRef] : "") ||
    process.env.GITHUB_PAT_PAYKARIBAZARONLINE ||
    process.env.GITHUB_TOKEN ||
    process.env.GH_TOKEN ||
    "";
  if (!apiKey) throw new Error(`Missing GitHub Token in env for target: ${target}`);

  let baseUrl = account?.url;
  if (!baseUrl) {
    const cleanRepo = target.replace(/^github-pay-/, "").replace(/^Supremeai-bd\//i, "");
    baseUrl = `https://api.github.com/repos/Supremeai-bd/${cleanRepo}`;
  }
  return { apiKey, baseUrl };
}

export function githubHeaders(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "SupremeAI-MCP-Control-Tower",
  };
}

export async function getWorkflowRuns(accountId: string, limit = 5): Promise<unknown> {
  const { apiKey: token, baseUrl } = getAccountConfig(accountId);
  const res = await httpRequest(`${baseUrl}/actions/runs?per_page=${limit}`, {
    headers: githubHeaders(token),
  });
  return res.data;
}

export async function getFailedLogs(accountId: string, runId: string): Promise<unknown> {
  const { apiKey: token, baseUrl } = getAccountConfig(accountId);
  // Get jobs for the run
  const jobsRes = await httpRequest(`${baseUrl}/actions/runs/${runId}/jobs`, {
    headers: githubHeaders(token),
  });
  
  const jobs = (jobsRes.data as any).jobs || [];
  const failedJobs = jobs.filter((j: any) => j.conclusion === "failure");

  if (failedJobs.length === 0) {
    return { message: "No failed jobs found for this run.", jobs };
  }

  // To get actual raw logs for a job, you hit /actions/jobs/{job_id}/logs
  const failedJobLogs = await Promise.allSettled(
    failedJobs.map(async (job: any) => {
      try {
        const logRes = await fetch(`${baseUrl}/actions/jobs/${job.id}/logs`, {
          headers: githubHeaders(token),
          redirect: 'follow'
        });
        if (!logRes.ok) throw new Error(`Failed to fetch logs: ${logRes.status}`);
        const logText = await logRes.text();
        // Return only the last 2000 characters of the log to prevent massive payloads
        const snippet = logText.slice(-2000);
        return { jobName: job.name, logsSnippet: snippet };
      } catch (e) {
        return { jobName: job.name, error: (e as Error).message };
      }
    })
  );

  return {
    runId,
    failedJobs: failedJobLogs.map(r => r.status === 'fulfilled' ? r.value : r.reason),
  };
}

export async function listSecrets(accountId: string): Promise<unknown> {
  const { apiKey: token, baseUrl } = getAccountConfig(accountId);
  const res = await httpRequest(`${baseUrl}/actions/secrets`, {
    headers: githubHeaders(token),
  });
  // GitHub returns only secret names, not values!
  return res.data;
}

export async function readFile(accountId: string, path: string, ref: string = "main"): Promise<unknown> {
  const { apiKey: token, baseUrl } = getAccountConfig(accountId);
  const res = await httpRequest(`${baseUrl}/contents/${path}?ref=${ref}`, {
    headers: githubHeaders(token),
  });
  const data = res.data as any;
  if (data.content && data.encoding === "base64") {
    const decoded = Buffer.from(data.content, "base64").toString("utf-8");
    return {
      path: data.path,
      size: data.size,
      sha: data.sha,
      content: decoded,
    };
  }
  return data;
}

export async function searchCode(query: string, repo?: string, limit: number = 10): Promise<unknown> {
  const { apiKey: token } = getAccountConfig(repo || "github-primary");
  const q = repo
    ? `${query} repo:Supremeai-bd/${repo.replace(/^Supremeai-bd\//i, "")}`
    : `${query} org:Supremeai-bd`;
  const res = await httpRequest(
    `https://api.github.com/search/code?q=${encodeURIComponent(q)}&per_page=${Math.min(limit, 30)}`,
    { headers: githubHeaders(token) },
  );
  if (!res.ok) {
    const msg =
      res.data && typeof res.data === "object" && "message" in (res.data as Record<string, unknown>)
        ? String((res.data as Record<string, unknown>).message)
        : `HTTP ${res.status}`;
    throw new Error(`GitHub code search error: ${msg}`);
  }
  const data = res.data as any;
  const items = Array.isArray(data?.items) ? data.items : [];
  return items.map((item: any) => ({
    path: item.path,
    repository: item.repository?.full_name,
    url: item.html_url,
    score: item.score,
  }));
}

export const codeSearch = searchCode;

export async function listPullRequests(
  accountId: string,
  state: string = "open",
  limit: number = 5,
  opts?: { pullNumber?: number; sort?: string; direction?: string },
): Promise<unknown> {
  const { apiKey: token, baseUrl } = getAccountConfig(accountId);
  // #3368 / R81: single-PR addressability — the creation-ordered window
  // cannot answer "state of PR N" for any PR outside the newest ~100
  // ranks; REST GET /pulls/{number} can, at any rank (state/merged/
  // merged_at/closed_at — exactly the verdict-plane fields the #2567-class
  // re-verifications needed). pullNumber overrides the list knobs entirely.
  if (opts?.pullNumber !== undefined && opts.pullNumber !== null) {
    const res = await httpRequest(pullsEndpoint(baseUrl, opts.pullNumber), {
      headers: githubHeaders(token),
    });
    if (!res.ok || typeof res.data !== "object" || res.data === null) {
      const errorMsg =
        res.data && typeof res.data === "object" && "message" in (res.data as Record<string, unknown>)
          ? String((res.data as Record<string, unknown>).message)
          : `Failed to fetch PR #${opts.pullNumber} (HTTP ${res.status})`;
      throw new Error(`GitHub API error: ${errorMsg}`);
    }
    const pr = res.data as any;
    return [{
      number: pr.number,
      title: pr.title,
      state: pr.state,
      merged: pr.merged,
      mergedAt: pr.merged_at,
      closedAt: pr.closed_at,
      user: pr.user?.login,
      htmlUrl: pr.html_url,
      createdAt: pr.created_at,
      updatedAt: pr.updated_at,
    }];
  }
  const res = await httpRequest(`${baseUrl}/pulls?${pullsQuery(state, limit, opts?.sort, opts?.direction)}`, {
    headers: githubHeaders(token),
  });
  if (!res.ok || !Array.isArray(res.data)) {
    const errorMsg =
      res.data && typeof res.data === "object" && "message" in (res.data as Record<string, unknown>)
        ? String((res.data as Record<string, unknown>).message)
        : `Failed to list PRs (HTTP ${res.status})`;
    throw new Error(`GitHub API error: ${errorMsg}`);
  }
  const prs = res.data as any[];
  return prs.map((pr: any) => ({
    number: pr.number,
    title: pr.title,
    state: pr.state,
    merged: pr.merged,
    mergedAt: pr.merged_at,
    user: pr.user?.login,
    htmlUrl: pr.html_url,
    createdAt: pr.created_at,
    updatedAt: pr.updated_at,
  }));
}

export async function createIssue(
  accountIdOrRepo: string,
  title: string,
  body: string,
  labels?: string[]
): Promise<{ number: number; htmlUrl: string; title: string }> {
  const { apiKey: token, baseUrl } = getAccountConfig(accountIdOrRepo);
  const res = await httpRequest<{ number?: number; html_url?: string; message?: string }>(`${baseUrl}/issues`, {
    method: "POST",
    headers: {
      ...githubHeaders(token),
      "Content-Type": "application/json",
    },
    body: {
      title,
      body,
      ...(labels && labels.length > 0 ? { labels } : {}),
    },
    timeoutMs: 15_000,
  });

  if (!res.ok || !res.data?.number) {
    const errorMsg = res.data?.message || `Failed to create issue (HTTP ${res.status})`;
    throw new Error(`GitHub create issue error: ${errorMsg}`);
  }

  return {
    number: res.data.number,
    htmlUrl: res.data.html_url || "",
    title,
  };
}

