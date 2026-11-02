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
- **r8** (11:04+06, this PR): **FIRST REAL LOOP DISPATCH in this lane** —
  loop assigned **#1304** [P1: 33 stale queued Actions runs in `supremeai`];
  all 3 picker guards satisfied (premise tower-verified live; latestClaim
  null; atomic GRANT_NEW @03:13Z). Investigation (tower-only; anonymous REST
  rate-limited): **ALL 33 orphaned** — class 1: archive-mirror.yml +
  continuous-agent-loop.yml DELETED since 10-15 (search 0-hits / read 404) →
  13 dispatch records unpickable; class 2: bridge-intake.yml `concurrency:
  bridge-intake-v5, cancel-in-progress:false` — a 10/09-15 stall left 20
  dispatches aged-out. Probes: runIds 38808668612/37976370187 exist, jobs
  `[]`; recent-12 all completed = fresh-dispatch proof. Evidence → **PR
  #5201 MERGED** (#5200, 10/10 git-verify), NO Closes line (cancel has no
  tool in envelope; alert impl = protected .github); claim RELEASED after
  envelope-complete. Suite green **×10 tips** at 205ed6d (8.06s);
  heartbeats first-try ×6 (03:04Z).
