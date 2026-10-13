import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import {
  collectRepoHighlights,
  getRepoInfo,
  getRepoTree,
  parseRepoRef,
  readExternalFile,
  searchRepos,
} from "../adapters/github/external.js";
import { scrapeUrl } from "../adapters/firecrawl/actions.js";

/**
 * Open Source Collection Tools.
 * Сбор лучших практик из ЛЮБОГО публичного GitHub-репозитория
 * и веб-документации с license-check и noise-filter.
 */
export async function registerSourceTools(server: McpServer): Promise<void> {
  server.tool(
    "github.search_repos",
    "Search public GitHub repositories by topic/query, sorted by stars (default), forks, or updated.",
    {
      query: z.string().describe("Search query, e.g. 'react hooks library' or 'tailwindcss components'"),
      sort: z.enum(["stars", "forks", "updated"]).optional().describe("Sort order (default: stars)"),
      limit: z.number().int().min(1).max(50).optional().describe("Max results (default: 10)"),
    },
    async ({ query, sort, limit }) => {
      try {
        const result = await searchRepos(query, sort ?? "stars", limit ?? 10);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "github.repo_info",
    "Get metadata about any public repo: stars, forks, license verdict (MIT/Apache=accept, GPL=reject), default branch.",
    { repo: z.string().describe("Repo as owner/repo, e.g. 'vercel/next.js'") },
    async ({ repo }) => {
      try {
        const ref = parseRepoRef(repo);
        const info = await getRepoInfo(ref);
        return { content: [{ type: "text", text: JSON.stringify(info, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "github.repo_tree",
    "Get filtered directory tree of any public repo (noise removed: locks, builds, binaries). Ready for picking files.",
    {
      repo: z.string().describe("Repo as owner/repo, e.g. 'shadcn/ui'"),
      maxFiles: z.number().int().min(1).max(50).optional().describe("Max selected files (default: 30)"),
    },
    async ({ repo, maxFiles }) => {
      try {
        const ref = parseRepoRef(repo);
        const tree = await getRepoTree(ref, maxFiles ?? 30);
        return { content: [{ type: "text", text: JSON.stringify(tree, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "github.read_external_file",
    "Read a file from ANY public repo (not just ours). License guard blocks copyleft repos. Noise filter trims huge files.",
    {
      repo: z.string().describe("Repo as owner/repo, e.g. 'vercel/next.js'"),
      path: z.string().describe("File path inside the repo, e.g. 'packages/next/src/server/index.ts'"),
    },
    async ({ repo, path }) => {
      try {
        const ref = parseRepoRef(repo);
        const file = await readExternalFile(ref, path);
        return { content: [{ type: "text", text: JSON.stringify(file, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "github.collect_highlights",
    "Automatically pick the most valuable source files (cores, hooks, components, configs, README) from a repo, within a token budget. Ideal for AI analysis.",
    {
      repo: z.string().describe("Repo as owner/repo, e.g. 'sindresorhus/awesome'"),
      maxFiles: z.number().int().min(1).max(20).optional().describe("Max files (default: 10)"),
    },
    async ({ repo, maxFiles }) => {
      try {
        const ref = parseRepoRef(repo);
        const highlights = await collectRepoHighlights(ref, maxFiles ?? 10);
        return { content: [{ type: "text", text: JSON.stringify(highlights, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "firecrawl.scrape",
    "Scrape any web page (docs, guides, design-tokens, style guides) to markdown. Uses Firecrawl.",
    {
      url: z.string().url().describe("Full URL to scrape"),
      onlyMainContent: z.boolean().optional().describe("Strip nav/ads (default: true)"),
      maxTokens: z.number().int().min(100).max(20000).optional().describe("Output cap in tokens (default: 8000)"),
    },
    async ({ url, onlyMainContent, maxTokens }) => {
      try {
        const result = await scrapeUrl(url, {
          onlyMainContent: onlyMainContent ?? true,
          maxTokens: maxTokens ?? 8000,
        });
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );
}