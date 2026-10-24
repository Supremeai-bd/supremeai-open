---
id: plan-lifecycle-policy
subject: "SupremeAI Plan Lifecycle Policy"
document_role: policy
planning_authority: Architecture Governance / Planning Circle
canonical: true
status: active
evidence_state: verified
disposition: retain
last_verified: 2026-09-17
supersedes: []
superseded_by: []
target_scope: supremeai_internal
---

# SupremeAI Plan Lifecycle Policy

**Status:** active  
**Source of truth:** `docs/plans/implementation_plan.md`  
**Policy owner:** Planning / Governance  
**Last verified:** 2026-09-17

## Purpose

Prevent plan sprawl, conflicting execution instructions, stale infrastructure assumptions, premature implementation, weak evidence, and undocumented completion claims.

This policy governs the lifecycle of every document under `docs/plans/`, including strategic plans, specialized execution plans, reconciliations, and historical references.

## Core lifecycle principle

SupremeAI follows a **single-plan execution discipline**:

```text
discover one high-value opportunity
        ↓
reconcile against code + contracts + existing plans
        ↓
write one complete plan
        ↓
proposed / founder review
        ↓
approved
        ↓
active execution
        ↓
PR + verification
        ↓
deploy / observe
        ↓
record outcome evidence
        ↓
complete
        ↓
only then scout the next execution plan
```

Multiple future ideas may exist as references or candidates, but only **one plan may be in the active execution lifecycle at a time** unless the founder explicitly authorizes parallel execution.

## Required metadata

Every proposed, active, blocked, or complete execution plan must contain:

```yaml
id:
title:
status: proposed | active | blocked | complete | historical | superseded
document_role: architecture | roadmap | implementation | policy | audit
planning_authority:   # owner circle (legacy key `owner_circle` is accepted as an alias)
canonical: true | false | candidate
evidence_state: verified | partial | unverified
disposition: retain | merge | archive | redirect | delete-approved
target_scope: supremeai_internal | customer_facing | combined_ecosystem
scope:
depends_on:
implements:
supersedes:       # list of repository paths this plan replaces
superseded_by:    # list of repository paths that replace this plan
source_of_truth: true | false
last_verified:    # YYYY-MM-DD
code_evidence:
test_evidence:
acceptance_criteria:
risk_and_rollback:
```

### 3-Tier Planning Scope Taxonomy (Rule #1 & Rule #7 Scope Separation)

Every plan in `docs/plans/` MUST be classified into one of three operational scope layers:

| Planning Scope Layer | YAML `target_scope` | সংজ্ঞার্থ ও বাউন্ডারি | প্রযোজ্যতা ও বিধিনিষেধ |
|---|---|---|---|
| **Layer 1: SupremeAI Platform / Internal Only** | `supremeai_internal` | সুপ্রিমএআই-এর নিজস্ব রিপোসিটরি, ব্যাকগ্রাউন্ড কম্পিউট আরবিট্রেজ, অ্যাডমিন ব্রাউজার অটোমেশন পুল, সেলফ-ইভোলিউশন ও ইন্টারনাল সিআই/সিডি। | **কাস্টমার প্রজেক্টে সম্পূর্ণ নিষিদ্ধ।** এটি কেবল সুপ্রিমএআই প্ল্যাটফর্মের নিজস্ব উন্নয়নের জন্য। |
| **Layer 2: Customer / Tenant Projects Only** | `customer_facing` | শেষ-ব্যবহারকারী বা ক্লায়েন্ট প্রজেক্ট, টেন্যান্ট ওয়ার্কস্পেস, কাস্টমার এপিআই (`/api/v1/projects`), জিরো-পাসওয়ার্ড (Mode 3) এক্সপেরিয়েন্স। | **কাস্টমারদের জন্য নিবেদিত।** এখানে কোনো জটিল ব্রাউজার স্ক্র্যাপিং বা ইন্টারনাল জটিলতা থাকবে না। |
| **Layer 3: Combined / Ecosystem Core** | `combined_ecosystem` | সার্বজনীন আর্কিটেকচারাল নীতি—যেমন ডায়নামিক রেজিস্ট্রি (Zero Hardcoding), MCP কন্ট্রোল টাওয়ার প্রোটোকল, নিরাপত্তা ও টেন্যান্ট আইসোলেশন। | **উভয় ক্ষেত্রে প্রযোজ্য।** প্ল্যাটফর্ম এবং কাস্টমার উভয় রানটাইমে এই নীতিগুলো অপরিবর্তনীয় থাকবে। |


**Vocabulary authority (2026-09-17):** the status vocabulary and the registry
field model above are canonically defined by
[`CANONICAL_PLANNING_RECONCILIATION_AND_GUARDRAILS_PLAN.md`](./CANONICAL_PLANNING_RECONCILIATION_AND_GUARDRAILS_PLAN.md)
(§3 Canonical Plan Registry Model). `owner_circle` and `title` are accepted as
legacy aliases of `planning_authority` and `subject` by the automated scanner
(`scripts/governance/lint_plans.py`), which is the enforcement tool for this
policy; `docs/plans/plan_registry.json` is its generated machine cache.

Legacy schema (still valid, auto-normalized): `owner_circle:`

```yaml
owner_circle:
scope:
depends_on:
implements:
supersedes:
superseded_by:
source_of_truth: true | false
last_verified:
code_evidence:
test_evidence:
acceptance_criteria:
risk_and_rollback:
```

For plans that make quantitative claims, also include:

```yaml
baseline:
measurement_method:
success_threshold:
```

These fields do not have to contain production results before implementation, but the plan must define what will be measured and what evidence will determine success or failure.

## Source-of-truth hierarchy

```text
Current tested code
→ API / schema / provider contracts
→ docs/plans/implementation_plan.md
→ canonical architecture documents
→ one approved active execution plan
→ proposed / reference plans
→ historical plans
```

`implementation_plan.md` is the consolidated execution index, not permission to contradict tested reality. A specialized plan provides implementation detail only when it is reconciled with the current master plan and codebase.

If any plan conflicts with tested code or an authoritative contract, the plan is stale until reconciled. The code and contract win over the document.

## Status rules

- **proposed:** a complete candidate awaiting explicit approval. It must not be treated as an executable implementation instruction.
- **active:** explicitly approved and currently executable. Only one execution plan should be active at a time under the sequential discipline.
- **blocked:** approved in principle but not executable because of a named dependency, unresolved technical decision, missing resource, or failed prerequisite. The blocker must be explicit.
- **complete:** implementation is merged and the required verification, deployment, observability, and outcome evidence has been recorded. “Code exists” alone is not enough.
- **historical:** records a previous state, experiment, rejected direction, or execution model. Do not implement literally.
- **superseded:** replaced by a newer canonical plan. The replacement must be named and the old plan must remain traceable unless retention rules say otherwise.

## Approval and execution gates

A plan must pass these gates in order:

### Gate 0 — Discovery and reconciliation

Before drafting:

1. Search for an existing equivalent, duplicate, or overlapping plan.
2. Read the actual code and contracts touched by the proposed change.
3. Check `implementation_plan.md` and canonical architecture documents.
4. Identify what already exists before proposing new infrastructure, dependencies, or subsystems.

A plan based only on product documentation, blog posts, benchmarks, or assumptions fails this gate.

### Gate 1 — Plan completeness

The plan must explicitly answer, in this order:

**what we have → what we don't have → what to do → how to do it → benefit → harm / risk**

It must also define:

- acceptance criteria;
- evidence required for completion;
- baseline and measurement method for quantitative claims;
- rollback or kill-switch behavior for runtime changes;
- explicit out-of-scope items where scope could otherwise expand.

### Gate 2 — Approval

`proposed` means reviewable, not executable.

Only the founder / authorized owner may approve a plan for execution. Approval must be traceable in the PR, issue, decision log, or other repository evidence.

A plan must not be changed from `proposed` to `active` merely because engineering work has started.

### Gate 3 — Engineering execution

After approval:

1. start from a fresh `main` baseline;
2. use a dedicated feature branch;
3. keep the implementation within the approved scope;
4. do not silently add unrelated dependencies, infrastructure, services, or CI cost;
5. update the plan when implementation reveals a material mismatch with the original assumptions.

Material scope or architecture changes require re-review before execution continues.

### Gate 4 — Verification

Verification must match the risk of the change and may include:

```text
static checks
→ unit / integration tests
→ contract verification
→ runtime smoke test
→ observability evidence
→ deployment evidence
→ rollback / recovery verification
```

Mocked tests prove code behavior around a contract; they do **not** prove that a third-party provider, external service, or production metric behaves as assumed.

### Gate 5 — Outcome evidence

For changes intended to improve cost, latency, reliability, quality, or another measurable outcome, completion requires post-change evidence against a defined baseline.

Do not convert:

```text
expected benefit
→ observed benefit
```

without measurement.

Quantitative targets are hypotheses until measured in the actual SupremeAI workload.

### Gate 6 — Completion and next-plan unlock

Only after the plan's completion evidence is recorded may it be marked `complete` and the next execution plan be proposed as the new active candidate.

If the outcome criterion fails, the plan remains incomplete or is explicitly marked failed / blocked in the decision record; the next plan must not silently assume success.

## Evidence policy

Evidence should be explicit, traceable, and proportional to the claim.

### Code evidence

State the exact repository paths and, where practical, relevant symbols or line ranges used to verify the “what we have” and “what we don't have” sections.

### Test evidence

Record test files / commands and what they prove. A mocked provider test must not be described as proof of real provider behavior.

### External evidence

Claims about third-party pricing, model availability, provider behavior, API formats, rate limits, or documented performance must be verified against current authoritative sources before they are presented as factual assumptions. Record the verification date.

### Production evidence

For runtime changes, distinguish clearly between:

```text
implemented
→ deployed
→ observed
→ successful
```

A deployment is not evidence of a successful outcome.

## Quantitative-claim discipline

Plans may use estimates, targets, or published vendor figures, but must label them correctly.

Use:

- **estimate / hypothesis** for forecasts;
- **vendor-published figure** for third-party benchmarks or pricing;
- **measured result** for SupremeAI's own observed workload;
- **acceptance threshold** for the condition required to declare success.

Do not present an external benchmark as an expected SupremeAI result without qualification.

For cost-related work, distinguish at minimum:

```text
eligible cached / optimized portion
vs.
whole request cost
vs.
whole mission / task cost
```

For latency-related work, distinguish component latency from end-to-end user-visible latency.

## Scope and resource guardrails

Every execution plan must prefer existing assets before creation and should explicitly declare when it requires:

- a new dependency;
- a new server / service / account;
- a new paid tier or billable resource;
- additional CI runtime or external API spend;
- a new data store or persistent subsystem.

Any such addition must be justified by the plan and approved explicitly. “Free tier” is not, by itself, evidence of zero operational risk.

The default discipline for small optimization plans is:

```text
reuse existing capability
→ make the smallest safe change
→ measure
→ keep / tune / rollback
```

## Reconciliation rules

1. Search for an existing equivalent before adding a plan.
2. Reconcile every new plan with `implementation_plan.md`.
3. Every overlapping plan must name its canonical replacement or declare why it is intentionally complementary.
4. Never delete protected architecture history during the first reconciliation pass.
5. Prefer redirect / index metadata before physical moves.
6. Do not mark infrastructure, capability, dependency, or integration as missing without current code evidence.
7. Do not treat examples, targets, aspirations, vendor documentation, or proposed code as implemented capabilities.
8. Keep historical plans available for traceability, but clearly prevent literal execution.
9. Do not maintain multiple competing “master plans” for the same execution scope.
10. A candidate list is not an execution queue; the next plan becomes executable only after the current plan completes or is explicitly stopped.
11. If implementation evidence materially contradicts the plan, stop and reconcile rather than rationalizing the mismatch.
12. Security-sensitive, destructive, irreversible, or externally billable changes require explicit rollback / recovery consideration before approval.

## Failure, pause, and rollback rules

A plan may be paused before completion when:

- a key assumption is disproven;
- provider / API behavior differs materially from the documented contract;
- verification reveals unacceptable regression;
- cost, quota, resource, or security behavior exceeds the approved envelope;
- the intended outcome is not being measured correctly.

The plan must record the reason and current state. Restarting execution requires the plan to be revalidated against current code and dependencies.

For runtime changes, the implementation should expose the smallest practical rollback path, such as an existing feature flag, configuration switch, provider fallback, or safe revert.

## Completion rule

A document existing in the repository is not completion evidence.

A plan is complete only when all applicable evidence exists:

```text
approved scope implemented
+ tests / verification passed
+ deployed when deployment is in scope
+ observability confirms expected behavior
+ rollback / recovery path is known and validated when applicable
+ outcome measured against baseline when applicable
+ completion evidence recorded in the repository
```

## Plan lifecycle in one line

```text
Candidate → Proposed → Approved → Active → Verified → Observed → Complete → Historical
                              ↘ Blocked ↗
                              ↘ Superseded
```

This policy is intentionally stricter than a documentation workflow: **plans are hypotheses and execution contracts, while tested code and measured evidence determine reality.**