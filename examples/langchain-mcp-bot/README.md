# SupremeAI × LangChain MCP Bot (reference implementation)

> **Issue:** #42 · **Contract surface:** MCP Tower (`/sse` + JSON-RPC `tools/*`) · **Deps:** none required (LangChain optional)

A self-contained reference showing how to bind **SupremeAI MCP Tower tools** into **LangChain**: connect over SSE, discover tool declarations, convert them to `StructuredTool` instances, and run a sample multi-tool invocation loop — with an honest, zero-dependency fallback so the whole pipeline runs **offline**.

## Quickstart

```bash
# 1) Offline end-to-end harness (no deps, no network):
python bot.py --self-test
#    → Self-test (mock MCP tower): 11/11 checks passed
#      mode: SimpleTool fallback (offline)   [or: LangChain StructuredTool]

# 2) Optional: exercise the real LangChain path
pip install langchain-core          # >= 0.3 (pydantic v2 comes with it)
python bot.py --self-test
#    → mode: LangChain StructuredTool

# 3) Optional: run against the live Tower (network + credential)
export SUPREMEAI_API_KEY=...           # Tower credential — header-only, never in URLs
python bot.py --live --base-url https://supremeai-mcp-tower.onrender.com
```

## How it works

```
┌──────────────┐  GET /sse (?client=…)   ┌──────────────────────┐
│   bot.py     │ ───────────────────────▶│  SupremeAI MCP Tower │
│              │◀──── event: endpoint ───│  (session announce)  │
│  tools/list  │  POST /messages?…       │                      │
│  tools/call  │ ───────────────────────▶│  JSON-RPC 2.0        │
│              │◀──── result envelope ───│  repo_read, …        │
└──────┬───────┘                         └──────────────────────┘
       │ to_structured_tool(declaration)
       ▼
┌─────────────────────────────────────────────┐
│ langchain_core.tools.StructuredTool         │  ← when langchain-core installed
│   (pydantic args model from inputSchema)    │
│ ── or ──                                    │
│ SimpleTool (offline fallback, same surface) │  ← zero-dep mode
└─────────────────────────────────────────────┘
```

1. **Session announce** — `GET /sse` returns `event: endpoint` carrying the
   message POST URL for this session (`?client=langchain-mcp-bot` identity).
2. **Discovery** — `tools/list` returns declarations: `name`, `description`,
   JSON-Schema `inputSchema`.
3. **Conversion** — each declaration becomes a tool:
   - **With LangChain:** `StructuredTool.from_function(func=…, coroutine=…,
     args_schema=<pydantic model built from inputSchema>)`.
   - **Without:** `SimpleTool` — same `name` / `description` / args surface /
     `ainvoke({...})`, so the demo is identical in both modes.
4. **Multi-tool loop** — a sample plan (`repo_read` → `agent_status` →
   `repo_read`) is executed with per-call correlation ids (`inv-*`); every
   outcome is honest data (`ok`, `result`, `error{code,message,retryable}`),
   never a silent swallow.

## MCP → LangChain mapping

| MCP declaration | LangChain surface |
|---|---|
| `name` | `StructuredTool.name` |
| `description` | tool description (agent-visible doc) |
| `inputSchema.properties` | pydantic args model fields (`create_model`, types mapped string/integer/number/boolean) |
| `tools/call` result `{content, isError}` | `ainvoke({...}) → {"ok", "invocation_id", "result", "error"}` |
| transport/auth | `Authorization: Bearer $SUPREMEAI_API_KEY` header — **never** in URLs |

## Honest limitations

- **Dual-mode responses:** the reference uses the POST response body (towers
  that answer inline). Towers that deliver JSON-RPC replies **asynchronously
  on the SSE stream** would need stream correlation by `id` — deliberately out
  of scope here; see `docs/MCP_CONNECT.md` for the full transport contract.
- **Sync path caveat:** `StructuredTool`'s sync `.run()` uses `asyncio.run`
  and is only valid outside a running event loop; the demo always awaits
  `ainvoke()`.
- **Single session:** one SSE session per run; reconnection/backoff belongs to
  the caller (the SDK clients in `examples/sdk-client-py/` show the pattern).
- **`agent_status` shape:** mock returns a text payload; live towers may
  return structured content — the loop prints raw results either way.

## Verification

```bash
python -m py_compile bot.py        # boot smoke
python bot.py --self-test          # offline harness (exit 0 = pass)
python scripts/agents/continuous_agent_loop.py --verify-only   # repo contract
```

The embedded harness covers: SSE endpoint announce, `tools/list` discovery,
`inputSchema` carry-through, conversion (both modes), the 3-call loop,
correlation ids, unknown-tool honesty, and dead-tower `TransportError`.
