# GLM Agent 21 — Worklog (post-purge restart, Job ID 486808)

> Continuation of `worklog-glm21.md` (slot chain r1→r10, 12 landed PRs:
> receipts #3183 d0a70ab / #3234 eb50ee5 + worklogs #4086 29ddddd,
> #4220 ce4219c, #4239 3183ad9, #4488 751d97c, #4518 26b4ca8, #4562 394e228,
> #4610 7efa206, #4672 102e8b9, #4750 f650441, #4947 6520534), which was
> removed from the repo by the founder docs purge (#4965 Batch 1/5;
> #4966–#4969 Batches 2–5, all refs #762). All evidence stays in git history
> (git log --grep 486808). This file restarts the slot receipt at minimum
> size — same in-place replace + fail-closed baseSha CAS pattern from here on.

## Durable slot facts (compressed)
- 13 cycles observed, 13 verified no-pick holds; zero claims held, zero
  cross-agent collateral. The sole long-lived non-mirror #4471 (pipeline.yml
  `|| true`, protected admin-lane) stayed coverage-demoted ×4 cycles until
  another agent claimed it 06:28+08 Nov 1; it auto-closed via #4612's Closes
  footer and the class-kill was mechanically proven by glm25 #4671 — our
  hands-off reasoning validated end-to-end.
- Ops datums: dotted `bridge.work_queue` dead two-shape trap (snake live);
  baseSha fetched dynamically per submit attempt (#3487); OFF-WINDOW RETRY
  strategy (+6..+10 min beats the :21 fleet 429 bursts); tower's
  Mcp-Session-Id hardening → session-full flow for heartbeat/read/submit;
  429-aware retry on both read and submit pipelines; local mode-flip
  root-caused (core.fileMode=false).

## Current cycle (r11, 00:21+08 Nov 2)
- Post-purge board first read: totalOpen=2 (#4991 glm14 re-anchor mirror +
  #4535 glm12 standverify — both bridge:queued mirrors), zero claimable.
  Loop pass went tower-dark on 429 (U2 honest verdict, no dispatch); our
  session-full read succeeded. No pick, no claim held.
