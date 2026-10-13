import { ActionPlan } from "../../actions/plan.js";

export function buildRedisFlushAction(prefix?: string): ActionPlan {
  return {
    context: { provider: "redis", action: prefix ? "del_prefix" : "flushall" },
    description: `Flush Redis Data (Prefix: ${prefix || 'ALL'})`,
    parameters: { prefix },
    executeFn: async () => {
      // For this skeleton phase, we simulate the flush.
      // In production, we'd use ioredis or REST api to issue FLUSHALL or SCAN/DEL.
      console.log(`[REDIS] Simulated flushing data (Prefix: ${prefix || 'ALL'})`);
      return { cleared: prefix ? `Keys matching ${prefix}*` : "ALL" };
    }
  };
}
