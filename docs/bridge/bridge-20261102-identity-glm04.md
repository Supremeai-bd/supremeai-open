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
  path — 12-cycle chain folded into the durable facts above. Mid-purge
  census: 19 collection errors (`gateway.config` ×10 dominant), suite
  uncertifiable.
- **r2** (02:04+06, trace ...202611020204): NO-PICK standing-verify
  (claimable 0/5). **CENSUS RESOLVED** — the owner resolved the
  restore-vs-prune fork by pruning BOTH sides: #4984 (717-file mega
  purge of core/gateway/skills) + #4988 (361 legacy-test prune) + #4995
  (repo cleaned to 58 lean SSOT files) removed the missing modules and
  the orphaned tests together. Fresh tip (1798735): 5 test files / 62
  tests, **62 passed + 12 subtests in 7.67s, zero collection errors** —
  first clean full-suite certification of the new era. Collateral
  repairs observed: #4990 (freshness suite restored fail-closed after
  #4976 collateral delete), #5016 (tower-429 test re-land — its subject
  was live, not legacy). Hooks: python activator pruned by #4987 →
  git-native `git config core.hooksPath .githooks` applied locally (loop
  probe satisfied). Board 23→11 rows (SWEEP #3 @15:51:30Z; refill-era
  w2 6→10 per sentry c112). PR plane: #4872 lone open (status UNSEEN).
  Heartbeat first-try OK (agent-3, 18:04Z).
