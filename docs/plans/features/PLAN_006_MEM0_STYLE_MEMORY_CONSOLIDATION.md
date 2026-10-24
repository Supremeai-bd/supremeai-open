---
id: head-of-planning-memory-consolidation-v1-2026-09-17
title: "Head of Planning — Plan #006: mem0/ChatGPT-Style Write-Time Memory Consolidation (বিদ্যমান M3 Canonical ai_memory Store-এর উপর, শূন্য নতুন Dependency, শূন্য নতুন Infra)"
status: proposed
document_role: implementation
owner_circle: Memory Circle (backend/services/memory_service.py — CascadeMemoryService) — PLAN_004-এর হুবহু মালিকানা, একই memory সাবসিস্টেম
target_scope: supremeai_internal
scope: "ONE complete plan, grounded in actual repo code on fresh main 4575104f (2026-09-17) — founder-implemented M3 canonical ai_memory store এবং PLAN-004 distilled write path-এর উপর একটি ছোট, deterministic, LLM-free write-lifecycle সংযোজন (similarity-gated dedup + update-on-conflict + importance wiring); PLAN_LIFECYCLE_POLICY.md (2026-09-17, target_scope taxonomy সহ) কঠোরভাবে অনুসরণ; Gates 0–6; quantitative claims labeled; explicit out-of-scope"
depends_on:
  - backend/services/memory_service.py (CascadeMemoryService — canonical M3 store service: store_memory L351–443 — pg INSERT fallback L389–401, M01 P-A consolidation gate L378; _consolidate_into_existing L444–518; _embed L272, _cosine_similarity L633, query_context L641, _query_via_pgvector_rpc L213–254, _MEMORY_ROW_CAP L54; memory_dedup_enabled L57, _dedup_similarity_threshold L73) — 2026-09-19 founder commit 2a39b5e9 এই প্লানের P-A প্রেসক্রিপশন বাস্তবায়ন করেছেন (কোড কমেন্টে সরাসরি "PLAN_006 P-A (M01)")
  - backend/core/unified_memory.py (founder-implemented PLAN-004 distillation — store_long_term_memory_distilled L189, kill-switch SUPREMEAI_MEMORY_DISTILL L38–44) — এই প্ল্যানের upstream writer
  - backend/core/ai_memory/vector_store.py (L16 _coerce_uuid uuid5 deterministic dedup, L60 upsert_batch) — AutoRAG write path-এ বিদ্যমান upsert precedent
  - backend/core/memory/auto_rag_injector.py (TOP_K=5 L38, MAX_CHARS_PER_MEMORY=400 L39, MIN_RELEVANCE_SCORE=0.55 L41) — downstream recall consumer
  - backend/agents/syncguard/syncguard_agent.py L104 (L86→L104, push-race রিবেজ-করেশন — founder commit 797e003f-এর +19 লাইন) + backend/api/routes/unified_memory_api.py L47/L56 — বাস্তব store callers
  - docs/database/AI_MEMORY_SCHEMA_AUDIT.md L232 (canonical columns — importance_score, updated_at বিদ্যমান কিন্তু মূল write path সেগুলো লেখেই না)
  - docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md ERR-F02 (M3 module-consolidation blueprint — এই প্ল্যান row-level lifecycle, সম্পূরক; ওভারল্যাপ নয়)
  - README.md Constitution #11 (Memory Must Compound), #3 (Reuse Before Creation), #8 (Graceful Degradation), #13 (No Silent Failure), #14 (Sustainable Cost)
  - AGENTS.md Mandatory Rule #9 (Enterprise-Grade Completeness & Safety by Design)
implements:
  - mem0-র "extraction + deduplication + conflict resolution on every add() call" প্যাটার্নের deterministic, LLM-free, right-sized ভার্সন — প্রতিটি store-এ similarity-gated INSERT-vs-UPDATE decision
  - ChatGPT saved-memory মডেল — একই fact বারবার সেভ করলে row-স্ফীত নয়; বিদ্যমান memory update + importance reinforcement
  - canonical schema-র dead columns (importance_score, updated_at) মূল write path-এ প্রথমবার জীবন্ত করা
  - Constitution #11 "Memory Must Compound"-এর তৃতীয় স্তম্ভ: PLAN_002 = in-session compaction, PLAN_004 = write-time quality (distillation), PLAN_006 = write-time identity (consolidation)
supersedes: []
superseded_by: []
source_of_truth: false  # proposed candidate — tested code + contracts remain reality; execution only after explicit founder approval per Gate 2; single-plan execution discipline অনুসারে অনুমোদনের পর এটিই হবে একমাত্র active plan
last_verified: "2026-09-17 (fresh main 4575104f code-read: PLAN-001/002/004 implementation commits 65a1f1f6, 2fbe7fcd, 4575104f পরবর্তী state; store_memory L287–339 sed-verified — pg path blind INSERT, কলাম তালিকা (user_id, session_id, agent_type, task_type, summary, embedding, metadata) — content/importance_score/updated_at কোনোটিই লেখা হয় না, কোনো similarity probe বা UPDATE branch নেই; _embed L208, _cosine_similarity L477, query_context L485, _MEMORY_ROW_CAP=2000 L52 sed-verified; vector_store.py _coerce_uuid L29 + upsert_batch L60 grep-verified; auto_rag_injector.py TOP_K/MIN_RELEVANCE/MAX_CHARS L38–44 sed-verified; syncguard_agent.py L86, unified_memory_api.py L47/L56 grep-verified; grep-verified: CascadeMemoryService-এ dedup/UPDATE-on-similarity কোনো path নেই — এই প্ল্যানের subject সম্পূর্ণ unclaimed); re-verified 2026-09-17 on main 6a2e0464 — founder-এর PLAN-003 implementation commit (backend/core/code_indexer.py + backend/services/dynamic_planner.py) এই প্ল্যানের কোনো evidence file-ই স্পর্শ করেনি (memory_service.py, unified_memory.py, core/ai_memory/vector_store.py, core/memory/auto_rag_injector.py সব 0-diff — evidence transitively holds); re-verified 2026-09-17 on main 68cf886c — founder commit 1dea1fe2 (CI unblock) memory_service.py-তে কেবল ১টি blank-line removal করেছে (def _embed L208-এর পরে) — ফলে L209-এর পরের সব citation ঠিক ১ লাইন উপরে shift করেছে (store_memory L288→L287, pg INSERT path L310–321→L309–320, _cosine_similarity L478→L477, query_context L486→L485); এই প্লানের সব line-ref সেই অনুযায়ী reconciled (উপরের সংখ্যাগুলোই এখন current-main সত্য); বাকি সব evidence file (unified_memory.py, vector_store.py, auto_rag_injector.py, syncguard_agent.py, unified_memory_api.py, AI_MEMORY_SCHEMA_AUDIT.md, defect register) 0-diff; store_memory body-তে আজও কোনো similarity probe/UPDATE branch নেই (grep-verified 68cf886c) — subject still unclaimed); final-state re-verification 2026-09-17 on main 5bdda2e2 + 71b55f8a (rebase + docs-only — evidence files 0-diff): store_memory L287, _cosine_similarity L477, query_context L485 পুনঃgrep-verified — এই প্লান ফাইল নিজেই এখন তার পূর্ণ verification state বহন করছে; re-verified 2026-09-19 on fresh main 0acb7436 — founder commit 2a39b5e9 (feat(wave4)) এই প্লানের P-A প্রেসক্রিপশন M01 P-A হিসেবে বাস্তবায়ন করেছেন: commit message ও কোড কমেন্টে সরাসরি 'PLAN_006 P-A (M01)' উল্লেখ; store_memory-তে similarity-gated consolidation + UPDATE + metadata-importance-bump + SUPREMEAI_MEMORY_DEDUP kill-switch (memory_dedup_enabled L57 — ডিফল্ট true, zero-cost default-ON, অজানা মানে loud warning) + SUPREMEAI_MEMORY_DEDUP_THRESHOLD (ডিফল্ট 0.92, env-tunable — প্লানের success_threshold-এর সাথে হুবহু মিল); প্রেসক্রাইবড টেস্ট-ফাইল backend/tests/memory/test_memory_consolidation.py এখন বিদ্যমান (১২ টেস্ট); ফলে সব line-anchor পুনঃsed-verified ও reconciled: store_memory L351–443, pg INSERT L389–401, dedup gate L378, _consolidate_into_existing L444–518, probe LIMIT L468, _embed L272, _cosine_similarity L633, query_context L641, _query_via_pgvector_rpc L213–254, _MEMORY_ROW_CAP L54; vector_store.py _coerce_uuid L29→L16 (upsert_batch L60 অপরিবর্তিত); auto_rag_injector.py L38–44, unified_memory.py L189–237, syncguard_agent.py L86, unified_memory_api.py L47/L56, AI_MEMORY_SCHEMA_AUDIT.md L232 — সব 0-diff, অপরিবর্তিত; status proposed অপরিবর্তিত — Gate-2 সিদ্ধান্ত founder-এর; FORENSIC LESSON (এই সাইকেল): নাম-ভিত্তিক 0-diff drift-check অস্তিত্বহীন path-এ vacuously true — সেশন-summary-র ভুল path backend/memory/memory_service.py কখনোই অস্তিত্বহীন (git log শূন্য), অথচ একাধিক সাইকেল '0-diff' রিপোর্ট করেছে; ডকুমেন্টের নিজের সাইটেশন সবসময় path-সঠিক ছিল — ভবিষ্যতে সব drift-check existence-first (ফাইল-অস্তিত্ব → তারপর diff); PUSH-RACE REBASE CORRECTION (একই সাইকেল): race-window founder commits 797e003f + 01125a43 (multi-model decoupling #473, M17 P-B) — syncguard_agent.py +19 লাইন → store_long_term_memory_distilled call L86→L104 (grep-verified rebased main-এ), unified_memory_api.py L47/L56 অপরিবর্তিত; উপরের 'syncguard 0-diff' কথাটি 0acb7436-base-এ সত্য ছিল, rebased main-এ reconciled — চূড়ান্ত সব anchor rebased main-এ পুনঃযাচাইকৃত"
code_evidence:
  - backend/services/memory_service.py L351–443 — store_memory(): pg path এখন similarity-gated consolidation বহন করে (M01 P-A, founder commit 2a39b5e9 — কোড কমেন্ট 'PLAN_006 P-A (M01)') — dedup gate L378 (memory_dedup_enabled() + _consolidate_into_existing → UPDATE সফল হলে return), fallback blind INSERT L389–401 INTO ai_memory (user_id, session_id, agent_type, task_type, summary, embedding, metadata) — dedup অফ/probe ব্যর্থ/scope-শূন্য লেখায় আজও প্রচলিত; content/importance_score/updated_at কলাম আজও INSERT কলাম-তালিকায় নেই (importance bump metadata-ভিত্তিক, নতুন কলাম নয়)
  - backend/services/memory_service.py L272 (_embed) + L633 (_cosine_similarity) + L641 (query_context) — probe-এর সব মেশিনারি এই একই ক্লাসে বিদ্যমান — নতুন কোনো dependency বা service লাগেনি (M01 P-A ঠিক এই নীতিতেই বাস্তবায়িত)
  - backend/services/memory_service.py L54 — _MEMORY_ROW_CAP = 2000 + P0 fix comment (in-Python cosine ranking cap) — capped candidate-set প্যাটার্ন এই ফাইলেই প্রমাণিত; M01 P-A-র probe-ও এই নীতিতেই capped (LIMIT clause L468)
  - backend/services/memory_service.py L213–254 — _query_via_pgvector_rpc (match_ai_memories RPC, similarity AS score) — scalable probe path; M01 P-A-র নিজস্ব _consolidate_into_existing (L444–518) এখন (user_id, session_id)-স্কোপড in-Python cosine probe ব্যবহার করে — threshold SUPREMEAI_MEMORY_DEDUP_THRESHOLD ডিফল্ট 0.92 (_dedup_similarity_threshold L73), প্লানের success_threshold-এর সাথে হুবহু মিল
  - backend/core/ai_memory/vector_store.py L16 (_coerce_uuid — uuid5 deterministic dedup) + L60 (upsert_batch) — একই রিপোর অন্য write path-এ upsert-dedupe semantics ইতিমধ্যে accepted pattern (Phase C fix, AI_MEMORY_PHASE_C_EXECUTION_EVIDENCE.md L37/L44) — অর্থাৎ দুই write path-এর row-identity semantics আজ inconsistent
  - backend/core/memory/auto_rag_injector.py L38–44 — TOP_K=5, MAX_CHARS_PER_MEMORY=400, MIN_RELEVANCE_SCORE=0.55 — recall-এ মাত্র ৫টি context-স্লট, প্রতি স্লটে ৪০০ অক্ষর; near-duplicate rows এই দুর্লভ স্লটগুলো নষ্ট করে — M2 Context Engine-এর budget discipline-এর সাথে সরাসরি সাংঘর্ষিক
  - backend/core/unified_memory.py L189–237 — founder-implemented PLAN-004 store_long_term_memory_distilled: distilled summary প্রতিটি store-এ store_memory-তে যায় — dedup না থাকায় একই fact-এর distilled variants প্রতিবার নতুন row হিসেবে জমে
  - backend/agents/syncguard/syncguard_agent.py L104 (push-race রিবেজ-করেশন — L86→L104, founder commit 797e003f-এর +19 লাইন) + backend/api/routes/unified_memory_api.py L47/L56 — বাস্তব callers: syncguard audit ও API endpoint দুই পথেই repeated store ঘটে
  - docs/database/AI_MEMORY_SCHEMA_AUDIT.md L232 — canonical ai_memory contract: (id, user_id, session_id, agent_type, task_type, content, summary, embedding, metadata, agent_id, memory_type, importance_score, created_at, updated_at) — importance_score ও updated_at columns আছে, কিন্তু store_memory-র INSERT কলাম-তালিকায় নেই → dead columns
  - docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md ERR-F02 — M3 module-level consolidation blueprint (15+ store মডিউল → canonical ai_memory); row-level write-lifecycle সেই ব্লুপ্রিন্টেও নেই — এই প্ল্যান সেই গ্যাপ পূরণ করে, ওভারল্যাপ নয়
test_evidence: "founder-delivered 2026-09-19 (commit 2a39b5e9, M01 P-A): backend/tests/memory/test_memory_consolidation.py এখন বিদ্যমান — ১২টি টেস্ট, এই প্লানের ৮-পয়েন্ট প্রেসক্রিপশনের P-A স্কোপ কভার করে (dedup UPDATE, distinct INSERT, fallback, kill-switch, tenant scoping); Gate 4 CI-proof ও Gate 5 live-smoke যাচাই founder-এর সিদ্ধান্তে বহাল — পরবর্তী phase-এর (যদি থাকে) টেস্ট-স্কোপ অপরিবর্তিত"
acceptance_criteria:
  - "pytest backend/tests/memory/test_memory_consolidation.py → নতুন ≥৬ assertion সব PASS"
  - "backend/tests/memory/ → zero regression (বর্তমান baseline 171/171 per PLAN_TO_CODE_TRACEABILITY_MATRIX.md)"
  - "pg path-এ: একই (user_id, session_id) scope-এ identical summary re-store → ai_memory row count অপরিবর্তিত, importance_score বাড়ে, updated_at refresh হয়"
  - "probe-এর যেকোনো ব্যর্থতা → legacy INSERT fallback — store loss শূন্য, ব্যর্থতা warning-লগড (Constitution #13)"
  - "pyproject.toml diff = শূন্য; নতুন কোনো route/infra/dep/network call নেই; AutoRAGInjector ও core/ai_memory/vector_store.py অপরিবর্তিত"
test_evidence_note: "unit/integration টেস্ট contract behavior প্রমাণ করে (Gate 4); Gate 5-এ live evidence — একই fact ৩ বার store → ai_memory-তে ১ row + AutoRAG recall-এ duplicate slot-waste শূন্য — completion claim-এর আগে বাধ্যতামূলক"
risk_and_rollback:
  - "সিঙ্গেল-কমিট, additive change: store_memory-র সিগনেচার অপরিবর্তিত; dedup হলো INSERT-এর আগে একটি guarded branch — বন্ধ করলেই আজকের আচরণ"
  - "Runtime kill-switch: SUPREMEAI_MEMORY_DEDUP=false → সব path byte-সমতুল্য legacy blind INSERT (founder-এর PLAN-004 kill-switch প্যাটার্নেই, unified_memory.py L38–44)"
  - "UPDATE policy destructive নয়: নতুন summary replace + embedding refresh + importance = max(existing, incoming) + bump — কখনো DELETE নয়; merge-history metadata-য় সংরক্ষিত; ভুল positive-এও তথ্য-লস নেই"
  - "Probe সবসময় user_id-scoped (tenant isolation লঙ্ঘন অসম্ভব); probe-এর যেকোনো exception → fallback INSERT — কোনো অবস্থাতেই store হারায় না"
  - "Rollback = একক implementation commit-এর git revert + env kill-switch; কোনো schema migration নেই (বিদ্যমান canonical columns-ই ব্যবহৃত হয়)"
baseline: "(hypothesis — implementation PR-এ মাপা হবে) আজ: identical/near-duplicate fact-এর প্রতিটি store-এ নতুন row — n store = n rows (hypothesis, টেস্টে সংখ্যাগতভাবে প্রমাণযোগ্য); long-lived tenant-এর ai_memory অসীমভাবে স্ফীত; AutoRAG-এর ৫-স্লট recall-এ near-duplicates স্লট waste করে; importance_score ও updated_at কোনোদিন লেখা হয় না"
measurement_method:
  - "(a) টেস্ট-স্যুট কাউন্ট — নতুন dedup/tenant/fallback টেস্ট পাস + tests/memory regression শূন্য (Gate 4)"
  - "(b) controlled store sequence — একই fact ×৩ ও near-duplicate ×২ store করে row-count + importance delta সংখ্যাগতভাবে মাপা (integration টেস্টে)"
  - "(c) Gate-5 live স্মোক — store → query_context round-trip: recall top-5-এ duplicate শূন্য, প্রতিটি slot-এ স্বতন্ত্র fact"
success_threshold: "identical re-store → ঠিক ১ row (১০০% dedup, hard threshold); near-duplicate (cosine ≥ 0.92 — estimate, env-tunable) → update; tenant cross-contamination = শূন্য (hard threshold); বাকি সব সংখ্যা acceptance threshold হিসেবে টেস্টে যাচাই হবে — hypothesis যতক্ষণ না Gate 5-এ measured হয়"
plan_lifecycle: "living — proposed candidate under strengthened PLAN_LIFECYCLE_POLICY (2026-09-17, target_scope taxonomy সহ). ফাউন্ডার অনুমোদন করলে এটিই একমাত্র active execution plan হবে; PLAN_003/PLAN_005 এই প্ল্যানের সম্পূরক প্রার্থী — কোনোটিই অনুমোদন-পূর্বে executable নয়"
---

# Head of Planning — Plan #006: mem0/ChatGPT-Style Write-Time Memory Consolidation

**Status:** proposed (founder review অপেক্ষমাণ — Gate 2 পূর্বে executable নয়)
**Owner:** Memory Circle (CascadeMemoryService) — PLAN_004-এর একই সাবসিস্টেম
**Main anchor:** fresh main `4575104f` (2026-09-17) — রিফ্রেশড 2026-09-19 on `0acb7436` (M01 P-A landed)
**Resource delta:** 0 dependency / 0 infra / 0 CI / 0 LLM-call / 0 schema migration

> **📋 STATUS UPDATE (2026-09-19, fresh main `0acb7436`):** founder commit `2a39b5e9` (feat(wave4)) এই প্লানের **P-A প্রেসক্রিপশন M01 P-A হিসেবে বাস্তবায়ন করেছেন** — কোড কমেন্টে সরাসরি "PLAN_006 P-A (M01)" উল্লেখ; `store_memory`-এ similarity-gated consolidation + UPDATE + metadata-importance-bump + `SUPREMEAI_MEMORY_DEDUP` kill-switch (threshold ডিফল্ট 0.92, env-tunable) + ১২ টেস্টের `backend/tests/memory/test_memory_consolidation.py` (প্লানেই প্রেসক্রাইবড ফাইলনেম)। নিচের সব present-tense gap-statement ও inline line-ref মূল 2026-09-17 baseline (`4575104f`..`f6f6f70b`) বর্ণনা করে — design rationale হিসেবে অক্ষুণ্ণ রাখা হয়েছে; বর্তমান-main সত্য ও রিফ্রেশড anchor ফ্রন্টম্যাটারের code_evidence/last_verified-তে। **status: proposed অপরিবর্তিত — Gate-2 সিদ্ধান্ত founder-এর; এই নোট কোনো completion-certification নয়।**

## বাংলা সারসংক্ষেপ

SupremeAI-র স্থায়ী মেমোরি (Eternal Brain) এখন তিনটি ধাপ পেরিয়েছে: founder M3-এ canonical store হিসেবে Supabase `ai_memory` (vector 384) ঠিক করেছেন, আর PLAN-004 write-time distillation বাস্তবায়িত হয়েছে (4575104f) — অর্থাৎ মেমোরি **লেখার মান** এখন ভালো। কিন্তু মেমোরি **লেখার পরিচয় (identity)** আজও অনিয়ন্ত্রিত: `CascadeMemoryService.store_memory()` (memory_service.py L287–339) প্রতিটি store-কে অন্ধ INSERT করে — একই fact দশবার এলে দশটি আলাদা row, কোনো similarity probe নেই, কোনো UPDATE branch নেই। ফলে (১) সময়ের সাথে ai_memory অসীমভাবে স্ফীত হয়, (২) AutoRAGInjector-এর মাত্র ৫টি recall-স্লট (TOP_K=5) near-duplicate দিয়ে ভরে যায় — M2 Context Engine-এর কঠোর budget discipline-এর ঠিক বিপরীতে, (৩) canonical schema-র `importance_score` ও `updated_at` columns — যেগুলো এই কাজের জন্যই তৈরি — মূল write path কোনোদিন লেখেই না (dead columns)।

প্রতিযোগীরা এই সমস্যাটি সমাধান করেছে: **mem0** প্রতিটি `add()` কলে deduplication ও conflict resolution চালায়; **ChatGPT** saved memories-কে deduplicated, updatable সেট হিসেবে রাখে; **Letta/MemGPT**-এর tiered memory-র পুরো প্রেমিসই হলো archival যেন unbounded duplicate-এ ভরে না যায়। এই প্ল্যান সেই প্যাটার্নের **deterministic, LLM-free, right-sized** ভার্সন: store-এর ঠিক আগে user-scoped top-5 similarity probe (একই ফাইলের বিদ্যমান `_embed` + `_cosine_similarity` + pgvector RPC দিয়ে), threshold-এর উপরে মিললে UPDATE (importance bump সহ), না মিললে INSERT — সবকিছু env kill-switch (SUPREMEAI_MEMORY_DEDUP) ও graceful fallback সহ। এতে নতুন dependency নেই, infra নেই, LLM-call নেই, schema migration নেই — শুধু বিদ্যমান মেশিনারির সঠিক ব্যবহার।

Constitution #11-এর পূর্ণতা: **PLAN_002 = in-session compaction (হিস্ট্রি ছোট), PLAN_004 = write-time quality (সারমর্ম ভালো), PLAN_006 = write-time identity (duplication শূন্য)** — তিনটি মিলে মেমোরি সত্যিকার অর্থে "compound" করে।

---

## Part 1 — Competitor Intelligence (dated external evidence, verified 2026-09-17)

### ১.১ mem0 — write-time deduplication + conflict resolution

- mem0-র মূল স্থাপত্য: প্রতিটি `add()` কলে **extraction → deduplication → conflict resolution** পাইপলাইন চলে — নতুন তথ্য বিদ্যমান মেমোরির সাথে মিলিয়ে ADD/UPDATE/NOOP সিদ্ধান্ত নেওয়া হয় (web search 2026-09-17; fresh result ~2026-09-15: "Mem0 runs extraction, deduplication, and conflict resolution inside its pipeline on every add() call")।
- মূল প্রকাশ: "Mem0 introduces a scalable long-term memory architecture that dynamically extracts…" (May 15, 2025)।
- **সৎ সতর্কতা (honest caveat):** mem0 v2.0.0 বাস্তবে ADD-only extraction architecture-এ গেছে এবং UPDATE/conflict behavior-এ documentation–implementation mismatch প্রমাণিত হয়েছে (Apr 20, 2026) — অর্থাৎ LLM-driven conflict resolver এখনও অপরিণত প্যাটার্ন। এ কারণেই এই প্ল্যান **LLM-free deterministic similarity-gated upsert** বেছে নিয়েছে — প্রমাণিত, সসীম খরচের, টেস্টযোগ্য মিনিমাল কোর; semantic conflict resolution স্পষ্টভাবে out-of-scope (Part 3)।
- Vendor benchmark: "agent memory layer token cost ৯০% পর্যন্ত কমাতে পারে" (May 5, 2026) — **vendor-published figure; SupremeAI-র নিজস্ব কোনো expectation নয়**; এই প্ল্যানের কোনো cost claim vendor figure-এর উপর দাঁড়ায় না।

### ১.২ ChatGPT Memory (OpenAI)

- ChatGPT-র saved memories আচরণগতভাবে একটি **deduplicated, updatable সেট**: ব্যবহারকারী একই তথ্য আবার বললে নতুন memory-item তৈরি হয় না — বিদ্যমানটি update হয়; ইউজার সেট দেখতে ও বদলাতে পারে (product behavior — সাধারণভাবে প্রত্যক্ষ; তারিখযুক্ত fresh citation এই মুহূর্তে সংগ্রহযোগ্য নয়, তাই এটিকে **product-behavior observation** হিসেবেই label করা হলো, vendor doc-claim হিসেবে নয়)।
- SupremeAI-র জন্য শিক্ষা: মেমোরির মান লেখার **সংখ্যা** নয়, লেখার **অনন্যতা ও সাম্প্রতিকতা**-তে। একই fact-এর পাঁচটি row recall-কে পাঁচগুণ ভালো করে না — উল্টে ৫-স্লটের ৪টি নষ্ট করে।

### ১.৩ Letta (f.k.a. MemGPT) + Claude Memory

- MemGPT: OS-অনুপ্রাণিত memory hierarchy — core / recall / archival (Aug 12, 2025); Letta তিন স্তরের মেমোরি মডেল (Mar 15, 2026); explicit `core_memory_append` / `archival_memory_insert` tools (Jun 16, 2026 result)।
- এই প্ল্যান সেই hierarchy-র **row-identity ভিত্তিটাই** ধরে: archival memory যদি unbounded near-duplicate হয়, তবে tiering নামের বাকি স্থাপত্য অর্থহীন। Letta-র write-time distillation দিকটি SupremeAI ইতিমধ্যে গ্রহণ করেছে (PLAN-004, implemented 4575104f) — এই প্ল্যান তার সরাসরি পরবর্তী ধাপ।
- Claude Code-এর MEMORY.md একটি একক, সম্পাদনাযোগ্য ডকুমেন্ট — structurally-ই একটি "consolidated" memory; ভিন্ন মডেল, তবে একই নীতি: পুনরাবৃত্তি জমে না, merge হয়।

### ১.৪ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল

| প্রতিযোগী | যা করে | SupremeAI আজ (4575104f-verified) | গ্যাপ |
|---|---|---|---|
| mem0 | প্রতিটি add()-এ dedup + conflict resolution | `store_memory` blind INSERT (L309–320) | ✋ **এই প্ল্যান** |
| ChatGPT | updatable, deduplicated memory সেট | blind INSERT; dead importance/updated_at columns | ✋ **এই প্ল্যান** |
| Letta/MemGPT | tiered memory + explicit write tools | canonical store একমাত্র (M3) + distillation (PLAN-004) | আংশিক — row-lifecycle নেই |
| Claude Code | একক consolidated MEMORY.md | ভিন্ন মডেল (file-based) | প্রযোজ্য নয় |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main 4575104f, 2026-09-17)

**বিদ্যমান প্ল্যান/ডক-ওভারল্যাপ অনুসন্ধান (সবগুলো পুনঃপাঠ করা হয়েছে):**

| বিদ্যমান | বিষয় | এই প্ল্যানের সাথে সম্পর্ক |
|---|---|---|
| PLAN_001 (complete) | Anthropic prompt caching — LLM gateway খরচ | ভিন্ন স্তর; সম্পর্কহীন |
| PLAN_002 (complete) | WS চ্যাট-হিস্ট্রি semantic compaction — **in-session** | ভিন্ন lifecycle-স্তর; সম্পূরক |
| PLAN_003 (complete — implemented 6a2e0464, founder-verified এই চক্রেই) | Aider-style repo map — Epistemic Probe-র কোডবেস-দৃষ্টি | ভিন্ন সাবসিস্টেম; সম্পর্কহীন |
| PLAN_004 (complete) | write-time **distillation** — সারমর্মের **মান** | upstream সম্পূরক: distillation লেখার মান ভালো করে, এই প্ল্যান লেখার **পরিচয়** (duplication) নিয়ন্ত্রণ করে — একই store-এ দুই ভিন্ন সমস্যা |
| PLAN_005 (proposed) | user-controlled /compact — WS UX | ভিন্ন স্তর (in-session, user-facing); সম্পর্কহীন |
| M3 decision table + ERR-F02 (OPEN, blueprint pinned) | **module-level** consolidation (15+ store মডিউল → canonical ai_memory) | ভিন্ন granularity: M3 ঠিক করে **কোন দোকানে** মেমোরি থাকবে; এই প্ল্যান ঠিক করে **একই fact দোকানে কতবার** থাকবে — সম্পূরক, কোনো conflict নেই |
| M2 Context Engine (e48daaf0, complete) | HTTP-route budgeted assembly | সংলাপ শক্তিশালীকারী: context budget যত কঠোর, duplicate recall-স্লট তত বেশি ব্যয়বহুল |

**Defect register cross-check:** ERR-F01–F04 ও full-recheck F/B আইটেমগুলোতে row-level memory dedup/lifecycle-এর কোনো বিদ্যমান বা পরিকল্পিত আইটেম নেই (grep-verified 2026-09-17) — subject সম্পূর্ণ unclaimed।

**কি আছে / কি নাই-এর সংক্ষিপ্ত প্রমাণ:** বিস্তারিত নিচে §২.১/§২.২-তে; সারমর্ম: probe-এর সব মেশিনারি (`_embed` L208, `_cosine_similarity` L477, pgvector RPC L149, capped-scan প্যাটার্ন L52) একই ক্লাসে আছে, কিন্তু `store_memory` সেগুলো লেখার সময় ব্যবহারই করে না — এবং একই রিপোর অন্য write path (`vector_store.py` uuid5 upsert) প্রমাণ করে upsert semantics এই কোডবেসে already-accepted pattern।

---

## Part 2 — Plan #006: Six-Field Complete Plan

### ২.১ কি আছে (code-verified, fresh main 4575104f)

1. **Canonical store + tri-path service:** `CascadeMemoryService` (memory_service.py) — pg (`_use_pg`), SQLite fallback, bounded in-process degraded buffer (P0) — তিন path-ই `store_memory`-তে গাঁথা।
2. **Probe-এর সম্পূর্ণ মেশিনারি একই ক্লাসে:** `_embed` (L208), `_cosine_similarity` (L477), `query_context`-এর cosine ranking (L485+), pgvector RPC `_query_via_pgvector_rpc` (L149–188, `match_ai_memories`, `similarity AS score`)।
3. **Capped-scan প্যাটার্ন প্রমাণিত:** `_MEMORY_ROW_CAP = 2000` (L52) — P0 fix হিসেবেই in-Python scan cap করার নীতি এই ফাইলে গৃহীত।
4. **Upsert precedent এই রিপোতেই:** `core/ai_memory/vector_store.py` `_coerce_uuid` (L29, uuid5 deterministic dedup) + `upsert_batch` (L60) — AutoRAG path Phase C fix-এ upsert-dedupe semantics প্রতিষ্ঠিত (AI_MEMORY_PHASE_C_EXECUTION_EVIDENCE.md L37/L44)।
5. **Kill-switch প্যাটার্ন প্রতিষ্ঠিত:** PLAN-004-এর `SUPREMEAI_MEMORY_DISTILL` (unified_memory.py L38–44) — env-gated graceful fallback-এর founder-approved নমুনা।
6. **Canonical schema ready:** `importance_score`, `updated_at`, `content` columns আছে (AI_MEMORY_SCHEMA_AUDIT.md L232; Alembic single-head contract) — লেখার অপেক্ষায়।
7. **Recall consumer সংজ্ঞায়িত:** AutoRAGInjector — TOP_K=5, MIN_RELEVANCE_SCORE=0.55, MAX_CHARS_PER_MEMORY=400 (L38–44); `query_context` score-desc sort (L485+)।

### ২.২ কি নাই

1. `store_memory`-তে (L287–339) **কোনো similarity probe নেই** — একই summary হাজারবার এলে হাজারটি row।
2. **কোনো UPDATE-on-similarity branch নেই** — pg path-এ কেবল INSERT (L309–320)।
3. **importance_score / updated_at লেখা হয় না** — INSERT কলাম-তালিকায় নেই → canonical contract-এর dead columns।
4. **কোনো reinforcement/bump নেই** — recall হোক বা না হোক, মেমোরির গুরুত্ব কখনো পরিবর্তিত হয় না।
5. **দুই write path-এর semantics inconsistent** — AutoRAG path (uuid5 upsert) বনাম Cascade path (blind INSERT)।
6. **store-path-এ কোনো decision provenance নেই** — কোনো row কেন সৃষ্টি হলো, কোনো লগ/মেটাডেটা নেই।

### ২.৩ কি করতে হবে

`CascadeMemoryService.store_memory()`-এর pg path-এ একটি **guarded dedup branch** যোগ হবে:

```text
store_memory(content, summary, ...):
  যদি SUPREMEAI_MEMORY_DEDUP == false  → legacy blind INSERT (আজকের আচরণ)
  probe চেষ্টা করো (user_id-scoped, top-5):
      pgvector RPC ব্যবহারযোগ্য হলে  → _query_via_pgvector_rpc-style top-5
      নাহলে                        → _MEMORY_ROW_CAP-capped recent rows + _cosine_similarity
  best_similarity ≥ threshold (env, default 0.92 — estimate):
      → UPDATE ওই row: summary/embedding refresh, importance_score = max(old, incoming)+bump,
        updated_at = NOW(), metadata-য় merge-history append, decision logger.info
  best_similarity < threshold বা probe ফাঁকা:
      → INSERT (আজকের মতো) — তবে এখন থেকে importance_score/updated_at-ও লিখে
  probe-এর যেকোনো exception:
      → legacy blind INSERT fallback + warning লগ (No Silent Failure)
```

সাথে: নতুন টেস্ট ফাইল, honest telemetry লগ, এবং SQLite/degraded path-এর অপরিবর্তিততা নিশ্চিতকরণ টেস্ট।

### ২.৪ কিভাবে করব (file-by-file)

**ফাইল ১ — `backend/services/memory_service.py` (একমাত্র প্রোডাকশন-টাচ):**

- মডিউল-টপে দুটি কনস্ট্যান্ট: `MEMORY_DEDUP_ENV = "SUPREMEAI_MEMORY_DEDUP"` ও `MEMORY_DEDUP_SIMILARITY_ENV = "SUPREMEAI_MEMORY_DEDUP_SIMILARITY"` (default 0.92 — **estimate**; PLAN-004-এর `MEMORY_DISTILL_ENV` নমুনায়)।
- নতুন ব্যক্তিগত মেথড `_find_duplicate(summary_embedding, user_id, session_id) -> tuple[int|None, float]`: user_id-scoped top-5 similarity probe — pgvector RPC path উপলব্ধ হলে সেটি, নাহলে `_MEMORY_ROW_CAP`-capped recent-rows + `_cosine_similarity`; **কোনো exception-ও caller-এ fallback ট্রিগার করবে** (মেথড নিজে raise করবে না — ভুল লুকাবে না, ছুঁড়বে)।
- `store_memory`-র pg branch-এ INSERT-এর ঠিক আগে guarded sequence: kill-switch চেক → probe → মিললে `UPDATE ai_memory SET summary=%s, embedding=%s, metadata=%s, importance_score=%s, updated_at=NOW() WHERE id=%s` → না মিললে INSERT (কলাম-তালিকায় `importance_score` ও `updated_at` যোগ — `metadata.importance` থাকলে সেটি, নাহলে neutral default 0.5)।
- প্রতিটি সিদ্ধান্তে `logger.info("memory store decision: %s sim=%.3f row=%s", ...)` — honest telemetry (Constitution #13)।
- SQLite path (L327–340 `ON CONFLICT(file_path)`) ও degraded buffer path **হুবহু অপরিবর্তিত** — ওরা আগেই upsert-semantic; এই প্ল্যান pg canonical path-ই ধরে।

**ফাইল ২ — `backend/tests/memory/test_memory_consolidation.py` (নতুন, শুধু টেস্ট):**

- বিদ্যমান `tests/memory/` ট্রি-র ফিক্সচার প্যাটার্নে (local SQLite/__main__ self-test নীতি অনুসরণ করে কোনো লাইভ store স্পর্শ নয়): §frontmatter `test_evidence`-র ৮টি দৃশ্য।
- Tenant-isolation টেস্ট স্পষ্ট: user A-র identical store user B-র কোনো row update করে না (hard threshold: contamination = শূন্য)।

**ফাইল ৩ — ডকস (এই প্ল্যানের নিজস্ব প্রতিশ্রুতি):** implementation PR-এ PLAN_TO_CODE_TRACEABILITY_MATRIX.md-এর Memory-row হালনাগাদ (founder-এর update rule অনুযায়ী)।

**কী টচ হবে না:** `unified_memory.py` (PLAN-004 মেশিনারি — অপরিবর্তিত), `auto_rag_injector.py`, `core/ai_memory/vector_store.py`, সব frontend, সব route, `pyproject.toml`, কোনো Alembic migration (বিদ্যমান columns-ই লেখা শুরু হবে)।

### ২.৫ বেনিফিট

1. **Recall-মান:** AutoRAG-এর ৫টি দুর্লভ স্লটে near-duplicate বসে যাওয়া বন্ধ — প্রতি চ্যাটে একই খরচে বেশি স্বতন্ত্র, প্রাসঙ্গিক past-context (M2 budget discipline-এর সাথে সামঞ্জস্য; প্রভাবের মাত্রা = **hypothesis**, Gate 5-এ মাপা হবে)।
2. **Store-স্বাস্থ্য:** unbounded row-স্ফীত বন্ধ — `_MEMORY_ROW_CAP`-capped scan ও pgvector index-এর উপর চাপ বৃদ্ধি থামে (দীর্ঘমেয়াদি, **estimate**)।
3. **ভবিষ্যৎ-ভিত্তি:** `importance_score` প্রথমবার লেখা হয় → decay/TTL/ranking-এর মতো ভবিষ্যৎ ক্যান্ডিডেট (Part 6) প্রথমবারের মতো সম্ভব হয় — আজ নয়, কাল নয়; ভিত্তি আজ।
4. **Consistency:** দুই write path-এর row-identity semantics কাছাকাছি আসে — একই রিপোর দুই দোকানে একই fact-এর দুই আচরণ নয়।
5. **Constitution #11 পূর্ণতা:** compaction (PLAN_002) + distillation (PLAN_004) + consolidation (এই প্ল্যান) — মেমোরি এবার সত্যিই "compound" করে।

### ২.৬ ক্ষতি/রিস্ক (honest)

1. **ভুল-positive merge:** দুটি ভিন্ন fact যদি cosine ≥ 0.92 হয়, একটি আরেকটির মধ্যে merge হয়ে যেতে পারে। Mitigation: threshold env-tunable, metadata-তে merge-history (পুরনো summary সংরক্ষিত), **কখনো DELETE নয়**, kill-switch — এবং 0.92 threshold-টি ইচ্ছাকৃতভাবে উঁচু (estimate; টেস্টে near-dup ও distinct-এর সীমানা প্রমাণ করা হবে)।
2. **Probe latency:** প্রতি store-এ একটি অতিরিক্ত top-5 RPC — store কল-হার নগণ্য বলে **hypothesis**; probe ব্যর্থ হলে fallback-এ latency আজকের সমান।
3. **আচরণ-পরিবর্তন:** পুরনো ব্যবহারকারী "আমি একই কথা দুবার বলেছি, মেমোরিতে দুটি ঢুকেছিল" — এখন একটি হবে; এটিই উদ্দেশ্য, তবে পর্যবেক্ষণযোগ্য পরিবর্তন — telemetry-তে দৃশ্যমান থাকবে।
4. **SQLite/degraded path parity:** ওখানে কোনো dedup probe যোগ করা হচ্ছে না (বিদ্যমান upsert-ই যথেষ্ট) — তিন path-এর আচরণ ১০০% অভিন্ন নয়; সৎ ঘোষণা: এই প্ল্যান কেবল canonical pg path নিয়ন্ত্রণ করে।

---

## Part 3 — Explicit Out-of-Scope (সুস্পষ্ট ঘোষণা)

1. **LLM-driven semantic conflict resolution** (mem0-স্টাইল ADD/UPDATE/DELETE decision) — Phase 2 hypothesis; খরচ + অপরিণত প্যাটার্ন (mem0 v2-র ADD-only বাস্তবতা, Apr 20 2026-এর observation)।
2. **TTL / decay / garbage-collection** — importance_score জমা হওয়ার পরেই অর্থবহ; ভবিষ্যৎ ক্যান্ডিডেট (Part 6)।
3. **Cross-user dedup** — কখনোই নয়; tenant isolation অবাধ্যাতামূলক।
4. **AutoRAGInjector বা `core/ai_memory/vector_store.py`-তে কোনো পরিবর্তন** — ওদের uuid5/upsert আচরণ এই প্ল্যানের অনুপ্রেরণা, স্পর্শের বস্তু নয়।
5. **Embedding মডেল/ডাইমেনশন পরিবর্তন** (vector 384 অপরিবর্তিত)।
6. **Read-path threshold পরিবর্তন** (MIN_RELEVANCE_SCORE=0.55 ইত্যাদি অপরিবর্তিত)।
7. **`backend/memory/`-র 15+ পুরনো মডিউল স্পর্শ** — ERR-F02/M3-এর এক্তিয়ার (module consolidation); এই প্ল্যান row-lifecycle।
8. **WS চ্যাট বা HTTP chat route-এ কোনো পরিবর্তন** — PLAN_002/005-এর এক্তিয়ার।

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | একটাই প্ল্যান; decay/TTL আইডিয়া Part 6 reference-এ |
| 2. Small change to existing code | ✅ | একটি প্রোডাকশন ফাইলে guarded branch; নতুন ফাইল কেবল tests/memory ট্রিতে |
| 3. No new infrastructure | ✅ | Render/Supabase/GH Actions — কিছুই নতুন নয়; কোনো migration নেই |
| 4. No CI cost amplification | ✅ | টেস্টে লোকাল store ফিক্সচার; কোনো LLM/network call নেই |
| 5. No credit-burn risk | ✅ | probe LLM-free (embedding+cosine); zero-cost chain |
| 6. No academic leaderboard | ✅ | সরাসরি প্রোডাক্ট ক্ষমতা — recall মান ও store স্বাস্থ্য |
| 7. Realistic resource budget | ✅ | top-5 RPC per store; কল-হার নগণ্য (hypothesis, লগড) |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main 4575104f code-read; `code_evidence`-তে line refs |

| Constitution ধারা | প্রভাব |
|---|---|
| #1 Eternal Brain | ✅ মূল লক্ষ্য — মেমোরি এখন পরিচয়-সচেতনভাবে জমে |
| #3 Reuse Before Creation | ✅ নতুন dep/subsystem/store শূন্য — `_embed`+`_cosine`+RPC পুনঃব্যবহার |
| #5 Verify Before Trust | ✅ Gate 4 টেস্ট + Gate 5 live স্মোক বাধ্যতামূলক |
| #8 Graceful Degradation | ✅ probe failure → legacy INSERT; kill-switch → আজকের আচরণ |
| #11 Memory Must Compound | ✅ প্রাথমিক অ্যাংকর — তৃতীয় স্তম্ভ |
| #13 No Silent Failure | ✅ প্রতিটি সিদ্ধান্ত লগড; fallback warning-লগড |
| #14 Sustainable Cost | ✅ বিদ্যমান ফ্রি-কোটার মধ্যে সসীম; store-স্ফীতি থামানোই দীর্ঘমেয়াদি সাশ্রয় |

---

## Part 5 — Verification & Acceptance (Gates 4–6)

1. **Gate 4 (verification):** `pytest backend/tests/memory/ -v` → সব বিদ্যমান + নতুন consolidation টেস্ট PASS; `SUPREMEAI_MEMORY_DEDUP=false`-তে আচরণ byte-সমতুল্য legacy; pg/SQLite/degraded তিন path-এর টেস্ট-প্রমাণ।
2. **Gate 5 (outcome evidence):** controlled store sequence (একই fact ×৩, near-dup ×২, distinct ×২) — row-count/importance/uniqueness সংখ্যাগত রেকর্ড এই প্ল্যানের আউটকাম-ব্লকে; **threshold মিস → Gate 6 অনুযায়ী failed/blocked ঘোষণা**।
3. **Deployment evidence (যখন প্রযোজ্য):** deployed ≠ successful — লগে store-decision হার (insert vs update vs fallback) পর্যবেক্ষণ; fallback-হার অস্বাভাবিক হলে pause।
4. **Gate 6 (unlock):** সম্পূর্ণ প্রমাণ-রেকর্ড ছাড়া `complete` নয়; পরবর্তী execution plan কেবল তখনই স্কাউট-টু-প্রোপোজড।

**Rollback:** একক ইমপ্লিমেন্টেশন কমিট revert; runtime kill-switch (env); কোনো data/config/schema migration নেই — পুরনো rows বৈধ থাকে, merge-history metadata-য় বিপরীতযোগ্য।

---

## Part 6 — পরবর্তী ক্যান্ডিডেট লাইনেজ (শুধু reference; rule 10 — candidate list ≠ execution queue)

- **PLAN_003 (complete — implemented 6a2e0464):** Aider-style repo map — এই চক্রেই founder বাস্তবায়ন করেছেন (backend/core/code_indexer.py); এই প্ল্যানের সাথে সম্পর্কহীন, প্রমাণ অপরিবর্তিত।
- **PLAN_005 (proposed):** user-controlled /compact — সম্পূরক প্রার্থী, অপরিবর্তিত।
- **(reference, unclaimed) memory decay/TTL + importance-ranked recall:** এই প্ল্যানের importance_score write হওয়ার **পরেই** অর্থবহ — এই প্ল্যানের প্রাকৃতিক উত্তরসূরি, আলাদা প্ল্যান হিসেবে ভবিষ্যৎ চক্রে প্রস্তাব হতে পারে (hypothesis; আজ কিছুই প্রস্তাব করা হলো না)।
- **(reference, unclaimed) repo-map MCP tool:** PLAN_003 এখন implemented (6a2e0464 — code_indexer.py), তাই একটি MCP tool candidate এখন grounded speculation নয়; ভবিষ্যৎ চক্রে প্রস্তাবযোগ্য (আজ কিছুই প্রস্তাব করা হলো না — policy rule 10)।
