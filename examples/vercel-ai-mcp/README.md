# SupremeAI × Vercel AI SDK — Node.js MCP Agent (reference)

> **Issue:** #43 · **Contract surface:** MCP Tower (`/sse` + JSON-RPC `tools/*`) · **Deps:** optional (zero-dep fallback built in)

A clean TypeScript reference for binding **SupremeAI MCP Tower tools** into the
**Vercel AI SDK** tool surface: connect via the official
`@modelcontextprotocol/sdk` (preferred) or a built-in zero-dependency fetch
bridge, expose the tools to `generateText` / `streamText`, and run a
deterministic CLI demo — offline by default.

## `npm start` (bootstrap + run)

The Touching Files boundary for issue #43 is `index.ts` + `README.md` only —
so `package.json` is bootstrapped on first run (one-time, no manual editing):

```bash
cd examples/vercel-ai-mcp
npm init -y                                             # one-time
npm pkg set type=module scripts.start="tsx index.ts"    # one-time
npm i tsx                                               # one-time (TS runner)

npm start                       # offline demo: embedded mock tower, zero deps
npm i @modelcontextprotocol/sdk ai   # optional: official SDK + AI SDK paths
npm start -- --self-test        # harness reports the active mode
npm start -- --live --base-url=https://supremeai-mcp-tower.onrender.com
```

`bun` users can skip the bootstrap entirely: `bun index.ts --self-test`.

## How it works

```
┌────────────────────┐   GET /sse (?client=…)    ┌──────────────────────┐
│      index.ts      │ ─────────────────────────▶│ SupremeAI MCP Tower  │
│                    │◀──── event: endpoint ─────│  (session announce)  │
│  tools/list        │   POST /messages?…        │                      │
│  tools/call        │ ─────────────────────────▶│  JSON-RPC 2.0        │
│                    │◀──── result envelope ─────│  repo_read, …        │
└────────┬───────────┘                           └──────────────────────┘
         │ mcpToolsToAiSdkTools(transport)
         ▼
┌─────────────────────────────────────────────────────┐
│ Preferred: @modelcontextprotocol/sdk Client         │  ← when installed
│   + Vercel AI SDK: ai.tool({ parameters: jsonSchema │
│     (inputSchema), execute })                       │
│ ── or (zero-dep) ──                                 │
│ fetch-bridge transport + plain-shaped tools with    │
│ the identical execute(args) surface                 │
└─────────────────────────────────────────────────────┘
```

1. **Session announce** — `GET /sse` streams `event: endpoint` with the
   message POST URL; identity rides `?client=vercel-ai-mcp-agent`.
2. **Transport** — official `Client` + `SSEClientTransport` when the SDK is
   installed (responses correlated on the SSE stream); otherwise the fetch
   bridge (inline POST responses). Same tool surface either way.
3. **Conversion** — each `tools/list` declaration becomes an AI SDK tool:
   `ai.tool({ description, parameters: ai.jsonSchema(inputSchema), execute })`
   (pydantic-free; the tower's JSON Schema is used as-is), or a plain fallback
   object with the same shape.
4. **Demo loop** — `repo_read → agent_status → repo_read` with `inv-*`
   correlation ids and honest outcomes `{ok, invocation_id, result, error}`.

## Wiring `generateText` / `streamText` (bring your own model)

```ts
import { generateText } from "ai";
import { yourModel } from "your-provider";        // e.g. @ai-sdk/openai
import { mcpToolsToAiSdkTools, connect } from "./index.ts";

const transport = await connect("https://supremeai-mcp-tower.onrender.com",
                                "vercel-ai-mcp-agent", process.env.SUPREMEAI_API_KEY);
const tools = await mcpToolsToAiSdkTools(transport);

const { text } = await generateText({
  model: yourModel("…"),
  tools,                       // ← MCP tower tools, AI-SDK native
  prompt: "Summarize docs/MCP_CONNECT.md and report agent status.",
});
```

Model providers are intentionally **not** bundled: the tower integration and
the model wiring are independent concerns, and the demo must run offline.

## MCP → AI SDK mapping

| MCP declaration | Vercel AI SDK surface |
|---|---|
| `name` | tool key in the record passed to `generateText({ tools })` |
| `description` | `tool.description` (agent-visible) |
| `inputSchema` (JSON Schema) | `parameters: ai.jsonSchema(inputSchema)` |
| `tools/call` result `{content, isError}` | `execute(args) → {ok, invocation_id, result, error}` |
| transport/auth | `Authorization: Bearer $SUPREMEAI_API_KEY` header — never in URLs |

## Honest limitations

- **Dual-mode responses:** the fetch bridge reads inline POST bodies; the
  official SDK correlates replies on the SSE stream. The embedded mock tower
  answers **both ways** so one harness exercises both transports.
- **Single session:** one connection per run; reconnection/backoff belongs to
  the caller (see `examples/sdk-client-ts/` for the streaming pattern).
- **`initialize` handshake:** handled by the official SDK automatically; the
  fetch bridge skips handshake negotiation because the demo towers answer
  `tools/*` directly.
- **Token spend / rate limits:** towers may answer 429 — the bridge surfaces
  `Retry-After` in the error message (honest, no silent retry loops).

## Verification

```bash
bun index.ts --self-test        # or npm start -- --self-test after bootstrap
bun x tsc --noEmit --strict --target es2022 --module esnext \
  --moduleResolution bundler --lib es2022 index.ts
```

The harness covers: connection (both transports), discovery + conversion
(both tool modes), the 3-call loop, correlation ids, unknown-tool honesty,
dead-tower failure honesty, and clean process exit (explicit `process.exit` —
the official SDK holds its SSE socket open by design).
