import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { globalActionExecutor } from "../actions/executor.js";
import { buildRenderDeployAction } from "../adapters/render/actions.js";
import { buildRedisFlushAction } from "../adapters/redis/actions.js";
import { buildCloudflarePurgeCacheAction } from "../adapters/cloudflare/actions.js";

export async function registerActionTools(server: McpServer): Promise<void> {
  server.tool(
    "action.render_deploy",
    "Trigger a Render service deployment. Pass 'overrideRequestId' if you are executing an already-approved HITL request.",
    {
      serviceId: z.string().describe("Render Service ID"),
      clearCache: z.boolean().optional().describe("Whether to clear build cache"),
      overrideRequestId: z.string().optional().describe("Approved Request ID to bypass policy engine")
    },
    async ({ serviceId, clearCache, overrideRequestId }) => {
      try {
        const plan = buildRenderDeployAction(serviceId, clearCache);
        const result = await globalActionExecutor.execute(plan, overrideRequestId);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err: any) {
        return { isError: true, content: [{ type: "text", text: err.message }] };
      }
    }
  );

  server.tool(
    "action.redis_flush",
    "Flush Redis cache (optionally by prefix). Pass 'overrideRequestId' if you are executing an already-approved HITL request.",
    {
      prefix: z.string().optional().describe("Prefix to match keys. If empty, flushes all."),
      overrideRequestId: z.string().optional().describe("Approved Request ID to bypass policy engine")
    },
    async ({ prefix, overrideRequestId }) => {
      try {
        const plan = buildRedisFlushAction(prefix);
        const result = await globalActionExecutor.execute(plan, overrideRequestId);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err: any) {
        return { isError: true, content: [{ type: "text", text: err.message }] };
      }
    }
  );

  server.tool(
    "action.cloudflare_purge",
    "Purge Cloudflare Cache. Pass 'overrideRequestId' if you are executing an already-approved HITL request.",
    {
      overrideRequestId: z.string().optional().describe("Approved Request ID to bypass policy engine")
    },
    async ({ overrideRequestId }) => {
      try {
        const plan = buildCloudflarePurgeCacheAction();
        const result = await globalActionExecutor.execute(plan, overrideRequestId);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err: any) {
        return { isError: true, content: [{ type: "text", text: err.message }] };
      }
    }
  );
}
