import assert from "node:assert/strict";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { RequestContextStore } from "./src/policy/auth.context.js";
import { toolAccessError } from "./src/policy/mcp-access.js";
import {
  executeGeminiFunctionCall,
  geminiAdapterInfo,
  listGeminiTools,
  sanitizeForGeminiSchema,
  type GeminiAdapterContext,
} from "./src/adapters/gemini/gemini.adapter.js";

/**
 * #2590 — Gemini Function Calling Adapter contract tests (Universal 3rd Pillar).
 *
 * বাংলা মন্তব্য:
 * যাচাই হয় যে /gemini adapter —
 *   ১. MCP tool list-কে Gemini functionDeclarations-এ নির্ভুল রূপান্তর করে
 *      (নাম sanitize + schema subset)
 *   ২. Stateless function-call execution কাজ করে (InMemoryTransport pair)
 *   ৩. RBAC default-deny gate-কে সম্মান করে (viewer → safe tool ok,
 *      restricted tool denied; admin → allowed; কোনো context → denied)
 *   ৪. Unknown tool ও malformed args-এ fail-closed আচরণ করে
 */

/** টেস্ট serverFactory — index.ts-এর createMcpServer-এর RBAC-wrapped ছোট সংস্করণ। */
async function testServerFactory(): Promise<McpServer> {
  const server = new McpServer({ name: "tower-test", version: "1.0.0" });
  const originalTool = server.tool.bind(server);
  (server as unknown as { tool: unknown }).tool = (name: string, ...args: unknown[]) => {
    const sanitizedName = name.replace(/\./g, "_");
    let handlerIndex = -1;
    for (let i = args.length - 1; i >= 0; i--) {
      if (typeof args[i] === "function") { handlerIndex = i; break; }
    }
    if (handlerIndex >= 0) {
      const originalHandler = args[handlerIndex] as (toolArgs: unknown, extra: unknown) => unknown;
      args[handlerIndex] = async (toolArgs: unknown) => {
        // index.ts-এর মতোই কেন্দ্রীয় default-deny RBAC gate (#695)।
        const denial = toolAccessError(sanitizedName);
        if (denial) return { isError: true, content: [{ type: "text", text: denial }] };
        return originalHandler(toolArgs, {});
      };
    }
    return (originalTool as unknown as (n: string, ...a: unknown[]) => unknown)(sanitizedName, ...args);
  };

  // নাম দেখেই পরিচিত: safe/public টুল বনাম restricted (secret-class) টুল।
  server.tool(
    "system.health",
    "Tower health probe",
    {},
    async () => ({ content: [{ type: "text", text: "healthy" }] }),
  );
  server.tool(
    "admin.secret_tool",
    "Secret-class tool (admin only)",
    {},
    async () => ({ content: [{ type: "text", text: "TOP-SECRET" }] }),
  );
  server.tool(
    "echo.with_schema",
    "Echo tool with a nested schema",
    { payload: z.object({ value: z.string() }) },
    async (toolArgs: unknown) => ({ content: [{ type: "text", text: JSON.stringify(toolArgs) }] }),
  );
  return server;
}

const ctx: GeminiAdapterContext = {
  serverName: "tower-test",
  serverVersion: "1.0.0",
  serverFactory: testServerFactory,
};

// ─── ১. Schema sanitize: unsupported keys ফেলে, nested recursively প্রযোজ্য ───
assert.deepEqual(
  sanitizeForGeminiSchema({ type: "object", additionalProperties: false, $schema: "x", properties: { a: { type: "string" } } }),
  { type: "object", properties: { a: { type: "string" } } },
);
assert.deepEqual(
  sanitizeForGeminiSchema({ type: "string", enum: ["a", "b"], exclusiveMinimum: 1 }),
  { type: "object", properties: {} }, // root object নয় → Gemini-safe fallback
);
assert.deepEqual(
  sanitizeForGeminiSchema(null),
  { type: "object", properties: {} },
);
assert.deepEqual(
  sanitizeForGeminiSchema({ type: "object", properties: { list: { type: "array", items: { type: "number" } } } }),
  { type: "object", properties: { list: { type: "array", items: { type: "number" } } } },
);

// ─── ২. Adapter info manifest: ৩-পিলার সম্পূর্ণ ───
const info = geminiAdapterInfo(ctx);
assert.equal((info as { adapter?: string }).adapter, "gemini-function-calling");
const pillars = (info as { pillars?: Record<string, string> }).pillars ?? {};
assert.ok(pillars["mcp"] && pillars["sse"] && pillars["gemini"], "all 3 pillars must be documented");

// ─── ৩. listGeminiTools: sanitized নাম + Gemini-format parameters ───
{
  const manifest = await listGeminiTools(ctx);
  assert.ok(manifest.toolCount >= 3, `expected ≥3 tools, got ${manifest.toolCount}`);
  const names = manifest.functionDeclarations.map((d) => d.name);
  assert.ok(names.includes("system_health"), "dot-sanitized name must be listed");
  assert.ok(!names.some((n) => n.includes(".")), "no dots allowed in Gemini function names");
  for (const declaration of manifest.functionDeclarations) {
    assert.equal(typeof declaration.description, "string");
    assert.equal(declaration.parameters.type, "object");
    assert.ok(!("additionalProperties" in declaration.parameters), "unsupported keys must be stripped");
  }
  const echo = manifest.functionDeclarations.find((d) => d.name === "echo_with_schema");
  assert.ok(echo, "echo_with_schema missing from manifest");
  assert.ok(echo!.parameters.properties && typeof echo!.parameters.properties === "object");
}

// ─── ৪. Safe tool execution (viewer role) — stateless POST /gemini path ───
{
  const result = await RequestContextStore.run(
    { role: "viewer", accessMode: "viewer", authenticated: true, tenantBound: false, scopes: ["health:read"] },
    async () => executeGeminiFunctionCall(ctx, "system_health", {}),
  );
  assert.equal(result.ok, true);
  assert.equal(result.tool, "system_health");
  assert.equal(result.content, "healthy");
}

// ─── ৫. RBAC default-deny: viewer → restricted tool denied; admin → allowed ───
{
  const denied = await RequestContextStore.run(
    { role: "viewer", accessMode: "viewer", authenticated: true, tenantBound: false, scopes: [] },
    async () => executeGeminiFunctionCall(ctx, "admin_secret_tool", {}),
  );
  assert.equal(denied.ok, false, "viewer must NOT execute a secret-class tool");
  assert.ok(String(denied.error).includes("Forbidden"), `expected RBAC denial, got: ${denied.error}`);

  const allowed = await RequestContextStore.run(
    { role: "admin", accessMode: "admin", authenticated: true, tenantBound: false, scopes: ["*"] },
    async () => executeGeminiFunctionCall(ctx, "admin_secret_tool", {}),
  );
  assert.equal(allowed.ok, true, "admin must execute the secret-class tool");
  assert.equal(allowed.content, "TOP-SECRET");
}

// ─── ৬. No request context at all → fail-closed (default-deny) ───
{
  const result = await executeGeminiFunctionCall(ctx, "admin_secret_tool", {});
  assert.equal(result.ok, false, "no-context call must be denied by the RBAC gate");
}

// ─── ৭. Args pass-through: nested payload অক্ষত পৌঁছায় (admin — echo টুল restricted-class) ───
{
  const result = await RequestContextStore.run(
    { role: "admin", accessMode: "admin", authenticated: true, tenantBound: false, scopes: ["*"] },
    async () => executeGeminiFunctionCall(ctx, "echo_with_schema", { payload: { value: "bangla" } }),
  );
  assert.equal(result.ok, true);
  const echoed = JSON.parse(String(result.content));
  assert.equal(echoed.payload.value, "bangla");
}

// ─── ৮. Unknown tool → fail-closed logical error (SDK isError path; HTTP 200 + ok:false) ───
{
  const result = await RequestContextStore.run(
    { role: "admin", accessMode: "admin", authenticated: true, tenantBound: false, scopes: ["*"] },
    async () => executeGeminiFunctionCall(ctx, "nonexistent_tool", {}),
  );
  assert.equal(result.ok, false, "unknown tool must NOT report success");
  assert.ok(/not found/i.test(String(result.error)), `expected not-found error, got: ${result.error}`);
}

console.log("✅ test_gemini_adapter: ৮/৮ contract test পাস — Gemini 3rd pillar adapter verified (#2590)");
