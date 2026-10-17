/**
 * SupremeAI MCP Tower — zero-dependency TypeScript client (SSE + Streamable HTTP).
 *
 * Spec companion: docs/MCP_CONNECT.md (issue #31).
 *
 * House style:
 * - no third-party dependencies; fetch + WHATWG streams only (Node 18+ / Bun / Deno)
 * - honest errors: every failure class carries its status code
 * - network I/O happens ONLY on explicit CLI action (offline-safe import)
 * - credentials never appear in URLs or logs (SECRETS_MODEL.md)
 *
 * Transports (verified against infrastructure/mcp-control-plane/src/index.ts):
 * - POST/GET/DELETE /mcp  — Streamable HTTP, stateful via Mcp-Session-Id
 * - GET /sse              — Server-Sent Events (text/event-stream)
 * - GET /health           — public smoke probe
 */

export const DEFAULT_BASE_URL =
  process.env.SUPREMEAI_MCP_TOWER_URL ?? "https://supremeai-mcp-tower.onrender.com";
export const DEFAULT_CLIENT_NAME = process.env.SUPREMEAI_CLIENT_NAME ?? "demo-ts-client";
const MCP_ACCEPT = "application/json, text/event-stream";

/** সব Tower-ত্রুটির মূল — status_code বহন করে (honest failure). */
export class TowerError extends Error {
  readonly statusCode?: number;
  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = "TowerError";
    this.statusCode = statusCode;
  }
}

export class TowerRateLimited extends TowerError {
  constructor(message: string) {
    super(message, 429);
    this.name = "TowerRateLimited";
  }
}

export class TowerForbidden extends TowerError {
  constructor(message: string) {
    super(message, 403);
    this.name = "TowerForbidden";
  }
}

export class TowerSessionLost extends TowerError {
  constructor(message: string) {
    super(message, 404);
    this.name = "TowerSessionLost";
  }
}

interface ModelEndpointish {
  provider: string;
  model: string;
  max_context_tokens?: number;
  cost_per_1k_tokens_usd?: number;
}

// ---------------------------------------------------------------------------
// HTTP core
// ---------------------------------------------------------------------------

interface PlainResponse {
  status: number;
  headers: Headers;
  text: string;
}

async function request(
  method: "GET" | "POST" | "DELETE",
  url: string,
  opts: { body?: unknown; headers?: Record<string, string>; timeoutMs?: number } = {},
): Promise<PlainResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? 30_000);
  try {
    const headers: Record<string, string> = { Accept: MCP_ACCEPT, ...(opts.headers ?? {}) };
    let body: string | undefined;
    if (opts.body !== undefined) {
      body = JSON.stringify(opts.body);
      headers["Content-Type"] = "application/json";
    }
    const resp = await fetch(url, { method, headers, body, signal: controller.signal });
    const text = await resp.text();
    if (resp.status === 429) {
      const retryAfter = resp.headers.get("Retry-After") ?? "unknown";
      throw new TowerRateLimited(`429 rate limited (Retry-After: ${retryAfter}s) — ${text.slice(0, 300)}`);
    }
    if (resp.status === 403) {
      throw new TowerForbidden(`403 default-deny RBAC — register or present verified credentials: ${text.slice(0, 300)}`);
    }
    if (resp.status === 404 && text.includes("-32001")) {
      throw new TowerSessionLost("404 -32001 session not found — re-initialize a fresh session");
    }
    if (!resp.ok) {
      throw new TowerError(`HTTP ${resp.status} — ${text.slice(0, 300)}`, resp.status);
    }
    return { status: resp.status, headers: resp.headers, text };
  } catch (err) {
    if (err instanceof TowerError) throw err;
    throw new TowerError(`network unreachable: ${(err as Error).message}`);
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// Streamable HTTP transport (/mcp)
// ---------------------------------------------------------------------------

export class McpHttpClient {
  private nextId = 1;
  sessionId: string | null = null;

  constructor(
    readonly baseUrl: string = DEFAULT_BASE_URL,
    readonly clientName: string = DEFAULT_CLIENT_NAME,
  ) {}

  private url(): string {
    return `${this.baseUrl.replace(/\/+$/, "")}/mcp?client=${encodeURIComponent(this.clientName)}`;
  }

  private async rpc<T = unknown>(method: string, params?: unknown): Promise<T> {
    if (this.sessionId === null && method !== "initialize") {
      throw new TowerSessionLost("no active session — call initialize() first");
    }
    const id = this.nextId++;
    const payload: Record<string, unknown> = { jsonrpc: "2.0", id, method };
    if (params !== undefined) payload.params = params;
    const headers: Record<string, string> = {};
    if (this.sessionId !== null) headers["Mcp-Session-Id"] = this.sessionId;

    const resp = await request("POST", this.url(), { body: payload, headers });
    const sid = resp.headers.get("Mcp-Session-Id");
    if (sid) this.sessionId = sid;

    let parsed: unknown;
    try {
      parsed = JSON.parse(resp.text);
    } catch {
      throw new TowerError(`non-JSON response from /mcp: ${resp.text.slice(0, 200)}`);
    }
    const obj = parsed as { error?: { code?: number; message?: string }; result?: T };
    if (obj.error) {
      throw new TowerError(`JSON-RPC error ${obj.error.code}: ${obj.error.message}`);
    }
    return obj.result as T;
  }

  /** Fresh `initialize` (no session header) mints a new per-session transport. */
  async initialize(): Promise<Record<string, unknown>> {
    this.sessionId = null;
    const result = await this.rpc<Record<string, unknown>>("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: this.clientName, version: "1.0.0" },
    });
    // notifications/initialized handshake completes the MCP init sequence (best-effort).
    try {
      const headers: Record<string, string> = {};
      if (this.sessionId !== null) headers["Mcp-Session-Id"] = this.sessionId;
      await request("POST", this.url(), {
        body: { jsonrpc: "2.0", method: "notifications/initialized" },
        headers,
      });
    } catch {
      /* notification is best-effort per spec tolerance */
    }
    return result;
  }

  async listTools(): Promise<Array<{ name: string; description?: string; [k: string]: unknown }>> {
    const result = await this.rpc<{ tools?: Array<{ name: string; description?: string }> }>("tools/list");
    return result.tools ?? [];
  }

  async callTool<T = unknown>(name: string, args: Record<string, unknown> = {}): Promise<T> {
    return this.rpc<T>("tools/call", { name, arguments: args });
  }

  /** DELETE /mcp — always release the session on shutdown (etiquette §5). */
  async close(): Promise<void> {
    if (this.sessionId === null) return;
    try {
      await request("DELETE", this.url(), {
        headers: { "Mcp-Session-Id": this.sessionId },
        timeoutMs: 10_000,
      });
    } catch {
      /* best-effort; server TTL cleans up regardless */
    } finally {
      this.sessionId = null;
    }
  }
}

// ---------------------------------------------------------------------------
// SSE transport (/sse)
// ---------------------------------------------------------------------------

export interface SseFrame {
  event: string | null;
  data: string;
}

/**
 * Read the first SSE frames from /sse (text/event-stream).
 * Bounded by maxFrames for demo use. Real clients: reconnect on
 * network errors with exponential backoff (docs/MCP_CONNECT.md §3).
 */
export async function sseRead(
  maxFrames = 5,
  baseUrl: string = DEFAULT_BASE_URL,
  clientName: string = DEFAULT_CLIENT_NAME,
  timeoutMs = 30_000,
): Promise<SseFrame[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const url = `${baseUrl.replace(/\/+$/, "")}/sse?client=${encodeURIComponent(clientName)}`;
  const frames: SseFrame[] = [];
  try {
    const resp = await fetch(url, {
      headers: { Accept: "text/event-stream" },
      signal: controller.signal,
    });
    if (resp.status === 503) {
      throw new TowerError("503 SSE session table full — back off and reconnect later", 503);
    }
    if (!resp.ok || !resp.body) {
      throw new TowerError(`HTTP ${resp.status} on /sse`, resp.status);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let done = false;
    while (frames.length < maxFrames && !done) {
      const chunk = await reader.read();
      done = chunk.done;
      if (chunk.value) {
        buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      }
      let idx: number;
      while (frames.length < maxFrames && (idx = buffer.indexOf("\n\n")) !== -1) {
        const rawFrame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        let event: string | null = null;
        const dataLines: string[] = [];
        for (const line of rawFrame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
        }
        if (dataLines.length > 0) frames.push({ event, data: dataLines.join("\n") });
      }
    }
    await reader.cancel().catch(() => undefined);
    return frames;
  } catch (err) {
    if (err instanceof TowerError) throw err;
    throw new TowerError(`network unreachable: ${(err as Error).message}`);
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// Health probe
// ---------------------------------------------------------------------------

export async function health(baseUrl: string = DEFAULT_BASE_URL): Promise<unknown> {
  const resp = await request("GET", `${baseUrl.replace(/\/+$/, "")}/health`, { timeoutMs: 15_000 });
  try {
    return JSON.parse(resp.text);
  } catch {
    return { raw: resp.text.slice(0, 200) };
  }
}

// ---------------------------------------------------------------------------
// CLI (network only on explicit action)
// ---------------------------------------------------------------------------

async function main(argv: string[]): Promise<number> {
  const actions = `Usage: bun run client.ts <action> [args]
  health — GET /health smoke probe (no credentials)
  sse    — read first SSE frames from /sse
  tools  — initialize + tools/list over Streamable HTTP
  call   — initialize + tools/call <name> [json-args]`;
  const [action, ...rest] = argv;
  if (!action) {
    console.log(actions);
    return 0;
  }
  if (action === "health") {
    console.log(JSON.stringify(await health(), null, 2));
    return 0;
  }
  if (action === "sse") {
    for (const frame of await sseRead(3)) {
      console.log(`[${frame.event ?? "message"}] ${frame.data}`);
    }
    return 0;
  }
  if (action !== "tools" && action !== "call") {
    console.log(actions);
    return 2;
  }

  const client = new McpHttpClient();
  try {
    const init = await client.initialize();
    const serverInfo = (init.serverInfo ?? {}) as { name?: string; version?: string };
    console.log(`# connected as '${client.clientName}' — server: ${serverInfo.name ?? "?"} ${serverInfo.version ?? ""}`);
    console.log(`# session: ${client.sessionId}`);
    if (action === "tools") {
      for (const tool of await client.listTools()) {
        console.log(`- ${tool.name}: ${(tool.description ?? "").slice(0, 80)}`);
      }
    } else {
      const toolName = rest[0];
      if (!toolName) {
        console.error("usage: client.ts call <tool-name> [json-arguments]");
        return 2;
      }
      const args = rest[1] ? (JSON.parse(rest[1]) as Record<string, unknown>) : {};
      console.log(JSON.stringify(await client.callTool(toolName, args), null, 2));
    }
    return 0;
  } finally {
    await client.close();
  }
}

// CLI entry — import is offline-safe; network only when executed as main.
const isMain =
  typeof process !== "undefined" &&
  Array.isArray(process.argv) &&
  process.argv[1] !== undefined &&
  /client\.ts$/.test(process.argv[1]);
if (isMain) {
  main(process.argv.slice(2))
    .then((code) => process.exit(code))
    .catch((err: Error) => {
      console.error(`ERROR: ${err.message}`);
      process.exit(1);
    });
}

// Re-exported for consumers that want the endpoint shape on hand.
export type { ModelEndpointish };
