---
id: implementation-plan-index
subject: "docs/plans — Implementation Plan (Master, Reconciled)"
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
canonical: true
status: active
evidence_state: partial
disposition: retain
last_verified: 2026-09-17
supersedes: []
superseded_by: []
target_scope: supremeai_internal
---

# docs/plans — Implementation Plan (Master, Reconciled)

> **Purpose:** Consolidated implementation direction for the current SupremeAI codebase.
> **Rule:** Existing plans are historical design inputs; this file records the current execution order where plans overlap or conflict.

---

## 0. Current Architecture Direction

SupremeAI follows:

```text
User Goal
  ↓
Intent / Context
  ↓
Capability + Resource Discovery
  ↓
Reusable Implementation Discovery
  ↓
Cost / Risk / Quality / Authorization evaluation
  ↓
reuse / compose / adapt / delegate / generate
  ↓
execute
  ↓
verify
  ↓
learn + promote safely
```

The system must optimize **work avoided**, not merely infrastructure added.

---

## 1. Bootstrap Brain — Current Priority

Source plans:

- `docs/ADMIN_TASKS/SUPREMEAI_BOOTSTRAP_BRAIN_AND_DECISION_LOGIC_PLAN.md`
- `docs/ADMIN_TASKS/implementation_plan.md`

### Decision

`discover_reusable_implementation` is logically available for **every `dev` task**.

It is tiered:

```text
L1: memory / semantic cache
 ↓ miss
L2: internal code / docs / registered capabilities
 ↓ miss
L3: external GitHub / OSS / official SDK / compatible source
```

L3 is policy- and expected-value-gated. Therefore “always enabled” does **not** mean “always perform an expensive web/GitHub search.”

### Methodology decision

The methodology is selected **after discovery**:

```text
reuse → compose → adapt → delegate → generate_new_code
```

Greenfield code is the fallback.

### Required finishing work

- bootstrap seed
- L1/L2/L3 discovery service
- planner wiring
- resource/authorization discovery
- advisor contract
- brain metrics
- verification + governed promotion

---

## 2. Free-Tier Scaling — Reconciled Direction

Source plans:

- `docs/plans/features/free_tier_production_upgrade_plan_v2.md`
- `docs/plans/infrastructure/free_tier_federation_master_plan.md`
- `docs/plans/features/free_tier_scaling_constitution_and_compliance_policy.md`
- `docs/plans/features/multi_cloud_free_tier_federation_master_plan_v3.md` (archived; superseded by v4)

### Architectural decision

Free tiers are **optimization surfaces**, not correctness dependencies.

Preferred order:

```text
cache
→ deduplicate
→ reuse
→ batch
→ async queue
→ authorized user-owned resource
→ suitable free/low-cost provider
→ paid burst only when necessary
```

### Important correction

The old federation concept must **not** treat account multiplication as an unlimited quota multiplier.

Do not build production correctness around:

- rotating multiple accounts solely to multiply quotas
- stealth keep-alives
- fake browser interaction to defeat idle policies
- CAPTCHA/anti-abuse circumvention
- turning interactive notebook free tiers into hidden permanent worker fleets

Multiple resources are valid when they represent legitimate ownership, tenant, security, environment, or provider-supported separation.

### Provider roles

```text
Firebase / CDN
  → static frontend and delivery

Cloudflare
  → edge routing, cache, validation, lightweight logic

Render
  → lean control plane / API

Supabase
  → durable state and memory

Upstash
  → hot cache, locks, queue/rate limiting where appropriate

GitHub Actions
  → repository-native CI/build/test work

Kaggle
  → optional batch/research workloads

Colab
  → optional interactive/admin research; never a required production worker
```

### Quota rule

All quota values must be treated as **provider-versioned configuration**, not hard-coded architectural guarantees.

---

## 3. Missing Services Integration — Reconciled

Source: `docs/plans/MISSING_SERVICES_INTEGRATION_PLAN_V4.1.md`

The existing plan correctly emphasizes:

- secret management
- Eternal Brain / pgvector
- multi-model routing
- resilience
- observability
- **Browser automation** → `architecture/browser_automation.md`

But implementation should be driven by current code evidence rather than the plan's historical “missing” label.

Before implementing any listed item:

```text
inspect current code
→ confirm missing
→ check existing equivalent
→ measure need
→ implement only if still required
```

Do not create duplicate services when the capability already exists elsewhere.

---

## 4. Production Upgrade — Reconciled

Source: `docs/plans/PRODUCTION_UPGRADE_PLAN.md` and `docs/PRODUCTION_READINESS_PLAN_V3.md`

Enterprise targets such as 99.99% uptime or sub-100ms P95 are **future target (planned)**, not current guarantees.

Free-tier production work should prioritize:

1. startup correctness
2. authentication/security correctness
3. tenant isolation
4. DB indexes/query efficiency
5. connection pooling where justified
6. websocket/resource caps
7. graceful degradation
8. observability
9. rollback/readiness
10. measured load testing

Kubernetes/microservices should not be introduced merely because an old plan contains them. Introduce them only after measured bottlenecks justify the additional maintenance/cost.

---

## 5. Storage and Memory

Source: `docs/FREE_TIER_STORAGE_PLAN.md`

The Eternal Brain should follow:

```text
hot working state
→ recent episodic state
→ validated semantic/procedural knowledge
→ compressed/archive artifacts
→ delete disposable data
```

Do not store every raw intermediate artifact indefinitely.

The memory system should optimize for:

- retrieval quality
- provenance
- confidence
- verification
- reuse
- storage efficiency

---

## 6. Resource-as-Capability

This is now a first-class architectural rule.

When a user/admin legitimately connects a service, SupremeAI should inspect:

```text
what it can do
what permissions exist
what limits exist
what it costs
what data boundary applies
```

Then register usable capabilities without taking ownership of the user's resource.

Example:

```text
User connects GitHub
   ↓
inspect authorized repo/actions capabilities
   ↓
repository-native task?
   ↓
use GitHub-native execution where appropriate
   ↓
verify
   ↓
return result
```

A user's resource must never silently become shared infrastructure for another tenant.

---

## 7. External Implementation Discovery

For any task requiring new implementation:

```text
Estimate missing capability
   ↓
search internal capability/memory/docs
   ↓
search known implementation registry
   ↓
if worthwhile → external discovery
   ↓
license + provenance + security + compatibility + maintenance review
   ↓
reuse/adapt/compose
   ↓
only then create missing code
```

This is the principal mechanism for reducing greenfield implementation over time.

---

## 8. Cost Intelligence

Every execution path should eventually expose:

```text
estimated_cost
actual_cost
latency
quota_pressure
maintenance_cost
risk
verification_history
```

The cheapest path is **not automatically the path with $0 provider price**.

A free service that requires fragile manual operation or creates unacceptable reliability risk may be more expensive operationally than a small paid burst.

Therefore optimize for:

> **minimum sustainable total cost of ownership.**

---

## 9. Self-Evolution

SupremeAI's learning loop:

```text
real problem
 ↓
capability gap
 ↓
reuse/discovery/delegation analysis
 ↓
execution
 ↓
verification
 ↓
lesson candidate
 ↓
confidence + provenance evaluation
 ↓
quarantine if uncertain
 ↓
governed promotion
 ↓
future reuse
```

A failed execution is data, not automatically knowledge.

---

## 10. Implementation Priority

### P0 — Correctness and security

- verify current production blockers
- tenant isolation
- secret handling
- authentication
- DB integrity
- migration correctness

### P1 — Brain decision loop

- bootstrap brain
- L1/L2 discovery
- discovery-first methodology
- resource/authorization discovery
- verification

### P2 — Efficiency

- semantic cache
- task deduplication
- artifact hashing
- batch execution
- quota-aware admission
- backpressure

### P3 — External capability ecosystem

- MCP capability registry
- GitHub-native workflows
- approved browser delegation
- external provider adapters
- L3 reusable implementation discovery

### P4 — Self-evolution

- lesson promotion
- capability creation
- sandbox validation
- rollback
- routing optimization from historical outcomes

### P5 — Scale validation

- concurrency tests
- queue stress tests
- provider failure tests
- quota exhaustion tests
- cache/reuse measurements
- heavy-task admission tests

---

## 11. Acceptance Criteria

Do not declare this architecture “complete” because the documents exist.

Demonstrate with tests that:

- similar dev tasks increasingly reuse existing capability
- every dev task has access to reusable-implementation discovery
- expensive external discovery is avoided when internal evidence is sufficient
- `generate_new_code` is a fallback
- provider failure does not destroy core task state
- user authorization boundaries are enforced
- repeated work is deduplicated
- queue/backpressure prevents overload
- new knowledge is not promoted without verification
- the system can operate without any single optional provider
- free-tier changes do not require an architectural rewrite

---

## 12. Plan Governance

When a new plan is added to `docs/`:

1. identify which existing plan it supersedes
2. inspect current code before marking work “missing”
3. avoid duplicate implementations
4. record assumptions and external limits
5. define verification criteria
6. assign an owner/status
7. reconcile it into this master plan

This prevents plan sprawl from becoming an architecture problem.


---

## 13. Proposed Plan Candidates — Reconciliation Register (2026-09-17)

Per the strengthened [PLAN_LIFECYCLE_POLICY.md](PLAN_LIFECYCLE_POLICY.md) (2026-09-17): a candidate list is not an execution queue (rule 10). The entries below are `proposed` candidates awaiting explicit founder approval; **none is executable** until one is approved as the single active plan (Gate 2/6).

| Plan | Status | Scope (one line) | Resource delta | Reconciliation note |
|---|---|---|---|---|
| [PLAN_002 — Claude Code-style semantic context compaction](PLAN_002_CLAUDE_STYLE_CONTEXT_COMPACTION_2026-09-16.md) | **complete** (founder-verified: implemented 2fbe7fcd, closed fb2ce032 — row reconciled 2026-09-17 per policy rule 11; was "proposed") | Replace silent `deque(maxlen=50)` eviction in WS chat with summarization-based compaction on the existing zero-cost chain | 0 dep / 0 infra / 0 CI | Complementary to PLAN_001 (cache ≠ compaction); supports §1 discovery-first, §2 efficiency, §10 P1; Gate 0 evidence in plan Part 1.5 |
| [PLAN_003 — Aider-style repo map (stdlib-ast)](PLAN_003_AIDER_STYLE_REPO_MAP_2026-09-17.md) | **complete** (founder-verified: implemented 6a2e0464 — `backend/core/code_indexer.py` + DynamicPlanningEngine wiring + tests; row reconciled 2026-09-17 per policy rule 11; was "proposed") | Give the Epistemic Probe real codebase vision: stdlib-ast symbol graph + pure-Python PageRank + budgeted render into CODER-domain probe input | 0 dep / 0 infra / 0 CI / 0 LLM | Implements first real basis of §1 discovery-first ("discover_reusable_implementation" is currently aspiration — grep-verified); complementary to PLAN_001/002 (different problem spaces) |
| [PLAN_004 — Letta/ChatGPT-style write-time memory distillation](PLAN_004_LETTA_STYLE_MEMORY_DISTILLATION_2026-09-17.md) | **complete** (founder-verified: implemented + closed 4575104f — `distill_content` + `store_long_term_memory_distilled` in core/unified_memory.py, syncguard writer switched, kill-switch SUPREMEAI_MEMORY_DISTILL; row reconciled 2026-09-17 per policy rule 11; was "proposed") | Replace the Eternal Brain's literal `content[:200]  # Placeholder` summary with LLM-distilled summary + structured facts on the existing facade, opt-in per call site, honest fallback | 0 dep / 0 infra / 0 CI / 0 schema | Implements Constitution #11 (Memory Must Compound) at the write path; complementary to PLAN_002 (in-session compaction ≠ persistent memory distillation); Gate 0 evidence in plan frontmatter (unified_memory.py L57–58, memory_service.py L306); kill-switch SUPREMEAI_MEMORY_DISTILL |
| [PLAN_005 — Claude Code-style user-controlled /compact trigger](PLAN_005_USER_CONTROLLED_COMPACT_TRIGGER_2026-09-17.md) | proposed | Intercept `/compact [instructions]` in the WS chat loop to run the implemented `_compact_history()` on demand with honest ack + threshold guard — user control on top of PLAN-002 machinery | 0 dep / 0 infra / 0 CI / 0 frontend | Builds directly on founder-implemented PLAN-002 (2fbe7fcd, complete); only existing-code touch is an additive return-type on `_compact_history`; complementary to PLAN_003/004 (different subjects); /map and auto-compaction UI explicitly out-of-scope; Gate 0 evidence in plan Part 1 |
| [PLAN_006 — mem0/ChatGPT-style write-time memory consolidation](PLAN_006_MEM0_STYLE_MEMORY_CONSOLIDATION_2026-09-17.md) | proposed | Similarity-gated dedup + update-on-conflict + importance_score/updated_at wiring in CascadeMemoryService.store_memory (pg path) on the implemented M3 canonical ai_memory store — user-scoped probe, env kill-switch SUPREMEAI_MEMORY_DEDUP, honest INSERT fallback | 0 dep / 0 infra / 0 CI / 0 LLM / 0 schema | Builds on founder-implemented PLAN-004 (4575104f, complete) + M3 canonical store; write-time **identity** ≠ PLAN-004 write-time **quality**; ERR-F02 module-consolidation complementary (different granularity); cross-user dedup never (tenant isolation); Gate 0 evidence in plan Part 1.5 |