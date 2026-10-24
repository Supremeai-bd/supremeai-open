# SupremeAI × Infinity Tech Stack — অনুসরণ পরিকল্পনা

> **ভাষা:** বাংলা (Bangla) · **তারিখ:** 2026-10-24 · **উৎস:** https://infinitytechstack.uk/  
> **লক্ষ্য:** Infinity Tech Stack-এর প্রমাণিত প্যাটার্ন/টুল/আর্কিটেকচার থেকে SupremeAI যেভাবে উপকৃত হতে পারে, তার একটি বহু-পথ (multi-way) কর্মপরিকল্পনা।

---

## ১. সারসংক্ষেপ (Executive Summary)

- **Infinity Tech Stack** (Bart Chmiel, London) একজন ইঞ্জিনিয়ারের তৈরি ৩৬০K+ LOC-এর পোর্টফোলিও: ১৩টি ফ্রি AI Academy, ১৩+ ফ্রি ডেভ টুল, এবং from-scratch Rust/CUDA সিস্টেম (SPINE, ChronoFact, HARNESS, MCPlex, Infinity Security Stack)।
- SupremeAI-এর আর্কিটেকচার (gateway + core + studio + vscode + agents + browser + mcp-control-plane) Infinity-এর বিভিন্ন উপাদানের সাথে প্রায় ১:১ মিলে যায় — তাই এটি "tailor-made" মনে হয়েছে।
- অনুসরণের মূল নীতি: **"Simple yet Powerful"** (AGENTS.md §4 এর সাথে সামঞ্জস্যপূর্ণ) — ওভার-ইঞ্জিনিয়ারিং নয়, প্রমাণিত প্যাটার্ন পুনঃব্যবহার।
- **প্রস্তাব:** ১০টি স্বতন্ত্র অনুসরণ-পথ (Way), প্রায়োরিটি অনুযায়ী ৩টি ফেজে ভাগ করা।

---

## ২. Infinity Tech Stack — মূল উপাদান (সংক্ষিপ্ত)

| উপাদান | কাজ | SupremeAI-এর সমতুল্য |
|---|---|---|
| **Project SPINE** (Rust) | Anti-sycophancy gateway, 33 vertebrae invariants, stream sanitizer (<0.15µs), 4-level reality dial | `gateway/` (FastAPI provider gateway) |
| **ChronoFact** (Rust) | Epistemic backbone, TF-IDF tool pruning (74-92% token cut), relevance-gated memory (0.72 gate), temporal horizon calibration | `gateway/memory.py`, `core/` (decision moat) |
| **MCPlex Gateway** | MCP smart gateway, semantic tool routing (70-90% token save), RBAC, audit logs | `infrastructure/mcp-control-plane/` |
| **Infinity Security Stack** | Infinity ID (OIDC/MFA), Observe (logs/traces), Data (HNSW vector), Stream (BM25) — SaaS বিকল্প | Qdrant/Redis/Upstash dependencies |
| **HARNESS Engine** | Pure-Rust LLM inference, 30B MoE on 8GB VRAM, wgpu kernels | `core/` inference adapters |
| **Prompt Studio** | 63-model prompt engineering IDE, MCP schema builder, auto-optimize | `studio/` (no equivalent yet) |
| **Developer Tools (13+)** | SEO, JSON, schema, resume, color, cost calc, humaniser, readme | `studio/` (no equivalent yet) |
| **AI Academies (13)** | Free interactive courses (Claude, OpenAI, MCP, Agents, Rust, etc.) | `docs/` (no interactive equivalent) |
| **PulseBridge** | Mobile companion for IDE monitoring, screen streaming, prompt injection | `supremeai-vscode` mobile app |
| **EU AI Act Hub** | Compliance intelligence, risk tiers, penalty calculator | `core/governance/` |

---

## ৩. কেন "tailor-made" মনে হয়েছে — মিল বিশ্লেষণ

1. **Gateway pair:** SupremeAI-এর `gateway/` (FastAPI, provider chain, SSE, rate limit) ≈ Infinity-এর SPINE+ChronoFact duo (Rust gateway + epistemic backbone)। দুটোই LLM-এর সামনে বসে প্রোভাইডার-অ্যাগনস্টিক স্ট্রিমিং + সেফটি করে।
2. **MCP Control Plane:** SupremeAI-এর `mcp-control-plane` ≈ MCPlex Gateway (semantic routing, RBAC, audit)।
3. **Core intelligence:** SupremeAI-এর `core/` (DAG decision moat) ≈ HARNESS/ChronoFact epistemic layer।
4. **Studio (Vercel web UI):** SupremeAI-এর `studio/` ≈ Infinity-এর Prompt Studio + dev tools + academies হাব।
5. **VS Code extension + mobile:** SupremeAI-এর `vscode/` ≈ PulseBridge (IDE companion)।
6. **Browser stealth:** SupremeAI-এর `browser/` ≈ Infinity-এর stealth web agents (না, কিন্তু কাছাকাছি)।
7. **Federation/bridge model:** SupremeAI-এর bridge pipeline ≈ Infinity-এর zero-residue dispatch (কিন্তু Infinity-তে এটা নেই — এটা SupremeAI-এর নিজস্ব শক্তি)।
8. **Zero-Admin / ≤0.01%:** দুটোই "human-in-the-loop কম, automation বেশি" ফিলোসফি।
9. **Open-core embassy:** দুটোই public boundary + private core।

**মূল পার্থক্য:** Infinity = single engineer, Rust-first, from-scratch engines, heavy on academies/dev-tools. SupremeAI = federation of 12 satellites, Python/TS, FastAPI gateway, agent orchestration focus. Infinity-এর **content/education + dev-tools + anti-sycophancy** দিকগুলো SupremeAI-তে দুর্বল — এখানেই অনুসরণের সুযোগ।

---

## ৪. অনুসরণের ১০টি পথ (Multi-Way Follow Plan)

### Way 1 — Anti-Sycophancy Gateway (SPINE প্যাটার্ন) · **Phase 1, High**
**কী নেব:** SPINE-এর 4-level reality dial, Thoracic Invariant T1 (unearned apology strip), StreamTailSanitizer (two-phase SSE), Aho-Corasick lexical matcher (<0.2µs), credential-intimidation detachment (C4)।
**SupremeAI টার্গেট:** `gateway/service/` + `gateway/middleware/` + `gateway/sanitization.py`।
**কাজ:**
- SSE stream sanitizer মডিউল যোগ (Phase 1 opening cushion strip + Phase 2 mid-stream capitulation pivot) — `gateway/service/stream_sanitizer.py`।
- Reality dial config (Level 1-4) gateway config-এ — `gateway/config.py` / `routing_policy.json`।
- Aho-Corasick-based forbidden-phrase matcher (Python `pyahocorasick`) middleware।
- Unearned apology detection metric (telemetry counter)।
**প্রমাণ:** gateway tests + 58-test parity target।
**ঝুঁকি:** Python-এ <0.2µs পাওয়া যাবে না; Rust sidecar (SPINE binary) বিকল্প।

### Way 2 — Epistemic Backbone / Token Optimization (ChronoFact) · **Phase 1, High**
**কী নেব:** TF-IDF tool pruning (74-92% token cut), relevance-gated memory (cosine 0.72 threshold, 0 leak), temporal horizon calibration (`model_horizon.json`), SHA-256 tool cache।
**SupremeAI টার্গেট:** `gateway/capability_router.py`, `gateway/memory.py`, `core/`।
**কাজ:**
- `gateway/capability_router.py`-এ TF-IDF-based tool schema pruner (query → cosine sim → retain ≥ threshold)।
- Memory gate: cosine < 0.72 → reject cross-domain context (gateway/memory.py)।
- `gateway/model_horizon.json` — provider/model cutoff + training freeze dates (ChronoFact Pillar 1)।
- SHA-256 cache for tool responses (0ms hit)।
**প্রমাণ:** token-reduction benchmark (target ≥ 70%)।

### Way 3 — MCP Smart Gateway (MCPlex প্যাটার্ন) · **Phase 1, High**
**কী নেব:** Semantic tool routing (70-90% token save), constant-time auth, server-verified RBAC role binding, redacted audit logs, optionally-authenticated live security dashboard।
**SupremeAI টার্গেট:** `infrastructure/mcp-control-plane/`, `gateway/security.py`, `gateway/masking.py`।
**কাজ:**
- Semantic tool router in MCP control plane (TF-IDF over tool schemas)।
- Constant-time token compare (`hmac.compare_digest`) + RBAC role binding at server side।
- Redacted audit log format (no PII/secrets)।
- Optional auth dashboard endpoint।
**প্রমাণ:** security tests + audit log review।

### Way 4 — Developer Tools Suite (13+ free tools) · **Phase 2, Medium**
**কী নেব:** JSON formatter/validator/diff, schema generator (JSON-LD), SEO meta tag gen, color palette/WCAG, API cost calculator, README builder, prompt studio, humaniser।
**SupremeAI টার্গেট:** `studio/` (new `studio/tools/` or `studio/free-tools/`)।
**কাজ:**
- ৫-৭টি হাই-ইমপ্যাক্ট টুল প্রথমে (JSONForge, SchemaForge, CostForge, Prompt Studio, Humaniser) — Next.js pages।
- SEO-optimized landing pages (SupremeAI-এর ট্রাফিক বাড়াতে)।
- Browser-native, zero sign-up (Infinity-এর মতো)।
**প্রমাণ:** frontend_performance_guard + Lighthouse।

### Way 5 — Interactive AI Academies · **Phase 2, Medium**
**কী নেব:** ১৩টি ফ্রি ইন্টারেক্টিভ কোর্স (MCP, Agents, Claude, OpenAI, Rust, Inference) — labs, quizzes, XP, local progress।
**SupremeAI টার্গেট:** `studio/` + `docs/` (new `studio/academies/`)।
**কাজ:**
- SupremeAI-এর নিজস্ব স্ট্যাক শেখানোর কোর্স: "SupremeAI Gateway Academy", "MCP Control Plane Academy", "Agent Orchestration Academy"।
- ৩-৫টি কোর্স প্রথমে (MCP, Agents, Gateway)।
- LocalStorage progress (Infinity-এর মতো)।
**প্রমাণ:** content review + accessibility।

### Way 6 — Security Stack (Infinity ID/Observe/Data/Stream) · **Phase 3, Low-Medium**
**কী নেব:** SaaS বিকল্প — OIDC/MFA identity, observability (logs/metrics/traces), HNSW vector DB, streaming+BM25 search — single Rust binary, zero per-seat tax।
**SupremeAI টার্গেট:** `supremeai-archive` (vector store), `gateway/` observability, infra।
**কাজ:**
- স্বল্পমেয়াদে: Qdrant/Redis রাখুন, কিন্তু Infinity-এর HNSW/Stream মডিউল মূল্যায়ন করুন।
- দীর্ঘমেয়াদে: Infinity ID → SupremeAI auth (OIDC) প্রতিস্থাপন বিকল্প।
- Observe → gateway telemetry/metrics export।
**প্রমাণ:** infra cost comparison + migration playbook।

### Way 7 — Mobile IDE Companion (PulseBridge প্যাটার্ন) · **Phase 3, Medium**
**কী নেব:** মোবাইল অ্যাপ থেকে IDE/agent monitoring, screen streaming, prompt injection, project file tree।
**SupremeAI টার্গেট:** `vscode/` mobile (React Native/Flutter) + `gateway/ws/`।
**কাজ:**
- `gateway/ws/`-এ low-latency streaming endpoint (PulseBridge-এর Axum 0.7 মডেল)।
- Mobile app scaffold (React Native) under `vscode/mobile/`।
- Touch-drag scroll, file tree, prompt injection।
**প্রমাণ:** integration tests + latency benchmark (<15ms)।

### Way 8 — From-Scratch Engines Showcase (HARNESS/Vitalis/Void) · **Phase 2, Low**
**কী নেব:** SupremeAI-এর নিজস্ব engine-গুলো (core DAG, agent runner) পাবলিক showcase পেজে প্রদর্শন — Infinity-এর "About & Projects" মডেল।
**SupremeAI টার্গেট:** `studio/` (new showcase pages) + `docs/`।
**কাজ:**
- "About Bart"-এর মতো "About SupremeAI Architect" পেজ।
- Engine metrics (LOC, test count, benchmark) প্রদর্শন।
- GitHub links to open-source satellite repos।

### Way 9 — Swiss-Watch Duo Pairing (SPINE+ChronoFact) · **Phase 1, High**
**কী নেব:** দুটি complementary ইঞ্জিন (anti-sycophancy + epistemic backbone) একসাথে চালানো, পারস্পরিক horizon sync (T12/L3)।
**SupremeAI টার্গেট:** `gateway/` + `core/` integration।
**কাজ:**
- Gateway (Way 1) এবং Core (Way 2) এর মধ্যে shared invariant contract (ChronoFact ↔ SPINE style sync)।
- Paired health check endpoint (both must be green)।
- Cross-component test (gateway + core joint)।

### Way 10 — Telemetry Cockpit (React 19 HUD) · **Phase 2, Medium**
**কী নেব:** Live telemetry HUD (port :3333 style) — rigidity %, intercepted apology count, token saved, drift events।
**SupremeAI টার্গেট:** `studio/` (new dashboard widgets) + `gateway/` metrics endpoint।
**কাজ:**
- Gateway `/metrics` endpoint (Prometheus-style)।
- Studio dashboard widgets: token saved, schemas pruned, drift intercepted, cache hit %।
- Real-time SSE feed for live updates।

---

### Way 11 — Frontend Design Language & UX Patterns (Infinity-style) · **Phase 2, High**
**কী নেব:** Infinity-এর ভিজ্যুয়াল ডিজাইন সিস্টেম ও UX প্যাটার্ন — ডার্ক-ফার্স্ট cosmic theme, glass surfaces, neon accent (emerald #10b981 + purple #a855f7 + indigo #6366f1), monospace/HUD aesthetic, interactive labs with live telemetry, card-based badge system (FREE/NEW/OPEN SOURCE/COMMERCIAL), 4-level reality dial, animated gradients, accessibility (reduced-motion)।
**SupremeAI টার্গেট:** `studio/src/styles/tokens.css`, `studio/src/components/ui/`, `studio/src/components/common/`, `studio/src/components/layout/`।
**কাজ:**
- Design tokens আপডেট: Infinity-এর exact palette (emerald/purple/indigo) + glow + glass + aurora gradient (SupremeAI tokens ইতিমধ্যে কাছাকাছি — diff কম)।
- HUD/telemetry component library: live metric cards, rigidity gauge, token-saved counter, drift-event log panel (React 19)।
- Interactive lab pattern: "try it live" widgets (TF-IDF pruner simulator, reality dial slider) — studio pages-এ reusable।
- Badge system: FREE / NEW / HOT / POPULAR / COMMERCIAL SAAS / OPEN SOURCE (card headers)।
- Card grid layout (Infinity-এর 01-06 numbered sections) — landing page structure।
- Reduced-motion + a11y (prefers-reduced-motion) — already in tokens.css।
- Typography: monospace for code/telemetry, sans for body, tight tracking for headings।
- Infinity-এর "corner accent + glowing border" card style।
**প্রমাণ:** frontend_performance_guard + Lighthouse ≥ 90 + visual regression (Playwright snapshots)।
**ঝুঁকি:** SupremeAI-এর বিদ্যমান cosmic theme ইতিমধ্যে কাছাকাছি — বড় re-skin নয়, incremental polish।

---

### Way 12 — Super Admin Dashboard × Infinity Frontend Fusion · **Phase 1-2, High**
**কী নেব:** Infinity-এর HUD/telemetry aesthetic (live metric cards, rigidity gauge, token-saved counter, drift-event log, 4-level reality dial, corner-accent glowing cards, monospace telemetry) Super Admin Control Plane-এ প্রয়োগ — system command console, permission-request prompt, live platform summary, service health snapshot, approval queue, live alerts, audit/telemetry quick access।
**SupremeAI টার্গেট:** `studio/src/components/admin/` (SupremeAdminControlPlane, AdminShell, ApprovalQueue, AdminAlertsTab, health map), `studio/src/styles/tokens.css`, `studio/src/components/ui/`।
**কেন ভালো হবে:**
- Super Admin dashboard মূলত একটি "telemetry cockpit" — Infinity-এর HUD প্যাটার্ন (live metric cards, freshness timestamp, correlation id, module-level error isolation) সরাসরি প্রযোজ্য।
- Infinity-এর "unknown status ≠ healthy" নীতি → Super Admin health snapshot-এর observability requirement (§9) সাথে মিলে।
- Glass surfaces + neon accents → admin console-এর high information density-তে readability বাড়ায়।
- Reduced-motion + a11y → admin dashboard accessibility।
**কাজ:**
- `studio/src/components/admin/`-এ Infinity-style HUD components reuse: metric card, gauge, live log panel, status badge (FREE/NEW/HOT → HEALTHY/DEGRADED/DOWN)।
- Health snapshot cards-এ freshness timestamp + "unknown" distinct styling (not green)।
- Approval queue rows: Infinity card pattern with corner accent + glowing border on pending OTP-gated items।
- Alert stream panel: Infinity drift-event log style (timestamp + level + message)।
- Command console: monospace, dark glass surface, command history sidebar।
- Module-level error isolation: Infinity-এর "module crash ≠ blank page" pattern (ErrorBoundary per module)।
- Design tokens: reuse existing `--aurora-green`, `--aurora-purple`, `--nebula-gradient` (already aligned with Infinity)।
**প্রমাণ:** frontend_performance_guard + Lighthouse ≥ 90 + admin auth/approval smoke tests + visual regression।
**ঝুঁকি:** PR #1109/#1111-এর existing AdminShell reuse করতে হবে; নতুন fake authorization তৈরি করা যাবে না (manual roadmap-এর নিয়ম)।

---

---

## ৪.২ আমার নিজস্ব বেস্ট সাজেশন (SupremeAI-নির্দিষ্ট, Infinity-এর বাইরে)

> নিচেরগুলো Infinity-এর সাথে সরাসরি সম্পর্কিত নয়, কিন্তু SupremeAI-এর বিদ্যমান কোডবেস, memory-র decision/constraint/correction এবং AGENTS.md-এর নীতি থেকে প্রাপ্ত — এগুলো না করলে Infinity-অনুসরণ অসম্পূর্ণ থাকবে।

### Way 13 — Skill-Centric Agent Architecture (memory decision) · **Phase 2, High**
**কী:** Fixed agent-type-centric → Skill-centric universal agent (Agent = task worker, Skill = reusable method)। বিদ্যমান agent capabilities/workflows inventory → extract skills → universal dispatcher।
**টার্গেট:** `core/agents/`, `core/skills/`, `core/agent_factory.py`, `core/skill_manager.py`।
**কাজ:** skill registry + skill manifest schema + agent dispatcher that resolves skill by task; reuse 80% existing code।
**প্রমাণ:** skill resolution tests + non-regression (existing agents still work)।

### Way 14 — Infra Hardening: Redis Rate Limiter + httpx Pooling + Qdrant Memory (memory decisions) · **Phase 1, High**
**কী:** distributed rate limiter (Upstash Redis), httpx.AsyncClient connection pooling, memory store → Qdrant vector cluster (semantic search + persistence)।
**টার্গেট:** `gateway/rate_limit.py`, `gateway/pool.py`, `gateway/memory_store.py`, `core/unified_memory.py`।
**কাজ:** Redis-backed sliding window; shared httpx client with limits; Qdrant client with cosine 0.72 gate (ChronoFact Pillar 3 alignment)।
**প্রমাণ:** load test + memory leak test + rate-limit concurrency test।

### Way 15 — SWE Benchmark Gate (Infinity-style 216-case held-out) · **Phase 2, Medium**
**কী:** self-evolution/agent-breeding-এর জন্য 216-case held-out SWE benchmark gate (140 blind + 76 in-sample) — pre/post remediation metrics, SHA-256 frozen cases।
**টার্গেট:** `core/evaluation/`, `core/self_evolution/`, `core/self_benchmark.py`।
**কাজ:** frozen test corpus + accuracy/precision/recall/specificity/F1 reporting + CI gate (fail if regression)।
**প্রমাণ:** `cargo`/`pytest` benchmark suite green।

### Way 16 — Bangla-First Content & Docs (differentiator) · **Phase 2, Medium**
**কী:** Infinity English-only; SupremeAI Bangla-First হতে পারে (বাংলাদেশ/বাংলা-ভাষী ডেভেলপার)। `core/i18n/`, `studio` BanglaHint ইতিমধ্যে আছে।
**টার্গেট:** `docs/`, `studio/src/components/BanglaHint.tsx`, `core/localization/`, academies content।
**কাজ:** Bangla academies (SupremeAI Gateway Academy বাংলায়), Bangla UI strings, Bangla README/docs।
**প্রমাণ:** i18n completeness check + Bangla rendering test।

### Way 17 — Prompt Injection Defense + Anti-Hacking (SPINE T1 × gateway anti_hacking) · **Phase 1, High**
**কী:** gateway-এর `middleware/anti_hacking.py` + `sanitization.py` + SPINE-style Thoracic Invariant T1 (unearned apology strip, credential-intimidation detachment, Aho-Corasick lexical)।
**টার্গেট:** `gateway/middleware/anti_hacking.py`, `gateway/sanitization.py`, `gateway/security.py`।
**কাজ:** Aho-Corasick forbidden-phrase matcher (`pyahocorasick`), prompt-injection pattern set, red-team test suite (Infinity's 100-case blind held-out style)।
**প্রমাণ:** injection red-team pass rate ≥ 99%।

### Way 18 — Idempotency + Duplicate-Click Prevention for Approval Queue · **Phase 1, High**
**কী:** `gateway/middleware/idempotency.py` ইতিমধ্যে আছে; Super Admin approval queue-তে duplicate click → duplicate execution প্রতিরোধ।
**টার্গেট:** `gateway/middleware/idempotency.py`, `gateway/routes/approval_manager.py`, `studio` ApprovalQueue।
**কাজ:** idempotency key on approve/reject/cancel; backend dedup; frontend disable-on-submit + spinner।
**প্রমাণ:** duplicate-click test (no duplicate execution)।

### Way 19 — Webhook-Primary Dispatch Permanent Fix (correction) · **Phase 1, High**
**কী:** webhook must be primary (1st) and permanently fixed from root — PC-on webhook-primary / PC-off cloud-API failover plan নয়।
**টার্গেট:** `gateway/stealth_webhook.py`, `gateway/telegram_webhook.py`, `command/` handlers।
**কাজ:** webhook as primary dispatch path; cloud API fallback only when webhook unavailable; remove assumption-based failover।
**প্রমাণ:** dispatch smoke test (webhook path exercised first)।

### Way 20 — Evidence-Based Verification Gate (correction) · **Phase 1, High**
**কী:** controller coder-এর self-report বিশ্বাস করবে না; git diff scope + SHA-256 + controller-run tests exit 0 দিয়ে evidence verify।
**টার্গেট:** CI guards (`scripts/ci/`), `core/verification/`, evidence verification in PR pipeline।
**কাজ:** evidence verifier job: diff scope check, SHA-256 of changed files, run tests, exit 0 required; fail-closed।
**প্রমাণ:** CI gate green on main।

### Way 21 — Navigation/App Route Parity Test (constraint) · **Phase 1, Medium**
**কী:** `navigationRegistry.ts` এবং `App.tsx` রাউট হুবহু এক কিনা — automated CI test।
**টার্গেট:** `studio/src/router/`, `studio/src/routes/`, `studio/tests/`।
**কাজ:** parity test (set equality of registered routes) + CI job।

### Way 22 — Unified Store Server Migration + Rollback Contract (constraint) · **Phase 2, Medium**
**কী:** `src/store/index.ts` localStorage flag → server-configured safe migration + rollback contract।
**টার্গেট:** `studio/src/store/`।
**কাজ:** migration flag from server config; rollback on failure; audit log entry।

### Way 23 — Worker Service Private Access (constraint) · **Phase 1, High**
**কী:** Render worker-এর অভ্যন্তরীণ এন্ডপয়েন্টে service-to-service secret token / private networking; 0.0.0.0/0 ওপেন নয়।
**টার্গেট:** `core/worker_service.py`, infra/networking।
**কাজ:** shared secret header validation; private network config; close public access।

### Way 24 — Render API healthCheckPath = /health (constraint) · **Phase 1, Low**
**কী:** Render supremeai-api service-এর healthCheckPath `/health` সেট।
**টার্গেট:** infra/render config।
**কাজ:** config update + verify probe।

### Way 25 — Command ID Runtime Discovery (constraint) · **Phase 2, Low**
**কী:** third-party command id ব্যবহারের আগে `vscode.commands.getCommands` availability check + graceful fallback notification।
**টার্গেট:** `vscode/` extension code।
**কাজ:** availability check helper + notification fallback।

### Way 26 — Federation Auditor = Single Agent (correction) · **Phase 1, Low**
**কী:** Federation Auditor (মাইক্রোস্কোপ 🔬) এবং auditor একই agent — দুটি আলাদা নয়।
**টার্গেট:** `core/agents/`, agent registry।
**কাজ:** merge duplicate agent definitions; single source of truth।

### Way 27 — Continuous Agent Loop = Dispatcher Only (correction) · **Phase 1, Medium**
**কী:** continuous agent loop নিজে কাজ করবে না; শুধু dispatcher/Lazy Team Leader; board খালি হলে dispatch_idle_audit() read-only scout (report only, no issue creation)।
**টার্গেট:** `core/automation/`, `core/agent_loop*`, `core/ecosystem_scout/`।
**কাজ:** refactor loop to dispatcher; idle-audit read-only; no issue creation on empty board।

### Way 28 — OpenTelemetry + Correlation ID Standardization · **Phase 2, Medium**
**কী:** Infinity-এর Observe (logs/traces/metrics) প্যাটার্ন — SupremeAI-এর `observability/`, `monitoring/`, `telemetry/` একত্রিত, correlation id সব লগে।
**টার্গেট:** `core/observability/`, `core/monitoring/`, `core/telemetry/`, `gateway/` middleware।
**কাজ:** OTel SDK + correlation id middleware + unified dashboard (Super Admin cockpit)।

### Way 29 — EU AI Act Compliance Module · **Phase 3, Low**
**কী:** Infinity-এর EU AI Act Hub — risk tiers, penalty calculator, Annex IV docs. SupremeAI-এর `core/governance/` + studio page।
**টার্গেট:** `core/governance/`, `studio/` (new compliance page)।
**কাজ:** risk classification checker + penalty calculator + technical doc templates।

### Way 30 — Red-Team Gate for Agent Breeding (Infinity adversarial_redteam) · **Phase 2, Medium**
**কী:** `core/agent_breeding.py` + adversarial red-team gate (vague quantifiers, missing rollback, retired models)।
**টার্গেট:** `core/agent_breeding.py`, `core/evaluation/`।
**কাজ:** red-team rubric + gate in breeding pipeline; 100% specificity target।

---

## ৫. ফেজ-ভিত্তিক রোডম্যাপ (Phased Roadmap)

### Phase 1 — Gateway Hardening (২-৪ সপ্তাহ)
- Way 1 (Anti-sycophancy stream sanitizer)
- Way 2 (TF-IDF tool pruning + memory gate + model horizon)
- Way 3 (MCP semantic routing + constant-time auth + audit)
- Way 9 (Duo pairing + joint health check)
- Way 12 (Super Admin HUD components: metric cards, health snapshot, alert log, approval queue styling)
- Way 14 (Redis rate limiter + httpx pooling + Qdrant memory)
- Way 17 (Prompt injection defense + anti-hacking)
- Way 18 (Idempotency + duplicate-click prevention)
- Way 19 (Webhook-primary dispatch permanent fix)
- Way 20 (Evidence-based verification gate)
- Way 23 (Worker service private access)
- Way 24 (Render healthCheckPath = /health)
- Way 26 (Federation auditor = single agent)
- Way 27 (Continuous agent loop = dispatcher only)

**সাফল্যের সূচক:** gateway tests pass, token reduction ≥ 70%, 0 unearned-apology leak in SSE test, RBAC audit log review pass।

### Phase 2 — Studio & Content (৪-৮ সপ্তাহ)
- Way 4 (5-7 free dev tools)
- Way 11 (frontend design system + HUD components + interactive labs)
- Way 5 (3-5 interactive academies)
- Way 8 (showcase pages)
- Way 10 (telemetry cockpit)
- Way 13 (Skill-centric agent architecture)
- Way 15 (SWE benchmark gate)
- Way 16 (Bangla-first content & docs)
- Way 21 (Navigation/App route parity test)
- Way 22 (Unified store server migration + rollback contract)
- Way 25 (Command id runtime discovery)
- Way 28 (OpenTelemetry + correlation id standardization)
- Way 30 (Red-team gate for agent breeding)

**সাফল্যের সূচক:** Lighthouse ≥ 90, frontend_performance_guard pass, 3 academies live।

### Phase 3 — Infrastructure & Mobile (৮-১৬ সপ্তাহ)
- Way 6 (security stack evaluation + migration playbook)
- Way 7 (mobile IDE companion)
- Way 29 (EU AI Act compliance module)

**সাফল্যের সূচক:** cost comparison doc, mobile app alpha।

---

## ৬. প্রাথমিকতা ম্যাট্রিক্স (Priority Matrix)

| Way | প্রভাব | খরচ | ঝুঁকি | প্রাথমিকতা |
|---|---|---|---|---|
| 1 Anti-sycophancy | উচ্চ | মধ্য | নিম্ন | ★★★ |
| 2 Token optimization | উচ্চ | মধ্য | নিম্ন | ★★★ |
| 3 MCP smart gateway | উচ্চ | মধ্য | নিম্ন | ★★★ |
| 9 Duo pairing | মধ্য | নিম্ন | নিম্ন | ★★★ |
| 12 Super Admin × Infinity HUD | উচ্চ | মধ্য | নিম্ন | ★★★ |
| 13 Skill-centric agent arch | উচ্চ | উচ্চ | মধ্য | ★★ |
| 14 Infra hardening (Redis/pool/Qdrant) | উচ্চ | মধ্য | নিম্ন | ★★★ |
| 15 SWE benchmark gate | মধ্য | মধ্য | নিম্ন | ★★ |
| 16 Bangla-first content | মধ্য | মধ্য | নিম্ন | ★★ |
| 17 Prompt injection defense | উচ্চ | মধ্য | নিম্ন | ★★★ |
| 18 Idempotency approval queue | উচ্চ | নিম্ন | নিম্ন | ★★★ |
| 19 Webhook-primary dispatch | উচ্চ | নিম্ন | নিম্ন | ★★★ |
| 20 Evidence verification gate | উচ্চ | নিম্ন | নিম্ন | ★★★ |
| 21 Nav/route parity test | মধ্য | নিম্ন | নিম্ন | ★★ |
| 22 Unified store migration+rollback | মধ্য | মধ্য | নিম্ন | ★★ |
| 23 Worker service private access | উচ্চ | নিম্ন | নিম্ন | ★★★ |
| 24 Render healthCheckPath /health | নিম্ন | নিম্ন | নিম্ন | ★ |
| 25 Command id runtime discovery | নিম্ন | নিম্ন | নিম্ন | ★ |
| 26 Federation auditor single agent | নিম্ন | নিম্ন | নিম্ন | ★ |
| 27 Agent loop dispatcher-only | মধ্য | মধ্য | নিম্ন | ★★ |
| 28 OpenTelemetry + correlation id | মধ্য | মধ্য | নিম্ন | ★★ |
| 29 EU AI Act compliance module | নিম্ন | উচ্চ | নিম্ন | ★ |
| 30 Red-team gate for breeding | মধ্য | মধ্য | নিম্ন | ★★ |
| 11 Frontend design (Infinity-style) | উচ্চ | মধ্য | নিম্ন | ★★★ |
| 10 Telemetry cockpit | মধ্য | নিম্ন | নিম্ন | ★★ |
| 4 Dev tools | মধ্য | মধ্য | নিম্ন | ★★ |
| 5 Academies | মধ্য | উচ্চ | নিম্ন | ★★ |
| 8 Showcase | নিম্ন | নিম্ন | নিম্ন | ★ |
| 7 Mobile companion | মধ্য | উচ্চ | মধ্য | ★ |
| 6 Security stack | উচ্চ | উচ্চ | উচ্চ | ★ |

---

## ৭. ঝুঁকি ও সতর্কতা (Risks & Cautions)

1. **ভাষা/স্ট্যাক মিসম্যাচ:** Infinity Rust-first; SupremeAI Python/TS। Rust sidecar গ্রহণ করলে নতুন বিল্ড পাইপলাইন লাগবে। → প্রথমে Python-এ প্যাটার্ন প্রয়োগ, পরে Rust sidecar।
2. **লাইসেন্স:** Infinity-এর কোড MIT/Apache-2.0 — পুনঃব্যবহার করা যায়, কিন্তু attribution দিতে হবে। সরাসরি copy-paste নয়; প্যাটার্ন অ্যাডাপ্ট।
3. **স্কোপ ক্রিপ:** Infinity-এর সবকিছু অনুসরণ করা অসম্ভব। → Phase 1-এ gateway-কেন্দ্রিক ৪টি Way দিয়ে শুরু।
4. **Non-regression (AGENTS.md P3):** নতুন ফিচার যোগ করতে গিয়ে বিদ্যমান gateway/provider-chain নষ্ট করা যাবে না। → feature flags + tests।
5. **Satellite-first (AGENTS.md):** কোড `gateway/`, `studio/`, `core/` mirror-এ থাকতে হবে; root-level shadow নয়। → boundary_sanitization_guard চালাতে হবে।
6. **৩-সেকেন্ড প্রি-ফ্লাইট:** কাজ শুরুর আগে origin/main rebase + issue claim।

---

## ৭. পরবর্তী পদক্ষেপ (Next Steps)

1. **এই প্ল্যান রিভিউ** — ইউজার/টিম অনুমোদন।
2. **Phase 1 কিকঅফ:** Way 1-এর জন্য issue + branch `feat/gateway-anti-sycophancy-stream-sanitizer`।
3. **Way 2 TF-IDF pruner** — `gateway/capability_router.py` refactor।
4. **Way 3 MCP semantic router** — `infrastructure/mcp-control-plane/`।
5. **Way 9 duo pairing** — joint health check endpoint।
6. প্রতিটি PR-এ: `python scripts/ci/boundary_sanitization_guard.py --files <paths>` + tests + lint/typecheck।

---

## ৮. রেফারেন্স (References)

- Infinity Tech Stack: https://infinitytechstack.uk/
- Project SPINE: https://infinitytechstack.uk/spine
- ChronoFact: https://infinitytechstack.uk/chronofact
- PulseBridge: https://infinitytechstack.uk/pulsebridge
- Prompt Studio: https://infinitytechstack.uk/prompt-playground
- MCPlex Gateway: https://github.com/ModernOps888/mcplex
- SupremeAI AGENTS.md: ./AGENTS.md
- SupremeAI ARCHITECTURE_PLAN.md: ./ARCHITECTURE_PLAN.md
- SupremeAI ECOSYSTEM_MAP.md: ./ECOSYSTEM_MAP.md

---

> **মন্তব্য:** এই প্ল্যান AGENTS.md-এর "Zero Over-Engineering", "Extend, Never Regress", "Satellite-First" নীতিগুলোর সাথে সামঞ্জস্যপূর্ণ। প্রতিটি Way একটি স্বতন্ত্র PR (single-domain) হিসেবে বাস্তবায়ন করা হবে।
