---
id: risk-remediation-hardening-execution
subject: "SupremeAI প্রকল্প: ঝুঁকি থেকে বাস্তব Fix Plan"
document_role: implementation
planning_authority: Architecture Circle
canonical: false
status: active
evidence_state: unverified
disposition: retain
last_verified: 2026-09-17
supersedes: []
superseded_by: []
related: docs/plans/features/production_hardening_and_p1_p2_roadmap_2026_09_11.md
target_scope: supremeai_internal
---

# SupremeAI প্রকল্প: ঝুঁকি থেকে বাস্তব Fix Plan

> **উদ্দেশ্য:** এই নথিতে শুধু পরামর্শ নয়—প্রতিটি বড় ঝুঁকির জন্য কোথায় পরিবর্তন করতে হবে, কীভাবে করতে হবে, কীভাবে যাচাই করতে হবে এবং কোন পর্যায়ে কাজটি সম্পূর্ণ ধরা হবে তা দেওয়া হয়েছে।
>
> **ভিত্তি:** `AUDIT_REPORT_2026-09-10.md`, `STATUS.md`, `MASTER_PLAN.md`, `CHECKPOINT.md`, `PRODUCTION_ROADMAP_2026-09-11.md` এবং repository structure।
>
> **নীতি:** আগে নিরাপত্তা ও সত্যতা, তারপর reliability, তারপর নতুন feature। কোনো পরিবর্তন সরাসরি `main`-এ নয়; branch + PR + CI evidence ব্যবহার করতে হবে।

---

## ১. P0: Secret এবং credential ঝুঁকি বন্ধ করুন

### ঝুঁকি

Render credential আগে chat/transcript-এ ব্যবহৃত হয়েছে। Live key এখন scan-এ পাওয়া না গেলেও key compromise ধরে rotate করা উচিত।

### কোথায় পরিবর্তন হবে

- `backend/tools/learning/Diagnosed deployment failures and organizations.ini`
- `backend/tools/learning/`
- `.secrets-allowlist.json`
- `.github/workflows/ci.yml`
- `backend/core/security/secret_vault.py`
- `backend/utils/environment.py`

### কীভাবে fix করবেন

1. Render dashboard-এ `RENDER_API_KEY` এবং `RENDER_API_KEY_BACKUP` revoke করে নতুন key তৈরি করুন।
2. নতুন key repository-তে লিখবেন না; Infisical বা Vercel environment variable-এ রাখুন।
3. `backend/tools/learning/Diagnosed deployment failures and organizations.ini` ফাইলটি admin approval নিয়ে repository থেকে সরান। এটি code package-এর মধ্যে transcript হিসেবে থাকা উচিত নয়।
4. `.gitignore`-এ যোগ করুন:

   ```gitignore
   *.ini.local
   *.secret
   *.credentials
   backend/tools/learning/*.ini
   ```

5. `backend/core/security/secret_vault.py`-কে একমাত্র application secret access layer করুন। Route, agent বা provider adapter থেকে সরাসরি secret read নিষিদ্ধ করুন।
6. `backend/utils/environment.py`-এ environment variable-এর truthiness parsing এক জায়গায় রাখুন; `"false"`, `"0"`, empty string যেন সত্য হিসেবে গণ্য না হয়।
7. `.github/workflows/ci.yml`-এ secret scan blocking করুন। Scan fail হলে workflow pass করা যাবে না।

### যাচাই

- TruffleHog/Gitleaks scan clean
- `git log -S "RENDER_API_KEY" --all`-এ actual value নেই
- secret rotation-এর audit evidence আছে
- application log-এ secret value বা full token নেই

### সম্পূর্ণ ধরা হবে যখন

Credential rotate, transcript অপসারিত, CI secret scan blocking এবং runtime secret access centralised হবে।

---

## ২. P0: Backend authentication এবং tenant isolation শক্ত করুন

### ঝুঁকি

AI/MCP system-এ শুধু endpoint authentication যথেষ্ট নয়। কোনো authenticated user যেন অন্য tenant-এর task, memory, workspace, credential, execution বা audit record পড়তে/পরিবর্তন করতে না পারে। এটি BOLA/IDOR ঝুঁকি।

### কোথায় পরিবর্তন হবে

- `backend/core/security/authentication/auth_middleware.py`
- `backend/core/security/authentication/rbac.py`
- `backend/core/security/tool_gateway.py`
- `backend/core/task_policy.py`
- `backend/runtime/task_context.py`
- `backend/database/tenant_db.py`
- `backend/api/routes/task.py`
- `backend/api/routes/task_gateway.py`
- `backend/api/routes/unified_memory_api.py`
- `backend/api/routes/workspaces_route.py`
- `backend/api/routes/tools_ops.py`
- `backend/api/routes/tenant_admin.py`

### কীভাবে fix করবেন

প্রতিটি resource query এবং mutation-এর আগে এই scope বাধ্যতামূলক করুন:

```text
actor_id → tenant_id → resource_id → permitted action
```

1. `task_context.py`-এ immutable request context রাখুন:
   - `actor_id`
   - `tenant_id`
   - `roles`
   - `scopes`
   - `correlation_id`
2. Route path থেকে আসা `tenant_id` কখনো trusted identity হিসেবে ব্যবহার করবেন না। Session/token থেকে tenant resolve করুন; path tenant কেবল equality check হিসেবে ব্যবহার করুন।
3. `tenant_db.py`-এর সব read/write helper-এ `tenant_id` required parameter করুন। Optional default রাখবেন না।
4. `tool_gateway.py`-তে tool call allow করার আগে tenant, capability, resource এবং action যাচাই করুন।
5. Admin route-এ সাধারণ user-এর `tenant_id` override নিষিদ্ধ করুন।
6. Memory query-তে `tenant_id` এবং user-scoped data হলে `user_id` বাধ্যতামূলক filter করুন।
7. Object lookup না পেলে `404` দিন; অন্য tenant-এর object আছে কি না বোঝায় এমন error দেবেন না।
8. প্রতিটি denied action `audit_logger.py`-তে actor, tenant, resource, action, reason সহ লিখুন।

### নতুন test কোথায় লিখবেন

- `backend/tests/security/test_cross_tenant_isolation.py`
- `backend/tests/security/test_hardening_controls.py`
- `backend/tests/core/test_multi_tenant_isolation.py`
- `backend/tests/api/test_route_rbac_matrix.py`

প্রতিটি resource-এর জন্য অন্তত এই test লিখুন:

```text
Tenant A token + Tenant B resource → 404/403
User A token + User B private memory → 404/403
Non-admin + admin endpoint → 403
Valid tenant + invalid resource → 404
```

### সম্পূর্ণ ধরা হবে যখন

Critical route-এর cross-tenant test pass করবে এবং query helper-এ unscoped access আর থাকবে না।

---

## ৩. P0: Thin-client key exposure বন্ধ করুন

### ঝুঁকি

`frontend/src/services/SupremeAIService.ts`-এ OpenRouter direct fetch থাকার কথা `CHECKPOINT.md` এবং audit-এ উল্লেখ আছে। Frontend থেকে provider call হলে secret expose হতে পারে এবং policy bypass হতে পারে।

### কোথায় পরিবর্তন হবে

- `frontend/src/services/SupremeAIService.ts`
- `frontend/src/services/`-এর provider-specific service files
- `backend/api/routes/stream_chat_sse.py`
- `backend/api/routes/task_gateway.py`
- `backend/core/providers/`
- `frontend/.env.example`

### কীভাবে fix করবেন

1. `SupremeAIService.ts` থেকে OpenRouter URL, API key এবং direct provider fetch সরান।
2. Frontend কেবল backend-এর authenticated endpoint call করবে।
3. Backend provider adapter-এর মাধ্যমে model call করবে; provider key server-side environment-এ থাকবে।
4. Offline mode দরকার হলে কেবল explicitly configured local Ollama endpoint ব্যবহার করুন; public production build-এ provider key fallback রাখবেন না।
5. Frontend bundle scan-এ provider key pattern এবং `OPENROUTER_API_KEY` search যোগ করুন।
6. Backend-এ model/provider selection allowlist করুন; client-supplied arbitrary URL বা model blindly গ্রহণ করবেন না।

### যাচাই

- `frontend/dist` বা production bundle-এ কোনো provider key নেই
- Browser network trace-এ সরাসরি OpenRouter request নেই
- Backend endpoint ছাড়া frontend model response পায় না
- Unauthorized request rejected হয়

---

## ৪. P0: Migration system একটিতে নামিয়ে আনুন

### ঝুঁকি

দুটি migration tree আছে:

- `backend/database/migrations/`
- `backend/alembic_migrations/versions/`

দুটি source of truth থাকলে staging এবং production schema আলাদা হয়ে যেতে পারে।

### কোথায় পরিবর্তন হবে

- `backend/alembic.ini`
- `backend/alembic_migrations/env.py`
- `backend/alembic_migrations/versions/`
- `backend/database/migrations/`
- `backend/pyproject.toml`
- `backend/README.md`
- `.github/workflows/ci.yml`

### কীভাবে fix করবেন

1. সিদ্ধান্ত লিখুন: **Alembic canonical migration system**।
2. `backend/database/migrations/`-এর প্রতিটি SQL migration inventory করুন।
3. ইতিমধ্যে production-এ থাকা schema-এর জন্য একটি baseline Alembic revision তৈরি করুন।
4. পরের raw SQL migration Alembic-এর বাইরে নিষিদ্ধ করুন।
5. পুরনো SQL-গুলো `backend/database/migrations/legacy/`-এ read-only archive হিসেবে রাখুন অথবা admin approval নিয়ে সরান।
6. `backend/README.md`-এ একমাত্র migration command লিখুন:

   ```bash
   alembic upgrade head
   ```

7. CI-তে fresh database তৈরি করে `alembic upgrade head` চালান এবং schema validation করুন।
8. Production migration-এর আগে backup, dry-run এবং rollback plan বাধ্যতামূলক করুন।

### যাচাই

- Fresh database থেকে `upgrade head` সফল
- Previous production snapshot থেকে upgrade সফল
- Alembic ছাড়া migration চালালে CI fail
- Schema diff empty

---

## ৫. P1: Scripts/tools-এর real runtime bug ঠিক করুন

### ঝুঁকি

Audit-এ `tools`, `scripts`, `packages`, `.github/scripts`-এ প্রায় ১৮১টি `F821 undefined-name` পাওয়া গেছে। এগুলো operational script হওয়ায় runtime-এ সরাসরি crash করবে।

### নির্দিষ্ট file

প্রথম batch:

- `scripts/core_engine/tool_ranker.py`
- `scripts/db/auto_seed.py`
- `scripts/devops/cloud_watchman.py`
- `scripts/devops/config/cli.py`
- `tools/knowledge/card_builder.py`
- `scripts/devops/config/validators.py`

### কীভাবে fix করবেন

1. প্রতিটি F821-এর জন্য import, rename, missing implementation বা dead path—একটি সিদ্ধান্ত নিন।
2. Missing type হলে সঠিক shared type import করুন; placeholder `Any` দিয়ে ঢাকবেন না।
3. `logger`-এর মতো dependency হলে module-level `logging.getLogger(__name__)` ব্যবহার করুন।
4. Undefined validator বা service হলে বাস্তব implementation import করুন; silent fallback রাখবেন না।
5. Script-এর অন্তত একটি smoke test লিখুন।
6. Unused বা abandoned script হলে delete না করে admin approval request তৈরি করুন—repository constitution অনুযায়ী।

### CI কোথায় পরিবর্তন হবে

- `.github/workflows/ci.yml`

Backend-only ruff-এর পাশাপাশি root job যোগ করুন:

```bash
ruff check tools scripts packages .github/scripts
```

প্রথম ধাপে F821 blocking করুন; পরের ধাপে style warnings কমান।

### সম্পূর্ণ ধরা হবে যখন

সব F821 resolve বা approved exception হবে এবং CI নতুন F821 আটকাবে।

---

## ৬. P1: Test collection এবং skipped tests পরিষ্কার করুন

### ঝুঁকি

`respx` না থাকায় test collection ভাঙে এবং ছয়টি test missing module-এর কারণে skip হয়। Skip থাকা মানে capability সত্যিই কাজ করে না বা test stale।

### কোথায় পরিবর্তন হবে

- `backend/pyproject.toml`
- `backend/README.md`
- `backend/tests/tools/test_sso_integrator_comprehensive.py`
- `backend/tests/scripts/test_billing_fraud_detector.py`
- `backend/tests/scripts/test_billing_quota_enforcer.py`
- `backend/tests/scripts/test_billing_usage_reporter.py`
- `backend/tests/test_strategic_patches/test_cognitive_router.py`
- `backend/tests/core/test_grpc_client.py`
- `backend/tests/api/test_task_router.py`

### কীভাবে fix করবেন

1. Standard setup হিসেবে `poetry install` document করুন; bare pip install-কে supported setup হিসেবে রাখবেন না।
2. `respx` dev dependency হিসেবে lock file-এ আছে কি না নিশ্চিত করুন; CI ও local command একই করুন।
3. Billing tests-এর জন্য সিদ্ধান্ত নিন:
   - `scripts/billing/` বাস্তবে দরকার হলে তিনটি module implement করুন;
   - দরকার না হলে tests এবং stale dependency admin approval নিয়ে archive করুন।
4. Cognitive Router test-এর জন্য `backend/brain/cognitive_router.py`-এর বাস্তব contract সম্পূর্ণ করুন অথবা test-কে planned test হিসেবে আলাদা করুন।
5. gRPC test-এর `protos` generation pipeline তৈরি করুন; generated file commit করবেন না হলে CI generation বাধ্যতামূলক করুন।
6. Permanent `pytest.skip` রেখে issue বন্ধ করবেন না; প্রত্যেক skip-এর owner ও deadline রাখুন।

### যাচাই

```bash
poetry install
poetry run pytest --collect-only
poetry run pytest -q
```

Collection error শূন্য এবং unexplained skip শূন্য হতে হবে।

---

## ৭. P1: Coverage gate বাস্তব করুন

### ঝুঁকি

`.github/workflows/ci.yml`-এ backend coverage 35% এবং frontend coverage 9%—এগুলো regression আটকানোর জন্য খুব কম।

### কোথায় পরিবর্তন হবে

- `.github/workflows/ci.yml`
- `backend/pyproject.toml`
- `frontend/vitest.config.ts`
- `backend/tests/`
- `frontend/src/`

### কীভাবে fix করবেন

1. আগে CI-তে actual coverage report artifact হিসেবে publish করুন।
2. প্রথম release-এ gate করুন:
   - backend: 65%
   - frontend: 40%
3. প্রতি মাসে threshold বাড়�������নোর issue তৈরি করুন।
4. Security, tenant isolation, tool gateway এবং task execution module-এর জন্য আলাদা higher threshold রাখুন।
5. Coverage দিয়ে untested critical path আড়াল করবেন না; mission tests আলাদা বাধ্যত���মূল��� রাখুন।

### সম্পূর্ণ ধরা হবে যখন

Coverage threshold fail করলে CI fail হবে এবং report PR-এ দেখা যাবে।

---

## ৮. P1: Frontend quality debt কমান

### ঝুঁকি

Frontend-এ ১২৬টি ESLint warning আছে, যার মধ্যে ৫৭টি `no-explicit-any`, ৪৮টি unused variable এবং ১২টি `no-console`।

### কোথায় পরিবর্তন হবে

প্রথমে audit-এ চিহ্নিত file:

- `frontend/src/components/ChatInterface.tsx`
- `frontend/src/components/BrowserPreview.tsx`
- `frontend/src/providers/ThemeProvider.tsx`
- `frontend/src/hooks/useEventBus.ts`
- `frontend/src/services/authStore.ts`
- `frontend/src/services/ecosystem/api.ts`
- `frontend/src/services/llm.router.ts`
- `frontend/src/services/secureWebSocket.ts`
- `frontend/src/components/InteractiveChatTab.tsx`
- `frontend/src/components/SlashCommandMenu.tsx`
- `frontend/src/components/ServiceHealthMonitor.tsx`
- `frontend/src/components/AuthGuards.tsx`
- `frontend/src/routes/workspaceFeatureRoutes.tsx`

### কীভাবে fix করবেন

1. Unused imports এবং variables সরান।
2. `any`-এর বদলে domain interface বা `unknown` + runtime narrowing ব্যবহার করুন।
3. `console.*`-এর বদলে central logger ব্যবহার করুন; production bundle-এ debug log নিষিদ্ধ করুন।
4. `useEventBus.ts` এবং `SlashCommandMenu.tsx`-এর hook dependency warning যুক্তিসঙ্গতভাবে ঠিক করুন; warning suppress করবেন না।
5. Component file থেকে non-component export আলাদা utility file-এ সরান।
6. ESLint warning count CI artifact হিসেবে রাখুন এবং ধীরে zero-এর দিকে নামান।

---

## ৯. P1: Bare exception এবং silent failure বন্ধ করুন

### ঝুঁকি

নিচের production file-গুলোতে bare `except:` আছে; এতে security, provider failure এবং data corruption লুকিয়ে যেতে পারে।

### কোথায় পরিবর্তন হবে

- `backend/api/routes/dock_integrations.py`
- `backend/agents/ide/trio_adapters.py`
- `backend/pyerrorfix/core/catalog.py`
- `backend/pyerrorfix/detectors/`
- `backend/pyerrorfix/fixers/except_fixer.py`
- `backend/tools/code/code_smell_detector.py`
- `backend/core/security/audit_logger.py`

### কীভাবে fix করবেন

1. `except:`-এর বদলে নির্দিষ্ট exception ধরুন।
2. Expected failure হলে structured result return করুন।
3. Unexpected failure হলে correlation ID সহ log করুন এবং যথাযথ error raise করুন।
4. Secret, token, prompt content বা ব্যক্তিগত data log করবেন না।
5. Retry করা নিরাপদ কি না তা আলাদা করুন; সব exception retry করবেন না।
6. Failure path-এর test লিখুন—বিশেষত timeout, invalid response, permission denial এবং provider outage।

---

## ১০. P1: MCP/tool execution-এর জন্য policy gateway বাধ্যতামূলক করুন

### ঝুঁকি

MCP capability discovery শক্তিশালী হলেও tool call ভুল scope, prompt injection, SSRF বা excessive privilege তৈরি করতে পারে। URL বা model instruction কখনো authority হতে পারে না।

### কোথায় পরিবর্তন হবে

- `backend/core/security/tool_gateway.py`
- `backend/tools/mcp/mcp_server.py`
- `backend/tools/mcp/mcp_workspace.py`
- `backend/tools/mcp/mcp_github_cicd.py`
- `backend/tools/mcp/mcp_cloud_deploy.py`
- `backend/adaptive_engine/governed_executor.py`
- `backend/adaptive_engine/approval_workflow.py`
- `backend/core/security/audit_logger.py`
- `backend/tests/security/test_tool_policy_gateway.py`
- `backend/tests/security/test_hitl_state_machine.py`

### কীভাবে fix করবেন

প্রতিটি tool invocation-এর আগে:

```text
validate input
→ resolve tenant and actor
→ check capability allowlist
→ check resource scope
→ classify risk
→ request approval if needed
→ execute with timeout
→ verify output
→ write audit event
```

আরও নির্দিষ্টভাবে:

1. Tool registry-তে risk level, required scopes, allowed resource type এবং timeout রাখুন।
2. User prompt থেকে আসা URL সরাসরি fetch করবেন না; SSRF-safe URL validator ব্যবহার করুন।
3. Filesystem, shell, deployment, email, payment এবং deletion action default-deny করুন।
4. High-risk action-এর জন্য approval state machine ব্যবহার করুন; frontend flag দিয়ে approval bypass করা যাবে না।
5. Tool output untrusted data হিসেবে treat করুন; পরবর্তী tool instruction হিসেবে blind pass করবেন না।
6. প্রতিটি tool call-এর idempotency key এবং correlation ID রাখুন।

---

## ১১. P2: Dead code এবং duplicate surface কমান

### ঝুঁকি

Knip-এ unused dependency/export/type এবং duplicate export পাওয়া গেছে। কিন্তু repository constitution অনুযায়ী admin approval ছাড়া deletion করা যাবে না।

### কোথায় পরিবর্তন হবে

- `frontend/package.json`
- `frontend/src/`-এর Knip report-এ চিহ্নিত files
- `tools/vscode-extension/jest.config.js`
- `tools/vscode-extension/vitest.config.ts`
- `tools/vscode-extension/test/__mocks__/vscode.ts`
- `tools/vscode-extension/test/mocks/vscode.ts`
- `.knip.json`
- `MODULES_LIST.md`

### কীভাবে fix করবেন

1. Knip output থেকে candidate inventory তৈরি করুন।
2. প্রতিটি item-এর caller, owner, replacement এবং risk লিখুন।
3. Admin approval নিয়ে unused dependency/export সরান।
4. VS Code extension-এ একটি test runner এবং একটি mock directory রাখুন।
5. Duplicate default/named export-এর canonical form ঠিক করুন।
6. Package removal-এর পর clean install, typecheck ও test চালান।

---

## ১২. P2: Product scope কমিয়ে verified mission চালু করুন

### ঝুঁকি

অনেক operational/partially wired module থাকলেও user journey এবং reliability evidence তুলনামূলক দুর্বল। নতুন feature যোগ করলে complexity আরও বাড়বে।

### কোথায় পরিবর্তন হবে

- `backend/tests/missions/test_mission_suite.py`
- `backend/core/orchestration/`
- `backend/core/unified_router.py`
- `backend/core/task_policy.py`
- `backend/core/security/tool_gateway.py`
- `frontend/src/`-এর primary task flow
- `MASTER_PLAN.md`
- `ROADMAP_BANGLA.md`
- `MODULES_LIST.md`

### কীভাবে fix করবেন

প্রথম release-এর জন্য ৩টি mission lock করুন:

1. Repository/code task
2. Research + verified report
3. Bengali business/operator task

প্রতিটি mission-এ লিখুন:

- input contract
- allowed tools
- expected output
- verification rule
- retry limit
- cost budget
- failure reason
- audit evidence

`MODULES_LIST.md`-এ প্রতিটি module-কে `operational`, `wire-next`, `archive-pending`, `remove-approved` status দিন। Status claim-এর পাশে test বা runtime evidence link করুন।

---

## ১৩. Bengali capability-এর জন্য evaluation আগে তৈরি করুন

### কোথায় পরিবর্তন হবে

- `backend/agents/domain/bangla_nlp_agent.py`
- `backend/adapters/`
- `backend/tests/`
- `docs/`-এর Bangla documentation
- নতুন evaluation directory: `evals/bangla/`

### কীভাবে fix করবেন

1. বাংলা, Banglish এবং code-switching-এর ২০০–৫০০টি anonymized test case তৈরি করুন।
2. Category রাখুন:
   - instruction following
   - factuality
   - summarization
   - regional vocabulary
   - business/admin language
   - prompt injection resistance
3. Baseline provider বনাম Bangla adapter head-to-head score করুন।
4. Model training বা routing পরিবর্তনের আগে benchmark run বাধ্যতামূলক করুন।
5. User data evaluation set-এ নেওয়ার আগে consent, anonymization এবং retention policy লিখুন।

---

# বাস্তবায়নের ক্রম

## Sprint 1: Security stop-the-bleed

- Secret rotation
- Transcript removal
- Thin-client key removal
- Tenant isolation test
- Tool gateway deny-default
- Branch protection এবং required CI checks

## Sprint 2: Build এবং test সত্য করা

- `mypy.ini` encoding fix
- Root ruff gate
- `respx`/Poetry setup
- Six skipped test decision
- Coverage report এবং higher gate

## Sprint 3: Architecture cleanup

- Alembic canonical করা
- Bare exception fix
- Dead code approval inventory
- Duplicate VS Code test setup cleanup

## Sprint 4: Product reliability

- Three mission lock
- Pass³ mission suite
- Bengali evaluation set
- User-visible execution summary
- Cost, latency, success এবং retry metrics

---

# Done Definition

এই remediation phase সফল ধরা হবে যখন:

- কোনো known compromised credential active নেই;
- frontend-এ provider secret বা direct provider call নেই;
- critical route-এ cross-tenant access test pass কর���;
- MCP/tool action policy gateway ছাড়া execute হয় না;
- Alembic একমাত্র migration source;
- root scripts/tools lint CI-তে blocking;
- test collection error এবং unexplained skip নেই;
- coverage gate বাস্তব এবং reportable;
- তিনটি mission end-to-end verification evidence সহ pass করে;
- `STATUS.md`-এর প্রতিটি production claim-এর পাশে evidence link থাকে।

# প্রত্যেক পরিবর্তনের PR checklist

- [ ] কোন risk ঠিক হচ্ছে তা issue/PR description-এ লেখা আছে
- [ ] নির্দিষ্ট file এবং test উল্লেখ আছে
- [ ] Tenant/auth/security impact review হয়েছে
- [ ] Migration বা data impact review হয়েছে
- [ ] Unit/contract/security test যোগ হয়েছে
- [ ] CI evidence সংযুক্ত আছে
- [ ] Rollback plan আছে
- [ ] Documentation (`STATUS.md`, `CHECKPOINT.md`, roadmap) আপডেট হয়েছে
- [ ] `main`-এ সরাসরি push নয়; branch ও review সম্পন্ন

> **মূল কথা:** নতুন capability যোগ করার আগে existing capability-কে secure, wired, tested এবং measurable করুন। SupremeAI-এর production advantage হবে “অনেক কিছু করতে পারে” নয়; “নিরাপদে, যাচাইসহ, বারবার একই মানে কাজ শেষ করতে পারে।”

---

# ১৪. International, multilingual এবং configurable product model

## লক্ষ্য

SupremeAI যেন শুধু বাংলা-কেন্দ্রিক assistant না হয়ে user-এর locale, ভাষা, terminology, tone এবং formatting preference অনুযায়ী কাজ করতে পারে। বাংলা হবে প্রথম-class capability, কিন্তু architecture হবে language-neutral। User যেন English, বাংলা, Hindi, Arabic, Spanish, French, Portuguese, German, Japanese, Korean, Chinese অথবা নিজের tenant-এর নির্দিষ্ট ভাষা বেছে নিতে পারে।

## কোথায় পরিবর্তন হবে

- `backend/runtime/task_context.py`
- `backend/core/orchestration/`
- `backend/core/unified_router.py`
- `backend/core/task_policy.py`
- `backend/agents/domain/bangla_nlp_agent.py`
- `backend/adapters/`
- `backend/api/routes/`
- `frontend/src/services/SupremeAIService.ts`
- `frontend/src/providers/ThemeProvider.tsx` অথবা locale provider
- `frontend/src/i18n/` — না থাকলে নতুন canonical directory
- `frontend/src/components/LanguageSelector.tsx` — না থাকলে তৈরি করতে হবে
- `docs/i18n/INTERNATIONALIZATION.md`
- নতুন: `backend/core/i18n/locale_policy.py`
- নতুন: `backend/core/i18n/language_profiles.py`
- নতুন: `evals/multilingual/`

## কীভাবে fix/implement করবেন

1. `task_context.py`-এ request-level `locale`, `language`, `fallback_languages`, `timezone`, `date_format`, `number_format` এবং `response_style` রাখুন।
2. Tenant profile-এ `default_language` রাখুন; user preference থাকলে সেটি tenant default-এর উপর প্রাধান্য পাবে।
3. Language detection কখনো একমাত্র authority হবে না। User-selected language, tenant policy এবং detected language—এই তিনটির precedence document করুন।
4. Prompt, tool input, tool output এবং final answer আলাদা করুন। Tool/API input সাধারণত canonical schema-তে থাকবে; শুধু user-facing text translate হবে।
5. Error code, audit event, permission name এবং database enum translate করবেন না। এগুলো stable machine-readable identifier থাকবে।
6. Translation fallback রাখুন: requested language → tenant fallback → English. Silent language switch নয়; UI-তে fallback status দেখান।
7. Locale-specific system prompt ও terminology `language_profiles.py`-তে version করুন; user prompt-কে system policy override করতে দেবেন না।
8. Frontend-এ সব visible string translation key-তে নিন। `en`, `bn`, `hi`, `ar`, `es`, `fr`, `pt`, `de`, `ja`, `ko`, `zh` দিয়ে শুরু করা যেতে পারে; বাস্তব demand অনুযায়ী ভাষা যুক্ত হবে।
9. RTL ভাষার জন্য `dir="rtl"`, date/number formatting এবং layout test যোগ করুন।
10. User বা tenant glossary যুক্ত করুন—যেমন legal terms, product names, internal abbreviations—কিন্তু glossary-কে permission policy হিসেবে ব্যবহার করবেন না।
11. Prompt injection ও translation attack test করুন: অনুবাদিত text-এ instruction লুকিয়ে tool permission বদলানো যাবে না।

## ভাষাভিত্তিক data model

```text
TenantSettings:
  default_language
  fallback_languages[]
  timezone
  glossary_version
  response_style

TaskContext:
  requested_language
  detected_language
  effective_language
  locale_source
  translation_fallback_used
```

## আন্তর্জাতিক quality gate

- `evals/multilingual/test_instruction_following.py`
- `evals/multilingual/test_factuality.py`
- `evals/multilingual/test_code_switching.py`
- `evals/multilingual/test_rtl_rendering.py`
- `backend/tests/core/test_locale_policy.py`
- `frontend/src/i18n/__tests__/localeFallback.test.ts`

প্রতিটি supported language-এর জন্য অন্তত একই task-এর translated এবং native-authored version রাখুন। শুধু machine translation দিয়ে benchmark তৈরি করবেন না; native reviewer বা trusted corpus দিয়ে sample validation করুন।

---

# ১৫. Skill এবং tool ecosystem: কী যুক্ত করা যাবে

## মূল নিয়ম

কোনো MCP/skill শুধু “নাম আছে” বলে যুক্ত করবেন না। প্রতিটি integration-এর জন্য registry entry, permission scope, risk tier, timeout, cost limit, data classification, owner, health check এবং verification rule বাধ্যতামূলক।

## প্রস্তাবিত tool categories

| Category | Candidate | ব্যবহার | প্রথমে কোথায় যুক্ত হবে |
|---|---|---|---|
| Web research | Perplexity MCP বা সমতুল্য research MCP | citation-সহ current web answer | `backend/tools/mcp/`, `backend/core/security/tool_gateway.py` |
| Web crawling | Firecrawl | page crawl, sitemap, structured extraction | `backend/tools/mcp/mcp_web_research.py` |
| Browser automation | Playwright | reliable browser task, screenshot, form flow | `backend/tools/browser/`, `backend/core/security/tool_gateway.py` |
| Browser debugging | Chrome DevTools Protocol | console, network, performance diagnostics | `backend/tools/browser/cdp/` |
| Developer inspection | VS Code extension tools | repository context, test/run feedback | `tools/vscode-extension/`, `backend/tools/mcp/` |
| Creative media | Higgsfield বা approved video/image provider | media generation workflow | `backend/core/providers/media/` |
| Search/retrieval | OpenSearch, Qdrant বা pgvector | hybrid/vector retrieval | `backend/retrieval/`, `backend/database/` |
| Productivity | GitHub, Linear, Notion connectors | issue/PR/docs execution | `backend/tools/connectors/` |

`oerokexity MCP` নামটি যদি নির্দিষ্ট কোনো vendor/product বোঝায়, আগে official package, license, maintenance status, authentication model এবং data residency যাচাই করুন। অস্পষ্ট বা unverified MCP production registry-তে যোগ করবেন না।

## প্রতিটি tool-এর registry contract

নতুন file: `backend/core/tools/tool_manifest.py` অথবা বিদ্যমান registry-তে একই contract ব্যবহার করুন:

```yaml
name: playwright.browser
version: 1
risk_level: medium
required_scopes: [browser:read, browser:interact]
allowed_domains: []
network_policy: allowlist
filesystem_access: none
timeout_seconds: 30
max_retries: 1
requires_approval: false
handles_pii: true
verification: screenshot_or_dom_assertion
owner: platform-team
```

## নিরাপত্তা fix

- `tool_gateway.py`-তে domain allowlist, SSRF protection এবং private IP block করুন।
- `backend/tools/browser/`-এ browser profile প্রতি task-এ isolate করুন; cookies cross-task reuse করবেন না।
- Playwright/CDP-তে arbitrary download, shell execution, extension install এবং credential export default-deny করুন।
- Firecrawl result-কে untrusted content ধরুন; page-এর instruction execute করবেন না।
- Higgsfield/media provider-এ user upload, copyright status, retention এবং public/private output policy রাখুন।
- MCP server health এবং schema drift `backend/health/` বা বিদ্যমান health registry-তে monitor করুন।
- প্রত্যেক tool result-এ `source_url`, `retrieved_at`, `content_hash`, `tool_version` রাখুন।

## Tool onboarding process

1. Vendor/license/security review লিখুন: `docs/integrations/<tool-name>.md`।
2. Integration status এবং environment variables যাচাই করুন; secret code বা frontend-এ রাখবেন না।
3. Read-only scope দিয়ে শুরু করুন।
4. Sandbox tenant-এ contract test চালান।
5. Approval এবং rollback rule নির্ধারণ করুন।
6. Mission suite-এ অন্তত ৫টি success এবং ৫টি failure case যোগ করুন।
7. Canary traffic ছাড়া production-wide enable করবেন না।

---

# ১৬. Open-source stack থেকে কী নেওয়া যায়

## সম্ভাব্য উপকারী foundation

- **Playwright:** browser automation ও deterministic E2E verification
- **Firecrawl/self-hosted crawler alternative:** controlled crawling; robots, rate limit ও legal policyসহ
- **OpenTelemetry:** request/tool/provider trace
- **Prometheus + Grafana:** latency, error, queue এবং cost metrics
- **Langfuse বা OpenLIT:** LLM trace, prompt/version এবং evaluation observability
- **Ragas/DeepEval:** RAG এবং answer quality evaluation
- **Inspect AI অথবা lm-eval-harness:** reproducible model benchmark
- **vLLM অথবা Ollama:** approved local/open model serving
- **LiteLLM:** provider abstraction; তবে existing provider router-এর duplicate যেন না হয়
- **Presidio:** PII detection/redaction
- **OPA অথবা Cedar:** policy decision layer; existing policy engine-এর সাথে comparison করে নিন
- **Qdrant বা OpenSearch:** scale বাড়লে vector/hybrid retrieval
- **OpenFeature:** model/tool routing experiment ও feature flag
- **SLSA/Sigstore:** build provenance ও artifact signing

## কোথায় সতর্ক হতে হবে

একই কাজের জন্য দুইটি framework যুক্ত করবেন না। উদাহরণ: existing provider router থাকলে LiteLLM সরাসরি core path-এ ঢোকাবেন না; adapter হিসেবে benchmark করে লাভ প্রমাণ করতে হবে। প্রতিটি open-source dependency-এর জন্য license, CVE, maintainer activity, SBOM এবং upgrade owner রাখুন:

- `.github/workflows/ci.yml`
- `backend/pyproject.toml`
- `frontend/package.json`
- `docs/security/SBOM_AND_DEPENDENCY_POLICY.md`

---

# ১৭. Fine-tuning, human behavior এবং সত্যিকারের শেখা যাচাই

## প্রথম নীতি

Kaggle বা Hugging Face dataset সরাসরি production training data নয়। Dataset-এর license, provenance, PII, bias, toxicity, contamination এবং task relevance যাচাই না করে train করবেন না। Human behavior শেখানো মানে মানুষের private conversation কপি করা নয়; বরং consent-সহ anonymized behavior pattern, preference এবং evaluation signal শেখানো।

## কোথায় পরিবর্তন হবে

- `evals/behavior/`
- `evals/multilingual/`
- `backend/learning/`
- `backend/agents/`
- `backend/core/memory/`
- `backend/core/orchestration/`
- `docs/ml/DATASET_CARD_TEMPLATE.md`
- `docs/ml/MODEL_CARD_TEMPLATE.md`
- `docs/ml/TRAINING_GOVERNANCE.md`
- `scripts/evals/`
- `scripts/training/`

## নিরাপদ training pipeline

```text
dataset registry
→ license/provenance check
→ PII/toxicity filtering
→ deduplication
→ train/validation/test split
→ contamination check
→ baseline evaluation
→ fine-tune/adapter training
→ held-out evaluation
→ adversarial evaluation
→ shadow deployment
→ canary
→ rollback or promote
```

## Kaggle/Hugging Face ব্যবহারের বাস্তব পদ্ধতি

1. `docs/ml/dataset_registry.yaml`-এ dataset name, source URL, license, version, language, intended use, prohibited use এবং hash রাখুন।
2. Dataset download script `scripts/training/fetch_dataset.py`-তে রাখুন; manual unknown file commit করবেন না।
3. PII scan, duplicate removal এবং toxic content filter চালান।
4. User data থাকলে consent scope, deletion request এবং retention policy enforce করুন।
5. Full fine-tuning-এর আগে prompt routing, retrieval, few-shot এবং LoRA/adapter baseline compare করুন।
6. Model artifact object storage/model registry-তে version করুন; production code-এ mutable `latest` ব্যবহার করবেন না।
7. Training run-এর config, seed, dataset hash, base model, adapter version এবং evaluation result সংরক্ষণ করুন।

## Human behavior কীভাবে model করবেন

“মানুষের মতো” vague target না রেখে observable behavior label করুন:

- clarification চায় কি না
- uncertainty প্রকাশ করে কি না
- ভুল হলে correction গ্রহণ করে কি না
- unsafe request reject করে কি না
- user preference মনে রাখে কি না
- ভাষা/টোন ঠিক রাখে কি না
- tool ব্যবহারের আগে permission মানে কি না
- output verify করে কি না

Behavior policy model-এর system/security policy override করতে পারবে না। Human preference optimization-এ safety, privacy এবং truthfulness score বাধ্যতামূলক constraint হবে।

---

# ১৮. Human testing কমিয়ে automated evaluation চালু করুন

মানুষের test পুরোপুরি বাদ দেওয়া যাবে না; কিন্তু repetitive comparison, regression এবং monitoring automate করা উচিত। Human review থাকবে gold-set creation, ambiguous case, safety boundary এবং release approval-এ।

## Automated evaluation architecture

নতুন directory:

- `evals/cases/` — versioned test cases
- `evals/golden/` — approved expected properties
- `evals/runners/` — provider/model/tool runner
- `evals/metrics/` — scoring functions
- `evals/reports/` — generated artifacts; large output repository-তে নয়
- `scripts/evals/run_eval.py`
- `scripts/evals/compare_runs.py`
- `backend/api/routes/admin_evals.py`
- `frontend/src/routes/admin/EvaluationDashboard.tsx`

প্রতিটি case-এ রাখুন:

```yaml
id: multilingual.tool_safety.001
language: bn
input: ...
expected_properties:
  - answers_in_requested_language
  - does_not_call_unapproved_tool
  - cites_source
  - states_uncertainty
risk_level: high
max_cost_usd: 0.05
```

## কী automate করা যাবে

- language adherence
- JSON/schema validity
- citation presence ও URL validity
- factual claim verification যেখানে trusted source আছে
- PII leakage scan
- secret/token leakage scan
- prompt injection resistance
- tool permission enforcement
- cross-tenant isolation regression
- latency, token এবং cost budget
- retry/failover behavior
- browser DOM/screenshot assertion
- code task test pass
- response toxicity/safety classifier
- output diff এবং regression comparison
- memory recall precision/tenant boundary
- model drift এবং language-wise quality trend

LLM-as-judge একা final truth নয়। Rule-based assertion, deterministic test, reference answer, external verifier এবং human sample audit একসাথে ব্যবহার করুন। Judge model হলে judge bias, prompt version এবং inter-rater agreement track করুন।

## CI/CD gate

`.github/workflows/ci.yml`-এ আলাদা `evaluation` job যোগ করুন:

1. smoke suite প্রতিটি PR-এ
2. security/multilingual suite প্রতিটি backend change-এ
3. full mission suite nightly
4. provider/model change-এ mandatory benchmark
5. threshold কমলে PR fail
6. report artifact এবং JSON summary সংরক্ষণ

প্রস্তাবিত gate:

- critical safety regression: zero tolerance
- cross-tenant failure: zero tolerance
- schema/tool policy failure: zero tolerance
- overall quality: baseline-এর চেয়ে নির্ধারিত minimum-এর নিচে নয়
- cost increase: approved budget-এর মধ্যে
- latency regression: defined P95 threshold-এর মধ্যে

---

# ১৯. Admin কীভাবে ফলাফল দেখবে

## কোথায় পরিবর্তন হবে

- `backend/api/routes/admin_evals.py`
- `backend/api/routes/admin_telemetry.py`
- `backend/core/security/rbac.py`
- `backend/core/security/audit_logger.py`
- `backend/database/`-এর evaluation/experiment schema
- `frontend/src/routes/admin/EvaluationDashboard.tsx`
- `frontend/src/routes/admin/ExperimentDetail.tsx`
- `frontend/src/components/admin/MetricCard.tsx`
- `frontend/src/components/admin/FailureTrace.tsx`

## Admin dashboard-এর আবশ্যিক view

### ১. Executive overview

- verified task success rate
- safety violation count
- cross-tenant denial count
- cost per task
- P50/P95 latency
- provider outage/failover
- language-wise quality
- model version এবং evaluation timestamp

### ২. Experiment comparison

প্রতিটি run-এ দেখান:

- experiment ID
- base model বনাম candidate model
- dataset/eval-set version
- prompt/tool policy version
- total cases
- pass/fail score
- confidence interval
- cost ও latency
- regression categories
- promote/hold/rollback recommendation

### ৩. Failure explorer

Filter:

- tenant
- language
- task type
- tool
- provider/model
- risk level
- failure class
- date range

প্রতিটি result-এ raw secret বা private prompt দেখাবেন না। Redacted input, trace ID, policy decision, tool calls, verifier output এবং remediation link দেখান।

### ৪. Promotion control

Admin যেন দেখতে পারে:

```text
candidate → shadow → canary → promoted / held / rolled back
```

Promotion button backend policy ছাড়া কাজ করবে না। `admin_evals.py`-তে RBAC, approval reason, two-person approval for high-risk model/tool changes এবং immutable audit event রাখুন।

### ৫. Dataset/model governance

- dataset license/status
- consent status
- PII scan result
- model card
- artifact hash
- training run
- evaluation evidence
- rollback version
- expiry/review date

---

# ২০. International expansion-এর বাস্তব rollout

## Phase A: Language-neutral core

- machine-readable task/policy/audit contract
- locale-aware context
- translation keys
- English + বাংলা parity
- multilingual eval runner

## Phase B: Common languages

Demand, safety quality এবং native review অনুযায়ী Hindi, Arabic, Spanish, French, Portuguese, German, Japanese, Korean এবং Chinese যুক্ত করুন। প্রত্যেক ভাষা production-এ enable করার আগে minimum benchmark এবং fallback path pass করতে হবে।

## Phase C: Tenant customization

- tenant glossary
- custom tone/style
- approved tools
- region-specific compliance
- retention/data residency
- organization-specific evaluation set

## Phase D: Regional operations

- timezone-aware scheduling
- local date/number/currency format
- RTL support
- regional provider routing
- data residency policy
- language-specific support and incident runbook

---

# ২১. নতুন Done Definition

International এবং automated-learning phase সফল ধরা হবে যখন:

- request-level language/locale policy backend-এ enforced;
- অন্তত English ও বাংলা একই core mission-এ pass করে;
- supported language যোগ করা configuration-driven, code duplication-driven নয়;
- প্রতিটি MCP/skill-এর manifest, owner, scope, risk, timeout এবং verification rule আছে;
- tool output untrusted এবং policy gateway দ্বারা controlled;
- dataset license, provenance, PII এবং model version audit করা যায়;
- fine-tuned model baseline-এর বিরুদ্ধে held-out evaluation pass করে;
- automated eval CI-তে regression ধরতে পারে;
- human review কেবল gold set, ambiguous case এবং high-risk release-এ সীমিত;
- admin dashboard-এ experiment, failure, cost, latency, language এবং promotion status দেখা যায়;
- candidate model/tool shadow ও canary ছাড়া production-wide promote হয় না;
- rollback version এবং evidence প্রতিটি promotion-এর সাথে আছে।

> **চূড়ান্ত লক্ষ্য:** SupremeAI যেন “একটি বাংলা AI” না থেকে একটি language-neutral, policy-governed, verifiable এবং tenant-configurable AI execution platform হয়—যেখানে নতুন ভাষা, নতুন skill, নতুন model এবং নতুন provider যুক্ত করা যায় নিরাপত্তা, benchmark ও rollback evidence বজায় রেখে।

---

# ২২. Third-party free-tier থেকে বৈধভাবে সর্বোচ্চ উপকার নেওয়া

## মূল নীতি

Free tier ব্যবহার করে cost কমানো যাবে, কিন্তু provider-এর terms ভেঙে quota bypass, fake identity, disposable account, credential sharing, CAPTCHA bypass বা concurrent multi-account rotation করা যাবে না। বর্তমান multi-account setup থাকলে প্রতিটি account-এর ownership, billing responsibility, quota এবং provider policy লিখিতভাবে inventory করতে হবে। **Account সংখ্যা বাড়িয়ে quota লুকিয়ে বাড়ানো নয়; official team plan, grant, academic/open-source program, self-hosted fallback এবং workload optimization হবে নিরাপদ পথ।**

## কোথায় পরিবর্তন হবে

- `backend/core/providers/` — provider adapter ও fallback policy
- `backend/core/providers/provider_registry.py` — না থাকলে canonical registry
- `backend/core/quotas/` — নতুন quota/budget layer
- `backend/core/security/tool_gateway.py` — provider/tool permission
- `backend/runtime/task_context.py` — tenant, plan, provider এবং quota context
- `backend/database/` — provider account, quota bucket, usage ledger schema
- `backend/api/routes/admin_telemetry.py`
- `backend/api/routes/admin_evals.py`
- `frontend/src/routes/admin/ProviderUsageDashboard.tsx` — নতুন admin view
- `frontend/src/components/admin/QuotaCard.tsx`
- `docs/integrations/THIRD_PARTY_FREE_TIER_POLICY.md` — নতুন policy
- `docs/integrations/PROVIDER_CATALOG.md` — নতুন provider catalog
- `docs/security/DEPENDENCY_AND_PROVIDER_RISK.md` — নতুন risk register
- `.github/workflows/ci.yml`

## এখন যে সুবিধাগুলো অনেক provider-এ নেওয়া যায়

প্রতিটি provider-এর official free feature এবং বর্তমান terms যাচাই করে নিচের সুবিধাগুলো inventory করুন:

| সুবিধা | কীভাবে ব্যবহার করবেন | SupremeAI-তে ফলাফল |
|---|---|---|
| API quota ও usage dashboard | usage API/webhook সংগ্রহ করে daily budget monitor | quota শেষ হওয়ার আগে graceful fallback |
| Batch/asynchronous API | non-urgent embedding/evaluation/training job batch করুন | request cost ও rate-limit pressure কমে |
| Webhook ও event notification | job complete, failure, quota warning event গ্রহণ | polling কমে, admin alert বাড়ে |
| Caching | একই public retrieval/query-এর normalized cache | duplicate provider call কমে |
| Conditional requests | ETag/If-Modified-Since support থাকলে ব্যবহার | crawl/API bandwidth কমে |
| Model routing | cheap/free model দিয়ে classification, paid model দিয়ে কঠিন কাজ | cost-quality balance |
| Provider-native retries | documented retry-after ও idempotency ব্যবহার | duplicate charge/request কমে |
| Export/log API | provider usage, error, latency, model version import | central admin dashboard |
| Grants/credits | startup, education, open-source বা research program-এ apply | বৈধভাবে capacity বাড়ে |
| Self-host/open-source mode | suitable model/tool self-host বা local runner | vendor quota dependency কমে |

এই সুবিধাগুলো অনুমান করে enable করবেন না। `docs/integrations/PROVIDER_CATALOG.md`-এ provider, feature, plan, limit, reset time, terms URL, data retention, region এবং last verified date রাখুন।

## Recommended provider capability matrix

প্রথমে existing provider list থেকে এই capability map তৈরি করুন:

```text
provider_id
official_account_owner
allowed_use_case
free_tier_limits
rate_limit
batch_available
webhook_available
usage_api_available
cache_allowed
commercial_use_allowed
data_retention
region
fallback_provider
terms_url
last_verified_at
owner
```

`backend/core/quotas/quota_manager.py`-এ token, request, browser-minute, crawl-page, storage এবং media-generation—প্রতিটি resource আলাদা হিসাব করুন। শুধু HTTP request count দিয়ে quota মাপবেন না।

## Multi-account-এর compliant design

### যা করা যাবে

1. একই organization-এর official team/workspace account হলে account mapping করুন।
2. Provider-এর অনুমোদিত sub-account, project, environment বা workspace ব্যবহার করুন।
3. আলাদা tenant-এর নিজস্ব provider credential হলে tenant isolation বজায় রেখে tenant-এর account-এ request পাঠান।
4. Open-source project, education, startup বা research credits-এর জন্য official application করুন।
5. Provider-এর official billing limit, budget alert এবং quota increase request ব্যবহার করুন।
6. একই provider-এর একাধিক account থাকলে প্রতিটি account-এর owner, purpose, terms acceptance, region এবং credential expiry registry-তে রাখুন।

### যা করা যাবে না

- এক user-এর free quota বাড়ানোর জন্য ভুয়া account তৈরি
- disposable email/identity বা credential sharing
- rate limit এড়াতে account rotation
- একই task একাধিক account-এ duplicate পাঠানো
- provider-এর terms নিষেধ করলে proxy/relay দিয়ে quota conceal করা
- free tier-কে production SLA হিসেবে advertise করা

### Account-aware routing

`backend/core/providers/provider_registry.py` এবং `quota_manager.py`-এ routing rule রাখুন:

```text
request
→ tenant/account ownership check
→ provider policy check
→ remaining quota check
→ risk/data-region check
→ choose one eligible account
→ reserve quota atomically
→ execute with idempotency key
→ record actual usage
→ release unused reservation
```

Account rotation কেবল official organization/project boundary, tenant ownership এবং provider terms অনুযায়ী হবে। `round_robin` দিয়ে blind quota evasion করবেন না।

### Team member-এর নিজস্ব account এক system-এ যুক্ত করার সঠিক মডেল

ছোট team-এর প্রত্যেক সদস্য নিজের email ও নিজের third-party account ব্যবহার করতে পারেন। এখানে account merge করা হবে না; বরং account আলাদা রেখে SupremeAI-এর একটি centralized provider gateway-তে official OAuth/API connection হিসেবে যুক্ত করা হবে। ফলে interface, policy, audit এবং usage reporting এক থাকবে, কিন্তু credential ownership আলাদা থাকবে।

```text
Team member
  → SupremeAI login
  → Connect Provider (official OAuth/API consent)
  → encrypted provider connection
  → policy-aware provider gateway
  → member-এর authorized third-party account
```

### কোথায় বাস্তবায়ন হবে

- `backend/models/provider_connection.py` — owner, tenant, provider, scopes, status, expiry metadata
- `backend/api/routes/provider_connections.py` — connect, callback, refresh, disconnect ও revoke endpoint
- `backend/core/security/credential_vault.py` — encrypted token storage; raw token response/log-এ নয়
- `backend/core/providers/provider_gateway.py` — unified provider call interface
- `backend/core/providers/account_router.py` — eligible account নির্বাচন
- `backend/core/quotas/quota_manager.py` — account-level reservation ও usage হিসাব
- `backend/core/security/tool_gateway.py` — task, data classification ও consent scope যাচাই
- `backend/database/migrations/` — `provider_connections`, `provider_scopes`, `provider_usage_events`, `provider_disconnect_events`
- `backend/api/routes/admin_telemetry.py` — aggregate usage ও health
- `frontend/src/pages/settings/ConnectedAccounts/` — member connection management
- `frontend/src/routes/admin/ProviderUsageDashboard.tsx` — account owner, quota, errors ও routing history
- `backend/tests/security/test_provider_account_isolation.py` — owner/tenant isolation
- `backend/tests/quotas/test_account_routing.py` — policy-aware routing

### বাধ্যতামূলক data model ও policy

প্রতিটি connection record-এ রাখুন:

```text
connection_id
provider_id
tenant_id
credential_owner_id
connected_by_user_id
allowed_scopes
approved_use_cases
data_region
terms_accepted_at
expires_at
revoked_at
status
```

Routing-এর আগে এই checks চালাতে হবে:

```text
request actor
→ tenant match
→ credential owner/consent scope match
→ provider terms/use-case policy
→ data classification and region check
→ quota and budget check
→ reserve quota atomically
→ execute with idempotency key
→ record usage and audit event
```

### Team account ব্যবহারের নিয়ম

1. Member-এর personal connection defaultভাবে শুধু সেই member-এর task-এ ব্যবহার করুন।
2. অন্য member-এর task-এ ব্যবহার করতে হলে account owner-এর explicit consent scope এবং team policy দুটিই থাকতে হবে।
3. Shared workload-এর জন্য ব্যক্তিগত account-এর বদলে provider-এর official team/workspace/service account ব্যবহার করুন।
4. Password share করবেন না; OAuth authorization বা provider-approved API key flow ব্যবহার করুন।
5. Member team ছাড়লে connection revoke, pending job stop, token deletion এবং cached private data purge করুন।
6. Admin raw token দেখবে না; শুধু owner, scopes, status, quota, usage, errors ও revoke action দেখবে।
7. এই architecture quota bypass-এর জন্য নয়; প্রতিটি account-এর provider terms, owner consent ও legitimate workload আলাদা করে সংরক্ষণ করতে হবে।

### Required tests

- User A-এর connection দিয়ে User B-এর private task চালানো `403` হবে।
- Tenant A-এর connection Tenant B-তে ব্যবহার করা যাবে না।
- Missing/expired/revoked connection হলে নতুন request শুরু হবে না।
- Restricted PII বা অনুমোদনহীন data scope থাকলে provider call block হবে।
- একই request retry হলেও idempotency key-এর কারণে duplicate execution হবে না।
- Member offboarding-এর পরে token ব্যবহার এবং pending job দুটিই বন্ধ হবে।

## Free-tier optimization-এর বাস্তব automation

নিচের কাজগুলো automated করা যাবে:

- quota threshold 50%, 80%, 95%-এ admin alert
- quota reset calendar এবং projected exhaustion time
- duplicate prompt/result cache detection
- low-risk task-এর জন্য cheapest eligible provider নির্বাচন
- batch window-তে embedding/evaluation queue করা
- provider outage হলে circuit breaker ও approved fallback
- retry-after সম্মান করে backoff
- per-tenant daily/monthly budget enforcement
- unused reserved quota reconciliation
- provider invoice/usage বনাম internal ledger reconciliation
- sudden account rotation, unusual volume এবং quota spike anomaly detection
- PII বা restricted data free-tier provider-এ পাঠানোর আগে block/redact
- provider terms বা model availability change হলে catalog review task তৈরি

নতুন automation files:

- `scripts/provider_usage/sync_usage.py`
- `scripts/provider_usage/reconcile_ledger.py`
- `scripts/provider_usage/check_quota_expiry.py`
- `backend/workers/provider_quota_worker.py`
- `backend/core/quotas/anomaly_detector.py`
- `backend/tests/quotas/test_account_routing.py`
- `backend/tests/quotas/test_quota_reservation.py`
- `backend/tests/security/test_provider_data_policy.py`

## কোন third-party category যুক্ত করা যেতে পারে

নতুন vendor যোগ করার আগে existing capability duplicate নয় তা প্রমাণ করুন। সম্ভাব্য category:

| Category | সম্ভাব্য উপকার | নিরাপদ প্রথম ধাপ |
|---|---|---|
| Observability | trace, error, cost ও provider comparison | OpenTelemetry-compatible export |
| Evaluation | regression, RAG score, model comparison | offline eval; production prompt নয় |
| Browser | DOM, screenshot, accessibility ও performance test | isolated Playwright worker |
| Search/retrieval | hybrid search ও citation | read-only index |
| Storage | artifact, report ও model version | private bucket + retention |
| Notification | quota/failure/admin alert | non-sensitive summary only |
| Translation | common-language coverage | user-selected language + fallback |
| Model serving | open model/embedding fallback | offline benchmark first |
| Security | PII redaction, SBOM, secret scan | CI blocking scan |

Candidate-এর জন্য `docs/integrations/<provider-name>.md` লিখুন এবং এই gate pass না করা পর্যন্ত production credential দেবেন না:

1. license ও commercial use review
2. terms/free-tier limit review
3. data retention/residency review
4. security/authentication review
5. cost ceiling ও quota behavior test
6. sandbox contract test
7. fallback/rollback plan
8. admin visibility
9. owner ও renewal date
10. mission suite success/failure evidence

## Admin কীভাবে দেখবে

`ProviderUsageDashboard.tsx`-এ দেখান:

- provider ও account/project status
- official quota বনাম internal usage
- আজ/সপ্তাহ/মাসের request, token, page, minute ও cost
- quota reset time এবং projected exhaustion
- account ownership ও policy status; secret নয়
- provider health, error rate, latency এবং fallback count
- cache-hit rate ও saved cost
- unusual account switching বা quota spike
- terms review এবং credential expiry
- pending grant/credit request

প্রতিটি usage record-এ রাখুন:

```text
usage_id, task_id, tenant_id, provider_id, account_ref,
resource_type, reserved_amount, actual_amount, unit,
request_hash, status, error_class, created_at
```

Admin dashboard-এ API key, access token, raw prompt বা private provider response দেখাবেন না। High-risk provider/account policy change-এর জন্য approval এবং immutable audit event রাখুন।

## Done Definition

এই অংশ সম্পূর্ণ ধরা হবে যখন:

- সব third-party provider ও account-এর catalog এবং owner আছে;
- প্রতিটি provider-এর free-tier terms ও last-verified date আছে;
- quota reservation ও actual usage ledger atomic এবং tenant-scoped;
- account routing official ownership/terms ছাড়া হয় না;
- quota alert, reset forecast, circuit breaker ও fallback কাজ করে;
- PII/data-region policy free-tier provider call-এর আগে enforce হয়;
- usage বনাম provider dashboard reconciliation report তৈরি হয়;
- admin কোনো secret না দেখে quota, cost, health, fallback ও anomaly দেখতে পারে;
- multi-account setup documented, auditable এবং compliant;
- terms পরিবর্তন বা quota exhaustion production failure না হয়ে controlled degradation তৈরি করে।