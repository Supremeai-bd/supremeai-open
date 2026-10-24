---
id: crown-jewel-module-01-memory-power-up-v1-2026-09-17
title: "Crown Jewel Module Series — Module 01: Memory Subsystem Power-Up (মেমোরি সাবসিস্টেমকে প্ল্যাটফর্মের সবচেয়ে শক্তিশালী স্তম্ভে রূপান্তর — M3 একীকরণ + Memory Flywheel সক্রিয়করণের পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Memory Circle (backend/services/memory_service.py — CascadeMemoryService + backend/memory/ + backend/core/ai_memory/) — PLAN_004/PLAN_006-এর একই সাবসিস্টেম
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ১ — একটি মডিউল (Memory), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — fresh main 07604ad (2026-09-17) sed/grep-যাচাইকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; প্রতিটি ধাপে kill-switch; কোনো নতুন dependency/infra নয়"
depends_on:
  - "backend/services/memory_service.py (CascadeMemoryService — canonical M3 store service: store_memory L288 blind INSERT, _embed L208, _cosine_similarity L478, query_context L486, _query_via_pgvector_rpc L149, _MEMORY_ROW_CAP=2000 L52)"
  - backend/core/unified_memory.py (founder-implemented PLAN-004 write-time distillation — store_long_term_memory_distilled L189, kill-switch SUPREMEAI_MEMORY_DISTILL L38–44)
  - backend/core/ai_memory/vector_store.py (L29 _coerce_uuid uuid5 deterministic dedup, L60 upsert_batch — বিদ্যমান upsert precedent)
  - backend/core/memory/auto_rag_injector.py (TOP_K=5 L38, MAX_CHARS_PER_MEMORY=400 L39, MIN_RELEVANCE_SCORE=0.55 L41 — downstream recall consumer)
  - backend/workers/synaptic_dream.py (memory-consolidation worker — কোড বিদ্যমান কিন্তু কোনো scheduler-এ wired নয়; backend/workers/celery_app.py 9-LN stub)
  - "backend/memory/ (15 store মডিউল: chromadb_store, cloud_postgres_store, episodic_memory, hierarchical_tree, long_term_memory, rag_pipeline, sliding_window, sqlite_store, summary_tree, supabase_store, mcp_server, unified_db_manager, checkpoint_resume, vector_store_config — 2026-09-17 fresh main 07604ad ls-verified)"
  - backend/integrations/mem0_adapter.py + backend/integrations/graphiti_adapter.py (flag-gated zero-cost capability borrows — 2026-09-17 ls-verified)
  - backend/agents/syncguard/syncguard_agent.py L86 + backend/api/routes/unified_memory_api.py L47/L56 (বাস্তব store callers)
  - backend/tests/memory/test_memory_pkg_integrity.py (মেমোরি প্যাকেজ-ইন্টিগ্রিটি টেস্ট বেসলাইন — 07604ad-এ যুক্ত)
  - docs/database/AI_MEMORY_SCHEMA_AUDIT.md L232 (canonical ai_memory কলাম-চুক্তি — importance_score, updated_at সহ ১৪ কলাম)
  - docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md ERR-F02 (একমাত্র OPEN foundational defect — memory store একীকরণ)
  - docs/plans/M3_MEMORY_STORE_CONSOLIDATION_DECISION_TABLE.md (keep/merge/archive সিদ্ধান্ত টেবিল — active)
  - docs/plans/PLAN_006_MEM0_STYLE_MEMORY_CONSOLIDATION_2026-09-17.md (row-level write identity — proposed; এই নীলনকশার Phase A)
  - docs/plans/HEAD_OF_PLANNING_STRATEGIC_LEVERAGE_2026-09-16.md (L4 Memory Flywheel — "single largest architectural obstacle to Phase 3")
  - README.md Constitution #1 (Eternal Brain), #3 (Reuse Before Creation), #5 (Verify Before Trust), #8 (Graceful Degradation), #11 (Memory Must Compound), #13 (No Silent Failure), #14 (Sustainable Cost)
implements:
  - M3 consolidation blueprint-এর ধাপে ধাপে execution-পথ — 15+ প্রতিযোগী store → একক canonical write path (`MemoryStore` protocol-এর পিছনে Supabase ai_memory), যা `docs/plans/M3_MEMORY_STORE_CONSOLIDATION_DECISION_TABLE.md` ইতিমধ্যে pin করেছে কিন্তু এখনো শুরু হয়নি (deliberate — live Supabase env প্রয়োজন)
  - "L4 Memory Flywheel-এর পূর্ণ সক্রিয়করণ: write-time identity (PLAN_006) → nightly consolidation (synaptic_dream scheduling) → hybrid recall ranking → run-anchored writes → recall evaluation"
  - "Constitution #11 \"Memory Must Compound\"-এর চতুর্থ স্তম্ভ: PLAN_002 = in-session compaction, PLAN_004 = write-time quality, PLAN_006 = write-time identity, **এই মডিউল-নীলনকশা = সিস্টেম-স্তরের একীকরণ ও চক্রবৃদ্ধি (flywheel)**"
  - B4 battlefield (Memory)-কে "unmeasured" থেকে "measured"-এ নেওয়া — recall evaluation harness দিয়ে
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা — tested code + contracts-ই reality; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান হিসেবে অনুমোদিত হবে
last_verified: "2026-09-17 (fresh main 07604ad code-read: memory_service.py store_memory L288 sed-verified, _MEMORY_ROW_CAP=2000 L52 sed-verified; unified_memory.py kill-switch L38–44 sed-verified; backend/memory/ 15 ফাইল ls-verified — 07604ad hygiene commit এই ফোল্ডার স্পর্শ করেছে কিন্তু store_memory/distillation evidence-ফাইলগুলো 0-diff; workers/synaptic_dream.py বিদ্যমান, celery_app.py 9-LN stub; core/kernel/dispatcher.py + core/orchestration/swarm_orchestrator.py স্পর্শ হয়নি; দর্শন-সংগতি পুনঃযাচাই 2026-09-17 branch crown-jewel-v2 (base ed35eaf): proposal-স্তরে ৪-নীতি অডিট + মূল-যন্ত্রপাতি spot-check (store_memory blind INSERT অটুট, synaptic_dream unscheduled, periodic_task_scheduler interval_seconds প্রমাণিত); PLAN_006-এর sed-verified লাইন-রেফারেন্সগুলো (auto_rag_injector L38–44, vector_store L29/L60, schema audit L232) উত্তরাধিকারসূত্রে গৃহীত — ওই ফাইলগুলো 07604ad-এ 0-diff)"
code_evidence:
  - "backend/services/memory_service.py L288–340 — store_memory(): pg path blind INSERT INTO ai_memory (user_id, session_id, agent_type, task_type, summary, embedding, metadata) — একই summary আবার এলেও নতুন row; কোনো similarity probe নেই, কোনো UPDATE branch নেই; content/importance_score/updated_at কোনোটিই লেখা হয় না"
  - backend/services/memory_service.py L149–188 — _query_via_pgvector_rpc (match_ai_memories RPC) — scalable probe path প্রস্তুত; L52 — _MEMORY_ROW_CAP=2000 (in-Python cosine ranking cap — capped candidate-set pattern প্রমাণিত)
  - "backend/core/unified_memory.py L189–237 — store_long_term_memory_distilled: PLAN-004 distillation live (kill-switch SUPREMEAI_MEMORY_DISTILL L38–44) — লেখার মান ভালো, কিন্তু distilled variants-ও dedup ছাড়া জমে"
  - backend/core/memory/auto_rag_injector.py L38–44 — TOP_K=5, MAX_CHARS_PER_MEMORY=400, MIN_RELEVANCE_SCORE=0.55 — recall-এ মাত্র ৫টি context-স্লট; ranking শুধু relevance-ভিত্তিক — importance/recency অনুপস্থিত
  - backend/core/ai_memory/vector_store.py L29 (uuid5 deterministic dedup) + L60 (upsert_batch) — একই রিপোর অন্য write path-এ upsert-dedupe semantics accepted pattern
  - backend/memory/ — ১৫টি সমান্তরাল store মডিউল (chromadb_store.py, cloud_postgres_store.py, episodic_memory.py, hierarchical_tree.py, long_term_memory.py, rag_pipeline.py, sliding_window.py, sqlite_store.py, summary_tree.py, supabase_store.py, mcp_server.py, unified_db_manager.py, checkpoint_resume.py, vector_store_config.py) — একই দায়িত্বের একাধিক বাস্তবায়ন; ERR-F02-এর subject
  - backend/workers/synaptic_dream.py — memory-consolidation worker-এর কোড বিদ্যমান; কিন্তু backend/workers/celery_app.py 9-LN stub — কোনো প্রোডাকশন scheduler-এ wired নয়
  - backend/integrations/mem0_adapter.py + graphiti_adapter.py — বাইরের সেরা প্যাটার্নের সাথে ইতিমধ্যেই integration seam আছে (flag-gated)
  - "backend/agents/syncguard/syncguard_agent.py L86 + backend/api/routes/unified_memory_api.py L47/L56 — বাস্তব callers: repeated store দুই পথেই ঘটে"
  - backend/tests/memory/test_memory_pkg_integrity.py — 07604ad-এ যুক্ত ইন্টিগ্রিটি টেস্ট — consolidation-এর regression-বেসলাইন
  - docs/database/AI_MEMORY_SCHEMA_AUDIT.md L232 — canonical কলাম-তালিকায় importance_score ও updated_at আছে, কিন্তু store_memory-র INSERT কলাম-তালিকায় নেই → dead columns
test_evidence: "none yet — প্রতিটি Phase-এর নিজস্ব execution প্ল্যান টেস্ট-চুক্তি সংজ্ঞায়িত করবে; সমষ্টিগত চুক্তি: (১) Phase A → PLAN_006-এর ৮টি নামাঙ্কিত টেস্ট-দৃশ্য; (২) Phase B → per-store adapter contract test + dual-write shadow parity test; (৩) Phase C → consolidation scheduler smoke + idempotency test; (৪) Phase D → hybrid ranking টেস্ট (kill-switch=false → আজকের ranking byte-সমতুল্য); (৫) Phase E → run_id propagation test; (৬) Phase F → eval fixture-এ measured recall@5; (৭) backend/tests/memory/ ও backend/tests/runs/ ট্রিতে zero regression"
acceptance_criteria:
  - "প্রতিটি Phase আলাদা ছোট execution প্ল্যান হিসেবে Gate 0–6 পাস করবে; এই নীলনকশা তাদের সমষ্টিগত দিক-নির্দেশক মাত্র"
  - "Flywheel সক্রিয় হওয়ার সংজ্ঞা: (a) canonical write path = ১টি; (b) identical re-store → ঠিক ১ row (PLAN_006 threshold); (c) nightly consolidation scheduled + পরিমাপযোগ্য; (d) recall top-5-এ duplicate শূন্য + hybrid ranking kill-switch-যুক্ত; (e) memory row ↔ run traceability; (f) measured recall@5 baseline প্রকাশিত"
  - "বিদ্যমান tests/memory/ + tests/runs/ + AutoRAG consumers-এ zero regression — প্রতিটি Phase-এর PR-এ প্রমাণিত হবে"
  - "নতুন dependency/infra/LLM-call শূন্য — সব মেশিনারি বিদ্যমান কোডেই (pgvector RPC, uuid5, synaptic_dream, periodic scheduler)"
test_evidence_note: "unit/integration টেস্ট contract behavior প্রমাণ করে (Gate 4); Gate 5-এ live evidence — একই fact ×৩ store → ১ row; consolidation রাতভর চলে duplicate-হ্রাস মাপা; eval harness recall@5 সংখ্যা প্রকাশিত — completion claim-এর আগে বাধ্যতামূলক"
risk_and_rollback:
  - "প্রতিটি Phase স্বাধীন ও বিপর্যয়-বিচ্ছিন্ন: কোনো Phase ব্যর্থ হলে আগের Phase-গুলোর লাভ অক্ষত থাকে"
  - "Phase A rollback = PLAN_006-এর kill-switch (SUPREMEAI_MEMORY_DEDUP); Phase B = per-store dual-write flag → single-store ফিরে যাওয়া; Phase C = scheduler-unwire (worker আজও optional); Phase D = hybrid-weight env → legacy relevance-only; Phase E = metadata.run_id optional field — পড়ার কোড অনুপস্থিত হলেও কোনো কিছু ভাঙে না"
  - "কোনো Phase-এই DELETE নয় — legacy store প্রথমে read-only archive, তারপর (আলাদা অনুমোদনে) removal; তথ্য-লস-শূন্য নীতি"
  - "tenant isolation: সব probe/ranking/consolidation user_id-scoped — cross-tenant লিখা/পড়া অসম্ভব (PLAN_006-এর একই চুক্তি)"
  - "Supabase free-tier 512MB চাপ: consolidation ও dedup উল্টোদিকে row-স্ফীতি *কমায়*; তবু docs/plans/ এ বিদ্যমান free-tier-512mb-memory-pressure-remediation প্ল্যানের সাথে reconciliation বাধ্যতামূলক (Part 1.5)"
baseline: "(hypothesis — Phase-ভিত্তিক execution PR-এ মাপা হবে) আজ: identical fact-এর প্রতিটি store = নতুন row (PLAN_006 baseline-এর সাথে সামঞ্জস্যপূর্ণ); recall top-5-এ near-duplicate slot-waste (hypothesis); consolidation শূন্যবার চলে (scheduler-অনুপস্থিতি); B4 Memory battlefield = unmeasured (`docs/plans/HEAD_OF_PLANNING_STRATEGIC_LEVERAGE_2026-09-16.md` §3 scoreboard)"
measurement_method:
  - "(a) store-স্বাস্থ্য: ai_memory row-count growth-rate প্রতি সপ্তাহ (dedup-পূর্ব বনাম পরে)"
  - "(b) recall-গুণমান: eval fixture-এ recall@5 ও duplicate-share — Phase F-এর harness-এ measured"
  - "(c) consolidation-কার্যকারিতা: রাত্রিক রান-এ merged-row count ও হ্রাস-শতাংশ (measured)"
  - "(d) traceability: run_id-সহ memory row-এর শতাংশ (measured)"
success_threshold: "Phase-ভিত্তিক হার্ড-থ্রেশহোল্ড সংশ্লিষ্ট execution প্ল্যানে সংজ্ঞায়িত হবে; সমষ্টিগত লক্ষ্য (target, hypothesis): identical re-store → ১ row; recall top-5 duplicate-share → <5%; রাত্রিক consolidation → প্রতি রাতে চলে; memory-run traceability → >90% নতুন row"
plan_lifecycle: "living — Crown Jewel Module Series চক্র ১-এর প্রস্তাবিত নীলনকশা; PLAN_006 এই নীলনকশার Phase A হিসেবে সর্বনিকটতম execution-প্রার্থী থেকে যাবে; কোনো Phase-ই ফাউন্ডার-অনুমোদন-পূর্বে executable নয়"
---

# Crown Jewel Module Series — Module 01: Memory Subsystem Power-Up

**Status:** proposed (ফাউন্ডার রিভিউ অপেক্ষমাণ — Gate 2 পূর্বে executable নয়)
**Owner:** Memory Circle (CascadeMemoryService + `backend/memory/` + `backend/core/ai_memory/`)
**Main anchor:** fresh main `07604ad` (2026-09-17)
**Resource delta:** 0 নতুন dependency / 0 নতুন infra / 0 নতুন CI cost / 0 বাধ্যতামূলক LLM-call / 0 schema migration

## বাংলা সারসংক্ষেপ

SupremeAI-র সবচেয়ে দামি সম্পদ তার স্মৃতি — Constitution #1 "Eternal Brain" বলে দেয় বাইরের মডেল বদলাতে পারে, কিন্তু স্মৃতিই প্ল্যাটফর্মের স্থায়ী পরিচয়। আজ মেমোরি সাবসিস্টেম এক অদ্ভুত অবস্থায়: **সবচেয়ে বেশি নির্মিত, তবু সবচেয়ে বেশি বিভক্ত**। একদিকে প্রতিভাবান যন্ত্রপাতি — canonical Supabase `ai_memory` store (vector-384), `CascadeMemoryService` (976 লাইন, pgvector-RPC + cosine similarity), PLAN-004 write-time distillation (live, kill-switch সহ), AutoRAGInjector recall (সর্ব-উষ্ণ পথে), এমনকি একটি consolidation worker (`backend/workers/synaptic_dream.py`)। অন্যদিকে `backend/memory/` ফোল্ডারে **১৫টি সমান্তরাল store** — chromadb, sqlite, cloud-postgres, episodic, hierarchical-tree, sliding-window, summary-tree… — প্রত্যেকটির নিজস্ব লেখা-পড়া, পরস্পর-অসচেতন। Defect register-এ এটিই একমাত্র OPEN foundational defect (**ERR-F02**)। ফলাফল: একই fact বারবার নতুন row হিসেবে জমে (blind INSERT — `store_memory` L288–340), recall-এর দুর্লভ ৫টি স্লট near-duplicate-এ নষ্ট হয়, `importance_score`/`updated_at` কলাম দুটি মৃত, আর রাতের consolidation worker কাউকে ডাকা ছাড়াই ঘুমিয়ে আছে।

কৌশল-নথি (`docs/plans/HEAD_OF_PLANNING_STRATEGIC_LEVERAGE_2026-09-16.md`, L4) নিজেই স্বীকার করেছে — এই ভাঙা একীকরণই "single largest architectural obstacle to Phase 3 (Own Model v1)"। এই নীলনকশা মেমোরিকে **crown jewel স্তম্ভে** রূপান্তরের ৬-ধাপের flywheel দেয়: **(A)** write-time identity (PLAN_006 landing) → **(B)** একক canonical write path (M3 execution) → **(C)** রাত্রিক consolidation scheduling → **(D)** hybrid recall ranking → **(E)** run-anchored traceability → **(F)** recall evaluation harness। প্রতিটি ধাপ আগেরটির উপর দাঁড়ায়, প্রতিটির নিজস্ব kill-switch, কোনো নতুন dependency নেই — শুধু বিদ্যমান মেশিনারির সঠিক সংযোগ। প্রতিযোগীরা (mem0, Letta, Zep/Graphiti, LangMem) প্রত্যেকে এই চাকার এক-একটি পাল্লা প্রমাণ করেছে; SupremeAI-র সব পাল্লা ইতিমধ্যেই গ্যারেজে আছে — এই নীলনকশা সেগুলো জুড়ে দেয়।

---

## Part 1 — Competitor Intelligence (dated external evidence; mem0/ChatGPT/Letta অংশ PLAN_006-এর same-day verification থেকে উত্তরাধিকারসূত্রে গৃহীত, verified 2026-09-17)

### ১.১ mem0 — write-time extraction + deduplication + conflict resolution

- প্রতিটি `add()` কলে extraction → deduplication → conflict resolution পাইপলাইন (PLAN_006 Part ১.১, web-verified 2026-09-17)। Honest caveat: mem0 v2.0.0 ADD-only extraction-এ গেছে, UPDATE/conflict behavior-এ doc–implementation mismatch প্রমাণিত (Apr 20, 2026, PLAN_006-য়াচাইকৃত) — তাই SupremeAI-র পথ deterministic, LLM-free similarity-gated upsert (`backend/core/ai_memory/vector_store.py` L29/L60-এর বিদ্যমান precedent)।
- SupremeAI-র সংযোগবিন্দু: `backend/integrations/mem0_adapter.py` ইতিমধ্যেই বিদ্যমান (flag-gated) — pattern-borrow করতে নতুন integration লাগবে না।

### ১.২ Letta (f.k.a. MemGPT) — tiered memory + consolidation

- OS-অনুপ্রাণিত hierarchy: core / recall / archival (Aug 12, 2025, PLAN_006-যাচাইকৃত)। মূল শিক্ষা: archival যদি unbounded duplicate-এ ভরে যায়, tiering অর্থহীন।
- SupremeAI-র সংযোগবিন্দু: PLAN-004 distillation (write-time quality) already landed; বাকি ছিল row-identity (PLAN_006) ও archival স্বাস্থ্য-রক্ষণ (এই নীলনকশার Phase B+C)।

### ১.৩ Zep / Graphiti — temporal knowledge-graph memory

- Zep-এর Graphiti স্মৃতিকে সময়-সচেতন graph-এ রাখে — fact-এর দ্বৈত টাইমস্ট্যাম্প (ঘটনা-সময় বনাম জ্ঞান-সময়) ও incremental update মূল বৈশিষ্ট্য (established vendor pattern — fresh-dated citation পরবর্তী চক্রে সংগ্রহ করা হবে; এ চক্রে এটি design-pattern observation হিসেবে labeled)।
- SupremeAI-র সংযোগবিন্দু: `backend/integrations/graphiti_adapter.py` বিদ্যমান। এই নীলনকশা graph-স্তর নয় — কিন্তু Phase E-র run-anchored traceability ও Phase F-এর পরিমাপ ভবিষ্যৎ temporal-graph স্তরের ভিত্তি রাখে (কোনো দ্বন্দ্ব নেই, সম্পূরক)।

### ১.৪ LangMem (LangChain) — hot-path বনাম background memory

- LangMem দুই মোডে স্মৃতি লেখে: আলাপ-পথে দ্রুত, আর background-এ "নিশ্চিত" মোডে জমা-যাচাই করে consolidate করে (established vendor pattern — fresh-dated citation পরবর্তী চক্রে; design-pattern observation হিসেবে labeled)।
- SupremeAI-র সংযোগবিন্দু: ঠিক এই দ্বৈততাই এই নীলনকশার Phase A (write-time identity) + Phase C (background consolidation scheduling)।

### ১.৫ ChatGPT Memory — deduplicated, updatable user-facing সেট

- একই তথ্য আবার বললে নতুন item নয়, বিদ্যমানটি update হয় (product-behavior observation — PLAN_006 Part ১.২-তে labeled)। মেমোরির মান সংখ্যায় নয়, অনন্যতা ও সাম্প্রতিকতায়।

### ১.৬ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল (fresh main 07604ad-verified)

| প্রতিযোগী | যা করে | SupremeAI আজ (07604ad-verified) | গ্যাপ |
|---|---|---|---|
| mem0 | add()-কালীন dedup + conflict resolution | `store_memory` blind INSERT (`backend/services/memory_service.py` L288–340) | Phase A (PLAN_006) |
| Letta/MemGPT | tiered memory + consolidation | canonical store + distillation আছে; consolidation worker unscheduled (`backend/workers/synaptic_dream.py`) | Phase B + C |
| Zep/Graphiti | temporal graph + incremental update | flag-gated adapter আছে (`backend/integrations/graphiti_adapter.py`); memory rows অনুলেখ্য নয় (run-id নেই) | Phase E (ভিত্তি); পূর্ণ graph পরবর্তী যুগ |
| LangMem | hot-path + background dual-write | একমাত্র তাৎক্ষণিক লেখা; background মোড অনুপস্থিত | Phase C |
| ChatGPT | deduplicated updatable সেট | blind INSERT + dead importance/updated_at কলাম | Phase A + D |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main 07604ad, 2026-09-17)

| বিদ্যমান | বিষয় | এই নীলনকশার সাথে সম্পর্ক |
|---|---|---|
| PLAN_001 (complete) | Anthropic prompt caching | ভিন্ন স্তর (LLM gateway); সম্পর্কহীন |
| PLAN_002 (complete) | WS চ্যাট-হিস্ট্রি compaction — in-session | ভিন্ন lifecycle-স্তর; সম্পূরক |
| PLAN_003 (complete) | Aider-style repo map | ভিন্ন সাবসিস্টেম; সম্পর্কহীন |
| PLAN_004 (complete) | write-time distillation | upstream সম্পূরক — distillation লেখার *মান* ভালো করে; এই নীলনকশা সিস্টেম-একীকরণ |
| PLAN_005 (proposed) | user-controlled /compact | ভিন্ন স্তর (in-session UX); সম্পর্কহীন |
| PLAN_006 (proposed) | write-time dedup + importance wiring | **সরাসরি সম্পূরক — এই নীলনকশার Phase A ঠিক এটিই**; PLAN_006 তার নিজস্ব Gate 0–6 দিয়ে আলাদা execution হবে; এই ডকুমেন্ট তাকে supersede করে না (supersedes: []) |
| `docs/plans/M3_MEMORY_STORE_CONSOLIDATION_DECISION_TABLE.md` (active) | store keep/merge/archive সিদ্ধান্ত-টেবিল | এই নীলনকশার Phase B সেই টেবিলের execution-পথ — ওভারল্যাপ নয়, বাস্তবায়ন-স্তর |
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` ERR-F02 | 15+ store একীকরণ | এই নীলনকশা ERR-F02-এর নিরাময়-পথ — সরাসরি alignment |
| `docs/plans/free-tier-512mb-memory-pressure-remediation` (active) | Supabase 512MB চাপ | পরিপূরক: dedup+consolidation row-স্ফীতি *কমায়* — চাপ-প্রশমনের আর্কিটেকচারাল অর্ধ; infra-অর্ধ ওই প্ল্যানে |
| `docs/plans/HEAD_OF_PLANNING_STRATEGIC_LEVERAGE_2026-09-16.md` L4 | Memory Flywheel লিভার | এই নীলনকশা L4-এর বিস্তারিত নীলনকশা — সরাসরি alignment |

**গ্রেপ-যাচাই:** fresh main 07604ad-এ কোনো বিদ্যমান ডকুমেন্ট M3-এর *executed* canonical single-write-path, hybrid ranking, run-anchored memory বা recall eval harness-এর execution-নীলনকশা দেয় না — এই চারটি সম্পূর্ণ unclaimed (`docs/plans/` recursive grep, 2026-09-17)।

---

## Part 2 — Six-Field Complete Plan

### ২.১ কী আছে (কোড-যাচাইকৃত)

1. **Canonical M3 store:** Supabase `ai_memory` (vector-384) founder-স্থাপিত; কলাম-চুক্তি `docs/database/AI_MEMORY_SCHEMA_AUDIT.md` L232 — ১৪ কলাম (importance_score, updated_at সহ)।
2. **CascadeMemoryService** (`backend/services/memory_service.py`, ~976 লাইন): store_memory L288, _embed L208, _cosine_similarity L478, query_context L486, pgvector-RPC path L149, _MEMORY_ROW_CAP=2000 L52 — dedup probe-এর প্রয়োজনীয় সব মেশিনারি একই ক্লাসে।
3. **Write-time quality (live):** PLAN-004 distillation (`backend/core/unified_memory.py` L189, kill-switch L38–44)।
4. **Recall consumer (live):** AutoRAGInjector (`backend/core/memory/auto_rag_injector.py` L38–44) — TOP_K=5, 400 chars/slot, MIN_RELEVANCE 0.55।
5. **Upsert precedent:** `backend/core/ai_memory/vector_store.py` L29 (uuid5 dedup) + L60 (upsert_batch)।
6. **Consolidation worker (নির্মিত, অনির্ধারিত):** `backend/workers/synaptic_dream.py` — কোড আছে; `backend/workers/celery_app.py` 9-LN stub — কোনো লাইভ scheduler নেই।
7. **Integration seams:** `backend/integrations/mem0_adapter.py`, `backend/integrations/graphiti_adapter.py` — প্রতিযোগী-প্যাটার্ন ধার নেওয়ার প্রস্তুত seam।
8. **বাস্তব callers:** `backend/agents/syncguard/syncguard_agent.py` L86, `backend/api/routes/unified_memory_api.py` L47/L56।
9. **টেস্ট-বেসলাইন:** `backend/tests/memory/test_memory_pkg_integrity.py` (07604ad) + PLAN_TO_CODE_TRACEABILITY_MATRIX-এ রেকর্ডকৃত tests/memory regression-বেসলাইন।

### ২.২ কী নেই (কোড-যাচাইকৃত অনুপস্থিতি)

1. **একক canonical write path** — `backend/memory/`-তে ১৫টি সমান্তরাল store; ERR-F02 OPEN।
2. **Row-level write identity** — dedup/UPDATE branch নেই (PLAN_006 proposed, unapproved)।
3. **জীবন্ত importance/updated_at** — canonical কলাম আছে, লেখা হয় না।
4. **Hybrid recall ranking** — relevance-only; importance/recency-ওজন নেই।
5. **Scheduled consolidation** — synaptic_dream কোনো scheduler-এ নেই; retention/TTL নীতি নেই।
6. **Run-anchored traceability** — memory row থেকে তাকে জন্ম-দেওয়া task/run-এ যাওয়ার পথ নেই।
7. **Recall evaluation** — B4 "unmeasured" (`docs/plans/HEAD_OF_PLANNING_STRATEGIC_LEVERAGE_2026-09-16.md` §3)।
8. **ক্লাউড বিভ্রাটে লোকাল রেজিলিয়েন্সের অভাব** — Supabase pgvector সাময়িক ডাউন বা স্লো (>২৫০০ms) হলে মেমোরি রাইট ক্র্যাশ করে বা সাইলেন্টলি ড্রপ হয়।

### ২.৩ কী করতে হবে (flywheel-এর ৭ ধাপ)

```text
P-A: Write-time identity (PLAN_006)     → একই fact = ১ row, importance জীবন্ত
P-B: একক canonical write path (M3)      → MemoryStore protocol-এর পিছনে ai_memory; legacy = adapter
P-C: রাত্রিক consolidation scheduling   → synaptic_dream-কে periodic scheduler-এ wire
P-D: Hybrid recall ranking              → cosine × importance × recency, env-tunable, kill-switch-যুক্ত
P-E: ক্যানোনিকাল InferenceContext ও রান-ট্রেসেবিলিটি → metadata.run_id + request_id (Module 03 Gateway-র সাথে সিঙ্ক)
P-F: বাউন্ডেড ফেইল-ওপেন ও লোকাল ক্যাশ রেজিলিয়েন্স   → Supabase আউটেজে SQLite/Disk ফলব্যাক বাফার + রিকানেক্ট সিঙ্ক
P-G: Recall evaluation harness          → measured recall@5 — B4 unmeasured → measured
```

### ২.৪ কীভাবে করব (ফাইল-স্তরের দিক-নির্দেশ, প্রতিটি Phase আলাদা execution প্ল্যান)

- **P-A:** PLAN_006 যথার্থ হিসেবে নিষ্পাদিত হবে — এই ডকুমেন্ট তার নতুন স্কোপ সংজ্ঞায়িত করে না।
- **P-B:** `MemoryStore` Protocol (`backend/memory/protocol.py` — নতুন ছোট ফাইল, ৩ মেথড: store/query/health) → `backend/memory/supabase_store.py` canonical implementation → legacy store-দের `M3_MEMORY_STORE_CONSOLIDATION_DECISION_TABLE.md`-এর রায় অনুযায়ী adapter/archive। ধাপ: dual-write shadow → parity পরিমাপ → cutover → legacy read-only। `backend/core/orchestration/periodic_task_scheduler.py`-র মতো বিদ্যমান seam পুনঃব্যবহার। **কী টচ হবে না:** `CascadeMemoryService`-র সিগনেচার, AutoRAGInjector-র consumers, কোনো API route।
- **P-C:** `backend/workers/synaptic_dream.py`-কে বিদ্যমান periodic scheduler-এ নিবন্ধন; idempotent consolidation (merge-only, কখনো DELETE নয়); ফল `docs/plans/` লগে সংখ্যাত। **Cadence হার্ডকোড নয় (zero-hardcode সংশোধন):** interval সম্পূর্ণ scheduler-config/env-চালিত (`backend/core/orchestration/periodic_task_scheduler.py`-র বিদ্যমান `interval_seconds` প্যাটার্ন, L36), ডিফল্ট-মান env-থেকে — কোডে কোনো স্থির সময়-সংখ্যা লেখা হবে না। **কী টচ হবে না:** worker-এর consolidation-লজিক, কোনো নতুন queue-ভিত্তি।
- **P-D:** `auto_rag_injector.py`-তে scoring branch: `score = w1·cosine + w2·importance + w3·recency` (weights env-tunable, default আজকের আচরণে সমতুল্য রাখা সম্ভব না হলে kill-switch SUPREMEAI_MEMORY_HYBRID_RANK=false → relevance-only)। **Weights সম্পূর্ণ runtime-env-পঠিত — কোডে কোনো কনস্ট্যান্ট নয়** (zero-hardcode নীতি); env-অনুপস্থিতিতে fallback = legacy relevance-only আচরণ। **কী টচ হবে না:** TOP_K/MAX_CHARS, injector-এর public interface।
- **P-E (InferenceContext ও Run-Anchored Traceability):**
  - মেমোরি স্টোর এবং রিকল পাথে Module 03 LLM Gateway-র ক্যানোনিকাল `InferenceContext(tenant_id, user_id, request_id, run_id, task_type)` সরাসরি বাইন্ড করা।
  - `metadata["run_id"]` এবং `metadata["request_id"]` JSONB মেটাডেটাতে সংরক্ষিত থাকবে (কোনো ডাটাবেজ স্কিমা মাইগ্রেশন ছাড়াই)।
  - কারেন্ট রানের শর্ট-টার্ম কনটেক্সট বুস্ট করতে রিকল র‍্যাংকিংয়ে `run_id` ম্যাচিংয়ের জন্য ডায়নামিক প্রক্সিমিটি বোনাস প্রযোজ্য হবে।
- **P-F (বাউন্ডেড ফেইল-ওপেন ও লোকাল ক্যাশ রেজিলিয়েন্স):**
  - Supabase pgvector বা ক্লাউড নেটওয়ার্ক ডাউন হলে বা ল্যাটেন্সি থ্রেশহোল্ড (>২৫০০ms) পার হলে কোনো মেমোরি অপারেশন ক্র্যাশ করবে না।
  - সিস্টেম স্বয়ংক্রিয়ভাবে লোকাল SQLite বাফার স্টোরে (`backend/memory/sqlite_store.py`) ফলব্যাক করবে (Bounded Fail-Open)।
  - নেটওয়ার্ক পুনরুদ্ধার হওয়া মাত্রই ব্যাকগ্রাউন্ড টাস্ক লোকাল বাফার থেকে ক্লাউড Supabase-এ সিঙ্ক ও ডিডুপ্লিকেশন সম্পন্ন করবে (`sync_on_reconnect`)।
  - **কঠোর টেন্যান্ট আইসোলেশন:** প্রতিটি ভেক্টর প্রোব এবং রিকলে ডাটাবেজ ও লোকাল উভয় স্তরেই `tenant_id` এবং `user_id` স্কোপ বাধ্যতামূলক, যাতে কোনো ক্রস-টেন্যান্ট তথ্য লিক অসম্ভব হয়।
- **P-G:** `backend/tests/memory/eval/` fixture: নিয়ন্ত্রিত corpus → query সেট → recall@5 + duplicate-share মাপা; ফল PR-বডিতে measured হিসেবে প্রকাশ।

### ২.৫ বেনিফিট (সবই hypothesis — Gate 5-এ measured হবে)

1. **মেমোরি চক্রবৃদ্ধি করে** (Constitution #11): dedup + consolidation একই fact-এর পুনরাবৃত্তি থামায় — store ছোট, recall ধারালো।
2. **Token-অর্থনীতি (hypothesis):** ৫টি দুর্লভ recall-স্লটে duplicate শূন্য → প্রতি আলাপে কার্যকর context-মান বাড়ে — M2 Context Engine-এর budget discipline-এর সরাসরি সহায়ক।
3. **জিরো-ক্র্যাশ মেমোরি আর্কিটেকচার (P-F):** ক্লাউড ডাটাবেজ সাময়িক ডাউন হলেও লোকাল বাফার ক্যাশের কারণে এজেন্টের মেমোরি পাইপলাইন শতভাগ সচল থাকে।
4. **সম্পূর্ণ ট্রেসেবিলিটি (P-E):** প্ল্যাটফর্মের প্রতিটি জ্ঞান কোন রানের কোন এআই কল থেকে এসেছে তা Gateway `InferenceContext`-এর সাথে ১০০% সংযুক্ত।
5. **Phase 3-পথ খোলা:** L4-এর মতেই এটি own-model যুগের বৃহত্তম স্থাপত্য-অন্তরায় নিরস্ত্র হবে।
6. **পরিমাপযোগ্যতা:** B4 প্রথমবার measured — "ভালো হয়েছে বলে মনে হচ্ছে" থেকে "recall@5 X% → Y%"।

### ২.৬ ক্ষতি/ঝুঁকি (সৎ, প্রশমন সহ)

1. **Dual-write drift (P-B):** shadow-পর্বে দুই store ভিন্ন হতে পারে — প্রশমন: parity টেস্ট + cutover শুধু 100% parity-তে; kill-switch প্রতি store-এ।
2. **Consolidation ভুল-positive merge (P-C):** ভিন্ন fact ভুল করে মিশতে পারে — প্রশমন: merge-only (কখনো DELETE নয়), merge-history metadata-য়, threshold conservative; ভুল merge-ও তথ্য-লস নয়।
3. **Hybrid ranking regression (P-D):** ওজন ভুল হলে recall খারাপ হতে পারে — প্রশমন: default = আজকের আচরণ; weights env-tunable; P-F harness-এ A/B পরিমাপ-পূর্বে default পরিবর্তন নয়।
4. **লোকাল বাফার সিঙ্ক কনফ্লিক্ট (P-F):** লোকাল থেকে ক্লাউডে সিঙ্কের সময় কনফ্লিক্ট — প্রশমন: ڈیٹারমিনিস্টিক `uuid5` ডিডুপ্লিকেশন এবং টাইমস্ট্যাম্প-বেসড লাস্ট-রাইট-উইনস (LWW) লজিক।
5. **Supabase free-tier চাপ:** embedding-স্টোরেজ বাড়তে পারে (hypothesis) — প্রশমন: dedup/consolidation নিজেই row-সংখ্যা কমায়; 512MB-প্ল্যানের সাথে reconciliation।
6. **পরিসর-ঝুঁকি:** ৭ Phase = ৭ সুযোগ scope-creep-এর — প্রশমন: প্রতিটি Phase আলাদা Gate 0–6 execution প্ল্যান; এই নীলনকশা নিজে কোনো কোড লেখে না।

---

## Part 3 — Explicit Out-of-Scope

1. নতুন vector database / নতুন embedding মডেল — শূন্য নতুন dependency নীতি।
2. LLM-driven semantic conflict resolution — mem0 v2.0-প্রমাণিত অপরিণত প্যাটার্ন; deterministic upsert-ই যথেষ্ট (PLAN_006 caveat)।
3. Temporal knowledge-graph স্তর (Zep/Graphiti-পূর্ণ সমতা) — পরবর্তী যুগের প্রার্থী; এই নীলনকশা কেবল ভিত্তি রাখে।
4. ai_memory schema-তে নতুন কলাম/migration — run_id metadata JSONB-তে।
5. Cross-tenant memory sharing — কখনোই নয় (tenant isolation অ-আলোচনাসাপেক্ষ)।
6. Memory UI/frontend পরিবর্তন — `frontend/` MemoryPanel এই সিরিজের পরিসরে নেই।
7. Legacy store-এর তাৎক্ষণিক deletion — read-only archive-পর্যন্ত কিছুই মুছে না।

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | এই নীলনকশা বিশ্লেষণ-স্তর; প্রতিটি Phase আলাদা proposed execution; একসময়ে একটাই active |
| 2. Small change to existing code | ✅ | প্রতিটি Phase guarded branch/flag; নতুন ফাইল কেবল protocol + tests |
| 3. No new infrastructure | ✅ | Supabase/Render/GH Actions যা আছে তাই; migration শূন্য |
| 4. No CI cost amplification | ✅ | eval fixture লোকাল; কোনো LLM/network-নির্ভর টেস্ট নয় |
| 5. No credit-burn risk | ✅ | dedup probe embedding+cosine (LLM-free); consolidation নিয়ন্ত্রিত |
| 6. No academic leaderboard | ✅ | সরাসরি প্রোডাক্ট-ক্ষমতা: recall মান, store-স্বাস্থ্য |
| 7. Realistic resource budget | ✅ | nightly worker + capped probe — free-tier সামঞ্জস্য (hypothesis, লগড) |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main 07604ad sed/ls/grep-যাচাই; `code_evidence`-তে line refs |

| Constitution ধারা | প্রভাব |
|---|---|
| #1 Eternal Brain | ✅ মূল লক্ষ্য — স্মৃতি একক, স্বাস্থ্যকর, চক্রবৃদ্ধি-সক্ষম |
| #3 Reuse Before Creation | ✅ সব মেশিনারি বিদ্যমান — protocol + wiring-ই নতুন |
| #5 Verify Before Trust | ✅ প্রতিটি Phase Gate 4 টেস্ট + Gate 5 live পরিমাপ |
| #8 Graceful Degradation | ✅ প্রতিটি Phase নিজস্ব kill-switch; ব্যর্থতা → আজকের আচরণ |
| #11 Memory Must Compound | ✅ প্রাথমিক অ্যাংকর — flywheel-এর সংজ্ঞা |
| #13 No Silent Failure | ✅ merge/probe/scheduler ব্যর্থতা লগড + fallback |
| #14 Sustainable Cost | ✅ row-স্ফীতি থামানোই দীর্ঘমেয়াদি সাশ্রয় |

---

## Part 5 — Verification & Acceptance (Gates 4–6) + Rollback

- **Gate 4 (প্রতি Phase):** `pytest backend/tests/memory/` — নতুন assertion পাস + zero regression; P-B-তে per-store parity টেস্ট; P-D-তে kill-switch byte-সমতুল্যতা টেস্ট।
- **Gate 5 (live):** identical fact ×৩ store → ১ row; nightly consolidation রান-লগ; eval harness recall@5 সংখ্যা PR-এ প্রকাশ; run_id-যুক্ত নতুন row-শতাংশ।
- **Gate 6:** প্রতিটি Phase তার নিজস্ব execution প্ল্যানে complete-হবে; এই নীলনকশা "complete" হবে যখন acceptance_criteria-র ছয়টি flywheel-সংজ্ঞা সবই evidence-সহ সত্য।
- **Rollback:** প্রতিটি Phase-এর নিজস্ব kill-switch (§২.৬/`risk_and_rollback`); সমষ্টিগত revert = সংশ্লিষ্ট Phase-commit-এর git revert — কোনো data-loss path নেই (merge-only, archive-only)।

---

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Pass, 2026-09-17, branch `crown-jewel-v2`)

প্রতিষ্ঠাতা-নির্দেশিত চার মূল-দর্শনের (zero cost / lightweight / fast-smooth / zero-hardcode) আলোকে প্রকাশিত নীলনকশার proposal-স্তর অডিট:

| দর্শন | রায় | ভিত্তি |
|---|---|---|
| Zero cost | ✅ সংগত | 0 নতুন dependency/infra/LLM-call (Part 4 rule 3–5); free-tier 512MB-সচেতনতা (§২.৬-৪) |
| Lightweight | ✅ সংগত | ছোট protocol-ফাইল + বিদ্যমান scheduler/worker পুনঃব্যবহার; 0 schema migration |
| Fast & smooth | ✅ সংগত | recall হট-পথে ডিফল্ট আচরণ-অপরিবর্তিত; capped probe (`_MEMORY_ROW_CAP=2000`); kill-switch প্রতি Phase |
| Zero hardcode | ⚠️ ছিল → ✅ **সংশোধিত** | P-C-র "nightly cadence" ও P-D-র weights আংশিক স্থির-ধারণা ছিল — এই পাসে দুটোই runtime-config/env-চালিত (§২.৪ সংশোধিত); মূল-যন্ত্রপাতি spot-check (base `ed35eaf`): `store_memory` blind INSERT অটুট, `synaptic_dream` এখনো unscheduled, scheduler `interval_seconds`-প্যাটার্ন প্রমাণিত |

স্কোপ-সততা: এই পাস proposal-দর্শন অডিট + মূল-যন্ত্রপাতি spot-check; সম্পূর্ণ line-ref re-verification নয় (original `last_verified`-র 07604ad-প্রমাণ অক্ষুণ্ণ)।

---

## Part 6 — পরবর্তী চক্র লাইনেজ (reference-only; candidate list ≠ execution queue)

- **চক্র ২ (প্রকাশিত):** Module 02 — Orchestration Core → `MODULE_02_ORCHESTRATION_CORE_POWER_UP_2026-09-17.md`।
- **চক্র ৩ (কিউতে):** Module 03 — LLM Gateway & Model Routing (`backend/core/llm/` + `backend/brain/model_router.py`)।
- পরিমাপ-ফল (P-F ইত্যাদি) কিউ পুনঃর‍্যাঙ্ক করতে পারে — সূচি: `crown_jewel_series/README.md`।
