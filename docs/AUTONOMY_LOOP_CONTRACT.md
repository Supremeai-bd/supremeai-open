---
id: autonomy-loop-contract
title: "Autonomy Layer — Continuous Loop Integration Contract (supremeai-open)"
document_role: reference
status: active
canonical: true
owner: coder
last_verified: 2026-10-29
related_docs:
  - AGENTS.md
  - docs/AGENT_LOOP_SPEC.md
  - CONTRIBUTING.md
source_issue: 26
source_pr: null
supersedes: []
superseded_by: []
---

# Autonomy Loop Integration Contract

This document is the public integration contract for the autonomy-layer continuous
execution loop implemented by `scripts/agents/continuous_agent_loop.py`. It exists so
external agents (IDE copilots, scheduler daemons, other federation repos) can drive or
embed the loop without reading its source, and so the 8-step cycle, the stateless
lifecycle and the machine-checkable surfaces are declared exactly once.

Scope of truth (anti-drift): this document describes the cycle and the integration
hooks. The canonical flag surface is `docs/AGENT_LOOP_SPEC.md` §4b; the canonical
evidence-tier list is `docs/AGENT_LOOP_SPEC.md` §4. Neither is duplicated here.

## 1. The 8-Step Cycle (SSOT)

`run_cycle()` executes exactly these phases, in order. Step names below are copied
verbatim from the runner's step labels — external integrators may key logs, dashboards
or hooks on these strings.

1. **Understand** — load the task contract. An explicit `--issue <n>` is resolved to a
   live board issue; `--pick-next` scans the upstream board (implicit claimable
   lifecycle, #222: any open issue is claimable unless it carries an exclusion
   label from the SSOT set — the authoritative enumeration is the
   `EXCLUDED_LABELS` frozenset in `scripts/agents/continuous_agent_loop.py`,
   deliberately not duplicated here: hand-copies of it drifted twice
   (pipeline.yml board pre-check, WO #2221/PR #2222; this list, caught by
   parity guard 8); priority from labels
   P0<P1<P2<P3<unlabeled, oldest issue number breaks ties). Fail-closed: a
   closed issue, an unparseable contract, or a duplicate-PR preflight hit
   aborts the cycle.
2. **Rules** — verify the constitution is present and readable (`AGENTS.md`,
   `.github/PULL_REQUEST_TEMPLATE.md`; the loop's RULE_FRESHNESS_FILES). Fail-closed on absence.
3. **Inspect State** — git worktree hygiene gate. A dirty worktree stops the cycle
   (bypassable only via `--force`, which integrators should treat as test-only).
4. **Branch** — ensure the isolated working branch for the task (auto-created session
   branch on collision; never work on a foreign PR branch).
5. **Work** — the dispatch phase: role resolution (7 roles; coder/auditor/ci-fixer/
   security-breaker/browser-qa/planner/watcher) and execution of the task body within
   the declared Touching Files boundary.
6. **Verify** — run the evidence-tier contract. The tier list is SSOT'd in
   `docs/AGENT_LOOP_SPEC.md` §4 (currently 8 tiers; the count is derived, never
   hardcoded, and parity-enforced by `scripts/agents/check_loop_contract_parity.py`).
   A failing tier fails the cycle — no partial passes.
7. **Record** — generate the submission record: a PR body embedding the task-contract
   YAML (7-`##`-section template), the derived evidence list, and the claim. With
   `--auto-pr` the runner submits via `gh pr create`; with `--fork-owner` (Pathway 2)
   it pushes to the named fork and opens the PR from there. `Closes #N` must ride in
   the commit message (squash-merge auto-close doctrine, AGENTS.md Invariant 4).
8. **Return** — board-freshness re-poll and cycle completion report. The cycle ends
   with a fresh view of the board so the next cycle never acts on stale state.

## 2. Stateless Lifecycle Contract

The loop holds **no durable task state between cycles** (AGENTS.md §2):

- Every cycle re-derives its world from GitHub: the issue board, the PR registry and
  the git state. There is no local queue, no cursor, no resume checkpoint.
- The Task Envelope (`task-envelope-v1`, SPEC §2) is the only cross-boundary payload;
  it is deterministic — byte-identical rebuilds are part of the evidence contract.
- Integration implication: schedulers may kill and restart the loop at any cycle
  boundary without corruption; work in progress belongs to an isolated branch and is
  recoverable purely from git + the issue claim.
- Persistence that does exist is evidence-shaped, not state-shaped: verify transcripts
  are captured as CI artifacts (retention 14 days), never as loop input.

## 3. CLI Runner Hooks (Integration Surface)

The runner is a single stdlib-only Python entrypoint:
`python scripts/agents/continuous_agent_loop.py <mode> [flags]`.

Integration modes (non-exclusive):

- **`--pick-next`** — autonomous mode: claim the highest-priority claimable issue and
  run one full 8-step cycle. This is the mode the pipeline's `agent-loop` job uses when
  dispatched manually; its */30 schedule is disabled per admin directive.
- **`--issue <n>`** — targeted mode: claim a specific issue (still subject to the
  duplicate-PR preflight and all gates).
- **`--loop` + `--max-tasks N`** — sequential mode: N cycles back-to-back with a short
  cooldown; each cycle re-polls the board (freshness between tasks is contractual).
- **`--task-envelope`** — envelope mode: emit the deterministic Task Envelope as the
  final stdout line (human banner goes to stderr) and exit — for agents that only need
  the canonical work order. `--emit-prompt` / `--emit-contract` are deprecated shims
  for this mode.
- **`--verify-only`** — gate mode: run the evidence tiers and exit; the final stdout
  line is the parity marker `CONTRACT_VERSION=agent-loop-contract/1`. This is the
  machine-checkable health probe for integrators.
- **`--auto-pr`** — submission hook: after a passing cycle, submit the PR directly
  (Pathway 3). Without it, the runner prints the record for a human or wrapper agent
  to submit.
- **`--fork-owner <owner>`** — Pathway 2 hook: push the cycle's branch to the named
  fork and open the PR with `head <owner>:<branch>` (env fallback:
  `SUPREMEAI_FORK_OWNER`).
- **Context qualifiers** — `--role`, `--task-type`, `--priority`, `--group`,
  `--touching-files` shape the envelope/contract when no board issue drives the run
  (`--allow-adhoc` enables that offline/testing path; `--force` bypasses the dirty-
  worktree gate and is not recommended for real submissions).

The full canonical flag surface (including private-mirror-only flags) is
`docs/AGENT_LOOP_SPEC.md` §4b — that table, not this list, is authoritative.

## 4. Exit-Code Contract

| Code | Meaning |
|---|---|
| 0 | Success (cycle completed, or verify/envelope modes produced their output) |
| 1 | Task-level failure (contract violations, failed gates, failed verification) |
| 2 | Guard/environment failure (operational error — e.g. binary missing, tooling absent) |

Integrators should treat exit 2 as "the harness is broken", not "the task failed" —
retrying a broken harness unchanged is the wrong response.

## 5. Versioning & Parity

- `CONTRACT_VERSION=agent-loop-contract/1` is the cross-repo parity marker (printed as
  the final `--verify-only` stdout line, mirrored in the private codebase; contract in
  `docs/AGENT_LOOP_SPEC.md` §4b).
- Drift between docs and code is machine-checked by
  `scripts/agents/check_loop_contract_parity.py` (tier-count parity, guard-set parity
  against `pipeline.yml`, flag-table copy prohibition, SSOT pointers,
  claim-exclusion parity for the pipeline pre-check and this document).
- Changing the cycle (adding/reordering steps, changing tier count, changing the claim
  policy) requires: runner edit + SPEC edit + passing parity guard **in the same PR**.

## Related Documents

- [AGENTS.md](../AGENTS.md) — agent entrypoint, zero-admin pathways, policy invariants
- [docs/AGENT_LOOP_SPEC.md](./AGENT_LOOP_SPEC.md) — envelope schema §2, canonical flag surface §4b, open guards §5
- [CONTRIBUTING.md](../CONTRIBUTING.md) — contributor quickstart and submission paths
