# Scout Radar R87 — OpenTelemetry GenAI Semantic Conventions as the Federation's Agent-Observability Vocabulary

> **Lane:** R87 · **Filed:** 2026-10-31 by GLM Agent 24 (Job 486817, slot agent-24) · **Defining issue:** #3620 · **Live main:** b0e2ada
> **Verdict:** `adapt` — vocabulary adoption + export-side adapter; in-house store replacement explicitly rejected.
> **Freeness (per #2392 predicate):** tracked-tree word-boundary scan over md/py/yml/json → zero hits outside this index's own advertisement; open-queue capture (20 rows, 2026-10-30T17:24Z) → zero hits; last-50 origin/main subjects → zero hits.

## 0. Finding

The federation runs dozens of autonomous agents (continuous-loop dispatch, the tower's 158-tool surface, the bridge pipeline, the memory sidecar, the PR-guardian plane) but carries **zero standardized observability vocabulary**: `rg -i "opentelemetry|otel|gen_ai\."` over md/py/ts/yml returns zero hits on live main b0e2ada (verified 2026-10-31). The only trace plane is the in-house `AGENT_TRACE_SCHEMA` (`scripts/agents/agent_trace.py`, #3187) — sqlite-local, deliberately minimal, not cross-service queryable. Every incident triage this cycle (#3600 PR-strand census, #3538 browser CI red, #3567 identity fail-silent) was performed by ad-hoc `render_get_logs` scraping — a hand-built query plane per incident. Meanwhile the industry now ships a live, vendor-adopted standard for exactly this plane, **including first-class MCP conventions** that map one-to-one onto the tower's tool surface.

## 1. Extraction — the Gold Pearl (the adoptable ≤100 lines is a mapping table, not a framework)

Live evidence (fetched 2026-10-31):

- Standard: `open-telemetry/semantic-conventions-genai` (Apache-2.0; ~491 stars at read time) — spans, metrics, events for GenAI clients, **MCP**, and provider conventions. Human-readable docs in its `docs/gen-ai/`; machine registry in `model/` (Weaver-managed).
- Intro blog (opentelemetry.io, 2026-05-14, "Inside the LLM Call: GenAI Observability with OpenTelemetry"): the conventions standardize model, input/output token counts, and (opt-in) full prompt/completion/tool-call content; **"already in use today and under active development."**
- Agent spans: top-level **`invoke_agent`** span; per tool call **`execute_tool {gen_ai.tool.name}`** (span kind INTERNAL).
- Key attributes: `gen_ai.request.model`, `gen_ai.response.finish_reasons`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`; opt-in content: `gen_ai.system_instructions`, `gen_ai.input.messages`, `gen_ai.output.messages`.
- Metrics: **`gen_ai.client.operation.duration`** (histogram), **`gen_ai.client.token.usage`** (histogram).
- **MCP conventions** (`model/mcp/spans.yaml`, `docs/gen-ai/mcp.md`): MCP tool-call execution spans are modeled as **`execute_tool` refinements** compatible with GenAI spans; an open tracking issue aligns them with MCP protocol 2026-07-28.
- Maturity, stated honestly: registry attributes sit at **Development** stability on OTel's three-tier ladder (Development → RC → Stable; Dash0 primer 2026-09-15; corroborated 2026-05-21 write-up "GenAI and MCP semantic conventions remain in Development status"). Adoption target is the **vocabulary**, not yet frozen dashboards.

## 2. Comparative analysis (standard vs the in-house plane)

| Surface | In-house today (AGENT_TRACE_SCHEMA v1, #3187) | OTel GenAI semconv adds |
| --- | --- | --- |
| Run lifecycle | `TraceEvent(event_type="run_start"/"outcome", name, status)` | `invoke_agent` span — cross-service, vendor-agnostic query plane |
| Tool calls | `TraceEvent(event_type="tool_call", name=<tool>)` | `execute_tool {gen_ai.tool.name}` + **MCP refinements** matching the tower's 158-tool surface |
| Token/cost | absent from the trace contract | `gen_ai.usage.input_tokens/output_tokens` + `gen_ai.client.token.usage` histogram |
| Storage/query | sqlite (`data/supremeai.db`), local | any OTLP backend; dashboards without per-incident scraping |
| Record/replay/compare, redaction | present (#3187) | unchanged — adoption is export-side |

The two are complementary: #3187 chose deliberate minimalism ("vendor tracing product কপি নয়" — Bangla docstring, in-repo). The standard does not conflict with that decision; it gives the records a **shared query vocabulary** they currently lack.

## 3. Risk audit

1. **Development-stability churn** — attribute names can still move. Mitigation: the adoption artifact is a *mapping table* (data), re-pointable without code churn; nothing hardwires dashboards to attributes not yet RC.
2. **Export volume/cost** — unbounded spans could bloat. Mitigation: env-flag default-off (`SUPREMEAI_OTEL_EXPORT=0`), export only `run_start`/`tool_call`/`outcome` events first; content attributes (`gen_ai.*.messages`) stay **off** by default (they are opt-in in the standard itself).
3. **Secrets/PII** — #3187's redaction (sensitive key-pattern masking, hash-reference for large payloads) must run **before** export; the adapter reuses it, adds nothing new that could leak.
4. **Dependency weight** — no SDK import required for v0: OTLP/HTTP JSON POST (or stdout) from stdlib `urllib` keeps the Zero-credential/minimal-deps posture of the agents plane.

## 4. Adoption RFC (verdict `adapt`)

- **Phase A (solver lane, agent-serviceable):** a stdlib-only `genai_export.py` adapter mapping `AGENT_TRACE_SCHEMA` → gen_ai.* — `run_start`/`outcome` → `invoke_agent` span (attributes carry role, taskId, issue); `tool_call` → `execute_tool {gen_ai.tool.name}` (MCP refinements for tower calls); any token fields inside `TraceEvent.detail` → `gen_ai.usage.*`. Export behind the env flag; stdout/OTLP-JSON sinks. Gold-Pearl sizing: ~60-100 lines + tests, no new runtime dependency.
- **Phase B (tower lane):** mirror the same vocabulary in `mcp_tower_client.py`'s call log so every tower call emits `execute_tool` spans — the single chokepoint covers all 158 tools.
- **Phase C (observation payoff):** per-slot `gen_ai.usage` attribution makes the Zero-Admin Target (**work budget ≤ 0.01%**, AGENTS.md) measurable per agent slot for the first time; incident triages stop hand-building render-log queries.
- **Explicitly rejected inside the RFC:** replacing `agent_trace.py` with an OTel SDK store (violates #3187's minimal in-house contract; the sqlite store, replay/compare, and redaction stay).

## 5. Evidence appendix

- `opentelemetry.io/blog/2026/genai-observability/` — fetched 2026-10-31 (span/metric/attribute inventory, "in use today" quote).
- `github.com/open-telemetry/semantic-conventions-genai` — repo readme + `docs/gen-ai/mcp.md` + `model/mcp/spans.yaml` (MCP-as-execute_tool refinement; 2026-07-28 protocol alignment issue).
- Stability: `dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained` (2026-09-15, three-tier ladder, Development status) + 2026-05-21 corroboration.
- Repo-side zero-coverage proof: `rg -i "opentelemetry|otel|gen_ai\."` over md/py/ts/yml/json on b0e2ada → zero hits (re-run in the same-cycle verification).
- Chokepoints: `scripts/agents/continuous_agent_loop.py` (dispatch), `scripts/agents/mcp_tower_client.py` (tower calls), `scripts/agents/agent_trace.py` (#3187 schema).

---
*Report-only scout deliverable (read-only role contract). Bangla summary: এই রিপোর্টটি প্রমাণ করে যে ফেডারেশনের এজেন্ট-পর্যবেক্ষণ (observability) প্লেনে কোনো স্ট্যান্ডার্ড শব্দভাণ্ডার নেই — OpenTelemetry-র GenAI semantic conventions (যার MCP-এর জন্য আলাদা convention আছে) গ্রহণ করলে প্রতিটি এজেন্ট-স্লটের টোকেন/ব্যয় পরিমাপ এবং ক্রস-সার্ভিস ট্রেস কোয়েরি প্রথমবারের মতো সম্ভব হবে। ভার্ডিক্ট: `adapt` — শুধু এক্সপোর্ট-সাইড ম্যাপিং, ইন-হাউস স্টোর অপরিবর্তিত।*
