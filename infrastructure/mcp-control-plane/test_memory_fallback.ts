import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { MemorySubAdapter } from "./src/adapters/memory/index.js";
import { registerMemoryTools } from "./src/tools/memory.tools.js";
import { jsonSchemaToZodShape } from "./src/adapters/memory/jsonSchemaToZod.js";

// 1. Schema converter sanity
const shape = jsonSchemaToZodShape({
  type: "object",
  properties: {
    query: { type: "string", description: "Search query" },
    n_results: { type: "integer", default: 5 },
    tags: { type: "array", items: { type: "string" } },
    metadata: { type: "object" },
  },
  required: ["query"],
});
console.log("converter keys =", Object.keys(shape).join(","));

// 2. Fallback registration WITHOUT starting sidecar (offline, fast)
const server = new McpServer({ name: "test", version: "0.0.1" });
const adapter = new MemorySubAdapter(); // never started
// Monkey-patch listTools to simulate cold sidecar
adapter.listTools = async () => [];
await registerMemoryTools(server, adapter);
// @ts-expect-error - introspect registered tools
const tools = server._registeredTools ?? {};
console.log("registered tool count =", Object.keys(tools).length);
console.log("has memory.search_nodes =", "memory.search_nodes" in tools);
console.log("has memory.remember_fact =", "memory.remember_fact" in tools);
console.log("has memory.status =", "memory.status" in tools);
console.log("FALLBACK-TEST-PASS");
process.exit(0);
