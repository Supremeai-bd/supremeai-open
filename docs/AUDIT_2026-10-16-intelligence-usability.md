---
id: audit-2026-10-16-intelligence-usability
title: "Full-project intelligence & usability audit — functional defects, plan-vs-build gaps, customer/admin surface review"
document_role: audit
status: active
canonical: true
owner: agent-orchestration
last_verified: 2026-10-16
related_docs:
  - AGENTS.md
  - AGENT_RULES.md
  - docs/CONSUMERS.md
  - docs/HEARTBEAT_PROTOCOL.md
  - docs/AUDIT_2026-10-16-external-audit.md
source_issue: null
source_pr: null
supersedes: []
superseded_by: []
---

# AUDIT — 2026-10-16 intelligence & usability audit (`supremeai-open`)

**Scope:** every plan-defining doc (AGENTS.md §0–§8, CONSUMERS.md, HEARTBEAT_PROTOCOL.md,
gateway.openapi.yaml) cross-read against the shipped code: MCP Control Plane
(28 tool modules, RBAC/discovery/governance layers, orchestrator engine,
killswitch), agent loop (`continuous_agent_loop.py` 1158 lines), gateway client,
schemas. **Method:** line-level reads at main `bc80a40`; every finding carries a
file:line evidence anchor; live MCP probes where the surface is remote.
**Filing:** each actionable finding below is or will be a Bridge Work Order on
the public repo (zero-credential issue-creation lane, AGENTS.md §2.1 Pathway 1);
ADMIN_DECISION-class items are flagged inline per AGENTS.md §1.3.

## 1. Functional defects (features that will not work correctly)

### F1 — P0: Emergency kill-switch resets on process restart (autonomy is not actually stoppable)

Evidence: `infrastructure/mcp-control-plane/src/remediation/killswitch.ts` —
`KillSwitchManager` is a plain in-memory boolean (`private autonomyEnabled: boolean = true`,
L2–L28). `autonomy.kill_switch` flips it to `false`; **nothing persists it** —
no Redis write (the Redis account chain already exists in the same service:
`lib/redis_chain.js`), no env gate, no boot-time restore.

Impact: Render auto-deploy or a crash-restart silently re-enables autonomy —
an admin's emergency stop to L0 (Read-Only) survives only until the next
restart. For an "emergency stop" primitive this is a correctness defect, not a
hardening nicety.

Fix direction (smallest safe): boot-time `AUTONOMY_DISABLED` env read +
Redis-persisted switch state via the existing chain, fail-closed to DISABLED
when the store is unreachable. **ADMIN_DECISION not required** (no policy
change; strict strengthening of the same primitive), but the persistence
medium choice should be confirmed by the maintainer.

### F2 — P1: `agent_heartbeat` MCP tool violates its own SSOT schema (task-ownership telemetry impossible)

Evidence: `api-schemas/heartbeat.schema.json` (declared SSOT by
`docs/HEARTBEAT_PROTOCOL.md` §2) marks `task_id`, `status`, `ttl_seconds` as
**required** fields. The MCP tool
(`src/tools/agent.tools.ts` L30–86) accepts **only** `slot` + optional
`agentId` — no task, no status, no TTL. Registry entry consequently cannot say
which task a slot is executing.

Impact: (a) an MCP-only agent cannot satisfy the protocol it documents; (b)
orphan-release (HEARTBEAT_PROTOCOL §4) cannot key on `task_id` for
heartbeat-registered slots; (c) the queue-audit report structure (§5) is
unfillable from tower data. Today's `agent-1 expired` triage (#252) needed the
slot-registry cross-check precisely because ownership data was absent.

Fix direction: extend the tool with optional `task_id` / `status`
(alive|busy|idle) / `ttl_seconds` (30–3600), stored on the heartbeat record;
schema stays SSOT. Backward compatible (all fields optional on the wire).

### F3 — P1: Orchestrator "assigns" tasks that no agent will ever see

Evidence: `src/registry/orchestrator_dispatch.ts` L299–332 —
`orchestratorDispatch()` picks an online slot, writes the decision into Redis
state `supremeai:orchestrate:<issueRef>`, `console.log`s the audit line… and
returns. There is **no notification pathway** (no `notify.*` call, no queue
push) and **no agent-side poll tool** — `agent_status` lists workforce state,
nothing reads `orchestrate:*` state for "my assigned tasks".

Impact: the event→role→agent pipeline (issues #1803/#1439 Phase D) routes
decisions into a log, not into work. `decision: assigned` is truthful only in
the sense that a ledger entry exists.

Fix direction: add `orchestrator_my_tasks` (agent-side poll: heartbeat slot →
open assignments) + optional Telegram dispatch notice on `assigned`/`escalate`.

### F4 — P2: Orchestrator `no-candidate` has no re-evaluator — retry promise is unimplemented

Evidence: same file L152–157 — `reason: "retry N/3 on next evaluation"`, but
nothing schedules the next evaluation: no cron re-dispatch, no TTL-based
requeue. If the targeted lane stays offline, the state stays `no-candidate`
until the same event fires again (which for `issues.opened` never happens —
issues open once).

Fix direction: periodic sweep over `orchestrate:*` keys whose `updatedAt` is
older than N minutes and whose decision is `no-candidate` (the tower already
runs scheduled ops in the private lane; a public-side `--reconcile` flag on the
dispatch tool is the smallest public slice).

## 2. Plan-vs-build intelligence gaps (not intelligent enough yet)

### G1 — P1: The loop runs with amnesia — memory sidecar is built but never consumed

Evidence: the tower bridges the full Python memory server
(`src/tools/memory.tools.ts`: knowledge graph, RAG ingest, **episodic task
records** `record_task`/`get_similar_tasks`/`build_context`, long-term
`remember_fact`/`search_learned_facts`) — yet
`scripts/agents/continuous_agent_loop.py` contains zero references to memory
tools (grep: 0 hits). Per AGENTS.md §2 every agent is stateless by lifecycle,
which is correct for authority — but the *federation* is supposed to
accumulate experience, and today each task starts from zero even though the
infrastructure to recall similar past tasks exists one MCP hop away.

Fix direction (public slice): task-envelope gains an optional
`related_experience` block filled via `get_similar_tasks` when a memory
endpoint is configured; completed tasks optionally `record_task` their outcome
signature. Loop stays stateless; the *system* becomes the learner.

### G2 — P2: Routing intelligence = slot-name prefix matching

Evidence: `orchestrator_dispatch.ts` L58–80 — lane identity is derived from
slot-name regex (`^coder-\d+$` …) and a mirrored legacy table. No
load-awareness (two online coders → first match wins, L134 `find`), no
capability scoring, no retry-affinity (a task that failed on agent-3 twice can
be assigned to agent-3 again after `attempts` reset only on success paths).

Fix direction: smallest step = least-recently-assigned selection among online
lane peers (data already in heartbeat records); capability scoring can follow.

### G3 — P2: Gateway routing is static — provider health teaches it nothing

Evidence: `api-schemas/gateway.openapi.yaml` models `model: auto` with a
config-driven router and a 502 "all providers failed" terminal state; nothing
in the public tree feeds provider latency/failure back into ordering. The
plan's §22 provider-agnosticism works, but the *intelligence* half (score-based
fallback ordering, circuit-breaker memory) is unimplemented in the public
surface.

Fix direction: document the intended feedback loop first (plan doc), then
ship `/healthz`-adjacent provider stats so the router (private side) has a
public, testable contract to consume.

## 3. Customer & admin usability review (are all options really usable?)

### U1 — P1: Gateway errors are documented in prose but not in the machine contract

Evidence: `docs/CONSUMERS.md` §3 defines the four error semantics (401/429/502/503)
in a Bangla table; `gateway.openapi.yaml` declares the four status codes
(L32–35) but **defines no error response body schema at all** — no
`components/schemas/Error`, no `Retry-After` header on 429 (the doc *tells*
consumers to honor a header the schema never mentions), no per-status response
`$ref`s.

Impact: a customer building an integration test or a typed client has no
machine-readable truth to code against; the "honor Retry-After" instruction is
unverifiable from the contract. This is the top customer-usability gap on the
only stable public API surface. **Fix WO filed with this audit** (schema-only
change, no behavior claim).

### U2 — P2: `stream: true` is advertised but nothing supports it

Evidence: OpenAPI `ChatCompletionRequest.stream` (L90, default false) — yet the
spec has no `text/event-stream` response for it, and the zero-dependency client
(`examples/gateway_client.py`, 121 lines) has zero streaming code paths.
OpenAI-compatible tooling (Cursor/Aider) defaults to streaming for agents.

Fix direction (honest either way): either declare `stream` unsupported-with-400
in the schema description (smallest, truth-preserving), or spec the SSE shape —
but shipping a silent no-op field is the one option that violates the
honesty doctrine (§सतता in the schema's own Bangla comments).

### U3 — P2: Customer self-visibility ends at the key — no usage/quota introspection surface

Evidence: CONSUMERS.md §2 documents key issue/rotate via monolith admin UI and
§5 promises per-agent quota attribution (`key_id` in usage logs) — but no
public endpoint or documented UI path lets a consumer see their own quota,
rate limits, or usage. Every 429 a customer hits is unexplainable from their
side (no `X-RateLimit-*` headers modeled, no usage endpoint in the stable
contract).

Fix direction: model `X-RateLimit-Limit/Remaining/Reset` headers on
`/v1/chat/completions` + document where usage lands (monolith path) — schema +
docs only.

### U4 — P2: Autonomy kill-switch governance is too loose for a destructive primitive

Evidence: `classifyToolCapability()` (`src/policy/mcp-access.ts` L116+) has no
case for `autonomy_kill_switch`/`autonomy_enable` → they fall to the default
class: `restricted` + `internal` ⇒ **rank ≥ 3 (any agent role) may call
them**; `approvalRequired: false`; the only audit is a `console.error`
(killswitch.ts L12). The discovery layer hides it from guests
(tool-visibility.ts L68) but hide ≠ authorize.

Fix direction: explicit classifier case → `secret`-grade (rank ≥ 4, admin
only) + `approvalRequired: true`; persist an audit record (F1's Redis write is
a natural place). **ADMIN_DECISION flag:** raising the required role is a
policy hardening — filed for maintainer confirmation.

### U5 — P3: WhatsApp notify lane is dead weight in the public surface

Evidence: `notify.send_whatsapp` registered
(`src/tools/notify.tools.ts` L44+) while the env gate guarantees `unconfigured`
(#252 confirmed live: `WHATSAPP_ACCESS_TOKEN` missing). Customers/admins see a
tool that cannot ever succeed until provisioning. Documented as expected state
in TOWER_HEALTH_RUNBOOK §5 — but the tool itself could honestly advertise
"requires env provisioning" in its description to prevent guest confusion.

## 4. What is already good (verified, so nobody re-audits these wrongly)

- RBAC default-deny + live re-authorization + per-identity tool rate limits +
  payload caps + timeouts + output truncation, one choke point
  (`index.ts` L120–279) — genuinely solid governance.
- Discovery filter `list ⊆ call` composition (tool-visibility.ts) with
  fail-closed degraded paths — exemplary.
- Redis account-chain quota rotation with UTC cooldown
  (`orchestrator_dispatch.ts` L166–258) — well-engineered failover.
- Gateway client error taxonomy matches CONSUMERS.md exactly, retries only
  502/503 (`gateway_client.py` L20–33) — honest contract adherence.
- Agent loop: task-envelope, 8-tier verify, parity guard, session dedup —
  all green on main at audit time.

## 5. Intelligence roadmap (priority order)

1. **F1 kill-switch persistence** (P0 — correctness of an emergency primitive)
2. **F2 heartbeat task-ownership fields** (P1 — unlocks §4/§5 of the protocol)
3. **G1 loop↔memory experience block** (P1 — the single biggest
   intelligence win; infra already exists)
4. **F3 orchestrator poll/notify loop closure** (P1 — routing → real work)
5. **U1 error schema + U3 rate-limit headers** (P1 — customer trust surface)
6. **F4 dispatch re-evaluation sweep** (P2)
7. **G2 load-aware lane selection** (P2)
8. **U2 streaming decision** (P2 — decide, then document honestly)
9. **G3 provider-health feedback contract** (P2/P3)
10. **U4 kill-switch role tightening** (P2 — with ADMIN_DECISION)

## 6. Verification statement

Every file:line above was read at main `bc80a40` (2026-10-16). Live probes:
`agent_status` (workforce counts), `system_health` (29/30), `slot_status`
(`Slot not found: agent-1`) — consistent with F2/F3 analysis. No invented
mechanisms: each "Fix direction" names existing primitives
(`lib/redis_chain.js`, `notify.send_telegram`, heartbeat records,
memory-sidecar tools) already shipped in the public tree. No secrets, no
tokens, no env values in this document.
