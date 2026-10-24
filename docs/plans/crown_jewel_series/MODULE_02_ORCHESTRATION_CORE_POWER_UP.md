---
id: crown-jewel-module-02-orchestration-core-power-up-v1-2026-09-17
title: "Crown Jewel Module Series — Module 02: Orchestration Core Power-Up (SupremeKernel-কে একমাত্র প্রবেশদ্বার করা + Run-Fabric সেতু সম্পূর্ণ করা — প্ল্যাটফর্মের মেরুদণ্ডকে সবচেয়ে শক্তিশালী করার পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Kernel Circle (backend/core/kernel/ — SupremeKernel dispatcher + backend/core/orchestration/ + backend/runs/ + backend/runtime/)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ২ — একটি মডিউল (Orchestration Core), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — fresh main 07604ad (2026-09-17) sed/head/grep-যাচাইকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; প্রতিটি ধাপে flag+kill-switch; 721-route surface-এ zero-regression লক্ষ্য"
depends_on:
  - "backend/core/kernel/dispatcher.py (SupremeKernel Central Dispatcher — docstring-যাচাইকৃত: governed single-door entry facade, FCC federation routing Governance/Execution/Evolution/Infrastructure circles, legacy flat-registry fallback, policy+circuit breakers, distributed trace+audit)"
  - backend/core/kernel/interface.py (KernelRequest/KernelResponse/CircleScope চুক্তি)
  - backend/core/orchestration/swarm_orchestrator.py (class SwarmOrchestrator — DAG execution + tool synthesis — grep-verified 2026-09-17)
  - backend/core/orchestration/conversation_orchestrator.py (class ConversationOrchestrator L73, 422 লাইন — capability registry + policy gateway, live dispatch)
  - backend/core/orchestration/orchestrator.py (13-LN shim — চতুর্থ প্রজন্মের অবশেষ, wc-verified)
  - backend/core/orchestration/agent_orchestrator.py + master_cognitive_orchestrator.py + periodic_task_scheduler.py (সমান্তরাল প্রজন্ম — ls-verified)
  - backend/runs/ (state_machine.py 12-state, budgets.py, retry.py, hitl.py, bridges.py, api.py, service.py — ls-verified; backend/tests/runs/ ৭ টেস্ট-ফাইল)
  - backend/missions/ (state machine + traces + repair loop)
  - backend/runtime/ (canonical task runtime — planner, budget guard, executor)
  - backend/core/agents/framework/crewai_agents.py (hand-rolled CrewAI-lookalike — ModelRouter-নির্ভর, no CrewAI dep) + langgraph_agent.py (pure rename shim)
  - backend/adaptive_engine/resource_registry.py (restart/deploy/rollback NotImplemented — defect register-রেকর্ডকৃত)
  - backend/core/orchestration/cloud_sandbox_orchestrator.py (ERR-G04 — provider="local" branch missing → HTTP 500)
  - "docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md ERR-F01 (Run bridge: pending_tasks→HITL ও execution_logs writers test-only/dormant) + ERR-G04"
  - "docs/plans/UNIFIED_NEXT_ROADMAP_2026-09-15.md (M1 Run fabric — code complete; sequencing: \"Run before Context\")"
  - README.md Constitution #5 (Verify Before Trust), #6 (Policy Before Power), #8 (Graceful Degradation), #10 (One System, Many Execution Surfaces), #12 (Least Privilege), #13 (No Silent Failure)
implements:
  - SupremeKernel-কে *প্রয়োগগত* একমাত্র প্রবেশদ্বার করা — কোডে docstring-দাবি আছে (`backend/core/kernel/dispatcher.py`), প্রয়োগে ৪ প্রজন্ম orchestrator সহ-বিদ্যমান; এই নীলনকশা flag-নিয়ন্ত্রিত shadow→cutover→retirement সিঁড়ি দেয়
  - ERR-F01 Run-bridge সম্পূর্ণকরণ — pending_tasks→HITL ও execution_logs writers-কে প্রোডাকশন-wired করা, যাতে প্রতিটি কাজ সত্যিই পর্যবেক্ষণযোগ্য হয়
  - Constitution #10 "One System, Many Execution Surfaces"-এর পূর্ণতা — user-work/research/maintenance সব একই task-machinery দিয়ে
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (fresh main 07604ad: dispatcher.py head-30 পাঠ — single-door/FCC/legacy-fallback docstring স্বয়ং কোডে; swarm_orchestrator.py grep 'class SwarmOrchestrator' hit; conversation_orchestrator.py L73 class + wc 422; orchestrator.py wc 13; runs/ ও runs/tests ls-verified; crewai_agents.py/langgraph_agent.py agent-audit-রেকর্ডকৃত; resource_registry L123–129 ও cloud_sandbox provider-gap উৎস defect register — register স্বয়ং প্রাথমিক উৎস হিসেবে cited)"
code_evidence:
  - "backend/core/kernel/dispatcher.py L1–30 — docstring নিজেই দাবি করে: \"Governed Single-Door Entry Facade… Routes through the FCC federation… Falls back to the legacy flat registry\" — অর্থাৎ single-door *নকশায়* আছে, fallback-পথেই পুরনো প্রজন্ম এখনো জীবিত"
  - backend/core/orchestration/orchestrator.py — 13 লাইনের shim (wc-verified) — পুরনো import-পথ ভাঙতে না দেওয়ার অবশেষ; ৪ প্রজন্ম সহ-বিদ্যমানতার প্রমাণ
  - backend/core/orchestration/swarm_orchestrator.py — class SwarmOrchestrator (grep-verified) — DAG execution + tool synthesis বাস্তব
  - backend/core/orchestration/conversation_orchestrator.py L73 — class ConversationOrchestrator, 422 লাইন — capability registry + policy gateway, live dispatch
  - backend/core/orchestration/agent_orchestrator.py + master_cognitive_orchestrator.py — সমান্তরাল প্রজন্ম (ls-verified) — একই দায়িত্বের আরও বাস্তবায়ন
  - backend/runs/state_machine.py + budgets.py + retry.py + hitl.py + bridges.py — 12-state Run fabric বাস্তব; bridges.py-ই ERR-F01-এর অসম্পূর্ণ সেতু
  - backend/missions/ + backend/runtime/ — mission state machine ও canonical runtime আলাদা দ্বীপে বাস্তব
  - backend/core/agents/framework/crewai_agents.py + langgraph_agent.py — বাইরের ফ্রেমওয়ার্কের lookalike/shim — orchestration-এর ভাঙা অভিন্নতার আরও প্রমাণ
  - backend/adaptive_engine/resource_registry.py L123–129 — restart/deploy/rollback NotImplementedError (defect register)
  - backend/core/orchestration/cloud_sandbox_orchestrator.py — provider="local" শাখা অনুপস্থিত → HTTP 500 (defect register ERR-G04)
test_evidence: "none yet — প্রতিটি Phase-এর execution প্ল্যান সংজ্ঞায়িত করবে; সমষ্টিগত চুক্তি: (১) kernel shadow-mode parity টেস্ট (legacy বনাম kernel dispatch ফল-সমতা স্যাম্পল-রুটে), (২) bridge writers-এর integration টেস্ট (HITL রাউটিং + execution_logs row), (৩) backend/tests/runs/ ও backend/tests/orchestration/ zero regression, (৪) flag-off → byte-সমতুল্য legacy আচরণ"
acceptance_criteria:
  - "প্রতিটি Phase আলাদা ছোট execution প্ল্যান হিসেবে Gate 0–6 পাস"
  - "Kernel single-door সংজ্ঞা: নতুন প্রতিটি capability-dispatch ডিফল্টে dispatcher.py দিয়ে যায়; legacy fallback flag-gated; shadow-parity পরিমিত"
  - "Run-bridge সংজ্ঞা: HITL-অপেক্ষমাণ কাজ pending_tasks থেকে HITL-এ পৌঁছায়, প্রতিটি execution execution_logs-এ row লেখে — দুটোই প্রোডাকশন-পথে (টেস্ট-নিষ্ঠা নয়)"
  - "721-route surface-এ zero regression — প্রতিটি Phase-এর PR-এ CI প্রমাণ"
  - "নতুন dependency/infra শূন্য; কোনো route মুছে না যায় — শুধু রাউটিং-পথ একত্রিত হয়"
test_evidence_note: "Gate 4-এ shadow-parity ও bridge integration টেস্ট; Gate 5-এ live — বাস্তব কাজের run_id-সহ execution_logs row + HITL routing পর্যবেক্ষণ; completion claim-এর আগে বাধ্যতামূলক"
risk_and_rollback:
  - "সবচেয়ে বড় ঝুঁকি: 721-route live surface-এ রাউটিং-পরিবর্তন — প্রশমন: কোনো cutover নয় যতক্ষণ না shadow-parity ১০০% (sampled); flag-off → আজকের আচরণ; প্রতি Phase স্বাধীন"
  - "Legacy callers ভাঙার ঝুঁকি — প্রশমন: orchestrator.py shim অপসারণ সবশেষ ধাপ, তাও deprecation warning-পর্বের পর; import-path অক্ষত"
  - "Bridge writers-এর ডেটা-ভার (P-B): execution_logs স্ফীতি — প্রশমন: বিদ্যমান db-retention workflow (.github/workflows/db-retention.yml) পুনঃব্যবহার"
  - "ERR-G04 ফিক্স নতুন ব্যর্থতা-মোড আনতে পারে — প্রশমন: provider='local' branch প্রথমে explicit error-এ ব্যর্থ (fail-honest), তারপর বাস্তব বাস্তবায়ন"
  - "Rollback: প্রতিটি Phase = একক commit revert + flag; কোনো schema migration নেই"
baseline: "(hypothesis — Phase PR-এ মাপা হবে) আজ: নতুন dispatch-গুলোর কত শতাংশ kernel দিয়ে যায় তা অপরিমিত; HITL-রাউটিং প্রোডাকশনে অদৃশ্য (bridge dormant); ৪ প্রজন্মের কোন পথ কোথায় ব্যবহৃত — কোনো একক উত্তর নেই"
measurement_method:
  - "(a) kernel coverage: নতুন dispatch-গুলোর kernel-path শতাংশ (লগড)"
  - "(b) bridge-liveness: প্রতি ২৪ ঘণ্টায় execution_logs row + HITL transition সংখ্যা"
  - "(c) parity: shadow বনাম legacy dispatch ফল-সমতা শতাংশ"
  - "(d) regression: CI route-graph টেস্ট (tests/ root meta-tests) শূন্য-ব্যর্থতা"
success_threshold: "kernel coverage → >90% নতুন dispatch (target); bridge-liveness → প্রতিদিন >0 (hard threshold: শূন্য মানে bridge এখনো dormant); parity → 100% sampled (hard); সব সংখ্যা measured-হওয়া পর্যন্ত hypothesis"
plan_lifecycle: "living — Crown Jewel Module Series চক্র ২-এর প্রস্তাবিত নীলনকশা; single-plan discipline অটুট — কোনো Phase ফাউন্ডার-অনুমোদন-পূর্বে executable নয়; দর্শন-সংগতি পুনঃযাচাই 2026-09-17 branch crown-jewel-v2 (base ed35eaf): proposal-স্তরে ৪-নীতি অডিট (P-A shadow→sampled/non-blocking সংশোধিত) + মূল-যন্ত্রপাতি spot-check (orchestrator.py 13-LN, resource_registry NotImplemented L123-129, dispatcher fallback অটুট)"
---

# Crown Jewel Module Series — Module 02: Orchestration Core Power-Up

**Status:** proposed (ফাউন্ডার রিভিউ অপেক্ষমাণ — Gate 2 পূর্বে executable নয়)
**Owner:** Kernel Circle (`backend/core/kernel/` + `backend/core/orchestration/` + `backend/runs/` + `backend/runtime/`)
**Main anchor:** fresh main `07604ad` (2026-09-17)
**Resource delta:** 0 নতুন dependency / 0 নতুন infra / 0 নতুন CI cost / 0 schema migration / 0 route deletion

## বাংলা সারসংক্ষেপ

যদি মেমোরি (Module 01) SupremeAI-র *স্মৃতি* হয়, orchestration core তার *মেরুদণ্ড* — প্রতিটি ব্যবহারকারীর লক্ষ্য, প্রতিটি এজেন্ট-কল, প্রতিটি টুল-ব্যবহার কোনো না কোনো orchestrator দিয়ে যায়। আজ এই মেরুদণ্ডে এক বিরল বিরোধাভাস: **নকশা বিশ্বমানের, বাস্তবতা চার-প্রজন্মের স্তূপ**। একদিকে `backend/core/kernel/dispatcher.py` — SupremeKernel — যার নিজের docstring-ই দাবি করে "Governed Single-Door Entry Facade": প্রতিটি অনুরোধ প্রমাণীকৃত, tenant-যাচাইকৃত, FCC-federation দিয়ে Governance/Execution/Evolution/Infrastructure circles-এ রাউটেড, policy+circuit-breaker সহ। অন্যদিকে সেই এক-দরজার ভেতরেই চারটি প্রজন্ম একসাথে বাস করে: SwarmOrchestrator (`swarm_orchestrator.py`), ConversationOrchestrator (`conversation_orchestrator.py` L73), agent/master-cognitive orchestrator, এবং ১৩-লাইনের অবশেষ `orchestrator.py` shim। ফলাফল: একই দায়িত্বের চার বাস্তবায়ন, নতুন কোড কোন দরজা ব্যবহার করবে তা অনির্দিষ্ট, আর M1-এর গর্বের Run fabric (`backend/runs/`) — যার 12-state machine, budget, retry, HITL সব বাস্তব — তার দুটি সেতু (ERR-F01) এখনো টেস্ট-দ্বীপে বন্দি: বাস্তব কাজের execution_logs-এ row পড়ে না, HITL-রাউটিং প্রোডাকশনে অদৃশ্য।

এই নীলনকশা মেরুদণ্ডকে crown-jewel স্তম্ভে তোলে ৫ ধাপে: **(A)** kernel single-door *প্রয়োগে* (shadow-mode parity → flag-cutover → পুরনো পথ flag-gated) → **(B)** ERR-F01 সেতু সম্পূর্ণ → **(C)** missions assigner-এর governed আধুনিকীকরণ → **(D)** চার-প্রজন্ম retirement সিঁড়ি → **(E)** ERR-G04 fail-honest ফিক্স। প্রতিযোগীরা প্রমাণ করেছে সাফল্য এখানেই নির্ধারিত হয়: LangGraph-এর durable graph, OpenAI Agents SDK-র সংক্ষিপ্ত handoff, Temporal-এর durable execution — প্রত্যেকে *একটাই* নিয়ন্ত্রণ-কেন্দ্রে জেতে। SupremeAI-র নিজস্ব কেন্দ্র ইতিমধ্যেই নির্মিত — শুধু সেটিকে একমাত্র দরজা করতে হবে। মজার ব্যাপার: এই মডিউলে কাজটি বেশিরভাগ *বিয়োগফল* — নতুন কিছু যোগ নয়, পুরনো পথগুলো এক দরজায় একত্রিত করা (কৌশল-নথির মতেই "planning job is subtractive")।

---

## Part 1 — Competitor Intelligence (established patterns; fresh-dated citations পরবর্তী চক্রে সংগ্রহ হবে — এ চক্রে design-pattern observation হিসেবে labeled)

### ২.১ LangGraph — durable graph state machine

- LangGraph-এর মূল শক্তি: একক graph state machine + checkpoint/resume — প্রতিটি এজেন্ট-কল একই মেশিনে, একই ট্রেসে (established vendor pattern)।
- SupremeAI-র সংযোগবিন্দু: `backend/runs/state_machine.py` (12-state) + `backend/missions/` ইতিমধ্যেই এই মতবাদে নির্মিত — খালি জায়গা হলো সেগুলোর *সর্বজনীন গ্রহণ*। মজা: `backend/core/agents/framework/langgraph_agent.py` বাস্তব LangGraph নয় — rename shim (agent-audit)।

### ২.২ OpenAI Agents SDK — handoff-ভিত্তিক সরলতা

- OpenAI-র Agents SDK ছোট প্রিমিটিভ (agent + handoff + guardrail) দিয়ে orchestration সরল রাখে (established vendor pattern)।
- শিক্ষা: নিয়ন্ত্রণ-কেন্দ্র যত ছোট ও অভিন্ন, রচনাযোগ্যতা তত বড়। SupremeKernel-এর interface (`backend/core/kernel/interface.py` — KernelRequest/KernelResponse/CircleScope) ঠিক সেই ছোট প্রিমিটিভ — খালি জায়গা হলো সবার একই প্রিমিটিভ ব্যবহার নিশ্চিত করা।

### ২.৩ CrewAI — role-based crews

- CrewAI role/goal/backstory-ভিত্তিক crew রচনা জনপ্রিয় করেছে (established vendor pattern)।
- SupremeAI-র সংযোগবিন্দু: `backend/core/agents/framework/crewai_agents.py` একটি *হাতে-লেখা lookalike* — কোনো CrewAI dependency নেই, ModelRouter-নির্ভর (agent-audit)। অর্থাৎ প্যাটার্নটি আয়ত্ত; কিন্তু এটিও kernel-দরজার বাইরে আলাদা দ্বীপে — retirement/cutover-এর অংশ।

### ২.৪ Temporal — durable execution

- Temporal প্রমাণ করেছে দীর্ঘ-চলা workflow-এর জয় durable state + automatic retry + visibility-তে (established vendor pattern)।
- SupremeAI-র সংযোগবিন্দু: `backend/runs/`-এর retry classes + budgets + HITL + `backend/runtime/` executor একই ত্রিমুখী দর্শন (state + retry + visibility) — খালি জায়গা ERR-F01: visibility-র writers প্রোডাকশনে জাগেনি।

### ২.৫ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল (fresh main 07604ad-verified)

| প্রতিযোগী | যা করে | SupremeAI আজ (07604ad-verified) | গ্যাপ |
|---|---|---|---|
| LangGraph | একক durable graph machine | 12-state Run machine আছে (`backend/runs/state_machine.py`) কিন্তু সর্বজনীন নয় | Phase A+B |
| OpenAI Agents SDK | ছোট অভিন্ন প্রিমিটিভ | Kernel interface আছে (`backend/core/kernel/interface.py`) কিন্তু সবাই ব্যবহার করে না | Phase A |
| CrewAI | role-crew রচনা | lookalike বিদ্যমান (`backend/core/agents/framework/crewai_agents.py`) — দ্বীপে | Phase D |
| Temporal | durable state+retry+visibility | state+retry আছে; visibility writers dormant (ERR-F01) | Phase B |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main 07604ad, 2026-09-17)

| বিদ্যমান | বিষয় | এই নীলনকশার সাথে সম্পর্ক |
|---|---|---|
| PLAN_001–006 সিরিজ | মেমোরি/ক্যাশ/repo-map/compaction | ভিন্ন সাবসিস্টেম — সম্পর্কহীন; Module 01-এর সাথে *সম্পূরক* (মেমোরি লেখা → Run fabric-এ অনুলেখ্যতা) |
| `docs/plans/UNIFIED_NEXT_ROADMAP_2026-09-15.md` M1 | Run fabric code-complete | এই নীলনকশার Phase B হলো M1-এর শেষ মাইল (ERR-F01) — ওভারল্যাপ নয়, সমাপ্তি |
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` ERR-F01/ERR-G04 | bridge/branch ঘাটতি | এই নীলনকশার Phase B/E সরাসরি নিরাময় — alignment |
| `docs/plans/federated-capability-circles-topology` (active) | FCC circles টপোলজি | নকশা-স্তর; এই নীলনকশা তার *প্রয়োগ*-স্তর (single-door enforcement) — সম্পূরক |
| `docs/plans/external-agent-orchestration-layer-canonical-v3` (active) | বাহ্যিক এজেন্ট orchestration | ভিন্ন স্তর (external); ভিতরের ৪-প্রজন্ম একীকরণ এর ভিত্তি মজবুত করে — সম্পূরক |
| `docs/plans/features/orphan_components_wiring_master_plan.md` | orphan-wiring মতবাদ | দর্শনে অভিন্ন ("finishing what was built"), পরিসরে ভিন্ন (frontend-orphan বনাম backend-kernel) — সম্পূরক |

**গ্রেপ-যাচাই:** fresh main 07604ad-এ কোনো বিদ্যমান ডকুমেন্ট kernel single-door *প্রয়োগ*-সিঁড়ি (shadow→cutover→retirement), ERR-F01 bridge সম্পূর্ণকরণ বা ৪-প্রজন্ম retirement ladder-এর execution-নীলনকশা দেয় না — সম্পূর্ণ unclaimed (`docs/plans/` recursive grep, 2026-09-17)।

---

## Part 2 — Six-Field Complete Plan

### ২.১ কী আছে (কোড-যাচাইকৃত)

1. **SupremeKernel (নকশায় একক-দরজা):** `backend/core/kernel/dispatcher.py` — প্রমাণীকরণ + tenant-যাচাই + FCC-federation routing + policy/circuit-breakers + trace/audit; `backend/core/kernel/interface.py` — ছোট প্রিমিটিভ চুক্তি।
2. **SwarmOrchestrator:** `backend/core/orchestration/swarm_orchestrator.py` — DAG execution + tool synthesis (grep-verified)।
3. **ConversationOrchestrator:** `backend/core/orchestration/conversation_orchestrator.py` L73, 422 লাইন — capability registry + policy gateway, live dispatch।
4. **Run fabric (M1):** `backend/runs/` — state_machine.py (12-state), budgets.py, retry.py, hitl.py, api.py, service.py; `backend/tests/runs/` ৭ টেস্ট-ফাইল।
5. **Missions:** `backend/missions/` — state machine + traces + repair loop।
6. **Canonical runtime:** `backend/runtime/` — planner + budget guard + executor।
7. **FCC circles:** `backend/core/circles/` — Governance/Execution/Evolution/Infrastructure চুক্তি (dispatcher import থেকে প্রমাণিত)।
8. **Legacy-fallback নিরাপত্তা:** dispatcher নিজেই "never breaks pre-FCC callers" fallback রাখে — cutover-এর নিরাপদ seam।

### ২.২ কী নেই (কোড-যাচাইকৃত অনুপস্থিতি)

1. **প্রয়োগে single-door** — ৪ প্রজন্ম সহ-বিদ্যমান; `orchestrator.py` 13-LN shim পুরনো import-পথ জীবিত রেখেছে; কোন dispatch কোন পথে যায় — অপরিমিত।
2. **ERR-F01 সেতু:** pending_tasks→HITL ও execution_logs writers test-only/dormant — বাস্তব কাজের পর্যবেক্ষণযোগ্যতা অসম্পূর্ণ।
3. **Missions assigner:** documented stub (auto-agent-v1, LLM-call নেই)।
4. **ERR-G04:** `cloud_sandbox_orchestrator.py`-এ provider="local" শাখা অনুপস্থিত → HTTP 500।
5. **resource_registry বাস্তবায়ন:** restart/deploy/rollback NotImplemented (`backend/adaptive_engine/resource_registry.py` L123–129, register-উৎস)।
6. **ক্যানসেলেশন প্রোপাগেশনের অভাব:** ইউজার কাজ ক্যানসেল করলে ব্যাকগ্রাউন্ডে ইন-ফ্লাইট এলএলএম কল চলতে থাকে এবং টোকেন অপচয় ঘটে।

### ২.৩ কী করতে হবে (মেরুদণ্ড-একীকরণের ৭ ধাপ)

```text
P-A: Kernel single-door প্রয়োগে   → shadow-mode parity → flag-cutover → legacy path flag-gated
P-B: ERR-F01 সেতু সম্পূর্ণ         → pending_tasks→HITL + execution_logs writers প্রোডাকশনে
P-C: Missions assigner আধুনিকীকরণ → governed LLM assignment, flag-এর পিছনে
P-D: চার-প্রজন্ম retirement সিঁড়ি  → deprecation warning → path-consolidation → shim অপসারণ (সবশেষে)
P-E: ERR-G04 fail-honest ফিক্স    → provider="local" explicit branch
P-F: রান-লেভেল ক্যানসেলেশন ও টাইমআউট প্রোপাগেশন → CancellationToken দিয়ে ইন-ফ্লাইট LLM কল ইনস্ট্যান্ট টার্মিনেট
P-G: ডুয়াল-ড্রাইভেন গভর্নেন্স ও বাজেট কাপলিং → Admin Mission Control বনাম Customer Scope + বাজেট এক্সহস্টেশনে অটো-পজ
```

### ২.৪ কীভাবে করব (ফাইল-স্তরের দিক-নির্দেশ, প্রতিটি Phase আলাদা execution প্ল্যান)

- **P-A:** dispatcher-এ dispatch-mode flag (SUPREMEAI_KERNEL_DOOR=shadow|enforce) — enforce-পর্বে নতুন dispatch ডিফল্ট kernel-path; legacy fallback থাকে কিন্তু flag-gated। **Shadow হট-পথ ভার হবে না (fast-smooth সংশোধন):** shadow-পর্বে দুই পথ *প্রতি অনুরোধে* চলবে না — shadow-parity **sampling-চালিত** (sample-rate env-পঠিত, ডিফল্ট নিম্ন/বন্ধ; zero-hardcode), shadow-শাখা কখনো ব্যবহারকারী-উত্তর ব্লক করবে না (ফল-তুলনা async লগে); অর্থাৎ ব্যবহারকারীর বিলম্ব/খরচ অপরিবর্তিত। **কী টচ হবে না:** `KernelRequest/KernelResponse` সিগনেচার, কোনো route, কোনো এজেন্ট।
- **P-B:** `backend/runs/bridges.py`-এর দুই writer-কে বাস্তব callers-এ wire (অটোমেশন/অর্কেস্ট্রেশন পথ); `backend/tests/runs/`-এ integration টেস্ট; retention `.github/workflows/db-retention.yml`-এ বিদ্যমান। **কী টচ হবে না:** state machine-এর 12-state চুক্তি।
- **P-C:** assigner-stub → ModelRouter-নির্ভর governed assignment, flag SUPREMEAI_MISSIONS_LLM_ASSIGNER=true (default false); ব্যর্থতা → আজকের stub-আচরণ (Graceful Degradation #8)।
- **P-D:** ধাপ ১: agent/master-cognitive-এ deprecation warning + kernel-পথে রিডাইরেক্ট; ধাপ ২: callers মাইগ্রেশন পরিমাপ; ধাপ ৩: shim অপসারণ — তবে কেবল baseline-N ratchet নীতিতে, শেষ ধাপে।
- **P-E:** provider="local" শাখায় প্রথমে fail-honest explicit error (NotImplemented-রিপোর্ট, কোনো 500 নয়), পরে আলাদা অনুমোদনে বাস্তব বাস্তবায়ন — defect register-র এক-লাইন নিরাময়।
- **P-F (রান-লেভেল ক্যানসেলেশন ও টাইমআউট প্রোপাগেশন):**
  - কার্নেল ডিসপ্যাচে প্রতিটি রানের জন্য একটি অ্যাসিঙ্ক `CancellationToken` বাইন্ড করা।
  - ইউজার রিকোয়েস্ট ক্যানসেল করলে বা রান টাইমআউট হলে কার্নেল সাথে সাথে সিগন্যাল পাঠিয়ে চাইল্ড সাব-টাস্ক এবং Module 03 LLM Gateway-র সক্রিয় HTTP কানেকশন অবলুপ্ত করবে, যা অপচয় হওয়া টোকেন কস্ট শূন্যে নামিয়ে আনবে।
- **P-G (ডুয়াল-ড্রাইভেন গভর্নেন্স ও বাজেট কাপলিং):**
  - `AGENTS.md Rule 7` অনুসারে কার্নেল ডিসপ্যাচার `admin_override` বনাম `customer_user` রিকোয়েস্ট পৃথক স্কোপ ও কঠোর RBAC চেক দিয়ে প্রসেস করবে।
  - Module 03 Gateway-র বাজেট এক্সহস্ট হলে কার্নেল স্টেট মেশিন রানকে ক্র্যাশ না করিয়ে স্বয়ংক্রিয়ভাবে `PAUSED_BUDGET_EXHAUSTED` স্টেটে নেবে এবং গ্রাহককে বাজেট টপ-আপ বা HITL অনুমোদনের অপশন দেবে।

### ২.৫ বেনিফিট (সবই hypothesis — Gate 5-এ measured হবে)

1. **এক দরজা = এক সত্য:** প্রতিটি dispatch-এর policy/audit/trace অভিন্ন — Constitution #6 "Policy Before Power" প্রয়োগে সত্য হয়।
2. **পর্যবেক্ষণযোগ্যতা পূর্ণ (P-B):** বাস্তব কাজের execution_logs + HITL — "কী হলো, কেন থামলো" প্রশ্নের উত্তর কোডে-স্থায়িত; Run fabric-এর মান ১০০% বাস্তবায়িত।
3. **রানঅ্যাওয়ে টোকেন কস্ট প্রতিরোধ (P-F):** ক্যানসেলেশন ও টাইমআউট প্রোপাগেশনের কারণে বাতিল হওয়া কাজের পেছনে আর কোনো ক্লাউড মডেল বিল হবে না।
4. **ডুয়াল-ড্রাইভেন নিরাপত্তা (P-G):** অ্যাডমিন পূর্ণ টেলিমেট্রি দেখবে, আর গ্রাহক পাবে নিরাপদ আইসোলেটেড এক্সপেরিয়েন্স।
5. **রচনাযোগ্যতা বাড়ে:** নতুন প্রতিটি ক্ষমতা kernel-প্রিমিটিভে সস্তায় সংযুক্ত — ৪ প্রজন্মের কোনটা কোথায় তা-জানা-প্রয়োজনীয়তা মরে।
6. **Module 01-এর সাথে সিনার্জি:** মেমোরি-লেখাও এক দরজা দিয়ে গেলে run-anchored traceability (Module 01 P-E) স্বয়ংক্রিয় সস্তা।
7. **কোড-হ্রাস:** retirement-পর্বে সমান্তরাল বাস্তবায়নের রক্ষণ-বোঝা কমে (hypothesis — পরিমিত হবে অপসারিত-লাইন-গণনায়)।

### ২.৬ ক্ষতি/ঝুঁকি (সৎ, প্রশমন সহ)

1. **721-route surface-এ regression:** সবচেয়ে বড় ঝুঁকি — প্রশমন: shadow-first (sampled, non-blocking — §২.৪ P-A), parity ১০০% ছাড়া cutover নয়, flag-off = আজকের আচরণ, প্রতি Phase স্বাধীন revert।
2. **দ্বিগুণ-লেখা খরচ (P-B):** execution_logs স্ফীতি — প্রশমন: বিদ্যমান retention workflow; row আকার সীমিত।
3. **ক্যানসেলেশন রেইস কন্ডিশন (P-F):** টাস্ক সমাপ্তির মুহূর্তে ক্যানসেল সিগন্যাল আসা — প্রশমন: ডিটারমিনিস্টিক লক ও টার্মিনাল স্টেট প্রোটেকশন (`assert_transition`)।
4. **Retirement অকালে কিছু ভাঙা (P-D):** লুকানো caller — প্রশমন: warning-পর্বে caller-পরিমাপ, shim সবশেষে; প্রতিটি অপসারণে root-tests সূচি।
5. **Kernel এক-বিন্দু-ব্যর্থতা ঝুঁকি:** সব দরজা এক হলে দরজা-ব্যর্থতা বড় দুর্ঘটনা — প্রশমন: dispatcher-এ ইতিমধ্যে circuit-breakers + legacy-fallback নকশায় আছে (`backend/core/kernel/dispatcher.py` docstring); flag-off চিরস্থায়ী escape।
6. **পরিসর-ঝুঁকি:** kernel-refactor-এর ঘুরপথে নতুন ফিচার-লোভ — প্রশমন: এই নীলনকশায় কোনো নতুন ফিচার নেই; শুধু একীকরণ; প্রতিটি Phase আলাদা Gate 0–6।

---

## Part 3 — Explicit Out-of-Scope

1. নতুন orchestration framework/dependency (বাস্তব LangGraph/CrewAI/Temporal আমদানি নয়) — lookalike ও নিজস্ব kernel-ই যথেষ্ট।
2. Kernel API-র breaking change — `KernelRequest/KernelResponse` অপরিবর্তিত।
3. কোনো route/frontend পরিবর্তন — backend রাউটিং-স্তর মাত্র।
4. resource_registry-র restart/deploy বাস্তবায়ন — আলাদা ভবিষ্যৎ প্ল্যানের প্রার্থী (এখানে কেবল register-এ উল্লিখিত)।
5. External-agent layer (EAOL) পরিবর্তন — ভিন্ন canonical প্ল্যানের পরিসর।
6. সমান্তরাল multi-plan execution — একসময়ে একটাই Phase active।

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | প্রতিটি Phase আলাদা proposed execution; একসময়ে একটাই active |
| 2. Small change to existing code | ✅ | flag+branch বিদ্যমান ফাইলে; নতুন কোড কেবল টেস্টে |
| 3. No new infrastructure | ✅ | বিদ্যমান CI/DB/workflow; migration শূন্য |
| 4. No CI cost amplification | ✅ | shadow-parity টেস্ট লোকাল-নির্ধারিত; নতুন শাখা নয় |
| 5. No credit-burn risk | ✅ | P-C assigner flag-gated, default বন্ধ |
| 6. No academic leaderboard | ✅ | সরাসরি প্রোডাক্ট-ক্ষমতা: coverage, liveness, parity |
| 7. Realistic resource budget | ✅ | লগ-লেখা নিয়ন্ত্রিত; retention বিদ্যমান |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main 07604ad head/wc/grep-যাচাই; register-উৎস স্পষ্ট |

| Constitution ধারা | প্রভাব |
|---|---|
| #5 Verify Before Trust | ✅ shadow-parity ও bridge integration টেস্ট বাধ্যতামূলক |
| #6 Policy Before Power | ✅ single-door = প্রতিটি কাজে অভিন্ন policy gate |
| #8 Graceful Degradation | ✅ flag-off → legacy; assigner ব্যর্থ → stub |
| #10 One System, Many Execution Surfaces | ✅ চার প্রজন্ম → এক machinery |
| #12 Least Privilege, Maximum Capability | ✅ kernel policy-gate প্রয়োগে প্রতিটি dispatch-এ |
| #13 No Silent Failure | ✅ ERR-G04 fail-honest; bridge liveness পরিমিত |

---

## Part 5 — Verification & Acceptance (Gates 4–6) + Rollback

- **Gate 4 (প্রতি Phase):** `pytest backend/tests/runs/ backend/tests/orchestration/` শূন্য-ব্যর্থতা; P-A shadow-parity টেস্ট; P-B integration টেস্ট (HITL transition + logs row); P-D প্রতি অপসারণে root meta-tests (`tests/` route-graph) পাস।
- **Gate 5 (live):** বাস্তব কাজে kernel-coverage শতাংশ (লগড); ২৪-ঘণ্টায় execution_logs row >0; HITL transition পর্যবেক্ষিত; parity শতাংশ প্রকাশিত।
- **Gate 6:** প্রতিটি Phase নিজস্ব execution প্ল্যানে complete; এই নীলনকশা complete যখন acceptance_criteria-র পাঁচটি সংজ্ঞা সবই evidence-সহ সত্য।
- **Rollback:** প্রতিটি Phase = একক commit revert + flag-off; কোনো schema/data-loss path নেই; shim অপসারণ শেষ ও সবচেয়ে সাবধান ধাপ — তারও revert-পথ: git revert একক commit।

---

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Pass, 2026-09-17, branch `crown-jewel-v2`)

প্রতিষ্ঠাতা-নির্দেশিত চার মূল-দর্শনের আলোকে proposal-স্তর অডিট:

| দর্শন | রায় | ভিত্তি |
|---|---|---|
| Zero cost | ✅ সংগত | 0 নতুন dependency/infra; P-C assigner flag-gated default বন্ধ; কাজ বেশিরভাগ বিয়োগফল |
| Lightweight | ✅ সংগত | নতুন framework আমদানি স্পষ্টভাবে বাইরে (Part 3-1); legacy-fallback seam পুনঃব্যবহার |
| Fast & smooth | ⚠️ ছিল → ✅ **সংশোধিত** | P-A আগে প্রতি-অনুরোধে দ্বি-পথ (shadow) চালাত — হট-পথে দ্বিগুণ বিলম্ব/গণনা; এই পাসে sampled + non-blocking shadow (§২.৪ সংশোধিত) |
| Zero hardcode | ✅ সংগত | সব mode/flag env-চালিত; sample-rate-ও env-পঠিত (এই পাসে স্পষ্ট); কোনো স্থির ম্যাজিক-সংখ্যা প্রস্তাব নেই |

মূল-যন্ত্রপাতি spot-check (base `ed35eaf`): `orchestrator.py` 13-LN shim অটুট; `resource_registry.py` L123–129 NotImplemented অটুট; dispatcher pre-FCC fallback অটুট।

স্কোপ-সততা: proposal-দর্শন অডিট + মূল-যন্ত্রপাতি spot-check; সম্পূর্ণ line-ref re-verification নয়।

---

## Part 6 — পরবর্তী চক্র লাইনেজ (reference-only; candidate list ≠ execution queue)

- **চক্র ১ (প্রকাশিত):** Module 01 — Memory Subsystem → `MODULE_01_MEMORY_POWER_UP_2026-09-17.md`।
- **চক্র ৩ (কিউতে):** Module 03 — LLM Gateway & Model Routing (`backend/core/llm/` + `backend/services/llm/` + `backend/brain/model_router.py`) — inference-spine; এই মডিউলের P-B সম্পূর্ণ হলে run-তথ্য model-routing সিদ্ধান্তেও প্রবাহিত হবে।
- সূচি ও কিউ-পুনঃর‍্যাঙ্ক: `crown_jewel_series/README.md`।
