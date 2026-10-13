import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { pingRedis, getRedisStats, readRedisKey } from "../adapters/redis/index.js";

export async function registerRedisTools(server: McpServer): Promise<void> {
  server.tool(
    "redis.ping",
    "Ping the Redis cache/queue to verify connectivity.",
    {},
    async () => {
      try {
        const res = await pingRedis();
        return {
          content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
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
    "redis.stats",
    "Get basic statistics from Redis via the INFO command.",
    {},
    async () => {
      try {
        const stats = await getRedisStats();
        return {
          content: [{ type: "text", text: JSON.stringify(stats, null, 2) }],
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
    "redis.read_key",
    "Safely read/get the value of a key from Redis cache (Read-Only).",
    {
      key: z.string().describe("The Redis key to read"),
    },
    async ({ key }) => {
      try {
        const res = await readRedisKey(key);
        return {
          content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
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
    "redis.rotation_status",
    "Inspect the Upstash Redis auto-rotation chain status, active primary, and quota cooldowns (#26).",
    {},
    async () => {
      try {
        const { quotaChainStatus, getActiveRedisAccount, nextQuotaResetEpochMs } = await import("../lib/redis_chain.js");
        const active = getActiveRedisAccount();
        const chain = quotaChainStatus();
        const nextReset = new Date(nextQuotaResetEpochMs()).toISOString();
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  autoRotateEnabled: true,
                  activePrimary: active.label,
                  quotaWindow: process.env.UPSTASH_QUOTA_WINDOW || "monthly",
                  nextGlobalResetAt: nextReset,
                  chain,
                },
                null,
                2
              ),
            },
          ],
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

