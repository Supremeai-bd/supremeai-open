import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { RequestContextStore } from "../policy/auth.context.js";
import { getAccountsForRole, ProviderAccount } from "../registry/account.registry.js";
import { globalHealthCache } from "../health/snapshot.js";
import { globalHealthEngine } from "../health/engine.js";
import { globalDependencyGraph } from "../health/dependency.js";
import { listClients } from "../policy/client-registry.js";
import { globalKillSwitch } from "../remediation/killswitch.js";

/**
 * S0.4 / Unified Observability Hub: `status(scope, targetId?)`
 *
 * Consolidates observation across:
 *  - system / services
 *  - health (live / cached)
 *  - dependencies
 *  - slots / agents
 *  - autonomy / killswitch
 *  - all (one-sweep composite snapshot)
 *
 * Fully backwards-compatible with existing legacy tools.
 */
export async function registerUnifiedStatusTool(server: McpServer): Promise<void> {
  server.tool(
    "status",
    "Unified system observation tool. Inspects health, service availability, dependencies, agent slots, and runtime status in a single call.",
    {
      scope: z
        .enum(["all", "system", "health", "health_live", "deps", "slots", "autonomy"])
        .default("all")
        .describe("The telemetry domain to observe. Default is 'all' (complete composite status)."),
      targetId: z
        .string()
        .optional()
        .describe("Optional target ID or agent slot to filter (e.g., 'agent-1', 'render-primary')."),
    },
    async ({ scope, targetId }) => {
      const store = RequestContextStore.get();
      const role = store?.role;

      try {
        const result: Record<string, unknown> = {
          timestamp: new Date().toISOString(),
          scope,
        };

        if (scope === "all" || scope === "system") {
          const registry: ProviderAccount[] = getAccountsForRole(role);
          const available = registry.filter((r: ProviderAccount) => r.available).length;
          result.system = {
            availableServices: `${available}/${registry.length}`,
            services: registry.map((r: ProviderAccount) => ({
              id: r.id,
              provider: r.provider,
              displayName: r.displayName,
              available: r.available,
            })),
          };
        }

        if (scope === "all" || scope === "health") {
          const cached = globalHealthCache.getAllSnapshots();
          result.health = Object.keys(cached).length > 0 ? cached : "Health cache empty. Use scope 'health_live' for fresh sweep.";
        } else if (scope === "health_live") {
          result.health_live = await globalHealthEngine.runFullSweep();
        }

        if (scope === "all" || scope === "deps") {
          result.dependencies = globalDependencyGraph.getRawMap();
        }

        if (scope === "all" || scope === "slots") {
          const clients = listClients(store?.isGlobalAdmin ? "*" : (store?.tenantId ?? "tenant_default"));
          const slots = clients.filter((c) => c.id.startsWith("slot_") || c.provider === "slot" || c.name.startsWith("agent-"));
          result.slots = targetId ? slots.filter((s) => s.id === targetId || s.name === targetId) : slots;
        }

        if (scope === "all" || scope === "autonomy") {
          result.autonomy = {
            enabled: globalKillSwitch.isAutonomyEnabled(),
            mode: globalKillSwitch.isAutonomyEnabled() ? "L2 (Autonomous)" : "L0 (Emergency Stop / Read-Only)",
          };
        }

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(result, null, 2),
            },
          ],
        };
      } catch (err) {
        return {
          isError: true,
          content: [
            {
              type: "text",
              text: `Status query error: ${(err as Error).message}`,
            },
          ],
        };
      }
    }
  );
}
