# Federation Specs — Single Source of Truth (Compact Index)

Companion to `AGENTS.md` / `AGENT_RULES.md`. One-line purpose per spec; open the linked file for full detail.

| Spec | Purpose | Key invariant |
|---|---|---|
| S01 Atomic Claim | Atomic task claim before branch | No Claim → No Branch |
| S02 Structured Evidence | PR evidence envelope (diff scope, SHA-256, tests exit 0) | Controller verifies, never trusts self-report |
| S03 Work Next | Pick next task from board | Priority + role classification |
| S04 Tool Consolidation | MCP tool surface consolidation | Single door, zero credential leak |
| S05 Unified Queue | Task queue / work order | Atomic claim + rebase |
| S06 Claim Quota | Per-agent claim quota | Fairness + anti-starvation |
| S07 PR Evaluator | Automated PR evaluation | Evidence before merge |
| S08 Mistake Immunity | Mistake capture & immunity | Verified solution → memory |
| S09 Role Trigger Matrix | Role cadence & dispatch | Per-role last_run |
| S10 Ecosystem Scout | Empty-board audit → issues | Read-only, no issue creation on idle tick |
| S11 Surgical Adoption | Minimal diff adoption | ≤30 files / ≤200 KB |
| S12 Nightly Train | Scheduled heavy suites | P0/P1 preemption + dedup |
| S13 Knowledge Graph | 1-hop context graph | Graceful fallback if unavailable |

## Core invariants (all specs)
- Law of Minimal Elegance: simple + effective > clever + complex.
- Zero-Admin ≤0.01%; system guards enforce boundaries.
- Evidence before action; smallest safe diff.
- Satellites hold 0 issues/PRs (FEDERATION_CHARTER).

Full specs: `docs/S01_*.md` … `docs/S13_*.md`.
