# #3441 (P0-critical) — core satellite CI: sync silently muted → stale root + stale shadow → pytest collection dead

- **Agent**: GLM Agent 28 (Job ID: 486832) — loop dispatch `cron-agent-loop-202610302228`, role solver/ci-fixer, claimed 2026-10-30T14:47:01Z (atomic `work_claim`, TTL 30m).
- **Row**: #3441 `fix(ci): [core] ci failed on main (Run #41072422845)` — repo:core, P0-critical.
- **Dispatch pick #3400 note**: first pick (#3400, landing-race mirror) was atomically claimed+closed by another agent at 14:32:34Z while this agent was mid-premise-verify; per the STALE-CLAIM GUARD the row was released without retry. The landing-race class evidence gathered there (post-remedy PR-lane failure 41072009314: `--admin` leg dead on stale base, `--auto` leg dead on `GraphQL: Auto merge is not allowed for this repository (enablePullRequestAutoMerge)`) is already covered by WO #3440 / the U3 receipt #3430 and is intentionally not duplicated here.

## 1. Live-verified evidence chain (all first-hand, zero-credential)

1. **Failing run**: `github.get_failed_logs(supremeai-core, 41072422845)` → job `🧪 Core Pytest & Lint` FAILED on push `4d33070a` ("fix(core): sync PR #2724 try/except guard to core/messaging/event_bus…"), created 14:32:19Z. Job window ≈22s (env dump 14:32:40.76 → cleanup 14:32:41.07) — a fast-fail, i.e. the collection/import class, not a slow test red.
2. **Three consecutive nightly reds**: core repo `ci` schedule runs failed 2026-10-28 07:58Z (`419a8388`), 10-29 08:06Z (`feda45e4`), 10-30 08:09Z (`32dccbb3`) — including a commit that was **green** on its landing day (Oct 26 20:33Z success on the same `419a8388`) ⇒ environment-independent, content-dependent breakage that only moved when content moved.
3. **Satellite split-brain verified via contents API** (Supremeai-bd/supremeai-core @ main):
   - `core/dag_planner.py` → **404 (absent)**; `core/monitoring/logging_config.py` → **404 (absent)**; `core/decision_engine.py` → present but **outdated** (7829B).
   - Canonical fresh mirror lives flat at the satellite ROOT (last sync push Oct 27 16:53Z, `832b27e6`); the nested `core/` copy is a stale, incomplete **self-shadow** — the #1676 class, core-domain instance.
   - `core/messaging/event_bus.py` (shadow) is byte-identical to open-repo `core/messaging/event_bus.py` @ HEAD — today's stranded-intake carrier landing `4d33070a` ported PR #2724's guard **into the shadow path**, i.e. even the operator tooling is confused about which surface is canonical.
4. **Local reproduction (exact live chain)**: reconstructed the satellite layout (flat root mirror + partial shadow) and ran the satellite's own `tests/test_core_planner.py`:
   - broken state → `ModuleNotFoundError: No module named 'core.monitoring'` → except-fallback → `No module named 'core.context_synthesizer'` → **1 collection error in 0.13s** (matches the 22s CI job);
   - fresh `core/` package copy → **11/11 passed in 0.26s**.
5. **The sync-miss root cause**: open-repo landing `54eda2f` (2026-10-30T11:47:08Z) touched `core/` with **1614 files / +354,939 lines**, yet the core satellite received **no sync push** between Oct 27 16:53Z and today 14:32:19Z, and **no `federation_ci_failed` dispatch fired** in that window (the only dispatches: 14:31:08Z, 14:32:44Z) ⇒ the satellite-sync job exited **green** while dropping the landing. The muting points, verbatim in `scripts/ci/federation_satellite_sync.py`:
   - clone failure: `⚠️ [GRACEFUL-DEGRADATION] … Skipping.` → `return True`
   - push failure: `⚠️ [GRACEFUL-DEGRADATION] Push … skipped due to permissions` → `return True`
   A permission-class failure on a target whose domain just changed is a **federation drift event**, not a graceful skip.
6. **#1676 overreach found in my own landed guard** (c99d8f5, 12:37:58Z): the generalized `prune_domain_self_shadows` would **delete** `supremeai-core:/core/` on the next core sync — but that nested copy is the satellite's only `core.*` import surface; deleting it converts the collection error into an even harder `ModuleNotFoundError`. The studio precedent (delete) does not generalize to a satellite whose own CI imports the package. Amended here with an explicit per-target policy.

## 2. The fix (3 layers, all inside this open repo)

1. **Fail-loud sync** (`scripts/ci/federation_satellite_sync.py`): permission-class clone/push failures now `return False` (red sync job) with a `::error::` annotation carrying the remedy; graceful degradation survives ONLY for repos in the new `SATELLITE_CLOAK_ALLOWLIST` (fail-closed default: empty; populate only via a documented cloaking receipt).
2. **Package-shadow refresh** (`PACKAGE_SHADOW_REFRESH_TARGETS = {"Supremeai-bd/supremeai-core"}`): for package-surface satellites the nested `<domain>/` copy is **refreshed from the mirror with prune=True on every sync** (`refresh_domain_package()`) instead of deleted — a sync-managed byte-exact copy can never drift, satisfying both the #1676 anti-split-brain goal and the satellite's import contract. The #1676 start-gate (mirror carrying top-level `<domain>/` ⇒ RuntimeError) applies under both policies.
3. **Contract tests** (`tests/test_federation_satellite_sync.py`, +7): refresh policy spares the shadow; refresh builds a fresh pruned copy (stale-only files removed); start-gate fatal under both policies; policy/allowlist targets must be federation members; allowlist default empty; permission-denied push → `False`; allow-listed push → `True`.

## 3. Test evidence (3-tier)

- Tier-1 (reflection): this receipt; the #1676-overreach admission is the load-bearing part.
- Tier-2 (live smoke): reproduction matrix in §1.4 (broken 0.13s error / fresh 11/11 pass); sentinel-adjacent checks via tower contents API in §1.3. Admin can validate end-to-end immediately by dispatching the pipeline with `force_satellite_sync=true` and watching the next core push carry `📦 [#3441] Refreshed sync-managed package copy 'core/'`.
- Tier-3 (tests): `tests/test_federation_satellite_sync.py` **18/18 PASS** (11 pre-existing + 7 new) on dual-rebased origin/main (0 behind, f616ced-family head); `continuous_agent_loop.py --verify-only` **8/8 PASS**.

## 4. Closure predicate (why closesOriginalIssue=false)

This landing mutes the muting, but the core satellite's CI turns green only when the **next core-touching main push** triggers a core sync that (a) is not permission-denied (if it is, the sync job now fails loudly instead of silently dropping) and (b) delivers the fresh `core/` package copy. That predicate lands after this WO merges, so the row stays open for the verdict plane.

## 5. Recommended follow-ups (not bundled, scope discipline)

- Add the `Trigger Federation CI Watchdog on Failure` dispatch step to the `satellite-dispatch-and-sync` job in `.github/workflows/pipeline.yml` (the only pipeline job without one) so a now-loud sync failure auto-creates an incident row. Currently a red sync job is visible only as a red main run.
- Admin: decide the `enablePullRequestAutoMerge` repo setting (the #3418 `--auto` leg is structurally dead — see WO #3440 evidence) and the stranded pre-remedy arcs.

## 6. Rollback

`git revert` the patch commit: one sync-script commit + one tests commit + this receipt; no runtime state depends on the new constants (allowlist is empty; refresh targets ⊆ DOMAIN_MAP asserted in self-test).
