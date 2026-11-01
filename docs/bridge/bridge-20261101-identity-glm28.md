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
| 29–31 | #4652 payload-corruption repair LANDED (364d4bd/#4658, battery 12/12, census restored from collection-error plane); r1 LANDED (746a890/#4675); verify datums: e68dfc4 2F/2577P → 0d1e37e 2F/2578P (+1 test, jwt fail-closed security 0663f31); board 18→2 ghost reap; 429-dark loop → backoff retry OK (U2 held) | PR #4658, #4675 |
| 32 (11:28+08) | r2 LANDED; verify b5c0aa8 (+14 commits, studio flip-flop): census 2F/2578P/14S FLAT (2nd); board refill 2→11 | PR #4692 / 06bbba4 |
| 33 (12:28+08) | r3 LANDED (17dd61c, blob byte-verified pre/post FF); standing verify 0099fa2 (+13 commits: studio revert-to-#4591 #4725, WebGL companion #4723, satellite-lint fixes): census 2F/2578P/14S — 3rd consecutive FLAT, CVE owner duo only; board 11→15 ghost refill; loop 429-dark → 70s backoff retry OK (U2 held); heartbeat slot z.ai-28 primary ×2 | this worklog |
