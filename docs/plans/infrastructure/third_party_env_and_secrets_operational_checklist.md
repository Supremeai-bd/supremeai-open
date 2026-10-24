---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:third_party_env_and_secrets_operational_checklist
subject: SupremeAI — Third-Party Services & Environment / Secret Checklist
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI — Third-Party Services & Environment / Secret Checklist

**Purpose:** A single operational checklist for tracking every external/third-party service used by SupremeAI, which environment variables/secrets belong to each service, what is required vs optional, and what still needs to be verified in production.

**Repository basis:** `SaifulHaqueNiloy/supremeai` — current `main` branch and repository secret/config documents were inspected on **2026-08-29**.

**Important:** This document tracks **configuration inventory**, not the actual secret values. Secret values must never be committed to GitHub or stored in this checklist.

---

## 0. How to use this checklist

Use one row per service and check it separately for each deployment surface:

- [ ] GitHub Actions
- [ ] Infisical vault
- [ ] Render backend
- [ ] Render admin / other Render services
- [ ] Firebase / GCP
- [ ] Vercel / Netlify
- [ ] Local development

For each secret, use this operational state:

- **PRESENT** — confirmed to exist in the intended secret store/environment.
- **MISSING** — required but not present.
- **OPTIONAL** — only needed when the corresponding feature/deployment is enabled.
- **NOT REQUIRED** — deliberately not configured for this environment.
- **VERIFY** — code/documentation says it may be needed, but live presence has not been verified.
- **DEPRECATED** — legacy alias; do not add for new deployments unless compatibility requires it.

### Security rules

- Never put actual secret values in this file.
- Never put production secrets in `.env.example`.
- Prefer one canonical secret name per provider; keep aliases only for migration/compatibility.
- CI bootstrap credentials must be isolated from application runtime credentials.
- Backend-only credentials (for example Supabase service-role keys) must never reach browser/mobile builds.
- For every new third-party integration, add the provider, secret names, requiredness, deployment target, and verification test to this file before enabling the feature.

---

# 1. Master Third-Party Service Inventory

The following services/infrastructure are explicitly represented in the current repository configuration, secret registry, deployment documents, source code, or integration configuration.

## A. Core platform / hosting / CI

### 1. GitHub
**Purpose:** Source control, GitHub API, repository operations, CI/CD workflows, repository mirroring.

**Secrets / env:**
- `GITHUB_TOKEN` — GitHub Actions normally provides this automatically.
- `GITHUB_API_TOKEN` — explicit GitHub API credential used by CI/tooling.
- `GH_TOKEN` — CI/tooling fallback alias.
- `GITHUB_CLIENT_ID` — GitHub OAuth/App integration.
- `GITHUB_CLIENT_SECRET` — GitHub OAuth/App secret.
- `MIRROR_REPO_TOKEN` — repository mirror sync.
- `STAGING_REPO_TOKEN` — staging repository sync.

**Operational priority:** `GITHUB_TOKEN` automatic; API/OAuth tokens are feature/deployment dependent.

### 2. Render
**Purpose:** Backend hosting and deployment automation.

**Secrets / env:**
- `RENDER_API_KEY`
- `RENDER_PRIMARY_SVC_ID`
- `RENDER_BACKEND_SVC_ID`
- `RENDER_API_KEY_BACKUP` — optional backup service.
- `RENDER_DEPLOY_HOOK_URL` — optional webhook deploy path.

**Operational priority:** Render runtime service does not normally need its own Render API key; deployment automation does.

### 3. GitHub Actions
**Purpose:** CI/CD, automated deploys, secret validation, maintenance workflows.

**Bootstrap credentials:**
- `INFISICAL_CLIENT_ID`
- `INFISICAL_CLIENT_SECRET`
- `INFISICAL_PROJECT_ID`
- optional legacy `INFISICAL_TOKEN`

**Deploy credentials used by workflows:** see Render / Cloudflare / Firebase / Vercel / Netlify / Sentry sections.

---

# 2. Secret Management

### 4. Infisical
**Purpose:** Central secret vault and secret distribution.

**Secrets / env:**
- `INFISICAL_CLIENT_ID`
- `INFISICAL_CLIENT_SECRET`
- `INFISICAL_PROJECT_ID`
- `INFISICAL_TOKEN` — legacy/optional fallback

**Important architecture:**
- `/github-actions` path → CI/CD bootstrap/deploy secrets only.
- `/backend` or `/render-backend` path → application runtime secrets.
- Keep these scopes separate.

---

# 3. Database / Cache / Data Infrastructure

### 5. Supabase
**Purpose:** PostgreSQL database, REST/Data API, RLS, vector/AI data, application persistence.

**Secrets / env:**
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY` — backend-only privileged Data API access.
- `SUPABASE_DATABASE_URL_POOLER`
- `SUPABASE_DATABASE_URL` — legacy/alternate connection variable; verify canonical usage.
- `SUPABASE_DB_CA_CERT` — required when explicit CA verification is used for DB TLS.

**Critical production checks:**
- [ ] `SUPABASE_SERVICE_ROLE_KEY` exists in backend runtime.
- [ ] Service-role key is never exposed to frontend/mobile.
- [ ] DB pooler URL points to the intended production project.
- [ ] CA certificate is present if the DB connector requires it.
- [ ] RLS policies are verified after every migration.

### 6. Upstash Redis / Serverless Redis
**Purpose:** Shared Redis, rate limiting, caching, task coordination, idempotency.

**Secrets / env:**
- `REDIS_URL`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`

**Critical production checks:**
- [ ] One canonical Redis connection strategy is used.
- [ ] Rate limiter is actually configured to use Redis in production.
- [ ] No accidental simplified/in-memory-only production mode.

### 7. Qdrant
**Purpose:** Vector database / semantic search.

**Secrets / env:**
- `QDRANT_URL`
- `QDRANT_API_KEY`

**Priority:** Required only when Qdrant-backed features are enabled.

### 8. NATS
**Purpose:** Messaging / event transport where enabled.

**Secrets / env:**
- `NATS_TOKEN`

**Priority:** Feature/infrastructure dependent; verify whether production currently enables NATS.

### 9. Neo4j
**Purpose:** Graph database / graph memory where enabled.

**Secrets / env:**
- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`

**Priority:** Optional unless graph features are enabled.

---

# 4. Cloud / CDN / Edge / Hosting

### 10. Cloudflare
**Purpose:** Workers, edge services, domain routing and related infrastructure.

**Secrets / env:**
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_ZONE_ID` — optional/domain-routing dependent.
- `CLOUDFLARE_WORKERS_API_TOKEN` — optional/legacy or separate worker credential.
- `CLOUDFLARE_API_KEY` — optional legacy credential; avoid for new setups.

**Critical production checks:**
- [ ] Prefer scoped API token over global API key.
- [ ] Account ID present for Wrangler/Worker deployment where required.
- [ ] Zone ID present only where zone-level actions are used.

### 11. Firebase
**Purpose:** Firebase Hosting / frontend deployment / Firebase admin integration.

**Secrets / env:**
- `FIREBASE_PROJECT_ID`
- `FIREBASE_SERVICE_ACCOUNT_JSON`
- `GCP_SA_KEY`

### 12. Google Cloud Platform (GCP)
**Purpose:** Service accounts, Secret Manager integrations, Firebase, Pub/Sub, Google Cloud APIs.

**Secrets / env:**
- `GCP_SA_KEY`
- `GCP_PROJECT_ID`
- `GCP_ACCESS_TOKEN`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_API_KEY`
- `GCP_PUBSUB_TOPIC`
- `GCP_PUBSUB_SUBSCRIPTION`

**Priority:** Depends on which GCP/Firebase functions are enabled.

### 13. Vercel
**Purpose:** Frontend deployment / optional alternate frontend.

**Secrets / env:**
- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

**Priority:** Required only if Vercel deployment remains part of the active production topology.

### 14. Netlify
**Purpose:** Alternate frontend deployment / legacy deployment path.

**Secrets / env:**
- `NETLIFY_AUTH_TOKEN`

**Priority:** Optional; mark NOT REQUIRED if the project is no longer deployed there.

---

# 5. AI / Model Providers

### 15. OpenAI
**Purpose:** LLM / AI generation.

**Secrets / env:**
- `OPENAI_API_KEY`

**Priority:** Optional provider; required when OpenAI is enabled in routing/fallback.

### 16. Google Gemini / Google AI
**Purpose:** LLM, generation, IDE/Trio integration.

**Secrets / env:**
- `GEMINI_API_KEY`
- `GOOGLE_API_KEY` — generic Google API key where applicable.

### 17. Groq
**Purpose:** Fast LLM inference.

**Secrets / env:**
- `GROQ_API_KEY`
- `GROQ_API_KEY_DEPLOYMENT_MONITOR` — deployment-monitor-specific credential.

### 18. DeepSeek
**Purpose:** LLM inference.

**Secrets / env:**
- `DEEPSEEK_API_KEY`

### 19. NVIDIA API
**Purpose:** NVIDIA-hosted AI model inference.

**Secrets / env:**
- `NVIDIA_API_KEY`

### 20. OpenRouter
**Purpose:** Multi-provider LLM gateway.

**Secrets / env:**
- `OPENROUTER_API_KEY`

### 21. Hugging Face
**Purpose:** Model hosting / inference / model artifact access.

**Secrets / env:**
- `HF_API_KEY`
- `HF_TOKEN` — CI/tooling alias.
- `HUGGINGFACE_TOKEN` — CI/tooling alias.
- `KAGGLE_API_TOKEN` and numbered variants are separate Kaggle credentials; do not confuse them with Hugging Face.

### 22. Anthropic
**Purpose:** Optional LLM provider.

**Secrets / env:**
- `ANTHROPIC_API_KEY`

**Priority:** Optional provider.

### 23. Firecrawl
**Purpose:** Web crawling / extraction.

**Secrets / env:**
- `FIRECRAWL_API_KEY`

**Priority:** Required only when Firecrawl-based tools are enabled.

### 24. E2B
**Purpose:** Sandboxed code execution where enabled.

**Repository signal:** Feature flag `e2b_enabled` / `SUPREMEAI_E2B_ENABLED` exists in configuration.

**Checklist:**
- [ ] Confirm whether an E2B API key is currently required by active code path.
- [ ] If yes, add the exact canonical key name used by the implementation.

### 25. Mem0
**Purpose:** External memory integration where enabled.

**Repository signal:** `SUPREMEAI_MEM0_ENABLED` feature flag exists.

**Checklist:**
- [ ] Confirm provider credential name from active implementation.
- [ ] Add only if feature is enabled.

### 26. Graphiti
**Purpose:** Graph-based memory / knowledge integration where enabled.

**Repository signal:** `SUPREMEAI_GRAPHITI_ENABLED` feature flag exists.

**Checklist:**
- [ ] Confirm provider credential name from active implementation.
- [ ] Add only if feature is enabled.

### 27. Browser-use
**Purpose:** Browser automation where enabled.

**Repository signal:** `SUPREMEAI_BROWSER_USE_ENABLED` feature flag exists.

**Checklist:**
- [ ] Confirm external provider/API credential requirements from the active implementation.
- [ ] Add only if enabled.

### 28. OpenHands
**Purpose:** Coding agent / external coding execution where enabled.

**Secrets / env:**
- `OPENHANDS_SERVER_URL`
- Feature flag: `SUPREMEAI_OPENHANDS_ENABLED`
- [ ] Confirm whether an additional provider API key is needed in the active implementation.

---

# 6. Payments / Billing / Customer Communication

### 29. Stripe
**Purpose:** Payments, subscriptions, billing webhooks.

**Secrets / env:**
- `STRIPE_API_KEY`
- `STRIPE_WEBHOOK_SECRET`

### 30. SSLCommerz
**Purpose:** Bangladesh payment gateway / billing webhook path.

**Checklist:**
- [ ] Identify exact production env names used by `billing`/payment implementation.
- [ ] Add merchant credentials and webhook/signature secrets here once confirmed.
- [ ] Verify sandbox vs production credentials are separated.

### 31. Resend
**Purpose:** Email delivery / notification.

**Secrets / env:**
- `RESEND_API_KEY`
- `ADMIN_NOTIFICATION_EMAIL`

### 32. Discord
**Purpose:** OTP/alerts/maintenance notifications.

**Secrets / env:**
- `DISCORD_BOT_TOKEN`
- `DISCORD_OTP_WEBHOOK_URL`
- `DISCORD_WEBHOOK_URL`
- `DISCORD_ALERT_WEBHOOK`

**Note:** These are different integration paths; verify whether all remain active before consolidating them.

### 33. Slack
**Purpose:** CI/maintenance/failure notifications.

**Secrets / env:**
- `SLACK_WEBHOOK_URL`
- `SLACK_BOT_TOKEN`

**Priority:** Optional notification service.

### 34. Telegram
**Purpose:** Admin/operational notifications where enabled.

**Secrets / env:**
- `TELEGRAM_BOT_TOKEN`
- `ADMIN_TELEGRAM_CHAT_ID`

---

# 7. Observability / Error Tracking

### 35. Sentry
**Purpose:** Application error monitoring and release/sourcemap tracking.

**Runtime secret:**
- `SENTRY_DSN`

**CI/deployment secret:**
- `SENTRY_AUTH_TOKEN`

**Critical distinction:** DSN is runtime config; auth token is CI/release credential.

### 36. Langfuse
**Purpose:** LLM observability / tracing.

**Secrets / env:**
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

---

# 8. Development / IDE / Automation Services

### 37. Kilo Code
**Purpose:** IDE reviewer / Trio pipeline stage.

**Repository config:**
- `TRIO_KILO_EXTENSION_ID=kilocode.kilo-code`

**Secret:**
- No canonical backend secret was conclusively identified in the current `.env.example`; verify extension-local auth/storage before adding one.

### 38. Cline
**Purpose:** IDE checker / Trio pipeline stage.

**Secrets / env:**
- `CLINE_API_KEY`
- `TRIO_CLINE_EXTENSION_ID=saoudrizwan.claude-dev`

### 39. Continue.dev
**Purpose:** Optional IDE integration.

**Secrets / env:**
- `CONTINUE_API_KEY`

### 40. Codeium
**Purpose:** Optional coding assistant integration.

**Secrets / env:**
- `CODEIUM_API_KEY`

### 41. Aider
**Purpose:** Optional coding assistant integration.

**Secrets / env:**
- `AIDER_API_KEY`

### 42. Kaggle
**Purpose:** Model/data access tooling.

**Secrets / env:**
- `KAGGLE_API_TOKEN`
- `KAGGLE_API_TOKEN_1` … `KAGGLE_API_TOKEN_6`

**Priority:** Optional; used as model/data tooling when enabled.

### 43. n8n
**Purpose:** Workflow automation / webhook integration.

**Secrets / env:**
- `N8N_WEBHOOK_SECRET`

---

# 9. Other External Integrations Detected in Repository Configuration

### 44. Appwrite
**Purpose:** Optional application backend/service integration.

**Secrets / env:**
- `APPWRITE_API_KEY`

### 45. Generic / custom API signing
**Purpose:** Internal/third-party API authentication support.

**Secrets / env:**
- `API_KEY_SIGNING_SECRET`
- `SUPREMEAI_API_KEY`
- `SUPREMEAI_API_TOKEN`
- `API_KEY`
- `API_KEYS`
- `DASHBOARD_API_KEY`

**Action:** Consolidate these aliases where possible. Maintain a provider-by-provider ownership map to prevent configuration drift.

---

# 10. Firebase / GCP / Frontend Build Variables That Are NOT Secrets

These are important configuration values but must not automatically be treated like passwords/tokens:

- `FIREBASE_PROJECT_ID`
- `GCP_PROJECT_ID`
- `GOOGLE_CLOUD_PROJECT`
- `FRONTEND_URL`
- `ADMIN_URL`
- `BACKEND_URL`
- `APP_BASE_URL`
- `ALLOWED_HOSTS`
- `USER_CORS_ORIGINS`
- `ADMIN_CORS_ORIGINS`
- `CORS_ORIGINS`
- `VITE_API_URL`
- `VITE_ADMIN_BACKEND`
- `VITE_USER_BACKEND`
- `VITE_PORTAL_TYPE`
- `VITE_WS_BASE_URL`
- `SUPREMEAI_BACKEND_URL`
- Trio extension IDs

Still keep sensitive deployment values out of client bundles; any `VITE_*` variable is client-visible at build time.

---

# 11. Production MUST-HAVE Matrix

The following should be treated as the minimum baseline before declaring the production environment correctly provisioned.

| Service | Production credential | Status |
|---|---|---|
| Infisical | `INFISICAL_CLIENT_ID` | [ ] |
| Infisical | `INFISICAL_CLIENT_SECRET` | [ ] |
| Infisical | `INFISICAL_PROJECT_ID` | [ ] |
| Render deploy | `RENDER_API_KEY` | [ ] |
| Supabase | `SUPABASE_URL` | [ ] |
| Supabase | `SUPABASE_KEY` | [ ] |
| Supabase backend | `SUPABASE_SERVICE_ROLE_KEY` | [ ] |
| Supabase PostgreSQL | `SUPABASE_DATABASE_URL_POOLER` | [ ] |
| Supabase TLS | `SUPABASE_DB_CA_CERT` | [ ] |
| Redis | `REDIS_URL` or canonical Upstash configuration | [ ] |
| Cloudflare | `CLOUDFLARE_ACCOUNT_ID` | [ ] |
| Cloudflare | `CLOUDFLARE_API_TOKEN` | [ ] |
| Firebase/GCP | `FIREBASE_PROJECT_ID` | [ ] |
| Firebase/GCP | `GCP_SA_KEY` / service account | [ ] |
| Auth | `SUPREMEAI_JWT_SECRET` | [ ] |
| Auth | `ENCRYPTION_KEY` | [ ] |
| Admin auth | `SUPREMEAI_ADMIN_PASSWORD_HASH` | [ ] |
| API security | `API_KEY_SIGNING_SECRET` | [ ] |
| Observability | `SENTRY_DSN` | [ ] |

**Provider-specific AI/payment/integration keys should be enabled only when that provider is actually active.**

---

# 12. Good-to-Have / Feature-Dependent Matrix

| Service / Feature | Credential(s) | Status |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | [ ] |
| Gemini | `GEMINI_API_KEY` | [ ] |
| Groq | `GROQ_API_KEY` | [ ] |
| DeepSeek | `DEEPSEEK_API_KEY` | [ ] |
| NVIDIA | `NVIDIA_API_KEY` | [ ] |
| OpenRouter | `OPENROUTER_API_KEY` | [ ] |
| Hugging Face | `HF_API_KEY` | [ ] |
| Firecrawl | `FIRECRAWL_API_KEY` | [ ] |
| Anthropic | `ANTHROPIC_API_KEY` | [ ] |
| Qdrant | `QDRANT_URL`, `QDRANT_API_KEY` | [ ] |
| Neo4j | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | [ ] |
| NATS | `NATS_TOKEN` | [ ] |
| Stripe | `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` | [ ] |
| SSLCommerz | exact implementation-specific keys | [ ] |
| Resend | `RESEND_API_KEY` | [ ] |
| Discord | webhook/bot keys | [ ] |
| Slack | webhook/bot keys | [ ] |
| Telegram | bot/chat keys | [ ] |
| Sentry CI | `SENTRY_AUTH_TOKEN` | [ ] |
| Langfuse | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | [ ] |
| Vercel | `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` | [ ] |
| Netlify | `NETLIFY_AUTH_TOKEN` | [ ] |
| E2B | confirm exact active credential name | [ ] |
| Mem0 | confirm exact active credential name | [ ] |
| Graphiti | confirm exact active credential name | [ ] |
| Browser-use | confirm exact active credential name | [ ] |
| OpenHands | `OPENHANDS_SERVER_URL` + confirm auth | [ ] |
| n8n | `N8N_WEBHOOK_SECRET` | [ ] |
| Appwrite | `APPWRITE_API_KEY` | [ ] |
| Cline | `CLINE_API_KEY` | [ ] |
| Continue.dev | `CONTINUE_API_KEY` | [ ] |
| Codeium | `CODEIUM_API_KEY` | [ ] |
| Aider | `AIDER_API_KEY` | [ ] |
| Kaggle | `KAGGLE_API_TOKEN*` | [ ] |

---

# 13. CI/CD Secret Separation Checklist

## GitHub Actions — bootstrap only

- [ ] `INFISICAL_CLIENT_ID`
- [ ] `INFISICAL_CLIENT_SECRET`
- [ ] `INFISICAL_PROJECT_ID`
- [ ] `GITHUB_TOKEN` is allowed to remain GitHub-provided
- [ ] `GITHUB_API_TOKEN` only where explicitly needed
- [ ] `RENDER_API_KEY` only if deploy workflow needs direct Render API access
- [ ] `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` only for worker deployment
- [ ] `GCP_SA_KEY` / Firebase deployment credential only for frontend deploy
- [ ] `SENTRY_AUTH_TOKEN` only for release/sourcemap upload

## Render backend runtime

- [ ] Do NOT copy full GitHub Actions secret set into Render.
- [ ] Do NOT copy mobile signing secrets into backend runtime.
- [ ] Do NOT expose service-role keys to browser/mobile builds.
- [ ] Backend gets only the runtime credentials it actually uses.

---

# 14. Configuration Drift / Alias Cleanup Checklist

The repository contains several legacy or overlapping names. Before final production hardening, verify and consolidate them.

- [ ] `SUPABASE_DATABASE_URL` vs `SUPABASE_DATABASE_URL_POOLER`
- [ ] `SUPABASE_KEY` vs `SUPABASE_SERVICE_ROLE_KEY`
- [ ] `SUPREMEAI_API_KEY` vs `SUPREMEAI_API_TOKEN` vs generic `API_KEY`
- [ ] `GOOGLE_API_KEY` vs `GEMINI_API_KEY`
- [ ] `HF_API_KEY` vs `HF_TOKEN` vs `HUGGINGFACE_TOKEN`
- [ ] `CLOUDFLARE_API_TOKEN` vs `CLOUDFLARE_WORKERS_API_TOKEN` vs `CLOUDFLARE_API_KEY`
- [ ] `DISCORD_WEBHOOK_URL` vs `DISCORD_ALERT_WEBHOOK` vs `DISCORD_OTP_WEBHOOK_URL`
- [ ] `FIREBASE_SERVICE_ACCOUNT_JSON` vs `GCP_SA_KEY` vs `GOOGLE_APPLICATION_CREDENTIALS`
- [ ] `INFISICAL_TOKEN` vs client ID/secret authentication
- [ ] `VERCEL_*` and `NETLIFY_*` deploy paths: keep only active hosting provider(s)

For every alias, define:

`canonical_name → legacy alias → owner → deployment target → migration date → removal date`

---

# 15. Live Verification Checklist

## Render

- [ ] Backend service has required runtime env vars.
- [ ] No required secret is silently falling back to a weaker credential.
- [ ] Health endpoint is live.
- [ ] Readiness endpoint reflects real dependency state.
- [ ] No recurring TLS certificate errors.
- [ ] No recurring Redis fallback messages.
- [ ] No repeated Supabase RLS 42501 errors.

## Supabase

- [ ] Project is the intended production project.
- [ ] Database URL is correct.
- [ ] SSL/CA verification succeeds.
- [ ] RLS policy inventory is current.
- [ ] Service-role backend operations succeed.
- [ ] Anonymous/client operations are denied where expected.

## Infisical

- [ ] `/github-actions` and backend runtime paths are separated.
- [ ] Bootstrap credentials work.
- [ ] Backend runtime secrets resolve correctly.
- [ ] No secret values appear in logs.

## GitHub

- [ ] Actions secret validation passes.
- [ ] Deploy workflows use least-privilege credentials.
- [ ] Repository automation tokens are scoped appropriately.

## Cloudflare

- [ ] Worker deploy authentication works.
- [ ] Account ID is correct.
- [ ] Zone-level credentials are only present when needed.

## Firebase / GCP

- [ ] Service account credential works.
- [ ] Project ID is correct.
- [ ] Firebase hosting deploy succeeds.
- [ ] No client build accidentally includes private service-account data.

## AI Providers

- [ ] Active providers have valid keys.
- [ ] Inactive providers are explicitly marked disabled/not required.
- [ ] Provider keys are not hardcoded.

## Payments / Notifications

- [ ] Stripe production keys/webhook secret verified.
- [ ] SSLCommerz production credentials verified.
- [ ] Email provider verified.
- [ ] Alert channels verified.

---

# 16. Change Log

| Date | Change | Owner | Result |
|---|---|---|---|
| 2026-08-29 | Initial third-party service + env/secret inventory created from current repository state | | |
| | | | |
| | | | |

---

# 17. Source-of-Truth Notes

This checklist is based on the repository's current configuration and secret-management documentation. The repository's `.env.example` enumerates many runtime, deploy, provider, IDE and frontend variables; `SECRETS.md` defines the intended separation between GitHub Actions bootstrap secrets, Infisical vault paths, and Render runtime secrets; and `scripts/ci/check_required_secrets.py` defines a smaller set of CI-critical variables. These sources are not perfectly identical, so this document deliberately marks some entries as **VERIFY** rather than falsely treating them as confirmed production requirements.

**Current repository evidence includes:**
- `.env.example` — runtime and deployment environment inventory.
- `SECRETS.md` — GitHub Actions / Infisical / Render secret strategy.
- `secrets_registry.yaml` — code-scan secret inventory and criticality metadata.
- `scripts/ci/check_required_secrets.py` — CI pre/post deployment required-secret checks.

**Recommended next step:** make this checklist machine-readable later (for example, YAML/JSON) and have CI generate a drift report comparing code usage vs `.env.example` vs `secrets_registry.yaml` vs deployment environments.