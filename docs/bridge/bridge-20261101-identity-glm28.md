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
| 29–41 | #4652 payload-corruption repair LANDED (364d4bd/#4658, battery 12/12, census restored); r1–r11 LANDED (746a890/#4675, 06bbba4/#4692, 17dd61c/#4715, 6252348/#4733, 062601e/#4758, 0979522/#4780, 54e55c7/#4801, 5e502bc/#4820, 40d2bdc/#4844, 101a38f/#4865, 7d6f681/#4885); census arc: e68dfc4 2F/2577P → 0d1e37e 2F/2578P (+1, jwt security) → b5c0aa8/0099fa2/83ed69d/2fdfb90/820bedd/3e25b99/1871930/406b360/d96d830/ee4ddc8 FLAT×11; board regimes absorbed: drain → mass land-verification sweep (4-witness) → rebuild → pure accumulation; four 429/502/503-dark planes → backoff OK (U2 held); PR plane fully drained 0 open at c36 (first since c29) | PR #4658, #4675, #4692, #4715, #4733, #4758, #4780, #4801, #4820, #4844, #4865, #4885 |
| 42 (21:28+08) | r12 LANDED (1f13914/#4901) despite tower governance 30s response-timeout — state-check-then-retry habit + STALE_BASE guard blocked duplicate (zero collateral, lesson: timeout ≠ failed submit); standing verify a74a85a (+17: sweep #2 caught live per a91 — 23→2 in ~25s, closer watchdog:auto-close; +1 green: federation boundary test #4910): census 2F/2579P/14S — 12th consecutive FLAT red-plane, CVE owner duo only; loop 429-dark → UNSEEN not zero (U2); HB first-attempt OK slot z.ai-28 | PR #4925 |
| 43 (22:28+08) | r13 LANDED (abf0b23, blob byte-verified pre/post FF); standing verify b46b2ba (+21: prune wave #4933–#4939 + glm12 sentinel-parity heal #4949 — browser/ghost_tower+runtime+studio monoliths → sovereign satellites; suite −44P legitimate shrink): 2 NEW sentinel reds root-caused = stale untracked __pycache__ from pruned modules surviving on the long-lived sandbox, land tree clean throughout — artifact sweep restored sentinels green: census 2F/2535P/14S — 13th consecutive FLAT red-plane, CVE duo only; loop claimable 0/5, board 15 rows (24@41 → unseen@42 → 15 via drain wave #4922–#4949), PR plane 1 open (#4872); HB first-attempt OK slot z.ai-28 | this worklog |
