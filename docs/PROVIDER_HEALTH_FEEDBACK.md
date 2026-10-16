---
id: provider-health-feedback
title: "Provider Health Feedback Contract — Runtime LLM Outcomes → Failover Routing"
document_role: specification
status: draft
canonical: true
owner: auditor
last_verified: 2026-10-16
governing_issue: 283
related_docs:
  - AGENT_RULES.md
  - docs/CONSUMERS.md
  - docs/AGENT_LOOP_SPEC.md
  - docs/HEARTBEAT_PROTOCOL.md
  - docs/AUTONOMY_LOOP_CONTRACT.md
---

# Provider Health Feedback Contract — Runtime LLM Outcomes → Failover Routing

> **What this document is:** a draft contract for closing the provider-health feedback gap — the missing path from *runtime LLM call outcomes* back into *failover routing decisions*. BN: রানটাইম LLM কলের ফলাফল থেকে ফেইলওভার রাউটিংয়ে ফিডব্যাক পৌঁছানোর নেই থাকা চুক্তির খসড়া নকশা।
>
> **Origin:** the founder-directed full-project audit (bridge WO #283, 2026-10-16) identified this gap as intelligence item **G3**. The WO record was closed unlanded during board cleanup; this document carries the item forward independently so the design is not lost.
>
> **Status:** `draft` — nothing here is implemented yet. This contract deliberately requires **zero schema changes** and **zero behavior changes** to existing shipped code; it only defines the shape a future implementation must take.

---

## 1. Problem — the feedback gap (evidence-anchored)

Three shipped primitives describe provider health today, and none of them consumes the most valuable signal:

| Shipped primitive | What it declares | What it cannot do |
|---|---|---|
| `api-schemas/provider-registry.schema.json` | The LLM provider SSOT: capability, `errorCode` failure classes (`rate_limited`, `timeout`, `provider_unavailable`, `auth_failure`, `quota_exhausted`, `context_overflow`, `content_filter`, `upstream_error`), the `errorAction` mapping, and the **static** `failover_cascade` / per-provider `failover.priority` | Its cascade is a declaration frozen at edit time — a provider that is actively failing keeps its declared priority until a human edits the registry |
| `src/health/snapshot.ts` (`HealthSnapshot`, `HealthCache`) | Probe-based health for **integration** providers (Render, GitHub, Redis, …): status `healthy\|degraded\|down\|circuit_open\|unknown`, latency, `consecutiveFailures`, 30 s cache TTL | Probes never see LLM call outcomes; the LLM lane produces no `HealthSnapshot` |
| `src/health/history.ts` (`HealthHistoryStore`) | Bounded history of sweep results | Same — LLM runtime outcomes are not recorded there |

**The gap, precisely.** The schema's own description says consumers must "branch on this code only — never on raw upstream payloads", and `errorAction` prescribes the single per-call action (`retry`, `backoff_then_retry`, `failover`, `abort`). So per-call recovery is specified. What is *not* specified is anything **between** the per-call action and the static declaration: when `failover` fires repeatedly because a provider is degraded, nothing remembers it, and the next cascade is built identically to the last one.

**Zero-Admin consequence.** Under the Zero-Admin doctrine (docs/ZERO_ADMIN_GUIDE.md, AGENT_RULES.md) "wait for a human to edit the registry" is the worst available answer. The federation's autonomy loop needs the routing floor to be self-correcting; a human edit may only be needed for the *unusual* case, never for the *normal* degradation case.

**Shipped-but-unconsumed check (2026-10-16, main `0c378d4`):** no TypeScript file under `src/` references the `errorCode` vocabulary or `failover_cascade` — the schema contract is declared; the feedback loop it implies does not exist.

## 2. Non-goals

- **No auto-remediation beyond routing.** This contract never buys quota, rotates keys, or edits provider credentials — `adapters/ai/key-pool.ts` remains the sole owner of key material.
- **No SLA claims.** A grade is a routing hint derived from a bounded window, not a promise.
- **No cross-tenant telemetry.** Observations are global to the Tower process/namespace, never per-tenant attributable.
- **No schema churn.** The runtime grade lives in the health store, never inside `provider-registry.schema.json` (see §3.6).
- **No new failure modes for callers.** Every consumer path is fail-open (§3.6, §4).

## 3. The contract

### 3.1 Observation record (the signal)

Every handled LLM provider call outcome MAY append exactly one observation:

| Field | Type / vocabulary | Source |
|---|---|---|
| `provider_id` | `providerId` pattern from the registry schema (`^[a-z][a-z0-9-]*$`) | the called provider |
| `error_code` | one of the registry's 8 `errorCode` values, or `ok` for success | the same normalization every consumer already branches on |
| `latency_bucket` | `lt_2s` \| `2_10s` \| `10_30s` \| `gt_30s` | coarse bucket only — never a raw duration, never a payload |
| `observed_at` | epoch milliseconds | call completion |

Rules:

1. **No payloads, no prompts, no completions, no key material, no tenant identifiers.** Class codes and coarse buckets only.
2. **Observations are advisory facts**, never commands. The grade derivation (§3.3) is the only consumer of raw observations.
3. **`ok` observations are mandatory input.** Without successes in the window, a restore can never be proven (§3.3).

### 3.2 Store & window

- Reuse the `HealthHistoryStore` pattern (bounded, in-memory, optional durable mirror) under the key namespace `supremeai:provider-health:<provider_id>`.
- Sliding window **W = 15 minutes** per provider, bounded to the most recent **64** observations per provider (oldest dropped first — no unbounded growth).
- The store MUST be **fail-open**: if the durable layer is unavailable, the in-memory window continues to work; if even that is unavailable, consumers see an empty store and fall back to declared routing (§3.4). A feedback store outage must never be a routing outage.

### 3.3 Derived grade + hysteresis

The grade is a **pure function of the current window contents** — same window, same grade, no wall-clock dependence beyond `observed_at`. This keeps it compatible with deterministic test harnesses.

| Grade | Enter when (in-window) | Leave when |
|---|---|---|
| `unavailable` | `auth_failure` observed (the provider refuses the credential, not the traffic), OR ≥ 8 failures of any class | manual reset or window rollover making the condition false, then restore rule met |
| `degraded` | ≥ 3 failures among `timeout`, `provider_unavailable`, `rate_limited`, `quota_exhausted`, `upstream_error` AND failure ratio ≥ 0.5 (min 4 observations) | 5 consecutive `ok` observations after a ≥ 60 s soak since the last failure |
| `healthy` | default when none of the above hold | — |

Hysteresis rules (anti-flap):

1. **No decision on a single observation.** Thresholds above are floors, not tuning suggestions; implementations may raise them, never lower them.
2. **Restore requires successes.** Only `ok` observations restore a grade; the passage of time alone never does.
3. **`content_filter` and `context_overflow` are excluded** from grade math entirely — they are request-shape problems, not provider-health problems (a provider correctly refusing one oversized request is healthy).
4. **`unknown`** is the grade for a provider with an empty window — it routes exactly like `healthy` (fail-open by default) and is distinct only for observability.

### 3.4 Consumption — cascade-building algorithm

The consumer is the (future) cascade builder. It MUST build routes like this:

```text
1. base      := declared failover_cascade (global) or provider.failover ordering
2. filtered  := base minus providers graded `unavailable`
3. demoted   := providers graded `degraded` or `unknown`… (see below)
4. final     := filtered, sorted by (grade_bucket, declared priority, id)
                 grade_bucket: healthy=0, unknown=1, degraded=2
5. untouched := retry_policy and errorAction mapping — the per-call contract
                 from the registry schema remains authoritative; this contract
                 NEVER rewrites retry behavior
```

Binding rules:

1. **The declared cascade is the floor.** With an empty/unreadable store, `final == base` byte-for-byte. No store, no change.
2. **`id` is the final tiebreak** so the same window always yields the same route (determinism, same doctrine as the agent loop envelope).
3. **`unavailable` providers are skipped, not deleted.** They re-enter automatically the moment their grade restores (§3.3) — no admin action, no registry edit.
4. **One grade read per build.** The builder takes one consistent snapshot of grades per cascade build; it must not interleave reads mid-build.

### 3.5 Observability surface

Two additive options, in recommended order:

1. **`ai.provider_health` (recommended first):** a new read-only MCP tool returning `{provider_id, grade, window: {observations, failure_ratio, last_error_code, observed_at}, entered_at}` per tracked provider. Smallest blast radius; follows the existing read-only tool family (`ai.list_providers`, `ai.available_providers`).
2. **Health-sweep integration (later):** surface provider grades as `HealthSnapshot`-compatible entries inside the existing dependency sweep, with `evidence.kind: "provider_response"` and `consecutiveFailures` derived from the same window. Only after option 1 has proven the grade logic in production traffic.

### 3.6 Versioning

- **No schema change is required to implement this contract.** The runtime grade lives in the health store (§3.2), not in `provider-registry.schema.json`.
- If grades are ever *persisted into* the registry file, that is an **additive MINOR** bump under the schema's own versioning rule ("MINOR bumps are additive-only"); this contract must never trigger a MAJOR bump.
- Contract text itself follows semver discipline in its title if revisions ever fork behavior: breaking consumption changes = MAJOR rewrite of this document, not silent edits.

### 3.7 Privacy & Zero-Admin compliance

- Observations carry **no content, no credentials, no tenant identity** (§3.1) — safe to store, log, and expose.
- Key material stays inside `adapters/ai/key-pool.ts`; the feedback store's key namespace (`supremeai:provider-health:*`) must never overlap or intermix with key-pool namespaces.
- The grade is derivable by any admin from the observation window alone — no hidden state, matching the Zero-Admin guide's "no secret state" posture.

## 4. Implementation notes — mapping to shipped anchors

| Contract element | Shipped anchor (main `0c378d4`) | Note |
|---|---|---|
| `error_code` vocabulary | `api-schemas/provider-registry.schema.json` → `$defs.errorCode` | reuse the enum verbatim; never fork the class list |
| Record shape precedent | `src/health/snapshot.ts` → `HealthSnapshot.evidence {kind, summary}` | the observation record is the same philosophy: classified fact + bounded summary |
| Store precedent | `src/health/history.ts` → `HealthHistoryStore` | bounded, oldest-dropped, optional durable mirror |
| Cache/TTL precedent | `src/health/snapshot.ts` → `HealthCache` (30 s default TTL) | grade reads SHOULD be cached ~30 s to bound recompute cost |
| Producer points | `src/adapters/ai/*` call paths; `ai.test_provider` tool | test-provider results are legitimate observations, flagged as such if exposed |
| Consumer | new cascade builder reading declared `failover_cascade` / `failover.priority` | §3.4 algorithm; the only new decision logic |
| Read surface | `ai.list_providers`, `ai.available_providers` | option 1 of §3.5 joins this family |
| Advisory doctrine | `docs/CONSUMERS.md` §৬ — "AI-আউটপুট = advisory, non-blocking" | the feedback path is itself advisory: routing must survive its total absence |

## 5. Verification checklist (implementer-facing)

1. **Determinism:** same window contents + same declared cascade ⇒ byte-identical built route (including `id` tiebreak).
2. **Hysteresis:** unit tests with an injected observation source — degrade threshold, restore soak, single-failure no-op, excluded classes (`content_filter`, `context_overflow`) never affecting the grade.
3. **Fail-open:** empty store, store-throw, and durable-layer-outage paths all yield `final == base` (declared order), with no exception escaping the consumer.
4. **Bounded growth:** >64 observations in a window provably drop oldest; no unbounded map/queue.
5. **Skip-not-delete:** an `unavailable` provider re-enters the route automatically on grade restore — assert no state persists the skip beyond the window.
6. **No schema delta:** implementing this contract adds zero bytes of required change to `api-schemas/provider-registry.schema.json` (its `schema_version` stays untouched).
7. **Key-pool isolation:** grep-level boundary check — no `provider-health` namespace string appears in or near key-pool code paths.
8. **Boundary guard:** any implementation respects the repo's public/private boundary rules (AGENT_RULES.md); no private surface names leak into this contract's public artifacts.

## 6. Related Documents

- [api-schemas/provider-registry.schema.json](../api-schemas/provider-registry.schema.json) — the provider SSOT this contract feeds back into
- [docs/CONSUMERS.md](./CONSUMERS.md) — consumer contract and the advisory/non-blocking doctrine (§৬)
- [docs/AGENT_LOOP_SPEC.md](./AGENT_LOOP_SPEC.md) — the autonomy loop that benefits from self-correcting routes
- [docs/HEARTBEAT_PROTOCOL.md](./HEARTBEAT_PROTOCOL.md) — task-lease health signals (analogous feedback discipline for agents)
- [docs/AUTONOMY_LOOP_CONTRACT.md](./AUTONOMY_LOOP_CONTRACT.md) — autonomy lifecycle boundaries
- [AGENT_RULES.md](../AGENT_RULES.md) — agent policy constitution (document circle, fail-closed guards, §8 navigation policy)
