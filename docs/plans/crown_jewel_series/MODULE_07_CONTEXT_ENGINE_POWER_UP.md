---
id: crown-jewel-module-07-context-engine-power-up-v1-2026-09-17
title: "Crown Jewel Module Series — Module 07: Context Engine Power-Up (উষ্ণ-পথের token-বাজেট-চুক্তিকে এক, মাপা ও সৎ করা — '≥30% হ্রাস' দাবিকে প্রথমবার পরিমাপযোগ্য করার পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Context Circle (backend/context_engine/ + backend/context/ + backend/api/routes/chat.py-assembly-অংশ + backend/core/memory/auto_rag_injector.py-সংযোগ-বিন্দু)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ৭ — একটি মডিউল (Context Engine), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — fresh main 4de7794 (2026-09-17) sed/grep/wc-যাচাইকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; Module 01/03 ও PLAN_002/004/006-র সাথে স্পষ্ট সীমানা (read-side মাত্র); প্রতিটি ধাপে flag+kill-switch; 721-route surface-এ zero-regression লক্ষ্য"
depends_on:
  - "backend/context_engine/engine.py (ContextEngine.assemble, 228 লাইন — LIVE: chat.py:223,381 grep-verified; Section/ContextBlock/BudgetReport/AssembledContext)"
  - "backend/context_engine/budget.py (60 লাইন — estimate_tokens Bengali/CJK-aware 1.3x L55-59 sed-verified; DEFAULT_INPUT_BUDGET=3000; SECTION_CAPS)"
  - "backend/context/ (727 লাইন দ্বিতীয় ইঞ্জিন — scopes/provenance/tenant-deny L203-211, dedup L236-252, L0/L1/L2 SummaryLevel, scoring 0.7·base+0.3·scope L216 — production import শূন্য, DORMANT)"
  - "backend/api/routes/chat.py (L120-233 assembly-পাইপলাইন: cache→USER→LTM MEMORY→recall KNOWLEDGE→governance→assemble; L225-228 BudgetReport কেবল logger.info)"
  - "backend/api/routes/stream_chat_sse.py (L45,203 auto_rag_injector — স্ট্রিমিং-পথে বাজেট-বিহীন আলাদা enrichment, sed-verified)"
  - "backend/core/llm/token_budget.py (L80-88 — কেবল CJK-aware 2.0; Bengali-factor নেই — split-estimator, sed-verified)"
  - "backend/core/memory/auto_rag_injector.py (200 লাইন)"
  - "PLAN_002 (_compact_history — websocket_agent.py:449, wired :581,:612 — COMPLETE; এই নীলনকশার HISTORY-উৎস)"
  - "docs/plans/UNIFIED_NEXT_ROADMAP_2026-09-15.md (M2 'one context assembly path' exit-criterion :172)"
  - "docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md ERR-F03 (FIXED 2026-09-17 — যাচাইকৃত)"
  - "tests/context_engine/ + tests/context/ (৩৮ টেস্ট — determinism, hard-reserve, best-fit, Bengali-factor, tenant-filter পিনকৃত)"
implements:
  - "পরিমাপ-ভিত্তি — BudgetReport.as_detail স্থায়ী + before/after baseline: '≥30% token-হ্রাস' দাবি প্রথমবার honest"
  - "এক assembly-পথ — M2 exit-criterion: dormant দ্বিতীয় ইঞ্জিনের চুক্তি canonical-এ, দ্বৈততা শেষ"
  - "স্ট্রিমিং-সমতা — বৃহত্তম serving-পৃষ্ঠ auto_rag_injector থেকে engine-এ: বাজেট-বহির্ভূত শেষ পথ বন্ধ"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (fresh main 4de7794: chat.py L223,381 grep-verified assemble; engine.py L190 'break # one system block is the contract' sed-verified; budget.py L55-59 sed-verified 1.3x; token_budget.py L80-88 sed-verified CJK-only; stream_chat_sse.py L45,203 sed-verified auto_rag; backend/context/ wc=727 + import-grep শূন্য)"
code_evidence:
  - "backend/api/routes/chat.py L225-228 — BudgetReport কেবল logger.info — as_detail()-এর consumer শূন্য; কোনো baseline/কাউন্টার/হার্নেস নেই → সিরিজ-README-র '≥30% token-হ্রাস (target)' দাবি আজ অপরিমাপযোগ্য"
  - "backend/context_engine/engine.py L190 — `break  # one system block is the contract` — দ্বিতীয়+ SYSTEM block চুপচাপ বাদ; report.dropped-এও নয় (silent-drop); L165 truncation-gate `used == 0` — multi-user-block overflow ক্ষেত্রে অচল"
  - "backend/context/ — 727-লাইন সম্পূর্ণ চুক্তি (tenant-deny filter, provenance, dedup, L0/L1/L2, scope-scoring) — production import শূন্য → UNIFIED_NEXT_ROADMAP M2 exit 'one context assembly path' ভাঙা"
  - "HISTORY-সেকশন মৃত — কোনো caller history-block তৈরি করে না (ChatPayload = prompt+model_name); PLAN_002-র _compact_history আউটপুট websocket-agent-পথে আটকে"
  - "backend/api/routes/stream_chat_sse.py L45,203 — স্ট্রিমিং-পথ auto_rag_injector ব্যবহার করে — বাজেট/SECTION_CAPS/রিপোর্ট-বহির্ভূত তৃতীয় enrichment-পৃষ্ঠ"
  - "split-estimator — engine-এর Bengali-aware 1.3x (budget.py:55-59) বনাম token_budget-র Bengali-blind CJK-only (token_budget.py:80-88) — M2-B ও gateway can_fit অন্ধ estimator ব্যবহার করে → বাংলা-ভারী প্রম্পটে হিসাব-ভুল"
  - "কোনো config নেই — caps/budget hardcoded (DEFAULT_INPUT_BUDGET=3000); settings-knob/kill-switch/per-tenant budget অনুপস্থিত"
  - "coverage — gateway-serving ~১৩ route-এর মাত্র ২টি (chat.py-র ২ কল-সাইট) engine ব্যবহার করে"
test_evidence: "none yet — প্রতিটি Phase-এর execution প্রল্যান সংজ্ঞায়িত করবে; সমষ্টিগত চুক্তি: (১) determinism-চুক্তি অটুট (৩৮ টেস্ট পিনকৃত), (২) baseline-হার্নেস টেস্ট (একই কর্পাসে before/after পুনঃগণনাযোগ্য), (৩) বিদ্যমান tests/api/test_api_chat.py:76-108 recall-mock চুক্তি অটুট, (৪) flag-off → আজকের আচরণ byte-সমতুল্য; prompt-shape চুক্তি (user bare-tail, engine.py:50-52) অক্ষত"
acceptance_criteria:
  - "প্রতিটি Phase আলাদা ছোট execution প্ল্যান হিসেবে Gate 0–6 পাস"
  - "পরিমাপ-সংজ্ঞা: প্রতি অনুরোধে BudgetReport-detail স্থায়ী + tokens-per-task baseline-তুলনা প্রকাশিত — '≥30%' হয় measured, নয় অপসারিত"
  - "এক-পথ সংজ্ঞা: gateway-serving প্রতিটি enrichment (chat-দুই + streaming) এক engine-চুক্তিতে; backend/context/ হয় canonical-এ পোর্টেড, নয় স্পষ্ট-retired"
  - "সততা-সংজ্ঞা: silent system-drop রিপোর্টে; overflow-ক্ষেত্রে truncation; split-estimator শেষ"
  - "721-route zero-regression CI প্রমাণ; prompt-shape চুক্তি (cache-compat) অটুট"
test_evidence_note: "Gate 4-এ হার্নেস-পুনঃগণনা ও চুক্তি-টেস্ট; Gate 5-এ live — প্রতি-অনুরোধ budget-report প্রবাহ ও baseline-তুলনা পর্যবেক্ষণ; completion claim-এর আগে বাধ্যতামূলক"
risk_and_rollback:
  - "সবচেয়ে বড় ঝুঁকি: উষ্ণ-পথে (chat/streaming) prompt-shape পরিবর্তন → cache-miss ও মান-ওঠানামা — প্রশমন: user-bare-tail চুক্তি অটুট; streaming-সংযোগ flag-এর পিছনে shadow-তুলনা-পর্ব"
  - "estimator-একত্রীকরণে হিসাব-স্থানান্তর (P-E): কিছু বাজেট-সিদ্ধান্ত বদলাবে — প্রশমন: বাংলা-ভারী কর্পাসে পরিমাপ-প্রথম; প্রভাবিত টেস্ট সমসাময়িক আপডেট"
  - "M2-B-পোর্টে ব্যবহারকারী-র‍্যাঙ্কিং পরিবর্তন (P-B) — প্রশমন: আগে shadow-তুলনা (পুরনো বনাম নতুন আউটপুট diff-রিপোর্ট), parity ≥threshold-এ কাটওভার"
  - "রিপোর্ট-স্থায়িত্বে লেখা-বৃদ্ধি (P-A) — প্রশমন: কেবল সংক্ষিপ্ত detail-row, বিদ্যমান retention পুনঃব্যবহার"
  - "Rollback: প্রতিটি Phase = একক commit revert + flag-off; কোনো schema migration নেই"
baseline: "(hypothesis — Phase PR-এ মাপা হবে) আজ: engine-কভারড serving-route = 2/13; স্থায়ী budget-report = 0; পরিমাপিত হ্রাস-শতাংশ = অজানা (দাবি ≥30% unmeasured); HISTORY-block = 0; জীবিত estimator = ২টি (একটি Bengali-blind); silent-drop প্রতিদিন ঘটে (অপরিমিত)"
measurement_method:
  - "(a) coverage: engine-ব্যবহারকৃত serving-route গণনা (লক্ষ্য 13/13 অথবা নথিভুক্ত ব্যতিক্রম)"
  - "(b) হ্রাস: baseline-কর্পাসে tokens-per-task before/after — '≥30%' হয় measured-সত্য/সমন্বিত-দাবি"
  - "(c) সততা: silent-drop ঘটনা রিপোর্টে-উপস্থিতি (লক্ষ্য: dropped-সর্বদা-সত্য)"
  - "(d) regression: ৩৮ context-টেস্ট + api-chat চুক্তি-টেস্ট শূন্য-ব্যর্থতা; prompt-cache hit-rate অ-হ্রাস"
success_threshold: "coverage → 13/13 অথবা নথিভুক্ত (hard); হ্রাস-দাবি → measured অথবা সমন্বিত (hard: unmeasured-দাবি চলমান থাকবে না); silent-drop → 0 (hard); cache-hit অ-হ্রাস (hard); সব সংখ্যা measured-হওয়া পর্যন্ত hypothesis"
plan_lifecycle: "living — Crown Jewel Module Series চক্র ৭-এর প্রস্তাবিত নীলনকশা; single-plan discipline অটুট — কোনো Phase ফাউন্ডার-অনুমোদন-পূর্বে executable নয়"
---

# Crown Jewel Module Series — Module 07: Context Engine Power-Up

**Status:** proposed (ফাউন্ডার রিভিউ অপেক্ষমাণ — Gate 2 পূর্বে executable নয়)
**Owner:** Context Circle (`backend/context_engine/` + `backend/context/` + `chat.py`-assembly-অংশ + `auto_rag_injector.py`-সংযোগ)
**Main anchor:** fresh main `4de7794` (2026-09-17)
**Resource delta:** 0 নতুন dependency / 0 নতুন infra / 0 নতুন CI cost / 0 schema migration / 0 route deletion

## বাংলা সারসংক্ষেপ

মেমোরি-গেটওয়ে-ব্রাউজার-লুপ-রানের পরে বাকি রইল উষ্ণ-পথের **বুদ্ধিমান ছাঁকনি**: Context Engine — কোন তথ্য মডেলের সীমিত জানালায় ঢুকবে তার বাজেট-চুক্তি। এই মডিউল বয়সে সবচেয়ে কচি (M2, সদ্য-ল্যান্ডেড, ERR-F03-ফিক্সসহ লাইভ) আর গুণেও পৃথক — কোড পরিষ্কার (শূন্য TODO/FIXME/mock), টেস্ট পিনকৃত (৩৮টি)। তবু তিনটি গভীর ফাটল: **(১) পরিমাপ-শূন্যতা** — সিরিজ-README-র গর্বের দাবি "≥30% token-হ্রাস (target)" আজ *অপরিমাপযোগ্য*: `BudgetReport.as_detail()`-এর consumer শূন্য, কোনো baseline/হার্নেস/কাউন্টার নেই — প্রতিষ্ঠানের নিজস্ব quantitative-claim-শৃঙ্খলার লঙ্ঘন; **(২) দ্বৈত-ইঞ্জিন** — `backend/context/`-এ ৭২৭-লাইনের সম্পূর্ণ উন্নততর চুক্তি (tenant-deny filter, provenance, dedup, L0/L1/L2 summary-s্তর, scope-scoring) লেখা কিন্তু production-import শূন্য — রোডম্যাপের M2-exit নিজেই ("one context assembly path") ভাঙা; **(৩) আওতা-ছিদ্র** — gateway-serving ~১৩ route-এর মাত্র ২ কল-সাইট engine ব্যবহার করে, আর বৃহত্তম streaming-পৃষ্ঠ (`stream_chat_sse.py`) বাজেট-বহির্ভূত `auto_rag_injector`-এ — অর্থাৎ যে পথে বেশিরভাগ টোকেন যায়, সেখানে ছাঁকনিই নেই। সাথে ছোট-ক্ষতের ঝাঁক: HISTORY-সেকশন মৃত (PLAN_002-র compaction-আউটপুট সংযুক্তই নয়), দুই estimator-এর বিভাজন (engine Bengali-aware, gateway Bengali-blind — বাংলা-ভারী প্রম্পটে হিসাব-ভুল), `engine.py:190`-এর silent system-drop, আর শূন্য config (caps hardcoded, kill-switch নেই)।

এই নীলনকশা ছাঁকনিটিকে crown-jewel স্তম্ভে তোলে ৭ ধাপে: **(A)** পরিমাপ-হার্নেস (দাবি→প্রমাণ) → **(B)** এক assembly-পথ (M2-B চুক্তি-পোর্ট, shadow-তুলনা-সহ) → **(C)** HISTORY জাগরণ → **(D)** streaming-সংযোগ → **(E)** এক Bengali-aware estimator → **(F)** config+kill-switch+per-tenant → **(G)** সততা-সংশোধন। **সীমানা-শৃঙ্খলা:** এই মডিউল read-side মাত্র — মেমোরি write-স্তর (Module 01/PLAN_006), gateway-execution (Module 03), compaction-যন্ত্র (PLAN_002/005) — কোনোটি স্পর্শ নয়; শুধু *খরচ-সহ তথ্য-প্রবাহ* এক চুক্তিতে। শিল্প-শিক্ষা (established context-management pattern): context-engineering-এ জয় দুই জায়গায় — *কী বাদ* পরিমাপ করা, আর *সব পথে এক নিয়ম* — দুটোই আজ খালি।

---

## Part 1 — Competitor Intelligence (established patterns; fresh-dated citations পরবর্তী চক্রে সংগ্রহ হবে — এ চক্রে design-pattern observation হিসেবে labeled)

### ৭.১ বাজেট-প্রথম context নির্মাণ

- পরিণত context-ব্যবস্থায় প্রতি-সেকশন cap + হার্ড-রিজার্ভ + বাদ-পড়ার রিপোর্ট মানক — "কী ঢুকল তার চেয়ে কী বাদ পড়ল জানা বেশি দামি" (established pattern)।
- SupremeAI-র সংযোগবিন্দু: BudgetReport/dropped-কাঠামো ইতিমধ্যে আছে — কেবল স্থায়িত্ব ও প্রবাহ নেই (P-A)।

### ৭.২ এক নিয়ম, সব পৃষ্ঠ

- context-ম্যানেজমেন্ট পণ্যগুলোর মূল শৃঙ্খলা: এক assembly-পথ — নয়তো per-path ব্যতিক্রমে বাজেট-অন্ধত্ব (established pattern)।
- SupremeAI-র সংযোগবিন্দু: M2-B-র dormant চুক্তি ঠিক এই স্পেক — পোর্ট-করলেই M2-exit সত্য (P-B/D)।

### ৭.৩ বহুভাষিক টোকেন-সত্য

- বহুভাষিক প্ল্যাটফর্মে script-aware estimator মানক — Latin-কেন্দ্রিক হিসাব বাংলা/CJK-তে ব্যর্থ (established pattern)।
- SupremeAI-র সংযোগবিন্দু: engine ইতিমধ্যে Bengali-aware — শুধু gateway পাশের estimator অন্ধ; একত্রীকরণ ছোট কাজ, বড় সত্য (P-E)।

### ৭.৪ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল (fresh main 4de7794-verified)

| প্যাটার্ন | যা করে | SupremeAI আজ (4de7794-verified) | গ্যাপ |
|---|---|---|---|
| বাজেট-প্রথম | বাদ-রিপোর্ট স্থায়ী | BudgetReport কেবল log | P-A |
| এক পথ | সব route এক engine | 2/13 কল-সাইট; streaming বাইপাস | P-B+D |
| বহুভাষিক সত্য | script-aware হিসাব | দুই estimator, একটি অন্ধ | P-E |
| পরিমাপযোগ্য দাবি | baseline-তুলনা | ≥30% unmeasured | P-A |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main 4de7794, 2026-09-17)

| বিদ্যমান | বিষয় | এই নীলনকশার সাথে সম্পর্ক |
|---|---|---|
| `MODULE_01_MEMORY_POWER_UP_2026-09-17.md` / PLAN_006 | মেমোরি write-side | **সীমানা:** এই মডিউল read-side — এক canonical recall-adapter consume করবে, কোনো স্টোর স্পর্শ নয় |
| `MODULE_03_LLM_GATEWAY_POWER_UP_2026-09-17.md` | gateway execution/খরচ | **সীমানা:** gateway টোকেনের গন্তব্য-শাসন; এই মডিউল ইনপুট-আকৃতি; শেয়ারড গ্রাউন্ড = PROVIDER_TOKEN_BUDGETS (P-E) |
| PLAN_002 (compaction, COMPLETE) + PLAN_005 (/compact) | history-সংকোচন যন্ত্র | সম্পূরক — তাদের আউটপুট এই মডিউলের HISTORY-ইনপুট (P-C); পুনঃবাস্তবায়ন নয় |
| PLAN_004 (write-time distillation) | L0/L1 স্তর-উৎপাদন | সম্পূরক — M2-B-র SummaryLevel চুক্তি তাদের সাথে সারিবদ্ধ রাখা হবে |
| `docs/plans/UNIFIED_NEXT_ROADMAP_2026-09-15.md` M2 | "one context assembly path" exit | এই নীলনকশার P-B/D সরাসরি সেই exit-criterion-এর বাস্তবায়ন |
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` ERR-F03 | context-সংযোগ ফিক্স | FIXED (যাচাইকৃত) — এই নীলনকশা ফিক্সের উপরে সর্বজনীনতা গড়ে |

**গ্রেপ-যাচাই:** fresh main 4de7794-এ কোনো বিদ্যমান ডকুমেন্ট budget-report স্থায়িত্ব, M2-B-পোর্ট-সিঁড়ি, streaming-engine-সংযোগ বা এক-estimator-একত্রীকরণের execution-নীলনকশা দেয় না — সম্পূর্ণ unclaimed (`docs/plans/` recursive grep, 2026-09-17)।

---

## Part 2 — Six-Field Complete Plan

### ২.১ কী আছে (কোড-যাচাইকৃত)

1. **লাইভ canonical ইঞ্জিন:** `context_engine/engine.py` (228 লাইন) — Section/ContextBlock/BudgetReport/AssembledContext; chat.py:223,381-এ লাইভ।
2. **Bengali-aware estimator:** `budget.py:55-59` — non-ascii>30% হলে 1.3x — বহুভাষিক সত্যের বীজ।
3. **বাজেট-চুক্তি:** USER হার্ড-রিজার্ভ 50% → SYSTEM cap 25% → best-fit greedy (MEMORY 40/KNOWLEDGE 60/HISTORY 75) — নির্ধারিত ও টেস্ট-পিনকৃত।
4. **Dormant সম্পদ:** `backend/context/` (727 লাইন) — tenant-deny filter, provenance, dedup, L0/L1/L2, scope-scoring — সম্পূর্ণ টেস্টেড (১১ টেস্ট) কিন্তু অসংযুক্ত।
5. **Compaction-উৎস:** PLAN_002-র `_compact_history` লাইভ (websocket-পথে) — HISTORY-র প্রস্তুত ইনপুট।
6. **পরিষ্কার কোড-সংস্কৃতি:** দুই প্যাকেজেই শূন্য TODO/FIXME/mock।
7. **টেস্ট-সম্পদ:** ৩৮ টেস্ট/৫৯১ LOC — determinism, hard-reserve, best-fit, Bengali-factor, tenant-filter সব পিনকৃত।

### ২.২ কী নেই (কোড-যাচাইকৃত অনুপস্থিতি)

1. **পরিমাপ** — as_detail consumer শূন্য; baseline/হার্নেস/কাউন্টার নেই; ≥30% দাবি অপরিমাপযোগ্য।
2. **এক পথ** — 2/13 কল-সাইট; streaming auto_rag_injector-বাইপাস; M2-exit ভাঙা।
3. **HISTORY** — সেকশন-কাঠামো আছে, কোনো উৎস-সংযোগ নেই।
4. **এক estimator** — Bengali-blind gateway-হিসাব; split-সত্য।
5. **Config/kill-switch/per-tenant** — সব hardcoded।
6. **সততা-ক্ষুদ্র** — silent system-drop (L190); overflow-gate ত্রুটি (L165)।

### ২.৩ কী করতে হবে (ছাঁকনি-সত্যকরণের ৭ ধাপ)

```text
P-A: পরিমাপ-হার্নেস         → as_detail স্থায়ী + baseline-কর্পাস + tokens-per-task তুলনা
P-B: এক assembly-পথ         → M2-B চুক্তি canonical-এ পোর্ট (shadow-তুলনা-প্রথম)
P-C: HISTORY জাগরণ          → PLAN_002-compact আউটপুট → HISTORY-blocks (priority=recency)
P-D: Streaming-সংযোগ        → auto_rag_injector → engine-চুক্তি (flag + shadow-তুলনা)
P-E: এক estimator           → Bengali-aware হিসাব core/llm/token_budget-এ ঐক্য
P-F: Config+kill-switch     → SECTION_CAPS/budget settings-চালিত + per-tenant budget
P-G: সততা-সংশোধন            → L190 silent-drop → report; L165 overflow-gate সংশোধন;
                              relevance-v1 (recall-similarity → priority)
```

### ২.৪ কীভাবে করব (ফাইল-স্তরের দিক-নির্দেশ, প্রতিটি Phase আলাদা execution প্ল্যান)

- **P-A:** chat.py-র দুই কল-সাইটে report-detail স্থায়ী-লেখা (সংক্ষিপ্ত row: dropped/truncated/tokens — **স্থায়ী-ভলিউম বিদ্যমান retention-চক্রে বাউন্ডেড রাখা বাধ্যতামূলক, নতুন অবাউন্ডেড টেবিল নয়**); একক baseline-কর্পাস-স্ক্রিপ্ট (টেস্ট-নির্ধারিত) — before/after পুনঃগণনাযোগ্য; "≥30%" দাবি হয় measured, নয় README-সমন্বিত।
- **P-B:** `backend/context/`-র tenant-filter/provenance/dedup/scope-scoring canonical engine-এ পোর্ট (চুক্তি অপরিবর্তিত); shadow-পর্বে পুরনো-বনাম-নতুন আউটপুট diff-রিপোর্ট; parity-গেটে কাটওভার; `backend/context/` হয় খালি-শেল-রিডাইরেক্ট, নয় স্পষ্ট-retired-নথি।
- **P-C:** chat-পথে PLAN_002-র compact-আউটপুট (websocket_agent-থেকে সরাসরি নয় — একই compaction-ফাংশন শেয়ার) → HISTORY-blocks, priority=recency (টেস্টে বিদ্যমান সমর্থন)।
- **P-D:** `stream_chat_sse`-এর enrichment engine-চুক্তিতে (auto_rag_injector হয় একটি source-adapter হয়ে যাবে); flag `SUPREMEAI_CONTEXT_UNIFIED_STREAM=true` (default false); shadow-তুলনা-পর্ব বাধ্যতামূলক (বৃহত্তম পৃষ্ঠ)।
- **P-E:** `token_budget.estimate_tokens`-এ Bengali-factor (engine-র যুক্তি সরানো); engine এটি import করবে; প্রভাবিত can_fit/budget-টেস্ট আপডেট; বাংলা-কর্পাসে হিসাব-তুলনা নথি।
- **P-F (Config, kill-switch ও Gateway ডাইনামিক উইন্ডো কাপলিং):**
  - SECTION_CAPS/DEFAULT_INPUT_BUDGET settings-চালিত; kill-switch `SUPREMEAI_CONTEXT_ENGINE=off` → আজকের raw-prompt আচরণ।
  - **মডেল-সচেতন ডাইনামিক উইন্ডো:** Module 03 Gateway-র ভেন্ডর-সত্য রেজিস্ট্রি থেকে টার্গেট মডেলের কনটেক্সট লিমিট (যেমন Groq 8k বনাম Claude/Flash 1M) স্বয়ংক্রিয়ভাবে পড়ে প্রম্পট প্যাকিং অ্যাডাপ্ট করা (আউট-অব-বাউন্ডস ট্রাঙ্কেশন রোধ)।
  - **ক্যাশ-সচেতন প্রিফিক্স স্টেবিলিটি (Prompt Cache-Aware Packing):** সিস্টেম প্রম্পট ও টুল ডেফিনিশনগুলোকে সবসময় প্রম্পটের শুরুতে স্ট্যাটিক ও অপরিবর্তিত রাখা, যাতে Anthropic/OpenAI প্রম্পট ক্যাশিং ৫০-৯০% ইনপুট টোকেন কস্ট কমায়।
- **P-G:** L190-এ বাদ-পড়া SYSTEM-block report.dropped-এ (চুপচাপ নয়); L165 truncation-gate সংশোধন (multi-user-block); relevance-v1: recall_memories-র similarity-স্কোর → block-priority (নতুন মডেল নয়)।

### ২.৫ বেনিফিট (সবই hypothesis — Gate 5-এ measured হবে)

1. **দাবি→প্রমাণ:** "≥30% token-হ্রাস" প্রথমবার measured — বিক্রয়/নথি/বিশ্বাস তিনটিতেই সত্য; না হলে দাবি সমন্বিত (সংস্কৃতি-লাভ তবু)।
2. **প্রম্পট ক্যাশিং সাশ্রয় (P-F):** প্রিফিক্স-স্ট্যাবল প্যাকিংয়ের ফলে Anthropic/OpenAI ক্যাশ হিট বেড়ে ইনপুট খরচ ৫০-৯০% কমে।
3. **মডেল কনটেক্সট মিসম্যাচ শূন্য (P-F):** ছোট উইন্ডোর মডেলে বড় প্রম্পট পাঠিয়ে 400 ContextLengthExceededError ক্র্যাশ স্থায়ীভাবে বন্ধ।
4. **খরচ-সাশ্রয় প্রসার:** streaming (বৃহত্তম পৃষ্ঠ) engine-এ ঢুকলে হ্রাস-সুবিধা পুরো ট্রাফিকে (hypothesis: বর্তমান 2/13 → 13/13)।
5. **বাংলা-সত্য (P-E):** বাংলা-ভারী প্রম্পটে বাজেট-হিসাব সঠিক — ভুল-অনুমানে ট্রাঙ্কেশন-দুর্ঘটনা হ্রাস।
6. **নিরাপদ বিকাশ-ভিত্তি (P-F):** kill-switch+config = পরীক্ষা-সাহস; per-tenant = ভবিষ্যৎ বাণিজ্যিক-স্তরের পূর্বশর্ত।
5. **M2-exit সত্য (P-B/D):** রোডম্যাপ-প্রতিশ্রুতি পূরণ; dormant 727-লাইন সম্পদ অবশেষে কাজে।
6. **সততা-সংস্কৃতি (P-G):** বাদ-পড়া কখনো অদৃশ্য নয় — ডিবাগিং-সময় হ্রাস।

### ২.৬ ক্ষতি/ঝুঁকি (সৎ, প্রশমন সহ)

1. **prompt-shape পরিবর্তনে cache-miss/মান-ওঠানামা:** বিশেষত P-B/D — প্রশমন: user-bare-tail চুক্তি অটুট, shadow-তুলনা-পর্ব, parity-গেট, flag default false।
2. **estimator-একত্রীকরণে হিসাব-স্থানান্তর (P-E):** কিছু সিদ্ধান্ত বদলাবে — প্রশমন: পরিমাপ-প্রথম, প্রভাবিত-টেস্ট সমসাময়িক, নথিভুক্ত তুলনা।
3. **রিপোর্ট-লেখা-বৃদ্ধি (P-A):** প্রতি-অনুরোধ row — প্রশমন: সংক্ষিপ্ত row + বিদ্যমান retention।
4. **নতুন-পুরনো দ্বৈততার পুনরাবৃত্তি (P-B):** পোর্ট অসম্পূর্ণ রইলে — প্রশমন: দুই-সমাপ্তির জোর (পোর্ট অথবা retire), M2-exit-যাচাই-টেস্ট।
5. **পরিসর-ঝুঁকি:** "context" নামে নতুন AI-ফিচার-লোভ (semantic-routing ইত্যাদি) — প্রশমন: read-side সীমানা-দর্শন; প্রতিটি Phase আলাদা Gate 0–6।

---

## Part 3 — Explicit Out-of-Scope

1. মেমোরি store/write-স্তর পরিবর্তন — Module 01/PLAN_006-র পরিসর (read-side adapter মাত্র)।
2. Gateway-পথ/খরচ-প্রয়োগ পরিবর্তন — Module 03-র পরিসর (estimator-শেয়ার মাত্র)।
3. Compaction-যন্ত্র পুনঃবাস্তবায়ন — PLAN_002/005-এর মালিকানা (উৎস-consumption মাত্র)।
4. Semantic-routing/re-ranking মডেল আমদানি — relevance-v1 বিদ্যমান স্কোর-পুনঃব্যবহারেই সীমাবদ্ধ।
5. Frontend context-UI — পরিসরে নেই।
6. সমান্তরাল multi-plan execution — একসময়ে একটাই Phase active।

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | প্রতিটি Phase আলাদা proposed execution; একসময়ে একটাই active |
| 2. Small change to existing code | ✅ | পোর্ট+মোড়ক+settings; নতুন কোড কেবল হার্নেস/টেস্টে |
| 3. No new infrastructure | ✅ | লেখা-স্থায়িত্ব বিদ্যমান DB/retention-এ |
| 4. No CI cost amplification | ✅ | হার্নেস-কর্পাস টেস্ট-নির্ধারিত; নতুন শাখা নয় |
| 5. No credit-burn risk | ✅ | কোনো নতুন LLM-কল নেই; relevance বিদ্যমান স্কোর-পুনঃব্যবহার |
| 6. No academic leaderboard | ✅ | coverage, measured-হ্রাস, silent-drop-গণনা — সরাসরি প্রোডাক্ট-মান |
| 7. Realistic resource budget | ✅ | সংক্ষিপ্ত report-row; কোনো নতুন স্থায়ী-ভলিউম-নীতি নয় |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main 4de7794 sed/grep/wc-যাচাই (last_verified-তালিকা); সীমানা-পাঠ (M01/M03/PLAN_002/004/006) |

| Constitution ধারা | প্রভাব |
|---|---|
| #5 Verify Before Trust | ✅ ≥30% দাবি → measured অথবা সমন্বিত — unmeasured-দাবি বন্ধ |
| #6 Policy Before Power | ✅ বাজেট-চুক্তি সব enrichment-পৃষ্ঠে; per-tenant policy |
| #8 Graceful Degradation | ✅ kill-switch → raw-prompt আচরণ; estimator-fallback |
| #10 One System, Many Execution Surfaces | ✅ এক assembly-পথ — ১৩ route + streaming |
| #13 No Silent Failure | ✅ silent-drop → রিপোর্ট; overflow-gate সংশোধন |
| #14 Zero-Mock Doctrine | ✅ পরিমাপ-শূন্য দাবি-সংস্কৃতির বিরুদ্ধে হার্নেস |

---

## Part 5 — Verification & Acceptance (Gates 4–6) + Rollback

- **Gate 4 (প্রতি Phase):** ৩৮ context-টেস্ট + api-chat চুক্তি-টেস্ট শূন্য-ব্যর্থতা; P-A হার্নেস-পুনঃগণনা-টেস্ট; P-B shadow-diff-রিপোর্ট ও parity-গেট; P-C HISTORY-সংযোগ টেস্ট; P-D streaming-shadow টেস্ট; P-E বাংলা-কর্পাস হিসাব-টেস্ট।
- **Gate 5 (live):** প্রতি-অনুরোধ budget-report প্রবাহ; baseline-তুলনায় হ্রাস-শতাংশ প্রকাশিত (অথবা দাবি-সমন্বিত); cache-hit-rate অ-হ্রাস; silent-drop শূন্য।
- **Gate 6:** প্রতিটি Phase নিজস্ব execution প্ল্যানে complete; এই নীলনকশা complete যখন acceptance_criteria-র পাঁচটি সংজ্ঞা সবই evidence-সহ সত্য।
- **Rollback:** প্রতিটি Phase = একক commit revert + flag-off; কোনো schema migration নেই; P-B/D-র কাটওভার-পূর্বে shadow-পর্ব সর্বদা রিভার্ট-নিরাপদ।

---

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Pass, 2026-09-17, branch `crown-jewel-v2`)

| দর্শন | রায় | ভিত্তি |
|---|---|---|
| Zero cost | ✅ সংগত (P-A সংশোধিত) | পরিমাপ-হার্নেস টেস্ট-নির্ধারিত; report-লেখা retention-বাউন্ডেড (§২.৪ সংশোধিত — নতুন অবাউন্ডেড টেবিল নয়) |
| Lightweight | ✅ সংগত | এক estimator-এ ঐক্য = ডুপ্লিকেট-যুক্তি অপসারণ; নতুন dependency শূন্য |
| Fast & smooth | ✅ সংগত | flag default false; shadow-তুলনা local-compute (LLM-কল নয়); kill-switch → আজকের আচরণ |
| Zero hardcode | ✅ সংগত | P-F SECTION_CAPS/budget settings-চালিতই এই নীলনকশার মূল-দাবি; P-E হার্ডকোডেড estimator-বিভেদ মুছে একটি Bengali-aware ফাংশনে ঐক্য |

মূল-যন্ত্রপাতি spot-check (base `ed35eaf`): `backend/context_engine/` (engine.py, budget.py) বিদ্যমান; `token_budget.estimate_tokens` L73 বিদ্যমান; SECTION_CAPS engine-এ বিদ্যমান।

স্কোপ-সততা: proposal-দর্শন অডিট + মূল-যন্ত্রপাতি spot-check; সম্পূর্ণ line-ref re-verification নয়।

---

## Part 6 — পরবর্তী চক্র লাইনেজ (reference-only; candidate list ≠ execution queue)

- **চক্র ১–৬ (প্রকাশিত):** Module 01 Memory → 02 Orchestration → 03 LLM Gateway → 04 Browser → 05 Self-Evolution → 06 Run Fabric।
- **চক্র ৮ (কিউতে):** Module 08 — Scout / Deep Research (`backend/scout/`) — সদ্য প্রোডাকশন-wired গবেষণা-চক্র; এই মডিউলের বাজেট-চুক্তি গবেষণা-প্রম্পটেও (সবচেয়ে বড় context-ভোক্তাদের একটি) প্রবাহিত হবে।
- সূচি ও কিউ-পুনঃর‍্যাঙ্ক: `crown_jewel_series/README.md`।
