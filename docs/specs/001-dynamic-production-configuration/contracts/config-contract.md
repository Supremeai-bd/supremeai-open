# Interface Contract — Canonical Configuration Keys

Feature: 001-dynamic-production-configuration · Date: 2026-08-29
Audience: developers, operators, AI agents. **Names only — never commit values.**

Legend — Class: R=required, O=optional, C=conditional, S=secret, P=public ·
Scope: B=backend service, F=frontend build, D=deploy-time · Source: env / vault (Infisical) / build / deploy

## Service locations

| Key | Class | Scope | Source | Consumers | Notes / legacy aliases |
|---|---|---|---|---|---|
| `SUPREMEAI_USER_BACKEND_URL` | R | B,D | env | portal rewrites, topology, /config/public | canonical main-backend location |
| `SUPREMEAI_ADMIN_BACKEND_URL` | R | B,D | env | admin surface, health aggregation | |
| `SCRAPER_URL` | O | B | env | health aggregation, topology, admin tooling | absent ⇒ `not_configured` |
| `ADMIN_URL` | O† | B | env | health aggregation, topology | † required when admin aggregation enabled |
| `CHECKOUT_BASE_URL` | C | B | env | billing touchpoints | required when billing enabled |
| `RENDER_SERVICE_NAME` | C | B | env (Render-injected) | config_validation derivation | fallback location derivation |

## CORS & host policy (single source: `backend/middleware/cors_policy.py`)

| Key | Class | Scope | Source | Consumers | Notes / legacy aliases |
|---|---|---|---|---|---|
| `CORS_ORIGINS` | R | B | env (JSON or CSV list) | user portal API | legacy alias: `USER_CORS_ORIGINS` |
| `ADMIN_CORS_ORIGINS` | R | B | env (JSON or CSV list) | admin portal API | |
| `ALLOWED_ORIGINS` | R(legacy) | B | env | legacy server.py wiring | maps to the two canonical keys; deprecated |
| `ALLOWED_HOSTS` | R | B | env (list) | host-header validation | `onrender.com` bare placeholder rejected |

## Frontend build & deploy-time

| Key | Class | Scope | Source | Consumers | Notes / legacy aliases |
|---|---|---|---|---|---|
| `VITE_USER_BACKEND` | R | F | build | `utils/api.ts` user portal | alias: `VITE_API_URL` |
| `VITE_ADMIN_BACKEND` | C | F | build | `utils/api.ts` admin portal | required when `VITE_PORTAL_TYPE=admin` |
| `VITE_SCRAPER_BACKEND` | O | F | build | admin tooling views | absent ⇒ not-configured UI state |
| `VITE_PORTAL_TYPE` | R | F | build | portal selection | values: `user` \| `admin`; unknown ⇒ default+warning |
| `VITE_USE_RELATIVE_PATH` | O | F | build | `utils/api.ts` | hosting-dependent |
| `VITE_WS_BASE_URL` | O | F | build | websocket bridge | derived from backend URL when absent |
| `VITE_FIREBASE_API_KEY` | R(P) | F | build | `firebase.ts` | public-by-design, required in prod |
| `VITE_FIREBASE_AUTH_DOMAIN` … `VITE_FIREBASE_APP_ID` | R(P) | F | build | `firebase.ts` | complete set required in prod; no fake defaults |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | R(P) | F | build | supabase client | public anon values |
| `{{USER_BACKEND_URL}}` | R | D | deploy | `firebase.template.json` rewrites | unsubstituted ⇒ deploy fails |

## Secrets & optional integrations (values never in repo/specs)

| Key | Class | Scope | Source |
|---|---|---|---|
| `SUPABASE_DATABASE_URL_POOLER`, `SUPABASE_DB_CA_CERT` | S / C-S | B | vault |
| `REDIS_URL` | O-S | B | vault — absent ⇒ cache disabled |
| `OLLAMA_URL` | O-C | B | env — user-local; never a backend dependency |
| `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `DEEPSEEK_API_KEY`, `HF_API_KEY`, `NVIDIA_API_KEY` | O-S | B | vault — absent ⇒ provider `not_configured` |
| `FIREBASE_SERVICE_ACCOUNT_JSON`, `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, `N8N_WEBHOOK_SECRET`, JWT/encryption keys | R-S / C-S | B | vault |

**Contract rules**: (1) canonical name wins over alias + deprecation warning;
(2) missing `required`/`required-when-conditional` in production ⇒ boot abort
naming every missing key; (3) missing optional ⇒ `not_configured` status, never
failure; (4) secret values are structurally masked in reports/logs.
