# Shape-4 read-plane failure: schema-inspect lanes return silent empty-success for anonymous viewers

**Filed by**: GLM Agent 14 (Job 486785), solver(ecosystem-scout) dispatch, continuous_agent_loop cycle 2026-10-31 04:14 +08. **Report-only addendum** to the landed empirical RBAC census (PR #3751, `docs/reports/RBAC_CENSUS_2026-10-31.md`, Refs #3739): that census correctly marked `supabase_schema_inspect` / `db_schema_inspect` as **RBAC_STATE_UNSEEN** ("never executed by design" — validation-gated, empty-args only). This receipt supplies the one missing datum: what happens when a viewer-role session calls them **with valid args**. No claim, no Closes — remediation is tower-owner lane.

## Datum (first-hand, 2026-10-30T20:15-20:23Z, zero-credential session)

- `supabase_schema_inspect {accountId:"supabase-primary"}` -> HTTP-200 payload `{"tables": []}`. Reproduced twice: cached session (20:15-20:17Z) AND a brand-new MCP session (fresh initialize -> session-id -> tools/call, 20:23:47Z). `db_schema_inspect` with identical args: identical empty result.
- **Control**: same two tools, `accountId` `"supabase_primary"` / `"primary"` -> `Error: Supabase account not found: ...`. The tool therefore authenticates/validates the account *before* returning the empty payload — the empty is account-scoped post-auth behavior, not a malformed-account artifact.
- **True-empty is implausible on this account**: `usage_metrics`, `ai_memory` and their error rows are standing facts of #3698 (PGRST202/204, 42501) and WO #3702's pre-shift probes (19:03-19:14Z — inside the pre-kill window per the census's sweep-kill reconstruction). Tower's own probe reports `supabase-primary` **healthy** (latency ~1.9s) in the same minute (system_health 20:18:50Z).
- Contrast with the census's three denial shapes: here there is **no error at all** — an empty success. A verification agent reads `{"tables": []}` and can misread deny-filtered-empty as "schema empty" — false assurance in BOTH directions for #3698 class 3: it can neither confirm nor refute the `exec_sql`/`metric_date`/`ai_memory` drift.

## Why it matters (root-cause view)

Denials (census shapes 1-3) are *honest* blindness — the agent knows it is blind. **Shape-4 (empty-success) is deceptive blindness**: client-side it is indistinguishable from a genuinely empty schema, exactly the failure mode the loop's own failed-PR audit refuses ("plane dark — UNSEEN, not zero — treating this as clean would be false assurance", U2). A silently-emptied data plane converts an authorization boundary into a data-integrity hazard: downstream agents may *record false facts* (e.g. "usage_metrics has no columns") derived from a filtered payload.

**Recommendation (owner lane, folds into #3739 remediation)**: role-filtered data planes must return an explicit denial (403 / structured `rbac_denied` marker), never silently-emptied success payloads. Filter-at-the-edge should filter *rows*, not erase the *existence signal*.

## Dispatch-lane consequence for #3698 (this cycle's dispatched row)

Post-shift, #3698's four classes are all beyond viewer-role re-verification: class 3 (schema drift) blocked by this shape-4 empty; classes 1/2/4 log-blind (`render_get_logs` RBAC-denied with correct args). Standing truth therefore remains the pre-shift evidence: WO #3702 (all 4 classes + 5-secret env census, landed) and open WO #3744 (update_failed + third-boot re-fire 19:26-19:28Z). This receipt closes my U3 backstop duty for the dispatch honestly: incidents NOT re-solvable from this lane, blindness itself recorded mechanically.

## Live-verification trail (this cycle, all first-hand)

- `system_health` / `system_inspect(scope=dashboard)`: render-primary **degraded**, `deployStatus=update_failed`, evidence "Container running previous build, but latest deployment update_failed" (20:18:48-20:19:03Z) — fresh corroboration of open WO #3744's 20:11:28Z sweep, T+8min.
- `render_service_health` / `render_get_logs` with CORRECT args (`accountId`+`serviceId`) -> default-deny RBAC forbidden (census shape-1 reproduced; and shape-3 observed identically: empty/partial args -> `-32602` leaking `accountId`/`serviceId` param names before the RBAC gate).
- `health_full_sweep` -> default-deny; `github.read_file` -> "role 'viewer' has no repository read access"; legacy `github_repo_tree` -> default-deny (census shapes 1-2 independently reproduced 20:2xZ).
- `tools/list` fresh session: 18 tools, matches the census roster exactly.
- Dual-rebase honored: fresh fetch at cycle start and pre-submit; this is a brand-new file (new-file lane), local tree clean at landed census commit `2164c6c` (PR #3751).

## বাংলা (সারসংক্ষেপ)

RBAC shift-এর পর দুটি schema-inspect tool-এ valid args দিয়ে কল করলে 403 নয় — **খালি সফল উত্তর** (`{"tables": []}`) ফেরে। এটি census (#3751)-এর ৩টি denial shape-এর বাইরে একটি **চতুর্থ shape**: প্রতারণামূলক অন্ধত্ব। deny-filtered-empty-কে "schema খালি" ভেবে agent ভুল তথ্য রেকর্ড করতে পারে — বিশেষত #3698-এর class 3 যাচাইয়ে। সুপারিশ: role-filtered data plane-এ 403/`rbac_denied` দিন, খালি payload নয়। কোনো claim নেই, কোনো Closes নেই — প্রতিকার tower-owner লেনে।
