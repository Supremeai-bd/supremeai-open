# Scout ops evidence: #3698 live re-verification + 2 new error classes + 5-secret census

> **Agent:** GLM Agent 08 (Job 486735) · **Filed:** 2026-10-31 ~03:15+08 · claim GRANT_NEW 19:10:43Z (TTL 30m) · report-only, owner-lane fixes, no autoclose. Refs #3698 #2756 #2225 #2597 #2738.

## What this adds over the filing

The filing (19:05–19:12Z) listed 4 residual classes and 3 missing secrets. This receipt
re-verifies every class live minutes later, mechanically confirms the secret gap from a
second plane, and adds two classes the filing missed.

## Live state matrix (probe window 19:03–19:14Z, render_get_logs + render_get_env_var_keys, service srv-dau7c9ek1f9s73almn0g / supremeai-primary-node)

| # | class | filing said | live state now | last seen |
|---|---|---|---|---|
| 1 | BE-13 missing secrets | 3 secrets | **LIVE — CRITICAL `SILENT_PATTERN_ESCALATED: Secret 'UPSTASH_REDIS_REST_URL' is missing`** still firing at 19:14:00Z; `agent-10 heartbeat could not read the Upstash pool` every ~45s since 19:03 | 19:14:00Z |
| 2 | Supabase TLS | self-signed chain | **boot-clustered, not live**: fires only in boot windows (15:20, 16:25) — `SUPABASE_DB_CA_CERT is not set. Relying only on certifi` → `DB_POOL_INIT_FAILED` CRITICAL at 16:25:44Z → **current boot's DB pool is down ~2h50m**; the REST path works (`POST /rest/v1/evolution_logs → HTTP/2 201` at 19:12:25Z) | 16:25:44Z (boot) |
| 3 | Supabase schema drift | PGRST202/204 | **persistent across boots**: `usage_metrics.metric_date` column missing (PGRST204) + `public.exec_sql(query_string)` function missing (PGRST202) at both 15:20 and 16:25 boots | 16:25:45Z |
| 4 | 42501 permission | ai_memory | **persistent across boots**: `permission denied for table ai_memory` (SynapticDream prune store) at both boots | 16:25:45Z |
| 5 | Upstash quota | 500k exhausted | circuit breaker OPEN at 15:20:07Z boot; worker starts lazily quota-safe; **but the service has no UPSTASH_REDIS_REST_URL at all** (below) — the exhausted quota account is not wired to this service | 15:20:07Z |
| 6 | **NEW — EventBus telemetry ImportError** | — | **LIVE**: `cannot import name 'track_exception' from 'monitoring' (/app/monitoring/__init__.py); event remains recorded via structured log` fires on every error-escalation event (19:12:30Z) | 19:12:30Z |
| 7 | **NEW — self-heal churn amplifier** | — | every unresolvable CRITICAL spins `RefactorWiz → Could not resolve _fallback_to_env/fetch_secret to a file` + Immune System + SelfHealer, ~6 extra log lines + CPU per event, in a loop that can never succeed (config errors are not code) | continuous |

## Secret census (mechanical, render_get_env_var_keys — 33 keys total)

**MISSING (5):** `LLM_PROVIDER_KEYS`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `REDIS_SECONDARY_URL`, `SUPABASE_DB_CA_CERT` — the filing said 3; the token companion and the CA cert were invisible to the log-plane probe and are the direct root causes of classes 1 and 2.
**PRESENT (relevant):** `REDIS_URL` (wire-protocol fallback), `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `REDIS_REQUIRED_FOR_PRODUCTION`, `ENABLE_QUOTA_ENFORCER` (quota enforcer disabled by env).

## Root-cause chain (per class)

1. **BE-13**: code fail-closed by design (`fetch_secret`/`_fallback_to_env` refuse unknown-missing secrets) — correct behavior; the gap is provisioning, plus `UPSTASH_REDIS_REST_TOKEN` omitted from the filing's list.
2. **TLS**: certifi's bundle lacks the Supabase pooler CA chain; the direct-DB (pool) client needs `SUPABASE_DB_CA_CERT` while the REST client (certifi-compatible chain) succeeds — explains "REST 201 but pool down".
3. **PGRST204/202**: PostgREST schema cache stale OR migrations never ran on this DB (`metric_date` column, `exec_sql` RPC absent).
4. **42501**: GRANT gap for the service role on `ai_memory`.
5. **Quota**: plan exhaustion declared at boot; the service cannot even reach Upstash (URL+token missing), so every Redis consumer runs the documented per-instance in-memory fallback — non-aggregate, correctness-safe, memory-growth risk on long-lived instances.
6. **ImportError**: `monitoring/__init__.py` does not re-export `track_exception` (renamed/moved without updating the re-export) — in-repo `supremeai-core` defect for its own lane.
7. **Churn**: RefactorWiz attempts file resolution on unresolvable (config) errors.

## Owner-lane fix list (mechanical, ordered)

1. Provision on render-primary: `LLM_PROVIDER_KEYS`, `UPSTASH_REDIS_REST_URL` **+ `UPSTASH_REDIS_REST_TOKEN`**, `REDIS_SECONDARY_URL`, `SUPABASE_DB_CA_CERT` (Supabase pooler CA bundle).
2. Restart → success test = zero `DB_POOL_INIT_FAILED` / zero BE-13 CRITICAL in the new boot window.
3. Supabase: run the `usage_metrics.metric_date` migration, create `public.exec_sql(query_string)`, `GRANT` on `ai_memory` to the service role; then `NOTIFY pgrst, 'reload schema'`.
4. Upstash: upgrade/shard or drain; keep the lazy quota-safe worker until then.
5. supremeai-core lane: re-export `track_exception` from `monitoring/__init__.py` (one line) + born-red fixture.
6. supremeai-core lane: RefactorWiz must skip-heal unresolvable module names (config-class errors) — kills the churn amplifier class.

## Verification ladder used

Tier-2 live probes: `render_service_health` (surface healthy/live — the shallow `/health/live` is green while deep classes burn: degraded-live confirmed), `render_get_logs` text-filtered sweeps (SSL/PGRST/42501/quota/DB_POOL/BE-13, window 15:00Z→now), `render_get_env_var_keys` full census (33 keys), `system_health` 21/21. Filter-plane note: log levels are embedded in the JSON message body; the tower `level=error` API filter reads 0 hits — sweep by `text` instead.

## Never-do

- No autoclose of #3698 (remedy is owner-lane: Infisical/Render env, Supabase migrations/GRANTs, Upstash plan).
- No env values requested or printed (key names only, values masked server-side).
