import { httpRequest } from "../../lib/http.js";
import { checkLicense } from "../../lib/source/licenses.js";
import { decideFile, estimateTokens, TokenBudget, DEFAULT_BUDGET } from "../../lib/source/filters.js";

/**
 * External Open Source Adapter.
 * Читает ЛЮБОЙ публичный GitHub репозиторий по owner/repo
 * с license-check и noise-filter. НЕ привязан к собственному репозиторию.
 */

function token(): string {
  return process.env.GITHUB_TOKEN || process.env.GH_TOKEN || process.env.GITHUB_API_TOKEN || "";
}

function ghHeaders(withAuth = true) {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "SupremeAI-MCP-Control-Tower",
  };
  if (withAuth && token()) headers.Authorization = `Bearer ${token()}`;
  return headers;
}

export interface RepoRef {
  owner: string;
  repo: string;
  ref?: string;
}

export function parseRepoRef(input: string): RepoRef {
  const value = input.trim();
  if (!value.includes("/")) {
    throw new Error("Invalid repo reference. Use 'owner/repo' or 'owner/repo/branch'");
  }
  const parts = value.split("/");
  const owner = parts[0];
  const repo = parts[1]?.replace(/\.git$/, "");
  const ref = parts.slice(2).join("/") || "main";
  if (!owner || !repo) throw new Error("Invalid repo reference. Use 'owner/repo'");
  if (!/^[a-zA-Z0-9_.-]+$/.test(owner) || !/^[a-zA-Z0-9_.-]+$/.test(repo)) {
    throw new Error("Invalid owner/repo characters");
  }
  return { owner, repo, ref };
}

export async function getRepoInfo(ref: RepoRef): Promise<{
  owner: string;
  repo: string;
  stars: number;
  forks: number;
  licenseVerdict: ReturnType<typeof checkLicense>;
  defaultBranch: string;
  description: string;
}> {
  const url = `https://api.github.com/repos/${ref.owner}/${ref.repo}`;
  const res = await httpRequest(url, { headers: ghHeaders(), timeoutMs: 10_000 });
  const data = res.data as any;
  if (!res.ok || data?.message) {
    throw new Error(`Repo not found or access denied: ${ref.owner}/${ref.repo} (${data?.message || res.status})`);
  }
  const spdx = data.license?.spdx_id || data.license?.key || "";
  return {
    owner: ref.owner,
    repo: ref.repo,
    stars: data.stargazers_count ?? 0,
    forks: data.forks_count ?? 0,
    licenseVerdict: checkLicense(spdx, `${ref.owner}/${ref.repo}`),
    defaultBranch: data.default_branch ?? "main",
    description: data.description || "",
  };
}

export async function searchRepos(query: string, sort: "stars" | "forks" | "updated" = "stars", limit = 10): Promise<unknown> {
  if (!query?.trim()) throw new Error("query is required");
  const url = `https://api.github.com/search/repositories?q=${encodeURIComponent(query)}&sort=${sort}&order=desc&per_page=${Math.min(Math.max(1, limit), 50)}`;
  const res = await httpRequest(url, { headers: ghHeaders(), timeoutMs: 10_000 });
  const data = res.data as any;
  return data?.items || [];
}

export async function getRepoTree(ref: RepoRef, maxFiles = 30): Promise<unknown> {
  const info = await getRepoInfo(ref);
  const branch = ref.ref || info.defaultBranch;
  const treeUrl = `https://api.github.com/repos/${ref.owner}/${ref.repo}/git/trees/${branch}?recursive=1`;
  const res = await httpRequest(treeUrl, { headers: ghHeaders(), timeoutMs: 15_000 });
  const data = res.data as any;
  if (!res.ok) throw new Error(`Failed to get tree: ${data?.message || res.status}`);

  const files = (data.tree || [])
    .filter((item: any) => item.type === "blob")
    .map((item: any) => ({
      path: item.path,
      size: item.size ?? 0,
      decision: decideFile(item.path, item.size ?? 0),
    }))
    .filter((f: any) => f.decision.shouldScrape)
    .sort((a: any, b: any) => b.decision.priority - a.decision.priority)
    .slice(0, Math.min(maxFiles, DEFAULT_BUDGET.maxFilesPerRepo));

  return {
    owner: ref.owner,
    repo: ref.repo,
    branch,
    defaultBranch: info.defaultBranch,
    stars: info.stars,
    license: info.licenseVerdict,
    totalFilesInTree: (data.tree || []).filter((i: any) => i.type === "blob").length,
    selectedFiles: files.length,
    files: files.map((f: any) => ({ path: f.path, size: f.size, priority: f.decision.priority })),
    budget: DEFAULT_BUDGET,
  };
}

export async function readExternalFile(ref: RepoRef, path: string): Promise<unknown> {
  if (!path?.trim()) throw new Error("path is required");
  const info = await getRepoInfo(ref);
  const branch = ref.ref || info.defaultBranch;

  if (info.licenseVerdict.tier === "reject") {
    throw new Error(
      `License guard: repo ${ref.owner}/${ref.repo} has license '${info.licenseVerdict.license}' (${info.licenseVerdict.reason}) — file not fetched.`
    );
  }

  const fileUrl = `https://api.github.com/repos/${ref.owner}/${ref.repo}/contents/${path}?ref=${encodeURIComponent(branch)}`;
  const res = await httpRequest(fileUrl, { headers: ghHeaders(), timeoutMs: 10_000 });
  const data = res.data as any;
  if (!res.ok) {
    throw new Error(`Failed to read ${path}: ${data?.message || res.status}`);
  }

  let content = "";
  if (data.content && data.encoding === "base64") {
    content = Buffer.from(data.content, "base64").toString("utf-8");
  } else if (typeof data === "string") {
    content = data;
  } else if (Array.isArray(data)) {
    return { path, isDirectory: true, entries: data.map((e: any) => ({ name: e.name, path: e.path, type: e.type })) };
  }

  const decision = decideFile(path, data.size ?? 0);
  const tokens = estimateTokens(content);
  return {
    path: data.path,
    sha: data.sha,
    size: data.size,
    tokens,
    decision,
    license: info.licenseVerdict,
    stars: info.stars,
    defaultBranch: info.defaultBranch,
    content: decision.shouldScrape ? content : content.slice(0, 2000) + "\n... [truncated by noise filter]",
  };
}

/** Коллекция приоритетных файлов репозитория с общим бюджетом токенов. */
export async function collectRepoHighlights(ref: RepoRef, maxFiles = 10): Promise<unknown> {

  const info = await getRepoInfo(ref);
  if (info.licenseVerdict.tier === "reject") {
    return { error: "License guard blocked repo extraction", license: info.licenseVerdict };
  }
  const branch = ref.ref || info.defaultBranch;
  const treeUrl = `https://api.github.com/repos/${ref.owner}/${ref.repo}/git/trees/${branch}?recursive=1`;
  const res = await httpRequest(treeUrl, { headers: ghHeaders(), timeoutMs: 15_000 });
  const data = res.data as any;
  const blobItems = (data.tree || []).filter((i: any) => i.type === "blob");
  const considered = blobItems
    .map((item: any) => ({ path: item.path, size: item.size ?? 0, decision: decideFile(item.path, item.size ?? 0) }))
    .filter((f: any) => f.decision.shouldScrape)
    .sort((a: any, b: any) => b.decision.priority - a.decision.priority)
    .slice(0, Math.min(maxFiles, 20));

  const budget = new TokenBudget();
  const collected: unknown[] = [];
  for (const file of considered) {
    try {
      const fileRes = await readExternalFile({ owner: ref.owner, repo: ref.repo, ref: branch }, file.path);
      const fileData = fileRes as any;
      const tokens = estimateTokens(fileData.content || "");
      if (!budget.canAdd(tokens)) break;
      budget.add(tokens);
      collected.push({ path: file.path, size: file.size, tokens, content: (fileData.content || "").slice(0, 4000) });
    } catch {
      continue;
    }
  }

  return {
    owner: ref.owner,
    repo: ref.repo,
    branch,
    stars: info.stars,
    license: info.licenseVerdict,
    filesCount: collected.length,
    tokenBudgetUsed: budget.used,
    files: collected,
  };
}