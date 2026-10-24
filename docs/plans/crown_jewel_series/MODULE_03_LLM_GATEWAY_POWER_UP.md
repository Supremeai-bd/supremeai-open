---
id: crown-jewel-module-03-llm-gateway-power-up-v1-2026-09-17
title: "Crown Jewel Module Series — Module 03: LLM Gateway & Model Routing Power-Up (Inference-Spine-কে সৎ, পরিমাপযোগ্য ও এক-দরজার খরচ-সীমান্ত করা — প্ল্যাটফর্মের প্রতিটি টোকেনের নিয়ন্ত্রণকেন্দ্রকে সবচেয়ে শক্তিশালী করার পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Gateway Circle (backend/core/llm/ — llm_gateway/ + providers/ + telemetry.py + free_tier_tracker.py + backend/brain/model_router.py + backend/services/llm/ + backend/api/routes/admin_llm.py)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ৩ — একটি মডিউল (LLM Gateway & Model Routing), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — fresh main 6ef6550 (2026-09-17) sed/grep/wc-যাচাইকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; প্রতিটি ধাপে flag+kill-switch; 721-route surface-এ zero-regression লক্ষ্য"
depends_on:
  - "backend/core/llm/llm_gateway/completion.py (CompletionMixin.acompletion — THE main entry, 561 লাইন, wc-verified: cache → CostGuard → Tier-0 → optimizer → chain-loop → telemetry)"
  - backend/core/llm/llm_gateway/streaming.py (StreamingMixin._stream_completion, 115 লাইন — track_llm_call/langfuse/cost grep-count = 0, wc-verified)
  - backend/core/llm/llm_gateway/registry.py (_MODEL_KEY_MAP 14 providers, _ProviderKeyPool rotation+cooldown, _RETIRED_MODELS L46-50 sed-verified)
  - backend/core/llm/llm_gateway/routing.py (RoutingMixin._build_call_chain + set_runtime_override — admin override বাস্তব, admin_llm.py-যাচাইকৃত)
  - backend/core/llm/llm_gateway/gateway.py (_router property L79-85 — ডিফল্ট unittest.mock.MagicMock sed-verified)
  - backend/core/llm/providers/cloud_adapter.py (CloudProviderAdapter → litellm.acompletion — বাস্তব provider HTTP boundary + PLAN-001 Anthropic cache_control)
  - backend/core/llm/telemetry.py (track_llm_call — অস্ট্রিম-পথে লাইভ; LearningStore durable sink + token calibration EMA)
  - backend/core/llm/free_tier_tracker.py (457 লাইন — RPM/TPM/RPD বাজেট, brain/model_router.py-এ পরামর্শকৃত)
  - backend/core/llm/provider_router.py (117 লাইন, LatencyAwareWeightedRouter — record_result/set_readiness-এর কোনো production caller নেই, grep-verified; তবু admin_llm.py এর stats পড়ে)
  - backend/brain/model_router.py (416 লাইন ফ্যাসাড — ~30 importer; route_and_stream fallback L405-406 স্থায়ী "Hello"/" World" yield sed-verified)
  - "backend/brain/model_registry.py (fabricated মডেল-নাম: claude-opus-4.7/gpt-5.5/gemini-3.5-flash/grok-4.3/glm-5/kimi-k2.6 — L17-176 sed-verified)"
  - backend/services/llm/llm_router.py (956 লাইন — দ্বিতীয় জীবিত স্ট্যাক, 10+ agent/tool caller; providers.py 708 লাইন হাতে-লেখা provider)
  - backend/config/routing_policy.json (প্রতিটি complexity-chain-এর head-এ retired gemini-2.0-flash/gemini-1.5-pro — grep-verified)
  - backend/core/competitive_kit.py L1353-1360 (_call_llm ফেব্রিকেটেড "[Response from ...]" রিটার্ন — sed-verified, defect register §7.2)
  - backend/api/routes/chat.py L233 (tenant_id ছাড়া acompletion — CostGuard bypass, sed-verified)
  - backend/api/routes/admin_llm.py (বাস্তব admin override POST + মৃত provider_router stats পাঠ)
  - docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md (§7.2 fake MultiLLMRouter, trap #16 runaway-cost, trap #17 tool-call, trap #19 fallback-semantic-mismatch)
  - frontend/src/components/dashboard/LlmGatewayPage.tsx (219 লাইন, /llm-gateway route — বাস্তব /api/admin/llm/* wired)
implements:
  - Streaming-পথে পর্যবেক্ষণযোগ্যতা-সমতা — streaming.py-এ track_llm_call + খরচ-গণনা যোগ করা (আজ 0 উল্লেখ — ব্যবহারকারী-দৃশ্যমান প্রধান ট্রাফিক অদৃশ্য)
  - Gateway-স্তরের খরচ-নীতি — প্রতিটি serving route থেকে tenant_id প্রচার + TokenDeductor/CostGuard প্রয়োগ (trap #16 কাঠামোগত নিরাময়)
  - "Constitution #11 \"Memory Must Compound\"-এর inference-স্পর্শ: প্রতিটি (স্ট্রিমিং-সহ) LLM-কল telemetry → LearningStore → routing-শেখায় প্রবাহিত"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (fresh main 6ef6550: streaming.py wc 115 + grep track_llm_call|langfuse|cost = 0; completion.py L111 'if tenant_id' sed-verified; chat.py L233 tenant_id-হীন acompletion sed-verified; model_registry.py fabricated নাম L17-176 sed-verified; routing_policy.json retired-head grep-verified; provider_router.py wc 117 + caller grep = self+test; competitive_kit.py L1353-1360 sed-verified; model_router.py L405-406 'Hello'/' World' sed-verified; gateway.py MagicMock-default L79-85 sed-verified)"
code_evidence:
  - "backend/core/llm/llm_gateway/streaming.py — 115 লাইন; grep -c \"track_llm_call|langfuse|cost\" = 0 — স্ট্রিমিং পথ telemetry/খরচের অন্ধ-ছিদ্র (কনট্রাস্ট: completion.py-এ দুটোই আছে)"
  - backend/core/llm/llm_gateway/completion.py L111 — `if tenant_id:` — CostGuard কেবল tenant_id পাস হলে; chat.py:233, task_workspace.py:73, reasoning.py:77 ইত্যাদি ১৩ route কোনোটাই tenant_id পাস করে না → প্রধান পথে বাজেট-গার্ড bypassed
  - backend/core/llm/token_deductor.py (292 লাইন, Redis+ledger) — gateway কখনো ডাকে না; কেবল billing_api + ৩ agent — খরচ-হিসাব স্পাইনের বাইরে দ্বীপে বন্দি
  - backend/brain/model_registry.py L17-176 — "claude-opus-4.7", "gpt-5.5", "gemini-3.5-flash", "grok-4.3", "glm-5", "kimi-k2.6" — অস্তিত্বহীন মডেল; performance_enhancer.py `_resolve_registry_model` (L257) alias-স্তর দিয়ে সেরামতো ঠিক করে — মিথ্যা উপাত্তের উপর প্যাচ
  - backend/config/routing_policy.json L5-26 — প্রতিটি complexity-chain ও fallback-এর head-এ `gemini/gemini-2.0-flash` / `gemini/gemini-1.5-pro`, যা registry.py _RETIRED_MODELS (L46-50) — রানটাইমে স্কিপ; head-অবস্থান কার্যত মৃত config; `task_overrides` কী-টি RoutingMixin কখনো পড়ে না (settings.task_models পড়ে)
  - backend/core/llm/provider_router.py — 117 লাইন; record_result/set_readiness-এর production caller শূন্য (grep-verified) → admin_llm.py:61 stats সবসময় unavailable/0ms দেখায়; সিদ্ধান্ত-পথে স্বাস্থ্য-উপাত্ত হার্ডকোডেড (advanced_model_router.py:381, performance_aware_router.py:22)
  - backend/core/competitive_kit.py L1353-1360 — `_call_llm` = asyncio.sleep(0.1) → "[Response from {provider}/{model}] Processed your N char prompt." — ফেব্রিকেটেড উত্তর (defect register §7.2, এখনো unfixed)
  - backend/core/llm/llm_gateway/gateway.py L79-85 — `_router` property ডিফল্টে `unittest.mock.MagicMock()` বানায় — প্রোডাকশন কোডে টেস্ট-ডাবল ডিফল্ট
  - backend/brain/model_router.py L405-406 — route_and_stream fallback `yield "Hello"` / `yield " World"` — ব্যর্থতায় ব্যবহারকারীকে মিথ্যা সান্ত্বনা (Constitution #13 লঙ্ঘন)
  - backend/core/llm/providers/cloud_adapter.py L94 — litellm.acompletion বাস্তব HTTP boundary + Anthropic cache_control — স্পাইনের সবচেয়ে সৎ স্তর; একীকরণের ভিত্তি
  - backend/services/llm/llm_router.py — 956 লাইন দ্বিতীয় জীবিত স্ট্যাক (নিজস্ব 7 provider, নিজস্ব cache/budget) + providers.py 708 লাইন হাতে-লেখা httpx ক্লায়েন্ট — litellm-এর ডুপ্লিকেট; 10+ বাস্তব caller
  - backend/api/routes/admin_llm.py L132 — runtime override POST বাস্তব (routing.py set_runtime_override-এ লেখে) — admin-ক্ষমতা প্রমাণিত; কেবল পাঠ-স্তর (stats) মৃত উপাত্তে
test_evidence: "none yet — প্রতিটি Phase-এর execution প্ল্যান সংজ্ঞায়িত করবে; সমষ্টিগত চুক্তি: (১) streaming-vs-nonstream telemetry-parity টেস্ট (একই প্রম্পট, দুই পথ, সমান খরচ-পার্থক্য 0%), (২) tenant-প্রচার integration টেস্ট (chat.py→gateway→CostGuard পর্যবেক্ষণ), (৩) বিদ্যমান 17 টেস্ট-ফাইল (~3,111 LOC: test_llm_gateway_completion.py 1,001, test_llm_router.py 355, test_model_router_unit.py 150, test_llm_gateway_consolidation.py 247) zero regression, (৪) flag-off → byte-সমতুল্য আজকের আচরণ; register §12-র 22 skipped টেস্ট consolidation-এ প্রথম লাভ"
acceptance_criteria:
  - "প্রতিটি Phase আলাদা ছোট execution প্ল্যান হিসেবে Gate 0–6 পাস"
  - "InferenceContext চুক্তি: একক ক্যানোনিকাল কনটেক্সট (tenant_id, user_id, request_id, run_id, task_type, budget_scope, source) প্রধান ১৩ serving route-এ বাধ্যতামূলক"
  - "Zero-Bypass চুক্তি: 'No LLM call may bypass the inference accounting boundary' — সিআই স্ট্যাটিক অ্যানালাইসিস গেট পাস"
  - "Streaming-সমতা সংজ্ঞা: stream=True কলও একই একাউন্টিং সোর্স থেকে track_llm_call + Langfuse + খরচ-এন্ট্রি উৎপন্ন করে এবং discrepancy নির্ধারিত সহনশীলতার (tolerance) মধ্যে থাকে"
  - "বাজেট-নীতি সংজ্ঞা: Pre-call BudgetReservation লিজ + Post-call UsageSettlement প্রয়োগ; Bounded Fail-Open ম্যাট্রিক্স (আউটেজে low-cost অনুমোদিত, expensive ব্লকড) — রেস-কন্ডিশন ও runaway-cost শূন্য"
  - "সত্য-উপাত্ত সংজ্ঞা: model_registry-তে শূন্য fabricated মডেল-নাম; routing_policy.json-এ শূন্য retired-head; ফেক-সাকসেস শূন্য (স্ট্রাকচার্ড এরর দ্বারা প্রতিস্থাপিত); admin UI provider-stats বাস্তব পরিমাপ-ভিত্তিক"
  - "721-route surface-এ zero regression — প্রতিটি Phase-এর PR-এ CI প্রমাণ; নতুন dependency শূন্য; কোনো route মুছে না যায়"
test_evidence_note: "Gate 4-এ parity, concurrency budget reservation (100 simultaneous calls), এবং failure matrix টেস্ট; Gate 5-এ live — বাস্তব স্ট্রিম-কলের খরচ ও unattributed_cost = 0 পর্যবেক্ষণ; completion claim-এর আগে বাধ্যতামূলক"
risk_and_rollback:
  - "সবচেয়ে বড় ঝুঁকি: প্রধান serving-path-এ খরচ-চেক যোগ → latency/ব্যবহার-ভাঙা — প্রশমন: Bounded Fail-Open নীতি (রেডিস বা বাজেট আউটেজে Groq/Gemini Flash-এর মতো লো-কস্ট মডেল Allow, কিন্তু দামি মডেল Blocked; অজ্ঞাত টেন্যান্ট Rejected), flag-off = আজকের নিরাপদ আচরণ"
  - "কনকারেন্সি ঝুঁকি: একযোগে একাধিক কল একই ব্যালেন্স দেখে ওভার-স্পেন্ড করা — প্রশমন: BudgetReservation লিজ (Atomic Redis lease with TTL) + Post-call UsageSettlement"
  - "Fabricated registry অপসারণে নির্ভরশীল কোড ভাঙা (_resolve_registry_model alias-স্তর) — প্রশমন: প্রথমে vendor-true metadata ঢোকানো, alias-স্তর deprecation-পর্ব, অপসারণ শেষ ধাপ; test_model_registry_readiness.py আপডেট"
  - "Consolidation (P-G)-এ 10+ llm_router caller-ভাঙা — প্রশমন: ফ্যাসাড-প্রথম (llm_router/ModelRouter অপরিবর্তিত সিগনেচার, ভেতরে gateway-ডেলিগেশন), caller-মাইগ্রেশন পরিমিত; register §12-র 22 skipped টেস্ট প্রথম লাভ"
  - "Streaming-এ telemetry যোগে per-chunk ওভারহেড — প্রশমন: telemetry কেবল final chunk-এ (usage-সহ), প্রতি-চাংক নয়; বিদ্যমান http_client disconnect-aware relay অটুট"
  - "Rollback: প্রতিটি Phase = একক commit revert + flag; কোনো schema migration নেই; competitive_kit purge-এ কেবল ডিলিট-অথবা-ওয়্যার দুই সমাপ্তি"
baseline: "(hypothesis — Phase PR-এ মাপা হবে) আজ: স্ট্রিমিং-ট্রাফিকের কত শতাংশ খরচ-হিসাবে অদৃশ্য — অপরিমিত (০ উল্লেখ দেখে ১০০%-এর কাছে hypothesis); tenant_id-প্রচারকৃত serving-route = 0/13; fabricated registry-entry = 6+; retired-head chain = 4/4 complexity-rule; admin UI-তে বাস্তব latency দেখানো provider = 0"
measurement_method:
  - "(a) streaming-parity: একই প্রম্পট stream বনাম non-stream — উভয়ে track_llm_call row উৎপন্ন করে কি না, খরচ-ব্যবধান সহনশীলতার মধ্যে কি না"
  - "(b) budget-coverage: InferenceContext-প্রচারকৃত serving-route গণনা (লক্ষ্য 13/13) + BudgetReservation লিজ কল-হার"
  - "(c) truth-পরিমাপ: registry-তে fabricated-entry গণনা (লক্ষ্য 0), retired-head chain গণনা (লক্ষ্য 0), unattributed_cost গণনা (লক্ষ্য 0), fake_success গণনা (লক্ষ্য 0)"
  - "(d) regression: CI-তে backend sharded tests + 17 gateway/router টেস্ট-ফাইল শূন্য-ব্যর্থতা; route-graph meta-tests পাস; zero-bypass gate পাস"
success_threshold: "streaming parity → tolerance within 1% (hard); budget coverage → 13/13 serving-route (target); unattributed_cost → 0 (hard); fake_success_responses → 0 (hard); budget_race_violations → 0 (hard); fabricated entries → 0 (hard); retired-head → 0 (hard); parity/regression → শূন্য-ব্যর্থতা (hard); সব সংখ্যা measured-হওয়া পর্যন্ত hypothesis"
plan_lifecycle: "living — Crown Jewel Module Series চক্র ৩-এর প্রস্তাবিত নীলনকশা; single-plan discipline অটুট — কোনো Phase ফাউন্ডার-অনুমোদন-পূর্বে executable নয়"
---

# Crown Jewel Module Series — Module 03: LLM Gateway & Model Routing Power-Up

**Status:** proposed (ফাউন্ডার রিভিউ অপেক্ষমাণ — Gate 2 পূর্বে executable নয়)
**Owner:** Gateway Circle (`backend/core/llm/` + `backend/services/llm/` + `backend/brain/model_router.py` + `backend/api/routes/admin_llm.py`)
**Main anchor:** fresh main `6ef6550` (2026-09-17)
**Resource delta:** 0 নতুন dependency / 0 নতুন infra / 0 নতুন CI cost / 0 schema migration / 0 route deletion

## বাংলা সারসংক্ষেপ

মেমোরি (Module 01) স্মৃতি হলে, orchestration (Module 02) মেরুদণ্ড হলে — **LLM Gateway হলো হৃৎপিণ্ড ও রক্তসংবহন**: প্ল্যাটফর্মে যত টোকেন ঢোকে-বেরোয়, প্রতিটি অণু এই স্পাইনের কাছ দিয়ে যায়, আর এখানেই ঠিক হয় প্ল্যাটফর্মের তিনটি সবচেয়ে বড় সত্য — *খরচ*, *গতি*, এবং *ভরসাযোগ্যতা*। সুখবর: `backend/core/llm/llm_gateway/` প্যাকেজটি বাস্তবেই প্রতিযোগী-মানের হৃৎপিণ্ড — 14-provider litellm বাউন্ডারি (`registry.py` + `cloud_adapter.py`), কী-পুল rotation+cooldown, 429 Retry-After resilience (`resilience.py`), Tier-0 zero-token bypass, semantic cache, আর বাস্তব admin runtime-override (`admin_llm.py` L132 → `routing.py`)। দুঃখবর: হৃৎপিণ্ডের তিনটি ধমনী কাটা: **(১) অদৃশ্য রক্তপ্রবাহ** — স্ট্রিমিং-পথ (`streaming.py`, 115 লাইন) একটিও telemetry/খরচ-উল্লেখ রাখে না (grep=0) — অথচ সেটাই ব্যবহারকারী-দৃশ্যমান প্রধান পথ; **(২) ছিদ্রময় খরচ-বাঁধ** — `completion.py` L111-এ `if tenant_id:` — আর প্রধান ১৩ serving-route কেউই tenant_id পাস করে না, `TokenDeductor` (292 লাইনের Redis+ledger) gateway কখনোই ডাকে না — runaway-cost trap #16 কাঠামোগতভাবে খোলা; **(৩) মিথ্যা উপাত্তের স্টেথোস্কোপ** — `model_registry.py`-তে "claude-opus-4.7", "gpt-5.5"-এর মতো অস্তিত্বহীন মডেল, `routing_policy.json`-এর প্রতিটি chain-এর head-এ retired মডেল, admin UI দেখায় মৃত provider_router-এর কাল্পনিক stats, আর `competitive_kit.py` L1353 "[Response from ...]"-জাত ফেব্রিকেটেড উত্তর — Constitution #5 "Verify Before Trust" ও #13 "No Silent Failure" এখানেই পরীক্ষায়। এর উপরে দ্বিতীয় জীবিত হৃৎপিণ্ড: `services/llm/llm_router.py` (956 লাইন, নিজস্ব provider/cache/budget, 10+ বাস্তব caller) — একই রক্ত দুই হৃৎপিণ্ডে।

এই নীলনকশা স্পাইনকে crown-jewel স্তম্ভে তোলে ৭ ধাপে: **(A)** streaming observability-সমতা → **(B)** tenant-প্রচার + gateway-বাজেট → **(C)** vendor-true model registry → **(D)** routing_policy পুনর্জন্ম → **(E)** প্রাণ ফেরানো provider-health → **(F)** false-assurance purge → **(G)** এক-গেটওয়ে একীকরণ (ফ্যাসাড, ফর্ক নয়)। প্রতিযোগীরা প্রমাণ করেছে জয় এখানেই: LiteLLM-এর unifed provider interface, OpenRouter-এর per-request খরচ-অ্যাট্রিবিউশন, Portkey-এর gateway-গ্রেড resilience+observability — আর SupremeAI-র সৌভাগ্য: এই তিনটির মূল প্রিমিটিভ ইতিমধ্যেই কোডে আছে; কাজটি বেশিরভাগ *সত্য-পুনঃসংযোগ* — নতুন হৃৎপিণ্ড বসানো নয়, কাটা ধমনী জোড়া।

---

## Part 1 — Competitor Intelligence (established patterns; fresh-dated citations পরবর্তী চক্রে সংগ্রহ হবে — এ চক্রে design-pattern observation হিসেবে labeled)

### ৩.১ LiteLLM — unifed provider interface (এবং SupremeAI-র বিদ্যমান সুবিধা)

- LiteLLM-এর মূল শক্তি: একটি `completion(model, messages)` চুক্তিতে ১০০+ provider — auth/retry/streaming-ভিন্নতা পুঁজিভূমি-স্তরে গুঁজে যায় (established vendor pattern)।
- SupremeAI-র সংযোগবিন্দু: স্পাইনের নিচতলায় বাস্তবেই litellm আছে — `backend/core/llm/providers/cloud_adapter.py` L94 (`litellm.acompletion`) ও `litellm_runtime.py`। অর্থাৎ এই লেয়ার কেনার প্রশ্নই নেই — খালি জায়গা হলো তার উপরের সত্য-উপাত্ত (registry/policy/health) সৎ করা। মজা: `services/llm/providers.py`-এর 708 লাইন হাতে-লেখা httpx ক্লায়েন্ট ঠিক এই লেয়ারের ডুপ্লিকেট — retirement-প্রার্থী।

### ৩.২ OpenRouter — রাউটিং + প্রতি-অনুরোধ খরচ-অ্যাট্রিবিউশন

- OpenRouter প্রতিটি অনুরোধে কোন মডেল, কত টোকেন, কত খরচ — সব অ্যাট্রিবিউট করে (established vendor pattern)।
- SupremeAI-র সংযোগবিন্দু: `telemetry.py` `track_llm_call` অস্ট্রিম-পথে এই মতবাদ পালন করে (LearningStore durable sink) — খালি জায়গা স্ট্রিমিং-সমতা (P-A) ও tenant-অ্যাট্রিবিউশন (P-B)। খরচ-মানচিত্র আজ ৯টি হাতে-টাইপ ধ্রুবক (`PROVIDER_COST_MAP`) — vendor-true pricing প্রয়োজন (P-C)।

### ৩.৩ Portkey — gateway-গ্রেড resilience ও observability

- Portkey-র মূল শক্তি: retries, fallbacks, load-balancing, semantic caching, guardrails — সব config-ভিত্তিক, প্রতিটি কলে পূর্ণ ট্রেস (established vendor pattern)।
- SupremeAI-র সংযোগবিন্দু: fallback-chain, semantic cache, breaker সব *কোডে* আছে (`completion.py` chain-loop, `semantic_cache.py`, resilience manager); খালি জায়গা — সিদ্ধান্ত-উপাত্ত সৎ না হওয়া (হার্ডকোডেড `PROVIDER_HEALTH_DEFAULT`, মৃত `provider_router`) ও নীতি hardcode থাকা (flat 12s timeout — reasoning মডেলের জন্য অপর্যাপ্ত; retry-policy config-হীন)। P-D/E/G এর নিরাময়।

### ৩.৪ Helicone / gateway-observability মতবাদ — প্রতি-কল জবাবদিহি

- Gateway-observability পণ্যগুলোর মূল শিক্ষা: যে কল মাপা যায় না, সে কল শাসনও হয় না — প্রতিটি কলে user/tenant/model/latency/cost জবাবদিহি-চাবি (established vendor pattern)।
- SupremeAI-র সংযোগবিন্দু: Langfuse ইন্টিগ্রেশন অস্ট্রিম-পথে আছে (`telemetry.py`); খালি জায়গা: স্ট্রিমিং-পথ এই মতবাদ থেকে পুরো বাদ (P-A) এবং tenant-চাবি প্রধান পথে প্রচারিতই হয় না (P-B)।

### ৩.৫ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল (fresh main 6ef6550-verified)

| প্রতিযোগী | যা করে | SupremeAI আজ (6ef6550-verified) | গ্যাপ |
|---|---|---|---|
| LiteLLM | unifed provider চুক্তি | ইতিমধ্যেই litellm-ভিত্তিক (`cloud_adapter.py` L94) — কেনার নয় | ডুপ্লিকেট providers.py retirement (P-G) |
| OpenRouter | প্রতি-অনুরোধ খরচ-অ্যাট্রিবিউশন | অস্ট্রিম-পথে track_llm_call আছে; স্ট্রিমিং-পথে শূন্য | P-A + P-B |
| Portkey | config-ভিত্তিক resilience + সৎ স্বাস্থ্য-উপাত্ত | fallback/cache/breaker কোডে আছে; উপাত্ত হার্ডকোডেড/মৃত | P-D + P-E |
| Helicone-ধাঁচ | প্রতি-কল জবাবদিহি-চাবি | Langfuse অস্ট্রিমে; tenant-চাবি প্রচারিত নয় | P-B |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main 6ef6550, 2026-09-17)

| বিদ্যমান | বিষয় | এই নীলনকশার সাথে সম্পর্ক |
|---|---|---|
| `MODULE_01_MEMORY_POWER_UP_2026-09-17.md` | মেমোরি একীকরণ (ERR-F02) | সম্পূরক — semantic cache-এর ভেক্টর-ব্যাকএন্ড (`semantic_cache.py` → ExperienceDatabase) মেমোরি-একীকরণের সাথে মিলবে; খরচ-টেলিমেট্রি → মেমোরি-সিদ্ধান্তে প্রবাহিত |
| `MODULE_02_ORCHESTRATION_CORE_POWER_UP_2026-09-17.md` | Kernel single-door + ERR-F01 | সম্পূরক — Run fabric-এর execution_logs সক্রিয় হলে routing-সিদ্ধান্তও run-anchored হবে; এই মডিউলের P-B tenant-চাবি orchestration-পথেও প্রবাহিত |
| PLAN_002/PLAN_004/PLAN_006 (caching/compaction/consolidation) | মেমোরি-ক্যাশ স্তর | ভিন্ন স্তর — তারা token-সামগ্রী নিয়ে; এই মডিউল provider-কল নিয়ে; `semantic_cache.py` দুটোর সংযোগ-বিন্দু মাত্র |
| `docs/plans/UNIFIED_NEXT_ROADMAP_2026-09-15.md` M2 Context Engine | প্রম্পট-প্যাকিং অপ্টিমাইজেশন | সম্পূরক — ContextEngine টোকেন *ঢোকানো* কমায়; gateway টোকেনের *খরচ ও গন্তব্য* শাসন করে |
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` §7.2 + trap #16/#17/#19 | fake MultiLLMRouter, runaway-cost, tool-call, fallback-mismatch | এই নীলনকশার P-F/P-B/P-G সরাসরি নিরাময় — alignment |
| `frontend/src/pages/PublicPages.tsx` `/models` static list | সর্বজনীন মডেল-তালিকা hardcoded | ভিন্ন surface — P-C-র vendor-true registry সক্রিয় হলে ভবিষ্যৎ চক্রে API-ভিত্তিক করার প্রার্থী (এই নীলনকশার পরিসরে নয়) |

**পুশ-পূর্ব re-verify (6ef6550):** pull-এর পরেও সব মূল প্রমাণ অপরিবর্তিত — `streaming.py` grep=0, `completion.py` L111 `if tenant_id:`, registry-তে fabricated নাম বর্তমান। নতুন কমিটে `token_budget.py` fail-closed (B-V2-03) ল্যান্ডেড হলেও সেটি serving-path-এ এখনো wired নয় — P-B-র প্রাসঙ্গিকতা অটুট।

**গ্রেপ-যাচাই:** fresh main 6ef6550-এ কোনো বিদ্যমান ডকুমেন্ট streaming-telemetry-সমতা, gateway-স্তর খরচ-প্রয়োগ, vendor-true registry বা দ্বিতীয়-স্ট্যাক (llm_router) একীকরণ-সিঁড়ির execution-নীলনকশা দেয় না — সম্পূর্ণ unclaimed (`docs/plans/` recursive grep, 2026-09-17; `backend/scripts/migrate_llm_routers.py` migration-validator কেবল পার্টনার-স্ক্রিপ্ট, নীলনকশা নয়)।

### ১.৫.১ ক্যানোনিকাল ইনফারেন্স চুক্তি (`InferenceContext`) ও Zero-Bypass Inference Boundary

SupremeAI-তে বিচ্ছিন্নভাবে স্ট্রিং `tenant_id` পাস করার ভঙ্গুরতা দূর করতে একটি একক ক্যানোনিকাল ডেটাক্লাস প্রণয়ন বাধ্যতামূলক:

```python
@dataclass(frozen=True)
class InferenceContext:
    tenant_id: str
    user_id: str
    request_id: str
    run_id: Optional[str] = None
    task_type: str = "general"
    budget_scope: str = "default"  # 'system_critical', 'user_interactive', 'background_eval'
    source_component: str = "unknown"
```

#### Zero-Bypass Inference Boundary ডকট্রিন:
1. **একক প্রবেশদ্বার:** কোনো মডিউল, এজেন্ট, টুল বা ব্যাকগ্রাউন্ড টাস্ক সরাসরি কোনো প্রোভাইডার ক্লায়েন্ট (যেমন `litellm.acompletion` বা raw `httpx`) সরাসরি কল করতে পারবে না।
2. **বাধ্যতামূলক কনটেক্সট:** প্রতিটি কল অবশ্যই একটি সম্পূর্ণ `InferenceContext` ধারণ করবে; কনটেক্সটবিহীন কল গেটওয়ে বাউন্ডারিতেই রিজেক্টেড হবে।
3. **সিআই স্ট্যাটিক অ্যানালাইসিস গেট (`check_inference_boundary.py`):** কোডবেসে সরাসরি প্রোভাইডার অ্যাডাপ্টার বা র-এপিআই ইমপোর্ট/কল ডিটেক্ট হলে পিআর বিল্ড ও সিআই ব্যর্থ হবে।

---

## Part 2 — Six-Field Complete Plan

### ২.১ কী আছে (কোড-যাচাইকৃত)

1. **Canonical gateway প্যাকেজ:** `backend/core/llm/llm_gateway/` — completion.py (561 লাইন: cache → CostGuard → Tier-0 → optimizer → chain-loop → telemetry), routing.py (174), registry.py (166), resilience.py (91), streaming.py (115), litellm_runtime.py (138), http_client.py (86), gateway.py (102); ১৩ API route-ফাইল ইমপোর্ট করে।
2. **বাস্তব provider boundary:** `providers/cloud_adapter.py` — litellm.acompletion + Anthropic cache_control; `ollama_adapter.py` env-gated লোকাল।
3. **14-provider key-map + key-pool rotation:** `registry.py` `_MODEL_KEY_MAP` (groq, gemini, openai, deepseek, openrouter, hf, nvidia, moonshot, together, ollama, hf_space, bynara, bai) + `_ProviderKeyPool` (round-robin + cooldown)।
4. **Resilience:** 429 → Retry-After backoff + key mark_error(60s); 401/403 → 300s; 5xx → jitter; সব-ব্যর্থ → SelfHealer.propose_fix + CRITICAL event (`completion.py` L533-561)।
5. **Tier-0 bypass:** `advanced_model_router.py` `route_with_confidence` — অ্যাংকর-regex-প্যাটার্নে zero-token উত্তর (লাইভ, `completion.py` L127-144)।
6. **Telemetry + free-tier:** `telemetry.py` (অস্ট্রিম পথে track_llm_call → LearningStore + calibration EMA); `free_tier_tracker.py` (457 লাইন RPM/TPM/RPD) — `brain/model_router.py` এর পরামর্শক।
7. **Semantic cache:** `core/cache/semantic_cache.py` (144 লাইন) — vector-ভিত্তিক, অস্ট্রিম-পথে লাইভ।
8. **বাস্তব admin ক্ষমতা:** `admin_llm.py` — runtime override POST (বাস্তব), breaker reset, fallback-chain preview; ফ্রন্টএন্ড `LlmGatewayPage.tsx` (219 লাইন) wired।
9. **ফ্যাসাড:** `brain/model_router.py` — ~30 importer-এর একক দরজা; breaker per task_type + honest quota-exhaustion dict।
10. **টেস্ট-সম্পদ:** ~3,111 LOC / 17 ফাইল — canonical path ভারী-আচ্ছাদিত (test_llm_gateway_completion.py 1,001 লাইন, ~50 টেস্ট)।

### ২.২ কী নেই (কোড-যাচাইকৃত অনুপস্থিতি)

1. **স্ট্রিমিং-পথে কোনো পর্যবেক্ষণযোগ্যতা** — `streaming.py`-এ track_llm_call/Langfuse/খরচ = 0 উল্লেখ; ব্যবহারকারী-দৃশ্যমান প্রধান ট্রাফিক LearningStore/calibration/খরচ-রিপোর্টে অদৃশ্য।
2. **প্রধান পথে কোনো খরচ-প্রয়োগ** — CostGuard কেবল `if tenant_id` (completion.py L111); ১৩ serving-route কেউ tenant_id পাস করে না (chat.py L233 sed-verified); TokenDeductor gateway-পথে অজাগত-ever।
3. **সৎ মডেল-উপাত্ত** — registry-তে ৬+ fabricated মডেল; `_resolve_registry_model` alias-প্যাচ; `PROVIDER_COST_MAP` ৯টি হাতে-টাইপ ধ্রুবক — vendor-true context-window/price নেই।
4. **জীবন্ত routing-policy** — প্রতিটি chain-এর head retired; `task_overrides` অপঠিত; নীতি কোডে হার্ডকোডেড (flat 12s timeout, one-shot 429 retry)।
5. **জীবন্ত provider-health** — `provider_router.py` সম্পূর্ণ অচল (caller শূন্য); সিদ্ধান্ত-পথে হার্ডকোডেড health; admin UI কাল্পনিক stats দেখায়।
6. **সত্য-উত্তরের নিশ্চয়তা** — false-assurance surface: competitive_kit fabricated (এখন `backend/core/competitive_kit.py` L1359) ও route_and_stream "Hello World" (এখন `async_route_and_stream`) জীবিত; gateway MagicMock-default upstream V4-এ বন্ধ (a3fe8bb) + model_router-এর production-ব্রাঞ্চে mock-শনাক্তকরণ।
7. **এক গেটওয়ে** — দ্বিতীয় জীবিত স্ট্যাক (llm_router 956 লাইন + providers.py 708 লাইন + HFSwarmRouter) — double breaker-namespace, বিচ্ছিন্ন fallback-আচরণ (trap #19)।

### ২.৩ কী করতে হবে (Phased Engineering Blueprint: P0 থেকে P7)

```text
P0: ক্যানোনিকাল কনট্রাক্ট ও জিরো-বাইপাস গেট (InferenceContext baseline + CI Bypass-Check)
P1: মিথ্যা-আশ্বাসের অবলুপ্তি ও স্ট্রাকচার্ড এরর (False-Assurance Purge + Structured Failure)
P2: স্ট্রিমিং অবজারভেবিলিটি সমতা (Streaming Telemetry & Cost Accounting Parity)
P3: বাউন্ডেড ফেইল-ওপেন ও বাজেট রিজার্ভেশন/সেটেলমেন্ট (Bounded Fail-Open + Atomic Budget Lease)
P4: ভেন্ডর-সত্য রেজিস্ট্রি ও ক্যাপাবিলিটি পলিসি (Vendor-True Registry + Dynamic Capability Policy)
P5: মাল্টি-ফ্যাক্টর হেলথ ও লাইভ টেলিমেট্রি ফিড (Passive Health Feed + Flag-Gated Opt-In Probes)
P6: স্ট্যাবিলাইজেশন, বেঞ্চমার্ক ও কনকারেন্সি টেস্ট (100 Simultaneous Race-Free Verification)
P7: সিঙ্গেল গেটওয়ে কনসোলিডেশন ও রিটায়ারমেন্ট (Facade-First Delegation + Dead Code Removal)
```

### ২.৪ কীভাবে করব (ফাইল-স্তরের সুনির্দিষ্ট বাস্তবায়ন কৌশল)

- **P0 — Contract Baseline & Zero-Bypass CI Gate:**
  - `backend/core/llm/llm_gateway/context.py`-এ ক্যানোনিকাল `InferenceContext` সংজ্ঞায়িত করা।
  - ১৩টি মূল serving route-এ (`chat.py`, `task_workspace.py`, `reasoning.py`, ইত্যাদি) ক্যানোনিকাল কনটেক্সট পাসিং বাধ্যতামূলক করা।
  - CI স্ট্যাটিক অ্যানালাইসিস স্ক্রিপ্ট যোগ করা যা সরাসরি প্রোভাইডার ক্লায়েন্ট কল সনাক্ত করে গেটওয়ে বাইপাস রোধ করবে।

- **P1 — False-Assurance Purge & Structured Failure Handling (P-F):**
  - `backend/core/competitive_kit.py` L1359-এর ফেব্রিকেটেড `"[Response from …]"` সম্পূর্ণ অপসারণ করে গেটওয়ে ডেলিগেশনে আনা।
  - `model_router.async_route_and_stream`-এর "Hello World" ফালব্যাক বন্ধ করে সুনির্দিষ্ট এরর টাইপ রেইজ করা।
  - এরর হ্যান্ডলিং হবে কঠোর কিন্তু ইউজার-ফ্রেন্ডলি: আনহ্যান্ডেলড ক্র্যাশের বদলে স্ট্রাকচার্ড এরর ডোমেইন (`GatewayExhaustionError`, `ProviderUnavailableError` with retry-after header) রিটার্ন করা।

- **P2 — Streaming Observability Parity (P-A):**
  - `streaming.py`-এর `_stream_completion` লুপের শেষ প্রান্তে (final chunk-এ টোকেন usage আসার সাথে সাথে) `track_llm_call` কল সংযুক্ত করা।
  - নন-স্ট্রিমিং ও স্ট্রিমিং-এর মধ্যে টেলিমেট্রি, ল্যাংফিউজ ট্রেসিং ও খরচ অ্যাট্রিবিউশনের ব্যবধান <১% টলারেন্সে নামিয়ে আনা।
  - প্রতি-চাঙ্কে কোনো এক্সট্রা নেটওয়ার্ক কল বা ওভারহেড থাকবে না; কেবল ফাইনাল চাঙ্কে সিঙ্ক সম্পন্ন হবে।

- **P3 — Bounded Fail-Open & Budget Reservation/Settlement (P-B):**
  - **Bounded Fail-Open ম্যাট্রিক্স:** রেডিস বা বাজেট ডাটাবেজ সাময়িক ডাউন হলে সব ট্রাফিকের জন্য ঢালাও ফেইল-ওপেন বিপজ্জনক (রানঅ্যাওয়ে কস্টের ঝুঁকি)। তাই বাউন্ডেড ম্যাট্রিক্স প্রযোজ্য:
    - *Groq, Gemini Flash, DeepSeek V3 (ফ্রি / অতি-সস্তা):* Allow with Warning (ব্যবসা নিরবচ্ছিন্ন থাকবে)।
    - *Claude 3.5 Sonnet, GPT-4o (ব্যয়বহুল মডেল):* Strictly Blocked (আউট-অব-বাজেট প্রতিরোধ)।
    - *অজ্ঞাত / আনঅথেনটিকেটেড টেন্যান্ট:* Strictly Blocked।
  - **Pre-call BudgetReservation + Post-call UsageSettlement:**
    - একযোগে ১০০টি কনকারেন্ট রিকোয়েস্ট একই ব্যালেন্স দেখে ওভার-স্পেন্ড করার রেস কন্ডিশন রোধ করতে প্রি-কল লেভেলে একটি অ্যাটমিক Redis লিজ (TTL: ৬০ সেকেন্ড) বরাদ্দ হবে।
    - ইনফারেন্স শেষ হলে পোস্ট-কল সেটেলমেন্টের মাধ্যমে প্রকৃত টোকেন খরচ অ্যাডজাস্ট হবে এবং অবশিষ্ট রিজার্ভেশন রিলিজ হবে।

- **P4 — Vendor-True Model Registry & Capability-Driven Policy (P-C & P-D):**
  - `model_registry.py`-এর ফেব্রিকেটেড নামগুলো ("gpt-5.5", "claude-opus-4.7") অপসারণ করে `litellm` ভেন্ডর-সত্য মেটাডেটা (context window, input/output cost, capability flags) দিয়ে প্রতিস্থাপন।
  - ডুপ্লিকেট `routing_policy.json` ফাইলগুলোকে একত্রিত করে একক ক্যানোনিকাল ফাইল নির্ধারণ।
  - হার্ডকোডেড চেইনের পরিবর্তে মডেলের লাইভ ক্যাপাবিলিটি (`tool_use`, `reasoning`, `vision`, `context_length`) অনুযায়ী ডাইনামিক ফিল্টারিং ও রুট নির্বাচন।

- **P5 — Multi-Factor Provider Health & Live Telemetry Feed (P-E):**
  - কোনো অতিরিক্ত পোলিং বা বুট-ল্যাটেন্সি তৈরি না করে `telemetry.py` `track_llm_call` থেকে সরাসরি `provider_router.record_result()` ফিড করা (EWMA latency, 429/5xx error rates)।
  - স্টার্টআপ অ্যাক্টিভ প্রোব ডিফল্টে বন্ধ (ফ্ল্যাগ-গেটেড opt-in) থাকবে যাতে কোনো ফ্রি-টিয়ার কোটা অপচয় না হয়।

- **P6 — Stabilization, Benchmark & Concurrency Gate:**
  - সিআই-তে ১০০টি সিমুলেটেড কনকারেন্ট রিকোয়েস্ট পাঠিয়ে বাজেট রিজার্ভেশনের রেস-কন্ডিশন ফ্রি আচরণ পরীক্ষা করা।
  - স্ট্রিমিং ও নন-স্ট্রিমিং প্যারিটি টেস্টে শূন্য খরচ-ব্যবধান নিশ্চিত করা।

- **P7 — Single Gateway Consolidation & Legacy Retirement (P-G):**
  - ফ্যাসাড-ফার্স্ট পদ্ধতি: `services/llm/llm_router.LLMRouter` এবং `brain/model_router.ModelRouter`-এর পাবলিক ইন্টারফেস অপরিবর্তিত রেখে ভেতরের কল গেটওয়েতে ডেলিগেট করা।
  - ধীরে ধীরে কলারদের মাইগ্রেট করে ডুপ্লিকেট `providers.py` (৭০৮ লাইন) এবং অচল কোড নিরাপদভাবে রিটায়ার করা।

### ২.৪.১ ক্লাউড বনাম লোকাল ইনফারেন্স নীতি: ৩-টায়ার রিয়েলিজম ম্যাট্রিক্স (3-Tier GPU Realism Matrix)

> **প্রতিষ্ঠাতা-প্রশ্ন ও আর্কিটেকচারাল নীতি:** *"SupremeAI-র মূল নীতি অনুযায়ী কোনো ব্যক্তিগত লোকাল পিসিকে ক্লাউড প্রোডাকশন সার্ভার হিসেবে ব্যবহার করা নিষিদ্ধ (AGENTS.md Section 1: Production Parity Rule) — তাহলে প্রোডাকশনে Ollama বা লোকাল মডেল কীভাবে কাজ করবে এবং কীভাবে খরচ ৮০% কমাবে?"*

SupremeAI ইনফারেন্সকে ৩টি স্পষ্ট ও বাস্তবসম্মত টায়ারে বিভক্ত করে পরিচালনা করে:

| টায়ার | ভূমিকা ও পরিবেশ | সমর্থিত রানটাইম | SLA ও অপারেশনাল গ্যারান্টি |
|---|---|---|---|
| **Tier 1: Production Managed Cloud** | ২৪/৭ প্রোডাকশন ক্লাউড সার্ভিস | Groq, Gemini Flash, DeepSeek API, Claude | **৯৯.৯% আপটাইম SLA**; সম্পূর্ণ ক্লাউড-প্যারিটি; শূন্য ক্লায়েন্ট ডিপেনডেন্সি |
| **Tier 2: Dedicated Cloud GPU** | প্রাইভেট এন্টারপ্রাইজ ভিপিএস | RunPod, Modal, Hetzner VPS with vLLM/Ollama | ডেডিকেটেড সেলফ-হোস্টেড ইনফারেন্স; এন্টারপ্রাইজ প্রাইভেসি |
| **Tier 3: Dev/Test & Evaluation Lab** | সিন্থেটিক ডেটা, টেস্টিং ও অফলাইন আইডিই | ৬-ক্যাগল ফেইলওভার পুল, Colab T4, লোকাল ওলামা সাইডকার | **জিরো প্রোডাকশন SLA**; টেস্ট, বেঞ্চমার্কিং ও অফলাইন এক্সিলারেশনের জন্য ১০০% ফ্রি |

1. **টায়ার ১ — প্রোডাকশন ক্লাউড ইনফারেন্স (Enterprise Managed Cloud):**
   - প্রোডাকশনে লাইভ ইউজার ট্রাফিক কখনো কোনো ডেভেলপার বা ইউজারের পার্সোনাল পিসির ওপর নির্ভর করে না।
   - সেন্ট্রাল ব্যাকএন্ড সরাসরি হাই-স্পিড কম খরচের ক্লাউড এপিআই দিয়ে পরিচালিত হয়:
     - সিনট্যাক্স, লিটার ও ফরম্যাটিং -> **Groq Llama-3 / Mixtral (ফ্রি / ০ ডলার)**
     - সাধারণ চ্যাট ও সামারি -> **Gemini 2.0 Flash (ফ্রি টিয়ার)**
     - রুটিন কোডিং ও রিফ্যাক্টরিং -> **DeepSeek V3 (প্রতি ১ মিলিয়ন টোকেন মাত্র $0.14)**
     - কেবল জটিল আর্কিটেকচারাল প্ল্যানিং -> **Claude 3.5 Sonnet / GPT-4o**
   - এই স্মার্ট রাউটিংয়ের মাধ্যমে প্রোডাকশনে কোনো আনরিলায়েবল সার্ভার ছাড়াই সার্বিক এপিআই খরচ **৮০% পর্যন্ত কমে যায়**।

2. **টায়ার ২ — সেলফ-হোস্টেড ডেডিকেটেড জিপিইউ (Private VPS / RunPod):**
   - এন্টারপ্রাইজ গ্রাহক বা প্রাইভেট ডিপ্লয়মেন্টে ডেডিকেটেড ক্লাউড GPU কন্টেইনারে `vLLM` বা `Ollama` চলে।
   - সেন্ট্রাল ব্যাকএন্ড এনভায়রনমেন্ট ভেরিয়েবল `OLLAMA_URL` দিয়ে সিকিউর প্রাইভেট নেটওয়ার্কে এর সাথে যোগাযোগ করে।

3. **টায়ার ৩ — ক্লায়েন্ট সাইডকার ও অফলাইন মোড (Client Mesh — লোকাল পিসি সার্ভার নয়, ক্লায়েন্ট!):**
   - আমাদের **Supreme Teleport** ও আইডিই এক্সটেনশনে (Antigravity, Cursor, Cline) লোকাল পিসি হলো *ক্লায়েন্ট*, সার্ভার নয়।
   - ব্যবহারকারী যখন নিজের মেশিনে কোড করেন, তখন ক্লাউড সার্ভারের ওপর চাপ ও খরচ কমাতে লোকাল সাইডকার সরাসরি মেশিনের নিজস্ব Ollama রানটাইম (`http://127.0.0.1:11434`, `offline_mode.py`) ব্যবহার করে ইনফারেন্স চালায়।

### ২.৪.২ ক্লাউডে সম্পূর্ণ ফ্রিতে ডেডিকেটেড GPU ব্যবহারের কৌশল (Zero-Cost Cloud GPU Blueprint)

ডেভেলপমেন্ট, ইভ্যালুয়েশন ল্যাব ও স্মোক-টেস্টিং পরিবেশে কোনো অর্থ বা ক্রেডিট কার্ড খরচ না করে ক্লাউড GPU ও ওপেন-সোর্স মডেল চালানোর জন্য ৫টি কার্যকর কৌশল:

1. **Google Colab + Cloudflare Tunnel (ফ্রি ১৫ জিবি Nvidia T4 GPU):**
   - Colab নোটবুকে ব্যাকগ্রাউন্ডে `ollama serve` এবং `cloudflared tunnel` চালু করে পাবলিক HTTPS টানেল URL তৈরি করা।
   - এই টানেল URL-টি ডেভ গেটওয়ের `OLLAMA_URL` এনভায়রনমেন্ট ভেরিয়েবলে দিয়ে স্মোক-টেস্টিং ও মডেল ইভ্যালুয়েশন চালানো যায় (প্রতি সেশন ১২ ঘণ্টা পর্যন্ত)।

2. **Kaggle Notebooks (সপ্তাহে ৩০ ঘণ্টা নিশ্চিত ফ্রি GPU):**
   - Kaggle প্রতি সপ্তাহে ৩০ ঘণ্টা বিনামূল্যে Nvidia P100 (16GB VRAM) বা Dual T4 GPU প্রদান করে।
   - ব্যাকগ্রাউন্ডে Ollama ও Cloudflare টানেল চালিয়ে দীর্ঘস্থায়ী টেস্ট রান ও ল্যাব বেঞ্চমার্কিং করা যায়।

3. **Hugging Face Spaces (২৪/৭ পার্মানেন্ট ফ্রি হোস্টিং):**
   - ফ্রি Docker Space-এ হালকা কোডিং মডেল (যেমন `Qwen2.5-Coder-1.5B/3B` বা `Llama-3.2-3B`) ডিপ্লয় করে ২৪/৭ সক্রিয় পাবলিক এন্ডপয়েন্ট তৈরি করা যায়।

4. **Cloudflare Workers AI (জিরো-মেইনটেন্যান্স ফ্রি এজ জিপিইউ):**
   - প্রতিদিন **১০,০০০ নিউরন ফ্রিতে** পাওয়া যায়; Llama 3.3 70B, DeepSeek R1 Distill, Qwen 2.5 Coder সরাসরি REST API দিয়ে কল করা যায়।

5. **Groq ও Cerebras ফ্রি ক্লাউড এপিআই (ওলামার চেয়েও ১০× দ্রুত ও ০ খরচ):**
   - কোনো সেলফ-হোস্টেড GPU কনটেইনার ম্যানেজ করার ঝামেলা ছাড়াই Groq (প্রতি সেকেন্ডে ৩০০-৫০০ টোকেন) এবং Cerebras (সেকেন্ডে ১,৮০০ টোকেন)-এর জেনেরাস ফ্রি টায়ার দিয়ে Llama-3 ও DeepSeek পরিচালনা করা যায়।

### ২.৪.৩ ৬-ক্যাগল অ্যাকাউন্ট ফেইলওভার পুল: ল্যাব ও ইভ্যালুয়েশনের ২৪/৭ ফ্রি GPU ক্লাস্টার (6x Kaggle Failover Pool Architecture)

> **ল্যাব স্কেলিং ও গাণিতিক ভিত্তি:**  
> ১টি Kaggle অ্যাকাউন্ট প্রতি সপ্তাহে দেয় **৩০ ঘণ্টা ফ্রি GPU** (Nvidia P100 / Dual T4, 16GB VRAM)।  
> ৬টি Kaggle অ্যাকাউন্ট = **৬ × ৩০ = ১৮০ ঘণ্টা প্রতি সপ্তাহে!**  
> অথচ ১ সপ্তাহে মোট সময় = **২৪ × ৭ = ১৬৮ ঘণ্টা**।  
> অর্থাৎ, **১৮০ ঘণ্টা > ১৬৮ ঘণ্টা** — ৬টি অ্যাকাউন্ট রোটেশন ও ফেইলওভার করে ৩৬৫ দিন সম্পূর্ণ ফ্রিতে হাই-এন্ড ডেডিকেটেড ক্লাউড GPU ল্যাব চালানো সম্ভব।

#### অপারেশনাল বাউন্ডারি ও প্রোডাকশন রিয়েলিজম গার্ড:
- **ল্যাব ও ইভ্যালুয়েশন পরিধি:** এই ৬-ক্যাগল পুলটি কঠোরভাবে **টায়ার ৩ (Dev/Test & Evaluation Lab)**-এর অন্তর্ভুক্ত। এটি সিন্থেটিক ডেটাসেট তৈরি, টেস্ট স্যুট এক্সিকিউশন এবং মডেল ফাইন-টিউনিং ইভ্যালুয়েশনের জন্য একটি অনন্য জিরো-কস্ট অ্যাসেট।
- **প্রোডাকশন আইসোলেশন:** প্রোডাকশন ইউজার-ফেসিং ট্রাফিকের জন্য এটি কখনোই প্রাথমিক ডিপেনডেন্সি হিসেবে ব্যবহৃত হবে না (সেশন রিস্টার্ট ও ক্লাউডফ্লেয়ার টানেল ড্রপআউটের কারণে)। প্রোডাকশন সবসময় টায়ার ১ (Groq / Flash / DeepSeek) দ্বারা সুরক্ষিত থাকবে।

#### আর্কিটেকচারাল ইমপ্লিমেন্টেশন ও ফেইলওভার মেকানিজম:
1. **অ্যাকাউন্ট পুলিং ও টানেল রেজিস্ট্রি (`KaggleEndpointPool`):**
   - ৬টি ক্যাগল নোটবুক নিজস্ব Cloudflare টানেল দিয়ে লাইভ থাকবে:
     ```python
     KAGGLE_GPU_NODES = [
         {"id": "kaggle-node-1", "url": "https://node1.trycloudflare.com", "status": "active"},
         {"id": "kaggle-node-2", "url": "https://node2.trycloudflare.com", "status": "standby"},
         {"id": "kaggle-node-3", "url": "https://node3.trycloudflare.com", "status": "standby"},
         {"id": "kaggle-node-4", "url": "https://node4.trycloudflare.com", "status": "standby"},
         {"id": "kaggle-node-5", "url": "https://node5.trycloudflare.com", "status": "standby"},
         {"id": "kaggle-node-6", "url": "https://node6.trycloudflare.com", "status": "standby"},
     ]
     ```
2. **অটো-রোটেশন ও সেশন লিমিট গার্ড (Session Timeout Resilience):**
   - ক্যাগলে একটি সেশন একটানা ৯ থেকে ১২ ঘণ্টা চলে। গেটওয়ের `resilience.py` নোড ১-এর সেশন শেষ হওয়া বা কোটা পূর্ণ হওয়া মাত্রই **<৫০০ মিলি-সেকেন্ডে নোড ২-এ ট্রাফিক ফেইলওভার** করবে।
3. **জিরো ডাউনটাইম শিডিউলিং (Supervisor Auto-Trigger):**
   - আমাদের `Module 22 (Scheduler Organ)`-এর মাধ্যমে নোডগুলোর স্টার্ট-টাইম শিডিউল করা থাকবে, যাতে একটি নোডের সেশন শেষ হওয়ার আগেই পরবর্তী নোডটি বুট হয়ে রেডি থাকে (Overlapping Canary Handover)।
4. **টায়ার ১ ফেইল-সেফ (Cloudflare / Groq Fallback):**
   - কোনো কারণে ক্যাগল ক্লাস্টারের সব টানেল অফলাইনে গেলে কোনো ল্যাব টেস্ট যাতে আটকে না যায়, গেটওয়ে স্বয়ংক্রিয়ভাবে ক্লাউডফ্লেয়ার Workers AI বা Groq-এ ফেইলওভার করবে।

### ২.৫ বেনিফিট (সবই hypothesis — Gate 5-এ measured হবে)

1. **অদৃশ্য → অ্যাট্রিবিউটেড:** স্ট্রিমিং-ট্রাফিক (সম্ভবত সিংহভাগ — hypothesis) খরচ/শেখায় যুক্ত হলে খরচ-রিপোর্ট, token-calibration ও learning-loop-এর উপাত্ত-ঘাটতি পূরণ — Constitution #11 "Memory Must Compound"-এর inference-অঙ্গনে পূর্ণতা।
2. **Runaway-cost trap কাঠামোগত বন্ধ (P-B):** trap #16 বন্ধ; billing-hooks (TokenDeductor/quota_enforcer) প্রথমবার প্রধান পথে সত্য — per-tenant জবাবদিহি সম্ভব।
3. **সিদ্ধান্ত-মান বৃদ্ধি (P-C/D/E):** মিথ্যা registry + মৃত head-chain + হার্ডকোডেড health → সৎ উপাত্ত; সঠিক মডেল-বাছাই = কম খরচ + কম latency (রিগ্রেশন-ঝুঁকির সাথেই, পরিমিত হবে)।
4. **আস্থা-পুনরুদ্ধার (P-F):** ফেব্রিকেটেড উত্তর শূন্য — "Verify Before Trust" (#5) ও "No Silent Failure" (#13) gateway-স্তরে সত্য; defect register §7.2 বন্ধ।
5. **রক্ষণ-বোঝা হ্রাস (P-G):** ~1,700+ লাইন ডুপ্লিকেট স্ট্যাক retirement-প্রার্থী; এক fallback-আচরণ, এক breaker-namespace (trap #19 নিরাময়-পথ)।
6. **দৃশ্যমান crown-jewel:** admin-প্যানেলে জীবন্ত chain/latency/breaker — ফাউন্ডার ও ব্যবহারকারী দুজনেই "কী হচ্ছে কেন" দেখবে।

### ২.৬ ক্ষতি/ঝুঁকি (সৎ, প্রশমন সহ)

1. **প্রধান পথে নতুন ব্যর্থতা-মোড (P-B):** বাজেট-চেক ভুল বাধা হলে ব্যবহার-অচল — প্রশমন: fail-open design, flag default false, shadow-পর্বে শুধু লগ (ব্লক নয়), flag-off = আজকের আচরণ।
2. **Registry-বদলে নির্ভরশীল-ভাঙা (P-C):** fabricated নামের উপর নির্মিত কোড/টেস্ট — প্রশমন: আগে ঢোকানো-পরে অপসারণ (add-then-remove), alias-স্তর অন্তর্বর্তী সেতু, readiness-টেস্ট সমসাময়িক আপডেট।
3. **Consolidation বৃহত্তম টেস্ট-পৃষ্ঠ (P-G):** 10+ caller, 22 skipped টেস্ট, দুই breaker-namespace — প্রশমন: ফ্যাসাড-প্রথম, প্রতি-caller মাইগ্রেশন আলাদা PR, `migrate_llm_routers.py` গেট, প্রতিটি ধাপে 17-টেস্ট-ফাইল zero-regression।
4. **Telemetry ওভারহেড (P-A):** প্রতি-চাংক লেখা হলে latency — প্রশমন: কেবল final-chunk টেলিমেট্রি; বিদ্যমান disconnect-aware relay অটুট।
5. **পরিসর-ঝুঁকি:** gateway-refactor-এর ঘুরপথে নতুন ফিচার-লোভ (guardrails, hedging, নতুন provider) — প্রশমন: এই নীলনকশায় কোনো নতুন ফিচার নেই; শুধু সত্য-পুনঃসংযোগ ও একীকরণ; প্রতিটি Phase আলাদা Gate 0–6।

---

## Part 3 — Explicit Out-of-Scope

1. নতুন gateway-product/dependency (Portkey/Helicone/LiteLLM-proxy server আমদানি নয়) — বিদ্যমান litellm-লাইব্রেরি ও নিজস্ব স্পাইনই যথেষ্ট।
2. Guardrails/PII-ফিল্টার, request-hedging, prompt-templating ইঞ্জিন — আলাদা ভবিষ্যৎ প্ল্যানের প্রার্থী (এখানে কেবল গ্যাপ-টেবিলে উল্লিখিত)।
3. `/models` সর্বজনীন পৃষ্ঠার API-করণ ও mission-control-এ LLM-view মিররিং — ফ্রন্টএন্ড-চক্রের প্রার্থী (কিউ #10-এর সাথে)।
4. কোনো route/frontend breaking change — backend সত্য-উপাত্ত ও একীকরণ-স্তর মাত্র।
5. Tool-call/structured-output normalization বাস্তবায়ন — trap #17-এর পূর্ণ নিরাময় আলাদা execution প্ল্যান চায় (এখানে P-F-এর সত্য-পুরস্কার পথ প্রস্তুত হবে)।
6. সমান্তরাল multi-plan execution — একসময়ে একটাই Phase active।

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | প্রতিটি Phase আলাদা proposed execution; একসময়ে একটাই active |
| 2. Small change to existing code | ✅ | সব পরিবর্তন বিদ্যমান ফাইলে (streaming/completion/registry/policy.json); নতুন কোড কেবল টেস্টে |
| 3. No new infrastructure | ✅ | litellm/Redis/LearningStore/Langfuse বিদ্যমান; migration শূন্য |
| 4. No CI cost amplification | ✅ | parity/tenant-টেস্ট বিদ্যমান sharded suite-এ; নতুন শাখা নয় |
| 5. No credit-burn risk | ✅ | উল্টো — এই নীলনকশাই credit-burn বন্ধের নীলনকশা; P-B flag default false |
| 6. No academic leaderboard | ✅ | সরাসরি প্রোডাক্ট-ক্ষমতা: parity%, budget-coverage, truth-গণনা |
| 7. Realistic resource budget | ✅ | telemetry কেবল final-chunk; retention-প্রয়োজন নেই (কোনো নতুন স্থায়ী-ভলিউম নয়) |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main 6ef6550 sed/grep/wc-যাচাই (frontmatter last_verified-এ তালিকাভুক্ত); register-উৎস স্পষ্ট |

| Constitution ধারা | প্রভাব |
|---|---|
| #5 Verify Before Trust | ✅ fabricated registry/health/উত্তর — তিনটি মিথ্যা-উৎস বন্ধ; parity টেস্ট বাধ্যতামূলক |
| #6 Policy Before Power | ✅ খরচ-নীতি প্রধান পথে (P-B) — ক্ষমতার আগে নীতি |
| #8 Graceful Degradation | ✅ বাজেট-চেক fail-open; registry-বদল add-then-remove |
| #11 Memory Must Compound | ✅ স্ট্রিমিং-টেলিমেট্রি → LearningStore → calibration/routing-শেখা |
| #13 No Silent Failure | ✅ "Hello World"/"[Response from ...]"/MagicMock — তিনটি silent-failure উৎস পর্যুগ |
| #14 Zero-Mock Doctrine (apps/mission-control মতবাদ) | ✅ P-F ও P-E মূলত zero-mock প্রয়োগ backend inference-স্পাইনে |

---

## Part 5 — Verification & Acceptance (Gates 4–6) + Rollback

- **Gate 4 (প্রতি Phase):** `pytest` backend sharded suite শূন্য-ব্যর্থতা; P-A: streaming-vs-nonstream parity টেস্ট (একই প্রম্পট → দুই track_llm_call row, খরচ-ব্যবধান 0%); P-B: tenant-propagation integration টেস্ট (chat.py→gateway→CostGuard/TokenDeductor পর্যবেক্ষণ, fail-open শাখা-টেস্ট সহ); P-C/D: registry/policy truth-গণনা-টেস্ট (fabricated=0, retired-head=0); P-G: `migrate_llm_routers.py` গেট + 17-টেস্ট-ফাইল zero-regression।
- **Gate 5 (live):** বাস্তব স্ট্রিম-কলের খরচ-রিপোর্টে উপস্থিতি; ২৪-ঘণ্টায় tenant-অ্যাট্রিবিউটেড কল >0; admin-প্যানেলে বাস্তব latency/unavailable-অনুপাত পর্যবেক্ষিত; fabricated-response গণনা শূন্য।
- **Gate 6:** প্রতিটি Phase নিজস্ব execution প্ল্যানে complete; এই নীলনকশা complete যখন acceptance_criteria-র পাঁচটি সংজ্ঞা সবই evidence-সহ সত্য।
- **Rollback:** প্রতিটি Phase = একক commit revert + flag-off; কোনো schema/data-loss path নেই; P-G-র retirement ধাপ সবশেষ ও সবচেয়ে সাবধান — তারও revert-পথ: git revert একক commit।

---

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Pass, 2026-09-17, branch `crown-jewel-v2`)

| দর্শন | রায় | ভিত্তি |
|---|---|---|
| Zero cost | ✅ সংগত (P-E সংশোধিত) | নতুন gateway-product/dependency স্পষ্ট বাইরে (Part 3-1); P-E-র স্টার্টআপ-প্রোব আগে সর্বদা-চালু প্রস্তাব ছিল — এখন flag-gated default-off (free-key quota-রক্ষা); P-B fail-open + flag default false |
| Lightweight | ✅ সংগত | বিদ্যমান litellm/LearningStore/Redis পুনঃব্যবহার; P-G facade-first — retirement-ই মূল কাজ |
| Fast & smooth | ✅ সংগত | P-A কেবল final-chunk টেলিমেট্রি (প্রতি-চাংক overhead নয়); P-E boot-latency-বিহীন ক্রম |
| Zero hardcode | ⚠️ ছিল → ✅ **সংশোধিত** | P-C ইতিমধ্যেই litellm-মেটাডেটা-চালিত; **নতুন আবিষ্কৃত**: routing_policy.json এখন ৩ কপি/২ বিষয়বস্তু (drift) — P-D-তে canonical-ফাইল + লাইভ-registry-derived চেইন সংযোজন (§২.৪ সংশোধিত) |

Upstream-রেকনসিলিয়েশন (base `ed35eaf`): streaming.py grep=0 অটুট (P-A প্রাসঙ্গিক), completion.py L111 `if tenant_id:` অটুট (P-B প্রাসঙ্গিক), gateway-MagicMock বন্ধ (P-F আংশিক done-upstream), competitive_kit → `backend/core/` স্থানান্তরিত (পথ-হালনাগাদ), "Hello World" fallback জীবিত (`async_route_and_stream`)।

স্কোপ-সততা: proposal-দর্শন অডিট + মূল-যন্ত্রপাতি spot-check; সম্পূর্ণ line-ref re-verification নয়।

---

## Part 6 — পরবর্তী চক্র লাইনেজ (reference-only; candidate list ≠ execution queue)

- **চক্র ১ (প্রকাশিত):** Module 01 — Memory Subsystem → `MODULE_01_MEMORY_POWER_UP_2026-09-17.md`।
- **চক্র ২ (প্রকাশিত):** Module 02 — Orchestration Core → `MODULE_02_ORCHESTRATION_CORE_POWER_UP_2026-09-17.md`।
- **চক্র ৪ (কিউতে):** Module 04 — Browser Automation Stack (`backend/tools/browser/` + `backend/services/browser/` + `backend/browser/`) — এজেন্টের "হাত"; এই মডিউলের P-A/P-B সম্পূর্ণ হলে browser-পথের LLM-খরচও অ্যাট্রিবিউটেড হবে।
- সূচি ও কিউ-পুনঃর‍্যাঙ্ক: `crown_jewel_series/README.md`।
