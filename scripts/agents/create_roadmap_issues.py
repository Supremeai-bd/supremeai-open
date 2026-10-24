#!/usr/bin/env python3
"""
Create GitHub issues for all trackable work items in the
Ecosystem Intelligence Roadmap v2 (docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md).

Source: Priority Execution Order table + key v2 architectural additions.
Governance: AGENTS.md Rule #6 (Bengali comments), proper issue template,
label set: P1-high/P2-medium/P3-low + area:* + ecosystem-learning + group:ecosystem-roadmap.
"""
import json
import os
import sys
import urllib.request

REPO = "SaifulHaqueNiloy/supremeai"
TOKEN = os.environ["GH_TOKEN"]

ISSUES = [
    # ───────────────────────── PHASE 1: Capability Inventory + Orphan Audit ─────────────────────────
    {
        "title": "[Roadmap v2 / P1] Capability Inventory — docs/architecture/CAPABILITY_INVENTORY.md",
        "labels": ["P1-high", "area:architecture", "documentation", "group:ecosystem-roadmap"],
        "body": """## Summary
Create `docs/architecture/CAPABILITY_INVENTORY.md` — a single source-of-truth document listing every integration/adapter, provider, and external dependency in SupremeAI with its current status (active / orphaned / deprecated), config flag, env var, health check, and replaceability assessment.

This is **Phase 1.1** of the Ecosystem Intelligence Roadmap v2. It is the prerequisite for every other roadmap item — you cannot decide what to revive/retire/adopt without first knowing what exists.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 1 → §1.1 SupremeAI Capability Inventory
- Source PR: #4042 (Roadmap v2)

## Acceptance Criteria
- [ ] `docs/architecture/CAPABILITY_INVENTORY.md` exists
- [ ] Every adapter under `backend/integrations/` is listed with status
- [ ] Every provider in `backend/core/llm/provider_registry.py` is listed with config flag + env var + health-check endpoint
- [ ] Every external dependency is listed with: purpose, replaceability assessment, governance tier (Internal / Governed Provider / Research Source)
- [ ] Inventory is machine-readable (YAML front-matter or companion `inventory.yaml`) so the Scout + Auditor pipeline can diff against it
- [ ] CI check (or pre-commit hook) fails if a new adapter/provider is added without an inventory entry

## Touching Files (expected)
- `docs/architecture/CAPABILITY_INVENTORY.md` (new)
- `docs/architecture/inventory.yaml` (new — machine-readable companion)
- `scripts/agents/inventory_lint.py` (new — CI guard)

## Dependencies / Blocks
- **Blocks**: every other Phase 1-5 item (orphan audit, no-new-provider rule, scout pipeline)

## Test Evidence
- `inventory_lint.py` exits 0 on current main
- Adding a stub adapter without an inventory entry fails the lint

## Bengali note (AGENTS.md Rule #6)
অনুক্রমিক ধাপ: প্রথমে ইনভেন্টরি তৈরি → তারপর orphan audit → তারপর সিদ্ধান্ত। ইনভেন্টরি ছাড়া কোনো revive/retire/adopt সিদ্ধান্ত গ্রহণযোগ্য নয়।
"""
    },
    {
        "title": "[Roadmap v2 / P1] Audit orphaned Browser Use adapter → revive-as-governed-provider or retire",
        "labels": ["P1-high", "area:architecture", "provider", "group:ecosystem-roadmap"],
        "body": """## Summary
`backend/integrations/browser_use_adapter.py` is currently marked **orphaned** in the capability inventory. Per Roadmap v2 Phase 1.2, orphan status does NOT automatically mean revive — audit first, then decide.

Run the v2 audit pipeline (upstream maintenance? API compatibility? SupremeAI use-case? benchmark vs alternatives? security review? maintenance cost?) and produce a documented decision: **Revive as Governed Provider / Replace / Retire**.

Roadmap's working hypothesis: Browser Use is mature (117k+ stars) → likely Revive as governed browser provider in the escalation chain `HTTP → Playwright → Browser Use`. But hypothesis ≠ decision; evidence required.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 1 → §1.2 Orphaned Adapter Audit
- Decision matrix row: `browser_use_adapter.py` → Audit → likely Revive

## Acceptance Criteria
- [ ] Audit report committed to `docs/architecture/audits/browser_use_audit.md` with sections:
  - [ ] Upstream status (latest release date, commit cadence, open-issue count)
  - [ ] API compatibility vs `browser_use_adapter.py` current calls
  - [ ] SupremeAI use-case (which agents actually need it? HTTP/Playwright insufficient?)
  - [ ] Benchmark: Browser Use vs Playwright vs raw HTTP on 3 representative tasks
  - [ ] Security review (sandbox isolation, data exfiltration risk, dependency surface)
  - [ ] Maintenance cost assessment
  - [ ] **Decision**: Revive / Replace / Retire (with rationale)
- [ ] If **Revive**: wire into Capability Router + Policy Engine per Phase 2.3 pattern; add health check; add `SUPREMEAI_BROWSER_USE_ENABLED` flag
- [ ] If **Retire**: delete adapter + remove from inventory + document replacement path

## Touching Files (expected)
- `docs/architecture/audits/browser_use_audit.md` (new)
- `backend/integrations/browser_use_adapter.py` (revive or delete)
- `backend/core/llm/provider_registry.py` (if revived — register as governed provider)
- `backend/observability/service_topology.py` (if revived — add health check)

## Dependencies / Blocks
- **Depends on**: Capability Inventory (#roadmap-issue-capability-inventory)
- **Blocks**: Phase 2 Governed Provider pattern for browser tier

## Test Evidence
- Audit report committed
- If revived: health check returns `HEALTHY` (or `CONFIGURED`/`REACHABLE` per #3226 honest states)
- If retired: no orphaned reference remains (grep clean)

## Bengali note (AGENTS.md Rule #6)
Orphan = স্বয়ংক্রিয়ভাবে revive নয়। প্রথমে audit (upstream কি এখনও maintained? API compatible? SupremeAI-তে আসলে দরকার কি?) → তারপর সিদ্ধান্ত। Evidence before adoption।
"""
    },
    {
        "title": "[Roadmap v2 / P1] Audit orphaned OpenHands adapter → revive-as-governed-provider or retire",
        "labels": ["P1-high", "area:architecture", "provider", "group:ecosystem-roadmap"],
        "body": """## Summary
`backend/integrations/openhands_adapter.py` is currently marked **orphaned**. Per Roadmap v2 Phase 1.2, audit first — do not blindly revive.

Roadmap's working hypothesis: OpenHands is the best autonomous coding engine → likely Revive as governed coding execution provider where SupremeAI = orchestrator and OpenHands = executor. But this must be verified with evidence, not assumed.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 1 → §1.2 Orphaned Adapter Audit
- Decision matrix row: `openhands_adapter.py` → Audit → likely Revive

## Acceptance Criteria
- [ ] Audit report committed to `docs/architecture/audits/openhands_audit.md` with sections:
  - [ ] Upstream status (release cadence, breaking changes since adapter was written)
  - [ ] API compatibility vs current `openhands_adapter.py`
  - [ ] SupremeAI use-case (which tasks genuinely need OpenHands vs native coder agent?)
  - [ ] Benchmark: OpenHands vs native coder on 3 representative CI-fix tasks (correctness + latency + cost)
  - [ ] Security review (code execution sandbox, secrets exposure, network egress)
  - [ ] Maintenance cost assessment
  - [ ] **Decision**: Revive / Replace / Retire (with rationale)
- [ ] If **Revive**: wire into Capability Router + Policy Engine; add health check; add `SUPREMEAI_OPENHANDS_ENABLED` flag; document escalation policy (when does SupremeAI delegate to OpenHands vs run native coder?)
- [ ] If **Retire**: delete adapter + remove from inventory + document replacement path

## Touching Files (expected)
- `docs/architecture/audits/openhands_audit.md` (new)
- `backend/integrations/openhands_adapter.py` (revive or delete)
- `backend/core/llm/provider_registry.py` (if revived)
- `backend/observability/service_topology.py` (if revived)

## Dependencies / Blocks
- **Depends on**: Capability Inventory issue
- **Blocks**: Phase 2 coding-execution provider governance

## Test Evidence
- Audit report committed
- If revived: health check `HEALTHY`/`CONFIGURED` per honest-state pattern (#3226)
- If retired: grep clean

## Bengali note (AGENTS.md Rule #6)
OpenHands revive করার আগে audit বাধ্যতামূলক। SupremeAI = orchestrator, OpenHands = executor — কিন্তু এই ভূমিকা ভাগাভাগি শুধু তখনই কাজ করবে যখন benchmark-এ প্রমাণ থাকবে যে OpenHands native coder-এর চেয়ে ভালো।
"""
    },
    {
        "title": "[Roadmap v2 / P1] Wire all active providers into service_topology health dashboard (CONFIGURED / REACHABLE / HEALTHY)",
        "labels": ["P1-high", "area:observability", "area:backend", "group:ecosystem-roadmap"],
        "body": """## Summary
Every active provider must be wired into the existing `service_topology.py` health check with honest tri-state status (`CONFIGURED` / `REACHABLE` / `HEALTHY`), leveraging the #3226 honest-state fix and the #3225 `check_integrations` honesty fix.

This is **Phase 1.3** — Provider Health Dashboard. Without it, the Policy Engine + Router cannot make health-aware routing decisions, and the Evaluation Engine cannot compute reliability scores.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 1 → §1.3 Provider Health Dashboard

## Acceptance Criteria
- [ ] Every provider registered in `provider_registry.py` has a corresponding entry in `service_topology.py`
- [ ] Each entry exposes tri-state: `CONFIGURED` (env set) / `REACHABLE` (TCP+auth ok) / `HEALTHY` (semantic probe ok)
- [ ] No provider reports `HEALTHY` when only `CONFIGURED` (this was the #3225 bug class — do not regress)
- [ ] Health state is queryable via Mission Control admin dashboard
- [ ] Health check failures emit structured logs (per #3415 PII redaction gate)
- [ ] Health state changes trigger webhook/event for the Evaluation Engine (reliability score input)

## Touching Files (expected)
- `backend/observability/service_topology.py`
- `backend/core/llm/provider_registry.py` (provider list)
- `apps/mission-control/` (dashboard surface)
- `backend/observability/health_events.py` (new — event emitter)

## Dependencies / Blocks
- **Depends on**: Capability Inventory (to know the full provider list)
- **Blocks**: Capability Evaluation Engine (needs reliability input), Policy Engine (needs health state)

## Test Evidence
- Unit test: provider with only env var set → status `CONFIGURED` (not `HEALTHY`)
- Unit test: provider unreachable → status `REACHABLE=false`
- Mission Control screenshot showing all providers with tri-state

## Bengali note (AGENTS.md Rule #6)
স্বাস্থ্য পরীক্ষণ সবসময় সত্যি বলবে — `CONFIGURED` মানে `HEALTHY` নয়। এটা #3225 fix-এর মূল শিক্ষা। Router ও Evaluation Engine এই ত্রি-অবস্থা ছাড়া সঠিক সিদ্ধান্ত নিতে পারবে না।
"""
    },
    {
        "title": "[Roadmap v2 / P1] Build Capability Evaluation Engine — correctness + latency + cost + security scoring",
        "labels": ["P1-high", "area:architecture", "area:routing", "ecosystem-learning", "group:ecosystem-roadmap"],
        "body": """## Summary
**THE MISSING COMPONENT identified in v2 feedback.** Without a Capability Evaluation Engine, automatic routing collapses to simplistic heuristics ("Cerebras fast → use Cerebras"). The Evaluation Engine produces evidence-based quality scores that feed the Router and Policy Engine.

This is the roadmap's most important new section (Phase 5.1) and the prerequisite for evidence-based auto-routing.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 5 → §5.1 Capability Evaluation Engine (THE MISSING COMPONENT)
- Architecture diagram: Evaluation Engine sits between Governed Providers and Verification Layer

## Scoring Dimensions (per provider × task-type)
| Dimension | Source | Measurement |
|---|---|---|
| **Correctness** | Benchmark task suite | does output solve the task? (LLM-judge + test-suite) |
| **Latency** | Instrumented calls | p50/p95/p99 ms |
| **Cost** | Provider billing API / cost log | $ per call + $ per task |
| **Reliability** | `service_topology.py` health events | uptime %, error rate |
| **Security** | Static analysis + data-flow audit | data exposure risk score |
| **Tool-use success** | Tool-use benchmark | % of tool calls that succeed |
| **Regression** | Diff vs last benchmark run | quality delta (improvement / degradation) |

## Acceptance Criteria
- [ ] `backend/evaluation/capability_evaluator.py` exists with pluggable scorers per dimension
- [ ] Benchmark task suite committed under `tests/evaluation/benchmark_tasks/` (representative workload per task-type: ci_fix, code_review, research, browser_automation, etc.)
- [ ] Each provider × task-type pair produces a `ProviderScore` JSON record with all 7 dimensions + weighted aggregate
- [ ] Scores persisted to `evaluation_scores` table (Prisma migration)
- [ ] Regression dimension: each new benchmark run diffs against previous — degradation > threshold triggers alert
- [ ] Scores queryable via admin API (`GET /api/admin/evaluation/scores`)
- [ ] Evaluation Engine emits events consumed by Router (re-route on score change) and Policy Engine (cost-limit recalculation)
- [ ] No hardcoded weights — weights are policy-driven (per task-type, admin-configurable per 3-tier routing boundary)

## Touching Files (expected)
- `backend/evaluation/capability_evaluator.py` (new)
- `backend/evaluation/scorers/{correctness,latency,cost,reliability,security,tool_use,regression}.py` (new)
- `tests/evaluation/benchmark_tasks/*.yaml` (new)
- `prisma/schema.prisma` — add `EvaluationScore` model
- `backend/admin/routes/evaluation.py` (new — admin API)
- `apps/mission-control/` — evaluation dashboard surface

## Dependencies / Blocks
- **Depends on**: Provider Health Dashboard (for reliability input), Capability Inventory (to know what to evaluate)
- **Blocks**: 3-Tier Auto-Routing (evidence-based routing impossible without scores), Learning Loop (regression dimension feeds learning)

## Test Evidence
- Unit tests: each scorer produces correct dimension score
- Integration test: 2 mock providers → 2 distinct `ProviderScore` records → Router picks higher-scoring one
- Regression test: provider quality drops → regression dimension flags degradation → alert fires

## Bengali note (AGENTS.md Rule #6)
এটাই v2 feedback-এর সবচেয়ে গুরুত্বপূর্ণ যোগ — Capability Evaluation Engine। এটা ছাড়া "Cerebras fast → use Cerebras" ধরনের simplistic routing হবে, যা evidence-based নয়। Evaluation Engine হলো সেই যন্ত্র যা routing-কে অনুমান থেকে প্রমাণে রূপান্তর করে।
"""
    },
    # ───────────────────────── PHASE 2: Governed Provider Revival + Policy Engine ─────────────────────────
    {
        "title": "[Roadmap v2 / P2] Add Cerebras as governed LLM provider (speed-optimized tier)",
        "labels": ["P2-medium", "area:backend", "provider", "area:routing", "group:ecosystem-roadmap"],
        "body": """## Summary
Add Cerebras as a governed LLM provider in the Provider Registry. Cerebras is the speed-optimized tier (fastest inference for short-form tasks). Must be added as a **Governed Provider** per Phase 2.3 pattern — not a direct dependency.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 2 → §2.2 Governed Provider Integration Matrix (row #5: Cerebras)
- Pattern: §2.3 Governed Provider Pattern

## Acceptance Criteria
- [ ] Cerebras provider registered in `backend/core/llm/provider_registry.py`
- [ ] `SUPREMEAI_CEREBRAS_ENABLED` env flag (default off)
- [ ] `SUPREMEAI_CEREBRAS_API_KEY` fetched via Infisical (not hardcoded — per security gate pattern)
- [ ] Health check in `service_topology.py` (tri-state per #3226)
- [ ] Policy Engine gate: which agents can use Cerebras, max cost per call, fallback to next-speed-tier provider
- [ ] Fallback path documented: Cerebras → OpenAI → DeepSeek → native
- [ ] Evaluation Engine produces Cerebras `ProviderScore` (correctness + latency + cost + security)
- [ ] No Cerebras dependency added to `package.json` / `requirements.txt` unless SDK is genuinely needed (prefer HTTP API)

## Touching Files (expected)
- `backend/core/llm/providers/cerebras.py` (new)
- `backend/core/llm/provider_registry.py` (register)
- `backend/observability/service_topology.py` (health check)
- `.env.example` (flag documentation)
- `docs/architecture/providers/cerebras.md` (governance doc)

## Dependencies / Blocks
- **Depends on**: Provider Health Dashboard, Policy Engine layer, Evaluation Engine (for score)

## Test Evidence
- Provider with flag off → registry skips registration, health check `CONFIGURED=false`
- Provider with flag on + valid key → health check `HEALTHY`
- Provider unreachable → fallback path triggered, structured log emitted

## Bengali note (AGENTS.md Rule #6)
Cerebras শুধু তখনই যোগ করব যখন Policy Engine + Evaluation Engine প্রস্তুত। "Fast → use" যথেষ্ট নয় — cost, security, fallback সব প্রমাণ থাকতে হবে। Governed Provider, কোনো direct dependency নয়।
"""
    },
    {
        "title": "[Roadmap v2 / P2] Build Policy Engine layer — who/what/cost/security gate for Capability Router",
        "labels": ["P2-medium", "area:architecture", "area:governance", "area:routing", "group:ecosystem-roadmap"],
        "body": """## Summary
The Capability Router alone is insufficient. **Who can use which provider, for which task, with what cost limit and security level** are Policy Engine decisions, not routing decisions. This connects directly to agent-governance.

This is **Phase 2 (new)** — the Policy Engine sits between the Capability Router and the providers, enforcing governance before any provider call.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Architecture → Capability Router + Policy Engine
- Pattern: §2.3 Governed Provider Pattern

## Policy Engine Decision Inputs
| Input | Source |
|---|---|
| Agent identity + role | `agent_identity.py` (CAS-based) |
| Task type + touching files | Claim contract |
| Cost budget (per-task, per-agent, per-tenant) | Admin policy |
| Security classification of inputs/outputs | Data classifier |
| Provider health state | `service_topology.py` |
| Provider evaluation score | Evaluation Engine |
| Tenant policy (which providers allowed for this tenant) | Tenant config |

## Policy Engine Outputs
- **Allow / Deny** (with reason)
- **Cost limit** (max $ per call, max $ per task)
- **Security constraints** (data redaction required? egress allowed?)
- **Fallback order** (if primary denied/unhealthy, which next?)

## Acceptance Criteria
- [ ] `backend/governance/policy_engine.py` exists with pluggable policy rules
- [ ] Every provider call traverses: `Router → Policy Engine → Provider` (no bypass path)
- [ ] Policy decisions logged with structured fields (per #3415 PII redaction)
- [ ] Admin API for policy CRUD (`/api/admin/policies`)
- [ ] Policy rules are data-driven (YAML/DB), not hardcoded
- [ ] Integration test: agent without cost budget → provider call denied with structured reason
- [ ] Integration test: provider unhealthy → Policy Engine re-routes to fallback

## Touching Files (expected)
- `backend/governance/policy_engine.py` (new)
- `backend/governance/policy_rules.py` (new — rule loader)
- `backend/governance/policy_types.py` (new — typed policy schema)
- `prisma/schema.prisma` — `Policy`, `PolicyDecision` models
- `backend/admin/routes/policies.py` (new)
- `apps/mission-control/` — policy management UI

## Dependencies / Blocks
- **Depends on**: Capability Inventory, Provider Health Dashboard
- **Blocks**: 3-Tier Auto-Routing (tier boundaries enforced by Policy Engine), all Governed Provider integrations

## Test Evidence
- Unit tests: each policy rule (cost, security, health, tenant) produces correct decision
- Integration test: full pipeline `Agent → Router → Policy Engine → Provider` with denial case
- Load test: Policy Engine adds < 5ms p99 latency to provider call

## Bengali note (AGENTS.md Rule #6)
Router একা যথেষ্ট নয় — Policy Engine বাধ্যতামূলক। কে কোন provider ব্যবহার করবে, কোন task-এ, কত cost-এ, কোন security level-এ — এগুলো policy সিদ্ধান্ত, routing সিদ্ধান্ত নয়। এটা agent-governance-এর সাথে সরাসরি যুক্ত।
"""
    },
    {
        "title": "[Roadmap v2 / P1] Implement 3-Tier Auto-Routing boundary (Automatic / Governed-automatic / Admin-only)",
        "labels": ["P1-high", "area:governance", "area:routing", "group:ecosystem-roadmap"],
        "body": """## Summary
**v2 key addition from user feedback.** Not all routing is automatic. Some routing decisions require admin governance. The 3-tier boundary aligns with SupremeAI's 99.99% automatic / 0.01% admin boundary principle.

This is **Phase 5.2** — the governance overlay on top of the Policy Engine + Evaluation Engine.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 5 → §5.2 3-Tier Auto-Routing

## Tier Boundary Matrix
| Tier | What | Who decides |
|---|---|---|
| **Automatic** | Latency weight, temporary provider health, cost optimization, retry/fallback | System (no human) |
| **Governed automatic** | Provider preference, model selection, benchmark-based routing | System (within admin-set policy bounds) |
| **Admin-only** | Constitutional changes, security-sensitive providers, permission escalation, new external capability adoption, architecture changes | Human (admin decision gate) |

## Acceptance Criteria
- [ ] Every routing decision is tagged with its tier (Automatic / Governed-automatic / Admin-only)
- [ ] Tier-1 (Automatic) decisions: zero-latency, zero-human, logged only on anomaly
- [ ] Tier-2 (Governed-automatic): decisions bounded by admin-set policy (max cost, allowed provider set, security constraints); logged with policy reference
- [ ] Tier-3 (Admin-only): routing decision BLOCKED until admin approval; approval workflow via Mission Control
- [ ] Attempting a Tier-3 routing without approval → structured denial + admin notification
- [ ] Admin approval audit trail (who approved what, when, rationale)
- [ ] Tier classification is data-driven (YAML policy), not hardcoded

## Touching Files (expected)
- `backend/governance/routing_tiers.py` (new)
- `backend/governance/policy_engine.py` (tier-aware)
- `prisma/schema.prisma` — `RoutingTierDecision`, `AdminApproval` models
- `backend/admin/routes/approvals.py` (new — approval workflow)
- `apps/mission-control/` — approval queue UI

## Dependencies / Blocks
- **Depends on**: Policy Engine layer, Evaluation Engine (for governed-automatic tier)
- **Blocks**: real auto-routing (without tier boundary, routing is unsafe)

## Test Evidence
- Unit test: Tier-1 decision completes in < 5ms, no human
- Unit test: Tier-2 decision respects policy bounds (over-budget → falls back)
- Integration test: Tier-3 decision blocked without approval; approved after admin action
- Audit trail test: every tier-3 decision has approval record

## Bengali note (AGENTS.md Rule #6)
সব routing automatic নয় — কিছু সিদ্ধান্ত admin ছাড়া চলবে না। 99.99% automatic / 0.01% admin boundary principle মেনে চলতে হবে। Constitutional change, security-sensitive provider, permission escalation — এগুলো কখনো automatic নয়।
"""
    },
    # ───────────────────────── PHASE 3: Memory + Learning Enhancement ─────────────────────────
    {
        "title": "[Roadmap v2 / P1] Adopt hierarchical context tiers — L0 governance / L1 task / L2 experience",
        "labels": ["P1-high", "area:architecture", "area:backend", "ecosystem-learning", "group:ecosystem-roadmap"],
        "body": """## Summary
Adopt OpenViking-inspired hierarchical context tiers. **v2 change**: L0 is not just "memory" — it's **governance context** (constitutional rules that constrain all behavior).

This is **Phase 3.1** — evolves SupremeAI's context loading from flat to hierarchical.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 3 → §3.1 Hierarchical Context Tiers

## Tier Definitions
| Tier | Loaded when | Contents |
|---|---|---|
| **L0** (Immutable / Constitutional) | Always | AGENTS.md, AGENT_RULES.md, security policies, governance rules. NOT memory — governance context |
| **L1** (Active Task Context) | On task assignment | Task contract, touching files, role policy, skill bundle |
| **L2** (Retrieved Experience / Skills) | On demand, similarity-ranked | Past decisions, learned patterns, successful approaches (from experience DB, vector similarity) |

## Acceptance Criteria
- [ ] `backend/memory/context_tiers.py` exists with `L0Context`, `L1Context`, `L2Context` classes
- [ ] L0 context: always loaded, derived from AGENTS.md + AGENT_RULES.md + security policies (parsed, not raw)
- [ ] L0 context changes trigger admin approval (Tier-3 — constitutional change)
- [ ] L1 context: loaded on claim assignment, includes task contract + touching files + role policy
- [ ] L2 context: retrieved on-demand via vector similarity from experience DB
- [ ] Token-budget aware: total context window budget allocated L0 > L1 > L2 (L0 always reserved first)
- [ ] L2 retrieval respects Policy Engine (tenant/agent scope)
- [ ] Context composition logged for debugging (which tiers loaded, token count per tier)

## Touching Files (expected)
- `backend/memory/context_tiers.py` (new)
- `backend/memory/l0_constitutional.py` (new)
- `backend/memory/l1_task_context.py` (new)
- `backend/memory/l2_experience_retrieval.py` (new)
- `backend/adaptive_engine/experience_db.py` (extend — vector similarity retrieval)
- `backend/core/ai_memory/repository.py` (extend — tier-aware storage)

## Dependencies / Blocks
- **Depends on**: Capability Inventory
- **Blocks**: Learning Loop (L2 is where learned patterns land), Decision Metadata Model (L2 retrieval uses decision metadata)

## Test Evidence
- Unit test: L0 always loaded regardless of task
- Unit test: L1 loaded only on task assignment
- Unit test: L2 retrieval returns top-K by similarity, respects tenant scope
- Integration test: agent context window shows L0+L1+L2 with token budget accounting

## Bengali note (AGENTS.md Rule #6)
L0 শুধু memory নয় — এটা governance context। AGENTS.md + AGENT_RULES.md সবসময় loaded থাকবে এবং সব আচরণকে নিয়ন্ত্রিত রাখবে। L0 change = Tier-3 admin approval, কারণ এটা constitutional change।
"""
    },
    {
        "title": "[Roadmap v2 / P2] Adopt decision metadata model — verification + policy_context + supersedes fields",
        "labels": ["P2-medium", "area:backend", "ecosystem-learning", "area:governance", "group:ecosystem-roadmap"],
        "body": """## Summary
Adopt agentmemory-inspired decision metadata model. **v2 change**: 3 additional fields beyond the original agentmemory schema — `verification`, `policy_context`, `supersedes`.

This is **Phase 3.2** — records every agent decision with enough metadata to learn from it.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 3 → §3.2 Decision Metadata Model

## Decision Metadata Schema
```json
{
  "agent_type": "coder",
  "task_type": "ci_fix",
  "decision": "chose_provider_X",
  "why": "lowest_latency_for_task_type",
  "evidence": ["benchmark_run_123: 0.3s", "cost_log: $0.001"],
  "confidence": 0.85,
  "outcome": "success",
  "reusability": "high",
  "expiry": "2026-12-31",
  "policy_context": "cost_optimization_mode: true, max_cost_per_task: $0.05",
  "verification": "pytest passed, CI green, 0 regression",
  "supersedes": null
}
```

## Why the 3 new fields?
- **`verification`** — SupremeAI doesn't just want "what did the agent decide?" — it wants **"did the decision actually work?"** This separates a learning system from a memory system.
- **`policy_context`** — captures the policy state at decision time (cost mode, security constraints). Enables "same decision different policy → different outcome" analysis.
- **`supersedes`** — when a better decision supersedes an old one, the old decision is marked deprecated but NOT deleted (provenance chain preserved).

## Acceptance Criteria
- [ ] Prisma `DecisionMetadata` model with all 13 fields
- [ ] Every agent decision recorded (provider choice, tool use, task approach)
- [ ] `verification` field populated post-task (CI result, test result, regression count)
- [ ] `policy_context` snapshot of active policy at decision time
- [ ] `supersedes` field: when a decision is replaced, the new decision references the old; old decision marked `deprecated` (not deleted)
- [ ] Admin API: `GET /api/admin/decisions?agent=&task_type=&since=` with filters
- [ ] Learning pipeline (Phase 5.3) consumes decision metadata

## Touching Files (expected)
- `prisma/schema.prisma` — `DecisionMetadata` model
- `backend/learning/decision_recorder.py` (new)
- `backend/learning/decision_verifier.py` (new — populates `verification` post-task)
- `backend/admin/routes/decisions.py` (new)
- `backend/evolution/learning_pipeline.py` (extend — consume metadata)

## Dependencies / Blocks
- **Depends on**: Hierarchical Context Tiers (L2 retrieval uses this metadata)
- **Blocks**: Learning Loop closure, Memory Governance (policy-driven TTL uses verification status)

## Test Evidence
- Unit test: decision recorded with all 13 fields
- Unit test: supersession chain — new decision marks old as `deprecated`, old not deleted
- Integration test: post-task `verification` field populated from CI result
- Query test: filter decisions by `outcome=success` + `task_type=ci_fix` returns matching set

## Bengali note (AGENTS.md Rule #6)
`verification` field হলো সবচেয়ে গুরুত্বপূর্ণ যোগ — "agent কী সিদ্ধান্ত নিয়েছে" নয়, "সিদ্ধান্তটি আসলে কাজ করেছে কি না" এটাই জানতে হবে। এটাই memory system থেকে learning system-এ পার্থক্য। `supersedes` provenance chain ধরে রাখে যাতে পুরোনো সিদ্ধান্ত মুছে না যায়।
"""
    },
    {
        "title": "[Roadmap v2 / P3] Memory governance — policy-driven TTL + conflict detection + provenance",
        "labels": ["P3-low", "area:backend", "area:governance", "ecosystem-learning", "group:ecosystem-roadmap"],
        "body": """## Summary
Adopt Memanto-inspired memory governance. **v2 change**: TTL is **policy-driven**, not hardcoded.

This is **Phase 3.3** — governs memory lifecycle (when to expire, when to merge, when to flag conflicts).

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 3 → §3.3 Memory Governance

## Policy-Driven TTL Inputs
```text
Memory Policy Engine
   ↓
Inputs:
  - type (procedural / episodic / cache / decision)
  - importance score
  - confidence level
  - verification status
  - usage frequency (how often retrieved?)
  - freshness (how recent?)
  - risk level (what happens if stale?)
   ↓
Output: TTL (dynamic, per-entry)
```

## NOT Hardcoded
- ❌ procedural = permanent, episodic = 30d, cache = 1h
- ✅ Policy-driven: high-importance + high-confidence + verified = permanent; low-confidence + unverified + stale = short TTL

## Acceptance Criteria
- [ ] `backend/memory/policy_engine_memory.py` exists
- [ ] TTL computed per-entry from inputs (type, importance, confidence, verification, usage, freshness, risk)
- [ ] Admin-configurable policy weights (YAML/DB, not hardcoded)
- [ ] Conflict detection: two entries with same semantic key but different values → flag for resolution (admin review or auto-merge per policy)
- [ ] Provenance: every entry has `source_decision_id` linking back to `DecisionMetadata`
- [ ] Expiry sweep job (cron) removes expired entries; expired-and-verified entries archived (not deleted)
- [ ] Memory governance decisions logged (structured, #3415 PII redaction)

## Touching Files (expected)
- `backend/memory/policy_engine_memory.py` (new)
- `backend/memory/conflict_detector.py` (new)
- `backend/memory/provenance.py` (new)
- `backend/core/ai_memory/repository.py` (extend — TTL-aware)
- `prisma/schema.prisma` — `MemoryPolicy`, `MemoryConflict` models
- `scripts/cron/memory_expiry_sweep.py` (new)

## Dependencies / Blocks
- **Depends on**: Decision Metadata Model (needs `verification` status for TTL computation)
- **Blocks**: clean memory state (without governance, memory grows unbounded)

## Test Evidence
- Unit test: high-importance + verified entry → TTL = permanent
- Unit test: low-confidence + stale entry → TTL = short
- Unit test: conflict between two entries → flagged
- Cron test: sweep removes only expired-and-not-archived entries

## Bengali note (AGENTS.md Rule #6)
TTL কখনো hardcoded নয় — policy-driven। high-importance + verified = permanent; low-confidence + stale = short TTL। এটা Memanto থেকে ধার করা concept কিন্তু SupremeAI-তে policy engine আকারে বাস্তবায়িত।
"""
    },
    {
        "title": "[Roadmap v2 / P2] Close the learning loop — decision → verify → learn → inject into next agent context",
        "labels": ["P2-medium", "area:backend", "ecosystem-learning", "area:governance", "group:ecosystem-roadmap"],
        "body": """## Summary
Complete the learning loop. This is **Phase 5.3** — the closing arc of the ecosystem intelligence loop. Without this, decisions are recorded but never learned from.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 5 → §5.3 Learning Loop

## Learning Loop Flow
```text
Agent executes task
  ↓
Decision + Evidence + Outcome + Verification recorded (Decision Metadata)
  ↓
Daily: learning_pipeline.py analyzes patterns
  ↓
Successful patterns → skill templates (stored as L2 experience)
Failed patterns → regression guards (stored as L2 anti-patterns)
Ambiguous patterns → Admin Decision (Tier-3)
  ↓
Skill templates injected into next agent's L1 context (on similarity match)
  ↓
Verified improvement measurable in next run (Evaluation Engine)
```

## Acceptance Criteria
- [ ] `learning_pipeline.py` extended to consume `DecisionMetadata` (not just raw logs)
- [ ] Pattern miner: clusters decisions by `(task_type, decision_type, outcome)` → identifies repeatable success/failure patterns
- [ ] Successful pattern → skill template YAML committed to `knowledge/skills/`
- [ ] Failed pattern → regression guard (test or policy rule)
- [ ] Ambiguous pattern → admin notification (Tier-3 decision)
- [ ] L1 context loader: on task assignment, query L2 for matching skill templates by similarity; inject if match score > threshold
- [ ] Evaluation Engine measures: did injecting the skill template improve the next run's outcome? (A/B comparison)
- [ ] If improvement confirmed → skill template weight increased; if no improvement → weight decreased / template retired

## Touching Files (expected)
- `backend/evolution/learning_pipeline.py` (extend)
- `backend/learning/pattern_miner.py` (new)
- `backend/learning/skill_template_writer.py` (new)
- `knowledge/skills/*.yaml` (new — generated skill templates)
- `backend/memory/l1_task_context.py` (extend — inject matching skills)

## Dependencies / Blocks
- **Depends on**: Decision Metadata Model (for pattern mining input), Hierarchical Context Tiers (L1/L2 injection), Evaluation Engine (for improvement measurement)
- **Blocks**: real self-evolution (without closed loop, no learning happens)

## Test Evidence
- Unit test: pattern miner clusters 10 decisions into 3 patterns
- Integration test: skill template injected into L1 → next run's outcome improved → Evaluation Engine confirms delta
- Regression test: failed pattern → regression guard added → future failure caught early

## Bengali note (AGENTS.md Rule #6)
শেখার লুপ বন্ধ না হলে সিদ্ধান্ত রেকর্ড হবে কিন্তু শেখা হবে না। সার্কিট পূর্ণ করতে হবে: decision → verify → pattern mine → skill template → inject L1 → measure improvement। এটাই SupremeAI-কে "AI platform" থেকে "self-evolving system" এ পরিণত করে।
"""
    },
    # ───────────────────────── PHASE 4: Ecosystem Scout + Evidence Pipeline ─────────────────────────
    {
        "title": "[Roadmap v2 / P1] Prototype Agent-Reach as Ecosystem Scout data acquisition layer",
        "labels": ["P1-high", "area:architecture", "ecosystem-learning", "area:governance", "group:ecosystem-roadmap"],
        "body": """## Summary
Prototype Agent-Reach as the daily Ecosystem Scout — the data acquisition layer that feeds the discovery pipeline. This is **Phase 4.1** — SupremeAI actively discovers external innovation rather than waiting for manual intake.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 4 → §4.1 Evidence-Based Discovery Pipeline

## Discovery Pipeline
```text
Daily Scout Cron (Agent-Reach)
  ↓
Raw findings from X, Reddit, YouTube, GitHub, Bilibili
  ↓
Deduplicate (fingerprint against existing inventory)
  ↓
Capability Inventory check (do we already have this?)
  ↓
Gap Analysis (is this a real gap in SupremeAI?)
  ↓
Benchmark / Evidence collection
  ↓
Recommendation (score: relevance × improvement × cost)
  ↓
Auditor Agent (Team Leader pattern — reviews, filters false-positives)
  ↓
GitHub Issue (only if score > threshold + auditor approves)
  ↓
Admin Decision Gate (if architectural — Tier-3)
```

## Hard Governance Rule (Phase 4.2)
> Discovery agents may discover. Auditor may recommend. Only governed issue-generation workflow may create issues.

This prevents malicious/low-quality external information from causing automated issue spam. (Aligns with #3973 Team Leader Scanner Pattern.)

## Acceptance Criteria
- [ ] `scripts/scout/agent_reach_runner.py` exists — daily cron
- [ ] Source adapters: GitHub trending, X posts, Reddit r/LocalLLaMA + r/MachineLearning, YouTube tech channels, Bilibili tech
- [ ] Deduplication: content fingerprint (hash of normalized title+summary) against `discovered_repos` table
- [ ] Capability Inventory check: does SupremeAI already have this capability? (cross-reference `inventory.yaml`)
- [ ] Gap analysis: is this a real gap? (LLM-judge with inventory as context)
- [ ] Recommendation score: `relevance × improvement × cost` — only > threshold reaches auditor
- [ ] Auditor agent (Team Leader pattern): reviews findings, filters false-positives, approves/rejects
- [ ] Only auditor-approved findings → GitHub issue (with `discovered-by:scout` label)
- [ ] Architectural findings → admin decision gate (Tier-3), not auto-issue

## Touching Files (expected)
- `scripts/scout/agent_reach_runner.py` (new)
- `backend/scout/sources/{github,x,reddit,youtube,bilibili}.py` (new)
- `backend/scout/dedup.py` (new)
- `backend/scout/gap_analyzer.py` (new)
- `backend/scout/recommender.py` (new)
- `backend/agents/auditor_agent.py` (extend — scout findings review)
- `prisma/schema.prisma` — `DiscoveredRepo`, `ScoutFinding` models
- `.github/workflows/scout-daily.yml` (new — cron)

## Dependencies / Blocks
- **Depends on**: Capability Inventory (for gap analysis cross-reference), Team Leader auditor pattern (already implemented in #3973)
- **Blocks**: ecosystem intelligence loop start (no discovery → no evaluation → no learning)

## Test Evidence
- Unit test: dedup catches same repo discovered from 2 sources
- Unit test: gap analyzer rejects repo already in inventory
- Integration test: mock finding → recommendation score → auditor approval → issue created
- Integration test: low-score finding → filtered before auditor
- Governance test: architecturally-sensitive finding → admin gate (no auto-issue)

## Bengali note (AGENTS.md Rule #6)
Scout শুধু discover করবে — issue সরাসরি তৈরি করবে না। Auditor (Team Leader pattern) approve করলে তবে issue। Architectural finding = admin gate (Tier-3)। এটা malicious/low-quality external info থেকে issue spam রোধ করে। #3973-এর সাথে সামঞ্জস্যপূর্ণ।
"""
    },
    {
        "title": "[Roadmap v2 / P3] DuckDB analytics layer — workload-driven (only when Postgres analytics insufficient)",
        "labels": ["P3-low", "area:backend", "area:architecture", "group:ecosystem-roadmap"],
        "body": """## Summary
Add DuckDB as a governed analytics engine. **v2 change**: deprioritized P2 → P3. Only adopt when daily analytics workload exceeds Postgres capability.

This is **Phase 4.3** — the analytics layer for ecosystem intelligence reports.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 4 → §4.3 DuckDB Analytics Layer

## Architecture
```text
Supabase/Postgres (operational DB)
      ↓
Export/Event stream (when analytics volume grows)
      ↓
DuckDB (analytics engine — NOT operational DB)
      ↓
Daily ecosystem audit + cost + latency + regression reports
```

## Workload Trigger (NOT premature adoption)
Adopt DuckDB only when ALL of:
- [ ] Daily analytics query volume > 10k rows scanned per report
- [ ] Postgres analytics queries > 5s p95
- [ ] At least 3 distinct daily report types (cost, latency, regression, ecosystem audit)

Until then: Postgres is sufficient. Do NOT add DuckDB prematurely.

## Acceptance Criteria (only when workload trigger met)
- [ ] Workload trigger documented + measured (Postgres query latency log)
- [ ] `backend/analytics/duckdb_layer.py` exists
- [ ] Event stream from Postgres → DuckDB export (daily or real-time depending on volume)
- [ ] Daily report queries (cost, latency, regression, ecosystem audit) migrated to DuckDB
- [ ] DuckDB as governed provider: `SUPREMEAI_DUCKDB_ENABLED`, health check, Policy Engine gate
- [ ] Postgres remains operational DB — DuckDB never writes back to operational tables

## Touching Files (expected)
- `backend/analytics/duckdb_layer.py` (new — only when triggered)
- `backend/analytics/export_stream.py` (new — Postgres → DuckDB)
- `backend/analytics/reports/{cost,latency,regression,ecosystem_audit}.py` (new)
- `backend/observability/service_topology.py` (health check)

## Dependencies / Blocks
- **Depends on**: workload trigger (do NOT adopt prematurely), Evaluation Engine (for regression report input)
- **Does NOT block** anything critical — Postgres is sufficient until workload grows

## Test Evidence
- Workload measurement: Postgres analytics query latency logged for 30 days
- If adopted: DuckDB report query < 1s p95 vs Postgres > 5s p95
- If not adopted: documented rationale (workload trigger not met)

## Bengali note (AGENTS.md Rule #6)
DuckDB এখন P3 — workload-driven। Postgres যখন analytics-এ ধীল হয়ে যাবে (p95 > 5s, daily 10k+ rows), তখনই DuckDB। আগে নয় — over-engineering পরিহার্য। এটা v2 feedback-এর গুরুত্বপূর্ণ পরিবর্তন।
"""
    },
    # ───────────────────────── PHASE 5: Self-Evolution (Evaluation Engine already covered above) ─────────────────────────
    # ───────────────────────── Retire orphaned adapters ─────────────────────────
    {
        "title": "[Roadmap v2 / P3] Retire orphaned adapters — mem0, e2b, graphiti (redundant with native capabilities)",
        "labels": ["P3-low", "area:backend", "area:architecture", "group:ecosystem-roadmap"],
        "body": """## Summary
Retire 3 orphaned adapters that are redundant with SupremeAI's native capabilities. This is the **retire** half of Phase 1.2 (the audit half is covered by separate Browser Use / OpenHands audit issues).

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 1 → §1.2 Orphaned Adapter Audit (decision matrix)

## Decision Matrix (from roadmap)
| Adapter | Action | Rationale |
|---|---|---|
| `mem0_adapter.py` | **Retire** | SupremeAI already has canonical MemoryRepository + pgvector; mem0 is redundant |
| `e2b_adapter.py` | **Retire** unless sandbox execution is needed | SupremeAI has its own sandbox; e2b is redundant |
| `graphiti_adapter.py` | **Retire** | SupremeAI's episodic + long-term memory covers this |

## Acceptance Criteria
- [ ] For each adapter: grep confirms no live caller (only dead code references)
- [ ] Adapter file deleted
- [ ] Inventory updated (status: `retired` with date + rationale)
- [ ] If any caller exists: migrate caller to native equivalent FIRST, then delete
- [ ] `requirements.txt` / `package.json`: remove unused transitive deps introduced by adapter
- [ ] Documentation: replacement path documented in `docs/architecture/retired_adapters.md`

## Touching Files (expected)
- `backend/integrations/mem0_adapter.py` (delete)
- `backend/integrations/e2b_adapter.py` (delete)
- `backend/integrations/graphiti_adapter.py` (delete)
- `docs/architecture/inventory.yaml` (update status)
- `docs/architecture/retired_adapters.md` (new — replacement path documentation)
- `requirements.txt` / `package.json` (remove unused deps if any)

## Dependencies / Blocks
- **Depends on**: Capability Inventory (confirm no live caller), Browser Use + OpenHands audit (so the orphan audit phase is complete)

## Test Evidence
- grep: no remaining reference to deleted adapters in `backend/` (except docs)
- CI: green after deletion (no broken imports)
- Import test: `python -c "import backend.integrations"` succeeds

## Bengali note (AGENTS.md Rule #6)
mem0, e2b, graphiti — এই তিনটি orphaned adapter redundant। SupremeAI-তে ইতিমধ্যে MemoryRepository + pgvector + নিজস্ব sandbox + episodic memory আছে। কিন্তু মুছার আগে নিশ্চিত করতে হবে কোনো live caller নেই — grep প্রমাণ বাধ্যতামূলক।
"""
    },
    # ───────────────────────── P3: Security + Visualization ─────────────────────────
    {
        "title": "[Roadmap v2 / P3] Security sandbox research — Metatron isolated scanner (research only)",
        "labels": ["P3-low", "area:security", "area:architecture", "documentation", "group:ecosystem-roadmap"],
        "body": """## Summary
Research Metatron as an isolated security sandbox scanner. This is **research only** at P3 — no implementation until research concludes it fills a gap SupremeAI's native security tooling cannot.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 2 → §2.2 Integration Matrix (row #13: Metatron)

## Acceptance Criteria (research deliverable)
- [ ] Research report: `docs/architecture/research/metatron_research.md`
- [ ] Sections: capability, isolation model, security surface, SupremeAI gap analysis, benchmark vs native scanner, recommendation (Adopt / Adapt / Reject / Reference)
- [ ] If **Adopt**: separate implementation issue created (Tier-3 admin gate — security-sensitive)
- [ ] If **Reject/Reference**: documented rationale, no further action

## Touching Files (expected)
- `docs/architecture/research/metatron_research.md` (new — research only)

## Dependencies / Blocks
- **Depends on**: Capability Inventory (gap analysis reference)
- **Does NOT block** anything — pure research

## Test Evidence
- Research report committed with all sections complete
- Decision recorded with rationale

## Bengali note (AGENTS.md Rule #6)
Metatron এখন শুধু research — implementation নয়। Evidence Before Adoption: প্রথমে গবেষণা → gap analysis → benchmark → তারপর সিদ্ধান্ত। security-sensitive হওয়ায় adoption হলে Tier-3 admin approval বাধ্যতামূলক।
"""
    },
    {
        "title": "[Roadmap v2 / P3] Mission Control visualization — Excalidraw integration (if existing viz insufficient)",
        "labels": ["P3-low", "area:frontend", "area:architecture", "group:ecosystem-roadmap"],
        "body": """## Summary
Evaluate Excalidraw as a Mission Control visualization component. **Only adopt if existing Mission Control viz is insufficient** for the ecosystem intelligence dashboard (provider topology, learning loop, evaluation scores).

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 2 → §2.2 Integration Matrix (row #12: Excalidraw)

## Acceptance Criteria
- [ ] Gap analysis: what visualization does Mission Control currently lack? (provider topology graph? learning loop flow? evaluation score matrix?)
- [ ] If gap exists: prototype Excalidraw component for that specific gap
- [ ] If no gap: document rationale, close issue as `wontfix` with evidence

## Touching Files (expected)
- `apps/mission-control/components/visualizations/` (if adopted)
- `docs/architecture/research/excalidraw_evaluation.md` (research)

## Dependencies / Blocks
- **Depends on**: Evaluation Engine (for score matrix viz), Provider Health Dashboard (for topology viz)

## Test Evidence
- Gap analysis committed
- If adopted: Excalidraw component renders in Mission Control
- If rejected: documented rationale

## Bengali note (AGENTS.md Rule #6)
Excalidraw শুধু তখনই যখন existing viz অপর্যাপ্ত। Consolidation over expansion — নতুন component যোগ করার আগে দেখতে হবে আসলে কি gap আছে।
"""
    },
    # ───────────────────────── P4: Research items ─────────────────────────
    {
        "title": "[Roadmap v2 / P4] Local inference benchmark — Strata vs Colibrì vs llama.cpp",
        "labels": ["P3-low", "area:architecture", "documentation", "group:ecosystem-roadmap"],
        "body": """## Summary
Benchmark local inference providers (Strata, Colibrì) against llama.cpp baseline. P4 — research only.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 2 → §2.2 Integration Matrix (rows #9 Strata, #10 Colibrì)

## Acceptance Criteria (research deliverable)
- [ ] Benchmark report: `docs/architecture/research/local_inference_benchmark.md`
- [ ] Metrics: tokens/sec, VRAM usage, RAM usage, setup complexity, model compatibility
- [ ] 3 representative models (small / medium / large)
- [ ] Recommendation: which provider for which workload? (or reject all if llama.cpp wins)

## Touching Files (expected)
- `docs/architecture/research/local_inference_benchmark.md` (new)

## Dependencies / Blocks
- None — pure research

## Test Evidence
- Benchmark report with reproducible methodology

## Bengali note (AGENTS.md Rule #6)
Strata ও Colibrì — দুটোই research stage। llama.cpp baseline ছাড়া তুলনা অর্থহীন। tokens/sec + VRAM + RAM + setup complexity — সব মিলিয়ে সিদ্ধান্ত।
"""
    },
    {
        "title": "[Roadmap v2 / P4] Chat UX research — LibreChat reference patterns (read-only)",
        "labels": ["P3-low", "area:frontend", "documentation", "group:ecosystem-roadmap"],
        "body": """## Summary
Mine LibreChat for chat UX patterns SupremeAI could adopt. P4 — reference only, no implementation unless a specific UX gap is identified.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 2 → §2.2 Integration Matrix (row #14: LibreChat)

## Acceptance Criteria
- [ ] Research note: `docs/architecture/research/librechat_ux_patterns.md`
- [ ] List of UX patterns worth adopting (with rationale + gap analysis vs current Mission Control chat)
- [ ] If any pattern adopted: separate implementation issue

## Touching Files (expected)
- `docs/architecture/research/librechat_ux_patterns.md` (new)

## Dependencies / Blocks
- None

## Test Evidence
- Research note committed

## Bengali note (AGENTS.md Rule #6)
LibreChat = reference মাত্র। কোনো direct adoption নয় — শুধু UX pattern mining।
"""
    },
    {
        "title": "[Roadmap v2 / P4] Local edition backend research — PocketBase for SupremeAI Local Edition",
        "labels": ["P3-low", "area:architecture", "documentation", "group:ecosystem-roadmap"],
        "body": """## Summary
Research PocketBase as a backend for a potential SupremeAI Local Edition (offline / self-hosted lightweight deployment). P4 — research only.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 2 → §2.2 Integration Matrix (row #18: PocketBase)

## Acceptance Criteria
- [ ] Research note: `docs/architecture/research/pocketbase_local_edition.md`
- [ ] Use-case: who needs a Local Edition? (air-gapped? offline-first? cost-sensitive?)
- [ ] Gap analysis: what does PocketBase offer that Supabase self-host doesn't?
- [ ] Recommendation: build Local Edition or not (if not, document why)

## Touching Files (expected)
- `docs/architecture/research/pocketbase_local_edition.md` (new)

## Dependencies / Blocks
- None

## Test Evidence
- Research note committed with use-case + recommendation

## Bengali note (AGENTS.md Rule #6)
PocketBase = optional Local Edition research। আগে দেখতে হবে আসলে কারও Local Edition দরকার কি না (air-gapped / offline use-case)। যদি না থাকে — wontfix।
"""
    },
    # ───────────────────────── REJECT (documentation only, no work) ─────────────────────────
    {
        "title": "[Roadmap v2] REJECT: anthropic-tools (archived + deprecated) — document rationale",
        "labels": ["P3-low", "documentation", "area:architecture", "group:ecosystem-roadmap"],
        "body": """## Summary
Document the rejection of `anthropic-tools` (archived + deprecated). This is a documentation-only issue to record the Evidence Before Adoption decision per Rule 4.

## Linked Roadmap Section
- File: `docs/architecture/ECOSYSTEM_INTELLIGENCE_ROADMAP.md`
- Section: Phase 2 → §2.2 Integration Matrix (row #24: anthropic-tools → REJECT)

## Acceptance Criteria
- [ ] Rejection record added to `docs/architecture/research/rejected_repos.md`
- [ ] Fields: repo, reason (archived/deprecated), upstream status check, decision date, decider
- [ ] Inventory marks anthropic-tools as `rejected` with rationale

## Touching Files (expected)
- `docs/architecture/research/rejected_repos.md` (new or extend)

## Dependencies / Blocks
- None

## Test Evidence
- Rejection record committed

## Bengali note (AGENTS.md Rule #6)
anthropic-tools archived + deprecated — স্পষ্ট REJECT। তবে সিদ্ধান্ত নথিভুক্ত করতে হবে যাতে ভবিষ্যতে আবার একই repo audit না হয়। Evidence Before Adoption-এর অংশ।
"""
    },
]


def create_issue(issue):
    url = f"https://api.github.com/repos/{REPO}/issues"
    payload = {
        "title": issue["title"],
        "body": issue["body"],
        "labels": issue["labels"],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"token {TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("number"), data.get("html_url"), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return None, None, f"HTTP {e.code}: {body[:200]}"
    except Exception as e:
        return None, None, str(e)


def main():
    print(f"Creating {len(ISSUES)} issues for Ecosystem Intelligence Roadmap v2...\n")
    created = []
    failed = []
    for i, issue in enumerate(ISSUES, 1):
        title = issue["title"]
        num, url, err = create_issue(issue)
        if num:
            created.append((num, title, url))
            print(f"[{i:02d}/{len(ISSUES)}] #{num} — {title[:70]}")
            print(f"         {url}")
        else:
            failed.append((title, err))
            print(f"[{i:02d}/{len(ISSUES)}] FAILED — {title[:70]}")
            print(f"         ERR: {err}")
        # be polite to API
        import time
        time.sleep(0.5)

    print(f"\n=== Summary ===")
    print(f"Created: {len(created)}")
    print(f"Failed:  {len(failed)}")
    if failed:
        print("\nFailed issues:")
        for t, e in failed:
            print(f"  - {t[:70]}\n    {e}")

    # write summary file
    with open("/tmp/roadmap_issues_created.md", "w") as f:
        f.write(f"# Ecosystem Intelligence Roadmap v2 — Issues Created\n\n")
        f.write(f"Total: {len(created)} issues\n\n")
        f.write("| # | Issue | Title | Priority |\n")
        f.write("|---|---|---|---|\n")
        for num, title, url in created:
            # extract priority from labels
            pri = next((l.replace("P1-high", "P1").replace("P2-medium", "P2").replace("P3-low", "P3")
                        for l in [t for t in title.split()] if t.startswith("P") and t.endswith(("high", "medium", "low"))), "?")
            # simpler: parse from title
            if "P1" in title: pri = "P1"
            elif "P2" in title: pri = "P2"
            elif "P3" in title: pri = "P3"
            elif "P4" in title: pri = "P4"
            elif "REJECT" in title: pri = "—"
            else: pri = "?"
            f.write(f"| {num} | [#{num}]({url}) | {title} | {pri} |\n")
    print(f"\nSummary written to /tmp/roadmap_issues_created.md")


if __name__ == "__main__":
    main()
