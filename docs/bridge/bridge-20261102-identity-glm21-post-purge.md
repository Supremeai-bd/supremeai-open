# GLM Agent 21 — Worklog (post-purge restart, Job ID 486808)

> Continuation of `worklog-glm21.md` (slot chain r1→r10, 12 landed PRs:
> receipts #3183 d0a70ab / #3234 eb50ee5 + worklogs #4086 29ddddd,
> #4220 ce4219c, #4239 3183ad9, #4488 751d97c, #4518 26b4ca8, #4562 394e228,
> #4610 7efa206, #4672 102e8b9, #4750 f650441, #4947 6520534), which was
> removed from the repo by the founder docs purge (#4965 Batch 1/5;
> #4966–#4969 Batches 2–5, all refs #762). All evidence stays in git history
> (git log --grep 486808). This file restarts the slot receipt at minimum
> size — in-place replace + fail-closed baseSha CAS from r12 onward.

## Durable slot facts (compressed)
- 14 cycles observed, 14 verified no-pick holds; zero claims held, zero
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
  root-caused (core.fileMode=false); brand-new paths must OMIT baseSha
  entirely (tower schema: "Omit only for brand-new files" — empty string or
  HEAD sha both rejected); #762 lean mandate pruned ops scripts too — the
  python hooks activator is gone (#4987), loop probe now git-native
  (`git config core.hooksPath .githooks`).

## Post-purge landings
- r11 → #5004 **merged** (432a44e): post-purge restart anchor, new-file
  submit with baseSha omitted; mirror WO #5003 opened by the bridge.
- r12 → #5039 **merged** (0463499): first in-place replace of this file,
  CAS resumed on the now-existing path; mirror WO #5038.
- r13 → #5060 **merged** (d658e27): CAS hold #15 receipt; first truncated
  board window observed (visible 20 of 21).
- r14 → #5081 **merged** (a2fcc80): CAS hold #16 receipt; second truncated
  window (refill ratchet 21→27).
- r15 → #5182 **merged** (a58e1c4): CAS hold #17 receipt; 5-cycle cron gap
  noted; refill burst fully drained (27→12).

## Current cycle (r16, 11:21+08 Nov 2) — first true pick in 17 cycles
- Loop dispatched **#5188** (P1, ci-failed, repo:monorepo) — first non-mirror
  pick since the purge. STALE-CLAIM GUARD caught label lag live: board said
  status:unclaimed but feedback plane showed **glm13 claimed 03:27:14Z** (TTL
  30m); #5191 claimed by contributor-agent 03:35:51Z. A lost race is never
  retried (Anti-Stampede; Invariant 8) — hands off both.
- Premise of #5188 re-verified TRUE on live main 0f7c005 (loop's own scan was
  429-dark): `scripts/bridge/bridge_intake.py:587` calls
  `gh_paged(..., max_pages=5)`; the helper raises "pagination cap reached"
  fail-honest at :207 — exactly the issue's evidence.
- Envelope census, the 5-row CI wave: unclaimed #5189/#5190/#5192 all have
  remedies OUTSIDE the agent envelope — #5189 targets monorepo
  `.github/workflows/ops-maintenance.yml` (absent in the open repo, which has
  only pipeline.yml) and `.github/` is a protected admin-review path;
  #5190/#5192 target satellite repos (studio `src/test/setup.ts`; supremeai-core
  SARIF) — open-repo `studio/` and `vscode/` are one-file stubs, and #5192's
  criterion 1 is a policy decision (Advanced Security enablement, HITL). Per
  the dispatch contract: evidence via bridge, NO auto-close, no Closes lines;
  closure stays with the verdict plane/admin.
- Board: totalOpen=23, truncated TRUE (visible 20 = 15 mirrors + the 5 CI
  rows). Ops: heartbeat first-try ok; reads absorbed several 429s (fleet burst
  on the new wave). No pick, no claim held; this receipt is the evidence.
