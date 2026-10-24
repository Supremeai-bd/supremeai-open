---
id: crown-jewel-module-06-run-fabric-completion-power-up-v1-2026-09-17
title: "Crown Jewel Module Series — Module 06: Run Fabric সম্পূর্ণকরণ Power-Up ('প্রতিটি কাজ পর্যবেক্ষণযোগ্য' চুক্তিকে সর্বজনীন করা — ৭/৮ পৃষ্ঠ অদৃশ্য থেকে সর্বজনীন adoption-এর পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Run Circle (backend/runs/ + backend/missions/ + backend/runtime/ + frontend runService সংযোগ-স্তর)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ৬ — একটি মডিউল (Run Fabric), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — fresh main 5b69c23 (2026-09-17) sed/grep/wc-যাচাইকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; Module 02 P-B-র সাথে স্পষ্ট সীমানা; প্রতিটি ধাপে flag+kill-switch; 721-route surface-এ zero-regression লক্ষ্য"
depends_on:
  - "backend/runs/state_machine.py (172 লাইন — 12 STATES + LEGAL_TRANSITIONS + assert_transition retry-guard L144-155 — pure-stdlib, টেস্ট-পিনকৃত)"
  - "backend/runs/service.py (RunService 548 লাইন — create/transition/check_run_budgets/record_usage/classify_failure/request_retry/cancel/finalize/request_approval/resolve_approval)"
  - "backend/runs/models.py (Run + RunEvent + RunType ×৮ — alembic 2026_09_15_120000-এ উভয় টেবিল migrated)"
  - "backend/runs/api.py (279 লাইন — ৯ endpoint /api/v1/runs; backend/api/routers.py:431-এ মাউন্টেড sed-verified)"
  - "backend/runs/bridges.py (observe_mission/tool/mcp/automation_run — কেবল automation প্রোডাকশনে জাগ্রত)"
  - "backend/core/automation/execution_recorder.py (L383 observe_automation_run + L353 _run_bridge_finalize — একমাত্র জীবিত writer-পথ, best-effort)"
  - "backend/core/orchestration/conversation_orchestrator.py (L124-130 dispatch → persist_execution — fire-and-forget, sed-verified)"
  - "backend/missions/service.py (510 লাইন — 8-state + MAX_REPAIRS=3; _default_assigner L54-56 'always labels auto-agent-v1' sed-verified)"
  - "backend/runtime/task_executor.py (L58 `output = f'Processed solution for: {task.goal}'` — ফেব্রিকেটেড fallback sed-verified)"
  - "backend/runtime/budget_guard.py (60 লাইন — কেবল task_runtime-এর ২ স্থানে লাইভ; gateway/tools-এ অসংযুক্ত)"
  - "frontend/src/services/runService.ts (L52 — /api/v1/missions র‍্যাপ — /runs পৃষ্ঠা missions-ভিত্তিক, canonical /api/v1/runs-এর FE-consumer শূন্য)"
  - "MODULE_02_ORCHESTRATION_CORE_POWER_UP_2026-09-17.md (P-B: ERR-F01 bridge-writers — এই নীলনকশার সীমানা-রেফারেন্স)"
  - "docs/plans/UNIFIED_NEXT_ROADMAP_2026-09-15.md (M1 Run fabric code-complete; এই নীলনকশা = সর্বজনীনতা-মাইল)"
  - "docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md ERR-F01"
implements:
  - "সর্বজনীন adoption — chat/scheduled/missions/tools/MCP/browser-পৃষ্ঠে run-তৈরি (আজ কেবল automation ১টি জাগ্রত)"
  - "বাজেট-জাগরণ — record_usage ফিডার + BudgetGuard-প্রসারণ: অ্যাডমিশন-নিয়ন্ত্রণ প্রথমবার প্রোডাকশনে প্রয়োগ"
  - "সত্য-ড্যাশবোর্ড — /runs পৃষ্ঠা missions-মিথ্যা থেকে canonical /api/v1/runs-এ"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (fresh main 5b69c23: conversation_orchestrator.py L124-130 sed-verified persist_execution; task_executor.py L58 sed-verified ফেব্রিকেটেড output; missions/service.py L54-56 sed-verified no-LLM assigner; routers.py:431 sed-verified runs.api মাউন্ট; runService.ts L52 sed-verified missions-র‍্যাপ; runs/ wc=1,884; execution_recorder L353 _run_bridge_finalize sed-verified)"
code_evidence:
  - "backend/core/orchestration/conversation_orchestrator.py L124-130 — একমাত্র প্রোডাকশন run-writer: dispatch → execution_recorder.persist_execution (fire-and-forget) — অর্থাৎ ৮ RunType-এর ১টি জাগ্রত, ৭টি অদৃশ্য"
  - "backend/runs/service.py — record_usage/classify_failure/request_retry প্রোডাকশন-caller শূন্য (কেবল runs/api.py:207 HTTP-endpoint-ভিত্তিক) — কাউন্টার কেউ ফিড করে না, check_run_budgets কার্যত অপ্রয়োগ"
  - "backend/runs/api.py + backend/api/routers.py:431 — ৯ endpoint লাইভ কিন্তু FE-consumer শূন্য; frontend runService.ts L52 /api/v1/missions র‍্যাপ করে — /runs পৃষ্ঠায় দেখা 'runs' আসলে missions"
  - "backend/runtime/task_executor.py L58 — ব্যর্থতায় `Processed solution for: {goal}` — সফল-দেখতে ফেব্রিকেটেড আউটপুট (Constitution #13 লঙ্ঘন)"
  - "backend/core/automation/dispatcher.py — AutomationDispatcher-এর production importer শূন্য (কেবল tests/core/test_automation.py) → record_start→_run_bridge_create কখনো আগুন হয় না"
  - "backend/runtime/budget_guard.py — কেবল task_runtime-এর ২ স্থানে (server.py:230 /api/v1/process-পথ); gateway/tool-পথে অ্যাডমিশন-গার্ড নেই"
  - "backend/runs/bridges.py — observe_mission_run/observe_tool_run/observe_mcp_run কেবল টেস্টে; missions/models.py docstring-ই দাবি করে 'a mission's executions ARE runs' — কিন্তু mission-পথ run-row লেখে না"
  - "automation-bridge user_id='system' লেখে — tenant/user পরিচয় হারায়; runs-এ tenant-কলাম-ব্যবহার শূন্য"
  - "backend/runs/hitl.py — PendingTaskApprovalHook ডর্ম্যান্ট (hook প্রোডাকশনে wired নয় — Module 02 P-B সীমানার ফ্যাব্রিক-পক্ষ)"
test_evidence: "none yet — প্রতিটি Phase-এর execution প্ল্যান সংজ্ঞায়িত করবে; সমষ্টিগত চুক্তি: (১) run_scope integration টেস্ট (chat/scheduled/tool-পথে run-row + terminal-settle), (২) usage-feeder idempotency টেস্ট (দ্বি-গণনা শূন্য), (৩) বিদ্যমান ~4,043 টেস্ট-LOC (tests/runs/ ১,৯১৩ + tests/missions/ ১,২৬৭ + execution_recorder 321 সহ) zero regression — 12-state ও autoflush=False চুক্তি অটুট, (৪) flag-off → আজকের আচরণ"
acceptance_criteria:
  - "প্রতিটি Phase আলাদা ছোট execution প্ল্যান হিসেবে Gate 0–6 পাস"
  - "সর্বজনীনতা-সংজ্ঞা: ৮ RunType-এর প্রতিটির অন্তত একটি প্রোডাকশন-পথ run-row লেখে ও terminal-অবস্থায় পৌঁছায় (automation ব্যতীত ৭টি নতুন)"
  - "বাজেট-সংজ্ঞা: record_usage gateway/tool-পথ থেকে ফিড হয় (idempotent); check_run_budgets অ্যাডমিশন-সিদ্ধান্তে ব্যবহৃত — flag-gated"
  - "সত্য-UI সংজ্ঞা: /runs পৃষ্ঠা /api/v1/runs থেকে; missions-ভিউ গৌণ; FE-consumer >0 CI-প্রমাণসহ"
  - "সত্য-সংজ্ঞা: task_executor ফেব্রিকেটেড আউটপুট শূন্য; automation-bridge user_id প্রকৃত পরিচয়; zero-regression CI প্রমাণ"
test_evidence_note: "Gate 4-এ integration টেস্ট (run_scope/idempotency); Gate 5-এ live — ২৪-ঘণ্টায় প্রতিটি RunType-এ ≥১ run-row ও FINALIZE-sweep পর্যবেক্ষণ; completion claim-এর আগে বাধ্যতামূলক"
risk_and_rollback:
  - "সবচেয়ে বড় ঝুঁকি: উষ্ণ-পথে (chat) run-লেখা latency — প্রশমন: best-effort fire-and-forget প্যাটার্ন (execution_recorder-প্রমিত), async লেখা, flag default false, kill-switch"
  - "দ্বি-গণনা/রাষ্ট্র-বিকৃতি (P-B): usage ফিডে ডুপ্লিকেট — প্রশমন: idempotency-key (execution_recorder-প্যাটার্ন), প্রতি attempt একক flush"
  - "12-state চুক্তি-ভাঙা — প্রশমন: assert_transition অপরিবর্তিত; সব নতুন পথ বিদ্যমান state-machine দিয়েই; tests/runs/ ১,৯১৩-LOC রক্ষা"
  - "FE-পরিবর্তনে ব্যবহারকারী-বিভ্রান্তি (P-D): missions-ভিউ বদল — প্রশমন: missions-ভিউ গৌণ-ট্যাব হিসেবে অটুট; কেবল উৎস-পুনর্নির্দেশ"
  - "Rollback: প্রতিটি Phase = একক commit revert + flag-off; কোনো schema migration নেই (runs/run_events টেবিল বিদ্যমান)"
baseline: "(hypothesis — Phase PR-এ মাপা হবে) আজ: জাগ্রত RunType = 1/8 (automation); record_usage-ফিডকৃত প্রোডাকশন-পথ = 0; FINALIZE-প্রাপ্ত non-automation run = 0; /runs-পৃষ্ঠার সত্য-উৎস = missions (মিথ্যা-সংযোগ); runs/run_events retention = নেই"
measurement_method:
  - "(a) adoption-matrix: প্রতি RunType-এ ২৪-ঘণ্টায় run-row গণনা (লক্ষ্য: ৮/৮ প্রতিদিন >0)"
  - "(b) budget-liveness: record_usage ফিড-হার + check_run_budgets-দ্বারা প্রত্যাখ্যাত অ্যাডমিশন গণনা (flag-অনে)"
  - "(c) finalize-liveness: terminal→FINALIZED sweep-গণনা; stuck-run শূন্য >7d"
  - "(d) regression: tests/runs/ + tests/missions/ + route-graph meta-tests শূন্য-ব্যর্থতা; FE /runs উৎস-যাচাই"
success_threshold: "adoption → ৮/৮ RunType প্রতিদিন >0 (target; hard: শূন্য মানে সর্বজনীনতা এখনো নেই); budget-liveness → flag-অনে ফিড >0 (hard); stuck-run >7d → 0 (hard); /runs সত্য-উৎস → /api/v1/runs (hard); সব সংখ্যা measured-হওয়া পর্যন্ত hypothesis"
plan_lifecycle: "living — Crown Jewel Module Series চক্র ৬-এর প্রস্তাবিত নীলনকশা; single-plan discipline অটুট — কোনো Phase ফাউন্ডার-অনুমোদন-পূর্বে executable নয়"
---

# Crown Jewel Module Series — Module 06: Run Fabric সম্পূর্ণকরণ Power-Up

**Status:** proposed (ফাউন্ডার রিভিউ অপেক্ষমাণ — Gate 2 পূর্বে executable নয়)
**Owner:** Run Circle (`backend/runs/` + `backend/missions/` + `backend/runtime/` + FE runService সংযোগ-স্তর)
**Main anchor:** fresh main `5b69c23` (2026-09-17)
**Resource delta:** 0 নতুন dependency / 0 নতুন infra / 0 নতুন CI cost / 0 schema migration (টেবিল বিদ্যমান) / 0 route deletion

## বাংলা সারসংক্ষেপ

মেমোরি-অর্ক-গেটওয়ে-ব্রাউজারের পরে বাকি রইল প্ল্যাটফর্মের **জবাবদিহি-কঙ্কাল**: Run Fabric — "প্রতিটি কাজ একটি Run, প্রতিটি Run পর্যবেক্ষণযোগ্য" চুক্তি। আর এখানে মনোরম দুঃখটা হলো: *কঙ্কাল নিখুঁত, কিন্তু শরীর তাকে ব্যবহারই করে না*। `backend/runs/` (১,৮৮৪ লাইন) প্রায় নিখুঁত — 12-state pure-stdlib machine (retry-guard সহ), RunService-এর ১০টি পদ্ধতি, ৯টি লাইভ endpoint (`/api/v1/runs`, routers.py:431 মাউন্টেড), উভয় টেবিল alembic-migrated, ১,৯১৩-লাইন কঠোর টেস্ট। কিন্তু **৮ ধরনের Run-এর মাত্র ১টি জাগ্রত**: কেবল automation-পথ run-row লেখে (`conversation_orchestrator.py` L124-130 → `persist_execution`) — chat, scheduled tasks, missions, tools, MCP, browser সব **অদৃশ্য**। ফলে ডমিনো: record_usage-এর কেউ ফিড দেয় না → `check_run_budgets` কার্যত অপ্রয়োগ; FINALIZE-এ non-automation পৌঁছায়ই না; আর ব্যবহারকারী যে /runs পৃষ্ঠা দেখে সেটি আসলে **missions-API-র র‍্যাপ** (`runService.ts` L52) — নিজের আসল run-তালিকা নয়। সাথে runtime-এর নিজস্ব ক্ষত: `task_executor.py` L58 ব্যর্থতায় "Processed solution for: ..." জাদু-সাফল্য দেখায়, `budget_guard` কেবল /api/v1/process-এ সীমাবদ্ধ, আর AutomationDispatcher — যাকে ERR-F01-পথ "wired" বলা হয় — নিজেই অনাথ (production importer শূন্য)।

এই নীলনকশা কঙ্কালকে শরীর পরিধান করায় ৭ ধাপে: **(A)** run_scope ইনস্ট্রুমেন্টেশন-কিট (সর্বজনীন adoption) → **(B)** usage-ফিডার → **(C)** finalize-sweep + retention → **(D)** সত্য /runs ড্যাশবোর্ড → **(E)** AutomationDispatcher জাগরণ/অপসারণ + পরিচয়-সংশোধন → **(F)** BudgetGuard-প্রসারণ → **(G)** TaskRuntime↔runs ঐক্য + মিথ্যা-executor শুদ্ধি। **সীমানা-শৃঙ্খলা:** Module 02 P-B-র মালিকানা (ERR-F01 bridge-writers, pending_tasks→HITL) এখানে পুনরাবৃত্ত নয় — এই মডিউল তার *পরের* ধাপ: লেখক-ব্যবস্থা জাগ্রত হওয়ার পরে সব পৃষ্ঠকে একই চুক্তিতে আনা। প্রতিযোগী-শিক্ষা (Temporal/LangGraph-ধাঁচ durable-visibility): প্রতিটি execution-এর একক সত্য-রেকর্ডই প্ল্যাটফর্মের বিশ্বাসযোগ্যতার ভিত — আর SupremeAI-র সৌভাগ্য: রেকর্ড-মেশিন ইতিমধ্যে নিখুঁত; শুধু সবাইকে তার দরজায় আনতে হবে।

---

## Part 1 — Competitor Intelligence (established patterns; fresh-dated citations পরবর্তী চক্রে সংগ্রহ হবে — এ চক্রে design-pattern observation হিসেবে labeled)

### ৬.১ Temporal-ধাঁচ — প্রতিটি execution-এর স্থায়ী রেকর্ড

- Durable-execution সিস্টেমের মতবাদ: প্রতিটি workflow-execution-এর একক স্থায়ী রেকর্ড — state+retry+visibility একই রেকর্ডে (established pattern)।
- SupremeAI-র সংযোগবিন্দু: Run+RunEvent মডেল ঠিক এই দর্শনে — খালি জায়গা সর্বজনীন গ্রহণ (P-A), মেশিন নয়।

### ৬.২ usage-metering মতবাদ — বাজেট মাপা না হলে বাজেট নয়

- বিলিং-গ্রেড সিস্টেমে প্রতি-execution usage-metering একক পথে (established pattern)।
- SupremeAI-র সংযোগবিন্দু: record_usage/check_run_budgets API প্রস্তুত — ফিডারই নেই (P-B); Module 03-র খরচ-টেলিমেট্রির পরিপূরক স্তর।

### ৬.৩ lifecycle-sweeper — আটকে-থাকা রাষ্ট্রের পরিচ্ছন্নতা

- workflow-সিস্টেমে terminal-অবস্থায় অপৌঁছানো রেকর্ডের periodic sweep মানক (established pattern)।
- SupremeAI-র সংযোগবিন্দু: finalize-পদ্ধতি আছে, caller নেই; retention-workflow (db-retention.yml) বিদ্যমান — runs/run_events যোগ করলেই হয় (P-C)।

### ৬.৪ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল (fresh main 5b69c23-verified)

| প্যাটার্ন | যা করে | SupremeAI আজ (5b69c23-verified) | গ্যাপ |
|---|---|---|---|
| Temporal-ধাঁচ | প্রতি execution স্থায়ী রেকর্ড | Run-model নিখুঁত, কেবল ১/৮ পৃষ্ঠ লেখে | P-A |
| Usage-metering | প্রতি-execution metering | API আছে, ফিডার শূন্য | P-B |
| Lifecycle-sweep | terminal+retention | finalize-কলার শূন্য; runs-retention নেই | P-C |
| সত্য-visibility | একক সত্য-তালিকা | /runs missions-ভিত্তিক | P-D |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main 5b69c23, 2026-09-17)

| বিদ্যমান | বিষয় | এই নীলনকশার সাথে সম্পর্ক |
|---|---|---|
| `MODULE_02_ORCHESTRATION_CORE_POWER_UP_2026-09-17.md` P-B | ERR-F01 bridge-writers + pending_tasks→HITL | **স্পষ্ট সীমানা** — সেটি লেখক-ব্যবস্থা জাগরণ (automation-পথ ও HITL); এই মডিউল তার পরের সর্বজনীনতা-স্তর; ওভারল্যাপ নয়, ধারাবাহিকতা |
| `MODULE_03_LLM_GATEWAY_POWER_UP_2026-09-17.md` P-B | tenant_id প্রচার | সম্পূরক — gateway-র tenant-চাবি run-রেকর্ডের পরিচয়-সংশোধনেও (P-E) ব্যবহৃত হবে |
| `MODULE_05_SELF_EVOLUTION_POWER_UP_2026-09-17.md` | learning-loop | সম্পূরক — run-anchored উপাত্ত learning-স্রোতকে সমৃদ্ধ করবে |
| `docs/plans/UNIFIED_NEXT_ROADMAP_2026-09-15.md` M1 | Run fabric code-complete | এই নীলনকশা = M1-এর "সর্বজনীনতা" সমাপ্তি-মাইল — ওভারল্যাপ নয় |
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` ERR-F01 | bridge | সীমানা-রেফারেন্স (Module 02 P-B নিরাময়); এখানে কেবল ফ্যাব্রিক-পক্ষের অবশিষ্ট (hitl-hook ইত্যাদি) |
| `.github/workflows/db-retention.yml` | বিদ্যমান retention | P-C তাতে runs/run_events যোগ করবে — নতুন infra নয় |

**গ্রেপ-যাচাই:** fresh main 5b69c23-এ কোনো বিদ্যমান ডকুমেন্ট run_scope-সর্বজনীনতা, usage-ফিডার, finalize-sweep বা /runs-সত্য-পুনর্নির্দেশের execution-নীলনকশা দেয় না — সম্পূর্ণ unclaimed (`docs/plans/` recursive grep, 2026-09-17)।

---

## Part 2 — Six-Field Complete Plan

### ২.১ কী আছে (কোড-যাচাইকৃত)

1. **12-state machine:** `runs/state_machine.py` — pure-stdlib, LEGAL_TRANSITIONS, retry-guard; ২৯২-লাইন কঠোর টেস্ট।
2. **RunService:** ১০টি পদ্ধতি (create/transition/budgets/usage/classify/retry/cancel/finalize/approval); ৪৫৪-লাইন টেস্ট।
3. **API:** ৯ endpoint `/api/v1/runs` — routers.py:431 মাউন্টেড, লাইভ।
4. **Models+migration:** Run/RunEvent + RunType ×৮ — alembic-স্থায়িত্ব।
5. **এক জীবিত writer-পথ:** execution_recorder (best-effort, idempotency-key, non-blocking) → observe_automation_run + _run_bridge_finalize — প্যাটার্ন-প্রমাণ।
6. **Missions-মেশিন:** 8-state + MAX_REPAIRS=3 repair-loop; ১,২৬৭-লাইন টেস্ট।
7. **Runtime বীজ:** TaskRuntime ৫-ধাপ + BudgetGuard (২ স্থানে লাইভ) + TaskContext/TraceEvent।
8. **Bridges-সম্পদ:** observe_mission/tool/mcp/automation_run চারটি ফাংশন লেখা — তিনটি টেস্ট-দ্বীপে।

### ২.২ কী নেই (কোড-যাচাইকৃত অনুপস্থিতি)

1. **সর্বজনীন adoption** — ৭/৮ RunType-এর কোনো প্রোডাকশন-লেখক নেই (chat/scheduled/missions/tools/MCP/browser/automation-dispatcher)।
2. **usage-ফিডার** — record_usage-র স্বয়ংক্রিয় প্রোডাকশন-ফিড শূন্য; বাজেট-নিয়ন্ত্রণ কার্যত অপ্রয়োগ।
3. **finalize-sweep + retention** — non-automation FINALIZE-অপৌঁছ; runs/run_events retention নেই।
4. **সত্য-UI** — /runs missions-ভিত্তিক; canonical API-র FE-consumer শূন্য।
5. **পরিচয়** — bridge user_id='system'; tenant-পরিচয় শূন্য।
6. **সত্য-runtime** — task_executor ফেব্রিকেটেড সাফল্য; AutomationDispatcher অনাথ; BudgetGuard gateway/tools-বহির্ভূত নেই।

### ২.৩ কী করতে হবে (জবাবদিহি-কঙ্কালে শরীর পরিধানের ৭ ধাপ)

```text
P-A: run_scope কিট          → context-manager: chat/scheduled/tool/mission-পথে
                              run-তৈরি+terminal-settle (best-effort, flag-gated)
P-B: usage-ফিডার            → gateway/tool সমাপ্তিতে record_usage (idempotent)
P-C: finalize-sweep+retention → ব্যাকগ্রাউন্ড সুইপ terminal→FINALIZED; db-retention.yml-এ
                              runs/run_events যোগ
P-D: সত্য /runs             → runService.ts → /api/v1/runs; events-টাইমলাইন; missions গৌণ
P-E: dispatcher জাগরণ/অপসারণ → revive অথবা delete; bridge-এ প্রকৃত user/tenant পরিচয়
P-F: BudgetGuard-প্রসারণ    → gateway/tool অ্যাডমিশন-গার্ড (flag-gated, fail-open)
P-G: TaskRuntime↔runs ঐক্য  → TaskContract run-এর ভিতরে চলে; মিথ্যা-executor শুদ্ধি;
                              planner-LLM আপগ্রেড flag-এর পিছনে (ঐচ্ছিক)
```

### ২.৪ কীভাবে করব (ফাইল-স্তরের দিক-নির্দেশ, প্রতিটি Phase আলাদা execution প্ল্যান)

- **P-A:** নতুন পাতলা `run_scope()` context-manager (runs প্যাকেজে) — entry/exit-এ create/transition; chat.py, scheduled_tasks.py, tool-execution, missions-advance-পথে মোড়ানো; execution_recorder-প্যাটার্ন (best-effort, DB-ব্যর্থতায় চলতে-থাকা); flag `SUPREMEAI_RUN_FABRIC_UNIVERSAL=true` (default false)।
- **P-B (Gateway UsageSettlement ও রান-লেভেল কস্ট রোলআপ):**
  - run_scope-সমাপ্তিতে (P-A-নির্মিত run-এ) record_usage কল হবে।
  - এটি সরাসরি Module 03 LLM Gateway-র `UsageSettlement` এবং `InferenceContext(run_id=...)`-এর সাথে সিঙ্ক হবে — ফলে একটি রানের অধীনে যতগুলো চাইল্ড এজেন্ট বা টুল কল হয়েছে, তাদের সমষ্টিগত টোকেন ও রিয়েল-ডলার খরচ স্বয়ংক্রিয়ভাবে সংশ্লিষ্ট `Run` রেকর্ডে রোল-আপ হয়ে সংরক্ষিত হবে।
  - idempotency-key = attempt-id; ডুপ্লিকেট কাউন্টিং শূন্য রাখার জন্য স্ট্রিক্ট টেস্ট-পিন থাকবে।
- **P-C:** বিদ্যমান worker-প্যাটার্নে stale-run sweep (interval **env-পঠিত — কোডে কোনো স্থির মিনিট-সংখ্যা নয়**; zero-hardcode সংশোধন; retention-দিনও env/config-চালিত, ডকুমেন্টে উদাহরণ-মাত্র): stale terminal-পূর্ব run → classify_failure→finalize; `.github/workflows/db-retention.yml`-এ runs/run_events prune — বিদ্যমান deletion-guard পুনঃব্যবহার।
- **P-D (ডুয়াল-ড্রাইভেন সত্য /runs ড্যাশবোর্ড):**
  - `runService.ts` list/detail/events → `/api/v1/runs`-এ পরিচালিত হবে।
  - `AGENTS.md Rule 7` অনুসারে ডুয়াল ভিউ চালু হবে:
    - *Customer Experience:* সাধারণ প্রগ্রেস বার, হিউম্যান-রিডেবল স্ট্যাটাস ও প্রগ্রেসিভ ডিসক্লোজার (সহজ ও দ্রুত)।
    - *Admin Mission Command:* সম্পূর্ণ সাব-টাস্ক DAG, ল্যাটেন্সি হিটম্যাপ, Gateway টোকেন ব্রেকডাউন ও HITL ওভাররাইড প্যানেল।
- **P-E:** AutomationDispatcher-এর সিদ্ধান্ত: scheduled-automation-পথে revive (bridge সক্রিয়) অথবা delete (register-দর্শন); দুই-সমাপ্তিই measured; bridge-লেখায় প্রকৃত user_id/tenant (P-A-প্রবাহিত)।
- **P-F:** BudgetGuard.check_pre_execution gateway/tool পথে (flag `SUPREMEAI_RUN_BUDGETS=true`, default false, fail-open); check_run_budgets-ফল অ্যাডমিশন-সিদ্ধান্তে।
- **P-G (TaskRuntime ঐক্য ও ক্যানসেলেশন প্রোপাগেশন):**
  - TaskRuntime.execute_task-কে run-এর ভিতরে চালানো (run_id-সহ trace)।
  - L58 ফেব্রিকেটেড আউটপুট → explicit error-ফল (fail-honest)।
  - যখন কোনো রান ক্যানসেল হবে (`/api/v1/runs/{id}/cancel` বা ইউআই বাটন থেকে), তখন `CancellationToken` দিয়ে ব্যাকগ্রাউন্ডের সব সাব-টাস্ক ও গেটওয়ে এপিআই কল সাথে সাথে টার্মিনেট হবে।

### ২.৫ বেনিফিট (সবই hypothesis — Gate 5-এ measured হবে)

1. **"কী হলো কোথায়" প্রশ্নের এক-উত্তর:** প্ল্যাটফর্মের প্রতিটি কাজ এক তালিকায় — সমর্থন-খরচ হ্রাস, বিশ্বাসযোগ্যতা বৃদ্ধি (hypothesis)।
2. **রান-লেভেল নির্ভুল বিলিং ও কস্ট ট্র্যাকিং (P-B):** প্রতিটি রানের নিখুঁত টোকেন ও ডলার খরচ Gateway `UsageSettlement` থেকে সরাসরি রানের গায়ে যুক্ত থাকবে।
3. **তাত্ক্ষণিক ক্যানসেলেশন ও অপচয় বন্ধ (P-G):** রান ক্যানসেল হলে ব্যাকগ্রাউন্ডের সব প্রসেস একযোগে বন্ধ হয়ে ক্লাউড রিসোর্স বাঁচাবে।
4. **ডুয়াল-ড্রাইভেন স্বচ্ছতা (P-D):** কাস্টমার পাবেন সহজ-সুন্দর আউটকাম, আর অ্যাডমিন পাবেন মিশন-কন্ট্রোল গ্রেড টেলিমেট্রি।
5. **পরিচ্ছন্ন জীবনচক্র (P-C):** FINALIZE-সম্পূর্ণ অডিট-লক + retention — DB-স্বাস্থ্য।
6. **Module 05-সিনার্জি:** run-anchored execution-উপাত্ত learning-স্রোতকে সমৃদ্ধ করে — শেখা প্রস্তাবগুলো run-প্রমাণসহ।
7. **সত্য-runtime (P-G):** মিথ্যা-সাফল্য শূন্য — Constitution #13 runtime-অঙ্গনে।

### ২.৬ ক্ষতি/ঝুঁকি (সৎ, প্রশমন সহ)

1. **উষ্ণ-পথ latency:** chat-পথে run-লেখা — প্রশমন: best-effort async (প্রমিত-প্যাটার্ন), flag default false, পরিমাপ-গেট।
2. **দ্বি-গণনা:** usage-ফিডে ডুপ্লিকেট — প্রশমন: idempotency-key; টেস্ট-পিন।
3. **12-state ভাঙা:** নতুন পথ অবৈধ ট্রানজিশনে — প্রশমন: সবই assert_transition দিয়ে; ১,৯১৩-LOC রক্ষা; নতুন state যোগ নয়।
4. **FE-বিভ্রান্তি:** /runs-উৎস বদল — প্রশমন: missions-গৌণ-ট্যাব, ধীরে পরিবর্তন, route-audit নথি।
5. **পরিসর-ঝুঁকি:** "observability" নামে dashboard-রোমাঞ্চ — প্রশমন: এই নীলনকশায় কোনো নতুন ফিচার নয়; বিদ্যমান চুক্তির সর্বজনীনতা; প্রতিটি Phase আলাদা Gate 0–6।

---

## Part 3 — Explicit Out-of-Scope

1. ERR-F01 bridge-writers ও pending_tasks→HITL সংযোগ — Module 02 P-B-র মালিকানা (সীমানা)।
2. নতুন state/মডেল-কলাম যোগ — 12-state ও স্কিমা অপরিবর্তিত।
3. missions-assigner LLM-করণ — Module 02 P-C-র মালিকানা।
4. নতুন dashboard-ফিচার/গ্রাফ — কেবল উৎস-সত্য; ডিজাইন পরিসর নয়।
5. WebSocket-স্ট্রিমে run-লাইভ-পুশ — ভবিষ্যৎ প্ল্যান-প্রার্থী।
6. সমান্তরাল multi-plan execution — একসময়ে একটাই Phase active।

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | প্রতিটি Phase আলাদা proposed execution; একসময়ে একটাই active |
| 2. Small change to existing code | ✅ | run_scope পাতলা নতুন-ফাইল; বাকি মোড়ক-লাইন; state/skema অটুট |
| 3. No new infrastructure | ✅ | টেবিল/worker/retention-workflow বিদ্যমান |
| 4. No CI cost amplification | ✅ | integration টেস্ট বিদ্যমান স্যুটে |
| 5. No credit-burn risk | ✅ | run-লেখা LLM-বিহীন; planner-LLM flag default false |
| 6. No academic leaderboard | ✅ | adoption-matrix, budget-liveness, stuck-run — সরাসরি প্রোডাক্ট-মান |
| 7. Realistic resource budget | ✅ | best-effort async; retention-guard বিদ্যমান |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main 5b69c23 sed/grep/wc-যাচাই (last_verified-তালিকা); Module 02 সীমানা-পাঠ |

| Constitution ধারা | প্রভাব |
|---|---|
| #5 Verify Before Trust | ✅ /runs-মিথ্যা → সত্য-উৎস; adoption CI-প্রমাণসহ |
| #6 Policy Before Power | ✅ অ্যাডমিশন-গার্ড ক্ষমতার আগে (P-F) |
| #8 Graceful Degradation | ✅ best-effort লেখা; fail-open বাজেট-গার্ড |
| #10 One System, Many Execution Surfaces | ✅ এই নীলনকশারই মূল-বাক্য: ৮ পৃষ্ঠ এক চুক্তিতে |
| #12 Least Privilege | ✅ tenant-পরিচয় প্রতি run-এ |
| #13 No Silent Failure | ✅ মিথ্যা-executor শুদ্ধি; stuck-run sweep |

---

## Part 5 — Verification & Acceptance (Gates 4–6) + Rollback

- **Gate 4 (প্রতি Phase):** tests/runs/+tests/missions/ (~৩,১৮০-LOC) শূন্য-ব্যর্থতা; P-A run_scope integration টেস্ট (৩ পৃষ্ঠে run-row+terminal); P-B idempotency টেস্ট; P-C sweep টেস্ট (stale→FINALIZED); P-D FE-consumer যাচাই।
- **Gate 5 (live):** ২৪-ঘণ্টায় adoption-matrix ৮/৮ (target); usage-ফিড >0; stuck-run >7d শূন্য; /runs সত্য-উৎস পর্যবেক্ষিত।
- **Gate 6:** প্রতিটি Phase নিজস্ব execution প্ল্যানে complete; এই নীলনকশা complete যখন acceptance_criteria-র পাঁচটি সংজ্ঞা সবই evidence-সহ সত্য।
- **Rollback:** প্রতিটি Phase = একক commit revert + flag-off; কোনো schema/data-loss path নেই; FE-উৎস-বদল একক revert-যোগ্য।

---

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Pass, 2026-09-17, branch `crown-jewel-v2`)

| দর্শন | রায় | ভিত্তি |
|---|---|---|
| Zero cost | ✅ সংগত | পাতলা context-manager + বিদ্যমান worker/retention-workflow পুনঃব্যবহার; BudgetGuard flag default false fail-open; কোনো নতুন infra/পরিশোধিত পরিষেবা নয় |
| Lightweight | ✅ সংগত | best-effort recording (DB-ব্যর্থতায় চলতে-থাকা); P-E wire-অথবা-delete দ্বি-সমাপ্তি |
| Fast & smooth | ✅ সংগত | flag default false → হট-পথ অপরিবর্তিত; sweep ব্যাকগ্রাউন্ড-স্তরে |
| Zero hardcode | ⚠️ ছিল → ✅ **সংশোধিত** | P-C-র "১৫-মিনিট sweep" ও স্থির retention-দিন উদাহরণ-মাত্র করে env/config-চালিত (§২.৪ সংশোধিত) |

মূল-যন্ত্রপাতি spot-check (base `ed35eaf`): `run_scope` backend-এ অনুপস্থিত (সত্যিই নতুন-প্রস্তাব); `BudgetGuard.check_pre_execution` বিদ্যমান (`backend/runtime/budget_guard.py` L19); TaskRuntime.execute_task বিদ্যমান।

স্কোপ-সততা: proposal-দর্শন অডিট + মূল-যন্ত্রপাতি spot-check; সম্পূর্ণ line-ref re-verification নয়।

---

## Part 6 — পরবর্তী চক্র লাইনেজ (reference-only; candidate list ≠ execution queue)

- **চক্র ১–৫ (প্রকাশিত):** Module 01 Memory → Module 02 Orchestration → Module 03 LLM Gateway → Module 04 Browser → Module 05 Self-Evolution।
- **চক্র ৭ (কিউতে):** Module 07 — Context Engine (`backend/context_engine/`) — উষ্ণ-পথের token-বাজেট-চুক্তি; এই মডিউলের run-scope trace-উপাত্ত context-assembly মাপেও প্রবাহিত হবে।
- সূচি ও কিউ-পুনঃর‍্যাঙ্ক: `crown_jewel_series/README.md`।
