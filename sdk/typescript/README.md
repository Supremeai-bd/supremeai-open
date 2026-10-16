# @supremeai/sdk

Official TypeScript SDK for the **SupremeAI MCP Tower** — the publishable,
packaged form of the validated reference implementation
[`examples/sdk-client-ts`](https://github.com/Supremeai-bd/supremeai-open/tree/main/examples/sdk-client-ts)
(issue #32, landed by PR #318), delivered per the issue-#338 packaging
contract: **dual CJS/ESM builds + complete `.d.ts` declaration maps**.

## Install

```bash
npm install @supremeai/sdk
```

Zero runtime dependencies. Requires Node 18+ (also runs on Bun and browsers —
platform surfaces are reached through `globalThis` only).

## Quick start

```ts
import { createClient, ToolInvocation } from "@supremeai/sdk";

const client = createClient(); // tower URL via SUPREMEAI_MCP_TOWER_URL or default

const health = await client.health(); // credential-free probe

const res = await client.dispatchTask({
  task_id: "task-1",
  issue: "1",
  objective: "Ship the smallest safe change",
  touching_files: ["src/feature.ts"],
});
console.log(res.tier, res.route); // router decision, primary provider first

const tool = await client.invokeTool({
  tool: "repo_read",
  arguments: { path: "docs/" },
  invocation_id: "inv-1", // echoed back on the ToolResult
});
```

## Streaming status (SSE)

Two transports, one frame contract (websocket-events aligned):

```ts
// EventSource-capable runtimes (browsers, Bun, Node 20+)
for await (const frame of client.streamStatus("task-1")) {
  console.log(frame.seq, frame.event);
}

// Any runtime with fetch (Node 18+) — hand-rolled SSE parser
for await (const frame of client.streamStatusFetch("task-1")) {
  console.log(frame.seq, frame.event); // terminal agent:done/error ends stream
}
```

## Error taxonomy (honest failures)

`SdkRateLimited` (429, carries `retryAfterMs` from `Retry-After`),
`SdkForbidden` (403 default-deny RBAC), generic `SdkError` (other statuses).
Tool failures surface as structured, retryable-honest envelopes — never silent.

## Dual builds

| Output      | Module   | Entry                        |
| ----------- | -------- | ---------------------------- |
| `dist/esm`  | ESM      | `import` condition           |
| `dist/cjs`  | CommonJS | `require` condition          |

Both ship `index.d.ts` **and `index.d.ts.map`** (declaration maps, so editor
go-to-definition lands on the original TypeScript source). `scripts/mark-outputs.mjs`
stamps each tree with the correct `package.json#type` and fails closed if a
build pass is missing.

## Development

```bash
npm install   # devDependencies: typescript only
npm test      # builds (pretest) then node --test against dist/esm
```
