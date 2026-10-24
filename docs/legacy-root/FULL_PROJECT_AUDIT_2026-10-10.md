# SupremeAI — সম্পূর্ণ প্রজেক্ট অডিট রিপোর্ট (বাংলা)

**সংস্করণ:** v1 (২০২৬-১০-০৯ ~১৯:২৪ UTC) → **recheck #1** (~১৯:৫২ UTC, ৫২ কমিট ডেল্টা) → **recheck #2** (~১৯:৫৭ UTC, Workflow Diet merge + branch-squash দেখা গেছে)
**পদ্ধতি:** git-tracked ফাইল স্ক্যান (৪,৩৩০ ফাইল) + ব্যাকএন্ড/ফ্রন্টএন্ড/স্ক্রিপ্ট-CI/ডকস-কনফিগ চার-দিকে গভীর অডিট + সরাসরি যাচাই (py_compile ×২, git ইতিহাস/reflog, CI রান, ফাইল-লাইন গণনা)

> ⚠️ **এই repo-তে concurrent agent-fleet প্রতি কয়েক মিনিটে কমিট করে।** অডিট চলাকালীন ট্রি তিনবার আলাদা অবস্থায় ছিল: (১) initial scan, (২) `coder-67-workflow-diet` ব্রাঞ্চে ৫২ কমিট, (৩) main-এ merge/reset (HEAD `53c9b1035`, ২০২৬-১০-১০ ০১:৫৭ +0600)। বিশ্লেষণ করা অডিট নোট-ফাইল একবার agent-এর `git stash -u`-তে পড়ে গিয়ে BOM-only হয়ে ছিল — concurrent ট্রিতে কাজ করার সময় এটি বাস্তব ঝুঁকি (নিচে R4)।

---

## ০. দুই রিচেকের ডেল্টা (Tree Churn Delta)

**Recheck #1 (~১৯:৫২ UTC):**

| # | আগে | পরে (যাচাইকৃত) | অবস্থা |
|---|---|---|---|
| 1 | ৪,৩৪২ ফাইল / ৮৮৯,৩৭১ লাইন | **৪,৩৩০ / ৮৮৩,০৪৭** | −১২ ফাইল, −৬,৩২৪ লাইন |
| 2 | docs .md = ১০৩ | **৯১** | ✅ আর্কাইভ অফলোড |
| 3 | ১২টি historical spec (~৬,৩০০ L) ট্রিতে | **`paykaribazaronline/supremeai-archive`-এ সরানো** (AIBRAIN-01 ২,৭৪৮ L, AIBRAIN-02 ১,৩৮৪ L, MULTI_PLATFORM ৯৪৬ L, FRONTEND_DASHBOARD_V1 ৯৪৬ L …) + ২টি legacy tarball খালি | ✅ সুপারিশ বাস্তবায়িত |
| 4 | "`backend/_archive/` git-ignored" (audit-ভাষ্য ভুল) | **ট্র্যাকড: ৫৭টি .py + MANIFEST.md** (ডিস্কে আরও ৬০টি .pyc) | ⚠️ সংশোধন |
| 5 | `frontend/dist/` tracked (১৩টি entry) | **untracked** (ডিস্কে আছে) | 🟡 আংশিক — delete বাকি |
| 6 | scripts = ৪৬৭ | **৪৭০** (নতুন `scripts/bridge/` ৫৬৬ L + README + tests, `scripts/ci/schedule_watchdog.py` ২৫৬ L) | নতুন সাবসিস্টেম |
| 7 | workflow ২২ (৪টি uncommitted) | ২২ commit + hardened (bridge-intake concurrency #66, watchdog PUT #63, schedule-watchdog #59) | ✅ |
| 8 | py_compile ১২০/১২০ | **১২০/১২০ (re-verified)** | ✅ |
| 9 | `.env.example` ৭৮৪ L (subagent মাপ) | **৬৫৭ L** (মাপ-পদ্ধতিভিন্ন; README-র ৫৪৬ উভয়ই ভুল) | 📌 |
| 10 | tracked.txt / dead-WF ×৩ / `.secrets/` / self_improving_agent / ci_summary_v2 / tmp_sync / standup_bot / delete_vault_dup / Header.tsx / knip-baseline / intent_router_v2 / missing build_import_graph | **সব অপরিবর্তিত** | ❌ open |

**Recheck #2 (~১৯:৫৭ UTC, main @ `53c9b1035`):**

| # | ঘটনা | প্রভাব |
|---|---|---|
| R1 | **PR #69 "Workflow Diet" (#67) মার্জ** | continuous-agent-loop + issue-ops → **workflow_dispatch only** (per-event Actions runs quota পুড়াচ্ছিল); nightly-ops ৩-cron → ২-tier; schedule-watchdog/code-quality/branch-guard/dependabot/dep-health/has-pr-reconciler → dispatch-only; auto-sync-upstream → daily; archive-mirror → weekly; core-5 (main/pr/merge-gate/deploy-train/bridge-intake) + smart-deploy untouched | ✅ আমার "CI-নয়েজ/সমস্যা"র বড় অংশ ঠিক হয়েছে |
| R2 | শেষ tracked অবস্থা | **৪,৩৩০ ফাইল / ৮,৮২,৯৪১ লাইন** (merge-এর পরে মাপ) | স্থির |
| R3 | ৫২ কমিট ছিল ব্রাঞ্চে, main-এ squash-merge | main = c5074f388 + d96ff8f8b (squash) | ✅ |
| R4 | **Concurrent-hygiene ঝুঁকি observed:** agent-fleet-এর merge-এর সময় `git stash -u` চালিয়ে আমার untracked রিপোর্ট ফাইল BOM-only করে দেয়েছিল (content recoverable ছিল না; পুনর্লিখন করতে হয়েছে) | যেকোনো agent-নেই collaborator হিসেবে এই repo-তে কাজ করলে: **কাজ শেষে ফাইল commit করতে হবে** অথবা temp-dir (`C:\Users\N\AppData\Local\Temp\kilo`) ব্যবহার করতে হবে | ⚠️ process finding |
| R5 | smart-deploy.yml = "Category A core" — **বরং রাখা হয়েছে**; auto-sync-pr-branches = Category E dispatch-only (revertible) | removal list সংশোধন | 📌 |

---

## ১. এক নজরে (Executive Summary)

SupremeAI একটি **governed, model-agnostic AI task-execution platform** — FastAPI ব্যাকএন্ড + React/Vite ফ্রন্টএন্ড + Next.js Mission Control + MCP Control Tower + GitHub Actions-governed autonomous agent fleet। প্রজেক্টটি **বড়, সক্রিয় ও largely সুস্থ** — কমিট গতি চরম, maintainability culture (knip, sprawl guard, silent-error baseline, STATUS-PROOF, Task Outcome Ledger, Workflow Diet) অসাধারণ, এবং সুপারিশের কিছু **সত্যিই বাস্তবায়িত হচ্ছে** (archive offload, dist untracked, workflow quota diet)।

কিন্তু sprawl-এর মূল গঠন অপরিবর্তিত: dead code, duplicate tool families, doc-drift ও stale artifact জমছে। নিচে ফিক্স/যোগ/সরানোর পূর্ণ তালিকা।

| মেট্রিক | মান (final, ১৯:৫৭ UTC) |
|---|---|
| Tracked files | **৪,৩৩০** |
| মোট লাইন | **৮,৮২,৯৪১** |
| Python | ২,৮৭৪ ফাইল (backend .py ২,১৯৮) |
| TypeScript/TSX | ৮৫০ ফাইল |
| Markdown | ৮৯ ফাইল |
| GitHub workflows | ২২ — কিন্তু এখন scheduled-run সংখ্যা অনেক কম (diet) |
| শেষ কমিট | `53c9b1035` (merge) — ২০২৬-১০-১০ ০১:৫৭ +0600 |
| Remote branches | ৩৩ · Stashes | ১১ |

---

## ২. প্রজেক্টের বর্তমান মাপ (Scale)

| এলাকা | ফাইল | মন্তব্য |
|---|---|---|
| `backend/` | ২,২৮১ tracked · .py ২,১৯৮ | ~৩.৮ লাখ LOC (অনুমিত); `tests/` ৭২১ টেস্ট ফাইল; `_archive/` ৫৭ .py tracked |
| `frontend/src` | ৫০০ TS/TSX · ৫২,৮০৮ লাইন | React 19 + Vite 7; ১২২ unit + ৪ e2e |
| `apps/mission-control` | ১০০ ফাইল · ~১৪,৪০০ লাইন | Next.js 16.3.8; test=০ |
| `apps/docs`, `packages/` (৬৮), `client/` (১১), `tools/vscode-extension` (৪৮) | — | packages ≈২,৯০০ লাইন TS |
| `scripts/` | ৪৭০ ফাইল · ~১,৩৩,০০০ লাইন | `ci/` ১৩৬+; নতুন `bridge/` সাবসিস্টেম |
| `tools/` | ~৭,৪৫০ লাইন Python + ৪৭ TS | অনেক ১৫–৫০ লাইনের stub |
| `docs/` | ৯১ .md | `master_docs/` ১৮ ক্যানোনিকাল স্পেক |
| `.github/workflows` | ২২ yml | core-5 + nightly bundle + sync/mirror/bridge/watchdog |

---

## ৩. যাচাইকৃত সুস্থ দিক (Verified Healthy)

- ✅ **Python syntax:** ১২০টি র‍্যান্ডম ব্যাকএন্ড ফাইল `py_compile` — ১২০/১২০ ক্লিন (দুবার)
- ✅ **Secrets/Tree:** কোনো `.env`, `*.pem`, `*.key`, `credentials*.json`, `node_modules`, `__pycache__`, `dist/` tracked নয়; `frontend/dist/` এখন untracked
- ✅ **TODO/FIXME debt প্রায় শূন্য** (ব্যাকএন্ড ২, ফ্রন্টএন্ড ২) — disciplined টিমের লক্ষণ
- ✅ **Bare `except:` মাত্র ২টি** — দুটোই fixture
- ✅ **CI quota problem actively managed:** Workflow Diet #67 — per-event loops dispatch-only, nightly-ops tiered
- ✅ **Workflow consolidation (#1858) স্থিতিশীল;** নতুন ৪টি workflow commitেও hardened
- ✅ **Shell scripts:** ৩৪/৩৪ shebang, `curl | bash` শূন্য
- ✅ **Dependency security floors আধুনিক:** fastapi 0.141.1, pydantic 2.13.5, sqlalchemy 2.1.1, cryptography 50.0.1, axios 1.20.0, dompurify 3.4.16
- ✅ **Archive hygiene mobile + Task Outcome Ledger Phase 0** — evidence culture প্রমাণিত
- ✅ **Live production path verified** (STATUS.md): SPA + CORS-verified API path ডেইলি smoke-এ

---

## ৪. 🔴 CRITICAL — অতি জরুরি ফিক্স

1. **`tracked.txt` — stale false-evidence (OPEN)**
   রুটে ৪,১৬৮ লাইনের স্ন্যাপশট: ৩১টি মৃত workflow-এর নাম আছে, পুরো `scripts/agents/` ট্রি (৩৯ ফাইল) বাদ। ৫২+ কমিটের পরেও অপরিবর্তিত। repo-এর অবস্থা সম্পর্কে মিথ্যা প্রমাণ — **মুছে দিন** বা live generator দিন।

2. **লাইভ secret ফাইল ওয়ার্কিং-ট্রিতে (OPEN)**
   `.secrets/github_app.pem` (আসল RSA private key), `.secrets/encryption.key`, `.secrets/jwt_secret.key` — track হয় না (ভালো), কিন্তু `.secrets/` **ডিরেক্টরিটি `.gitignore`-এ নেই**; `secrets/`-এ আরও ৬টি GitHub App private key। **অ্যাকশন:** ডিরেক্টরি ignore; ট্রি কপি হলে rotate।

3. **Module inventory বিশৃঙ্খল + মুছে-যাওয়া "module" (OPEN)**
   "১৮৮" (MODULES_LIST + capability matrix) vs "~১৯৩" (CODEBASE_GUIDE) vs ২২৪ পর্যন্ত গণনা (FRONTEND-01)। ডিস্কে নেই: `tools/parallel_agent_executor.py`, `tools/firebase_functions_v1`, `tools/social/telegram_bot.py`, **`backend/services/llm/` (০টি .py — recheck নিশ্চিত)**, `frontend/src/store/chatStore.ts|themeStore.ts|useSupremeStore.ts`, `backend/tools/ensemble_router.py`, `infrastructure/kubernetes`। stale `.pyc` import-failure লুকোাতে পারে।

4. **নিরাপত্তা early-warning control silent death (OPEN)**
   `scripts/maintenance/check_infisical_vault_synth.py` (১২৩ L) কেউ চালায় না; doc বলে daily maintenance.yml-এ। **nightly-ops-এ re-wire করুন।**

5. **Mega-files (OPEN)**
   `config_classification.py` ২,৫০৫, `zero_cost_patch_phase1_4.py` ২,২৯৯, দুটি corrective migration ১,৯৩০/১,৮৪৯, `supabase_client.py` ১,৭৬১, `mcp_github_cicd.py` ১,৪৯৪, `memory/mcp_server.py` ১,২৯২ — ১৩+ ফাইল ১০০০+ লাইন।

---

## ৫. 🟠 HIGH — উচ্চ অগ্রাধিকার

6. **`backend/_archive/` — ট্র্যাকড dead duplicate**
   ৫৭টি shim .py + MANIFEST.md git-এ **tracked** — live module-এর dead duplicate (`orchestrator`, `capability_registry`, `task_engine`, `billing_plans`, `logging`, `idempotency_middleware`, `pgbouncer_pool`…) + ডিস্কে ৬০টি stale `.pyc`। সঙ্গে `self_improving_agent.py` (৪৪৭ L, "DO NOT WIRE"), `agents/autonomous_agent.py` (১৩ L facade), `core/agents/legacy/`।

7. **Frontend dead code baselined, removed নয়** — knip-baseline: ১৮ unused ফাইল / ৮৩ unused export / ৪৮ duplicate export / ১০ unused dep; `Header.tsx` (২১৩ L) শুধু নিজের টেস্ট, `useIdeStore.ts` (৮১), `stateOwnership.ts` (১৭), `components/customer/index.ts` (৭), `WorkspaceSkeleton` — সব অপরিবর্তিত।

8. **দুটি সমান্তরাল admin UI** — `components/admin/*` (৬৩ ফাইল, ৯,২৫৬ L) vs `commandcenter/modules/*`; ১০টি same-named component জোড়া (CommandBar, CommandPalette, ConfigEditor, HealthMap, LiveLogs, ModelRouter, CostAuditor, Skeleton, EmptyState, Badge + AgentNode ×২)।

9. **দুটি জীবিত MCP server** — `memory/mcp_server.py` (১,২৯২) vs `tools/mcp/mcp_server.py` (৬৩৮)।

10. **Tracked build/test artifact — ১টি সংশোধন**
    ✅ `frontend/dist/` + `test-results/` untracked
    ❌ বাকি: `infrastructure/vitest-report.json`, `backend/ci-reports/test.json`, `reports/*.json` (৫টি), `docs/plans/SupremeAI_Action_Plan_Visual.png`।

11. **Doc-drift**
    ✅ অনেক broken link archive offload-এ গেছে
    ❌ বাকি: workflow-name reference (~২৬টি মৃত নাম: CODEBASE_GUIDE-তে ১৩টি কার্ড, SECURITY_CONTROLS_BASELINE দাবি `ci.yml`-কে, ARCH-02-তে never-existed `system-gates.yml`), CONTRIBUTING.md ভুল (requirements.txt নেই, npm vs pnpm, Node 18 vs 24), README ".env.example ৫৪৬ L" (আসল ৬৫৭ L)।

12. **`apps/mission-control`-এ typecheck/test নেই; `noImplicitAny: false`** — ১০০ ফাইল/~১৪,৪০০ L; `packages/*` test=০; `frontend/e2e/*.spec.ts` tsconfig-এর বাইরে; root `test:e2e` পাথ ভুল; `App.routes.test.tsx:75` stale mock।

13. **Dependency split** — lucide-react 0.525 vs 1.34, recharts 2 vs 3, resizable-panels 3 vs 4; `vite` override 7.3.5 < frontend ^7.3.6; `next-auth@4.24.15` on next 16.3.8 (EOL v4)।

14. **`pnpm-workspace.yaml` dead overrides** — lock-এ `valibot@1.2.0` (ডিক্লেয়ার করা >=1.4.2-এর নিচে)।

15. **৪৪টি dormant backend module** (most `backend/tools/**`) + ৫–৬টি fully-skipped টেস্ট মডিউল (`test_api_bootstrap.py` সহ) + baseline ~৮,৪০০ টেস্টে ১৭ failed + ২ collection-error।

16. **Coverage config স্ব-বিরোধী** — `source` ৫টি dir, `addopts` শুধু `--cov=core`।

17. **Shell strict-mode অনুশীলন নেই** — `superai_quick_deploy.sh` (৮৩১ L) শুধু `set -e`; shellcheck gate নেই; `run_task.sh:28` eval; `atomic_claim.sh:447` unquoted loop; `setup_kms.sh` plaintext key print।

18. **`main.yml` "Artifact Auto-Regen" no-op** — `build_import_graph.py` ও `update_module_capability_matrix.py` নেই (guarded skip)।

19. **Duplicate script families** — secret-deleter ×২ (৯৫% identical), `.github/scripts/` orphan ~২,২৭০ L (ci_summary_v2 ১,৩৮০ + supreme_ci + ci_smart_summary + ci_error_report; workflow ref শূন্য), dead-code ×৩, secret-rot ×৪, api-contract ×৩, smoke ×৫, benchmark ×৪, health ×৩, audit ×৫; `create_issue.py` দুই package-তে; mega `smart_priority_merger.py` ১,৯০২ + `continuous_agent_loop.py` ১,৯৩৫ — diet-এর পরেও locally চলছে (dispatch-only), তাই sprawl open।

20. **Basename collisions** — `agent_departments.py` ×২ + typo `agent_department.py`; `agent_registry.py` ×৩; `mcp_server.py` ×২; `context/` vs `context_engine/`; `get_db()` দুই রূপ।

21. **`core/logging_config.py` deprecated shim ~২৫টি module-এ import** — deprecation অসম্প্ল।

22. **Workflow Diet-এর পরের নতুন জায়গা:** auto-trigger বন্ধ হওয়ায় bridge-intake-এর বাইরে কোনো scheduled safety-net নেই; watchdog re-arm logic-এর উপর নির্ভরশীলতা বেড়েছে — watchdog ফেল করলে কীই ঘটবে তার runbook নেই।

---

## ৬. 🟡 MEDIUM (recheck-যাচাইকৃত)

23. `scripts/tools/` git-ignored কিন্তু doc দৃশ্যমান (৫টি ফাইল CI-এর জন্য অদৃশ্য)।
24. Tight bounds: fastapi cap-এর ধারেকাছে; bespoke litellm marker।
25. `apps/docs` + `mcp-control-plane` pnpm-workspace-এর বাইরে; তিন lockfile; mcp-control-plane আলাদা সংস্করণ জগত (TS ^7, ioredis ^6)。
26. `z-ai-web-dev-sdk ^0.0.18` prod dep; `@reactuses/core` সন্দেহজনক; apps/docs floating `latest`।
27. `config/mcp-clients.json` — unsalted SHA-256 ×৭; L15=L30 (দুই client এক credential)।
28. `.gitignore` ৭৩৫ লাইনে ৪টি duplicated region + খালি `f` pattern (L299/L526)।
29. Frontend `any` ১২৩ (production ~৭৯) — `useAdminApi.ts` ৮, `adminStore.ts` ৬, `authStore.ts` ৫।
30. Oversized frontend: `dashboard-tab.tsx` ৮৮৭ (একমাত্র >৮০০), DeepResearchPanel ৬৫৪, apiClient ৬১৬।
31. Orphans (০ reference): `tmp_sync_gh_secrets.py`, `auto_daily_standup_bot.py` (self-DEPRECATED), `log_anomaly_detector.py` ৭১২, `auto_test_generator.py` ৫৯০, `test_runners.py` ১,৩৩৩।
32. `backend/tests/e2e/`-তে ০টি .py (marker mismatch)।
33. Empty package dirs: `backend/services/llm/`, `core/metrics/`, `core/config/`, `core/behavioral_intelligence/`, `config/`, `data/`, `mcp/`, `docker/`।
34. **Concurrent-workflow hazard (observed!):** fleet merge-এর সময় `git stash -u` অন্যান্য agent-এর untracked কাজ নষ্ট করেছে (আমার রিপোর্ট BOM-only হয়েছিল) — claim-guard আছে কিন্তু **untracked-file protection নেই**।
35. CHECKPOINT.md পিছিয়ে (শেষ ১২:২২ UTC; আসল শেষ ১৯:৫৭); git workflow run-note-থেকে lag ঘটছে।

---

## ৭. 🟢 LOW

- gitleaks false positive fixture `ghp_SUPERSECRET1234567890` allowlist-এ নেই।
- `scripts/duplicate_audit.txt` — ১৪,৩৬৮ লাইন noise।
- Debt register নেই (শুধু knip-baseline)।
- Storybook assets app-source-এ।
- `.env.example` line-count তিন জায়গায় তিন রকম (README ৫৪৬ / subagent ৭৮৪ / current ৬৫৭) — generator-check দরকার।

---

## ৮. ➕ যা যোগ করতে হবে (Missing / Needs Adding)

**নিরাপত্তা ও গভর্নেন্স**
1. `nightly-ops.yml`-এ **Infisical vault synthetic check** re-wire (C4)।
2. `.gitignore`-এ `.secrets/` + `secrets/`; `tracked.txt` সরিয়ে live generator।
3. Shellcheck gate + `set -euo pipefail` fixation।
4. MCP clients: salted hash + আলাদা token; systematic "doc says daily but nothing runs it" audit।
5. **Concurrent-safety:** untracked-file protection policy — agent-দের কাজ commit/stash-safe রাখার নিয়ম (R4 থেকে)।

**কোয়ালিটি গেট**
6. mission-control typecheck + test script; `noImplicitAny: true` পরিকল্পনা; packages unit-test scaffold।
7. e2e specs + playwright.config tsconfig-এ; root `test:e2e` পাথ ঠিক।
8. knip threshold enforce (new unused = fail) + baseline হ্রাস লক্ষ্য।
9. Broken-link CI checker + workflow-name reference validator।
10. সুদু唔 py_compile/`pytest --collect-only` preflight gate (৫২ কমিট/৩০ মিনিট গতিতে)।
11. একক SSOT module-inventory generator + `.env.example` line-count machine-check।

**পরীক্ষা ও নজরদারি**
12. Coverage broaden (`--cov=core,api,tools,ws,workers`)।
13. Worker/Scraper/MCP/Cloudflare runtime probes daily smoke-এ।
14. Performance-check/churn-analysis `|| true` সরানো (owner decision)।
15. Staging canary (`vars.STAGING_ENABLED=true`)।
16. Frontend API boundary type-safety (OpenAPI → TS)।
17. **Diet-পরবর্তি watchdog runbook + failure drill** (H22)।

---

## ৯. ➖ যা সরানো/মুছে ফেলা উচিত (Removal List)

| # | আইটেম | প্রমাণ / অবস্থা |
|---|---|---|
| 1 | `tracked.txt` (রুট) | stale false-evidence — OPEN |
| 2 | `backend/_archive/` ৫৭টি .py (+৬০ stale .pyc) | tracked dead duplicate |
| 3 | `adaptive_engine/self_improving_agent.py` | "DO NOT WIRE", ০ import |
| 4 | `agents/autonomous_agent.py` + `core/agents/legacy/` | ০ production import |
| 5 | `frontend/src/components/core/Header.tsx` (২১৩ L) | শুধু নিজের টেস্ট |
| 6 | `useIdeStore.ts`, `stateOwnership.ts`, `components/customer/index.ts` | টেস্ট-ছাড়া ০ ref |
| 7 | `WorkspaceSkeleton` export | টেস্ট-only |
| 8 | `frontend/dist/` + `test-results/` | ✅ untracked হয়েছে — ডিস্ক থেকে delete বাকি |
| 9 | `.github/workflows/issue-template-guard.yml` | ট্রিগার নেই — OPEN |
| 10 | `.github/workflows/auto-sync-pr-branches.yml` | Category E dispatch-only (diet-এ টিকিয়ে রাখা হয়েছে — revertible) |
| 11 | `.github/workflows/smart-deploy.yml` | ⚠️ **সংশোধন:** diet-এ এটিকে "core" ধরা হয়েছে — সরানো নয়, রক্ষা করুন |
| 12 | `.github/scripts/` orphan (ci_summary_v2 ১,৩৮০ + supreme_ci + ci_smart_summary + ci_error_report) | ০ workflow ref — OPEN |
| 13 | `delete_vault_duplicate_render_keys.py` | ৯৫% identical deleter — OPEN |
| 14 | `scripts/ci/tmp_sync_gh_secrets.py` | `tmp_` prefix — OPEN |
| 15 | `scripts/bots/auto_daily_standup_bot.py` | self-DEPRECATED — OPEN |
| 16 | `scripts/duplicate_audit.txt` | ১৪,৩৬৮ লাইন noise — OPEN |
| 17 | Duplicate families: smoke ×৫→১, benchmark ×৪→১, secret-rot ×৪→১, api-contract ×৩→১, dead-code ×৩→১, audit ×৫→১, health ×৩→১ | re-inflation ঠেকাতে |
| 18 | `core/intent_router_v2.py` + shim + `admin_v1.py` | version-leftover |
| 19 | `agent_department.py` typo | `agent_departments.py`-এর সাথে মিলিয়ে |
| 20 | `core/logging_config.py` shim | ~২৫ import migrate-এর পরে |
| 21 | `backend/services/llm/__pycache__` + empty package dirs | stale bytecode |
| 22 | `pnpm-workspace.yaml` dead `overrides:` | valibot floor enforce বা ব্লক সরান |
| 23 | ৩৩ stale remote branches + ১১ stash | CHECKPOINT-এরও pending (stash-কে যত্ন দিয়ে দেখুন — R4) |
| 24 | archive-সরানো ফাইলের stale doc links (যেমন AIBRAIN-01-এর refs) | sweeper দরকার |
| 25 | knip ৪৮ duplicate exports/aliases | যেমন `AdminBrowserPanel = CrownJewelBrowser` |

---

## ১০. যাচাইপদ্ধতির বিবৃতি (Verification Statement)

**মেশিন-প্রমাণ (তিন রাউন্ডে যাচাই):**
- `git ls-files` = ৪,৩৩০ ফাইল · ৮,৮২,৯৪১ লাইন (final main HEAD)
- তিনবার snapshট: initial ৪,৩৪২/৮৮৯,৩৭১ → recheck#১ ৪,৩৩০/৮৮৩,০৪৭ → recheck#২ ৪,৩৩০/৮,৮২,৯৪১
- `py_compile` — ১২০/১২০ ক্লিন (২ বার)
- git reflog/flog analysis: ৫২ কমিট ব্রাঞ্চ `coder-67-workflow-diet`-এ → squash-merge (53c9b1035)
- `git show d96ff8f8b` — Workflow Diet complete scope
- re-verify: tracked.txt, `_archive` (tracked), services/llm (০.py), dist (untracked), ৩ dead WFs, `.secrets/` সব অপরিবর্তিত
- working tree: ১ modified + untracked (audit file經過 stash-incident-এর পরেও লক্ষ্য)

**স্ট্যাটিক অডিট থেকে:** চারটি subagent-এর বিস্তারিত ফলাফল (dead code, sprawl, doc-drift, dependency) — প্রতিটি recheck-এ টিকে থাকার অভ্যন্তরীণ যাচাই করা হয়েছে; বদল তিনটি ডেল্টা টেবিলে।

**এখনো চলায়নি (রানटাইम यাচ棋 — 추천 করে):**
```bash
cd backend  && poetry run pytest --collect-only -q          # collection health
cd backend  && poetry run python -m compileall -q .          # syntax gate
cd frontend && pnpm test 2>&1 | tail -5                       # vitest (১১৬ ফাইল)
cd apps/mission-control && npx tsc --noEmit                    # প্রথমবার চালান
pnpm knip                                                      # dead code snapshot
```

---

## ১১. ফেজভিত্তিক অ্যাকশন প্ল্যান (recheck#২-সংশোধিত)

| ফেজ | কাজ | অবস্থা |
|---|---|---|
| **F0** | `.secrets/` gitignore + rotate; uncommitted `account.registry.ts` রিভিউ; **tracked.txt মুছে ফেলা** | ❌ OPEN (৫২ কমিটেও হয়নি) |
| **F1** | Infisical synth re-wire; বাকি artifacts `git rm --cached`; dead workflow/orphan scripts মোচন; CONTRIBUTING/README সংশোধন | ❌ OPEN |
| **F2** | `_archive/` (৫৭ tracked .py) + dead modules + dead frontend মোচন; duplicate families merge | ❌ OPEN |
| **F3** | MCP server consolidation; admin UI একীকরণ; mission-control typecheck/test; module-inventory SSOT + doc-drift gate | ❌ OPEN |
| **F4** | dep reconciliation (valibot floor, next-auth v5, lockfile single-source); coverage broaden; smoke probes; **watchdog runbook** | ❌ OPEN |
| **done** | ✅ archive offload (১২ ধ পুরোনো spec + tarball) · ✅ frontend/dist untracked · ✅ **Workflow Diet #67/#69 (quota)** · ✅ ৪টি নতুন sync/mirror/bridge/watchdog workflow hardened · ✅ Task Outcome Ledger Phase 0 | ✅ |

---
*প্রস্তুত: Kilo full-status audit — চার-দিকের গভীর স্ক্যান + ২ রাউন্ড recheck (৫২ কমিট ডেল্টা + diet merge)। অগ্রাধিকার: CRITICAL ১→৫, তারপর HIGH ক্রমে। concurrent fleet-এর কারণে F0/F1 আইটেমগুলো এক-দুটি merge-তে বন্ধ হয়ে যেতে পারে — প্রতিটি session-এ recheck করুন।*

---

## ১২. ফিক্স লগ — বাস্তবায়িত পরিবর্তন (২০২৬-১০-০৯ ~২০:০০–২১:০০ UTC)

সব ফিক্স লোকালি প্রয়োগ ও যাচাই করা হয়েছে (কোনো commit/push করা হয়নি — মালিকের রিভিউ প্রতীক্ষায়)।

| # | ফিক্স | পরিবর্তিত ফাইল | প্রমাণ |
|---|---|---|---|
| F1 | \.secrets/\ + \secrets/\ gitignore | \.gitignore\ | \git check-ignore -v .secrets/k.json\ → rule 41 |
| F2 | stale \	racked.txt\ মুছে ফেলা | (ডিস্ক থেকে মুছে ফেলা) | Test-Path = False |
| F3 | Infisical vault synthetic check re-wire | ightly-ops.yml\ (+২টি doc) | YAML OK · inputs=২৫ (limit-এ ঠিক) · job \ault-synthetic\ weekly-গেটেড |
| F4 | committed artifacts untrack | ৭টি ফাইল \git rm --cached\ + \.gitignore\ ব্লক | সব ৭টি এখন ignored |
| F5 | dead workflows মুছে ফেলা | \issue-template-guard.yml\, \uto-sync-pr-branches.yml\ | ২০ workflow রহল; \issue-ops.yml\ comment সংশোধন |
| F6 | orphan CI scripts মুছে ফেলা | \.github/scripts/\-এর ৪টি | ০ workflow ref যাচাইকৃত; \ci_dashboard_api.py\ docstring, \change_impact_detector.py\, \check_hardcoded_deployment_config.py\, \openapi.json\ (১-লাইন surgical) সংশোধন |
| F7 | duplicate/orphan scripts মুছে ফেলা | \delete_vault_duplicate_render_keys.py\, \uto_daily_standup_bot.py\, \	mp_sync_gh_secrets.py\, \duplicate_audit.txt\ | \_INDEX.md --check\ OK; matrix + list রিজেনারেট |
| F8 | inventory truth-sync | \MODULES_LIST.md\ ×২, matrix, wiring JSON | **🔴 Broken: ৫ → ০**; telegram_bot.py → package re-path; contract test আপডেট (১৮৪) |
| F9 | CONTRIBUTING/README সংশোধন | দুটি ফাইল | Poetry/pnpm/Node২৪/\.env.example\ ৬৫৭-লাইন সঠিক; script-নাম যাচাইকৃত |
| F10 | \.gitignore\ hygiene | \.gitignore\ (৭৩৫→৫৬৬ লাইন) | ১৬৪টি dup লাইন মুছে ফেলা, \\ anchored, \scratch_*.py\ repaired, \docs/audits/evidence\ re-include, negation ক্রম ঠিক |
| F11 | \_archive\ quarantine শেষ (১-স্প্রিন্ট নিয়ম) | ৫৭টি .py + MANIFEST মুছে ফেলা | import-ref শূন্য যাচাই; gitignore note সংশোধন |
| F12 | gitleaks fixture + main.yml rewiring | \.gitleaks.toml\, \main.yml\ | TOML valid; matrix regen সত্যিই wired; empty package dir পরিষ্কার |

**যাচাই সম্পন্ন:** ২০/২০ workflow YAML valid · ৯০-ফাইল py_compile ০ fail · \generate_script_index.py --check\ OK · module contract ৬/৬ pass · cross-tenant ৩৩/৩৩ pass · change_impact ৫/৫ pass · openapi JSON valid · services/llm সম্পর্কিত tests ১২/১২ pass।

**স্থগিত (owner decision দরকার):** mega-files ভাগ, admin UI একীকরণ, MCP server consolidation, duplicate tool families merge, frontend dead code removal (knip items), mission-control typecheck/test, dependency split — এগুলি আর্কিটেকচারালভাবে বড়, issue/ADMIN_DECISION দরকার।
