---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto-codebase_modularization_and_splitting_matrix
subject: "🏗️ Plan: Comprehensive Codebase Modularization & File Splitting Matrix"
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# 🏗️ Plan: Comprehensive Codebase Modularization & File Splitting Matrix

## 🎯 Goal Description
SupremeAI-এর বিভিন্ন লেয়ারে (Backend, Frontend, VS Code Extension, Scripts, CI Pipelines, Test Suites) বেশ কিছু মনোলিথিক ফাইল রয়েছে যা ৬০০ থেকে ২০০০+ লাইন পর্যন্ত বিস্তৃত। এই বড় ফাইলগুলোতে মাল্টিপল রেসপনসিবিলিটি একসাথে মিশে থাকায় মেইনটেন্যাবিলিটি কমে যায়, টেস্ট করা জটিল হয় এবং কোড ইভল্যুশনে বাধা সৃষ্টি করে।

আমাদের **"Lean Execution over Meta-Overengineering"** এবং **"Continuous Matrix Splitting"** প্রিন্সিপাল অনুযায়ী এই ফাইলগুলোকে ডোমেন-ভিত্তিক সাব-মডিউলে স্প্লিট (Split / Refactor) করার পূর্ণাঙ্গ তালিকা ও আর্কিটেকচারাল ব্লুপ্রিন্ট নিচে প্রদান করা হলো।

---

## 🌟 High-Impact File Splitting Master Matrix

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                      SUPREMEAI FILE SPLITTING ARCHITECTURE                       │
├───────────────────────┬───────────────────────┬──────────────────────────────────┤
│ Layer / Domain        │ Monolithic File       │ Target Modular Sub-Modules       │
├───────────────────────┼───────────────────────┼──────────────────────────────────┤
│ 1. Backend Routes     │ admin_dashboard.py    │ 5 Sub-Routers + Aggregator       │
│                       │ browser.py            │ Driver + Actions + Session + API │
├───────────────────────┼───────────────────────┼──────────────────────────────────┤
│ 2. Core AI & LLM      │ llm_gateway.py        │ Provider Adapters + Router + Cost│
│                       │ llm_router.py         │ Routing Rules + Load Balancer    │
├───────────────────────┼───────────────────────┼──────────────────────────────────┤
│ 3. Memory & Evolution │ mcp_server.py         │ MCP Handlers + Tools + Protocols │
│                       │ temporal_system.py    │ Timeline + Abstraction + State   │
│                       │ tom_system.py         │ TheoryOfMind + Intent + Persona  │
├───────────────────────┼───────────────────────┼──────────────────────────────────┤
│ 4. VS Code Extension  │ SupremeAIService.ts   │ Auth + Chat + Stream + Telemetry │
│                       │ CodeFlowHandler.ts    │ Refactor + Fix + AST + Parser    │
│                       │ extension.ts          │ Commands + Providers + Lifecycle │
├───────────────────────┼───────────────────────┼──────────────────────────────────┤
│ 5. Frontend (Web/UI)  │ BrainVisualizer.tsx   │ GraphCanvas + NodeInspect + Stats│
│                       │ Dashboard.tsx         │ MetricsGrid + Activity + Actions │
├───────────────────────┼───────────────────────┼──────────────────────────────────┤
│ 6. Scripts & DevOps   │ api_contract_valid... │ Schemas + Diff Engine + Reporter │
│                       │ auto_vulnerabil...    │ SAST + DAST + SecretHunter + CLI │
├───────────────────────┼───────────────────────┼──────────────────────────────────┤
│ 7. Test Suites        │ test_mcp_servers_i... │ BaseFixtures + Unit + E2E Suites │
│                       │ test_core_missing_... │ Domain-specific test units       │
└───────────────────────┴───────────────────────┴──────────────────────────────────┘
```

---

## 📂 Detailed File-by-File Breakdown & Splitting Strategy

### 1. Backend API & Routes

#### 🔴 Monolith: [`backend/api/routes/admin_dashboard.py`](file:///f:/supremeai%20backup/backend/api/routes/admin_dashboard.py) (~1,130 lines)
- **Problem:** সিস্টেম মেট্রিক্স, ইউজার ম্যানেজমেন্ট, টেন্যান্ট ওভারভিউ, কস্ট অ্যানালিটিক্স এবং অডিট লগ সব কিছু একটিমাত্র ফাইলে স্তূপীকৃত।
- **Proposed Split Directory:** `backend/api/routes/admin/`
  - 📄 `__init__.py` *(Main APIRouter aggregator)*
  - 📄 `metrics_router.py` *(System health, CPU/RAM, DB stats)*
  - 📄 `tenants_router.py` *(Tenant CRUD, quotas, limits)*
  - 📄 `cost_router.py` *(Cost tracking, token burn, budget alerts)*
  - 📄 `audit_router.py` *(Security logs, system event history)*
  - 📄 `brain_telemetry_router.py` *(Memory, vector store, neural stats)*

---

#### 🔴 Monolith: [`backend/api/routes/browser.py`](file:///f:/supremeai%20backup/backend/api/routes/browser.py) (~710 lines)
- **Problem:** Playwright/Selenium ব্রাউজার লঞ্চ, সেশন স্টেট, ইন্টারঅ্যাকশন স্ক্রিপ্ট এবং স্ক্রিনশট রুট একসাথে রয়েছে।
- **Proposed Split Directory:** `backend/api/routes/browser/` & `backend/services/browser/`
  - 📄 `browser_router.py` *(Clean FastAPI endpoint handler ~100 lines)*
  - 📄 `services/session_manager.py` *(Browser session lifecycle, isolation)*
  - 📄 `services/action_executor.py` *(Click, type, scroll, wait automation)*
  - 📄 `services/dom_parser.py` *(Accessibility tree & visual diffing)*

---

### 2. Core AI, LLM & Gateway

#### 🔴 Monolith: [`backend/core/llm/llm_gateway.py`](file:///f:/supremeai%20backup/backend/core/llm/llm_gateway.py) (~849 lines) & [`backend/services/llm/llm_router.py`](file:///f:/supremeai%20backup/backend/services/llm/llm_router.py) (~847 lines)
- **Problem:** ডাইনামিক প্রোভাইডার হ্যান্ডলিং (OpenAI, Gemini, Groq, Ollama), টোকেন ট্র্যাকিং, ফলব্যাক লজিক ও প্রম্পট ইঞ্জিনিয়ারিং একসাথে কোড করা।
- **Proposed Split Directory:** `backend/core/llm/gateway/`
  - 📄 `gateway_manager.py` *(Core entry point & fallback orchestrator)*
  - 📄 `adapters/` *(Dedicated per-provider adapters: `gemini.py`, `groq.py`, `openai.py`, `local_ollama.py`)*
  - 📄 `token_budgeter.py` *(Free-tier quota, rate-limit & cost optimizer)*
  - 📄 `failover_circuit.py` *(JIT retry, circuit breaker & self-healing)*

---

### 3. Memory & Autonomous Evolution Systems

#### 🔴 Monolith: [`backend/memory/mcp_server.py`](file:///f:/supremeai%20backup/backend/memory/mcp_server.py) (~898 lines)
- **Problem:** Model Context Protocol (MCP) সার্ভার ইনিশিয়ালাইজেশন, প্রোটোকল হ্যান্ডলার, টুল রেজিস্ট্রেশন এবং মেমোরি কুয়েরি সব এক ফাইলে।
- **Proposed Split Directory:** `backend/memory/mcp/`
  - 📄 `server.py` *(Core MCP Server instance & lifecycle)*
  - 📄 `handlers.py` *(Request/Response protocol dispatcher)*
  - 📄 `tools_registry.py` *(Dynamic tool definitions & schema validators)*
  - 📄 `resource_provider.py` *(Context & vector memory resource provider)*

---

#### 🔴 Monolith: [`backend/evolution/temporal_abstraction/temporal_system.py`](file:///f:/supremeai%20backup/backend/evolution/temporal_abstraction/temporal_system.py) (~905 lines)
- **Problem:** টাইমলাইন ম্যানেজমেন্ট, মেমোরি কম্প্রেশন, লং-টার্ম অ্যাবস্ট্রাকশন ও হিস্ট্রি রিট্রিভাল একসাথে ব্লটেড।
- **Proposed Split Directory:** `backend/evolution/temporal_abstraction/`
  - 📄 `engine.py` *(Core orchestrator)*
  - 📄 `timeline_manager.py` *(Event sequencing & time-series frames)*
  - 📄 `abstraction_compressor.py` *(Knowledge summarization & decay models)*
  - 📄 `state_store.py` *(Persistence layer)*

---

#### 🔴 Monolith: [`backend/evolution/theory_of_mind/tom_system.py`](file:///f:/supremeai%20backup/backend/evolution/theory_of_mind/tom_system.py) (~830 lines)
- **Problem:** ইউজার সাইকোলজি মডেলিং, ইনটেন্ট ডিটেকশন, পার্সোনা ট্র্যাকিং এবং ডায়ালগ কন্টেক্সট এক ফাইলে রয়েছে।
- **Proposed Split Directory:** `backend/evolution/theory_of_mind/`
  - 📄 `tom_core.py` *(Cognitive engine)*
  - 📄 `intent_predictor.py` *(User intent & psychological context)*
  - 📄 `persona_tracker.py` *(Persona profile & adaptation)*
  - 📄 `cognitive_cache.py` *(Fast JIT caching of user patterns)*

---

### 4. VS Code Extension (Thin Client)

#### 🔴 Monolith: [`tools/vscode-extension/src/services/SupremeAIService.ts`](file:///f:/supremeai%20backup/tools/vscode-extension/src/services/SupremeAIService.ts) (~841 lines)
- **Problem:** অথেনটিকেশন, SSE স্ট্রিমিং, ব্যাকএন্ড কল, চ্যাট হিস্ট্রি ও এরর রিকভারি একই সার্ভিসে।
- **Proposed Split Directory:** `tools/vscode-extension/src/services/ai/`
  - 📄 `SupremeAIService.ts` *(Lightweight facade)*
  - 📄 `client/StreamClient.ts` *(SSE / WebSocket streaming engine)*
  - 📄 `client/ApiClient.ts` *(REST request handler with retry)*
  - 📄 `session/ChatSessionStore.ts` *(Local session state & cache)*
  - 📄 `auth/AuthManager.ts` *(Zero-config token sync)*

---

#### 🔴 Monolith: [`tools/vscode-extension/src/handlers/CodeFlowHandler.ts`](file:///f:/supremeai%20backup/tools/vscode-extension/src/handlers/CodeFlowHandler.ts) (~722 lines)
- **Problem:** কোড এডিট, রিফ্যাক্টরিং, ডিবাগিং, কোড লেন্স ও ডিফ ভিউয়ার লজিক একসাথে।
- **Proposed Split Directory:** `tools/vscode-extension/src/handlers/codeflow/`
  - 📄 `CodeFlowHandler.ts` *(Main event dispatcher)*
  - 📄 `DiffApplyEngine.ts` *(Precise unified diff application)*
  - 📄 `DiagnosticsSolver.ts` *(Quick-fix & lint issue auto-resolver)*
  - 📄 `CodeLensProvider.ts` *(Contextual inline action triggers)*

---

### 5. Frontend (Web Studio & Super-Admin)

#### 🔴 Monolith: [`frontend/src/components/admin/BrainVisualizer.tsx`](file:///f:/supremeai%20backup/frontend/src/components/admin/BrainVisualizer.tsx) (~797 lines)
- **Problem:** D3/Canvas রেন্ডারিং, নোড কালকুলেশন, ইনফো ড্রয়ার, অ্যানিমেশন লজিক এবং ফিল্টারিং সব এক ফাইলে।
- **Proposed Split Directory:** `frontend/src/components/admin/brain-visualizer/`
  - 📄 `BrainVisualizer.tsx` *(Main wrapper & container)*
  - 📄 `GraphCanvas.tsx` *(WebGL/Canvas graph rendering engine)*
  - 📄 `NodeInspectorDrawer.tsx` *(Node details, memory inspector)*
  - 📄 `VisualizerControls.tsx` *(Zoom, pan, search, filter toolbars)*
  - 📄 `types.ts` & `hooks/useBrainGraph.ts` *(Graph state & calculation hooks)*

---

#### 🔴 Monolith: [`frontend/src/components/admin/Dashboard.tsx`](file:///f:/supremeai%20backup/frontend/src/components/admin/Dashboard.tsx) (~782 lines)
- **Problem:** ওভারভিউ কার্ড, চার্টস, অ্যাক্টিভিটি ফিড, কুইক অ্যাকশন মোডাল সব এক ফাইলে।
- **Proposed Split Directory:** `frontend/src/components/admin/dashboard/`
  - 📄 `Dashboard.tsx` *(Layout grid orchestrator)*
  - 📄 `MetricsOverviewGrid.tsx` *(KPI Stat cards)*
  - 📄 `SystemLoadCharts.tsx` *(Realtime usage charts)*
  - 📄 `ActivityFeed.tsx` *(Streaming live audit log)*
  - 📄 `QuickActionsToolbar.tsx` *(Admin trigger shortcuts)*

---

### 6. DevOps & Diagnostic Scripts

#### 🔴 Monolith: [`scripts/testing/api_contract_validator.py`](file:///f:/supremeai%20backup/scripts/testing/api_contract_validator.py) (~1,077 lines)
- **Problem:** Pydantic -> TypeScript/Dart স্কিমা জেনারেশন, ওপেনএপিআই ড্রিফট ডিটেকশন ও এইচটিএমএল রিপোর্ট জেনারেশন এক ফাইলে।
- **Proposed Split Directory:** `scripts/contract_validator/`
  - 📄 `validator_cli.py` *(CLI Entrypoint)*
  - 📄 `schema_extractor.py` *(FastAPI OpenAPI JSON & Pydantic models parser)*
  - 📄 `drift_detector.py` *(Frontend TS vs Backend API contract diff)*
  - 📄 `report_generator.py` *(CI Markdown & terminal summary generator)*

---

#### 🔴 Monolith: [`scripts/security/auto_vulnerability_scanner.py`](file:///f:/supremeai%20backup/scripts/security/auto_vulnerability_scanner.py) (~872 lines)
- **Problem:** SAST, DAST, Secret Detection, সিআই ওয়ার্নিং জেনারেটর সব এক ফাইলে।
- **Proposed Split Directory:** `scripts/security/scanner/`
  - 📄 `scanner_runner.py` *(Runner orchestrator)*
  - 📄 `secret_hunter.py` *(Entropy & regex-based secret detection)*
  - 📄 `dependency_checker.py` *(CVE & pip/npm audit)*
  - 📄 `remediation_advisor.py` *(Auto-patch recommendations)*

---

### 7. Massive Test Suites

#### 🔴 Monolith: [`backend/tests/test_mcp_servers_integration.py`](file:///f:/supremeai%20backup/backend/tests/test_mcp_servers_integration.py) (~1,987 lines)
- **Problem:** সমস্ত MCP টুল ও প্রোটোকল টেস্ট ২০০০ লাইনের সিঙ্গেল ফাইলে রাখা। কোনো টেস্ট ফেইল করলে রুট কজ ট্র্যাক করা কষ্টকর।
- **Proposed Split Directory:** `backend/tests/mcp/`
  - 📄 `conftest.py` *(Shared mock servers & fixtures)*
  - 📄 `test_protocol_handshake.py` *(Init, capabilities, protocol flow)*
  - 📄 `test_tool_execution.py` *(File, memory, web tool invocations)*
  - 📄 `test_error_handling.py` *(Timeouts, broken streams, invalid JSON-RPC)*

---

## 🛡️ Modularization Execution Rules
1. **Zero Breaking Changes (Backward Compatibility):** প্রতিটি স্প্লিট করা মডিউলের রুট ফাইলে (`__init__.py` বা `index.ts`) আগের সব পাবলিক মেম্বার এক্সপোর্ট রাখতে হবে, যাতে বাইরের কোনো ফাইল ইমপোর্ট ব্রেক না করে।
2. **Lean & Direct Execution:** কোনো অহেতুক মেটা-ক্লাস বা ফ্রেমওয়ার্কের ভেতর ফ্রেমওয়ার্ক যোগ করা যাবে না। কোড থাকবে ক্লিন ও সরাসরি।
3. **Continuous Automated Verification:** প্রতিটি ফাইল স্প্লিট করার পরপরই `pytest` এবং `pnpm run test` চালিয়ে সম্পূর্ণ ফাংশনালিটি ভেরিফাই করা হবে।