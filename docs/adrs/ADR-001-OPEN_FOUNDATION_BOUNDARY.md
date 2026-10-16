---
id: adr-001-open-foundation-boundary
title: "Open Foundation Boundary — Public-First SSOT Split"
document_role: adr
status: accepted
canonical: true
decided: 2026-10-15
deciders: "Admin (governance issue #155); boundary is constitutionally admin-owned (AGENTS.md §1.3/§4)"
governing_issue: 155
related_docs:
  - AGENTS.md
  - docs/INGRESS_SECURITY_POLICY.md
  - docs/AGENT_PORTAL_SPEC.md
  - docs/ZERO_ADMIN_GUIDE.md
---

# ADR-001: Open Foundation Boundary — Public-First SSOT Split

## Status

**Accepted** — 2026-10-15, enacted by the #155 workflow diet and the `supremeai-open` public boundary contract. Recorded as the founding ADR by issue #44.

## Context

The federation initially grew as a single private monorepo (`Supremeai-bd/supremeai`) with everything inside it: backends, CI, schemas, agent tooling, docs. External autonomous agents had no credential-free way to contribute; every contribution required private access or admin hand-holding, which violated the Zero-Admin budget (AGENTS.md §2.1, admin effort ≤ 0.01%). At the same time, most of what agents need to verify — loop contracts, guards, schemas, docs, examples — provably requires **no** private context.

## Decision Drivers

- **Zero-Admin budget:** contribution and landing must complete without human review.
- **Quota:** the private org runs on a Free Actions budget (~2,000 min/month, shared); validation must be free and unlimited where possible.
- **Security boundary:** secrets-bearing and production-context content must never touch the public repo.
- **Determinism / fail-closed doctrine:** verification must be reproducible from public artifacts alone (U2).

## Considered Options

1. **Single private repo, credential-gated contributors** — violates Zero-Admin (every external agent needs access grants) and concentrates quota cost.
2. **Full open-source monorepo** — unacceptable: backends, secrets-bearing configs and production context would cross the boundary; also burdens contributors with irrelevant private complexity.
3. **Public-First SSOT split (CHOSEN)** — `supremeai-open` is the public SSOT for everything provable in public; the private monorepo stays the SSOT for private-context work; landed public work flows into private automatically via the bridge (webhook / direct dispatch), never by hand.

## Decision

`Supremeai-bd/supremeai-open` is the **public SSOT and the only public work-entry surface** for the federation. The approved public surface set (scripts/, api-schemas/, docs/, examples/, infrastructure/mcp-control-plane, workflow pair, issue templates) is codified in `scripts/ci/boundary_sanitization_guard.py` and may only be expanded by a PR referencing a governing issue. Everything else — private backends, deployment, secrets-bearing integration — lives in `Supremeai-bd/supremeai` and receives public work exclusively through the automated bridge. No agent or contributor opens manual PRs against the private repo for public-boundary work.

## Consequences

**Positive:** zero-credential contribution (fork+PR); unlimited free public CI minutes absorb all provable validation; agents onboard from `mcp.json` + public docs alone; the boundary is machine-checkable rather than reviewer-judged.

**Negative / accepted costs:** two-repo synchronization must be automatic (bridge) — any manual sync step would rot; drift between README's boundary contract and shipped content must be guarded (boundary guard, anti-duplicate, quota runbook exist because of this cost).

**Neutral:** workflow count is capped at two on the public side (pipeline.yml, landing.yml) — re-introducing the deleted `open-guards.yml`/`ci.yml`/`continuous-agent-loop.yml` is a boundary decision, not a convenience.

## Validation Evidence

- 🧱 **Boundary Sanitization Guard (#107):** full-tree scans on every PR — 200+ files scanned, 0 violations across all landed PRs of this session (e.g. PRs #229, #247, #253, #290, #293, #294, #298); guard self-test embedded in CI.
- **Guards as a fleet:** 7 PR guards registered in `docs/AGENT_LOOP_SPEC.md` §5 and asserted by the Loop-Contract Parity Guard (#118).
- **Landing evidence:** consecutive fully-autonomous landings with auto-closed issues (PRs #229/#232/#247/#253/#293/#294/#298 — each merged by the gate with zero admin action, task issues auto-closed by `Closes #N` propagation).
- **Ingress enforcement:** Zero-Force-Push live at three layers — local pre-push hook (5/5 self-test scenarios), CI 🛡️ Ingress Hook Guard, and server-side pre-receive rejection (observed live on PR #290's rebase attempt).

## Related Documents

- [AGENTS.md](../../AGENTS.md) — §2.3 Public-First SSOT doctrine (normative statement of this decision)
- [docs/INGRESS_SECURITY_POLICY.md](../INGRESS_SECURITY_POLICY.md) — push/merge enforcement surfaces for the boundary
- [docs/AGENT_PORTAL_SPEC.md](../AGENT_PORTAL_SPEC.md) — the two-repo architecture and machinery executing this split
- [docs/ZERO_ADMIN_GUIDE.md](../ZERO_ADMIN_GUIDE.md) — how work crosses the boundary autonomously
- [docs/OPS_ACTIONS_QUOTA_RUNBOOK.md](../OPS_ACTIONS_QUOTA_RUNBOOK.md) — the quota rationale for shift-left validation
