import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

/**
 * 🇧🇩 Gemini Function Calling Adapter — Universal 3rd Pillar (#2590)
 *
 * বাংলা মন্তব্য:
 * কন্ট্রোল টাওয়ারের ৩টি ইউনিভার্সাল ট্রান্সপোর্ট পিলারের তৃতীয়টি:
 *   ১. `streamable-http` (POST /mcp)   — আধুনিক MCP spec (#2588 per-session)
 *   ২. `sse`          (GET /sse)       — legacy MCP SSE / web connectors
 *   ৩. `gemini`       (/gemini)        — এই adapter: Gemini Function Calling
 *
 * Google Gemini Spark / AI Studio যেহেতু কখনো MCP handshake করে না
 * (native function-calling protocol ব্যবহার করে), এই adapter টাওয়ারের
 * সমস্ত MCP tool-কে Gemini-compatible `functionDeclarations` manifest-এ
 * রূপান্তর করে এবং stateless `POST /gemini` function-call execution দেয়।
 *
 * আর্কিটেকচার (SSoT principle — #2590 + #2429):
 *   - Tool-এর single source of truth থাকে McpServer registration-এ
 *     (serverFactory — RBAC wrapper + rate limit + timeout + truncation সহ)।
 *   - এই adapter কোনো tool logic duplicate করে না; প্রতি request-এ একটি
 *     fresh `McpServer` + `Client` pair `InMemoryTransport`-এ যুক্ত করে
 *     (`createLinkedPair` — SDK-র canonical in-process pattern) এবং
 *     listTools/callTool প্রোগ্রাম্যাটিকভাবে চালায়।
 *   - ফলে /mcp ও /sse যে governance layer পায়, /gemini-ও হুবহু সেটি পায় —
 *     কারণ একই `serverFactory` ব্যবহৃত হয়।
 */

/** Tower-এর সংস্করণ/নাম তথ্য (routing layer থেকে inject হয়)। */
export interface GeminiAdapterContext {
  serverName: string;
  serverVersion: string;
  /** প্রতি request-এ fresh McpServer বানানোর factory (RBAC wrapper সহ)। */
  serverFactory: () => Promise<McpServer>;
}

/** Gemini `functionDeclarations`-এ বৈধ JSON Schema keys-এর allowlist (string-typed — বাইরের input যেকোনো key হতে পারে)। */
const GEMINI_SCHEMA_KEYS: ReadonlySet<string> = new Set([
  "type",
  "format",
  "description",
  "nullable",
  "enum",
  "items",
  "properties",
  "required",
  "minimum",
  "maximum",
  "minItems",
  "maxItems",
  "anyOf",
  "title",
  "default",
]);

/**
 * বাংলা মন্তব্য: MCP JSON Schema → Gemini OpenAPI subset sanitize।
 * Gemini function-calling schema strict subset গ্রহণ করে — অজানা keys
 * (যেমন `$schema`, `additionalProperties`, `exclusiveMinimum`) ফেলে দিয়ে
 * বৈধ keys রাখা হয়। Object-নেস্টেড সব স্তরে recursively প্রযোজ্য।
 * Root-fallback (object/anyOf constraint) শুধু টপ-লেভেল স্কিমায় —
 * nested property নিজের টাইপ (string/number/array…) রাখতে পারে।
 */
export function sanitizeForGeminiSchema(schema: unknown): Record<string, unknown> {
  const sanitizedRoot = sanitizeNode(schema);
  // Gemini parameters root অবশ্যই object-typed হতে হবে (বা anyOf union)।
  if (sanitizedRoot["type"] !== "object" && !("anyOf" in sanitizedRoot)) {
    return { type: "object", properties: {} };
  }
  return sanitizedRoot;
}

/** Recursive sanitizer — প্রতিটি schema node-এ অজানা keys ফেলে দেয়। */
function sanitizeNode(schema: unknown): Record<string, unknown> {
  if (!schema || typeof schema !== "object" || Array.isArray(schema)) {
    return {};
  }
  const source = schema as Record<string, unknown>;
  const output: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(source)) {
    if (!GEMINI_SCHEMA_KEYS.has(key)) continue;
    if (key === "properties" && value && typeof value === "object" && !Array.isArray(value)) {
      const nested: Record<string, unknown> = {};
      for (const [propName, propSchema] of Object.entries(value as Record<string, unknown>)) {
        nested[propName] = sanitizeNode(propSchema);
      }
      output[key] = nested;
    } else if (key === "items") {
      output[key] = sanitizeNode(value);
    } else if (key === "anyOf" && Array.isArray(value)) {
      output[key] = value.map((entry) => sanitizeNode(entry));
    } else {
      output[key] = value;
    }
  }
  return output;
}

/** একটি MCP tool descriptor → Gemini functionDeclaration। */
function mcpToolToGeminiDeclaration(tool: {
  name?: string;
  description?: string;
  inputSchema?: unknown;
}): { name: string; description: string; parameters: Record<string, unknown> } {
  return {
    name: String(tool.name ?? ""),
    description: String(tool.description ?? ""),
    parameters: sanitizeForGeminiSchema(tool.inputSchema),
  };
}

/** `GET /gemini` — adapter info manifest (৩-পিলার পরিচিতি)। */
export function geminiAdapterInfo(ctx: GeminiAdapterContext): Record<string, unknown> {
  return {
    adapter: "gemini-function-calling",
    server: ctx.serverName,
    version: ctx.serverVersion,
    protocol: "Gemini Function Calling / OpenAPI-compatible tool schema",
    pillars: {
      mcp: "POST /mcp — Streamable-HTTP per-session (modern MCP spec)",
      sse: "GET /sse — Server-Sent Events transport (web connectors)",
      gemini: "GET/POST /gemini — this adapter (native function calling)",
    },
    usage: {
      listTools: "GET /gemini/tools → { functionDeclarations: [...] }",
      callTool: "POST /gemini { \"name\": \"<tool_name>\", \"args\": { ... } }",
      auth: "Optional MCP Bearer token; tokenless callers auto-register as guests (public read-only scope).",
    },
  };
}

/**
 * বাংলা মন্তব্য: fresh McpServer+Client in-memory pair খুলে callback চালায়,
 * শেষে উভয়প্রান্ত close করে (কোনো লিক নেই)। Per-request pair = per-session
 * /mcp pattern-এর stateless রূপ — এক ক্লায়েন্টের ফলে অন্যের session ভাঙবে না
 * (#2588-এর শিক্ষা: কখনো গ্লোবাল singleton transport নয়)।
 */
async function withInMemoryPair<T>(
  ctx: GeminiAdapterContext,
  fn: (client: Client) => Promise<T>,
): Promise<T> {
  const server = await ctx.serverFactory();
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: `${ctx.serverName}-gemini-adapter`, version: ctx.serverVersion });
  try {
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    return await fn(client);
  } finally {
    // বাংলা মন্তব্য: fail-safe teardown — যেকোনো error-এও pair-টি মুক্ত হবে।
    try { await client.close(); } catch { /* ইতিমধ্যে closed */ }
    try { await server.close(); } catch { /* ইতিমধ্যে closed */ }
  }
}

/** `GET /gemini/tools` — Gemini-compatible functionDeclarations manifest। */
export async function listGeminiTools(ctx: GeminiAdapterContext): Promise<{
  functionDeclarations: Array<{ name: string; description: string; parameters: Record<string, unknown> }>;
  toolCount: number;
}> {
  const result = await withInMemoryPair(ctx, async (client) => client.listTools());
  const declarations = (result.tools ?? [])
    .map((tool) => mcpToolToGeminiDeclaration(tool as { name?: string; description?: string; inputSchema?: unknown }))
    .filter((declaration) => declaration.name.length > 0);
  return { functionDeclarations: declarations, toolCount: declarations.length };
}

export interface GeminiFunctionCallResult {
  ok: boolean;
  tool?: string;
  content?: unknown;
  structuredContent?: unknown;
  error?: string;
}

/**
 * `POST /gemini` — একটি function call execute করে (stateless)।
 * বাংলা মন্তব্য: RBAC/timeout/rate-limit সব `serverFactory`-এর wrapped
 * handler-এ বাস্তবায়িত — এখানে শুধু transport। Tool-এর logical error
 * (isError: true) HTTP 200-এ `ok: false` হিসেবে ফেরে; protocol error
 * exception হিসেবে উপরে ওঠে (routing layer 4xx/5xx করবে)।
 */
export async function executeGeminiFunctionCall(
  ctx: GeminiAdapterContext,
  name: string,
  args: Record<string, unknown> | undefined,
): Promise<GeminiFunctionCallResult> {
  const parsedArgs = args && typeof args === "object" && !Array.isArray(args) ? args : {};
  const result = await withInMemoryPair(ctx, async (client) =>
    client.callTool({ name, arguments: parsedArgs }),
  );
  const isError = (result as { isError?: boolean }).isError === true;
  const contentBlocks = (Array.isArray((result as { content?: unknown }).content)
    ? ((result as { content: unknown[] }).content)
    : []) as Array<{ type?: string; text?: unknown }>;
  const textParts: string[] = [];
  for (const block of contentBlocks) {
    if (block.type === "text" && typeof block.text === "string") {
      textParts.push(block.text);
    }
  }
  return {
    ok: !isError,
    tool: name,
    content: textParts.length === 1 ? textParts[0] : textParts,
    structuredContent: (result as { structuredContent?: unknown }).structuredContent,
    ...(isError ? { error: textParts.join("\n") || "Tool execution failed" } : {}),
  };
}
