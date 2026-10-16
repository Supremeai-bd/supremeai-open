---
id: memory-sidecar-contract
title: "Semantic Memory Retrieval Sidecar — Interface Contract (Tower ↔ Python Memory Server)"
document_role: specification
status: active
canonical: true
owner: auditor
last_verified: 2026-10-16
governing_issue: 36
related_docs:
  - AGENT_RULES.md
  - docs/CONSUMERS.md
  - docs/AGENT_LOOP_SPEC.md
---

# Semantic Memory Retrieval Sidecar — Interface Contract

> **What this document is:** the formal interface contract between the MCP Control Tower and the Python Memory Server sidecar — the component that owns semantic memory retrieval (vector search, RAG ingestion, episodic similarity, learned facts). The interface is **already shipped**; this document codifies it so sidecar implementations can evolve against a stable public contract and new sidecar engines can be evaluated against the same rules. BN: টাওয়ার ও Python মেমরি সার্ভার সাইডকারের মধ্যে আন্তঃপৃষ্ঠ চুক্তি — সিমান্টিক মেমরি রিট্রিভালের স্থিতিশীল পাবলিক নিয়ম।
>
> **Codified at:** main `fe5fbbb` (2026-10-16). Every rule below is anchored to shipped code paths, live-probe evidence, or both. Where the code and this document ever disagree, the code is the bug source and one of them must be fixed — silent divergence is a defect.

---

## 1. Scope & parties

| Party | Surface | Responsibility |
|---|---|---|
| **Control Tower** (TypeScript) | `src/adapters/memory/index.ts` (`MemorySubAdapter`), `src/tools/memory.tools.ts`, `src/adapters/memory/jsonSchemaToZod.ts` | process lifecycle, discovery, namespace bridging, tenant injection, schema conversion, error classification, visibility |
| **Memory sidecar** (Python) | `backend/memory/mcp_server.py` over STDIO MCP | owns all memory semantics: knowledge graph, vector store, RAG, episodic records, learned facts |

**The one design law:** the sidecar is a real MCP server over a real MCP client connection (Law #9 — MCP is the universal interface; never a bespoke HTTP shape). Everything else in this contract follows from that choice.

## 2. Transport & lifecycle contract

1. **Transport:** STDIO (`StdioClientTransport`), child env `MEMORY_MCP_TRANSPORT=stdio`, working directory = resolved backend dir, full parent environment inherited.
2. **Entry point resolution (launcher ladder):**
   - `<backendDir>/.venv/bin/python` (win32: `.venv\Scripts\python.exe`) when present and executable — fast path;
   - otherwise `uv run --directory <backendDir> python memory/mcp_server.py`.
3. **Backend directory resolution:** `SUPREMEAI_BACKEND_DIR` env when it actually contains `memory/mcp_server.py`; otherwise the layout default. A missing env path falls back **with a loud one-line diagnostic**, never silently (#2612). A missing entry file at both paths = no spawn attempt + honest `lastError`.
4. **Start:** eager and non-blocking (kick off at tool-registration time), idempotent, single-flight — concurrent starters share one promise.
5. **Stop:** `close()` raced against a 3 s timeout; teardown can never block gateway shutdown.
6. **Respawn:** on-demand and lazy. Any transport error stops the client; the next `callTool`/`listTools` attempts a fresh start. No background restart timers.

## 3. Discovery & namespace contract

1. **Fully dynamic:** the tower exposes **every** tool the sidecar discovers, prefixed `memory.` — a new Python tool appears with **zero TypeScript changes**. This is the core extensibility promise of the sidecar boundary.
2. **Discovery cache:** 60 s. A failed discovery stops the sidecar and returns an empty inventory (never a partial one).
3. **Cold-start ladder (degradation, not failure):**
   - **Live inventory** when the sidecar is connected;
   - **Static fallback snapshot** (the 20-tool `FALLBACK_TOOLS` set mirroring `backend/memory/mcp_server.py` names: knowledge graph, vector store, RAG, episodic, context-builder, learned-facts families) when discovery returns empty — so clients still see the memory surface while the sidecar cold-starts;
   - **Honest absence** when the deployment bundles no Python runtime: calls fail with an explicit non-transient "Memory sidecar unavailable — no Python runtime in this deployment" message (see §6).
4. Every bridged description carries the provenance suffix `[proxied to Python memory sidecar as '<tool>']` — clients can always tell a bridge from a native tool.

## 4. Schema contract

1. Sidecar tools declare standard JSON Schema `inputSchema`; the tower converts JSON Schema → Zod (`jsonSchemaToZod.ts`) for the gateway's `server.tool()` API.
2. **Covered dialect:** `string`, `number`, `integer`, `boolean`, `array`, `object`, `enum`, plus `description`/`default`/`required`/`items`/`properties`.
3. **Permissive fallback:** anything exotic converts to a permissive schema — **a malformed or exotic sidecar schema must never break the gateway's tool advertisement** (graceful degradation is mandatory on this boundary).
4. The tower never hardcodes per-tool schemas on this bridge. Per-tool schema logic belongs in the sidecar, where the semantics live.

## 5. Tenant isolation contract

1. **`tenant_id` is always injected server-side.** The sidecar's call gate requires a non-empty, non-`default` tenant id (#1440), and **no client-claimed tenant id is ever trusted**: the tower resolves the caller's tenant from the authenticated request context.
2. **Explicit override is global-admin-only** (`isGlobalAdmin` + explicit non-`default` value). Everyone else gets their resolved tenant id (`tenant_default` when unresolvable).
3. Consequence for sidecar implementers: you may rely on `tenant_id` being present and correct in every call; you must never accept it as an authorization decision by itself.

## 6. Result envelope & error classification

Every `callTool` returns the same envelope — the sidecar boundary's universal shape:

```text
{ ok: boolean; data?: unknown; error?: string; transient?: boolean }
```

| Situation | Result | Contract meaning |
|---|---|---|
| Sidecar returns text content | `ok: true`, text parts joined, `JSON.parse` if it parses, else the raw string | best-effort data normalization, never a failure |
| Sidecar returns `structuredContent` | `ok: true`, data = structured content (fallback: whole result) | structured preferred when offered |
| Transport/call error | `ok: false, transient: true`, sidecar stopped | **transient** — caller should retry after respawn |
| No Python runtime in deployment (spawn `ENOENT` on both launch paths) | `ok: false, transient: false` + explicit "no Python runtime in this deployment" message | **permanent for this deployment** — retrying is pointless; the message names the actual cause and the local-store alternative (#1441 diagnostics rule: never surface a bare `spawn uv ENOENT`) |
| Sidecar not yet started | `ok: false, transient: true` + "startup in progress" | expected during cold-start; retry shortly |

Rules: error strings are **actionable** (they name the resolved command, the env var involved, or the deployment-level cause); the `transient` flag is the caller's retry contract — no caller may retry a non-transient failure.

## 7. Semantic retrieval surface (the intelligence boundary)

The sidecar's reason to exist: semantic memory retrieval. The contract names the six families the loop and agents consume — these are the **stability surface**; renames or reshapes of these are breaking changes (§9):

| Family | Tools (fallback snapshot names) | Consumer |
|---|---|---|
| Vector store | `store_document`, `search_semantic`, `ingest_document_rag` | RAG flows, knowledge grounding |
| Episodic memory | `record_task`, `get_similar_tasks`, `get_recent_episodes` | agent-loop past-experience grounding (docs/AGENT_LOOP_SPEC.md consumers) |
| Learned facts | `remember_fact`, `search_learned_facts` | durable cross-session knowledge |
| Context assembly | `build_context`, `get_session_stats`, `clear_session` | token-budget-aware prompt building |
| Knowledge graph | `create_entities`, `create_relations`, `add_observations`, `delete_*`, `read_graph`, `search_nodes`, `open_nodes` | structured relationship memory |

**Intelligence tie-in:** past-experience grounding for the autonomy loop (before-work recall via `get_similar_tasks`, after-work outcome recording via `record_task`) rides entirely on this boundary — the loop stays schema-agnostic and contract-driven, so sidecar-side improvements (better embeddings, smarter chunking) upgrade loop intelligence with zero loop-side changes.

## 8. Observability

`memory.status` (always registered, even on cold start) exposes exactly: `ready`, `toolCount` (live count, else fallback count), `startAttempts`, `lastError`. Honest introspection only — no invented "healthy" when the sidecar has never spawned. The `lastFailure` getter mirrors the same truth to internal callers.

**Live evidence (2026-10-16, Tower guest session):** `tools/list` advertises 9 tools, none `memory.*` — memory tools are visibility-scoped to authenticated tenants, exactly as the visibility policy layer (src/policy/tool-visibility.ts) intends. Advertisement absence for guests is correct behavior, not a defect.

## 9. Versioning & evolution rules

1. **Additive sidecar change** (new tool, new optional arg, richer description): always allowed; the tower picks it up within one discovery cache cycle. No tower change, no contract change.
2. **Breaking sidecar change** (rename/remove of a §7 stability-surface tool, required-arg addition, envelope change): requires a MAJOR note in this contract and a tower-side migration window — the fallback snapshot and this document must be updated in the same change.
3. **Visibility is tower-owned forever.** The sidecar never decides who sees a tool; the tower's visibility policy does (guest probe in §8).
4. **The envelope is frozen.** `{ok, data, error, transient}` is the boundary's ABI. Sidecar errors map into it; they never replace it.

## 10. Verification checklist (implementer-facing)

1. **Zero-TS-change rule:** adding a Python tool makes it appear under `memory.*` within one cache cycle, with converted schema and provenance suffix — no TypeScript edit.
2. **Ladder:** sidecar killed → discovery returns fallback snapshot; spawn impossible → honest non-transient message naming the deployment cause; slow start → "startup in progress" transient.
3. **Tenant injection:** non-admin client sending `tenant_id: "other"` gets the server-resolved tenant, never the claimed one; global admin override works; unauthenticated/default resolves to `tenant_default`.
4. **Envelope:** every path in §6 returns the exact envelope with the correct `transient` flag.
5. **Never-break-gateway:** a sidecar tool with an exotic schema still advertises (permissive fallback) and cannot crash registration.
6. **Lifecycle bounds:** single-flight start (N concurrent starts → 1 spawn); stop bounded by 3 s; no background timers.
7. **Boundary guard:** no private-surface names or credentials cross this contract's public artifacts (AGENT_RULES.md).

## 11. Related Documents

- [docs/AGENT_LOOP_SPEC.md](./AGENT_LOOP_SPEC.md) — the autonomy loop consuming episodic retrieval (`get_similar_tasks` / `record_task`)
- docs/PROVIDER_HEALTH_FEEDBACK.md (WO #306, queued) — sibling contract with the same envelope-plus-grade philosophy; link to be added once it lands
- [docs/CONSUMERS.md](./CONSUMERS.md) — consumer-side error semantics and the advisory/non-blocking doctrine
- [AGENT_RULES.md](../AGENT_RULES.md) — agent policy constitution (document circle, boundary guards, §8 navigation policy)
