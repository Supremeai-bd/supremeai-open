/**
 * PR Guardian — GitHub REST evidence + review-action client.
 *
 * Reuses the existing GitHub account resolver (`getAccountConfig`) so tokens and
 * the repository base URL come from the same account registry as every other
 * GitHub tool. No second credential path is introduced.
 */

import { getAccountConfig, githubHeaders } from "../adapters/github/index.js";
import { httpRequest } from "../lib/http.js";

export interface PullRequestEvidence {
  number: number;
  title: string;
  body: string | null;
  author: string;
  state: string;
  draft: boolean;
  htmlUrl: string;
  headRef: string;
  headSha: string;
  baseRef: string;
  baseSha: string;
  mergeableState: string;
  /** GitHub can return null while it computes mergeability. */
  mergeable: boolean | null;
  changedFiles: number;
  additions: number;
  deletions: number;
  labels: string[];
}

export interface PullRequestFileEvidence {
  filename: string;
  status: string;
  additions: number;
  deletions: number;
  patch?: string;
}

export interface CheckRunEvidence {
  name: string;
  status: string;
  conclusion: string | null;
  startedAt: string | null;
  completedAt: string | null;
  htmlUrl: string | null;
}

export class GitHubGuardianClient {
  constructor(private readonly accountId: string) {}

  private resolve(): { token: string; apiBase: string; repoSlug: string } {
    const { apiKey, baseUrl } = getAccountConfig(this.accountId);
    const repoSlug = baseUrl.replace(/^https?:\/\/api\.github\.com\/repos\//, "").replace(/\/+$/, "");
    return { token: apiKey, apiBase: baseUrl.replace(/\/+$/, ""), repoSlug };
  }

  private async request<T>(
    path: string,
    method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE" = "GET",
    body?: unknown,
  ): Promise<T> {
    const { token, apiBase } = this.resolve();
    const res = await httpRequest<T>(`${apiBase}${path}`, {
      method,
      headers: githubHeaders(token),
      body,
      timeoutMs: 20_000,
      retries: 1,
    });
    if (!res.ok) {
      const detail = typeof res.data === "string" ? res.data.slice(0, 400) : JSON.stringify(res.data).slice(0, 400);
      throw new Error(`GitHub ${method} ${path} failed (${res.status}): ${detail}`);
    }
    return res.data;
  }

  /** Repository slug, e.g. `owner/name`. */
  public repo(): string {
    return this.resolve().repoSlug;
  }

  /** List open pull requests (most recently updated first). */
  async listOpenPullRequests(limit = 20): Promise<PullRequestEvidence[]> {
    const prs = await this.request<any[]>(`/pulls?state=open&sort=updated&direction=desc&per_page=${Math.min(100, Math.max(1, limit))}`);
    return (prs ?? []).map((pr) => ({
      number: pr.number,
      title: pr.title,
      body: pr.body ?? null,
      author: pr.user?.login ?? "unknown",
      state: pr.state,
      draft: Boolean(pr.draft),
      htmlUrl: pr.html_url,
      headRef: pr.head?.ref ?? "",
      headSha: pr.head?.sha ?? "",
      baseRef: pr.base?.ref ?? "",
      baseSha: pr.base?.sha ?? "",
      mergeableState: pr.mergeable_state ?? "unknown",
      mergeable: typeof pr.mergeable === "boolean" ? pr.mergeable : null,
      changedFiles: pr.changed_files ?? 0,
      additions: pr.additions ?? 0,
      deletions: pr.deletions ?? 0,
      labels: Array.isArray(pr.labels) ? pr.labels.map((l: any) => l?.name ?? "") : [],
    }));
  }

  async getPullRequest(prNumber: number): Promise<PullRequestEvidence> {
    const pr = await this.request<any>(`/pulls/${prNumber}`);
    return {
      number: pr.number,
      title: pr.title,
      body: pr.body ?? null,
      author: pr.user?.login ?? "unknown",
      state: pr.state,
      draft: Boolean(pr.draft),
      htmlUrl: pr.html_url,
      headRef: pr.head?.ref ?? "",
      headSha: pr.head?.sha ?? "",
      baseRef: pr.base?.ref ?? "",
      baseSha: pr.base?.sha ?? "",
      mergeableState: pr.mergeable_state ?? "unknown",
      mergeable: typeof pr.mergeable === "boolean" ? pr.mergeable : null,
      changedFiles: pr.changed_files ?? 0,
      additions: pr.additions ?? 0,
      deletions: pr.deletions ?? 0,
      labels: Array.isArray(pr.labels) ? pr.labels.map((l: any) => l?.name ?? "") : [],
    };
  }

  async getPullRequestFiles(prNumber: number): Promise<PullRequestFileEvidence[]> {
    const files = await this.request<any[]>(`/pulls/${prNumber}/files?per_page=100`);
    return (files ?? []).map((f) => ({
      filename: f.filename,
      status: f.status,
      additions: f.additions ?? 0,
      deletions: f.deletions ?? 0,
      patch: typeof f.patch === "string" ? f.patch : undefined,
    }));
  }

  /**
   * Check runs for a commit. Best-effort: callers must tolerate failures so a
   * PR can still be judged on non-CI evidence (per the merge policy, CI status
   * is evidence — not the gate).
   */
  async getCheckRuns(ref: string): Promise<CheckRunEvidence[]> {
    const payload = await this.request<any>(`/commits/${ref}/check-runs?per_page=100`);
    const runs = payload?.check_runs ?? [];
    return runs.map((r: any) => ({
      name: r.name ?? "unnamed",
      status: r.status ?? "unknown",
      conclusion: r.conclusion ?? null,
      startedAt: r.started_at ?? null,
      completedAt: r.completed_at ?? null,
      htmlUrl: r.html_url ?? null,
    }));
  }

  /** Merge the PR. `method` follows GitHub semantics (merge | squash | rebase). */
  async mergePullRequest(
    prNumber: number,
    method: "merge" | "squash" | "rebase" = "squash",
    commitTitle?: string,
  ): Promise<{ merged: boolean; message: string; sha?: string }> {
    const payload = await this.request<any>(`/pulls/${prNumber}/merge`, "PUT", {
      merge_method: method,
      ...(commitTitle ? { commit_title: commitTitle } : {}),
    });
    return { merged: Boolean(payload?.merged), message: payload?.message ?? "", sha: payload?.sha };
  }

  /** Close the PR without merging (reversible: GitHub keeps the branch). */
  async closePullRequest(prNumber: number): Promise<void> {
    await this.request<any>(`/pulls/${prNumber}`, "PATCH", { state: "closed" });
  }

  /** Post an explanatory comment carrying the Guardian evidence. */
  async comment(prNumber: number, body: string): Promise<{ id: number; url: string }> {
    const payload = await this.request<any>(`/issues/${prNumber}/comments`, "POST", { body });
    return { id: payload?.id ?? 0, url: payload?.html_url ?? "" };
  }
}