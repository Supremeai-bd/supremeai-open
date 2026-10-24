---
id: crown-jewel-module-05-self-evolution-power-up-v1-2026-09-17
title: "Crown Jewel Module Series — Module 05: Self-Evolution & Learning Loop Power-Up ('Universal Self-Learning' প্রতিশ্রুতিকে সত্য করা — সংগ্রহ হয় কিন্তু আচরণ বদলায় না এমন লুপের শেষ-মাইল জোড়ার পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Evolution Circle (backend/core/learning/ + backend/core/self_evolution/ + backend/evolution/ + backend/adaptive_engine/ + backend/learning/ + backend/api/routes/evolution.py + backend/core/startup/agents.py-লার্নিং-অংশ)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ৫ — একটি মডিউল (Self-Evolution & Learning Loop), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — fresh main 9aca8d0 (2026-09-17) sed/grep/wc-যাচাইকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; প্রতিটি ধাপে flag+kill-switch; 721-route surface-এ zero-regression লক্ষ্য"
depends_on:
  - "backend/core/llm/telemetry.py (track_llm_call → _record_durable L153-192 → LearningStore.record_event → Postgres learning_events — সংগ্রহ-স্তর লাইভ ও স্থায়ী)"
  - "backend/core/learning/ (store.py LearningStore 697 লাইন; loop.py LearningLoopAgent L55 — startup agents.py:209-এ ENABLE_LEARNING_LOOP default false-গেট; provider_scorer.py:169-170 get_adaptive_routing_enabled default OFF)"
  - "backend/core/self_evolution/ (7,764 লাইন — FitnessEngine 299 লাইন লাইভ completion.py:362-374; AutoSkillCreator 587 লাইন /api/v1/evolution/forge-এ লাইভ; বাকি বেশিরভাগ env-gated/dormant)"
  - "backend/database/supabase_client.py (L1497 update_improvement_proposal_status — production caller শূন্য: grep = definition + warning-log + 1 টেস্ট)"
  - "backend/adaptive_engine/_store.py (L38-58 — SUPABASE_ALLOW_DB_DEGRADATION=false হলে প্রতি কলে fresh IN-MEMORY connection — প্রোডাকশনে ক্ষণস্থায়ী স্মৃতি)"
  - "backend/core/unified_learning.py (L598-600 _persist stub 'Would save to database here' + pass — মৃত-লেখা ইঞ্জিন, 683 লাইন)"
  - "backend/api/routes/evolution.py (L421-432 save_swarm_blueprint আপাত-সাফল্য 'আপাতত সাকসেস রেসপন্স রিটার্ন করছি'; L261-273 swarm-graph simulated)"
  - "backend/evolution/advanced_evolution_engine.py (L45 — evolutionary_gain = overall_gain * 1.15 — ফেব্রিকেটেড 15% বৃদ্ধি)"
  - "backend/evolution/ (auto_skill_creator-forge পথে canary/benchmark/fitness/artifact_integrity লাইভ L458-461; MemoryConsolidator 247 লাইন dormant)"
  - "backend/learning/ (pattern_recognizer একমাত্র নাগালযোগ্য living_engine.py:27 দিয়ে; hypothesis/outcome/bridge/evidence dormant)"
  - ".env.example (L134 ENABLE_EVOLUTION=false; ENABLE_LEARNING_LOOP-এর কোনো entry নেই)"
  - "docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md (§7.1 tools/learning fakes L730-734; resource_registry L123-129 NotImplemented)"
  - "docs/plans/features/SUPREMEAI_REAL_INTELLIGENCE_EVOLUTION_PLAN.md (১০-ধাপ Cognitive Loop সংজ্ঞা L15-40)"
  - "README.md Constitution #11 'Memory Must Compound' (L167)"
implements:
  - "শেষ-মাইল apply-path — proposal→approve→canary→প্রয়োগ: প্রথমবার এন্ড-টু-এন্ড পরিমাপযোগ্য আচরণ-পরিবর্তন (মানুষ-অনুমোদিত)"
  - "সুরক্ষিত লুপ-ডিফল্ট — ENABLE_LEARNING_LOOP=true + bounded exploration: লুপ পর্যবেক্ষণ→প্রস্তাব→অন্বেষণ শুরু করবে"
  - "Constitution #11-এর প্রয়োগ-অর্থ: সংরক্ষণে নয়, আচরণে যৌগিকীকরণ (compounding in behavior, not just storage)"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (fresh main 9aca8d0: startup/agents.py L209 sed-verified 'ENABLE_LEARNING_LOOP, false'; .env.example grep ENABLE_LEARNING_LOOP = শূন্য-entry; _store.py L38-45 sed-verified IN-MEMORY; evolution.py L421-432 sed-verified আপাত-সাফল্য; advanced_evolution_engine.py L45 sed-verified *1.15; supabase_client.py:1497 caller-grep = 1 টেস্ট; unified_learning.py L598-600 sed-verified pass-stub; .env.example:134 ENABLE_EVOLUTION=false)"
code_evidence:
  - "backend/core/startup/agents.py L209 — `if os.getenv('ENABLE_LEARNING_LOOP', 'false')...` — aggregate-স্তর ডিফল্ট বন্ধ; .env.example-এ এন্ট্রিই নেই → কেউ আবিষ্কারও করতে পারে না"
  - "backend/database/supabase_client.py L1497 — update_improvement_proposal_status — improvement_proposals-এর একমাত্র apply-দরজা; grep: definition + warning + 1 টেস্ট — production apply-executor অস্তিত্বহীন"
  - "backend/api/routes/evolution.py L381-417 — /proposals/{id}/approve ভিন্ন স্টোরের (SQLAlchemy CodeProposal) মিউটেট করে, শেষে মন্তব্য 'এখানে ভবিষ্যতে আমাদের অটোনোমাস মার্জ লজিক বা GitOps ট্রিগার কল হবে' — অনুমোদন হয়, প্রয়োগ হয় না"
  - "backend/adaptive_engine/_store.py L38-58 — SUPABASE_ALLOW_DB_DEGRADATION=false (ডিফল্ট) → প্রতি কলে IN-MEMORY — ExperienceDatabase-এর সব শেখা রিস্টার্টে মুছে যায়; supabase_vector_backend.py (pgvector) লেখা কিন্তু অব্যবহৃত"
  - "backend/core/llm/completion.py L378-401 — ENABLE_EVOLUTION_LEARNING=true হলে EvolutionEngine.learn_from_success চলে কিন্তু শুধু task_history লেখে — পাঠক শূন্য (write-only learning)"
  - "backend/evolution/advanced_evolution_engine.py L45 — evolutionary_gain = overall_gain × 1.15 — কোনো ভিত্তি ছাড়া ফেব্রিকেটেড ১৫% বৃদ্ধি"
  - "backend/api/routes/evolution.py L421-432 — save_swarm_blueprint: 'আপাতত সাকসেস রেসপন্স রিটার্ন করছি' + সময়-ভিত্তিক fake flow_id; L261-273 swarm-graph 'Simulated…prototype'"
  - "backend/core/unified_learning.py L598-600 — _persist: 'Would save to database/vector store here' + pass — 683-লাইন ইঞ্জিন স্মৃতিহীন; ৪টি deprecated wrapper এটিকে খাওয়ায়"
  - "backend/core/self_evolution/ — digital_twin (2,220), adversarial_defense (612), ewc (551), neural_symbolic (696), federated (21), EvolutionReActAgent (153) — মোট ~4.9K লাইন zero production caller"
  - "backend/core/llm/completion.py L362-374 — FitnessEngine.track_execution প্রতি সাফল্যে লাইভ — একমাত্র সবসময়-জাগ্রত শেখা-রেখা; L158-181 — adaptive exploration কেবল চেইন-লেজে ১ candidate, গেট OFF"
test_evidence: "none yet — প্রতিটি Phase-এর execution প্ল্যান সংজ্ঞায়িত করবে; সমষ্টিগত চুক্তি: (১) apply-path integration টেস্ট (proposal→approve→canary→bounded apply→প্রস্তাব PROMOTED), (২) গেট-অন টেস্ট (ENABLE_LEARNING_LOOP=true-তে run_cycle প্রস্তাব-তৈরি), (৩) বিদ্যমান ~4,100 টেস্ট-LOC (test_learning_store 525, test_llm_gateway_completion 1,001, test_sprint56_adaptation_promotion 176, test_governed_self_evolution_closed_loop 179) zero regression, (৪) flag-off → আজকের আচরণ byte-সমতুল্য"
acceptance_criteria:
  - "প্রতিটি Phase আলাদা ছোট execution প্ল্যান হিসেবে Gate 0–6 পাস"
  - "Apply-path সংজ্ঞা: improvement_proposals-এর অনুমোদিত প্রস্তাব canary-সহ বাস্তব প্রয়োগ হয় — status PROMOTED + পরিমাপযোগ্য আচরণ-পরিবর্তন (retry-policy/fallback-reorder-সীমাবদ্ধ ভোকাবুলারি)"
  - "লুপ-জাগরণ সংজ্ঞা: ডিফল্ট-ডিপ্লয়ে learning-events→rollup→proposal চক্র চলে; exploration কেবল চেইন-লেজে ১ candidate + sample-tier guardrail"
  - "স্থায়িত্ব-সংজ্ঞা: ExperienceDatabase pgvector-ব্যাকএন্ডে — রিস্টার্ট-পরবর্তী semantic-cache হিট প্রমাণসহ"
  - "সত্য-সংজ্ঞা: ৪টি false-assurance surface (forge/simulated/*1.15/approve-without-apply) বাস্তব বা honest-error; zero-regression CI প্রমাণ"
test_evidence_note: "Gate 4-এ apply-integration ও গেট-অন টেস্ট; Gate 5-এ live — বাস্তব proposal-এর canary-প্রয়োগ পর্যবেক্ষণ + রিস্টার্ট-পরবর্তী cache-hit; completion claim-এর আগে বাধ্যতামূলক"
risk_and_rollback:
  - "সবচেয়ে বড় ঝুঁকি: স্বয়ংক্রিয় আচরণ-পরিবর্তন ভুল হলে মান-অবনতি — প্রশমন: apply-ভোকাবুলারি সীমিত (retry-policy/fallback-reorder), ২-ধাপ অনুমোদন+canary (CanaryManager বিদ্যমান), রোলব্যাক এক-কমান্ড"
  - "গেট-অনে অতিরিক্ত লেখা/হিসাব — প্রশমন: LearningStore bounded deque + batch flush বিদ্যমান; exploration কেবল লেজে ১"
  - "pgvector-নির্ভরতা (P-C) — প্রশমন: বিদ্যমান supabase অবকাঠামো; ব্যর্থতায় বর্তমান degraded-আচরণ অক্ষত (Graceful Degradation #8)"
  - "Consolidation (P-D)-এ gateway-টেস্ট (1,001 LOC) স্পর্শ — প্রশমন: ফ্যাসাড-প্রথম, আচরণ-অপরিবর্তিত চুক্তি, ধাপে ধাপে"
  - "Rollback: প্রতিটি Phase = একক commit revert + flag-off; ডেটা-ক্ষতি-পথ নেই (pgvector যোগ, বদল নয়)"
baseline: "(hypothesis — Phase PR-এ মাপা হবে) আজ: এন্ড-টু-এন্ড প্রয়োগকৃত proposal = 0; ডিফল্ট-ডিপ্লয়ে জাগ্রত learning-চক্র = 0 (গেট false); রিস্টার্ট-পরবর্তী টিকে-থাকা ExperienceDB-র শেখা = 0 (IN-MEMORY); write-only শেখা-স্রোত = task_history (পাঠক 0); জীবিত fabricated evolution-surface = ৪"
measurement_method:
  - "(a) apply-liveness: ৩০-দিনে approve→canary→applied proposal গণনা (hard threshold: প্রথম ১টির আগে 'broken')"
  - "(b) loop-aliveness: ২৪-ঘণ্টায় learning-events→rollup→proposal উৎপন্ন কি না (ডিফল্ট-ডিপ্লয়ে)"
  - "(c) স্থায়িত্ব: রিস্টার্ট-পরবর্তী semantic-cache hit-rate বনাম আজকের 0"
  - "(d) truth-গণনা: জীবিত fabricated surface (লক্ষ্য 0) + regression: 4,100-LOC টেস্ট-স্যুট শূন্য-ব্যর্থতা"
success_threshold: "applied proposal → ≥1 পরিমাপিত (hard: শূন্য মানে লুপ এখনো ভাঙা); loop-aliveness → প্রতিদিন >0 (hard); স্থায়িত্ব → রিস্টার্ট-পরবর্তী hit >0 (target); fabricated → 0 (hard); সব সংখ্যা measured-হওয়া পর্যন্ত hypothesis"
plan_lifecycle: "living — Crown Jewel Module Series চক্র ৫-এর প্রস্তাবিত নীলনকশা; single-plan discipline অটুট — কোনো Phase ফাউন্ডার-অনুমোদন-পূর্বে executable নয়"
---

# Crown Jewel Module Series — Module 05: Self-Evolution & Learning Loop Power-Up

**Status:** proposed (ফাউন্ডার রিভিউ অপেক্ষমাণ — Gate 2 পূর্বে executable নয়)
**Owner:** Evolution Circle (`backend/core/learning/` + `backend/core/self_evolution/` + `backend/evolution/` + `backend/adaptive_engine/` + `backend/learning/` + `backend/api/routes/evolution.py`)
**Main anchor:** fresh main `9aca8d0` (2026-09-17)
**Resource delta:** 0 নতুন dependency / 0 নতুন infra (pgvector বিদ্যমান supabase-এ) / 0 নতুন CI cost / 0 schema migration / 0 route deletion

## বাংলা সারসংক্ষেপ

এই মডিউলটি SupremeAI-র ব্র্যান্ড-প্রতিশ্রুতির আসন — "Universal **Self-Learning** AI Agent"। এবং এখানেই সবচেয়ে সূক্ষ্ম বিরোধাভাস: **প্ল্যাটফর্ম প্রতিদিন শেখে, কিন্তু কখনো বদলায় না**। সংগ্রহ-স্তর অবিশ্বাস্যরকম সৎ ও স্থায়ী: প্রতিটি LLM-কল `track_llm_call` → LearningStore → Postgres `learning_events`-এ জমে (ব্যবহারকারী-ফিডব্যাক, cache-hit, 429-retry সহ)। কিন্তু লুপের বাকি অঙ্গগুলো বিভিন্ন দশায় অচল: **aggregate জন্মেই বন্ধ** (`ENABLE_LEARNING_LOOP` default false — .env.example-এ এন্ট্রিই নেই), **apply অস্তিত্বহীন** — `update_improvement_proposal_status`-এর production caller শূন্য, approve-endpoint ভিন্ন স্টোর ঘুরিয়ে শেষে করে মন্তব্য "এখানে ভবিষ্যতে... GitOps ট্রিগার কল হবে", **স্মৃতি ক্ষণস্থায়ী** — default ডিপ্লয়ে ExperienceDatabase প্রতি কলে IN-MEMORY (রিস্টার্টে সব শেখা গায়েব), **একটি শেখা-স্রোত write-only** (task_history-র পাঠক শূন্য)। তার উপর evolution-পণ্যের নিজস্ব ৪টি মিথ্যা-সাজ: swarm-blueprint "আপাতত সাকসেস", simulated swarm-graph, `gain × 1.15`-এর জাদু-সংখ্যা, আর apply-বিহীন approve। ফলাফল: Constitution #11 "Memory Must Compound" আজ কেবল *সংরক্ষণে* সত্য — *আচরণে* নয়; ২৪,৬০৯ লাইনের সাম্রাজ্যের মাত্র ~২৫% জাগ্রত, ~17-18K লাইন দুর্গ-বন্দি (env-gated) বা অনাথ।

এই নীলনকশা লুপটিকে প্রথমবার *সম্পূর্ণ* করে ৭ ধাপে: **(A)** সুরক্ষিত ডিফল্ট-উল্টো → **(B)** HITL apply-path (canary-সহ) → **(C)** স্থায়ী স্মৃতি (pgvector) → **(D)** এক লুপ-এক ফিটনেস-এক স্টোর → **(E)** false-assurance purge → **(F)** skill-forge ফিডব্যাক-ট্যাগিং → **(G)** মৃত-উপাদান সিদ্ধান্ত। শিল্পের শিক্ষা (self-improving systems-এর established pattern): নিরাপদ self-learning-এর রহস্য অসীম স্বাধীনতা নয় — *সংকুচিত ভোকাবুলারি + মানুষ-অনুমোদিত canary + পরিমাপযোগ্য রোলব্যাক*। আর SupremeAI-র সৌভাগ্য: লুপের সব অঙ্গ-প্রত্যঙ্গ ইতিমধ্যেই শরীরে আছে — শুধু শেষ-মাইলের স্নায়ুটা কাটা।

---

## Part 1 — Competitor Intelligence (established patterns; fresh-dated citations পরবর্তী চক্রে সংগ্রহ হবে — এ চক্রে design-pattern observation হিসেবে labeled)

### ৫.১ নিরাপদ self-improvement — সংকুচিত ভোকাবুলারি মতবাদ

- উন্নত self-improving ব্যবস্থায় স্বয়ংক্রিয় পরিবর্তনের জায়গা সীমিত ভোকাবুলারিতে বাঁধা (কনফিগ-মান, policy-ওয়েট) — কার্যকোড নয় (established pattern)।
- SupremeAI-র সংযোগবিন্দু: improvement_proposals স্কিমা ইতিমধ্যে পরিমাপ-ভিত্তিক — apply-executor-কে কেবল retry-policy/fallback-reorder ভোকাবুলারিতে বাঁধতে হবে (P-B)।

### ৫.২ canary-প্রথম প্রয়োগ — ছোট ঝুঁকি, বড় শেখা

- পরিণত সিস্টেমে প্রস্তাব প্রথমে canary-জনসংখ্যায়, পরিমাপ-তুলনার পরে পূর্ণ-প্রয়োগ (established pattern)।
- SupremeAI-র সংযোগবিন্দু: `evolution/CanaryManager` (132 লাইন) ও benchmark/fitness/artifact_integrity forge-পথে লাইভ — apply-path এই বিদ্যমান পাইপলাইন ধার করবে (P-B)।

### ৫.৩ অভিজ্ঞতা-ভেক্টর স্থায়িত্ব — রিস্টার্ট-পরও শেখা

- শেখা-সিস্টেমের সোনালি নিয়ম: experience স্থায়ী ভেক্টর-স্টোরে — নইল প্রতি রিস্টার্টে নবজাতক (established pattern)।
- SupremeAI-র সংযোগবিন্দু: `supabase_vector_backend.py` (pgvector) লেখা, কিন্তু `_store.py` ডিফল্টে IN-MEMORY — সংযোগটাই পুরো পার্থক্য (P-C)।

### ৫.৪ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল (fresh main 9aca8d0-verified)

| প্যাটার্ন | যা করে | SupremeAI আজ (9aca8d0-verified) | গ্যাপ |
|---|---|---|---|
| সংকুচিত ভোকাবুলারি | সীমিত স্বয়ংক্রিয় পরিবর্তন | proposal-স্কিমা আছে, apply অস্তিত্বহীন | P-B |
| canary-প্রথম | পরিমাপ-তুলনা-প্রয়োগ | CanaryManager লাইভ (forge-পথে), apply-path বিচ্ছিন্ন | P-B |
| স্থায়ী experience | রিস্টার্ট-পরও শেখা | pgvector লেখা, ডিফল্ট IN-MEMORY | P-C |
| বন্ধ-লুপ পরিমাপ | আচরণ-পরিবর্তন প্রমাণ | সংগ্রহ স্থায়ী, আচরণ-পরিবর্তন শূন্য | P-A+B+F |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main 9aca8d0, 2026-09-17)

| বিদ্যমান | বিষয় | এই নীলনকশার সাথে সম্পর্ক |
|---|---|---|
| `MODULE_01_MEMORY_POWER_UP_2026-09-17.md` | মেমোরি-একীকরণ (ERR-F02) | সম্পূরক — Module 01 write-স্তর গড়লে এই মডিউলের P-C পাঠ-স্তরে pgvector শেয়ার করবে; ভিন্ন পরিসর (মেমোরি বনাম শেখা-লুপ) |
| `MODULE_03_LLM_GATEWAY_POWER_UP_2026-09-17.md` | Gateway সত্য-উপাত্ত | সম্পূরক — P-A-র exploration ও P-B-র fallback-reorder gateway-চেইনে বসে; gateway-র P-A (streaming telemetry) শেখা-উপাত্ত সম্পূর্ণ করে |
| PLAN_006 (mem0-style consolidation) | write-time consolidation | ভিন্ন স্তর — PLAN_006 মেমোরি-লেখা নিয়ে; এই মডিউল আচরণ-শেখা নিয়ে; `MemoryConsolidator` (247 লাইন, dormant) PLAN_006-এর ভবিষ্যৎ প্রার্থী |
| `docs/plans/features/SUPREMEAI_REAL_INTELLIGENCE_EVOLUTION_PLAN.md` | ১০-ধাপ লুপ-সংজ্ঞা | এই নীলনকশা তার বাস্তবায়ন-স্তরের শেষ-মাইল — সংজ্ঞা নয়, জোড়া |
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` §7.1 + resource_registry | tools/learning fakes + NotImplemented | এই নীলনকশার P-E/P-G সরাসরি নিরাময় — alignment |
| `docs/plans/UNIFIED_NEXT_ROADMAP_2026-09-15.md` M3 | মেমোরি-কনসোলিডেশন মাইলস্টোন | সম্পূরক — M3 মেমোরি-পক্ষ; এই মডিউল learning-loop-পক্ষ; একই Constitution #11-এর দুই অর্ধ |

**গ্রেপ-যাচাই:** fresh main 9aca8d0-এ কোনো বিদ্যমান ডকুমেন্ট proposal-apply-path, learning-loop ডিফল্ট-জাগরণ, ExperienceDB pgvector-মাইগ্রেশন বা evolution false-assurance purge-এর execution-নীলনকশা দেয় না — সম্পূর্ণ unclaimed (`docs/plans/` recursive grep, 2026-09-17)।

---

## Part 2 — Six-Field Complete Plan

### ২.১ কী আছে (কোড-যাচাইকৃত)

1. **স্থায়ী সংগ্রহ-স্পাইন:** `telemetry.py` track_llm_call → LearningStore (bounded deque, batch flush) → Postgres `learning_events` — সর্বদা-জাগ্রত, কখনো throw করে না।
2. **FitnessEngine:** `self_evolution/fitness_engine.py` (299 লাইন) — প্রতি সাফল্যে completion.py:362-374 থেকে ফিড; shared singleton।
3. **Skill-forge পাইপলাইন:** AutoSkillCreator (587 লাইন) — LLM→AST→Docker-sandbox→skills/dynamic; canary+benchmark+fitness+artifact_integrity সহ লাইভ (`/api/v1/evolution/forge`)।
4. **Aggregate-কাঠামো:** LearningLoopAgent (rollup, fitness snapshot, error_hash≥3 → improvement_proposals INSERT) — কোড সম্পূর্ণ, গেট false।
5. **Exploration-বীজ:** provider_scorer + gateway চেইন-লেজে ১ candidate (completion.py:158-181) — কোড+টেস্ট সম্পূর্ণ, গেট OFF।
6. **Proposal দুই-স্টোর:** improvement_proposals (supabase) + CodeProposal (SQLAlchemy) — approve-endpoint লাইভ।
7. **Adaptive-পরিবার:** ExperienceDatabase (602 লাইন — semantic_cache-এর ভিত্তি), CapabilityRegistry, knowledge-routes-সংযুক্ত LearningLoop।
8. **টেস্ট-সম্পদ:** ~4,100 LOC — store-চুক্তি, exploration-অর্ধবৃত্তি, governed closed-loop টেস্ট বিদ্যমান (irony: টেস্ট আছে, প্রোডাকশন-পথ অকার্যকর)।

### ২.২ কী নেই (কোড-যাচাইকৃত অনুপস্থিতি)

1. **Apply-executor** — proposal-এর কোনো প্রয়োগ-পথ নেই; approve ভিন্ন স্টোরে হারায়; "PROMOTED" কেউ লেখে না।
2. **ডিফল্ট-জাগরণ** — aggregate+exploration গেট false; .env.example-এ দৃশ্যমানতাই নেই।
3. **স্থায়ী অভিজ্ঞতা** — ডিফল্ট IN-MEMORY; pgvector অব্যবহৃত।
4. **পাঠক-সহ শেখা** — task_history write-only; DailyLearner-আউটপুট অপভোজিত; unified_learning _persist pass-stub।
5. **সত্য-পণ্য** — ৪টি fabricated surface (forge-success, simulated-graph, ×1.15, approve-without-apply) + §7.1-র tools/learning fakes।
6. **সংযুক্ত প্রতিফলন** — EvolutionReActAgent/digital_twin/adversarial (~4.9K লাইন) অনাথ; প্রতিফলন-ধাপ প্রোডাকশনে নেই।

### ২.৩ কী করতে হবে (লুপ-সম্পূর্ণকরণের ৭ ধাপ)

```text
P-A: সুরক্ষিত ডিফল্ট-উল্টো   → ENABLE_LEARNING_LOOP=true (+.env.example দৃশ্যমানতা) +
                              exploration গেট sample-tier guardrail-সহ খোলা
P-B: HITL apply-path        → proposal→approve→canary→bounded-apply (retry-policy/
                              fallback-reorder ভোকাবুলারি) → PROMOTED+পরিমাপ
P-C: স্থায়ী স্মৃতি          → ExperienceDatabase → supabase_vector_backend (pgvector)
P-D: এক-লুপ-এক-ফিটনেস       → unified_learning+৪ wrapper retirement; proposal-স্টোর
                              একত্রীকরণ; এক fitness-সত্য
P-E: False-assurance purge  → forge/simulated/×1.15/approve-without-apply/§7.1 fakes
P-F: Forge ফিডব্যাক-ট্যাগিং  → track_llm_call-এ skill_id → skill_metrics বাস্তব উপাত্ত
P-G: মৃত-উপাদান সিদ্ধান্ত    → 4.9K-লাইন অনাথ subpackage: wire-অথবা-retire register-দর্শনে
```

### ২.৪ কীভাবে করব (ফাইল-স্তরের দিক-নির্দেশ, প্রতিটি Phase আলাদা execution প্ল্যান)

- **P-A:** `core/startup/agents.py:209` ডিফল্ট অপরিবর্তিত রেখে .env.example-এ `ENABLE_LEARNING_LOOP=true` + নথি; exploration গেট `get_adaptive_routing_enabled` সুইটেবল-ডিফল্ট true (sample-tier-এ কেবল); kill-switch অক্ষত; flag-off → আজকের আচরণ।
- **P-B (AGENTS.md Section 3 মান্যতা: এভিডেন্স-গেটেড গভর্নড অটোনমি ও ক্যানারি পাইপলাইন):**
  - **Self-Evolution Pipeline:** `Observation → Hypothesis → Risk Classification → Isolated GitHub Experiment → Automated Tests → Benchmark Comparison → Canary Rollout → Telemetry Check → Promote/Rollback`।
  - **রিস্ক-টায়ার্ড অটোনমি:**
    - *Low-risk (ডকুমেন্টেশন, টেস্ট অপ্টিমাইজেশন, মেমোরি বেঞ্চমার্ক):* পলিসি অনুযায়ী সম্পূর্ণ স্বয়ংক্রিয় এভিডেন্স গেট পাস হলে প্রমোশন।
    - *Medium/High-risk (রাউটিং নীতি, আর্কিটেকচার, সিকিউরিটি):* কঠোর এভিডেন্স ও বেঞ্চমার্ক কম্প্যারিজন ছাড়া কোনো চেঞ্জ প্রমোট হবে না; রোলব্যাক ট্রেইল সর্বদা সংরক্ষিত থাকবে।
  - নতুন পাতলা apply-executor (JSON-patch ভোকাবুলারি: retry-policy/fallback-reorder); CanaryManager-এ পাইপ; সাফল্যে `update_improvement_proposal_status(id,'PROMOTED')` + FitnessEngine পূর্ব/পর পরিমাপ; ব্যর্থতায় ROLLED_BACK।
- **P-C:** `_store.py`-র degradation-শাখায় pgvector-ব্যাকএন্ড প্রাথমিক, sqlite-ফাইল গৌণ, IN-MEMORY শেষ (Graceful Degradation ক্রম উল্টানো); বিদ্যমান স্কিমা অপরিবর্তিত; রিস্টার্ট-পরবর্তী cache-hit টেস্ট। **দর্শন-সংগতি সংশোধন (এই পাস):** (১) **রেকনসিলিয়েশন-বাধ্যতা** — `_store.py`-র নিজস্ব docstring "SQLite-only-by-design store" (P0 Task 9-c2) স্পষ্ট ডিজাইন-সিদ্ধান্ত; pgvector-প্রাথমিকতা সেই সিদ্ধান্তকে উল্টায়, তাই P-C-র execution-প্লানে Gate 0-তে এই দ্বন্দ্ব সুনির্দিষ্টভাবে উল্লেখ ও নিষ্পত্তি বাধ্যতামূলক (নীরব-উল্টোদিক নয়); (২) **flag-gated, default আজকের আচরণ** — পার্সিস্টেন্স-মোড env-পঠিত (pgvector|sqlite|memory), কোডে কোনো স্থির পছন্দ নয় (zero-hardcode); (৩) **হট-পথ latency-রক্ষা** — লেখা write-behind/ব্যাচড (বিদ্যমান bounded-deque + batch-flush প্যাটার্ন), পাঠ বাউন্ডেড — ব্যবহারকারী-দৃশ্যমান বিলম্ব শূন্য-লক্ষ্য (fast-smooth)।
- **P-D:** `unified_learning.py` + ৪ deprecated wrapper deprecation-warning → callers বিদ্যমান লুপে → অপসারণ সবশেষে; CodeProposal/improvement_proposals একত্রীকরণ-নীলনকশা (পাঠ-মাইগ্রেশন); এক fitness-সত্য (FitnessEngine canonical)।
- **P-E:** প্রতিটি surface-এ দুই-সমাপ্তির একটি: বাস্তব (forge persist বা 501; swarm-graph CapabilityRegistry-থেকে লাইভ; ×1.15 মুছে পরিমাপ-ভিত্তিক; approve→P-B-পথ) অথবা honest-error; §7.1 fakes-এর জায়গায় fitness_snapshots থেকে পরিমিত মান বা documented deferral।
- **P-F:** `track_llm_call`-এ `skill_id` kwargs — forge-generated skill-পথে সেট; LearningLoopAgent skill_metrics (loop.py:213 fallback বদলে বাস্তব); forge-ফল → FitnessEngine auto-feed।
- **P-G:** প্রতিটি অনাথ subpackage-এর (digital_twin/adversarial/ewc/neural_symbolic/federated/ReAct) wire-অথবা-retire সিদ্ধান্ত-টেবিল ফাউন্ডারের জন্য; retire হলে deprecation→measured→removal; wire হলে আলাদা execution প্ল্যান (এখানে নয়)।

### ২.৫ বেনিফিট (সবই hypothesis — Gate 5-এ measured হবে)

1. **ব্র্যান্ড-প্রতিশ্রুতি সত্য:** "Self-Learning" প্রথমবার এন্ড-টু-এন্ড প্রমাণযোগ্য — proposal→পরিমাপকৃত আচরণ-পরিবর্তন; Constitution #11 আচরণে সত্য।
2. **এভিডেন্স-গেটেড অটোনমি (P-B):** কোনো অন্ধ সেলফ-মডিফিকেশন নয়; প্রতিটি পরিবর্তন টেস্ট, বেঞ্চমার্ক এবং ক্যানারি এভিডেন্স দ্বারা সুরক্ষিত।
3. **পরিমাপ-বিহীন → পরিমাপকৃত:** লুপ-জাগরণে প্রতিদিন রোলআপ+প্রস্তাব — ফাউন্ডার দেখবেন "সিস্টেম কী শিখল" (হিউম্যান-রিডেবল প্রস্তাব-স্ট্রিম)।
4. **স্থায়িত্ব-লাভ (P-C):** রিস্টার্ট-পরও semantic-cache ও অভিজ্ঞতা টিকবে — খরচ-সাশ্রয় ও ধারাবাহিক মান (hypothesis: cache-hit-rate উল্লেখযোগ্য বৃদ্ধি)।
5. **নিরাপত্তা-মডেল প্রমাণ:** সংকুচিত ভোকাবুলারি+canary = বিশ্বকে দেখানোর মতো নিরাপদ self-improvement-গল্প — বিক্রয়-বিন্দু।
5. **আস্থা (P-E):** evolution-পণ্যের মিথ্যা শূন্য — L3-দর্শনের সমাপ্তি।
6. **রক্ষণ-হ্রাস (P-D/G):** ~5.6K+ লাইন মৃত/ডুপ্লিকেট-লুপের সিদ্ধান্ত-স্পষ্টতা।

### ২.৬ ক্ষতি/ঝুঁকি (সৎ, প্রশমন সহ)

1. **ভুল স্বয়ংক্রিয় পরিবর্তন:** apply-executor ভুল হলে মান-অবনতি — প্রশমন: ভোকাবুলারি-সীমা, ২-ধাপ অনুমোদন, canary পরিমাপ, এক-কমান্ড রোলব্যাক, kill-switch।
2. **গেট-অনে লেখা-বিস্ফোরণ:** learning-events বৃদ্ধি — প্রশমন: bounded deque+batch (বিদ্যমান), retention-workflow বিদ্যমান।
3. **pgvector-নির্ভরতা (P-C):** supabase-দুর্বলতায় পাঠ-ব্যর্থতা — প্রশমন: ৩-স্তর degradation-ক্রম, আচরণ-অপরিবর্তিত fallback।
4. **Consolidation-স্পর্শ (P-D):** 1,001-LOC gateway-টেস্ট — প্রশমন: ফ্যাসাড-প্রথম, আচরণ-চুক্তি অটুট, ধাপে-ধাপে।
5. **পরিসর-ঝুঁকি:** "self-learning" নামে বড় AI-ফিচার-লোভ — প্রশমন: এই নীলনকশায় কোনো নতুন AI-ক্ষমতা নয়; কেবল বিদ্যমান লুপ-জোড়া; প্রতিটি Phase আলাদা Gate 0–6।

---

## Part 3 — Explicit Out-of-Scope

1. নতুন AI-প্রযুক্তি (RL/RLHF-বাস্তবায়ন, neural training) — অনাথ subpackage-গুলোর wire-সিদ্ধান্ত আলাদা প্ল্যানের প্রার্থী।
2. স্বয়ংক্রিয় কার্যকোড-প্যাচ/ডিপ্লয় (GitOps) — ভোকাবুলারি-সীমা অতিক্রম করবে না।
3. মেমোরি write-স্তর পরিবর্তন — Module 01/PLAN_006-র পরিসর।
4. EvolutionForge UI রিডিজাইন — কেবল সৎ-উত্তর চুক্তি প্রয়োজনে।
5. resource_registry restart/deploy/rollback বাস্তবায়ন — register-নথিভুক্ত আলাদা প্ল্যান-প্রার্থী।
6. সমান্তরাল multi-plan execution — একসময়ে একটাই Phase active।

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | প্রতিটি Phase আলাদা proposed execution; একসময়ে একটাই active |
| 2. Small change to existing code | ✅ | apply-executor পাতলা নতুন-ফাইল; বাকি সব বিদ্যমান ফাইলে পরিবর্তন |
| 3. No new infrastructure | ✅ | pgvector বিদ্যমান supabase-এ; কোনো নতুন service/DB নয় |
| 4. No CI cost amplification | ✅ | টেস্ট বিদ্যমান স্যুটে; নতুন শাখা নয় |
| 5. No credit-burn risk | ✅ | exploration = চেইন-লেজে ১ candidate; forge-ফিডব্যাক বিদ্যমান কলে |
| 6. No academic leaderboard | ✅ | সরাসরি প্রোডাক্ট-ক্ষমতা: apply-liveness, স্থায়িত্ব, truth-গণনা |
| 7. Realistic resource budget | ✅ | bounded deque+batch flush বিদ্যমান; canary-জনসংখ্যা ছোট |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main 9aca8d0 sed/grep/wc-যাচাই (last_verified-তালিকা); register-উৎস স্পষ্ট |

| Constitution ধারা | প্রভাব |
|---|---|
| #5 Verify Before Trust | ✅ canary-পরিমাপ প্রয়োগ-পূর্বে; ৪ মিথ্যা-surface পর্যুগ |
| #6 Policy Before Power | ✅ apply কেবল অনুমোদন+ভোকাবুলারি-সীমার পরে |
| #8 Graceful Degradation | ✅ pgvector→sqlite→IN-MEMORY ক্রম; গেট kill-switch |
| #11 Memory Must Compound | ✅ এই নীলনকশারই মূল-লক্ষ্য: আচরণে যৌগিকীকরণ |
| #13 No Silent Failure | ✅ write-only স্রোত-পাঠকযুক্ত; approve-বিহীন-apply শূন্য |
| #14 Zero-Mock Doctrine | ✅ ×1.15/simulated/fake-success — সব zero-mock লক্ষ্যে |

---

## Part 5 — Verification & Acceptance (Gates 4–6) + Rollback

- **Gate 4 (প্রতি Phase):** বিদ্যমান ~4,100-LOC টেস্ট শূন্য-ব্যর্থতা; P-A গেট-অন টেস্ট (run_cycle প্রস্তাব-তৈরি); P-B apply-integration টেস্ট (approve→canary→PROMOTED+রোলব্যাক-পথ); P-C রিস্টার্ট-স্থায়িত্ব টেস্ট; P-D store-চুক্তি টেস্ট অটুট।
- **Gate 5 (live):** প্রথম বাস্তব proposal-প্রয়োগ পর্যবেক্ষণ (পরিমাপ-পূর্ব/পর প্রকাশিত); ২৪-ঘণ্টায় লুপ-জাগরণ প্রমাণ; রিস্টার্ট-পরবর্তী cache-hit; fabricated শূন্য।
- **Gate 6:** প্রতিটি Phase নিজস্ব execution প্ল্যানে complete; এই নীলনকশা complete যখন acceptance_criteria-র পাঁচটি সংজ্ঞা সবই evidence-সহ সত্য।
- **Rollback:** প্রতিটি Phase = একক commit revert + flag-off; apply-রোলব্যাক = এক-কমান্ড (রাষ্ট্র-পুনরুদ্ধার ভোকাবুলারির অংশ); pgvector-যোগ ডেটা-ক্ষতি-পথ নয়।

---

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Pass, 2026-09-17, branch `crown-jewel-v2`)

| দর্শন | রায় | ভিত্তি |
|---|---|---|
| Zero cost | ✅ সংগত | pgvector বিদ্যমান supabase-এ (নতুন infra/dependency নয়); HITL canary + bounded apply — কোনো পরিশোধিত পরিষেবা নয় |
| Lightweight | ✅ সংগত (P-C সংশোধিত) | 0 নতুন dependency; লুপ-অঙ্গ ইতিমধ্যেই শরীরে — সংযোগ-কাজ; P-C-তে বিদ্যমান batch-flush প্যাটার্নের পুনঃব্যবহার বাধ্যতামূলক করা হলো |
| Fast & smooth | ⚠️ ছিল → ✅ **সংশোধিত** | P-C আগে pgvector-প্রাথমিক লেখা-পাঠ সরাসরি প্রস্তাব করত — হট-পথে network round-trip; এখন write-behind + bounded-read + default-অপরিবর্তিত (§২.৪ সংশোধিত) |
| Zero hardcode | ⚠️ ছিল → ✅ **সংশোধিত** | persistence-মোড env-পঠিত (pgvector\|sqlite\|memory) — কোড-কনস্ট্যান্ট নয়; এবং `advanced_evolution_engine.py` L44-র `gain × 1.15` ম্যাজিক-সংখ্যা (false-assurance purge P-E তালিকাভুক্ত) সংশোধন-পথে measured-মানই থাকবে — নতুন কোনো ম্যাজিক-গুণক নয় |

মূল-যন্ত্রপাতি spot-check (base `ed35eaf`): `supabase_vector_backend.py` বিদ্যমান (adaptive_engine/); `ENABLE_LEARNING_LOOP` default false (`core/startup/agents.py` L209); `_store.py` degraded-mode docstring অটুট + **"SQLite-only-by-design" (P0 Task 9-c2) আবিষ্কৃত** — P-C-র Gate-0-রেকনসিলিয়েশন-বাধ্যতা সংযোজনের কারণ।

স্কোপ-সততা: proposal-দর্শন অডিট + মূল-যন্ত্রপাতি spot-check; সম্পূর্ণ line-ref re-verification নয়।

---

## Part 6 — পরবর্তী চক্র লাইনেজ (reference-only; candidate list ≠ execution queue)

- **চক্র ১–৪ (প্রকাশিত):** Module 01 Memory → Module 02 Orchestration → Module 03 LLM Gateway → Module 04 Browser।
- **চক্র ৬ (কিউতে):** Module 06 — Run Fabric সম্পূর্ণকরণ (`backend/runs/` + `backend/missions/` + `backend/runtime/`) — সর্বজনীন execution-observability চুক্তি; এই মডিউলের শেখা-উপাত্ত run-anchored হলে P-F-এর skill_id-মতবাদ run_id-মতবাদে পূর্ণ হবে।
- সূচি ও কিউ-পুনঃর‍্যাঙ্ক: `crown_jewel_series/README.md`।
