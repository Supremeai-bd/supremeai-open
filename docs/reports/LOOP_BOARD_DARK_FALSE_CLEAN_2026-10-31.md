### Finding (scout radar, report-only — no closure request)

**The r63 founder-directive board-clean gate prints a FALSE "clean and healthy" line when the board plane is DARK.**

Blob under audit: `764b6370` (scripts/agents/continuous_agent_loop.py, main @ 2026-10-31 ~01:2xZ, 241943 B). Defect still present on re-verify before this filing.

#### The defect

The new rotation gate (rotation section, after the P0-drainage block):

```python
claimable_count = 0
if not board_unavailable and isinstance(raw, list):
    claimable_count = sum(...)
if claimable_count < 5 and not force_flag:
    print(f"ACTION: System is clean and healthy (claimable issues: {claimable_count}/5 threshold). Observation roles idle.")
    return 0
```

When `board_unavailable` (e.g. `--offline`, or gh absent AND the tower fallback plane dark), `claimable_count` stays 0 and the gate prints **"System is clean and healthy (claimable issues: 0/5 threshold)"** — presenting an UNSEEN count as a verified clean zero. This contradicts, within the same run:

1. The preflight audit printed seconds earlier on the same dark plane: `"preflight P0 scan: board plane dark — open P0 blockers UNSEEN, not zero (U2)"` — the loop's own dark!=zero doctrine.
2. The board-unavailable honest-failure note: `"issue board unavailable (...): board query honestly skipped) — skipping solver dispatch. Cadence roles still evaluated."` — which says cadence roles are "still evaluated", then the gate idles them. Two adjacent lines disagree.

#### Live evidence (first-hand, this tick)

Clean sandbox worktree, byte-identical to main blob `764b6370`:

```
$ python3 scripts/agents/continuous_agent_loop.py --offline
⚠ preflight P0 scan: board plane dark — open P0 blockers UNSEEN, not zero (U2)
...
! issue board unavailable (offline mode (--offline/OFFLINE env): board query honestly skipped) — skipping solver dispatch. Cadence roles still evaluated.
ACTION: System is clean and healthy (claimable issues: 0/5 threshold). Observation roles idle.
rc=0
```

Encoded as a standing witness check in the auditor's boundary suite (run8_p0_test2 check E): the check FAILS BY DESIGN the day the honest-dark fix lands, forcing re-adaptation.

#### Why it matters (operator impact)

During a tower outage or fleet-wide gh absence, operators reading the loop log see "System is clean and healthy" — a false-green fleet status line. This is the same honesty class the loop already fixed twice: the failed-PR audit's dark-vs-zero split (`list | None` contract) and the preflight "UNSEEN, not zero" lines. The new gate reintroduced the class on the rotation plane.

#### Proposed minimal fix (smallest safe change, loop file only)

Behavior (suppress rotation when dark) may stay exactly as-is — only the LINE must be honest:

```python
if claimable_count < 5 and not force_flag:
    if board_unavailable:
        print("ACTION: Board plane dark — claimable count UNSEEN, not zero (U2). "
              "Observation roles idle (board-clean threshold unverifiable).")
    else:
        print(f"ACTION: System is clean and healthy (claimable issues: {claimable_count}/5 threshold). Observation roles idle.")
    return 0
```

Optional sibling alignment: the board-unavailable note "Cadence roles still evaluated." should read "... Cadence roles subject to the board-clean gate." so the two lines agree.

#### Reflection Evidence (why + alternatives_rejected)

**why**: fresh code landed this tick regressed the loop's own U2 dark!=zero doctrine on a user-visible status line; first-hand live repro, zero-cost one-line honest fix.

**alternatives_rejected**: (1) suppress rotation when dark without touching the line — keeps the false claim; (2) run rotation when the plane is dark — changes founder-directive behavior, admin-lane decision, not mine to make; (3) not filing — leaves a false-green line that misleads operators precisely during outages, when truthful status matters most.

#### Disposition

report-only radar row; Recovery: N/A. No claim taken, no Closes footer, no code patch attached (founder-directive code — admin/author lane owns the change). Evidence reproducible from any clean worktree on blob >= 764b6370 until fixed.
