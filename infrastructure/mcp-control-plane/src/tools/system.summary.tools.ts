import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { globalHealthEngine } from "../health/engine.js";
import { globalHealthCache } from "../health/snapshot.js";
import { globalDependencyGraph } from "../health/dependency.js";
import { listResources } from "../registry/resource.registry.js";

export async function registerSystemSummaryTools(server: McpServer): Promise<void> {
  server.tool(
    "health.full_sweep",
    "Universal Observe Layer: Forces a fresh sweep of all adapters (bypassing cache) and returns the incident report and snapshots.",
    {},
    async () => {
      try {
        const report = await globalHealthEngine.runFullSweep();
        return {
          content: [{ type: "text", text: JSON.stringify(report, null, 2) }],
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
    "health.dashboard",
    "Universal Observe Layer: Returns the latest cached health snapshot instantly (no network requests).",
    {},
    async () => {
      try {
        const snapshots = globalHealthCache.getAllSnapshots();
        if (Object.keys(snapshots).length === 0) {
          return {
            content: [{ type: "text", text: "Cache is empty. Please run health.full_sweep first." }],
          };
        }
        return {
          content: [{ type: "text", text: JSON.stringify(snapshots, null, 2) }],
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
    "resources.dashboard",
    "Returns the account-aware resource inventory with the latest cached provider status.",
    {},
    async () => {
      try {
        const resources = await listResources();
        return { content: [{ type: "text", text: JSON.stringify(resources, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "system.dependencies",
    "Universal Observe Layer: Returns the dependency graph map.",
    {},
    async () => {
      const deps = globalDependencyGraph.getRawMap();
      return {
        content: [{ type: "text", text: JSON.stringify(deps, null, 2) }],
      };
    }
  );
}
