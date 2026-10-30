# Bridge receipt — #3699 schema-contract guard repair (GLM Agent 10)

- **Agent:** GLM Agent 10 · Job 486755 · cycle 2026-10-31 03:10+08 · claim GRANT_NEW 19:13:19Z (TTL 30m)
- **Task:** solver dispatch #3699 (P1-high scout): post-sync primary container `supremeai-primary-node` (srv-dau7c9ek1f9s73almn0g) booted degraded-live with 4 residual error classes.

## U3 fresh live verification (probes 19:14–19:22Z)

The issue's premises were **accurate at filing time (16:20–19:10Z) and are now stale in three of four classes**:

1. **Secrets (BE-13) — unchanged, owner-lane.** `render_get_env_var_keys` (names only): `LLM_PROVIDER_KEYS`, `REDIS_SECONDARY_URL`, `UPSTASH_REDIS_REST_URL` still absent; Infisical client creds present, so the gap is inside the Infisical production environment itself. Boot at 16:25:42Z logged `Startup validation failed … continuing in degraded mode`.
2. **Upstash quota — mitigated by rotation.** `redis_rotation_status`: `autoRotateEnabled: true`, `activePrimary: tertiary` (1,554 / 500k, 0.31%); old primary+secondary crit-cooldown (480k / 500k, 96%) until the 2026-11-01T00:01Z monthly reset. `redis_ping` → PONG via tertiary, 45 ms. Quota guard alert exists (`scripts/ops/redis_quota_monitor.py`, #1839 wiring; `redis_quota_alert` telegram sent=true).
3. **Supabase TLS — not reproducing.** `render_get_logs` level=error, full window 16:20→19:14Z: **14 rows, all timestamped 16:24:52–16:25:46Z, zero after the 16:25:51Z deploy**. `supabase_health` → healthy, 133 ms. The SSL failure was a boot-window transient of the previous container state.
4. **Schema drift — structurally real, root-caused in-repo.** The boot errors (`public.exec_sql` missing, `usage_metrics.metric_date` missing, `permission denied for table ai_memory`) map to code dependencies with **no versioned definition** in the repo.

## Root cause (agent-lane leg, fixed here)

The permanent guardrail against exactly this drift class was **dead from birth**:

- `scripts/ci/check_database_schema.py` pointed its contract path at the pre-rename `backend/` tree (`REPO_ROOT/backend/database/contracts/…`). `backend/` does not exist (0 files), so every invocation exited 2 ("contract file not found") — the guard never guarded, silently.
- Even alive, the contract SSOT could not express the objects that drifted: no `ai_memory`, no `usage_metrics`, and **no functions/RPC section at all** (`exec_sql` is called at 5 sites — `scheduled_tasks.py:76`, `deep_research.py:126`, `branch_conversations.py:79+95`, `prompt_templates.py:281` — but no in-repo migration defines it; `ai_memory_phase_c.sql:209-210` carries the GRANTs prod never got).

## The fix (2 files, carrier-green, no born-red)

1. **`scripts/ci/check_database_schema.py`** — path now resolves against `core/` first with the legacy `backend/` kept as a named fail-closed candidate (a future rename breaks loudly, never silently); lazy DB imports so `--self-test` runs zero-dependency; diff logic refactored into a pure `diff_contract()` covering tables/columns/indexes/**functions** (`information_schema.routines`); built-in `--self-test` (5 checks) pins: ghost-path refusal, required-vs-optional routing, function-section semantics, empty-contract tolerance. Report line now prints visible-function count.
2. **`core/database/contracts/schema_contract.yaml`** — encodes the #3699 drift class: `ai_memory` (14 cols from phase-C DDL), `usage_metrics` (8 cols incl. `metric_date`), and a new top-level `functions:` section with `exec_sql`. All `required: false` with owner-lane notes + flip-to-true instructions — the check must not be born-red against live prod (#3544 lesson); flipping to `required: true` belongs to the same PR that lands the migrations.

## Owner-lane actions (outside the agent envelope)

**Corroboration:** GLM Agent 08's independent twin-row evidence (#3698, PR #3703, probe 19:03–19:14Z) concurs on every shared premise — TLS boot-clustered only, ai_memory 42501 GRANT gap persistent across boots, BE-13 live — and extends the secret census to **5 missing keys**: this receipt's 3 plus `UPSTASH_REDIS_REST_TOKEN` and `SUPABASE_DB_CA_CERT` (the TLS-class root cause). The schema-guard fix below is the complementary in-repo leg of the same incident.

1. Provision the 3 BE-13 secrets in the Infisical production environment and redeploy (LSE; agents never touch secret values).
2. Run on prod Supabase: `ai_memory_phase_c.sql` GRANTs (209-210) for the app role; add `usage_metrics.metric_date` + grants; version a locked-search-path, service_role-only `exec_sql` as a real migration. Then flip all three contract entries to `required: true`.
3. Wire `check_database_schema.py` into CI (`.github/` is a protected path — agents cannot edit workflows). Suggested: nightly + push, `DB_SCHEMA_CHECK_URL` read-only role, IPv4 pooler per the script's skip note.
4. Upstash: no plan upgrade needed while rotation holds; the crit-cooldown pair self-clears at the 11-01 reset.

## Reflection Evidence

- **why:** the issue's four classes looked like four production fires, but the live plane showed three were boot-window transients or already-mitigated by existing machinery — while the real root cause was hiding one level up: the guardrail built to catch schema drift had never once executed, because it pointed at a directory that does not exist, and its contract language could not name the very objects that drifted. Fixing the pointer and the expressiveness is the zero-recurrence move; re-reporting the four symptoms every cycle is not.
- **alternatives_rejected:** (a) writing the missing `exec_sql`/`metric_date` migrations myself — the live-prod application step is owner-lane and a versioned migration without prod execution would deepen the doc-vs-prod split rather than close it; the contract entries + notes hand the exact artifacts to that lane; (b) marking new contract entries `required: true` — born-red CI on main (#3544 class) that would mask future real drift; (c) `action_render_deploy` / secret handling — HITL envelope; (d) filing a new issue for the dead guard — it is the same root cause as #3699 class 3, fixed in the same slice instead.
