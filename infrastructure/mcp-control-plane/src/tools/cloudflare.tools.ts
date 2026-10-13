import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { getWorkerStatus, getAnalytics } from "../adapters/cloudflare/index.js";

export async function registerCloudflareTools(server: McpServer): Promise<void> {
  server.tool(
    "cloudflare.worker_status",
    "Ping the deployed Cloudflare Worker to check its availability and latency.",
    {},
    async () => {
      try {
        const status = await getWorkerStatus();
        return {
          content: [{ type: "text", text: JSON.stringify(status, null, 2) }],
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
    "cloudflare.analytics",
    "Get basic analytics/details from the Cloudflare account.",
    {},
    async () => {
      try {
        const analytics = await getAnalytics();
        return {
          content: [{ type: "text", text: JSON.stringify(analytics, null, 2) }],
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
