// mock_tower.mjs — offline MCP tower mock (issue #332 test harness).
//
// Surface:
//   POST /mcp              initialize (issues mcp-session-id) / notifications / tools/list / tools/call
//   GET  /sse              SSE leg: announces an endpoint frame
//   POST /mcp-sse-session  the endpoint the SSE leg announces (same JSON-RPC surface)
//   GET  /private          401 probe
// Run directly for a smoke: node src/mock_tower.mjs
import { createServer } from "node:http";

const SESSIONS = new Map(); // sessionId -> {initialized: bool}

function json(res, status, obj, headers = {}) {
  const raw = JSON.stringify(obj);
  res.writeHead(status, { "Content-Type": "application/json", ...headers });
  res.end(raw);
}

function rpcHander(req, res, body) {
  const rpc = JSON.parse(body);
  const sid = req.headers["mcp-session-id"];
  if (rpc.method === "initialize") {
    const newSid = `sess-${Math.random().toString(16).slice(2, 10)}`;
    SESSIONS.set(newSid, { initialized: false });
    json(res, 200, {
      jsonrpc: "2.0", id: rpc.id,
      result: { protocolVersion: "2025-03-26", capabilities: { tools: {} },
                serverInfo: { name: "mock-skills-tower", version: "1.0.0" } },
    }, { "mcp-session-id": newSid });
    return;
  }
  if (rpc.method === "notifications/initialized") {
    if (sid && SESSIONS.has(sid)) SESSIONS.get(sid).initialized = true;
    res.writeHead(202).end();
    return;
  }
  if (!sid || !SESSIONS.has(sid)) {
    json(res, 200, { jsonrpc: "2.0", id: rpc.id ?? null,
                     error: { code: -32001, message: "unknown session - initialize first" } });
    return;
  }
  if (rpc.method === "tools/list") {
    json(res, 200, { jsonrpc: "2.0", id: rpc.id, result: {
      tools: [{ name: "repo_read", description: "read a repo path" },
              { name: "repo_write", description: "write a repo path" }],
    } });
    return;
  }
  if (rpc.method === "tools/call") {
    const name = rpc.params?.name ?? "";
    if (name === "repo_write") {
      // The mock enforces its own server-side boundary too: writes are denied.
      json(res, 200, { jsonrpc: "2.0", id: rpc.id,
                       result: { content: [], isError: true, message: "server-side deny: repo_write" } });
      return;
    }
    json(res, 200, { jsonrpc: "2.0", id: rpc.id,
                     result: { content: [{ type: "text", text: `echo:${name}` }],
                              tool: name, echo: rpc.params?.arguments ?? {} } });
    return;
  }
  json(res, 200, { jsonrpc: "2.0", id: rpc.id ?? null,
                   error: { code: -32601, message: `unknown method ${rpc.method}` } });
}

export function startMockTower(port = 0) {
  const server = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => { body += c; });
    req.on("end", () => {
      if (req.method === "POST" && (req.url.startsWith("/mcp") || req.url.startsWith("/mcp-sse-session"))) {
        try { rpcHander(req, res, body); } catch {
          json(res, 200, { jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } });
        }
      } else if (req.method === "GET" && req.url.startsWith("/sse")) {
        res.writeHead(200, { "Content-Type": "text/event-stream" });
        res.write("event: endpoint\ndata: /mcp-sse-session\n\n");
        res.end();
      } else if (req.url.startsWith("/private")) {
        json(res, 401, { error: "unauthorized" });
      } else {
        json(res, 404, { error: "not found" });
      }
    });
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve({
    server,
    baseUrl: `http://127.0.0.1:${server.address().port}`,
  })));
}

if (process.argv[1] && process.argv[1].endsWith("mock_tower.mjs")) {
  const { server, baseUrl } = await startMockTower(0);
  console.log(`mock skills tower on ${baseUrl} (ctrl-c to stop)`);
  const stop = () => server.close(() => process.exit(0));
  process.on("SIGINT", stop);
}
