// installer.mjs — dynamic MCP installer: connect, initialize, execute (issue #332 AC2+AC3).
//
// Transports (MCP standards, docs/MCP_CONNECT.md etiquette):
//   - streamable-http: JSON-RPC over POST {base}{entry.path}; session rides
//     the mcp-session-id response header.
//   - sse: GET {base}/sse, parse the endpoint frame (event:/data: lines),
//     then JSON-RPC over the announced endpoint.
//
// EXECUTION BOUNDARY (AC3, fail closed): every execute() call re-validates
// the lease BEFORE any network activity. A denied call produces a structured
// {denied:true,...} envelope and NEVER touches the wire — nothing is
// partially executed, no scope escalation can slip a request through.

export class InstallerError extends Error {
  constructor(code, message, { status, retryable } = {}) {
    super(`${code}: ${message}`);
    this.name = "InstallerError";
    this.code = code;
    this.status = status;
    this.retryable = retryable ?? false;
  }
}

const MCP_ACCEPT = "application/json, text/event-stream";

/** Minimal SSE frame parser per docs/MCP_CONNECT.md section 3. */
export function parseSseFrames(text) {
  const frames = [];
  for (const block of text.split("\n\n")) {
    let event = null;
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length > 0 || event !== null) {
      frames.push({ event, data: data.join("\n") });
    }
  }
  return frames;
}

export class McpInstaller {
  constructor({ baseUrl, clientName = "skills-installer-reference", fetchImpl = globalThis.fetch }) {
    if (typeof baseUrl !== "string" || !/^https?:\/\//.test(baseUrl)) {
      throw new InstallerError("bad_base_url", "baseUrl must be an http(s) URL");
    }
    if (typeof fetchImpl !== "function") {
      throw new InstallerError("no_fetch", "fetch is unavailable in this runtime");
    }
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.clientName = clientName;
    this.#fetch = fetchImpl;
    this.sessionId = null;
    this.rpcId = 1;
  }

  #fetch;

  #url(path) {
    return `${this.baseUrl}${path}${path.includes("?") ? "&" : "?"}client=${encodeURIComponent(this.clientName)}`;
  }

  async #postJson(path, payload, { sessionId = this.sessionId } = {}) {
    const headers = { "Content-Type": "application/json", Accept: MCP_ACCEPT };
    if (sessionId) headers["mcp-session-id"] = sessionId;
    let resp;
    try {
      resp = await this.#fetch(this.#url(path), {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
    } catch (err) {
      throw new InstallerError("transport_error", String(err && err.message ? err.message : err), { retryable: true });
    }
    if (resp.status === 429) {
      throw new InstallerError("rate_limited",
        `429 (Retry-After: ${resp.headers.get("Retry-After") ?? "unknown"}s)`,
        { status: 429, retryable: true });
    }
    if (resp.status === 403) {
      throw new InstallerError("forbidden", "403 default-deny RBAC", { status: 403 });
    }
    if (!resp.ok) {
      throw new InstallerError("http_error", `HTTP ${resp.status}`, { status: resp.status });
    }
    const newSession = resp.headers.get("mcp-session-id");
    if (newSession) this.sessionId = newSession;
    const text = await resp.text();
    // SSE-framed JSON-RPC responses are legal under streamable MCP; unwrap.
    if (text.startsWith("event:") || text.startsWith("data:")) {
      const frames = parseSseFrames(text).filter((f) => f.data.startsWith("{"));
      if (frames.length === 0) throw new InstallerError("bad_frame", "no JSON frame in SSE response");
      return JSON.parse(frames[frames.length - 1].data);
    }
    return JSON.parse(text);
  }

  /**
   * Initialize over the chosen transport (AC2). Returns the server tool list.
   */
  async initialize({ transport, path }) {
    if (transport === "streamable-http") {
      const init = await this.#postJson(path, {
        jsonrpc: "2.0", id: this.rpcId++, method: "initialize",
        params: { protocolVersion: "2025-03-26", capabilities: {},
                  clientInfo: { name: this.clientName, version: "1.0.0" } },
      });
      if (init.error) throw new InstallerError("rpc_error", init.error.message ?? "initialize failed");
      await this.#postJson(path, { jsonrpc: "2.0", method: "notifications/initialized" }).catch(() => {});
      const list = await this.#postJson(path, { jsonrpc: "2.0", id: this.rpcId++, method: "tools/list" });
      return { transport, tools: list.result?.tools ?? [] };
    }
    if (transport === "sse") {
      // Open the SSE leg, read the endpoint frame, then JSON-RPC on it.
      let resp;
      try {
        resp = await this.#fetch(this.#url("/sse"), { headers: { Accept: "text/event-stream" } });
      } catch (err) {
        throw new InstallerError("transport_error", String(err && err.message ? err.message : err), { retryable: true });
      }
      if (!resp.ok) throw new InstallerError("http_error", `SSE HTTP ${resp.status}`, { status: resp.status });
      const head = await resp.text();
      const frames = parseSseFrames(head);
      const endpointFrame = frames.find((f) => f.event === "endpoint" || (f.data || "").startsWith("/"));
      if (!endpointFrame) throw new InstallerError("bad_frame", "no endpoint frame on SSE leg");
      const endpoint = endpointFrame.data.trim();
      const init = await this.#postJson(endpoint, {
        jsonrpc: "2.0", id: this.rpcId++, method: "initialize",
        params: { protocolVersion: "2025-03-26", capabilities: {},
                  clientInfo: { name: this.clientName, version: "1.0.0" } },
      }, { sessionId: null });
      if (init.error) throw new InstallerError("rpc_error", init.error.message ?? "initialize failed");
      await this.#postJson(endpoint, { jsonrpc: "2.0", method: "notifications/initialized" }).catch(() => {});
      const list = await this.#postJson(endpoint, { jsonrpc: "2.0", id: this.rpcId++, method: "tools/list" });
      return { transport, endpoint, tools: list.result?.tools ?? [] };
    }
    throw new InstallerError("bad_transport", `unsupported transport '${transport}'`);
  }

  /**
   * Execute a leased tool (AC3). Lease is re-checked BEFORE the wire.
   * @returns {{denied:false, result:object, invocation_id:string}}
   *          | {denied:true, code, reason}
   */
  async execute(installedManifest, lease, checkFn, toolName, args) {
    try {
      checkFn(lease, toolName, installedManifest);
    } catch (err) {
      return { denied: true, code: err.code ?? "lease_invalid", reason: err.reason ?? String(err.message) };
    }
    const declared = installedManifest.tools.find((t) => t.name === toolName);
    if (!declared) {
      // Belt and braces: the lease check re-reads the manifest too.
      return { denied: true, code: "unknown_tool", reason: `tool '${toolName}' not in manifest` };
    }
    const invocationId = `inv-${Math.random().toString(16).slice(2, 14)}`;
    const endpoint = this.endpointOverride ?? (installedManifest.entry.transport === "streamable-http"
      ? installedManifest.entry.path : this.sseEndpoint ?? installedManifest.entry.path);
    try {
      const resp = await this.#postJson(endpoint, {
        jsonrpc: "2.0", id: this.rpcId++, method: "tools/call",
        params: { name: toolName, arguments: args },
      });
      if (resp.error) {
        return { denied: false, invocation_id: invocationId, status: "error",
                 error: { code: "tool_failed", message: String(resp.error.message ?? "tool error"), retryable: false } };
      }
      if (resp.result && resp.result.isError) {
        // MCP tool-level failure: honest error envelope, no fabricated success.
        return { denied: false, invocation_id: invocationId, status: "error",
                 error: { code: "tool_denied", message: String(resp.result.message ?? "tool reported isError"), retryable: false } };
      }
      return { denied: false, invocation_id: invocationId, status: "ok", result: resp.result };
    } catch (err) {
      return { denied: false, invocation_id: invocationId, status: "error",
               error: { code: err.code ?? "transport_error", message: String(err.message), retryable: err.retryable ?? true } };
    }
  }
}
