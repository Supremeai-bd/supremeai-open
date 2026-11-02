# GLM Agent 04 (Job 486718) — bridge worklog (post-purge era)

> Founder purge wave #4965-#4969 (Batches 1-5) removed the predecessor
> 12-cycle chain (`docs/bridge/bridge-20261031-identity-glm04.md`, r1-r12,
> last landed PR #4828). Accepted as owner-side hygiene — no restoration.
> Slot restarts at minimum size at a fresh dated path (glm19/glm22/glm32
> precedent; same-path resubmission = silent purge revert, rejected).
> Identity: heartbeat slot `agent-3` (TTL 300s, refreshed each cycle),
> hourly cron trace class `...-cron-agent-loop-*`, zero-credential surface.

## Durable facts (folded from the purged 12-cycle chain)

1. **Flagship root-fix — Tower-tool drift (R66)**: `github_list_prs` with
   repo omitted silently defaults to `Supremeai-bd/supremeai` (NOT
   `supremeai-open`); camelCase `perPage` is silently dropped (default 5).
   Live re-hit 15:04Z. Law: explicit `repo:"Supremeai-bd/supremeai-open"`
   + snake_case `per_page` always; parse both response shapes (`list` vs
   dict-with-`prs` key).
2. **Dispatch-probe classification (r12 FIRST-CENSUS)**: the lone red on
   the main-branch CI filter can be maintainer own-probe traffic:
   `repository_dispatch` + actor `paykaribazaronline` + title
   `federation_ci_failed` + ~11s duration + green push-run on same SHA =
   probe lane, NOT main regression. 3/3 probes evidenced (09:52Z,
   09:54Z, 13:03Z).
3. **Transport discipline**: `bridge_submit_patch` content-mode full_file
   for brand-new paths; unified_diff (diff-header cut) + CAS `baseSha`
   (`git rev-parse origin/main:<path>`) for existing paths; summary ≤1000
   asserted first; branch `bridge/<slug>` — slash mandatory (r11 reject);
   targetRepo echo-verified on response.
4. **Landing protocol**: sleep 180s → `github_list_prs state=closed`
   mergedAt → `git fetch` → `git show origin/main:<path>` → fixed-string
   `rg -qF` multi-string verify. Never a list-mode snake_case merged probe
   (false-null, Refs #3523).
5. **no-patch law**: info-value < churn-risk → no patch, fold the finding
   into the next receipt; brownout retry 4 attempts × 35-40s
   (502/503/429 in cron windows is normal weather).
6. **Fleet lore**: "4-quiet → SWEEP" (c104 44→4; c106 SWEEP #2 23→2 in
   ~25s); gates-lag up to 15.4h documented on a sentry receipt.

## Cycle ledger (keep-small: older cycles fold to one-liners)

- **r1** (00:04+06, PR #4993): post-purge restart; mid-purge census 19 errors.
- **r2** (02:04+06, PR #5032): census RESOLVED (owner prune, 58-lean-SSOT).
- **r3** (04:04+06, PR #5071): suite ×3; workflow_runs: no branch param,
  per_page>12 → -32602 (window 12).
- **r4** (05:04+06, PR #5090): #4872 watch RESOLVED (closed-UNMERGED);
  MEGA-DRAIN #2 27→2; suite ×4.
- **r5** (08:04+06, PR #5137): folds 2 no-patch cycles; suite ×7; refill
  wave #3 MULTI-LEG; r4 close-out downstream-cited.
- **r6** (09:04+06, PR #5155): NO-PICK; closed recent-12 ALL merged; suite ×8.
- **r7** (10:04+06, PR #5175): LOOP CERTIFICATION UPGRADE — preflight
  positively certifies zero open P0 (board revived via tower fallback);
  MEGA-DRAIN #3 23→2 @01:15:40Z witness-pinned — drain model ×3-evidenced;
  queue 10 WOs = receipt-echoes; suite ×9; heartbeat ×5.
- **r8** (11:04+06, PR #5203): FIRST real loop dispatch — #1304 [33 stale
  queued runs in `supremeai`]; all 33 orphaned (deleted-workflow orphans ×13
  + bridge-intake concurrency-v5 stall ×20); evidence PR #5201 MERGED, no
  Closes (cancel = operator); claim GRANT_NEW→RELEASED; suite ×10.
- **r9** (12:04+06, this PR): SECOND real dispatch — **#5190** [P2 studio:
  jsdom scrollIntoView gap]; guards walked (premise LIVE-verified: latest
  main run 41309314254 still failure, no newer run; latestClaim None;
  GRANT_NEW). Both files read live: setup.ts (2002 B) lacks the stub,
  call site SplitStudioView.tsx:98 is a legit production effect → purely a
  jsdom gap. Delivered **copy-paste-grade +5-line patch proposal**
  (`Element.prototype.scrollIntoView = vi.fn()`, matches file idiom, no
  test skipped) + recurrence-class note in evidence → **PR #5224 MERGED**
  (issue #5223, 9/10 git-verify, no Closes — satellite repo outside
  envelope, a99/#5191 precedent honored). Claim RELEASED. Fleet: other
  lanes now working real WOs too (a99 first-real-work #5222 landed; GLM22
  #5214 open on #5188). Durable: suite grew 62→**67 passed** (+12 subtests,
  7.87s) — **×11 green tips** at c75b1cb; heartbeats first-try ×7 (04:04Z).
