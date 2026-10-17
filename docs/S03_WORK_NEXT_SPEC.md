# S0.3 — work.next(): Computed Actionable Queue — Full Specification

Task issue: #458 · Seq S0.3 of the Simplification Roadmap · P1-high
Author: Z.ai Code autonomous contributor (session web-26454b1b, zero-credential bridge lane)
Status: DELIVERED — spec + reference implementation + executable contract tests (prep lane; fires on claim)

---

## 1. Problem — agents guess, agents collide

Today an autonomous agent that wants work must: scrape the issue list,
parse the label matrix (P0-P3, sequence-hold, handoff, area, layer),
reverse-engineer which issues are claimed (label plane? comment plane?
expired?), check for in-flight WOs to avoid duplicates, and then pick.
Every step is a guess. The battle record:

- 20 open issues idled while the fleet guessed wrong about the claim-wall (2026-10-16/17).
- #453 was claimed but fleet WO #455 raced it — a duplicate-queue collision the agent could have avoided with one computed answer.
- #398 was re-targeted even though an in-flight WO (#442) already covered it — wasted intake, self-duplicate.

Design principle violated: single path. There are N paths today and each
agent invents its own. work.next() makes picking THE task a function call.

## 2. Solution — one call returns the one task

Add a single Control Tower MCP tool:

    work.next() -> WorkNextResult

The tower computes it from the live board snapshot (issues + labels +
atomic-claim markers + in-flight WO registry). No agent-side parsing of
labels ever again. The output is deterministic: same board, same answer.

    WorkNextResult {
      "pick":          { issue, title, priority, claim_decision, why },
      "runner_ups":    [ up to 3 more, same shape, ranked order ],
      "evaluated":     <int, issues considered>,
      "excluded":      { closed: n, live_foreign_claim: n, inflight: n, non_task: n },
      "computed_ts":   "2026-10-17T04:00:00Z"
    }

## 3. Claimability filter (normative — reuses S0.1 decision matrix)

An issue is CLAIMABLE iff all of:

1. State is open.
2. It is a task issue (not a bridge WO — WOs carry the bridge: prefix labels).
3. No live claim by a DIFFERENT agent (S0.1 CONFLICT_OTHER excludes it).
4. Expired claims DO NOT exclude: same agent -> GRANT_RENEW, other agent -> GRANT_TAKEOVER (the comment IS the ledger — no database).
5. No in-flight WO or open PR already targets it (race guard, U4 no-duplicates — the #453/#455 and #398/#442 lessons).
6. Not sequence-hold / handoff-blocked (label respected; those wait on predecessors, not agents).

Priority parse: P0-critical > P1-high > P2-medium > P3-low; missing
priority label ranks as P3 (never invisible, never first).

## 4. Ranking (deterministic, no tie left to chance)

    sort key = (priority_tier, issue_number ascending)

Lower tier number first (P0 before P1); within a tier the OLDEST issue
(lowest number) first — FIFO, the same fairness the board shows by age.
The runner_ups list is simply positions 2..4 of the same sort.

## 5. Error contract

| Code | Meaning | Agent action |
|---|---|---|
| E_QUEUE_EMPTY | nothing claimable right now | heartbeat and retry after TTL horizon (30m) |
| E_BOARD_UNAVAILABLE | snapshot fetch failed | retry with backoff; never guess from cache |

work.next() NEVER returns an unclaimable issue. If it returns a pick, the
immediately following work.claim(pick.issue) by the same agent succeeds or
fails only on a race that happened between the two calls (which work.claim
then resolves as CONFLICT_OTHER — the agent re-runs work.next()).

## 6. Guard integration

- Intake dedup: work.next() consults the in-flight WO registry, so agents stop creating self-duplicates (#398-class waste).
- Claim-guard: picks are claimable by construction; the guard stays fail-closed as the second wall.
- S0.4 consolidation: work.next survives as one of the five core tools — it is the front door's doorman (work.claim is the door).

## 7. Acceptance criteria (machine-checked)

1. Determinism: same snapshot -> identical result (no wall-clock in ranking).
2. Closed issues never picked.
3. Live foreign claim excludes; expired claims re-enter with correct decision code (GRANT_RENEW / GRANT_TAKEOVER).
4. In-flight WO excludes (race guard).
5. P0 sorts before P1 before P2; FIFO inside a tier.
6. Missing priority ranks P3, after labeled P3 on same number? No — same tier, FIFO by number decides.
7. E_QUEUE_EMPTY reachable when every open issue is excluded.
8. Input snapshot is never mutated (pure function).
9. runner_ups has at most 3 entries and never contains the pick.
10. Suite runs offline (unit) with a skip-until-landed live layer, S0.1/S0.2 pattern.

## 8. References

- Task issue #458 · siblings #456 (landed PR #462 + commit 073166b1 work_claim), #457 (WO #464), #459
- Race incidents: #453 vs WO #455; #398 vs WO #442 (in-flight)
- Decision matrix source: docs/S01_ATOMIC_CLAIM_SPEC.md section 3 (imported, never copied)
- Deliverables: scripts/tower/work_next_reference.py, tests/test_s03_work_next_contract.py
