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
- **r2** (02:04+06, PR #5032): CENSUS RESOLVED — owner pruned BOTH sides
  (#4984 717-file mega purge + #4988 361 legacy-test prune + #4995
  58-lean-SSOT); suite green at 1798735 (62 passed + 12 subtests, 0
  collection errors); hooks git-native `core.hooksPath .githooks`
  activated; board 23→11 (SWEEP #3 + refill w2).
- **r3** (04:04+06, trace ...202611020404; folds the two no-patch cycles
  03:04/04:04): NO-PICK ×3 standing (claimable 0/5 each window). Suite
  re-certified green at 5ee875a AND d09d0c2 (62+12, 7.4s / 7.6s) —
  stable across 3 consecutive tips. Board 11→18→23: two rising windows,
  no sweep (sentry c114's interval-model falsification independently
  consistent). **#4872 staleness quantified** (U2 defect-ownership):
  open 9.1h, silent 7.6h, single-PR mode confirms `merged:false`; no
  check-rollup even in single-PR mode; its branch runs aged out of the
  recent-12 window → the UNSEEN gap is STRUCTURAL in current tower
  tooling, not a probe error. GLM09's lane — untouched per cross-agent
  collateral law; watch continues. **Tower-quirk durable facts (new)**:
  `github_workflow_runs` schema carries NO branch param — filtering is
  client-side only, and `per_page>~12` returns `MCP error -32602:
  Output validation error` (reliable window = 12 rows; bigger pages are
  an error, not a truncation). Heartbeats first-try ×3 (18:04Z, 19:04Z,
  20:04Z); zero brownouts this window.
