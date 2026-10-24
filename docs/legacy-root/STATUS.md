# SupremeAI System Status (Single Source of Truth)

**Last Updated:** 2026-09-25 (issue #1133 documentation-truth reconciliation: verification snapshot re-derived from current machine proof; stale skip-registry counts reconciled — 96→26 active markers after the #1097 re-triage; volatile run-IDs replaced with evidence-stream pointers per the honesty contract. Previous round 2026-09-19: AI decoupling, Issue #466 — vendor-agnostic AI resource pool `$0..N` shipped across backend + MCP control plane.)

<!-- STATUS-PROOF:CHECK (machine-verified claims — scripts/ci/generate_status_proof.py
     fails CI when any value below drifts from tree reality. Only tree-checkable
     facts belong here; runtime/live claims must cite their evidence source.)
missions_tests=62
frontend_test_files=112
frontend_e2e_specs=4
registered_routes=761
-->

> লাইভ প্রমাণ (প্রতিটি দাবি generator-এর সাথে tree-বিরুদ্ধে যাচাইকৃত, প্রতি CI রানে auto-regen + diff-gate): [`docs/generated/STATUS_PROOF.md`](docs/generated/STATUS_PROOF.md) — এখানকার দাবি হাতে লেখা নয়, মেশিন-চেকড।
> Runtime/live প্রমাণ (CI run ফলাফল, production probe) ইচ্ছাকৃতভাবে কমিট করা হয় না — সেগুলো Actions run summary-তে থাকে; ভোলাটাইল ডেটা কমিট করলে diff-gate নিজেই অর্থহীন হয়ে যেত (false assurance by design)।

`STATUS.md` is the canonical summary. Current unresolved work and session handoff remain in `CHECKPOINT.md`; dated audit reports are historical evidence only.

## Current Verification Snapshot (refreshed 2026-09-25)

Tree-derived counts are machine-verified every CI run (`STATUS-PROOF:CHECK` block above;
cross-document consistency enforced for the skip-registry and checkpoint — see
[`docs/generated/STATUS_PROOF.md`](docs/generated/STATUS_PROOF.md)).

- Backend mission suite: **62/62 PASS** (reliability/failure-mode missions, `backend/tests/missions/`)
- Frontend unit tests: **PASS (112 test files)** — vitest (count machine-verified via STATUS-PROOF)
- Frontend typecheck: PASS (tsc --noEmit, 0 errors)
- Backend lint: PASS (ruff format + check — enforced CI gate)
- Coverage gates (thresholds in `ci.yml`): min backend 30%, min frontend 16%
- Registered routes: **761** (route inventory, generator-diff gated)
- Skip inventory: **27 applied skip-marker sites / 24 files** (AST recount 2026-09-25, machine-enforced — [`docs/SKIPPED_TESTS.md`](docs/SKIPPED_TESTS.md))
- CI Pipeline verdict + deploy results: **live in Actions run summaries** (volatile by design — not committed here; the latest run on `main` is the evidence stream)
- Production API liveness / customer chain: historical first verification 2026-09-18 (see 🚦 section below); the continuous evidence stream is the daily `QA — Live Production Smoke` run summaries

---

## 📊 Quick System Matrix

Status legend: ✅ = CI-verified on main · 🟡 = configured in tree, **live-unverified** (no automated evidence yet) · ❌ = known broken. No 🟢 is granted without evidence — the all-green matrix previously shown here was false assurance (V10 audit, 2026-09-17).

| Component | Status | Target / Runtime | Evidence status |
|---|---|---|---|
| **Backend Core** | ✅ Deployed + runtime-probed | FastAPI (Python 3.11, Async SQLAlchemy 2.0) | Deploy 6/6 SUCCESS (run 35288524158); **live-probed 2026-09-18**: health live/ready 200 direct + CORS-verified browser path |
| **Async Worker** | 🟡 Deployed, runtime-unprobed | Background Celery/HTTP (`worker_service.py`) | Deploy job SUCCESS 2026-09-17; runtime probe pending |
| **Browser Scraper** | ✅ Deployed + service-alive probed | Headless Browser Automation | Deploy SUCCESS 2026-09-17; service responds live (direct probe 2026-09-18 — route-404 body proves process alive; app-route liveness pending) |
| **MCP Control Tower** | 🟡 Deployed, runtime-unprobed | Node.js MCP Server | Build + Deploy job SUCCESS 2026-09-17; runtime probe pending |
| **Edge Router / Keepalive** | 🟡 Deployed, runtime-unprobed | Cloudflare Worker | `wrangler deploy` SUCCESS 2026-09-17; worker-level probe not yet in smoke chain |
| **LLM Gateway** | ✅ Verified in tests | Provider-Agnostic fallback chain | provider failover mission (partial-failure → fallback) in mission suite |
| **AutoHealer Service** | ✅ Verified in tests | Lifespan background loop | covered by backend test shards |
| **Database Pool** | 🟡 Live-verified schema only | PostgreSQL / Supabase + PgBouncer | **DB Schema Contract Check SUCCESS against live production DB 2026-09-17** — strongest live evidence so far; query-path liveness still unprobed |
| **Health Monitor** | ✅ Verified in tests | `scripts/health/check_system_health.py` | unit-covered |
| **Frontend UI** | ✅ Deployed + runtime-probed | React 19 + Vite 7 | build + vitest 532 + tsc green; Firebase deploy SUCCESS; **live-probed 2026-09-18**: SPA 200 + CORS-verified direct API call (live smoke Layer A) |
| **Thin Clients** | 🟡 Tree-only | Desktop (Tauri/Electron) & VS Code Ext | build gates only; no runtime evidence |

---

## 🚦 Deployment & Live Verification (honest state, 2026-09-18)

**The production chain ran for the first time in repo history on 2026-09-17 (run 35286772422 / 35288524158) — and on 2026-09-18 the live path was actually verified, catching a real production breakage in the process:**

- `Production Deploy`: **ALL SIX deploy jobs SUCCESS** — Core, Worker, Scraper, MCP (Render), Cloudflare Worker (`wrangler deploy`), and **DB Schema Contract Check against the live production database**. Render credentials are real; the schema contract matches production.

**2026-09-18 live incident — found by the daily smoke's first real probe; two layers of fiction removed:**

1. **Symptom:** every `/api/*` request through the frontend origins (`supremeai-a.web.app`, `supremeai-admin.web.app`) returned Firebase's HTML 404 page, while the Render core service answered health probes 200/200 when probed directly. The SPA fallback rewrite worked, proving the rewrites section was deployed — so the `/api/**` rewrite "worked as configured" but proxied nothing.
2. **Root cause (deeper than the first diagnosis):** Firebase Hosting rewrites **cannot proxy to external origins at all** — official docs define rewrite `destination` as *"a local file that must exist"* (dynamic backends are `function`/`run`/`dynamicLinks` blocks only). The same-origin API-rewrite layer in `firebase.template.json` was therefore an impossible architecture — a lying artifact that looked configured and did nothing. The repo's own `frontend/src/utils/api.ts` comment already documented the truth: *"Firebase hosting external rewrite proxy সাপোর্ট করে না, তাই Firebase-এ সরাসরি backend URL ব্যবহার হয় (CORS allow)"* — the SPA calls the API origin **directly with CORS**, and that path was live and healthy the whole time (CORS preflight + credentialed GET verified against production: `access-control-allow-origin: https://supremeai-a.web.app`, health 200).
3. **Fixes (wire-or-delete applied):** (a) the three impossible `/api` rewrites were deleted from `firebase.template.json` (both sites); (b) `generate_firebase_config.py`'s contract was replaced — SPA fallback required, any absolute-URL rewrite destination now **fails closed** (mis-pointed `BACKEND_URL` hosting-domain guard kept); (c) the daily smoke probes the **true browser path** — SPA load + CORS-verified direct API call with the UI origin — plus direct API probes, each row with provenance; (d) the `BACKEND_URL` secret was corrected to the verified Render core URL as hygiene (its only prior use fed the dead rewrite layer).

**What exists now (verification stack):**

- `qa-live-smoke.yml` — **QA — Live Production Smoke**: scheduled (daily 03:15 UTC) + `workflow_dispatch`. **Two-layer, zero-hardcode, fail-closed**: Layer A probes the customer chain exactly as a browser does — SPA load from the UI origin, then a direct API call carrying `Origin: <UI origin>`, asserting 200 JSON **and** `access-control-allow-origin` (a 200 without the CORS header is a browser-blocked path = FAIL); Layer B probes the API directly (`health/live`, `health/ready`, `billing plans` contract — 200 dict-shape, or 401 when the middleware honestly gates it). Every row prints its origin's provenance; target resolution order: `vars.PRODUCTION_URL || secrets.PRODUCTION_URL` → `FIREBASE_PROJECT_ID`-derived `.web.app` → Infisical `RENDER_CORE_URL`. Nothing resolvable = loud UNVERIFIED red. Cold-start honest: 2 attempts with transparent retry notes.
- `09-post-deploy-smoke.yml` — **QA — Post-Deploy Smoke** (Playwright guest canary): wired to real deploys; targets the FRONTEND surface (`secrets.FRONTEND_PRODUCTION_URL`, delivered 2026-09-19 = Firebase Hosting production) with an explicit backend `PRODUCTION_URL/api/v1/health` probe step — both surfaces verified, neither hidden. Missing both URLs → loud UNVERIFIED (not silent pass); configured + failing → hard red (first live run 35416603301 honestly exposed the backend-root URL contract bug; fixed + verified green live in 35417949822).
- Smart Pipeline Summary prints a **Deployment Truth block**: per-component result (docker/mcp/production/canary/staging) and explicit UNVERIFIED statements for anything skipped.
- `docs/generated/STATUS_PROOF.md` — machine-checked claims, diff-gated in CI (documentation truthfulness enforced).

**Owner actions remaining (all optional now that the live path lights itself from existing config):**

1. Optional: set `vars.PRODUCTION_URL` (repository variable → outside the 100-secret cap) to override the smoke/canary target resolution explicitly.
2. Optional: stand up staging service, then set `vars.STAGING_ENABLED=true` + `RENDER_STAGING_SERVICE_ID` + `STAGING_BASE_URL`.

---

## 🔒 Security & Secrets Status
- **Gitleaks / CI Secret Guard:** Active (CI-verified).
- **Webhook auth:** fail-closed trio (telegram / pr_review / ci_dashboard) + `/webhooks_ai` secret-token gate — V10 Wave-1, mission-tested.
- **Service Account Secrets:** Redacted from docs; production secrets loaded strictly via Infisical / runtime envs.
- **Secret cap note:** repo secrets at 100/100 (free-tier cap) — new config must use repository **variables** or environment secrets.

---

## 🎯 Current Engineering Milestones & Open Tasks

### ✅ Completed Milestones (recent, evidence-linked)

24. **Vendor-agnostic AI decoupling (2026-09-19, Issue #466):** the codebase no longer assumes any specific AI vendor key. Central ModelRouter resolves a dynamic `$0..N` provider pool (14 providers: Gemini, OpenRouter, OpenAI, Mistral, Groq, Anthropic, DeepSeek, Cohere, Bynara, BAI, Together, HF, Nvidia, Ollama); N=0 yields honest graceful responses everywhere (voice STT, router, telegram bot, MCP analyze) instead of crashes. Voice STT gained a real provider-error auto-switch cascade (Groq→OpenAI→Gemini→HF); vault-backed lazy key properties added for Mistral/Anthropic/Cohere/Together; `config_secrets` no longer warns on missing AI keys at boot. 3 latent runtime defects fixed in review (`NameError` in model_router, missing `get_voice_service` singleton factory, pytest network-hang guard). Evidence: 40 passed/4 skipped (7 suites incl. `test_dynamic_zero_key_resilience.py` with 6 new tests), CI lint gates green, `tsc --noEmit` clean.

23. **Live production path verified (2026-09-18):** the daily smoke's first real probe caught two layers of fiction — a same-origin rewrite layer that Firebase Hosting can never proxy (official docs + the repo's own `api.ts` comment), and a `BACKEND_URL` secret pointing at a hosting domain. Dead rewrites deleted (wire-or-delete), generator contract replaced (external-URL destinations fail-closed), `BACKEND_URL` corrected with a verified value, and the smoke upgraded to probe the true browser path (SPA + CORS-verified direct API call) with provenance. Live verdict: **PASS** — SPA 200, CORS allow-origin verified, health live/ready 200, billing plans honestly auth-gated. The "সবচেয়ে বড় gap" is closed with evidence, not claims.

22. **V10 four-wave cycle (2026-09-17):** Wave-1 security — webhook fail-closed trio + honest admin `/metrics` (null-guarded consumers); Wave-2 honesty — `manualChunks` revived (main chunk 862→391 KB, −54.6%), dead deps + lying artifacts removed, blocking `pnpm audit`, `pip-audit || true` removed, VulnerabilityProphet fake-green job deleted; Wave-3 UX/perf — billing `/api/v1`→`/api` 404 fix with dict-shape contract + 4 lock tests, 42-route crash isolation (`RouteBoundary`), 3 dead ErrorBoundary files removed, `useListResource` migration, knowledge-search mtime cache, `count(*)` memory stats, bounded conversations, async ffmpeg subprocess; Wave-4 moat — CI Doctor generalized to 8 scheduled/triggered workflows, 4 new failure-mode missions (57→62).
21. **PR Guardian v1 (2026-09-16):** improvement-only merge automation in MCP Control Tower (`test:guardian` 44/44); Tier-3 blast radius can never auto-merge. Plan: `docs/plans/PR_GUARDIAN_ANALYSIS_PLAN.md` §13.

### ⏳ High-Priority Pending Tasks
- Worker/Scraper/MCP/Cloudflare runtime liveness probes in the daily smoke (Layer B currently covers the core API; per-service probes are the next increment).
- Plans governance residual: ~586 lint error-level findings (mostly MASTER_PLAN_CANONICAL supersedes-lineage links) — batch-fix pending.
- Frontend hygiene: `: any` reduction and dead-file sweep pending.
- Zero-hardcoded doctrine enforcement ongoing (fake metric fallbacks removed in V5/V10).
- Owner decisions parked: dompurify/qs patch upgrades; `performance-check`/`churn-analysis` AI-agent `|| true` jobs in maintenance.yml; annotated `|| true` in slack/ci_policy/knip.

---

## 📑 Governance & Principles
- **Documentation truthfulness:** every machine-checkable claim above is diff-gated via `docs/generated/STATUS_PROOF.md`; unverifiable claims must cite their evidence source or be marked 🟡.
- **False-Assurance doctrine:** no silent fake fallbacks/fake data/fake green; every `except` carries a Bengali comment + log; fail-closed is the default auth posture.
- **Zero Infrastructure Cost:** architecture optimized for free-tier resilience without paid vendor lock-in.
