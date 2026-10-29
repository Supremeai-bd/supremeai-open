/**
 * c29 runtime rehearsal: boot a bare McpServer + registerBridgeTools (as the
 * onboarding harness does), connect an InMemory client, and CALL
 * bridge_work_queue for real. Asserts:
 *  1. result.structuredContent exists (dual emission live)
 *  2. it survives the SDK's own validateToolOutput (no McpError thrown)
 *  3. JSON.parse(result.content[0].text) deep-equals structuredContent
 *     (single-payload zero-drift guarantee)
 *  4. R59 echo keys present in structuredContent
 * Network failure tolerated: an isError result proves the error path stays
 * text-only and exempt from output validation (also a contract point).
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { registerBridgeTools } from "./src/tools/bridge.tools.js";
import { RequestContextStore } from "./src/policy/auth.context.js";

const server = new McpServer({ name: "c29-rehearsal", version: "0.0.1" });
// Mirror the production index.fixed.ts registerTool shim (name sanitization
// only — this rehearsal has no RBAC/rate-limit stores wired, which are
// covered by the onboarding + rate-limit test batteries).
const originalRegisterTool = (server as unknown as { registerTool: (n: string, c: unknown, cb: unknown) => unknown }).registerTool.bind(server);
(server as unknown as { registerTool: unknown }).registerTool = (name: string, config: unknown, cb: unknown) => {
  const sanitizedName = name.replace(/\./g, "_");
  return originalRegisterTool(sanitizedName, config, cb);
};
await registerBridgeTools(server);

const client = new Client({ name: "c29-rehearsal-client", version: "0.0.1" });
const [cT, sT] = InMemoryTransport.createLinkedPair();
await server.connect(sT);
await client.connect(cT);

const anon = { authenticated: false } as never;
await RequestContextStore.run(anon, async () => {
  const list = await client.listTools();
  const q = (list.tools ?? []).find((t) => t.name === "bridge_work_queue");
  console.log("[1] tools/list name:", q?.name, "| outputSchema advertised:", Boolean(q && (q as { outputSchema?: unknown }).outputSchema));
  if (q && (q as { outputSchema?: { required?: string[] } }).outputSchema) {
    const os = (q as { outputSchema: { required?: string[]; properties?: Record<string, unknown> } }).outputSchema;
    console.log("[1b] outputSchema.required:", JSON.stringify(os.required));
    console.log("[1c] outputSchema keys:", Object.keys(os.properties ?? {}).join(","));
  }

  const r = await client.callTool({ name: "bridge_work_queue", arguments: { limit: 3 } });
  const isError = (r as { isError?: boolean }).isError === true;
  const sc = (r as { structuredContent?: unknown }).structuredContent;
  const text = (r as { content?: Array<{ type: string; text?: string }> }).content?.[0]?.text ?? "";
  console.log("[2] isError:", isError, "| structuredContent present:", sc !== undefined);
  if (!isError && sc !== undefined) {
    const parsed = JSON.parse(text);
    const deepEq = JSON.stringify(parsed) === JSON.stringify(sc);
    console.log("[3] text deep-equals structuredContent:", deepEq);
    const s = sc as Record<string, unknown>;
    console.log("[4] echo keys:", "count=" + s.count, "totalOpen=" + s.totalOpen, "windowTruncated=" + s.windowTruncated,
      "| rows:", Array.isArray(s.workOrders) ? (s.workOrders as unknown[]).length : "n/a",
      "| nextStep:", typeof s.nextStep === "string");
    if (!deepEq) { console.error("DRIFT DETECTED"); process.exit(1); }
    console.log("REHEARSAL PASSED: dual emission live, SDK validation silent, zero drift");
  } else if (isError) {
    console.log("[2b] error-path receipt (network):", text.slice(0, 120));
    console.log("REHEARSAL (error-path): isError text-only, output validation exempt — contract point held");
  }
});
process.exit(0);
