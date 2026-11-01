import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

const GRAPHIFY_ENDPOINT = process.env.GRAPHIFY_ENDPOINT || "https://api.graphify.com/mcp";
const GRAPHIFY_TOKEN = process.env.GRAPHIPHY_API_KEY || process.env.GRAPIPHY_API_KEY || "";

async function callGraphifyMcp(toolName: string, args: Record<string, any>) {
  if (!GRAPHIFY_TOKEN) {
    throw new Error("GRAPHIPHY_API_KEY is not configured in environment or vault.");
  }

  // 1. Handshake
  const initRes = await fetch(GRAPHIFY_ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${GRAPHIFY_TOKEN}`,
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
    },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2024-11-05",
        capabilities: {},
        clientInfo: { name: "SupremeAI-Tower", version: "1.0.0" },
      },
    }),
  });

  if (!initRes.ok) {
    throw new Error(`Graphify MCP initialize failed: HTTP ${initRes.status}`);
  }

  const sessionId = initRes.headers.get("mcp-session-id");
  const headers: Record<string, string> = {
    Authorization: `Bearer ${GRAPHIFY_TOKEN}`,
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
  };
  if (sessionId) {
    headers["mcp-session-id"] = sessionId;
  }

  // 2. Call Tool
  const callRes = await fetch(GRAPHIFY_ENDPOINT, {
    method: "POST",
    headers,
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: {
        name: toolName,
        arguments: args,
      },
    }),
  });

  if (!callRes.ok) {
    throw new Error(`Graphify tool call failed: HTTP ${callRes.status}`);
  }

  const raw = await callRes.text();
  for (const line of raw.split("\n")) {
    if (line.startsWith("data:")) {
      try {
        return JSON.parse(line.slice(5).trim());
      } catch {
        // ignore
      }
    }
  }

  return { raw };
}

export async function registerGraphifyTools(server: McpServer): Promise<void> {
  server.tool(
    "graphify.call",
    "Call any Graphify MCP tool directly using the Infisical Graphify token (e.g. query_graph, search, list_repositories, graphify_trace, recall, remember).",
    {
      tool: z.string().describe("Graphify tool name (e.g. query_graph, search, list_repositories, recall)"),
      arguments: z.record(z.string(), z.any()).optional().describe("Arguments to pass to the Graphify tool"),
    },
    { readOnlyHint: true, idempotentHint: true },
    async ({ tool, arguments: args }) => {
      try {
        const result = await callGraphifyMcp(tool, args ?? {});
        return {
          content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        };
      } catch (err: any) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${err.message}` }],
        };
      }
    }
  );
}
