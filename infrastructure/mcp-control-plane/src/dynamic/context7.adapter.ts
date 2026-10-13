import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

/**
 * Context7 Documentation Adapter
 * Provides AI clients with up-to-date documentation for popular libraries and frameworks
 * Exposes docs as MCP resources for direct reading
 */

interface DocSource {
  name: string;
  url: string;
  description: string;
  category: string;
}

// Built-in documentation sources
const BUILTIN_DOC_SOURCES: DocSource[] = [
  { name: "supabase", url: "https://supabase.com/docs", description: "Supabase documentation", category: "database" },
  { name: "vercel", url: "https://vercel.com/docs", description: "Vercel deployment docs", category: "deployment" },
  { name: "render", url: "https://render.com/docs", description: "Render deployment docs", category: "deployment" },
  { name: "cloudflare", url: "https://developers.cloudflare.com", description: "Cloudflare developer docs", category: "infrastructure" },
  { name: "nextjs", url: "https://nextjs.org/docs", description: "Next.js framework docs", category: "framework" },
  { name: "fastapi", url: "https://fastapi.tiangolo.com", description: "FastAPI framework docs", category: "framework" },
  { name: "typescript", url: "https://www.typescriptlang.org/docs", description: "TypeScript documentation", category: "language" },
  { name: "python", url: "https://docs.python.org/3", description: "Python documentation", category: "language" },
];

/**
 * Register Context7 documentation tools and resources
 */
export async function registerContext7Adapter(server: McpServer): Promise<void> {
  // Documentation Search Tool
  server.tool(
    "docs.search",
    "Search across all documentation sources for a query. Returns relevant documentation snippets.",
    {
      query: z.string().describe("Search query"),
      source: z.string().optional().describe("Specific doc source to search"),
      limit: z.number().optional().describe("Max results to return"),
    },
    async ({ query, source, limit }) => {
      const results = await searchDocs(query, source, limit ?? 5);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(results, null, 2) }],
      };
    }
  );

  // Documentation Fetch Tool
  server.tool(
    "docs.fetch",
    "Fetch a specific documentation page by URL or topic",
    {
      url: z.string().describe("Full URL of the documentation page"),
      topic: z.string().optional().describe("Topic to fetch"),
    },
    async ({ url, topic }) => {
      const content = await fetchDocPage(url, topic);
      return {
        content: [{ type: "text" as const, text: content }],
      };
    }
  );

  // List Available Docs
  server.tool(
    "docs.list",
    "List all available documentation sources",
    {},
    async () => {
      return {
        content: [{
          type: "text" as const,
          text: JSON.stringify({
            sources: BUILTIN_DOC_SOURCES,
            count: BUILTIN_DOC_SOURCES.length,
            categories: [...new Set(BUILTIN_DOC_SOURCES.map(s => s.category))],
          }, null, 2),
        }],
      };
    }
  );

  // Documentation Resources
  for (const doc of BUILTIN_DOC_SOURCES) {
    server.resource(
      "docs://" + doc.name,
      "docs-" + doc.name,
      { description: doc.description, mimeType: "text/markdown" },
      async () => {
        return {
          contents: [{
            uri: "docs://" + doc.name,
            mimeType: "text/markdown",
            text: "# " + doc.name + "\n\n" + doc.description + "\n\nURL: " + doc.url + "\nCategory: " + doc.category,
          }],
        };
      }
    );
  }

  console.error("[MCP] Context7 Documentation Adapter registered");
}

async function searchDocs(query: string, source?: string, limit: number = 5): Promise<unknown[]> {
  const sources = source
    ? BUILTIN_DOC_SOURCES.filter(s => s.name.includes(source.toLowerCase()))
    : BUILTIN_DOC_SOURCES;

  return sources
    .filter(s =>
      s.name.toLowerCase().includes(query.toLowerCase()) ||
      s.description.toLowerCase().includes(query.toLowerCase()) ||
      s.category.toLowerCase().includes(query.toLowerCase())
    )
    .slice(0, limit)
    .map(s => ({
      name: s.name,
      url: s.url,
      description: s.description,
      category: s.category,
      relevance: calculateRelevance(query, s),
    }));
}

async function fetchDocPage(url: string, topic?: string): Promise<string> {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      return "Failed to fetch documentation: " + response.status + " " + response.statusText;
    }
    const text = await response.text();
    return text.substring(0, 5000) + (text.length > 5000 ? "\n\n... (truncated)" : "");
  } catch (error) {
    return "Error fetching documentation: " + String(error);
  }
}

function calculateRelevance(query: string, source: DocSource): number {
  const q = query.toLowerCase();
  let score = 0;
  if (source.name.toLowerCase().includes(q)) score += 0.5;
  if (source.description.toLowerCase().includes(q)) score += 0.3;
  if (source.category.toLowerCase().includes(q)) score += 0.2;
  return Math.min(score, 1);
}
