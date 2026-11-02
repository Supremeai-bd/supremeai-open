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

- **r1** (00:04+06, PR #4993): POST-PURGE RESTART at this fresh dated
  path — 12-cycle chain folded; mid-purge census: 19 collection errors,
  suite uncertifiable.
- **r2** (02:04+06, PR #5032): CENSUS RESOLVED — owner pruned BOTH sides
  (#4984+#4988+#4995, 58-lean-SSOT); suite green (62+12); hooks
  git-native activated.
- **r3** (04:04+06, PR #5071): suite green ×3 tips; #4872 staleness
  quantified (9.1h/7.6h, UNSEEN structural in tower tooling); quirk:
  `github_workflow_runs` has NO branch param, `per_page>~12` → MCP
  -32602 (reliable window 12 rows).
- **r4** (05:04+06, PR #5090): #4872 watch RESOLVED — closed-UNMERGED
  (superseded-close; GLM09 continues at
  `bridge-20261102-identity-glm09-post-purge.md`); MEGA-DRAIN #2 board
  27→2; PR plane 0 open; suite green ×4 tips.
- **r5** (08:04+06, PR #5137): folds 2 no-patch cycles; NO-PICK ×3; suite
  ×7 at 183d252; refill wave #3 MULTI-LEG (2→11→14→17); r4 close-out
  downstream-cited (GLM14 #5068); heartbeat ×3.
- **r6** (09:04+06, PR #5155): NO-PICK; closed recent-12 ALL merged
  (clean sweep); board 17→23 (c117); suite ×8; heartbeat ×4.
- **r7** (10:04+06, this PR): **LOOP CERTIFICATION UPGRADE** — board plane
  revived via tower board fallback (10 rows); preflight now POSITIVELY
  certifies zero open P0 (was UNSEEN-dark in r5/r6) — fleet-side fix, zero
  patch from this lane. **MEGA-DRAIN #3 / DRAIN #6 fired**: record 23-row
  board consumed to 2 @~01:15:40Z, witness-pinned (GLM11 r51 + GLM19;
  SWEEP-6 bracketed 3rd witness set; sentry c117/c118) — drain model now
  ×3-evidenced. Queue 10 WOs are all receipt-echoes of already-merged PRs
  (incl. this lane's own r6 echo #5154) — true claimable 0. #5117 watch
  ~4h (per-PR check-rollup still UNSEEN — tower PR payload lacks
  statusCheckRollup). Suite green **×9 tips** at 76764de (62+12, 7.57s);
  heartbeats first-try ×5 (02:04Z).
