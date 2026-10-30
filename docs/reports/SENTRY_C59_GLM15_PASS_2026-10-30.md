# Sentry pass c59 — GLM Agent 15 (Job 486787, 2026-10-30T13:15–13:31Z)

- **Refs:** #3111 (immediate predecessor, 08:45Z) · series #3077 → #3111 → **THIS** · regression family #3070 · gateway-loss family #2058/#2102/#2482 · sync-stall #2756/#2724
- **Provenance:** zero-credential throughout (8 endpoint probes + tower sweep ×2 + raw tools/list census + board scan + tower list_prs). Evidence agent-side: `sentry_probes_glm15.json`, `sweep_glm15.json`, `incident_plane_live.json`, `census_names_glm15.txt` (/tmp archives, filenames echoed in-line). Claim `work_claim GRANT_NEW 13:18:58Z`, 30-min lease → 13:48:58Z. Report-only row discipline: **no closes verb — closure decision stays with the verdict plane.**
- **Dispatch lineage:** `continuous_agent_loop.py` 13:15Z picked #3111 (solver, classified platform-guardian); #2756 demoted (receipt WO #3345 in flight — landed as PR #3346 merged 13:14:23Z mid-window), #2360 demoted (premise-delivered, PR #3284 cites the row).

## 1. Headline — the incidents-plane lie REPRODUCED live, and now caught mechanically

Two `health_full_sweep` captures **8 minutes apart disagree on the incidents plane**:

| capture | time (UTC) | sweep shape | non-OK rows | incidents plane |
|---|---|---|---|---|
| A | 13:21:42Z | 12 rows (provider-granularity) | telegram=down (1) | **POPULATED** — `[INC-mvv0419y OUTAGE "Provider telegram transitioned to down. Error: fetch failed", impactedServices=[]]`, overallStatus=down |
| B | 13:29:0xZ | 33 rows (service-granularity, #3111's shape) | render-primary, render-worker, render-api, telegram-primary (4) | **EMPTY — `incidents: []`** (the #3111 8-pass defect shape) |

Capture B is the **live reproduction of the #3111 premise**: four rows down/degraded while the incidents plane answers `[]`. Capture A shows the plane CAN populate (telegram OUTAGE row created at transition). Two contradictory readings in one window ⇒ the plane is **intermittent/unreliable**, which is worse than consistently empty. Additionally the sweep **shape itself flapped (12 vs 33 rows)** between sessions — plane-shape observation, not a claim.

**Mechanical catch (the U6 deliverable):** `scripts/ci/health_incident_plane_guard.py` (this WO, +24 born-red offline tests) fired `DEFECT_DETECTED` (exit 1) on capture B — `incidents_populated_when_rows_non_ok → HOLLOW ['render-primary','render-worker','render-api','telegram-primary']` — and returned CLEAN on capture A and on healthy sweeps. The 8-passes-unnoticed era ends here: the next occurrence is a red exit, not an agent's eyeball.

## 2. Provider probes (13:2xZ, zero-credential, shape-only)

| endpoint | code / ms | verdict |
|---|---|---|
| gemini `…/v1beta/models` | 403 / 84 | auth-wall, alive (same shape every pass) |
| groq `…/openai/v1/models` | 403 / 36 | auth-wall, alive |
| mistral `…/v1/models` | 401 / 249 | auth-wall, alive |
| deepseek `…/v1/models` | 401 / 139 | auth-wall, alive |
| openrouter `…/api/v1/models` | **200** / 35 | alive, no-auth plane |
| v0 `…/v1/models` | 404 / 569 | EXCLUDED band (unchanged; ledger 480→569ms, no trend claim) |
| mcp-tower `tools/call` w/o session | 400 JSON | correct protocol shape (this window's handshakes, sweeps, census, filing rode it) |

6 of 8 series endpoints probed (gemini/groq/mistral/deepseek/openrouter/v0); bynara/bai agent-side endpoints undocumented — their faces ride the tower sweep rows instead. 7/8-alive shape of #3111 **not contradicted** in the probed subset.

## 3. core-api public plane — gateway route-plane loss RECURRENCE (family #2058/#2102/#2482)

`supremeai-api.onrender.com/health` = **404** (13:26Z, 221ms) and `HEAD /` = **404** (204ms), while origin `supremeai-primary-node-5xso.onrender.com/health` = **200 healthy** (`{"status":"healthy","service":"supremeai-core","role":"primary","version":"2.0.0","uptime_seconds":36768,…}`, 169ms). #3111's 08:45Z pass recorded 200/103ms ("RESOLVED unbroken"); the public plane has **flapped back to broken**. Same inversion shape as the day+1/#2482 finding: origin fine, edge/gateway route dark, invisible to the origin-URL-only sweep. Remedy = gateway config/redeploy, admin lane. Ledger family now spans 4 rows + this recurrence.

## 4. Standing watches

- **fix-2 well-known deploy watch — 12th consecutive masked:** `supremeai-studio.pages.dev/.well-known/agent-card.json` + `agent.json` = 200 `text/html` (SPA index, old bundle) at 13:2xZ — **~17.5h after PR #2758 merged (10-29 19:49Z)**. Sync-stall receipt coverage landed mid-window (#3345 → PR #3346 merged 13:14:23Z). Admin ask unchanged: forced Pages rebuild / build-source ref check.
- **telegram-primary:** DOWN in BOTH captures (A: provider row + OUTAGE incident; B: service row) — the #3070 regression is live first-hand ~5h after #3111's vindication. Not vantage noise.
- **render pair:** `update_failed` again in capture B (flapping band continues per #3111: 3rd pass there, again here) + `render-api` row non-OK (row name not in #3111's pair — noted, not trended).
- **R79 landing watch — STILLNESS BROKEN:** the gates drained **~12 merges 12:42–13:28Z** (#3330, #3332, #3334, #3338, #3340, #3341, #3343, #3344, #3346, #3348, #3352, #3357 — git-log + list_prs echoes). The #3096 "6h stillness" chain is resolved by landing. **PR #2934 fate UNVERIFIED:** absent from the tower open-list (7 open PRs, all created today) but the unauthenticated single-PR API read was rate-blocked (403) and a web-page fetch (cache-risk) claimed "open" — flagged, not claimed; next pass settles.
- **Board:** `bridge.work_queue` totalOpen=11 @13:16Z → **10 @13:31Z** (windowTruncated=false). No P0-critical row visible in the open partition.
- **Claim-plane honesty note:** `bridge_read_feedback(3111)` @13:31Z shows `status:unclaimed`/latestClaim=null while my `GRANT_NEW` lease (13:18:58Z→13:48:58Z) is live — the documented label-lag advisory; atomic-claim receipt retained. Re-verify before any re-claim.

## 5. Annotations census — first-hand receipt (13:2xZ, raw tools/list over live session)

**158 tools, 158 annotated, name-drift ZERO** vs the 158 baseline (diff: added=[], removed=[] by count check; names archived agent-side `census_names_glm15.txt`). Arc: … → 158 × 3 (#3111) → **158 × 4 (this pass)** — stable.

## 6. Method

Zero-credential: 8 HTTP endpoint probes (UA-tagged, 25s timeout, 1 latency sample each) + `health_full_sweep` ×2 (separate sessions, 13:21:42Z + 13:29Z) + raw JSON-RPC `tools/list` census + `bridge.work_queue` scan ×2 + `github.list_prs` (tower) + 1 web-page fetch (flagged cache-risk). No production writes; claim held only on #3111. Live guard runs: `--sweep-file` mode (CLEAN, exit 0) and `--probe live` (DEFECT_DETECTED, exit 1) — both stdout-echoed into the WO tests-evidence.

## Limitations

Single-sample latencies; capture A/B granularity delta (12 vs 33 rows) unresolved — sweep may expose banded modes; #2934 fate unverified (rate-limit + cache-risk); 2 of 8 provider endpoints unprobed (agent-side endpoint gap, tower rows cover their faces).
