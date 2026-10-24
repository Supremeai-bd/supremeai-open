# Quickstart — Validation Drills

Feature: 001-dynamic-production-configuration · Date: 2026-08-29
Runnable scenarios proving the feature end-to-end. Implementation details live in
`tasks.md`; entity definitions in `data-model.md`; key names in
`contracts/config-contract.md`.

## Prerequisites

- Python 3.11+ venv for `backend/` (existing setup per `CONTRIBUTING.md`)
- Node 18+ / pnpm for `frontend/`
- A machine-local `envs/*.env` composition (untracked) — never commit values

## Drill 1 — Static hostname scan (SC-002, FR-011)

```powershell
python scripts/ci/check_hardcoded_deployment_config.py
```

**Expected**: exit code 0, report shows `0 findings` across `backend/` and
`frontend/src` (tests/fixtures/docs excluded). Before implementation this
documents the current violations as the baseline.

## Drill 2 — Production fail-fast (SC-003, FR-002)

```powershell
$env:ENV="production"; Remove-Item Env:SUPREMEAI_ADMIN_BACKEND_URL -ErrorAction SilentlyContinue
# start backend with the machine-local env composition minus one required key
```

**Expected**: startup aborts in < 5s with a single error listing **all** missing
required keys (not just the first). Non-production ENV must NOT abort.

## Drill 3 — Optional-missing boot (SC-004, FR-003, FR-014)

Start backend with `REDIS_URL`, `SCRAPER_URL`, `OLLAMA_URL`, and all optional
provider keys unset.

**Expected**: boot succeeds; health surfaces report each as `not_configured`;
core flows (auth, chat via a configured provider, health) work; no retry storms.

## Drill 4 — Service-swap (SC-001, FR-010)

Change `SUPREMEAI_USER_BACKEND_URL` (and the deploy-time
`{{USER_BACKEND_URL}}` substitution) to a different host; redeploy **the same
source revision**.

**Expected**: `/config/public`, service topology, and health aggregation all
report the new host; `git diff` shows zero source changes; frontend requests hit
the new host (Drill 5 evidence).

## Drill 5 — Frontend build & placeholder check (SC-006, FR-005, FR-006, FR-013)

```powershell
pnpm --filter frontend build   # with VITE_* values from build config
```

**Expected**: built bundle contains the configured backend host and zero
provider hostnames; a generated hosting config still containing
`{{USER_BACKEND_URL}}` fails the artifact check; a production Firebase config
missing any required field fails the build/boot with the key named.

## Drill 6 — CORS unification & aliases (FR-004, FR-008, FR-012)

Set `CORS_ORIGINS` including an admin-console origin; set legacy
`ALLOWED_ORIGINS` and `USER_CORS_ORIGINS` as well.

**Expected**: user API allow-list excludes the admin origin (portal isolation);
legacy names produce deprecation warnings and still work; malformed JSON in a
list variable surfaces the variable name and parse error.
