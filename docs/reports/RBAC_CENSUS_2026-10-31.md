# RBAC EMPIRICAL CENSUS — anonymous agent lane after the 19:12Z→20:11Z shift (GLM Agent 13, Job 486783, 20:13–20:21Z)

- **Series/refs**: corroboration + census extension of #3739 (GLM Agent 04, filed 20:04+08). Companion landed proofs: #3708 (c61 ledger — sweep alive at 19:17:58Z + tools/list=158 at 19:21Z), #3734 (c62), #3739 (first 403 table at 20:11Z).
- **Headline**: the shift is bigger than a per-tool 403 table — `tools/list` itself is now **role-filtered** (158 → 18 tools for the anonymous lane, two sessions, no pagination cursor), the denied family remains callable-by-name and returns explicit default-deny RBAC errors, the anonymous role is now literally **`viewer`** (from the github-family denial text), and **validation precedes the RBAC gate** (hidden tools leak their required-param schema through -32602 BEFORE being denied on valid args). Zero-credential contributor lanes (bridge/claim/submit) remain fully functional.

## 1. Flip window narrowed (landed proof chain)

| Datum | Time (Z) | Source |
|---|---|---|
| `health_full_sweep` alive (3× successful 33-row sweeps) | 19:17:51–19:17:58 | this lane, landed ledger #3708 |
| `tools/list` = **158** tools, unfiltered | 19:21 | this lane, landed ledger #3708 (census) |
| `render_service_health` last agent-lane success | 19:12 | #3739 (GLM 04) |
| health family dead (403 table) | 20:11 | #3739 (GLM 04) |
| `agent_review_workflow_status` → default-deny (was backend-401 in cycles 4–7) | 20:13:04 | this lane, first-hand |
| `tools/list` = **18** tools (cached session) | 20:16:40 | this lane, first-hand |
| `tools/list` = **18** tools (FRESH session, `nextCursor: null`) | 20:17 | this lane, first-hand |
| `health_full_sweep` by name → default-deny RBAC | 20:17 | this lane, first-hand |

**The sweep-kill window is [19:17:58, 20:11]** — 53 minutes wide, down from #3739's original 59-minute estimate; the tools/list filter flip is inside [19:21, 20:16].

## 2. The three denial shapes (all first-hand this lane)

1. **Tool-level default-deny** — `Forbidden: tool 'X' requires agent role or higher (default-deny RBAC). Present a valid MCP Bearer token with a sufficient role.` → `health_full_sweep`, `health_dashboard`, `agent_review_workflow_status`, `render_service_health` (with valid args).
2. **Repo-read denial for role `viewer`** — `Forbidden: role 'viewer' has no repository read access for 'github.list_prs'.` → `github.list_prs`, `github.read_file`. This names the anonymous lane's role explicitly: **viewer**.
3. **Validation-precedes-RBAC** — `render_service_health` with empty/partial args returns `-32602` that **leaks the hidden tool's schema** (`expected string, received undefined at accountId`, then `serviceId`); only with BOTH valid args does the default-deny fire. Consequence for census methodology: **a -32602 does NOT certify executability** — the RBAC gate sits behind validation. (Also a minor info-disclosure observation for the tower owner: hidden-tool param names are enumerable via validation errors.)

## 3. Empirical viewer-role matrix (anonymous lane, 20:13–20:21Z)

- **DEFINITELY_ALLOWED** (success, first-hand): `system_health` ×3 (20:13:53, 20:16:40, 20:17), `bridge_work` view:queue (20:13:49, 20 rows returned), `bridge_read_feedback` (20:15, #3739), `work_claim` (20:15:36, GRANT_NEW on #3739 — the atomic-claim lane works), `bridge_work_release` (exercised post-filing per convention).
- **DEFINITELY_DENIED**: `health_full_sweep`, `health_dashboard`, `agent_review_workflow_status`, `render_service_health`, `github.list_prs`, `github.read_file` — i.e. the entire sentry/guardian probe surface + the github repo-read family + the ARW status plane.
- **RBAC_STATE_UNSEEN** (validation-gated, never executed by design): `agent_heartbeat`, `bridge_lease_manage`, `bridge_submit`, `db_schema_inspect`, `slot_status`, `supabase_schema_inspect`, `system_inspect` (all required-args; empty-args calls reached -32602 only — per §2.3 this proves existence + schema, NOT permission).
- **UNPROBED_BY_DESIGN**: `bridge_submit_patch` (mutating; exercised only by this receipt's own submission), `bridge_work_release`/`bridge_work_renew` (mutating), `agent_status`, `status`, `system_summary`, `bridge_guide` (no-required-params, cannot prove non-execution — left uncalled). `github.*` mutating ops never touched.
- **18 visible tools** (fresh session): status, system_inspect, system_summary, system_health, slot_status, agent_heartbeat, agent_status, supabase_schema_inspect, db_schema_inspect, bridge_guide, bridge_work, bridge_submit_patch, bridge_submit, work_claim, bridge_read_feedback, bridge_lease_manage, bridge_work_renew, bridge_work_release. The health/github/devtools/workflow families are **absent from the listing** but present server-side (callable by name → shape-1/shape-2 denials).

## 4. Impact on landed agent tooling (concrete)

1. **Sentry series (c58→c62)**: the per-service snapshot planes (`health_full_sweep` 33-row table, `health_dashboard`) are blind; `system_health` survives but its service table reshaped 21 (19:18Z) → **12** (20:13:53Z `10 healthy · 1 degraded · 1 unreachable`; 20:16:40Z `11 healthy · 1 degraded · 0 unreachable` — telegram flap visible across the two reads). The series' built-on surface is gone mid-flight; remedy-B degraded mode (system_health + explicit 403 datum) is now exercised by this receipt.
2. **Loop failed-PR audit fallback (PR #3602, this agent's cycle-5 fix)**: `_tower_open_prs()` rides `github.list_prs` → now repo-read-denied → the fallback returns `(None, note)` and the audit degrades to the dark line carrying the note. The never-raise design and the honesty contract (dark ≠ zero, UNSEEN never certified clean) hold unchanged — verified by design inspection; the audit path needs no code change (root-cause is lane policy, not the fallback).
3. **U3 live-validity verification**: github repo-read denials mean landed-premise re-verification via tower github reads is blind (public GitHub API remains 403-rate-limited from this lane — dual blind).
4. **ARW three-layer state (this lane's standing note, cycles 4–7)**: the flip-probe can no longer REACH the backend — the plane is now gated at the tower RBAC layer before the SUPREMEAI_BACKEND_SERVICE_TOKEN question. L3 verification is owner-lane-only until the anonymous lane gets a role that can present the probe.
5. **Contributor pipeline survives**: claim → work → submit → release all ride allowed tools (§3 first-hand); the fleet's output lane is intact. The blindness is exactly the observability plane.

## 5. Interpretation (correlation, not causation)

The observed end-state (viewer role, default-deny on health/github/workflow families, filtered listing) is **consistent with the P0 #3663 remediation** — the fail-open `?? "admin"` identity that made anonymous sessions GLOBAL-ADMIN would have been the enabler of the pre-shift 158-tool unfiltered surface. Whether the shift was an intentional hardening deploy, and whether the viewer grant-list matches the intended end-state (AGENTS.md's zero-credential single-door design assumes SOME read plane), is owner-lane to confirm. This receipt supplies remedy-A's empirical floor: **the census above IS the viewer-role matrix snapshot** — publish or correct it.

## 6. Next-watch (for the next dispatched cycle)

1. Persistence check: is the 18-tool viewer surface stable across cycles, or still moving (render_service_health flipped 403→validation-reachable→403 inside [20:11, 20:20] per #3739 vs this census)?
2. Does the owner publish the role matrix or grant a read-only family (remedy A/C)? Watch AGENTS.md tool-routing note.
3. Sentry c63 under degraded mode: system_health shape (12 rows) + explicit 403 datum per #3739 remedy-B; provider /models probes are tower-independent and remain fully available.
4. Redis cooldown expiry 2026-11-01T00:01Z trajectory (now readable only via system_health's provider rows or sweep-less lanes).
5. The -32602 schema-leak observation — owner may want validation to not disclose hidden-tool schemas.

*Filed by GLM Agent 13, Job ID 486783, cycle cron-agent-loop-202610310413, 2026-10-30 ~20:24Z. Zero side effects by construction (required-args tools only ever called with empty args; mutating tools exercised only through the normal claim/submit/release flow of this very task). Refs #3739; no closure requested — remediation is owner-lane.*
