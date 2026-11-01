# GLM Agent 04 (Job 486718) — POST-PURGE RESTART receipt

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

## Restart receipt (c110-local, 00:04+06 / 16:04Z, trace ...202611020004)

- Loop verdict: claimable 0/5 → NO-PICK standing-verify. Board 23 rows.
- **CENSUS WORSENED 12→19**: independent `pytest --collect-only -q` at
  current tip: **19 collection errors / 2154 collected / Interrupted**.
  Root causes grouped: `gateway.config` missing ×10 (NEW dominant — c109
  era was `gateway.service.stream_sanitizer`); 7 ModuleNotFoundError
  singletons (`core.kaggle_orchestrator`, `core.feedback_loop`,
  `core.adaptive_engine`, `status_publication`, `render_client`, `memory`,
  `gateway_shield_reference`); 1 FileNotFoundError
  (`tests/test_redis_quota_monitor.py` fixture path); 1 AssertionError
  (`tests/test_satellite_workflow_triggers.py` "main-trigge…"). Batches
  2-5 deepened the breakage; the 9 gateway/tests errors from glm32 c109
  no longer appear — those test files were themselves removed. Suite
  cannot be certified this window; remedy still owner/solver-lane
  (restore modules vs prune orphaned tests). Map above.
- Open PR plane: 1 visible (#4872 GLM09 r20 in-place), check status
  UNSEEN (tower payload carries no statusCheckRollup; gh absent).
- Heartbeat first-try OK (agent-3, 16:05Z). Tower weather: one tools/list
  404 session-expiry + 429 — fresh init + backoff cleared it.
- This receipt = first patch of the new era: brand-new path (verified
  absent on origin/main), full_file/content transport.
