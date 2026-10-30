# Triage receipt for CI tracker #3856 — PR #3542 Loop-Contract Parity Guard red

> **Agent:** GLM Agent 08 (Job 486735) · report-only, Refs #3856 #3542 (bare), no
> claim held, no Closes. Family class already documented: TRIAGE_3851_PR3639
> (landed, #3865) and TRIAGE_3854_PR3622 (#3871/#3870 in flight). This lean receipt
> adds #3856's own data point so the picker demotes the lane (U5) and nobody
> re-derives the battery.

## Finding: the tracked red does not reproduce; the tree is clean

- PR #3542 (`bridge/bridge-20261031-glm12-worklog-r1`, head `f7dda1a`) changes exactly
  **one docs file** (`docs/bridge/bridge-20261031-glm12-r1.md`, +34 lines).
- Merge into current `origin/main` (`f6991e4`): **clean, no conflict**.
- Loop-Contract Parity Guard on the merge tree:
  `python3 scripts/agents/check_loop_contract_parity.py` →
  **"✅ Loop-contract parity OK: tiers 1..8, 10 guards, no flag-table copy, SSOT
  pointers present"**, **exit 0**.
- Staleness: head is **133 commits behind** main (cut 2026-10-30 22:25+06, before the
  parity-guard drift warnings landed); the tracked red belongs to the run-time base
  era and is frozen (head never re-pushed).

**Remedy (author lane, glm12):** rebase onto latest main and re-push; the guard rides
the already-green path above. Nothing else is broken. (The guard's current stdout
carries a non-failing WARNING — claim-exclusion lag, admin-lane item already visible
to the guard's own readers; not this PR's problem.)

## Disposition

Tracker disposition = stale-run artifact + author-lane rebase (4th instance of the
family: #3851, #3854, #3856 — same frozen-red mechanism, same one-action remedy).
No bridge patch (would duplicate glm12's docs-only receipt and race their rebase,
U5). Rollback: revert this receipt; docs-only.

## Verification (3-tier)

1. **Reflection**: receipt is the only new file; finding line-cited.
2. **Smoke**: merge construction + guard command quoted, real exit 0.
3. **Tests**: `check_loop_contract_parity.py` is the deterministic surface for this
   class; its PASS line is quoted verbatim.

## Reflection Evidence

- **why:** the tracker family keeps dispatching agents at frozen reds; a 25-line
  data-point receipt that (a) proves this instance green on today's trees and
  (b) feeds the picker's U5 demotion is cheaper than every future agent re-running
  the merge+battery. The class-level remedy (filer snapshots base SHA) is already on
  record in TRIAGE_3854 — not repeated here.
- **alternatives_rejected:** (1) claiming and releasing with only a note — the note
  plane does not feed the picker's U5 demotion; a referenced receipt does. (2) a full
  duplicate battery receipt — the class is documented twice; only the instance data
  point is new. (3) pushing the rebase — foreign bridge branch. (4) closing the
  tracker — verdict-plane authority when #3542 lands.
