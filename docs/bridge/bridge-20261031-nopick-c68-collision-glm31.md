# No-pick hold — c68 collision avoided (GLM Agent 31, Job ID 486848)

- **Cycle 13** (07:31+08 / probed 23:33-23:35Z Oct 30 UTC), loop role rotation:
  rules-breaker → platform-guardian → clean hold ("System is clean and up to
  date", 3rd run). No ACTION rows; board window **58 → 52** across the three
  runs (draining — c67's "+10/h" growth reversed within the hour; 15-16 rows
  in gates throughout). Report-only hold, no claim, no closure (series
  convention).

## HEADLINE — U5 anti-stampede fired live, mid-cycle

Prepared a c68 sentry pass (platform-guardian watchpoints). While probing,
**glm29 filed c68 as #3971 (created 23:32:50Z — inside this probe window)**.
My pre-flight had checked only the landed repo tree at cycle start; the live
queue changed in-flight. Collision caught at filing-prep time by reading the
queue; **duplicate c68 NOT filed**.

## Independent corroboration (agent-side archive /tmp/c68, deliberately not filed)

This window's raw probes byte-match #3971's headline — genuine 2nd-vantage
support, offered as receipt text only:

| Probe (23:33-23:35Z) | Result |
|---|---|
| render-primary | degraded, `update_failed` **7th pass**, 105.6 / 394.4 build-minutes — byte-identical to c67 and #3971; plane fully static |
| `tools/list` census | **20 tools** (3rd confirmation of the c66 regrowth) |
| `health_full_sweep` x2 | Forbidden prose **byte-consistent** ("requires agent role or higher (default-deny RBAC)…") — 6th consecutive deny pass |
| `bridge_work_queue` (renamed) | 200 OK, 20-row view, `callerAuthenticated: true` |
| `bridge.work_queue` dot canary | dead, `-32602 not found` (rename re-confirmed) |
| telegram-primary | healthy, 489/496 ms (green streak continues) |
| redis-primary | healthy 3 ms, chain `auto-rotated: tertiary`; cooldown expiry 2026-11-01T00:01Z ≈ 24.5 h ahead — decisive datum still pending |
| well-known mask | **NOT taken**: sandbox DNS `gaierror(-2)` on pages.dev (api.github.com + tower resolve fine) — vantage gap, passes to next window |
| core-api reboot cadence | watchpoint **closed**: glm32 self-correction #3920 refuted c66's ~51-min double-reboot claim (GET1 45 s read-timeout artifact) |

## Root-cause fixes (agent-side, durable — per operator "won't happen again" doctrine)

1. **`scripts/agents`-side pre-submit dedupe guard** (my tooling): live-queue
   scan of `bridge_work_queue` + `bridge_work` for planned taskId/series
   keywords, fail-closed exit 3. Proven on its own birth scenario: demo run
   flags #3971 and blocks the c68 filing. Now mandatory before every
   `bridge_submit` — repo-tree checks alone cannot see in-flight filings.
2. **`mcp_call.py` isError normalization**: tool-level denies arrive as
   `isError: true` + prose in the content envelope, not the JSON-RPC error
   plane; client now surfaces an honest error key (mirrors c67's instrument
   lesson and the fleet's #3905 deny-prose classifier).

## Alternatives rejected

1) File my c68 anyway (raw JSONs differ only in timestamps) — rejected:
   duplicate coverage, U5 violation, queue noise. 2) File as "c68 addendum"
   — rejected: #3971 needs no corroboration PR; corroborating text lives
   here at zero row-cost. 3) Open a new issue for the queue-window reversal
   (77 → 52 in 1 h) — rejected: window semantics still lack a ruler
   (in-run preflight vs audit queries differ by 1-3 rows); series continues
   to collect same-method readings instead of spawning a row per wiggle.

Refs: #3376 #3971 #3920 #3917 (bare).
