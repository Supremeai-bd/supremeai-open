import { MemorySubAdapter } from "./src/adapters/memory/index.js";

const adapter = new MemorySubAdapter();
console.log("starting sidecar (90s budget)...");
const started = await Promise.race([
  adapter.start().then(() => "done" as const),
  new Promise((r) => setTimeout(() => r("timeout" as const), 85000)),
]);
console.log("start result =", started);
console.log("ready =", adapter.isReady, "lastError =", adapter.lastFailure);
console.log("attempts =", adapter.attemptCount);
if (adapter.isReady) {
  const tools = await adapter.listTools();
  console.log("tool count =", tools.length);
  console.log("tool names =", tools.map((t) => t.name).join(","));
  const r = await adapter.callTool("read_graph", {});
  console.log("read_graph ok =", r.ok, JSON.stringify(r.data ?? r.error).slice(0, 300));
}
await adapter.stop();
console.log("stopped ok");
process.exit(0);
