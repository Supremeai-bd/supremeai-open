# Phase 1 — Data Model (configuration domain)

Feature: 001-dynamic-production-configuration · Date: 2026-08-29
No database schema changes — these are configuration-domain entities expressed in
code (registry module) and artifacts (validation report).

## Entity 1 — DeploymentConfiguration (registry entry)

| Field | Type | Rules |
|---|---|---|
| key | string (UPPER_SNAKE) | stable canonical name; legacy aliases resolve to it |
| classification | enum: `required` \| `optional` \| `conditional` \| `secret` \| `public` | per contracts/config-contract.md; `secret` ⇒ masked in any report/log |
| required_in_production | bool | derived: `required` ⇒ true; `conditional` ⇒ true when its condition holds (e.g. portal type, feature enabled) |
| aliases | list[string] | legacy names (e.g. `ALLOWED_ORIGINS` → `CORS_ORIGINS`); use triggers deprecation warning |
| source | enum: `env` \| `secret_manager` \| `build_time` \| `deploy_time` | provenance recorded in report |
| scope | enum: `backend` \| `frontend` \| `deploy` | which artifact consumes it |

Validation rules: unknown legacy key ⇒ warning; canonical wins over alias; empty
string counts as missing for `required`.

## Entity 2 — ServiceEndpoint

| Field | Type | Rules |
|---|---|---|
| service | enum: `main_backend` \| `admin_backend` \| `scraper` \| `studio_client` | stable logical name |
| location | string \| `not_configured` | resolved via config chain (explicit env → derived default → not_configured if optional) |
| required | bool | main/admin backend true; scraper/studio_client false |
| consumers | list[string] | surfaces that call it (portal apps, health aggregation, topology) |

State transitions: `not_configured → configured` (deploy-time only, via config +
redeploy); `configured → unreachable` (runtime health only; never mutates config).

## Entity 3 — ConfigValidationReport

| Field | Type | Rules |
|---|---|---|
| generated_at | timestamp | per boot / on-demand admin fetch |
| environment | enum: `development` \| `staging` \| `production` | drives fail-fast behavior |
| entries | list[key, status, classification, source, masked?] | status ∈ `loaded` \| `missing` \| `not_configured` \| `alias_used` |
| missing_required | list[key] | non-empty in production ⇒ boot abort |
| warnings | list[string] | alias usage, malformed values, placeholder residue |

Invariants: secret values never serialized (masking is structural, not cosmetic);
report is deterministic for identical environment inputs.
