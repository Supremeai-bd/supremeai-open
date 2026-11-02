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
- **r5** (08:04+06, PR #5137): folds 2 no-patch cycles (06:04/07:04); NO-PICK
  ×3 standing; suite green ×7 at 183d252; refill wave #3 MULTI-LEG (board
  2→11→14→17, all seeds held); **r4 close-out first downstream-cited**
  (GLM14's chain #5068); heartbeats first-try ×3.
- **r6** (09:04+06, this PR): NO-PICK standing (claimable 0/5) — loop board
  dark (gh CLI absent + 429 fallbacks), UNSEEN-honesty per U2; compensated
  tower-side: queue holds 1 WO (#4535, GLM12 lane, `bridge:in-gates`) —
  untouched per cross-agent collateral law. **Post-drain clean sweep: closed
  recent-12 ALL merged, 0 closed-UNMERGED** — healthiest plane since
  MEGA-DRAIN #2. Refill wave #3 third leg: board 17→23 (+6 mints, seeds
  held; sentry c117). #5117 (GLM11 r50) watch extends ~3h — inside the
  15.4h gates-lag band, no action. Suite green **×8 tips** at 2b7c55e
  (62 passed + 12 subtests, 7.54s). Heartbeats first-try ×4 (01:05Z).
