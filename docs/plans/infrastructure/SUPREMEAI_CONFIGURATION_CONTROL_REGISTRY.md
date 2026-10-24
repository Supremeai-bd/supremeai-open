---
target_scope: combined_ecosystem
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:SUPREMEAI_CONFIGURATION_CONTROL_REGISTRY_V2
subject: SupremeAI 2.0 — Configuration, Third‑Party Service & Secret Control Registry
document_role: policy
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI 2.0 — Configuration, Third‑Party Service & Secret Control Registry

**Document type:** Living operational checklist  
**Purpose:** Single source of truth for third‑party services, environment variables, secrets, configuration values, source/fallback provenance, hardcoded-vs-dynamic status, deployment injection paths, and verification.  
**Repository:** `SaifulHaqueNiloy/supremeai`  
**Primary environments:** `local`, `staging`, `production`  
**Last reviewed:** 2026-08-29

---

## 1. Why this document exists

SupremeAI's roadmap explicitly requires:

> “Never hardcode anything that is destined to evolve—build dynamically from Day 1.”

This registry turns that principle into an operational control system.

Use it to answer, for every external dependency or evolving configuration value:

- What service/provider is involved?
- Which variable/key does the code expect?
- Is it required, feature-dependent, or optional?
- Where does the value come from?
- Can it come from more than one source?
- What is the precedence/fallback order?
- Where is it injected?
- Is it runtime or build-time?
- Is the current implementation dynamic, hardcoded, or mixed?
- Has the value been verified in the real deployment?
- Does it have a rotation/expiry requirement?
- Is the repository documentation/config consistent with the code?

**Security rule:** never place secret values in this document. Record names, source locations, ownership, and verification state only.

---

# 2. Status legend

- [ ] Not verified
- [x] Verified
- [~] Partially verified / needs confirmation
- [!] Problem / mismatch / remediation required
- [N/A] Not applicable
- **MUST** = required for the active deployment/feature
- **GOOD** = recommended for reliability, portability, observability, or operations
- **OPTIONAL** = only required when the related feature is enabled
- **VERIFY** = referenced by docs/roadmap/config, but current runtime usage needs confirmation

---

# 3. Source-of-truth model

## 3.1 Allowed source locations

For each variable, explicitly record one or more of:

- [ ] Render Environment Variables
- [ ] GitHub Actions Secrets / Variables
- [ ] Infisical Vault
- [ ] Supabase project configuration/secrets
- [ ] Firebase / GCP configuration
- [ ] Cloudflare configuration
- [ ] Vercel project environment
- [ ] Netlify environment
- [ ] Docker build/runtime environment
- [ ] Local `.env`
- [ ] CI-generated environment
- [ ] Build-time frontend environment
- [ ] Runtime environment
- [ ] Database configuration
- [ ] External provider dashboard
- [ ] Generated automatically
- [ ] Code default
- [ ] Config file (non-secret)
- [ ] Remote configuration / feature flag

## 3.2 Source-of-truth rule

Every secret/config item should have:

```text
Primary Source:
Fallback Source:
Injection Target:
Runtime/Build:
Precedence:
Owner:
Rotation:
Validation:
```

Never silently invent a fallback. If multiple sources are allowed, document their explicit precedence.

### Recommended precedence pattern

```text
1. Explicit production secret manager / vault
2. Explicit deployment environment
3. CI-provided value
4. Local development `.env`
5. Safe non-secret code/config default
```

This is a policy template, not a claim that every variable currently follows it. Verify per variable.

---

# 4. Master third-party service inventory

## 4.1 Core infrastructure / hosting

| Service | Purpose | Expected source(s) | Runtime/CI | Criticality | Status |
|---|---|---|---|---|---|
| Render | Backend hosting/deployment | Render ENV; Infisical; GitHub Actions for deploy | Runtime + CI | MUST | [~] |
| GitHub | Source control, CI/CD, repository automation | GitHub Actions secrets; GitHub App/OAuth values; auto `GITHUB_TOKEN` | CI + runtime integrations | MUST | [~] |
| Infisical | Central secret vault | GitHub bootstrap secrets + Render runtime integration | Runtime + CI | MUST | [~] |
| Supabase | PostgreSQL + REST/API + RLS | Infisical / Render ENV | Runtime | MUST | [~] |
| Upstash Redis | Redis-compatible cache/rate limit/queues | Infisical / Render ENV | Runtime | MUST when Redis-backed features enabled | [~] |
| Firebase / GCP | Hosting, auth/integration, Google cloud services | GitHub Actions, GCP secrets, Firebase config | Build + CI + runtime | MUST for Firebase surfaces | [~] |
| Cloudflare | Workers / edge deployment / routing | GitHub Actions / Infisical | CI + edge runtime | OPTIONAL | [~] |
| Vercel | Frontend/optional deployment | Vercel project ENV / GitHub Actions | Build + CI | OPTIONAL | [~] |
| Netlify | Alternate frontend deployment | Netlify ENV / GitHub Actions | Build + CI | OPTIONAL | [~] |

## 4.2 Observability / notifications

| Service | Purpose | Expected source(s) | Criticality | Status |
|---|---|---|---|---|
| Sentry | Error monitoring / release sourcemaps | Infisical / GitHub Actions | GOOD / MUST when enabled | [~] |
| Discord | OTP/maintenance/system notifications | Infisical / Render ENV | OPTIONAL | [~] |
| Slack | CI/maintenance notifications | GitHub Actions / Infisical | OPTIONAL | [~] |
| Resend | Transactional email | Infisical / Render ENV | OPTIONAL | [~] |

## 4.3 Payments / business services

| Service | Purpose | Expected source(s) | Criticality | Status |
|---|---|---|---|---|
| Stripe | Billing/payment/webhooks | Infisical / Render ENV / GitHub CI where needed | OPTIONAL unless billing enabled | [~] |
| SSLCommerz | Bangladesh payment gateway | Infisical / Render ENV | OPTIONAL unless enabled | [~] |

## 4.4 AI / model providers

| Service | Typical variable(s) | Expected source(s) | Criticality | Status |
|---|---|---|---|---|
| OpenAI | `OPENAI_API_KEY` | Infisical → Render | OPTIONAL / feature dependent | [~] |
| OpenRouter | `OPENROUTER_API_KEY` | Infisical → Render | OPTIONAL / fallback provider | [~] |
| Google Gemini | `GEMINI_API_KEY` | Infisical → Render / CI | OPTIONAL | [~] |
| Groq | `GROQ_API_KEY` | Infisical → Render | OPTIONAL | [~] |
| NVIDIA | `NVIDIA_API_KEY` | Infisical → Render | OPTIONAL | [~] |
| DeepSeek | `DEEPSEEK_API_KEY` | Infisical → Render | OPTIONAL | [~] |
| Anthropic | `ANTHROPIC_API_KEY` | Infisical → Render | OPTIONAL / verify current code path | [~] |
| Hugging Face | `HF_API_KEY`, related token aliases | Infisical → Render / CI | OPTIONAL | [~] |
| Firecrawl | `FIRECRAWL_API_KEY` | Infisical → Render | OPTIONAL | [~] |

## 4.5 AI/IDE developer tooling

| Service | Typical variable(s) | Expected source(s) | Criticality | Status |
|---|---|---|---|---|
| Cline | `CLINE_API_KEY` | Infisical / local tool config | OPTIONAL | [~] |
| Continue.dev | `CONTINUE_API_KEY` | Infisical / local tool config | OPTIONAL | [~] |
| Kilo Code | extension ID / runtime integration | Local extension + backend | OPTIONAL | [~] |
| Aider | `AIDER_API_KEY` | Infisical / local | OPTIONAL | [~] |
| Codeium | `CODEIUM_API_KEY` | Infisical / local | OPTIONAL | [~] |

## 4.6 Data / infrastructure services referenced by code/docs/roadmap

| Service | Typical variable(s) | Criticality | Status |
|---|---|---|---|
| Qdrant | `QDRANT_URL`, `QDRANT_API_KEY` | OPTIONAL / feature dependent | [~] VERIFY |
| Neo4j | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | OPTIONAL / feature dependent | [~] |
| NATS | `NATS_TOKEN` | OPTIONAL / feature dependent | [~] VERIFY |
| GCP Pub/Sub | `GCP_PUBSUB_TOPIC`, `GCP_PUBSUB_SUBSCRIPTION` | OPTIONAL | [~] |
| Firestore | GCP service account / Firebase/GCP credentials | OPTIONAL / feature dependent | [~] |

---

# 5. Critical runtime secret registry

## 5.1 Authentication, signing and encryption

| Variable | Used for | Primary source | Fallback | Criticality | Runtime | Status |
|---|---|---|---|---|---|---|
| `SUPREMEAI_JWT_SECRET` | JWT signing | Infisical | Render ENV | MUST | Backend | [~] |
| `ENCRYPTION_KEY` | Application encryption | Infisical | Render ENV | MUST | Backend | [~] |
| `SUPREMEAI_ADMIN_PASSWORD_HASH` | Admin credential hash | Infisical | Render ENV | MUST | Backend | [~] |
| `SUPREMEAI_API_TOKEN` / `SUPREMEAI_API_KEY` | Backend/system authentication | Infisical | Render ENV | MUST where used | Backend | [~] |
| `API_KEY_SIGNING_SECRET` | API key signing | Infisical | Render ENV | GOOD/MUST for feature | Backend | [~] |
| `JIT_OTP_SECRET` | JIT OTP/security flow | Infisical | deployment ENV | OPTIONAL | Backend/frontend flow | [~] VERIFY |

### Mandatory production checks

- [ ] JWT secret is present and meets production length requirements.
- [ ] Encryption key is present and valid.
- [ ] Admin password hash is present.
- [ ] No secret falls back to a development default in production.
- [ ] Rotation path is documented.
- [ ] Secret values never appear in logs/errors.
- [ ] CI checks secret presence without printing values.

---

# 6. Supabase secret/config registry

Current code has a dedicated server-side service client for backend-only/RLS-protected operations.

| Variable | Purpose | Primary source | Fallback | Runtime | Criticality | Status |
|---|---|---|---|---|---|---|
| `SUPABASE_URL` | Supabase API URL | Infisical | Render ENV | Backend | MUST | [~] |
| `SUPABASE_KEY` | Main Supabase API key/client context | Infisical | Render ENV | Backend | MUST | [~] |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend-only RLS bypass | Infisical | **Do not silently use in production fallback** | Backend | MUST for service-client paths | [!] |
| `SUPABASE_DATABASE_URL_POOLER` | Direct PostgreSQL/pooler | Infisical | Render ENV | Backend | MUST | [~] |
| `SUPABASE_DB_CA_CERT` | Explicit PostgreSQL CA verification | Infisical | Render ENV | Backend | MUST when explicit CA path is used | [~] |

### Supabase control checks

- [ ] `SUPABASE_SERVICE_ROLE_KEY` exists in production when service-client paths are enabled.
- [ ] User-facing client never receives service-role credentials.
- [ ] Service client is never built from a user Authorization token.
- [ ] RLS-protected internal tables remain protected.
- [ ] Data API calls are mapped against table policies.
- [ ] PostgreSQL SSL verification remains enabled.
- [ ] `SUPABASE_DB_CA_CERT` is tested if required by the selected connection mode.
- [ ] RLS migration is idempotent.
- [ ] `anon`, `authenticated`, and backend-service access are separately tested.

---

# 7. Redis / Upstash registry

| Variable | Purpose | Primary source | Fallback | Criticality | Status |
|---|---|---|---|---|---|
| `REDIS_URL` | Redis/Upstash connection | Infisical | Render ENV | MUST for Redis-backed features | [~] |
| `UPSTASH_REDIS_REST_URL` | Upstash REST endpoint | Infisical / provider dashboard | Render ENV | OPTIONAL if REST path is used | [~] |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash REST authentication | Infisical | Render ENV | OPTIONAL if REST path is used | [~] |
| `RATE_LIMIT_FALLBACK_MAX_KEYS` | bounded in-memory fallback limit | Render ENV / safe code default | code default | GOOD | [~] |
| `RATE_LIMIT_USE_SIMPLIFIED` | disables real Redis in simplified mode | Render ENV | safe non-prod default | MUST verify in production | [!] |

### Redis controls

- [ ] Production does not unintentionally run with `RATE_LIMIT_USE_SIMPLIFIED=true`.
- [ ] Central `redis_manager` is used where intended.
- [ ] Rate limiter does not create an independent connection unnecessarily.
- [ ] Redis ping/connectivity is verified at runtime.
- [ ] Fallback cache is bounded.
- [ ] Redis failures have controlled fallback behavior.
- [ ] No secret/token printed in logs.

---

# 8. Render deployment registry

## 8.1 Render service configuration

| Variable | Purpose | Source | Criticality | Status |
|---|---|---|---|---|
| `RENDER_API_KEY` | Render API/deploy control | GitHub Actions / Infisical | MUST for automated deploy | [~] |
| `RENDER_PRIMARY_SVC_ID` | primary service identifier | GitHub Actions / Infisical | GOOD/MUST for automation | [~] |
| `RENDER_BACKEND_SVC_ID` | backend service identifier | GitHub Actions / Infisical | MUST if this name is used by CI | [!] |
| `RENDER_DEPLOY_HOOK_URL` | webhook deployment fallback | GitHub Actions / Infisical | OPTIONAL | [~] |
| `PORT` | application port | Render ENV | MUST | [x] |
| `ENV` | environment selector | Render ENV | MUST | [x] |
| `SERVICE_ROLE` | user/admin instance role | Render ENV | MUST | [x] |
| `ALLOWED_HOSTS` | host allow-list | Render ENV / Infisical | MUST | [~] |
| `USER_CORS_ORIGINS` | user frontend CORS | Render ENV / Infisical | MUST | [~] |
| `ADMIN_CORS_ORIGINS` | admin frontend CORS | Render ENV / Infisical | MUST | [~] |
| `BACKEND_URL` | canonical backend URL | Render ENV / Infisical | MUST | [~] |

### Render deployment checks

- [ ] `ENV=production`
- [ ] Correct `SERVICE_ROLE` for each service.
- [ ] Correct health-check path.
- [ ] Correct backend URL.
- [ ] Exact Render service IDs are consistent across GitHub/Infisical/docs.
- [ ] No obsolete service ID remains in CI.
- [ ] Auto-deploy is enabled only where intended.
- [ ] Runtime secrets are not committed to `render.yaml`.
- [ ] Secret injection path is verified after each deployment.

---

# 9. GitHub / CI/CD registry

| Variable | Purpose | Source | Criticality | Status |
|---|---|---|---|---|
| `GITHUB_TOKEN` | GitHub Actions built-in auth | GitHub Actions automatic | MUST for many workflows | [x] |
| `GITHUB_API_TOKEN` | explicit GitHub API token | GitHub Secret / Infisical | OPTIONAL/automation-dependent | [~] |
| `GH_TOKEN` | CLI/API fallback token | GitHub Secret | OPTIONAL | [~] |
| `GITHUB_CLIENT_ID` | GitHub OAuth/App integration | Infisical | OPTIONAL | [~] |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth/App integration | Infisical | OPTIONAL | [~] |
| `INFISICAL_CLIENT_ID` | CI bootstrap to Infisical | GitHub Secret | MUST for vault bootstrap | [~] |
| `INFISICAL_CLIENT_SECRET` | CI bootstrap to Infisical | GitHub Secret | MUST for vault bootstrap | [~] |
| `INFISICAL_PROJECT_ID` | Infisical project selection | GitHub Secret | MUST for vault bootstrap | [~] |
| `INFISICAL_TOKEN` | legacy/bootstrap alternative | GitHub Secret / Infisical | OPTIONAL legacy | [~] |
| `CI_WEBHOOK_SECRET` | CI webhook authentication | GitHub + Infisical + runtime | GOOD/MUST where used | [~] |

### GitHub CI controls

- [ ] Bootstrap secrets are kept separate from application runtime secrets.
- [ ] CI has access only to secrets required by the workflow.
- [ ] No production application master secret is exposed to unrelated CI jobs.
- [ ] GitHub built-in `GITHUB_TOKEN` is used where sufficient.
- [ ] Permissions are least-privilege.
- [ ] Secret-validation job runs before deploy.
- [ ] Secret validation checks both required and feature-dependent keys.
- [ ] CI never prints secret values.

---

# 10. Infisical registry

## 10.1 Bootstrap

These belong at the **GitHub Actions bootstrap layer**, not as ordinary application secrets:

- [ ] `INFISICAL_CLIENT_ID`
- [ ] `INFISICAL_CLIENT_SECRET`
- [ ] `INFISICAL_PROJECT_ID`
- [ ] Optional legacy `INFISICAL_TOKEN`

## 10.2 Recommended path separation

```text
Infisical
├── /github-actions
│   └── CI/CD-only deployment secrets
│
├── /render-backend
│   └── production backend runtime secrets
│
├── /render-admin
│   └── production admin runtime secrets
│
└── /other services
    └── service-specific secrets only
```

### Infisical controls

- [ ] CI cannot read unrelated production application secrets.
- [ ] Backend runtime cannot read GitHub-only deploy secrets unless required.
- [ ] Admin runtime receives only admin/runtime secrets.
- [ ] Environment separation (`prod`, `staging`, etc.) is explicit.
- [ ] Secret rotation ownership is documented.
- [ ] Every runtime secret has a source path recorded in this registry.

---

# 11. Firebase / GCP registry

| Variable / credential | Purpose | Source | Criticality | Status |
|---|---|---|---|---|
| `FIREBASE_PROJECT_ID` | Firebase project | GitHub / GCP / provider config | MUST for Firebase deployment | [~] |
| `GCP_PROJECT_ID` | GCP project selection | GitHub / Infisical / provider config | Feature dependent | [~] |
| `GCP_SA_KEY` | service-account credential for CI | GitHub Secret / Infisical | MUST when CI deploy uses it | [~] |
| `GOOGLE_APPLICATION_CREDENTIALS` | service account lookup path | runtime/CI | Feature dependent | [~] |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Firebase service account payload | Infisical / Render | Feature dependent | [~] |
| `GCP_ACCESS_TOKEN` | GCP API auth | CI/provider | OPTIONAL | [~] |
| `GCP_PUBSUB_TOPIC` | Pub/Sub topic | Infisical / runtime | OPTIONAL | [~] |
| `GCP_PUBSUB_SUBSCRIPTION` | Pub/Sub subscription | Infisical / runtime | OPTIONAL | [~] |

### Controls

- [ ] Firebase project IDs match deployed project.
- [ ] GCP service account is least privilege.
- [ ] Service account JSON is never committed.
- [ ] Firebase Hosting rewrites point to the correct backend.
- [ ] Production frontend build uses the intended backend URL.
- [ ] GCP credentials are available only where needed.

---

# 12. Cloudflare registry

| Variable | Purpose | Source | Criticality | Status |
|---|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API/Workers deployment | GitHub Secret / Infisical | OPTIONAL | [~] |
| `CLOUDFLARE_ACCOUNT_ID` | Wrangler account selection | GitHub Secret / Infisical | MUST for Workers deploy | [~] |
| `CLOUDFLARE_ZONE_ID` | DNS/zone routing | GitHub / Infisical | OPTIONAL | [~] |
| `CLOUDFLARE_WORKERS_API_TOKEN` | legacy/specific Worker auth | GitHub / Infisical | OPTIONAL / VERIFY | [~] |
| `CLOUDFLARE_API_KEY` | alternate Cloudflare auth | GitHub / Infisical | OPTIONAL / VERIFY | [~] |

### Controls

- [ ] Prefer scoped API tokens over global API keys.
- [ ] Account ID is non-secret configuration if provider treats it as such, but keep it in deployment config for consistency.
- [ ] Zone ID is tracked separately from API tokens.
- [ ] CI workflow uses the intended Cloudflare credential, not multiple conflicting ones.
- [ ] Worker names/bindings are dynamic/config-driven.

---

# 13. Frontend build-time environment registry

**Important:** `VITE_*` values are generally public build configuration, not secret storage.

| Variable | Purpose | Source | Runtime | Status |
|---|---|---|---|---|
| `VITE_API_URL` | frontend backend base URL | Vercel/Netlify/Firebase build env | Build-time | [~] |
| `VITE_ADMIN_BACKEND` | admin backend URL | frontend build env | Build-time | [~] |
| `VITE_USER_BACKEND` | user backend URL | frontend build env | Build-time | [~] |
| `VITE_PORTAL_TYPE` | user/admin portal mode | frontend build env | Build-time | [~] |
| `VITE_WS_BASE_URL` | WebSocket override | frontend build env | Build-time | [~] |
| `VITE_API_CONCURRENCY` | client concurrency | frontend build env | Build-time | [~] |
| `VITE_API_TIMEOUT_MS` | client timeout | frontend build env | Build-time | [~] |

### Frontend controls

- [ ] No secret is prefixed `VITE_`.
- [ ] Frontend URLs are environment-specific.
- [ ] No stale Render/Vercel/Netlify URL survives in production build.
- [ ] Backend URL is not hardcoded separately inside application code.
- [ ] WebSocket URL follows the same environment mapping.
- [ ] Portal type is not duplicated across code/config.

---

# 14. Email / messaging / notification registry

| Variable | Service | Source | Criticality | Status |
|---|---|---|---|---|
| `RESEND_API_KEY` | Resend | Infisical / Render | OPTIONAL | [~] |
| `ADMIN_NOTIFICATION_EMAIL` | Admin notification target | Infisical / Render | GOOD | [~] |
| `DISCORD_OTP_WEBHOOK_URL` | Discord OTP notification | Infisical / Render | OPTIONAL | [~] |
| `DISCORD_WEBHOOK_URL` | Discord alerts | Infisical / CI | OPTIONAL | [~] |
| `DISCORD_ALERT_WEBHOOK` | Discord alert path | Infisical / Render | OPTIONAL / VERIFY | [~] |
| `SLACK_WEBHOOK_URL` | Slack alerts | GitHub / Infisical | OPTIONAL | [~] |
| `SLACK_BOT_TOKEN` | Slack bot | GitHub / Infisical | OPTIONAL | [~] |
| `DISCORD_BOT_TOKEN` | Discord bot | Infisical / Render | OPTIONAL | [~] |
| `TELEGRAM_BOT_TOKEN` | Telegram integration | Infisical | OPTIONAL | [~] |
| `ADMIN_TELEGRAM_CHAT_ID` | Telegram destination | Infisical | OPTIONAL | [~] |

---

# 15. Billing / payment registry

| Variable | Service | Source | Criticality | Status |
|---|---|---|---|---|
| `STRIPE_API_KEY` | Stripe API | Infisical / Render | MUST when Stripe billing enabled | [~] |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook verification | Infisical / Render | MUST when webhooks enabled | [~] |
| SSLCommerz credential set | SSLCommerz | Infisical / Render | MUST when enabled | [~] VERIFY |

### Controls

- [ ] Webhook signing secrets are separate from API keys.
- [ ] Test and production payment credentials are separated.
- [ ] Payment environment is explicit.
- [ ] No payment secret is sent to the frontend.

---

# 16. AI provider registry

For every provider that is actually enabled:

```text
Provider:
API key variable:
Optional secondary key(s):
Primary model:
Fallback model:
Daily quota:
RPM/TPM:
Cost guard:
Circuit breaker:
Source:
Runtime:
Rotation:
Verified:
```

## Provider variables currently represented in the repository

- [ ] `OPENAI_API_KEY`
- [ ] `OPENROUTER_API_KEY`
- [ ] `GEMINI_API_KEY`
- [ ] `GROQ_API_KEY`
- [ ] `NVIDIA_API_KEY`
- [ ] `DEEPSEEK_API_KEY`
- [ ] `ANTHROPIC_API_KEY`
- [ ] `HF_API_KEY`
- [ ] Additional Hugging Face tokens/aliases (`HF_TOKEN`, `HUGGINGFACE_TOKEN`) — **verify which are still active**
- [ ] `FIRECRAWL_API_KEY`
- [ ] `GOOGLE_API_KEY` — **verify exact consumer**
- [ ] `GROQ_API_KEY_DEPLOYMENT_MONITOR` — **verify exact consumer**

### AI architecture controls

- [ ] Provider choice is configuration-driven.
- [ ] Model names are not hardcoded where roadmap says they should evolve.
- [ ] Provider fallback matrix is configuration-driven.
- [ ] Per-provider cost/quota limits are configuration-driven.
- [ ] Circuit breakers are configured.
- [ ] PII masking occurs before external provider transmission where required.
- [ ] A missing optional provider key disables only its feature/provider path.

The roadmap's provider-fallback design emphasizes replaceable vendors and avoiding hardcoded model/provider coupling. Track every future provider addition here.

---

# 17. Graph / vector / messaging service registry

## Qdrant

- [ ] `QDRANT_URL`
- [ ] `QDRANT_API_KEY`
- [ ] Feature enabled flag
- [ ] Collection name/config
- [ ] Dimension/embedding model configuration
- [ ] Source: Infisical / Render
- [ ] Connection health test
- [ ] Rotation procedure

## Neo4j

- [ ] `NEO4J_URI` / repository-specific naming
- [ ] `NEO4J_USER`
- [ ] `NEO4J_PASSWORD`
- [ ] Source: Infisical / Render
- [ ] Database/graph name
- [ ] Connection health test

## NATS

- [ ] `NATS_TOKEN`
- [ ] Server URL
- [ ] Stream/subject names
- [ ] Consumer configuration
- [ ] Source: Infisical
- [ ] Feature flag / usage verified

## GCP Pub/Sub

- [ ] `GCP_PUBSUB_TOPIC`
- [ ] `GCP_PUBSUB_SUBSCRIPTION`
- [ ] `GCP_PROJECT_ID`
- [ ] Credential source
- [ ] Topic/subscription existence verified

---

# 18. Feature flags and evolving configuration

These values should be tracked even though they are not secrets.

| Variable | Classification | Preferred source | Status |
|---|---|---|---|
| `ENABLE_TIER8` | feature flag | Render ENV / remote config | [~] |
| `ENABLE_EVOLUTION` | feature flag | Render ENV / remote config | [~] |
| `ENABLE_DAILY_LEARNER` | feature flag | Render ENV / remote config | [~] |
| `ENABLE_AUTO_HEALER` | feature flag | Render ENV / remote config | [~] |
| `AUTO_REMEDIATION_DRY_RUN` | safety flag | Render ENV | [~] |
| `ENABLE_MEMORY_AUGMENT` | feature flag | Render ENV | [~] |
| `ENABLE_AUTOSCALING_AGENT` | feature flag | Render ENV | [~] |
| `ENABLE_PERFORMANCE_TUNING_AGENT` | feature flag | Render ENV | [~] |
| `ENABLE_COST_OPTIMIZATION_AGENT` | feature flag | Render ENV | [~] |
| `ENABLE_DISASTER_RECOVERY_AGENT` | feature flag | Render ENV | [~] |
| `ENFORCE_ANTI_HACKING` | security flag | Render ENV | [~] |
| `SUPREMEAI_MEM0_ENABLED` | integration flag | Render ENV | [~] |
| `SUPREMEAI_GRAPHITI_ENABLED` | integration flag | Render ENV | [~] |
| `SUPREMEAI_BROWSER_USE_ENABLED` | integration flag | Render ENV | [~] |
| `SUPREMEAI_E2B_ENABLED` | integration flag | Render ENV | [~] |
| `SUPREMEAI_OPENHANDS_ENABLED` | integration flag | Render ENV | [~] |

### Feature-flag rule

Every flag must document:

```text
Default:
Production value:
Who may change it:
Restart required?:
Safe rollback:
Dependency:
Cost impact:
```

---

# 19. Non-secret evolving configuration checklist

These values belong in the registry even when they are not secrets because the roadmap requires dynamic, portable behavior.

## 19.1 URLs / endpoints

- [ ] Frontend URL
- [ ] Admin URL
- [ ] Backend URL
- [ ] WebSocket URL
- [ ] Supabase API URL
- [ ] PostgreSQL pooler URL
- [ ] Redis URL
- [ ] Qdrant URL
- [ ] Neo4j URI
- [ ] NATS endpoint
- [ ] GCP endpoints
- [ ] Provider base URLs
- [ ] Webhook URLs

## 19.2 Identity / resource IDs

- [ ] Render service IDs
- [ ] Firebase project ID
- [ ] GCP project ID
- [ ] Cloudflare account ID
- [ ] Cloudflare zone ID
- [ ] Vercel project/org IDs
- [ ] GitHub repository/installation IDs where runtime-configured
- [ ] Pub/Sub topic/subscription
- [ ] Worker/service names
- [ ] Bucket/resource names

## 19.3 Limits / thresholds

- [ ] API timeout values
- [ ] Connection timeouts
- [ ] Read/write/pool timeouts
- [ ] Max connections
- [ ] Cache max size
- [ ] Retry counts
- [ ] Retry backoff
- [ ] Circuit-breaker threshold
- [ ] Circuit-breaker cooldown
- [ ] Rate limits
- [ ] token limits
- [ ] daily quota thresholds
- [ ] task concurrency
- [ ] agent heartbeat threshold
- [ ] memory warning threshold
- [ ] maintenance interval

## 19.4 Provider/model selection

- [ ] Provider names
- [ ] Model IDs
- [ ] Fallback model IDs
- [ ] routing weights
- [ ] minimum provider weight
- [ ] latency SLA thresholds
- [ ] quota allocation
- [ ] cost-per-task ceiling

---

# 20. Hardcoded → dynamic conversion registry

Use this section to prevent regression.

| Value category | Current state | Desired state | Verification |
|---|---|---|---|
| Supabase URL | mixed/dynamic | ENV/Vault | [ ] |
| Supabase API keys | dynamic secret loader | Vault + deployment injection | [ ] |
| Supabase service key | dynamic secret loader | mandatory Vault in production | [!] |
| DB CA certificate | dynamic property exists | Vault/Render injected PEM | [~] |
| Render service IDs | mixed naming across docs/CI | single canonical variable names | [!] |
| CORS origins | env-driven | environment-specific | [~] |
| Allowed hosts | env-driven | environment-specific | [~] |
| Backend URL | env-driven | single source | [~] |
| Frontend API URL | build-time env | per-deployment build env | [~] |
| AI API keys | vault/env | vault-first | [~] |
| AI model names | mixed | configuration-driven | [~] |
| Rate-limit values | partly defaulted | configuration-driven | [~] |
| Feature flags | ENV/config | centralized configuration | [~] |
| Redis endpoint | env-driven | centralized source | [~] |
| Render port | safe default + ENV | deployment ENV | [x] |
| Worker count | ENV/config | deployment config | [~] |

---

# 21. Hardcoded value audit checklist

Run a recurring scan for these patterns:

```text
"http://..."
"https://..."
"postgresql://..."
"postgresql+asyncpg://..."
"redis://..."
"rediss://..."
"wss://..."
API key literals
token literals
secret/password literals
model ID literals
Render service IDs
Supabase project IDs
Firebase project IDs
Cloudflare account/zone IDs
Vercel project IDs
email addresses used as operational config
webhook URLs
provider names
rate-limit numbers
timeout numbers
retry numbers
feature flags
CORS origins
allowed hosts
bucket names
queue/topic names
```

For each match:

- [ ] Secret → move to vault/deployment secret
- [ ] Environment-specific value → move to ENV/config
- [ ] Provider/model selection → dynamic registry/config
- [ ] Safe constant → document why it is safely constant
- [ ] Protocol/standards constant → keep only when genuinely invariant
- [ ] Default → mark as safe fallback and verify production override

---

# 22. Source + fallback tracking template

Copy this block for every new variable:

```text
Variable:
Service:
Purpose:

Requiredness:
[ ] MUST
[ ] GOOD
[ ] OPTIONAL
[ ] VERIFY

Secret?
[ ] YES
[ ] NO

Primary Source:
[ ] Infisical
[ ] Render ENV
[ ] GitHub Secret
[ ] Provider Dashboard
[ ] Firebase/GCP
[ ] Cloudflare
[ ] Vercel
[ ] Netlify
[ ] Database
[ ] Generated
[ ] Code default

Fallback Source(s):
1.
2.
3.

Precedence:
1.
2.
3.

Injected Into:
[ ] Render backend
[ ] Render admin
[ ] GitHub Actions
[ ] Firebase build
[ ] Vercel build
[ ] Netlify build
[ ] Cloudflare Worker
[ ] Local development
[ ] VS Code extension
[ ] Other:

Build-time or Runtime:
[ ] Build-time
[ ] Runtime
[ ] Both

Used By:
File(s)/module(s):

Current State:
[ ] Dynamic
[ ] Hardcoded
[ ] Mixed

Validation:
[ ] CI
[ ] Startup
[ ] Health check
[ ] Integration test
[ ] Manual provider check

Rotation:
Frequency:
Owner:
Last rotated:
Next review:

Status:
[ ] Verified
[ ] Needs work
```

---

# 23. Environment-by-environment deployment checklist

## 23.1 Local

- [ ] `.env` exists only locally and is git-ignored.
- [ ] `.env.example` matches the documented variable names.
- [ ] No production credentials are used.
- [ ] Local defaults are safe.
- [ ] Optional services can be disabled cleanly.

## 23.2 Staging

- [ ] Separate secrets from production.
- [ ] Separate database/project where appropriate.
- [ ] Separate payment/provider credentials where applicable.
- [ ] Same variable names as production unless there is an explicit documented exception.
- [ ] Deployment performs secret validation.
- [ ] Health checks exercise real dependencies.

## 23.3 Production

- [ ] Every MUST variable is present.
- [ ] Every enabled optional feature has its required dependencies.
- [ ] Primary/fallback source is verified.
- [ ] No development fallback is active.
- [ ] No test authentication bypass is active.
- [ ] Service-role credentials are backend-only.
- [ ] RLS/access-control tests pass.
- [ ] TLS verification is enabled.
- [ ] Provider credentials are valid.
- [ ] Rotation dates are tracked.
- [ ] CI reports missing keys without exposing values.

---

# 24. Required / Good / Optional master list

## MUST-HAVE for current production baseline

### Core security
- [ ] `SUPREMEAI_JWT_SECRET`
- [ ] `ENCRYPTION_KEY`
- [ ] `SUPREMEAI_ADMIN_PASSWORD_HASH`
- [ ] `SUPREMEAI_API_TOKEN` / canonical equivalent
- [ ] `SERVICE_ROLE`
- [ ] `ENV`

### Supabase
- [ ] `SUPABASE_URL`
- [ ] `SUPABASE_KEY`
- [ ] `SUPABASE_DATABASE_URL_POOLER`
- [ ] `SUPABASE_SERVICE_ROLE_KEY` when service-client/RLS-protected backend writes are enabled
- [ ] `SUPABASE_DB_CA_CERT` when required by production TLS configuration

### Redis
- [ ] `REDIS_URL`
- [ ] Production `RATE_LIMIT_USE_SIMPLIFIED` verified false when Redis is intended

### Render/network
- [ ] `PORT`
- [ ] `ALLOWED_HOSTS`
- [ ] `USER_CORS_ORIGINS`
- [ ] `ADMIN_CORS_ORIGINS`
- [ ] `BACKEND_URL`

### CI/vault bootstrap
- [ ] `INFISICAL_CLIENT_ID`
- [ ] `INFISICAL_CLIENT_SECRET`
- [ ] `INFISICAL_PROJECT_ID`
- [ ] GitHub `GITHUB_TOKEN`/appropriate workflow permissions

## GOOD-TO-HAVE / recommended

- [ ] `SENTRY_DSN`
- [ ] `SENTRY_AUTH_TOKEN`
- [ ] `CI_WEBHOOK_SECRET`
- [ ] structured notification credentials
- [ ] provider quota/cost controls
- [ ] backup/DR credentials
- [ ] Render service ID registry
- [ ] Cloudflare account/zone metadata
- [ ] centralized configuration validation
- [ ] automatic hardcoded-value scan
- [ ] configuration drift CI gate
- [ ] secret rotation reminders

## OPTIONAL / feature-dependent

- [ ] Stripe
- [ ] SSLCommerz
- [ ] Resend
- [ ] Discord
- [ ] Slack
- [Telegram]
- [ ] Cloudflare Workers
- [ ] Vercel
- [ ] Netlify
- [ ] Qdrant
- [ ] Neo4j
- [ ] NATS
- [ ] GCP Pub/Sub
- [ ] OpenAI
- [ ] OpenRouter
- [ ] Gemini
- [ ] Groq
- [ ] NVIDIA
- [ ] DeepSeek
- [ ] Anthropic
- [ ] Hugging Face
- [ ] Firecrawl
- [ ] Cline
- [ ] Continue
- [ ] Aider
- [ ] Codeium
- [ ] mem0
- [ ] Graphiti
- [ ] browser-use
- [ ] E2B
- [ ] OpenHands

---

# 25. Configuration drift controls

The repository already contains a required-secret validator. Extend the process so CI checks:

```text
Code references
      ↓
.env.example
      ↓
secrets_registry.yaml
      ↓
Infisical registry
      ↓
GitHub Actions requirements
      ↓
Render requirements
      ↓
Frontend build requirements
```

For every variable:

- [ ] Exists in code
- [ ] Exists in registry
- [ ] Requiredness agrees
- [ ] Source agrees
- [ ] Fallback agrees
- [ ] Environment target agrees
- [ ] Naming agrees
- [ ] No duplicate/legacy alias without explanation
- [ ] No undocumented hardcoded equivalent

### CI failure conditions

CI should FAIL when:

- a production MUST secret is absent from the registry;
- code references an undeclared environment variable;
- a secret is classified as optional but code requires it unconditionally;
- two canonical variable names refer to the same configuration without a documented alias;
- a privileged secret falls back to a lower-privilege/user key in production;
- a secret is hardcoded in source;
- an environment-specific URL is hardcoded;
- a new third-party integration is added without registry entry.

---

# 26. Current known drift / discrepancies to resolve

These are deliberately listed as **action items**, not silently corrected.

### Render service identifiers
- [!] `RENDER_PRIMARY_SVC_ID` appears in the secret-management documentation.
- [!] `RENDER_BACKEND_SVC_ID` appears in the CI validator.
- [ ] Decide one canonical backend service-ID variable.
- [ ] Preserve aliases only when a migration requires them.

### Supabase service credential
- [!] Current code provides `SUPABASE_SERVICE_ROLE_KEY` with fallback to `SUPABASE_KEY`.
- [ ] Production should require the dedicated service-role credential for service-client paths.
- [ ] Add a startup/CI invariant.
- [ ] Verify no user Authorization token overrides the service-client authorization header.

### Rate limiter
- [!] Current `rate_limit.py` has simplified mode that can bypass Redis.
- [ ] Production configuration must explicitly use centralized Redis when Redis-backed rate limiting is intended.
- [ ] `redis_manager.get_client_async()` is the current async API; document/use the real method.

### Sentinel TLS
- [!] Do not solve the recurring TLS error by globally setting `verify=False`.
- [ ] Identify the exact endpoint being polled.
- [ ] Keep TLS verification for public HTTPS endpoints.
- [ ] Use HTTP for intentionally local HTTP endpoints.
- [ ] Use an explicit CA only when a private/custom CA is actually required.

### Health semantics
- [ ] `/live` = process liveness only.
- [ ] `/ready` = critical dependency readiness.
- [ ] `/deep` = diagnostic health.
- [ ] Render/platform health behavior must match the desired failure semantics.

### Memory / agents
- [ ] Record memory thresholds and ownership.
- [ ] Track agent heartbeat thresholds.
- [ ] Track supervisor lifecycle failures.
- [ ] Do not assume reducing one cache resolves all memory pressure.

---

# 27. Third-party onboarding checklist

Whenever a new external service is introduced:

## Discovery
- [ ] Service name
- [ ] Purpose
- [ ] Documentation URL
- [ ] API endpoint/base URL
- [ ] Required credentials
- [ ] Non-secret project/account identifiers

## Registry
- [ ] Add service to Master Inventory
- [ ] Add variables
- [ ] Mark MUST/GOOD/OPTIONAL
- [ ] Mark secret vs public config
- [ ] Set primary source
- [ ] Set fallback source
- [ ] Set precedence
- [ ] Set runtime/build-time target
- [ ] Set owner
- [ ] Set rotation requirement

## Code
- [ ] No hardcoded secret
- [ ] No hardcoded production URL
- [ ] No hardcoded provider/model selection when it should evolve
- [ ] Central config accessor
- [ ] Safe missing-key behavior

## Deployment
- [ ] Infisical entry
- [ ] Render/GitHub/etc. injection
- [ ] CI validation
- [ ] Startup validation
- [ ] Integration test
- [ ] Health check

## Operations
- [ ] Cost/quota guard
- [ ] Retry policy
- [ ] Circuit breaker where appropriate
- [ ] Failure fallback
- [ ] Rotation procedure
- [ ] Monitoring

---

# 28. Final release gate

A production release is **NOT configuration-ready** until:

- [ ] All MUST variables are verified.
- [ ] All enabled OPTIONAL integrations are verified.
- [ ] All source/fallback mappings are documented.
- [ ] All privileged credentials have dedicated sources.
- [ ] No secret is hardcoded.
- [ ] No environment-specific URL is hardcoded.
- [ ] No undocumented provider/model selection is hardcoded.
- [ ] `.env.example` matches the registry.
- [ ] `secrets_registry.yaml` matches the registry.
- [ ] CI secret validation matches the registry.
- [ ] Infisical paths match the registry.
- [ ] Render service variables match the registry.
- [ ] Frontend build variables match the registry.
- [ ] Supabase RLS access paths are verified.
- [ ] Redis path is verified.
- [ ] Health checks are verified.
- [ ] TLS verification is verified.
- [ ] Rotation dates are recorded.
- [ ] No secret values appear in Git, CI output, or logs.

---

# 29. Evidence / source notes

This registry is derived from the current repository's `.env.example`, `secrets_registry.yaml`, `SECRETS.md`, CI secret validation, current Supabase/Render troubleshooting, and the Ultimate Master Plan.

Important source-derived observations:

1. The Ultimate Master Plan states the core rule that evolving behavior/configuration should not be hardcoded.  
2. The current `.env.example` contains Supabase, Redis, Infisical, AI-provider, Firebase/GCP, frontend, and extension configuration names.  
3. The current `secrets_registry.yaml` contains a much larger set of code-scanned variables and deployment surfaces.  
4. The current CI validator has a smaller hard-coded required-secret list than the broader registry, so configuration drift prevention should be expanded.  
5. Current GitHub code has a dedicated `service_client` for backend-only Supabase operations and loads `SUPABASE_SERVICE_ROLE_KEY`, while the current route still has a client-vs-service-client conditional that must remain aligned.  
6. Current Redis management exposes `get_client_async()`; consumers should use the actual API rather than an undocumented `get_client()`.  
7. Current Render runtime issues have included Sentinel TLS failures, rate-limiter Redis fallback, and high memory/agent-heartbeat warnings; these are therefore included as verification gates.

---

# 30. Maintenance protocol

**Review frequency**
- [ ] Every production deploy
- [ ] Every new third-party integration
- [ ] Every new environment variable
- [ ] Every secret rotation
- [ ] Monthly configuration audit
- [ ] After any Render/Supabase/Infisical architecture change

**Change rule**

Do not add a new environment variable directly to code without first adding its registry entry.

Do not remove a variable from `.env.example` or `secrets_registry.yaml` until all consumers have been removed or intentionally migrated.

Do not introduce a second name for an existing setting without documenting an explicit compatibility alias and a removal date.

---

## Appendix A — Quick operational table

| Question | Check here |
|---|---|
| Which external services do we use? | §4 |
| Where is a secret stored? | §3 + service section |
| Can a secret come from two sources? | §3.2 + per-variable table |
| What is the fallback? | Variable registry |
| Is it build-time or runtime? | Variable registry |
| Is it actually required? | §24 |
| Is something still hardcoded? | §20–21 |
| Are code and docs drifting? | §26 |
| What must CI validate? | §25 |
| What must be checked before production? | §28 |

---

**Owner:** SupremeAI engineering / DevOps  
**Classification:** Internal operational configuration documentation  
**Rule:** Record names and metadata, never secret values.