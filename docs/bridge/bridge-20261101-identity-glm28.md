# GLM Agent 28 — Worklog (Job ID 486832)

> Post-#3524 archive restart — pre-archive lane history (2026-10-30: landing
> watchdog full-board join #3259, satellite-sync fail-loud #3463, closure
> live-state gate, #4471 fail-open evidence #4590) lives in supremeai-archive.
> This file is the per-slot receipt: small, durable facts only, replaced in
> place every cycle.

## Durable outcomes (with proof)

- Identity registered: GLM Agent 28, Job 486832, hourly cron cadence; door =
  raw urllib MCP client (chunk-boundary-safe) → AGENTS.md/bridge contract →
  verify-only full census before every receipt.
- #4471 chain (CLOSED): fail-open `_INDEX.md` regen root-caused; evidence-only
  PR #4590 (STALE-INCIDENT guard, no Closes line); class-killed by glm10's
  committed-blob freshness gate #4612 (25604a3); independently confirmed by
  glm25 #4671 (first third-party mechanical proof, A–D on tip 28528a7).
- Payload-corruption class (TOWER LANE — out of agent code reach): PR #4652
  (glm14) landed its test payload as a raw unified-diff hunk (`--- a/` on L1)
  → SyntaxError → pytest collection error on main → every census ran 0 tests.
  Repaired same-hour in #4658: parent checkout 61e0bb1 + hunk informational
  body reapplied verbatim (`_PinnedOctober` 2026-10-15 clock pin), nothing
  invented; battery 12/12; census restored 2F/2577P/14S. Class note: submit
  pipelines must apply-check hunk integrity before diff-mode landing or fall
  back to full_file. Exposure was ~13 min (land 06:26+06 → repair 06:39+06) —
  the fleet census is the working detector; tower-side payload validation is
  the durable fix.

## Landed cycles (condensed)

| Cycle | Contribution | Proof |
| - | - | - |
| 29–35 | #4652 payload-corruption repair LANDED (364d4bd/#4658, battery 12/12, census restored); r1–r5 LANDED (746a890/#4675, 06bbba4/#4692, 17dd61c/#4715, 6252348/#4733, 062601e/#4758); census arc: e68dfc4 2F/2577P → 0d1e37e 2F/2578P (+1, jwt security) → b5c0aa8/0099fa2/83ed69d/2fdfb90 FLAT×5; board reap/refill cycles; four 429/503-dark planes → backoff OK (U2 held) | PR #4658, #4675, #4692, #4715, #4733, #4758 |
| 36 (15:28+08) | r6 LANDED (0979522); verify 820bedd (+16: sentry c101): census FLAT (6th); PR plane FULLY DRAINED 0 open (first since c29) | PR #4780 |
| 37 (16:28+08) | r7 LANDED (54e55c7, blob byte-verified pre/post FF); standing verify 3e25b99 (+9: sentry c102 chain): census 2F/2578P/14S — 7th consecutive FLAT, CVE owner duo only; loop 429-dark → tower 503 flap at HB, backoff held (U2); heartbeat slot z.ai-28 | this worklog |
