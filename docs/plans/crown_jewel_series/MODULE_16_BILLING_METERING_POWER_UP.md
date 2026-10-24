---
id: crown-jewel-module-16-billing-metering-power-up-2026-09-17
title: "Crown Jewel Module Series — Module 16: Billing & Metering Gateway Power-Up (বিলিং-মিটারিং গেটওয়ে: ভাঙা টেলিমেট্রি-লুপ, রেভিনিউ-লিক ওয়েবহুক-ট্র্যাপ, দ্বৈত চেকআউট — মিটার-ফার্স্ট মতবাদে পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Governance Circle (backend/api/routes/billing_api.py + backend/services/billing/ + backend/core/cost_guard.py — বিলিং-মিটারিং অঙ্গ)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ১৬ — একটি মডিউল (বিলিং-মিটারিং গেটওয়ে), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field); Part 1 = গভীর ৩য়-পক্ষ বুদ্ধিমত্তা (LiteLLM model-cost-map + budgets, OpenMeter Apache-2.0, Stripe metering idempotency, OpenTelemetry GenAI conventions); branch crown-jewel-v2 base 41fd9181-এ spot-checkকৃত কোড-প্রমাণ; zero-cost সংবিধান test_billing_zero_cost.py-এ প্রতিষ্ঠিত — এই নীলনকশা তা ভাঙে না"
depends_on:
  - "ক্যানোনিকাল-লাইভ: backend/api/routes/billing_api.py (৫৮৯ লাইন) ALL_ROUTERS-এ is_critical=True (fail-fast import, routers.py L476-479) — ৯ রুট /api/billing/*; সেরা-হার্ডেনড কোড: Stripe-অবিন্যস্তে fail-closed 503 (ERR-G01, L272-280), idempotent ওয়েবহুক ledger pre-check + FOR UPDATE (L364-403, L491-536), wallet SQL optimistic concurrency (models/wallet.py L38-40)"
  - "ট্র্যাপ-ডুপ্লিকেট: backend/api/routes/payments.py (routers.py L217) — ডুপ্লিকেট checkout+plans+webhook; এর webhook নিজেই 'silent revenue leak' logger.critical লেবেল করে (L124-135, কিছুই process করে না); শূন্য frontend কলার"
  - "ভাঙা-লুপ (মূল-আবিষ্কার): পাঠক জীবিত — /api/billing/analytics + /ws/cost-updates Redis cost_guard:*:*:spent সমষ্টি করে (realtime_dashboard.py L264-292, সৎ-শূন্য, ফেব্রিকেট নয়); কিন্তু লেখক বিচ্ছিন্ন — cost_guard.record_spend-এর শূন্য production কলার → কাউন্টার-সর্বদা-খালি → ড্যাশবোর্ড-স্থায়ী-$০; enforcement নিজে জীবিত (llm_gateway/completion.py L122 + tool_gateway L191-193)"
  - "প্ল্যান-শুধু-প্রদর্শনী: কোনো middleware/route SUBSCRIPTION_PLANS/plan-tier/subscription_status পড়ে gate করে না; checkout.session.completed শুধু Firestore admin_users doc আপডেট করে (L405-423); stripe price_id লিটারেল 'price_pro_monthly' — fake"
  - "frontend ৩ চুক্তি-ভাঙা: BillingPage.tsx L26 GET /api/v1/billing/plans — পাথ অস্তিত্বহীন (বাস্তব /api/billing/plans) → silent .catch([]) → চির-কাল খালি পেজ; CostDashboard WS → /api/v1/metrics/stream অস্তিত্বহীন (বাস্তব /ws/cost-updates) → realtime মৃত; মৃত client-side tokens*0.0001 গণিত (V5 fake-$42.50 purge-এর অবশিষ্ট); /usage রুট get_project_admin-গেটেড → সাধারণ user-এর জন্য 403"
  - "শুদ্ধ-শিম-প্যাটার্ন-উপস্থিত: core/billing_plans.py L1-7 deprecated re-export shim → services/billing/billing_plans.py (একক-উৎস, test_deprecated_shims.py L18 টেস্টেড) — ERR-F02 সংগত-প্যাটার্ন payments.py-তে পুনরুৎপাদনযোগ্য"
  - "scripts-dormant: scripts/billing/{usage_reporter,fraud_detector,quota_enforcer} — .github/workflows-এ শূন্য উল্লেখ (grep-প্রমাণিত), manual CLI; টেস্ট চমৎকার (409/310/210 লাইন); কিন্তু fraud_detector এমন token_usage ledger-সারি স্ক্যান করে যা কেউ লেখে না → শুধু topup দেখতে পারে; multicloud_quota_monitor.py main() NameError (L502 CloudWatchman alias-এর আগে L515)"
  - "hardcode-জরিপ: billing_api.py L80 signup bonus Decimal(5.000000) pricing_tiers.json-এর 5.00 ডুপ্লিকেট; billing_plans.py L36-64 মূল্য 0/9.99/199.99 pricing_tiers.json-ক্রেডিট 0/10/100 থেকে বিচ্যুত; rate_limit_quota.py L19-24 DAILY_LIMITS 50/500/5000/999999; cost_guard.py L32-36 tier_limits 0.0/0.02/0.50; billing_api.py L487 bdt_exchange_rate ফলব্যাক '0.0085' — কোনো settings-field নেই; .env.example L511 STRIPE_SECRET_KEY ডকুমেন্ট করে কিন্তু config_secrets.py L682 পড়ে STRIPE_API_KEY → ডকুমেন্টেড-সেটআপ নীরবে Stripe নিষ্ক্রিয় করে; SSLCommerz রেল structurally মৃত (settings-এ sslcommerz_* ফিল্ডই নেই)"
  - "দ্বৈত-ব্যালেন্স-বাস্তবতা: TokenDeductor (core/llm/token_deductor.py) Redis user_balance:{id} ডেবিট করে যা কেউ ফান্ড করে না — SQL user_wallets-এর সমান্তরাল অপ্রতিসম ব্যবস্থা; deduct_tokens শূন্য production কলার অথচ billing_api.py L26-এ import-path-এ instantiation"
  - "৩য়-পক্ষ গবেষণা-ভিত্তি (2026-02-17 ওয়েব-প্রমাণ): LiteLLM spend-tracking + custom model cost map (docs.litellm.ai — JSON model→per-token-rate ম্যাপ, max_budget crossing-এ fail, spend reset duration); OpenMeter (github.com/openmeterio, Apache-2.0 — event-metering); Stripe metered billing idempotency (usage-record key 24h এক্সপায়ারি); OpenTelemetry GenAI semantic conventions (opentelemetry.io, 2026-05-14 — স্ট্যান্ডার্ডাইজড token/cost metrics)"
implements:
  - "মিটার-ফার্স্ট মতবাদ (শিল্পের অন্তর্দৃষ্টি): মিটারিং (event-append) ও চার্জিং (ledger) আলাদা স্তর — আমাদের লুপ ভাঙার মূল কারণই এই দুটোর অভিন্ন-অনুমান; এক-লাইন async record_spend-ফিডেই মিটারিং পুনরুজ্জীবিত"
  - "telemetry-লুপ বন্ধকরণ (P-A): LLM completion-পরবর্তী record_spend ফিড — analytics + WS সাথে সাথে বাস্তব-খরচ দেখাবে যা তারা ইতিমধ্যে পড়ে; শূন্য নতুন অবকাঠামো, hot-path-বাইরে"
  - "মূল্য-একক-উৎস (P-C): pricing_tiers.json বিস্তার (stripe_price_id/features/signup_bonus) + LiteLLM-প্যাটার্ন model_prices.json (মডেল→per-token rate) — সব মূল্য/সীমা ডেটা-ফাইলে, plans হবে derived-view (extend-not-replace)"
  - "চুক্তি-সংশোধন (P-D): frontend ৩ ভাঙা পাথ সংশোধন — শূন্য backend-পরিবর্তনে বিলিং-পেজ/realtime/usage জীবন্ত"
  - "env-সত্য-সংশোধন (P-E): STRIPE_API_KEY/.env.example সারিবদ্ধ; SSLCommerz বাস্তব config-ফিল্ড বা সৎ-মৃত-লেবেল; BDT_EXCHANGE_RATE বাস্তব ফিল্ড"
  - "প্রত্যাখ্যান-নথি (anti-cargo-cult): OpenMeter self-host সার্ভিস নয় (512MB), Stripe Metering-পেইড-ফিচার নয়, SaaS-মিটারিং-ভেন্ডর নয় — প্যাটার্ন-ই যথেষ্ট"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (branch crown-jewel-v2 base 41fd9181: billing_api পূর্ণ-কাঠামো-পাঠ, payments.py L124-135, realtime_dashboard L264-292, cost_guard L32-36/L59-63/L113/L155, pricing_tiers.json, .env.example L511 vs config_secrets.py L682, scripts-billing grep, BillingPage/CostDashboard পাথ-যাচাই; ৩য়-পক্ষ দাবি 2026-02-17 ওয়েব-সার্চে তারিখ-চিহ্নিত)"
code_evidence:
  - "পাঠক-জীবিত-লেখক-মৃত — realtime ড্যাশবোর্ড ও analytics সৎভাবে শূন্য দেখায় কারণ record_spend কেউ ডাকে না; V5 fake-metrics মতবাদ সংগত (কোনো জাল সংখ্যা নেই) কিন্তু ভাঙা-লুপ নিজেই এক ধরনের সত্য-ব্যর্থতা: ব্যবহারকারী খরচ দেখবেই না"
  - "রেভিনিউ-লিক-ট্র্যাপ — payments.py webhook নিজেই critical-log-এ বলে এটি কিছু প্রসেস করে না; দুটি checkout দুটি webhook মানে দুটি বিশ্বাস-উৎস — Stripe প্রতিটিতে ইভেন্ট পাঠাতে পারে; একটিই ক্যানোনিকাল হওয়া উচিত (ERR-F02 shim-প্যাটার্ন ইতিমধ্যে core/billing_plans.py-এ প্রতিষ্ঠিত)"
  - "ডকুমেন্টেড-সেটআপ-নীরব-ব্যর্থ — .env.example STRIPE_SECRET_KEY লিখে দেয় কিন্তু কোড পড়ে STRIPE_API_KEY: ফাউন্ডার সঠিকভাবে key সেট করলেও Stripe নিষ্ক্রিয় থাকবে এবং checkout fail-closed 503 দেবে — কারণ-গোপন ব্যর্থতা; এক-নাম-সারিবদ্ধকরণেই সমাধান"
  - "zero-cost-সংবিধান-টেস্টেড — test_billing_zero_cost.py দাবি করে: ফ্রি-টিয়ার $0.00-তে বিদ্যমান, ফ্রি-টিয়ার record_usage Stripe-ছাড়া $0 বিল, Stripe অনুপস্থিতিতে কখনো ক্র্যাশ নয় — এই নীলনকশার সব প্রস্তাব এই অক্ষ-রেখা সংরক্ষণ করে"
  - "মিটার-ফার্স্ট-অন্তর্দৃষ্টি — OpenMeter/LiteLLM উভয়েই মিটারিংকে চার্জিং থেকে আলাদা স্তর রাখে; আমাদের wallet/ledger বাস্তব কিন্তু মিটার শূন্য — চার্জিং-পথ (idempotent, হার্ডেনড) দারুণ, মিটারিং-পথ এক-ফিড-দূরে"
test_evidence: "বিদ্যমান: test_billing_api_routes.py 445L (wallet bootstrap/bonus, 402/422, add-funds validation, সব-env 503, দুই-webhook credit-exactly-once, analytics aggregate) + test_billing_zero_cost.py + স্ক্রিপ্ট-ত্রয়ী (409/310/210L) ≈ ১,৮৪৭ টেস্ট-লাইন; অনটেস্টেড-লাইভ: /payments/*, /ws/cost-updates, /admin-api/costs GET side-effect; প্রস্তাব-টেস্ট: record_spend-ফিড ইন্টিগ্রেশন, pricing-parity (কোড↔json), frontend-পাথ চুক্তি-টেস্ট"
acceptance_criteria:
  - "প্রতিটি প্রস্তাব চার-স্তম্ভ-দর্শন-সংগত (Part 5.5)"
  - "zero-cost সংবিধান অটুট: ফ্রি-রেল কখনো চার্জ করবে না, পেইড-রেল env-gated-ঐচ্ছিক — test_billing_zero_cost অপরিবর্তিত পাস"
  - "সব মূল্য/সীমা/থ্রেশহোল্ড ডেটা-ফাইল+env (P-C/P-F); কোনো hot-path latency-যোগ নয় (P-A async); extend-not-replace (shim)"
  - "লিন্ট-শৃঙ্খলা: lint_plans.py 0 error / 0 warning (সিরিজ); কোনো নতুন CI-গেট এই ডকে তৈরি হয় না (P-G শুধু ফাউন্ডার-গেটেড প্রস্তাব)"
---

# Module 16 — Billing & Metering Gateway Power-Up (বিলিং-মিটারিং গেটওয়ে)

## বাংলা সারসংক্ষেপ

বিলিং-অঙ্গ এক বিস্ময়কর দ্বৈততা বহন করে: **চার্জিং-পথ প্রকল্পের সেরা-হার্ডেনড কোড** (fail-closed Stripe, idempotent ওয়েবহুক, optimistic-concurrency wallet) — আবার **মিটারিং-পথ সম্পূর্ণ বিচ্ছিন্ন**: ড্যাশবোর্ড ও WS সৎভাবে শূন্য দেখায় কারণ `record_spend`-কে কেউ ডাকেই না। শিল্পের মূল-সূত্র (OpenMeter/LiteLLM) — **মিটার আগে, বিল পরে**; আমাদের এখানে বিল-অর্ধেক নিখুঁত, মিটার-অর্ধেক এক-ফিড-দূরে। এই নীলনকশার কেন্দ্র: (১) **এক-লাইনে লুপ বন্ধ** (P-A) — completion-পরবর্তী async ফিডেই realtime-খরচ জীবন্ত; (২) **রেভিনিউ-লিক-ট্র্যাপ বন্ধ** (P-B) — payments.py-এর self-admitted-মৃত webhook shim-এ; (৩) **মূল্যের একক-উৎস** (P-C) — LiteLLM-প্যাটার্নে pricing_tiers.json বিস্তার + model_prices.json; (৪) **frontend ৩ চুক্তি-ভাঙা সংশোধন** (P-D) — শূন্য backend-পরিবর্তনে ব্যবহারকারী-মুখী সত্য; (৫) **ডকুমেন্টেড-সেটআপ-নীরব-ব্যর্থ সংশোধন** (P-E) — STRIPE_SECRET_KEY বনাম STRIPE_API_KEY-এর এক-নাম-অমিল ফাউন্ডারের সঠিক সেটআপকেই নিষ্ক্রিয় করে রাখে। zero-cost সংবিধান (test_billing_zero_cost) অটুট থাকবে।

## Part 1 — Third-Party & Competitor Intelligence (৩য়-পক্ষ বুদ্ধিমত্তা, তারিখ-চিহ্নিত ওয়েব-প্রমাণ)

### ১.১ গ্রহণযোগ্য প্যাটার্ন (গ্রহণ — প্যাটার্ন হিসেবে, নির্ভরতা নয়)

| উৎস (তারিখ) | ধারণা | আমাদের অঙ্গে প্রয়োগ | চার-স্তম্ভ-বিচার |
|---|---|---|---|
| **LiteLLM custom model cost map** (docs.litellm.ai) | JSON ফাইলে model→per-token-rate + context-limit — প্রতি-রিকোয়েস্ট মূল্য ডেটা-থেকে | `model_prices.json` ডেটা-ফাইল (P-C): LLM Gateway-এর per-model হার ইন-কোড নয়; নতুন-মডেল = ডেটা-এডিট | zero-cost ✓; zero-hardcode ✓✓ |
| **LiteLLM budgets** (docs.litellm.ai/proxy/users) | max_budget per key/user/team; crossing-এ fail; spend-reset duration | cost_guard-এর tier_limits 0.0/0.02/0.50 → ডেটা-ফাইল + reset-window env (P-F); per-key attribution প্যাটার্ন | ডেটা-চালিত ✓ |
| **OpenMeter** (github.com/openmeterio, Apache-2.0) | metering ≠ billing: event-append → aggregate → usage-based | মিটার-ফার্স্ট স্তর-বিভাজনের স্থাপত্য-প্রমাণ; আমাদের রেডিস-INCRBYFLOAT-ই সরলীকৃত ইভেন্ট-মিটার (P-A); ইভেন্ট-idempotency-ধারণা প্রযোজ্য | সার্ভিস-প্রত্যাখ্যান (infra), প্যাটার্ন-গ্রহণ ✓ |
| **Stripe metered billing** (docs.stripe.com) | usage-record idempotency-key 24h-এক্সপায়ারি; increment-vs-set সিমান্টিকস | বিদ্যমান ledger-pre-check প্যাটার্নের অপারেশনাল-নোট: ২৪ঘণ্টা-পরে-রিট্রাই সচেতনতা অপস-ডকে (P-G-র রানবুক-অংশ) | জ্ঞান-ধার, খরচ-শূন্য ✓ |
| **OpenTelemetry GenAI conventions** (opentelemetry.io, 2026-05-14) | স্ট্যান্ডার্ডাইজড gen_ai.* token/cost metric-নামকরণ | ভবিষ্যৎ-নিরাপদ টেলিমেট্রি-কী-নামকরণ (cost_guard ফিড-ফরম্যাটে gen_ai.*-উপসর্গ-সংগত) — ভবিষ্যৎ-ড্যাশবোর্ড-সংগতি | zero-cost নামকরণ-ধার ✓ |

### ১.২ প্রত্যাখৃত বিকল্প (কারণ-সহ)

| বিকল্প | কেন নয় |
|---|---|
| **OpenMeter self-host** | অতিরিক্ত সার্ভিস (512MB ফ্রি-টিয়ার-লঙ্ঘন); আমাদের রেডিস-কাউন্টার-প্যাটার্ন বর্তমান-স্কেলে যথেষ্ট — স্থাপত্য এমনভাবে রাখা হবে যেন ভবিষ্যৎ-আদান-প্রত্যাদান সহজ |
| **Stripe Metering/Meters API-গভীর-আদান** | পেইড-বিভাগ-ঝুঁকি + vendor-lock; আমাদের বিদ্যমান idempotent-ledger মূল-চাহিদা মেটায় |
| **SaaS মিটারিং-ভেন্ডর (Metronome/Amberflo জাতীয়)** | zero-cost স্তম্ভ-লঙ্ঘন; ফ্রি-টিয়ার-প্রথম প্রকল্পে অপ্রাসঙ্গিক |
| **মিটার-স্টোরেজে DB-বিস্তার (per-request সারি)** | হট-পাথ DB-লেখা = fast-smooth লঙ্ঘন; রেডিস-কাউন্টার + বিদ্যমান runs/service Postgres-মিটার (Module 06) যথেষ্ট |

### ১.৩ প্রতিযোগী-তুলনার অন্তর্দৃষ্টি (ভিন্নভাবে ভাবা)

শিল্প "usage-based billing"-এর দিকে গড়ায় কারণ ব্যবহারকারী ন্যায্যতা দেখতে চায়। আমাদের ভিন্ন-সুবিধা: **zero-cost সংবিধান** — ফ্রি-রেল চিরন্তন। তাই প্রতিযোগীদের মত বিল-উৎপাদন-রেস নয়; আমাদের লক্ষ্য **খরচ-স্বচ্ছতা**: ব্যবহারকারী/অ্যাডমিন বাস্তব-টোকেন-খরচ দেখবে (P-A), BYOC-ব্যবহারকারী নিজের-কী-এর খরচ দেখবে — "আমরা আপনার জন্য কত খরচ করছি" আস্থা-স্তম্ভ। বিল-মেটার নয়, **আস্থা-মিটার** — এটাই ভিন্ন-পথ।

## Part 1.5 — Gate 0 Reconciliation

| লেগেসি-ডক | স্ট্যাটাস | সিদ্ধান্ত |
|---|---|---|
| docs/plans/features/Plan_10_API_Limit_Discovery.md | historical | সীমা-আবিষ্কার-দাবি ইতোমধ্যে বাস্তবায়ন-বহি; বিরোধ নেই |
| docs/plans/features/free_tier_federation_master_plan.1... | active | ফ্রি-টিয়ার-ফেডারেশন এই মডিউলের ফ্রি-রেল-অটুট-শর্তের সহিত; পরিপূরক |
| docs/plans/features/free_tier_scaling_constitution_and_compliance_policy.md | active | সংবিধান-স্তরের নথি; P-A…P-H এর চেয়ে কঠোর কিছু প্রস্তাব করে না — সংগত |
| billing-gateway-সমর্পিত-প্ল্যান | অনুপস্থিত | **greenfield** — docs/plans-এ কোনো billing-গেটওয়ে প্ল্যান নেই; এই নীলনকশাই প্রথম |
| Module 14 (p2p/credit_system) | published | boundary: p2p স্টাব-রায় দাঁড়ায় — পুনঃ-অডিট নয় |
| Module 13/15 (rate limiters) | published | boundary: rate_limit_quota.py-র বিলিং-মাত্রাই এখানে; লিমিটার-পাইপলাইন সেখানেই |
| Module 03 (LLM Gateway) | published | boundary: completion.py-র ভিতর-অডিট নয়; শুধু record_spend-ফিড-পয়েন্ট প্রস্তাব |

## Part 2 — Six-Field Analysis

### ২.১ কী আছে

- **ক্যানোনিকাল-লাইভ billing_api.py**: ৯ রুট, is_critical fail-fast; Stripe fail-closed (ERR-G01); idempotent ওয়েবহুক + FOR UPDATE; optimistic-concurrency wallet — চার্জিং-অর্ধেক শিল্প-গ্রেড
- **enforcement জীবিত**: cost_guard pre-flight LLM+tool-দুই-গেটে; budget-refusal admission runs-এ
- **পাঠক-তন্ত্র জীবিত**: analytics + /ws/cost-updates সৎ-সমষ্টি (কোনো ফেব্রিকেশন নেই)
- **শুদ্ধ-প্যাটার্ন উপস্থিত**: deprecated-shim (core/billing_plans→services), pricing_tiers.json + byoc_limits.json ডেটা-ফাইল, zero-cost সংবিধান-টেস্ট, স্ক্রিপ্ট-ত্রয়ীর চমৎকার টেস্ট (≈১,৮৪৭ লাইন)

### ২.২ কী নেই

- **মিটারিং-লেখক** — record_spend শূন্য-কলার; ড্যাশবোর্ড-স্থায়ী-$০
- **একক-চেকআউট** — payments.py ট্র্যাপ-ডুপ্লিকেট (self-admitted revenue leak)
- **মূল্য-একক-উৎস** — কোড-মূল্য 0/9.99/199.99 বনাম json-ক্রেডিট 0/10/100; ডুপ্লিকেট signup-bonus; কোনো model-price ডেটা-ফাইল নেই
- **frontend-সংযোগ** — ৩ চুক্তি-ভাঙা (plans-পাথ, WS-পাথ, /usage-403) + মৃত token-গণিত
- **env-সত্য** — STRIPE key-নাম-অমিল; SSLCommerz ফিল্ড-শূন্য; BDT-হার অনন্যোগ্য
- **cron-বাস্তবতা** — স্ক্রিপ্ট-ত্রয়ী কোনো workflow-এ নেই; fraud_detector এমন সারি স্ক্যান করে যা লেখা হয় না
- **gate-বাস্তবতা** — প্ল্যান-মেটাডেটা প্রদর্শনী-মাত্র; price_id লিটারেল

### ২.৩ কী করতে হবে

আটটি প্রস্তাব (ক্রম সস্তা→গভীর; সব ফাউন্ডার-রিভিউযোগ্য):

- **P-A (Gateway BudgetReservation ও UsageSettlement ওয়্যারিং)**: 
  - Module 03 LLM Gateway-র সাথে দ্বি-মুখী সংযোগ: প্রি-কল লেভেলে `BudgetReservation` লিজ (৬০ সেকেন্ড TTL) দিয়ে ব্যালেন্স হোল্ড করা, এবং পোস্ট-কল `UsageSettlement`-এ প্রকৃত টোকেন খরচ অনুযায়ী ওয়ালেট ডেবিট ও অবশিষ্ট লিজ রিলিজ করা।
  - কনকারেন্সি রেস ও ডাবল-স্পেন্ডিং প্রতিরোধে অ্যাটমিক রেডিস মিউটেক্স ও ডাটাবেজ অপটিমিস্টিক লকিং (`FOR UPDATE` / version check) নিশ্চিত করা।
  - এসিঙ্ক `record_spend` ফিড — analytics+WS সাথে-সাথে বাস্তব; ড্যাশবোর্ড স্থায়ী-$০ সমস্যা দূর।
- **P-D (ডুয়াল-ড্রাইভেন বিলিং ড্যাশবোর্ড ও Frontend সংশোধন)**: 
  - `AGENTS.md Rule 7` অনুসারে ডুয়াল বিলিং ভিউ:
    - *Customer View:* বর্তমান ওয়ালেট ক্রেডিট, স্বচ্ছ প্রতি-রান খরচ (টোকেন ও সেন্টে), ইনভয়েস হিস্ট্রি ও সহজ টপ-আপ অপশন।
    - *Admin View:* প্ল্যাটফর্ম-ব্যাপী মার্জিন অ্যানালিটিক্স, প্রোভাইডার-ভিত্তিক গ্রস খরচ বনাম কাস্টমার বিলিং, টোকেন ভেলোসিটি ও ফ্রড ডিটেকশন প্যানেল।
  - plans-পাথ (বাস্তব `/api/billing/plans` + array-রূপান্তর), WS → `/ws/cost-updates`, মৃত token-গণিত অপসারণ।
- **P-B**: payments.py → deprecation-shim (billing_plans-শিম-প্যাটার্নে); ট্র্যাপ-webhook নিষ্ক্রিয়; billing_api ক্যানোনিকাল
- **P-C**: মূল্য-একক-উৎস — pricing_tiers.json বিস্তার (stripe_price_id/features/signup_bonus) + model_prices.json (LiteLLM-প্যাটার্ন); SUBSCRIPTION_PLANS derived-view; কোড-মূল্য-লিটারেল অবসান; signup-bonus-দ্বৈততা অবসান
- **P-E**: env-সত্য — STRIPE_API_KEY/.env.example সারিবদ্ধ; SSLCOMMERZ_* বাস্তব ফিল্ড বা সৎ-মৃত-লেবেল+অপসারণ-প্রস্তাব; BDT_EXCHANGE_RATE বাস্তব ফিল্ড
- **P-F**: rails-as-data বিলিং-সুইপ (Module 15 P-B প্রেসিডেন্ট) — billing_tiers/thresholds/admin-কোটা ডেটা-ফাইলে; tenant_rate_limiter-এর dual fail-mode → env-aware (V5.1)
- **P-H**: TokenDeductor wire-or-mothball (ফাউন্ডার-সিদ্ধান্ত) — দ্বৈত-ব্যালেন্স অবসান-পথ; এতদ্বীনে billing_api import-path থেকে মৃত-instantiation অপসারণ
- **P-G**: ফাউন্ডার-গেটেড report-only cron-প্রস্তাব — nightly fraud_detector + weekly quota_enforcer --dry-run + monthly usage_reporter (scheduled-deep-audit-প্যাটার্ন); multicloud NameError-ফিক্স; এই ডক কোনো workflow তৈরি করে না

### ২.৪ কীভাবে করব

ক্রম P-A→P-D→P-B→P-C→P-E→P-F→P-H→P-G; প্রতিটি P = আলাদা ছোট execution-প্ল্যান (Gate 2-পরবর্তী); P-A-তে টেস্ট-প্রথম (ফিড-ইন্টিগ্রেশন + ফ্রি-টিয়ার-অপরিবর্তিত — test_billing_zero_cost পুনঃচালন + কনকারেন্ট ১০০ কল ডাবল-স্পেন্ড টেস্ট); P-C-তে parity-টেস্ট (কোড↔json অভিন্ন-ফল) + dual-read স্থানান্তর; P-B-তে shim+deprecation-নোট (ERR-F02); P-F-এ baseline-N র‍্যাচেট; সব env-নাম V5.1-সংগত

### ২.৫ বেনিফিট

- ব্যবহারকারী/অ্যাডমিন প্রথমবার বাস্তব-খরচ দেখবে — আস্থা-মিটার জীবন্ত
- রেস কন্ডিশন ও ডাবল-স্পেন্ডিং মুক্ত নিখুঁত ওয়ালেট ব্যালেন্স (P-A)
- ডুয়াল-ড্রাইভেন স্বচ্ছতা: কাস্টমার দেখে সরল খরচ, অ্যাডমিন দেখে লাভ-ক্ষতির পূর্ণ ব্যালেন্সশিট (P-D)
- রেভিনিউ-লিক-ঝুঁকি-স্থায়ী-অবসান (ট্র্যাপ-webhook shim-এ)
- মূল্য-পরিবর্তন = ডেটা-এডিট (ডিপ্লয়-মুক্ত) — zero-hardcode পূর্ণতা
- ফাউন্ডারের সঠিক সেটআপ আর নীরবে নিষ্ক্রিয় হবে না (P-E)
- স্ক্রিপ্ট-বিনিয়োগ (৯২৯ টেস্ট-লাইন) অবশেষে নির্ধারিত-বাস্তবতায় (P-G গ্রহণ হলে)

### ২.৬ ক্ষতি/ঝুঁকি

- P-A-তে ফিড-ভুল (অতি-গণনা) → idempotency-কী (request-id) + ফ্রি-টিয়ার $0-অপরিবর্তিত + টেস্ট-প্রথম
- P-C-তে মূল্য-স্থানান্তর-ভুল → parity-টেস্ট + dual-read + রোলব্যাক-এক-ফাইল
- P-B-তে বহিরাগত-ওয়েবহুক-অনুষদ → shim-পিরিয়ডে উভয়-পথ-লগ + Stripe-ড্যাশবোর্ড-এন্ডপয়েন্ট-সংশোধন-নোট
- P-D-তে WS-অথ-বিস্মৃতি → প্রথম-বার্তা-অথ-প্যাটার্ন টেস্টেড
- cron-প্রস্তাব (P-G) গ্রহণে CI-খরচ → report-only, warn-প্রথম (zero-false-positive পূর্বশর্ত)

## Part 3 — Out of Scope

- p2p/credit_system পুনঃ-অডিট (Module 14); rate-limiter-পাইপলাইন (Module 13/15)
- LLM Gateway-অভ্যন্তর (Module 03); runs-মিটার (Module 06)
- নতুন পেইড-গেটওয়ে/vendor-আদান; Stripe-account-বাস্তবায়ন (env-স্তরের বিষয়)
- কোনো workflow-ফাইল তৈরি (P-G শুধু প্রস্তাব)
- বিলিং-UI-রিডিজাইন (শুধু চুক্তি-সংশোধন)

## Part 4 — ৯-নিয়ম ও Constitution-সংগতি

| নিয়ম | এই নীলনকশার অবস্থান |
|---|---|
| Single-plan execution | প্রস্তাব-পাইপলাইন; একসময়ে একটিই active (P-A প্রথম) |
| Evidence-first | file:line প্রমাণ; ৩য়-পক্ষ তারিখ-চিহ্নিত |
| Extend-not-replace | P-B shim; P-C derived-view; ERR-F02 |
| Founder gates | enforcement/রেল-সিদ্ধান্ত (P-H, SSLCommerz-নিয়তি) Gate 2-পরবর্তী |
| Zero-false-positive | P-G report-only→প্রমাণ→গেট |
| Zero-cost সংবিধান | test_billing_zero_cost অটুট-শর্ত সর্বোচ্চ |
| Branch discipline | docs-only; execution আলাদা ব্রাঞ্চ+PR |

## Part 5 — Verification & Rollback

- **Gate 4 (proof)**: P-A ফিড-ইন্টিগ্রেশন-টেস্ট + test_billing_zero_cost পুনঃপাস; P-C parity-টেস্ট; P-D পাথ-চুক্তি-টেস্ট (openapi-বনাম-কল মিল); P-B দুই-webhook-credit-exactly-once পুনঃপাস
- **Gate 5 (measurement)**: ড্যাশবোর্ড-খরচ≠$০ (প্রথম-বাস্তব-মান); analytics-সমষ্টি=রেডিস-যোগফল নিয়মিত-যাচাই; মূল্য-উৎস-ফাইল-কাউন্ট (কোড-লিটারেল→০)
- **Gate 6 (rollback)**: P-A kill-switch env; P-C dual-read-রোলব্যাক; P-B shim-পুনঃসক্রিয়; P-D প্রতি-ফিক্স-এক-কমিট

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Audit)

| প্রস্তাব | Zero Cost | Lightweight | Fast Smooth | Zero Hardcode |
|---|---|---|---|---|
| P-A লুপ-বন্ধ | ✓ শূন্য-নতুন-অবকাঠামো | ✓ এক-ফিড | ✓ async hot-path-বাইরে | ✓ |
| P-D frontend-সত্য | ✓ | ✓ | ✓ | n/a |
| P-B ট্র্যাপ-shim | ✓ | ✓ কম-কোড | ✓ | n/a |
| P-C মূল্য-একক-উৎস | ✓ | ✓ json-লোড | ✓ | ✓✓ মূল-উদ্দেশ্য |
| P-E env-সত্য | ✓ | ✓ | ✓ | ✓ env-চালিত |
| P-F rails-as-data সুইপ | ✓ | ✓ | ✓ | ✓✓ |
| P-H TokenDeductor সিদ্ধান্ত | ✓ দ্বৈত-অবসান | ✓ | ✓ import-path হালকা | n/a |
| P-G cron-প্রস্তাব | ✓ ওপেন-সোর্স-পাইথন | ✓ report-only | ✓ nightly-বাইরে | ✓ |
| OpenMeter/ভেন্ডর প্রত্যাখ্যান | ✓✓ | ✓✓ | ✓ | n/a |

**জন্মগত-সংগতি-ঘোষণা**: zero-cost সংবিধান (ফ্রি-রেল-চিরন্তন) সর্বোচ্চ-শর্ত; মিটার-ফার্স্ট স্তর-বিভাজন শিল্প-প্যাটার্নে কিন্তু সরলীকৃত-রেডিস-বাস্তবায়নে; প্রত্যাখ্যান-সব-কারণ-নথিভুক্ত।

## Part 6 — পরবর্তী মডিউল লাইনেজ

- **চক্র ১৭-প্রার্থী**: HITL/Approval চেইন (backend/services/hitl/ + approval_manager — cryptographic_ledger ব্যবহৃত, কিন্তু approval_manager নিজস্ব `_audit`-ইনলাইন) — ৩য়-পক্ষ-প্রস্তুতি: LangGraph interrupt-প্যাটার্ন, Humanloop-স্টাইল review-loop, event-sourcing approval-লগ (প্যাটার্ন-হিসেবে)
- **চক্র ১৮-প্রার্থী**: simulated-class governance (মক-ক্লাস-পরিষ্কারক-স্ক্রিপ্ট, zero-false-positive পূর্বশর্তে) বা notification/delivery-অঙ্গ (email_agent পরিবার)
- কিউ-পুনঃর‍্যাঙ্ক: Gate 5-পরিমাপে; প্রতিটি চক্র ৩য়-পক্ষ-গবেষণা-চুক্তি বহাল
