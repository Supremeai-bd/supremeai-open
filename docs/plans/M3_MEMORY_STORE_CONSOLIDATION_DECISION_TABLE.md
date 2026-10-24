---
id: m3-memory-store-consolidation-decision-table
title: "M3/L4.1 — Memory Store Consolidation: Keep / Merge / Archive Decision Table"
document_role: architecture
status: active
canonical: true
owner_circle: Memory Circle
target_scope: supremeai_internal
last_verified: 2026-09-25
supersedes: []
superseded_by: []
depends_on:
  - docs/audits/M0_D_DORMANT_MODULE_DECISIONS.md
  - docs/audits/ISOLATED_COMPONENTS_AND_ORPHAN_ROUTES_CATALOG.md
  - docs/plans/PLAN_004_LETTA_STYLE_MEMORY_DISTILLATION_2026-09-17.md
---

# M3/L4.1 — Memory Store Consolidation Decision Table

> **বাংলা:** HEAD_OF_PLANNING L4 লেভার ও রিচেক অডিট র‍্যাংক #8 — "১৫+ প্রতিযোগী memory store = সবচেয়ে বড় architectural debt; প্রথম deliverable শুধু keep/merge/archive টেবিল"। এই ডকুমেন্ট সেই টেবিল। উদ্দেশ্য: (১) PLAN_004-এর distillation যেন **doomed store-এ না লেখা হয়** — canonical store ঘোষণা করা; (২) প্রতিটি মডিউলের ভাগ্য এক জায়গায় রেকর্ড করা, যাতে L2 orphan-spine ধাপে deletion সহজ হয়।
>
> পদ্ধতি: প্রতিটি মডিউলের জন্য ripgrep import-graph trace (production callers vs tests) + docstring/head read — 2026-09-17 main-এ। "Imported by" কলামের প্রমাণ এজেন্ট-যাচাইকৃত (tests/ বাদে)।

## Canonical declaration (single source of truth)

**Long-term "Eternal Brain" store = Supabase `ai_memory` table (pgvector, 384-dim) accessed via `services/memory_service.py::CascadeMemoryService`, exposed through `core/unified_memory.py::UnifiedMemoryInterface`.**

- Write path: `UnifiedMemoryInterface.store_long_term_memory` → `CascadeMemoryService.store_memory` (INSERT INTO `ai_memory`), embedding from summary (`memory_service.py` `_embed` → `core/embeddings.py`).
- Read paths: `query_context` (pgvector RPC `match_ai_memories` + cosine fallback), `core/ai_memory/vector_store.py` (tenant-scoped upsert/search), `core/memory/auto_rag_injector.py` (SSE chat injection).
- Schema authority: `database/supabase/ai_memory_phase_c.sql` (Phase C EXECUTED — `docs/database/AI_MEMORY_PHASE_C_EXECUTION_EVIDENCE.md`); contract test `tests/models/test_ai_memory_schema_contract.py`.
- PLAN_004 distillation writes **here only** (existing metadata JSON column — zero schema change).

Secondary live tiers (kept, deliberately separate concerns):
- **Short-term context:** `memory/sliding_window.py` (token-budgeted, SQLite-persisted) — PLAN_002 compaction operates in-session above it.
- **Knowledge/episodic vectors:** `memory/chromadb_store.py` (knowledge indexer, QA service, episodic memory, MCP memory server).
- **Task checkpoints:** `tools/checkpoint_manager.py` (pooled Postgres + write-behind batching).

## Decision table

| # | Module | Production callers (non-test) | Verdict | Rationale & action |
|---|---|---|---|---|
| 1 | `services/memory_service.py` (CascadeMemoryService) | 15+ files (chat routes, orchestrators, context sources, deep research, …) — heaviest fan-in | **KEEP — canonical** | Single long-term store. All new memory features write here. |
| 2 | `core/unified_memory.py` (UnifiedMemoryInterface) | syncguard, unified_memory_api, browser_routes (lazy ×2) | **KEEP — facade** | The Eternal Brain facade; PLAN_004 distillation lands here. |
| 3 | `core/ai_memory/vector_store.py` (FreeTierOptimizedVectorStore) | core/memory_manager (lazy), auto_rag_injector (lazy), mission suite | **KEEP** | Supabase `ai_memory` read/write companion (batched upsert, tenant-scoped). |
| 4 | `core/memory/auto_rag_injector.py` | stream_chat_sse, core/memory/__init__ | **KEEP** | Recall injection for SSE chat; silent-degradation fixed by audit G-3. |
| 5 | `memory/sliding_window.py` | core/unified_memory, api/routes/memory, memory/mcp_server (lazy) | **KEEP** | Canonical short-term tier; PLAN_002 foundation. |
| 6 | `memory/chromadb_store.py` | rag_pipeline, episodic_memory, unified_db_manager†, knowledge_base_indexer, knowledge_qa | **KEEP** | Anchors the knowledge/episodic vector side; LOW_MEMORY_MODE fallback exists. †its orphan importer's deletion does not affect it. |
| 7 | `memory/supabase_store.py` | unified_db_manager†, living_brain (lazy) | **KEEP (watch)** | Provider-detecting pgvector adapter with SQLite fallback; living_brain uses it lazily. ~455 lines — split candidate, not merge candidate. |
| 8 | `memory/sqlite_store.py` | supabase_store (base class), unified_db_manager†, tools/billing/cost_auditor | **KEEP** | Load-bearing by inheritance (`SupabaseStore` IS-A `SQLiteMemoryStore`) + cost auditor. |
| 9 | `memory/mcp_server.py` | **0 Python importers — subprocess-wired**: `infrastructure/mcp-control-plane/src/adapters/memory/index.ts` launches it | **KEEP** | Not dead: process-level wiring to the MCP Control Tower. 895-line monolith — split candidate for a later plan. |
| 10 | `memory/episodic_memory.py` | reasoning_orchestrator, self_reflection, synthetic_data_pipeline | **KEEP** | Live episodic tier (ChromaDB); default `:memory:` db noted as follow-up hardening item. |
| 11 | `memory/long_term_memory.py` (MemoryManager → `agent_memories` table) | api/routes/chat (lazy), reasoning_orchestrator, playwright_browser_agent | **KEEP — flag** | Second live Supabase table (`agent_memories`). NOT canonical; candidates for future absorption into `ai_memory` (L4 follow-up, separate plan — needs data migration, out of scope here). |
| 12 | `core/memory_manager.py` (FreeTierMemoryManager) | core/app middleware, startup/agents, self_evolution (lazy) | **KEEP — reclassify** | **Not a memory store** (RAM/GC manager for 512MB tier). Name trap; excluded from store decisions. |
| 13 | `core/intelligence/synaptic_memory.py` | intelligence package, chat (lazy), intelligence_insights | **KEEP** | Governance/consolidation singleton over dicts; storage-neutral, no store duplication. |
| 14 | `core/circles/centers/memory_center.py` | FCC center registry → kernel dispatcher | **KEEP** | Capability-circle adapter (memory.recall/store via rag_pipeline worker thread). |
| 15 | `memory/rag_pipeline.py` | mcp_server (lazy), memory_center (lazy) | **KEEP** | RAG over ChromaDB; both consumers lazy but real. |
| 16 | `memory/checkpoint_resume.py` | api/routes/memory | **MERGE (candidate, low urgency)** | Thin duplicate facade over CheckpointManager already exposed by core/unified_memory; shadow-prone fallback import (`from checkpoint_manager import`). Action: routes should use the facade directly; module deleted in L2 pass. |
| 17 | `memory/hierarchical_tree.py` | services/ingestion/context_collector — which itself has **0 production consumers** | **ARCHIVE (dormant chain)** | Effectively dead end-to-end; deletion belongs to the L2 orphan-spine step (with context_collector), not a hot fix. |
| 18 | `memory/unified_db_manager.py` | **0** (M0-D repaired import, deferred verdict here) | **ARCHIVE** | Fan-out manager with no production entrypoint; exports unused DI provider. Its children (#7/#8/#6) live on through other importers. Delete in L2. |
| 19 | `memory/cloud_postgres_store.py` | unified_db_manager only (orphan-by-transitivity) | **ARCHIVE** | Transitively dead; 0 tests; schema verify-only. Delete in L2 (check alembic `g2b3c4d5e6f7` note first). |
| 20 | `memory/summary_tree.py` | **0** | **ARCHIVE** | Naive summarizer overlapping hierarchical_tree; test-only usage. Delete in L2. |
| 21 | `memory/vector_store_config.py` | **0** | **ARCHIVE** | Dead config dataclass — no store consumes it. Delete in L2. |
| 22 | `memory/checkpoint_resume.py` | see #16 | — | (same row as #16) |

**Scorecard:** KEEP 15 (incl. 1 reclassified as non-store, 1 flagged for future absorption, 1 watch) · MERGE 1 · ARCHIVE 5 (all deferred to L2 orphan-spine deletion pass with knip gate on).

## Consequences for PLAN_004 (why this unblocks distillation)

- Distillation writes to the **canonical** `ai_memory` path (#1→#2) — no distilled data lands in any ARCHIVE-listed module.
- `metadata["memory_structure"]` + `metadata["distilled"]` provenance flag travel in the existing JSON column — if a future L4 follow-up absorbs `agent_memories` (#11) into `ai_memory`, distilled provenance survives.
- ARCHIVE deletions are **not** done in this document (they touch import graphs + knip baseline) — they execute in the queued L2 orphan-spine step, keeping this table cheap and safe.

## Update rule

Any change to the memory module topology (new store, deletion, merge) must update this table in the same PR. The canonical declaration may only change with a founder-level decision record.

---

## Re-verification 2026-09-25 (Wave 3.3, issue #1259 — WAVE_MASTER_PLAN §Wave 3)

Fresh audit of main @ e46af6a (exploration report) re-verified the table's
core claims and adds two structural findings. **No verdict changes.**

### Verified claims (spot-checks, byte-safe grep)
- ✅ #1 `CascadeMemoryService` — still the heaviest fan-in (26 prod importer files + 13 test)
- ✅ #9 `memory/mcp_server.py` — **subprocess-wiring re-confirmed**:
  `infrastructure/mcp-control-plane/src/adapters/memory/index.ts:34-37` launches it
  (`python memory/mcp_server.py`) — the fresh audit's "0 importers = orphan"
  first read was wrong; process-level wiring is real. Verdict **KEEP** stands.
- ✅ #8 `SQLiteMemoryStore` — still load-bearing by inheritance + cost_auditor
- ✅ Canonical declaration unchanged: Supabase `ai_memory` (pgvector) via
  CascadeMemoryService, exposed by UnifiedMemoryInterface.

### New structural finding 1 — two parallel SQLite fallback engines
`services/memory_service.py` re-implements its own inline sqlite3 fallback
(`data/memory.db`; import sqlite3:7, db_path:146, connect sites 256/425/578/610/…)
SEPARATE from `memory/sqlite_store.py` (SQLiteMemoryStore, the base class of
SupabaseStore). Consequence: two engines maintain fallback-schema divergence.
**Action (sequenced, NOT this wave):** extract the fallback engine into
SQLiteMemoryStore (or a shared base) so `ai_memory`-unavailable degradation
flows through ONE engine. Data risk = none if the extraction keeps
`data/memory.db` schema byte-compatible; needs its own issue + migration test.

### New structural finding 2 — facade adoption is the bottleneck
`core/unified_memory.py` (the declared facade) has only 4 direct prod
importers while CascadeMemoryService is imported directly by 26. The
consolidation lever is NOT merging store files (big-bang merge stays
FORBIDDEN per the 2026-09-25 plan audit) — it is **routing new callers
through the facade** and migrating existing direct importers in small
verified batches. L2 orphan-spine deletions (#16-#21) remain gated on the
knip pass as the table already mandates.

### Wave gate contribution
Memory domain: ০ fake-assurance (all live stores verified), consolidation
direction locked (facade-first, no big-bang), two structural risks registered
with owners. Plan row 3.3 = audit-doc deliverable SATISFIED.

