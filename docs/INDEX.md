---
id: docs-index
title: "Documentation Index — SupremeAI Open (broad doc-circle index)"
document_role: index
status: active
canonical: true
owner: governance
last_verified: 2026-10-16
related_docs:
  - AGENTS.md
  - AGENT_RULES.md
  - ECOSYSTEM_MAP.md
  - docs/GUARDIAN_EVALUATION.md
source_issue: 121
source_pr: null
supersedes: []
superseded_by: []
---

# Documentation Index

The broad documentation index for `Supremeai-bd/supremeai-open`, per
[AGENT_RULES.md §8](../AGENT_RULES.md) ("`docs/INDEX.md` is the broad
documentation index"). Entry point is [`AGENTS.md`](../AGENTS.md); navigation
rules live in §8 — no orphan canonical documents, broken links are defects,
this index links **every tracked `docs/*.md` file**.

## Agent constitution (entry points, repository root)

| Document | Role |
|---|---|
| [`AGENTS.md`](../AGENTS.md) | Agent entrypoint / universal constitution — authority, stateless lifecycle, Zero-Admin submission pathways |
| [`AGENT_RULES.md`](../AGENT_RULES.md) | Single source of agent policy — universal rules (U1–U10), engineering policies, roles, fail-closed guard list |
| [`ECOSYSTEM_MAP.md`](../ECOSYSTEM_MAP.md) | Federation repository directory, cross-repo routing, automation topology (+ Mermaid diagram) |
| [`README.md`](../README.md) | Public boundary artifact table, stable Gateway contract, bridge lane |

## docs/ — domain documents (all tracked files)

| Document | document_role | Scope |
|---|---|---|
| [`docs/AGENT_LOOP_SPEC.md`](./AGENT_LOOP_SPEC.md) | reference | Single deterministic task envelope (`task-envelope-v1`); evidence-tier SSOT (§4); VALID_GROUPS registry (§3) |
| [`docs/AUDIT_2026-10-15.md`](./AUDIT_2026-10-15.md) | audit | 2026-10-15 deep audit record (`id: audit-2026-10-15-deep-audit`) |
| [`docs/AUDIT_2026-10-15-duplicate-sweep.md`](./AUDIT_2026-10-15-duplicate-sweep.md) | audit | 2026-10-15 duplicate/conflict sweep follow-up |
| [`docs/AUTONOMY_LOOP_CONTRACT.md`](./AUTONOMY_LOOP_CONTRACT.md) | reference | The continuous agent-loop contract the dispatcher implements (§3 back-to-back cycles) |
| [`docs/CONSUMERS.md`](./CONSUMERS.md) | policy | Consumer onboarding: the 3-line Gateway contract, key lifecycle, error semantics |
| [`docs/CONTRIBUTING.md`](./CONTRIBUTING.md) | policy | Contributor + agent quickstart: the 8-step loop, bridge lane, verification tiers, caps, protected paths |
| [`docs/FEDERATED_CI_WATCHER.md`](./FEDERATED_CI_WATCHER.md) | reference | Federated CI failure watcher — cross-repo task normalization (`id: federated-ci-watcher`) |
| [`docs/GUARDIAN_EVALUATION.md`](./GUARDIAN_EVALUATION.md) | reference | CI Guardian PR evaluation rules — verdict derivation, scoring, merge eligibility (`id: guardian-evaluation`) |
| [`docs/HEARTBEAT_PROTOCOL.md`](./HEARTBEAT_PROTOCOL.md) | reference | Agent heartbeat protocol |
| [`docs/INGRESS_SECURITY_POLICY.md`](./INGRESS_SECURITY_POLICY.md) | policy | Ingress security — Zero-Force-Push, stale-base rejection, public-first policy |
| [`docs/OPS_ACTIONS_QUOTA_RUNBOOK.md`](./OPS_ACTIONS_QUOTA_RUNBOOK.md) | runbook | Private Actions quota & scheduler freeze runbook (free-org 2,000 min/month budget) |
| [`docs/INDEX.md`](./INDEX.md) | index | This file — the broad documentation index |

## Stable machine contracts

| Surface | Path |
|---|---|
| SupremeAI API Gateway (OpenAI-compatible `/v1/chat/completions`) | [`api-schemas/gateway.openapi.yaml`](../api-schemas/gateway.openapi.yaml) |
| CI Guardian evaluation schema (Draft 2020-12) | [`api-schemas/guardian-evaluation.schema.json`](../api-schemas/guardian-evaluation.schema.json) |
| Task-contract envelope schema | `scripts/agents/task_contract_schema.py` (embedded by `continuous_agent_loop.py`) |

## Reading path (document circle)

```text
AGENTS.md (entrypoint)
  → AGENT_RULES.md (policy)
    → Task Contract / docs/AGENT_LOOP_SPEC.md (envelope + tiers)
      → Domain doc for the assigned task (this index)
        → Issue / PR / Evidence
```

The §8 metadata block (id/title/document_role/status/canonical/owner/
last_verified/related_docs/source_issue) is demonstrated by the frontmatter of
this file and of the docs that carry it (e.g.
[`docs/GUARDIAN_EVALUATION.md`](./GUARDIAN_EVALUATION.md)); newer canonical
documents seed it per [AGENT_RULES.md §8](../AGENT_RULES.md).

## Related Documents

- [`AGENTS.md`](../AGENTS.md) — agent entrypoint
- [`AGENT_RULES.md`](../AGENT_RULES.md) — §8 document-circle policy this index implements
- [`ECOSYSTEM_MAP.md`](../ECOSYSTEM_MAP.md) — federation map + topology diagram
- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — contributor onboarding
