---
id: crown-jewel-module-18-telegram-organ-power-up-2026-09-17
title: "Crown Jewel Module Series — Module 18: Telegram Integration Organ Power-Up (টেলিগ্রাম-অঙ্গ: প্রোডাকশনে বধির বট, হার্ডকোডেড-ও-মুদ্রিত admin chat_id, secret-বিহীন spoofable webhook — activation-gate মতবাদে পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Governance Circle (backend/tools/social/telegram_bot/ + telegram_security.py — ব্যবহারকারী-মুখী মেসেজিং অঙ্গ)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ১৮ — একটি মডিউল (টেলিগ্রাম-ইন্টিগ্রেশন অঙ্গ), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field); Part 1 = গভীর ৩য়-পক্ষ বুদ্ধিমত্তা (Telegram Bot API সরকারি semantics: setWebhook secret_token, flood limits, webhook retry-then-drop; aiogram/grammY shape-ধার); branch crown-jewel-v2 base 5cfbbc06-এ spot-checkকৃত কোড-প্রমাণ"
depends_on:
  - "অঙ্গ-আকার: ১৩ ফাইল — handler.py ৩৩০ (COMMANDS L37-87, token bootstrap L89-103, is_admin L307-314), updates.py ৩০৬ (৫-ধাপ dispatcher: callbacks → AutonoGuard-injection guard L150-164 → TOTP L166-181 → critical interceptor L183-205 → commands L207-301 → AI L303-306), keyboards.py ১১৮, conversations.py ৩১৬, admin_handlers.py ২০৯ (/backup_now বাস্তব L191-209), user_handlers.py ১২৪, ai_engine.py ৯৫ (Gemini→Groq সরাসরি-HTTP ফলব্যাক-চেইন; orchestrator-ফলব্যাক মৃত L79-93), runtime.py ৭৪ (run_polling L21-56 কেবল __main__; start_webhook L58-74 শূন্য-কলার), telegram_security.py ২৭০ (singleton L270), router.py ৫১ (routers.py L240-244 মাউন্টেড /api/v1/telegram/*, is_admin: False)"
  - "বধির-বট-বাস্তবতা: প্রোডাকশন-ইনগ্রেস = কেবল webhook, এবং নিষ্ক্রিয় — setWebhook/start_webhook/sync_bot_profile-এর কোনো অ্যাপ-কলার নেই (app.py/app_builder/startup শূন্য); polling বাস্তবায়িত কিন্তু কখনো শুরু হয় না (কেবল `python -m` manual) — যাঁরা __init__.py L13-15-এর manual curl নির্দেশনা মানবেন, তখনই spoofable endpoint জাগ্রত হবে"
  - "সবচেয়ে গুরুতর: রেপো-ব্যাপী কোথাও X-Telegram-Bot-Api-Secret-Token যাচাই নেই (grep-শূন্য) যখন auth_middleware.py L129-134 স্পষ্টতই এন্ডপয়েন্টটিকে allowlist করে → জাল update = admin-অনুকরণ; admin-গেট = env ADMIN_TELEGRAM_CHAT_ID বা TELEGRAM_CHAT_ID বা হার্ডকোডেড '7804133572' — এবং হার্ডকোডটি দ্বিতীয়বারও চেক করা হয় (handler.py L312,314) ফলে env দিয়েও প্রত্যাহার অসম্ভব, আর ID-টি security-panel-এ মুদ্রিত (admin_handlers.py L154); গ্রুপ-চ্যাটে chat_id ≠ from.id → যে-কোনো সদস্য admin-গেট পেরোন্যাস"
  - "বাস্তব-সম্পদ নিচে চাপা: RFC 6238 TOTP (constant-time, ±1 drift, challenge TTL 300s, ৩-প্রয়াস, 600s lockout — telegram_security L30-58,L163-227); TelDrive AES-256(Fernet)+gzip → Telegram-cloud ব্যাকআপ (L191-209); MCP client list/approve/role বাস্তব-HTTP bearer-key-সহ (conversations L23-96)"
  - "fabricated-পৃষ্ঠ (V6-মতবাদ-লঙ্ঘন): /telemetry '38ms/142 Tasks/99.99% Uptime' হার্ডকোডেড (`handler.py` L63-67 — প্রমাণ-মার্কার); quick_self_healer '100% HEALTHY (0 active errors)', quick_audit '105/105 Passing' (`conversations.py` L122-129, L162-170 — প্রমাণ-মার্কার); TOTP-পরবর্তী executor-এর 'Task logged in System Audit Trail' — এমন audit trail নেই-ই (`conversations.py` L313-316 — প্রমাণ-মার্কার)"
  - "স্মৃতি-শূন্য: _ai_response এক-শট-স্টেটলেস (ai_engine L21-95, docstring 'persist chat memory' দাবি মিথ্যা); /session মেনু echo-মাত্র (updates L47-59); একমাত্র স্টেটফুল স্টোর security_guard-এর in-memory dict — restart-হারায়, key-অসীম-বৃদ্ধি, single-worker"
  - "৪টি প্রতিদ্বন্দ্বী handler-instance: telegram_bot নিজে + teldrive_storage L66-67 + mcp_telegram L27-31 + core/messaging/adapters L37-45 (নিজস্ব নিজস্ব instance); task_processor_interface কন্সট্রাক্টর-আর্গ কখনো পাস হয় না → processor সর্বদা None; রেজিস্ট্রি-নোট: core/plugins/official/telegram_plugin.py deprecated-shim → experimental stub NotImplementedError"
  - "transport-স্বাস্থ্য: 429/retry_after কখনো হ্যান্ডল নয় → বন্যায় বার্তা নীরবে-হারায়; 4096-char cap নেই; রাউটার fire-and-forget (router L37-39) — 200 আগে, processing পরে; malformed JSON → 500 (router L36); polling-এ 401-সহ যেকোনো ত্রুটিতে অসীম 2s-রিট্রাই-লুপ (runtime L54-56); ব্যবহারকারীর পূর্ণ বার্তা-টেক্সট INFO-তে লগ (updates L148,155-157) — privacy"
  - "৩য়-পক্ষ গবেষণা-ভিত্তি (2026-02-17 ওয়েব-প্রমাণ): core.telegram.org — setWebhook secret_token → 'X-Telegram-Bot-Api-Secret-Token' header, 1-256 chars [A-Za-z0-9_-]; flood limits ~30 msg/s global, ~1/s প্রতি-chat, ~20/min প্রতি-group, 429+retry_after (grammY 2024-11-02, botnamefinder); webhook-ব্যর্থতায় exponential-backoff রিট্রাই, কতিঘণ্টা-পরে ড্রপ (airbyte 2026-01-15); aiogram 3.31 / grammY কেবল shape-ধার"
implements:
  - "activation-gate মতবাদ (অস্বাভাবিক-চিন্তার কেন্দ্র): বর্তমান সুরক্ষা দুর্ঘটনাক্রমে বধিরতা; যেদিন webhook নিবন্ধিত হবে সেদিনের আগেই secret-যাচাই-বাধ্যতামূলক — সক্রিয়করণ ও সুরক্ষা এক-গেটে জোড়া (founder-gated)"
  - "P-A webhook secret-token যাচাই (সরকারি 1-256 charset) + TELEGRAM_WEBHOOK_SECRET config-field — সব admin-বাহকের পূর্বশর্ত"
  - "P-B admin-পরিচয়-সত্য: হার্ডকোডেড chat_id দ্বৈত-চেক অবসান + মুদ্রণ অবসান — env/vault-শুধু; গ্রুপ-বাস্তবতায় from.id-যাচাই"
  - "P-C telemetry-সত্য: জাল KPI → বাস্তব health_checker/cost-reporter পাঠ বা 'not measured' (V6 fake-event মতবাদ, test_billing_zero_cost-ঘরানা)"
  - "P-D security_guard স্বাস্থ্য: TTL sweep + বাউন্ডেড-dict (B-11 প্যাটার্ন) — restart-survivability ঐচ্ছিক pending_tasks-প্যাটার্নে"
  - "P-E Module-17 HITL-বাহক (P-A-gated): admin_handlers-এ এক-হ্যান্ডলার + updates callback-শাখা — resume-URL/inline-keyboard অনুমোদন"
  - "P-F transport-স্বাস্থ্য: 429 retry_after + 4096 chunking + শেয়ার্ড AsyncClient + ৪→১ handler-instance (lazy provider) — fd-churn ও latency হ্রাস"
  - "P-G orchestrator-সেতু-সত্য: বাস্তব processor-inject বা মৃত-ফলব্যাক+জাল-audit-লাইন অপসারণ; P-H বার্তা-ক্যাটালগ ডেটা-ফাইল (চক্র ১৯ i18n-সংগতি) + /session-সত্য"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (branch crown-jewel-v2 base 5cfbbc06: handler/updates/conversations/admin_handlers/runtime/ai_engine পূর্ণপাঠ, secret-token grep-শূন্য, auth_middleware L129-134, config_secrets L692-698, ৪-instance grep; ৩য়-পক্ষ দাবি 2026-02-17 ওয়েব-সার্চে তারিখ-চিহ্নিত core.telegram.org-প্রাথমিক)"
code_evidence:
  - "deaf-by-default-is-safe-by-accident — একমাত্র যা admin-spoofing ঠেকায় তা হলো কেউ webhook নিবন্ধন করেনি; ম্যানুয়াল-নিবন্ধন-নির্দেশনা (docstring L13-15) নিজেই এক সেটআপ-ফাঁদ: secret-যাচাই-ছাড়া নিবন্ধন = অবিশ্বস্ত-ইনগ্রেস-সহ admin-ক্ষমতা"
  - "TOTP-কেবল-টেক্সট — কঠোরতম যাচাই (TOTP) শুধু critical-টেক্সট-কমান্ডে; admin-বোতাম (vault/MCP approve/role) TOTP-বিহীন — যখন বোতামই সহজ-আক্রমণ-পৃষ্ঠ"
  - "privacy-নোট — ব্যবহারকারীর পূর্ণ-বার্তা INFO-লগ: LLM-সংলাপে ব্যক্তিগত-তথ্য লগ-ফাইলে স্থায়ী — রেডাকশন-প্রস্তাব P-C-সহগামী"
  - "এক-সেটআপ-ফাঁদ-প্রতিষেধক — activation-gate: webhook-নিবন্ধন-ফাংশন (set_webhook dormant) নিজেই secret-সেট+যাচাই-শর্তসাপেক্ষে জাগ্রত হবে — manual-curl-পথ docstring-সংশোধনে বন্ধ"
  - "ি18n-প্রস্তুতি — বার্তা EN+BN inline-মিশ্রিত; language-matching LLM-system-prompt-এ অর্পিত; ক্যাটালগ-প্যাটার্ন P-H চক্র ১৯-এর ভিত্তি-সারি"
test_evidence: "বিদ্যমান: test_telegram_bot.py 235L (config/sends/COMMANDS/paths) + v2 123L (callbacks, WebApp initData HMAC বাস্তব-বাস্ত্র) + mcp_telegram + teldrive ~600L; শূন্য-টেস্ট: is_admin authz/spoofing, injection/critical/TOTP-ফাংশন, polling happy-path, webhook HTTP-চুক্তি; প্রস্তাব-টেস্ট: secret-মিল/অমিল, admin-env-only, 429-রিট্রাই, chunk-4096, sweep-বাউন্ড"
acceptance_criteria:
  - "প্রতিটি প্রস্তাব চার-স্তম্ভ-দর্শন-সংগত (Part 5.5)"
  - "webhook-সক্রিয়করণ কখনো secret-যাচাই-বিহীন নয় (activation-gate); হার্ডকোডেড-পরিচয়/জাল-KPI অবশিষ্ট শূন্য"
  - "কোনো নতুন ভারী-নির্ভরতা নয় (httpx-শুধু বহাল; aiogram/grammY কেবল শেপ-ধার); মূল-অ্যাপ-স্টার্টআপে বট-ব্যর্থতা কখনো crash নয় (বিদ্যমান গুণ সংরক্ষণ)"
  - "সব TTL/সীমা/বার্তা ডেটা-ফাইল+env; লিন্ট 0 error / 0 warning (সিরিজ)"
---

# Module 18 — Telegram Integration Organ Power-Up (টেলিগ্রাম-অঙ্গ)

## বাংলা সারসংক্ষেপ

টেলিগ্রাম-অঙ্গ প্রকল্পের সবচেয়ে বিপরীতমুখী সত্য বহন করে: **প্রোডাকশনে বট বধির** — webhook কখনো নিবন্ধিত হয়নি, polling কখনো শুরু হয়নি; আর ঠিক এই বধিরতাই একমাত্র সুরক্ষা — কারণ webhook-এন্ডপয়েন্টে **secret-token যাচাই নেই** আর admin-গেট **হার্ডকোডেড-ও-মুদ্রিত chat_id**-তে। নিচে চাপা পড়ে আছে প্রকৃত সম্পদ: RFC 6238 TOTP (constant-time), TelDrive AES-256 ব্যাকআপ, MCP client-ব্যবস্থাপনা। মতবাদ: **activation-gate** — সক্রিয়করণ ও সুরক্ষা এক-গেটে জোড়া; webhook যেদিন জাগবে, সেদিন secret-যাচাই ইতোমধ্যে থাকবে। সাথে: জাল-KPI-সত্যায়ন (V6-মতবাদ), transport-স্বাস্থ্য (429/4096/শেয়ার্ড-ক্লায়েন্ট, ৪→১ instance), এবং বার্তা-ক্যাটালগ (চক্র ১৯-এর i18n ভিত্তি)। এটি বাংলাদেশ-প্রেক্ষাপটের মুখ্য ব্যবহারকারী-চ্যানেল — এবং Module-17-এর resume-URL অনুমোদনের প্রধান বাহক।

## Part 1 — Third-Party & Competitor Intelligence (৩য়-পক্ষ বুদ্ধিমত্তা, তারিখ-চিহ্নিত ওয়েব-প্রমাণ)

### ১.১ গ্রহণযোগ্য প্যাটার্ন (গ্রহণ — প্যাটার্ন হিসেবে, নির্ভরতা নয়)

| উৎস (তারিখ) | ধারণা | আমাদের অঙ্গে প্রয়োগ | চার-স্তম্ভ-বিচার |
|---|---|---|---|
| **Telegram Bot API সরকারি** (core.telegram.org) | setWebhook-এ secret_token → প্রতিটি webhook-request-এ `X-Telegram-Bot-Api-Secret-Token` header, 1-256 chars [A-Za-z0-9_-] | P-A-র নির্মাণ-স্পেক: config-field + router-প্রথম-লাইন তুলনা; charset-বৈধতা | প্রাথমিক-উৎস, খরচ-শূন্য ✓ |
| **Flood limits + 429** (grammY 2024-11-02; botnamefinder) | ~30 msg/s global, ~1/s প্রতি-chat, ~20/min প্রতি-group; 429-এ retry_after সম্মান | P-F: retry_after-aware পুনঃপ্রয়াস + প্রতি-chat কিউ-ছোঁয়া (সরল, রেডিস-ছাড়া ইন-মেমরি বাউন্ডেড) | ডেটা-ফাইল-সীমা ✓ |
| **Webhook retry-then-drop** (airbyte 2026-01-15) | ব্যর্থতায় exponential-backoff রিট্রাই; কতিঘণ্টা-পরে ড্রপ | ops-রানবুক: Render cold-start = স্বীকৃত-অবশিষ্ট-ঝুঁকি; ড্রপ-পরবর্তী getUpdates-offset পুনঃসমন্বয়-নোট | জ্ঞান-ধার ✓ |
| **aiogram 3.31 / grammY** | router-middleware/queuing স্থাপত্য-শেপ | কেবল শেপ-ধার (dispatcher-স্তর-বিভাজন ইতিমধ্যে আমাদের updates.py-র ৫-ধাপে মিলে); নির্ভরতা-প্রত্যাখ্যান | নির্ভরতা-নয় ✓ |
| **WebApp initData HMAC** (telegram-বাস্তবায়ন সাধারণ) | mini-app auth — আমাদের validate_webapp_init_data L243-266 বাস্তব কিন্তু ব্যবহার-শূন্য | P-A-পরবর্তী ঐচ্ছিক: Mini-App-রুটে যাচাই-সংযোগ (Mini App URL ইতিমধ্যে keyboards-এ settings.frontend_url থেকে) | বিদ্যমান-সম্পদ-জাগরণ ✓ |

### ১.২ প্রত্যাখৃত বিকল্প (কারণ-সহ)

| বিকল্প | কেন নয় |
|---|---|
| **aiogram/python-telegram-bot নির্ভরতা-আদান** | বর্তমান httpx-শুধু-ডিজাইন ইতোমধ্যে lightweight-স্তম্ভের শ্রেষ্ঠ; নতুন-ফ্রেমওয়ার্ক = পুনঃলিখন-চাপ + RAM |
| **পেইড-মেসেজিং/SMS-গেটওয়ে** | zero-cost স্তম্ভ-লঙ্ঘন; টেলিগ্রাম-ফ্রি ইতোমধ্যে |
| **WhatsApp-সমান্তরাল-অঙ্গ** | লেগেসি-ডক-চার্টার থাকলেও ডিরেক্টরি-অস্তিত্বহীন; এক-চ্যানেল-সুস্থ হওয়ার আগে দ্বিতীয়টি = বিভাজন (এক-সেতু-মতবাদ-সংগত) |
| **নিজস্ব পোলিং-সার্ভিস হোস্ট** | দ্বিতীয় always-on সার্ভিস — Render-ফ্রি-টিয়ার-লঙ্ঘন; webhook ইন-প্রসেসই সঠিক |

### ১.৩ প্রতিযোগী-তুলনার অন্তর্দৃষ্টি (ভিন্নভাবে ভাবা)

বাজারের বট-ফ্রেমওয়ার্ক "সর্বদা-জাগ্রত পোলার" মানসিকতা ধরে (আপনার ইনফ্রাকে poll চলবেই)। ফ্রি-টিয়ার-প্রথম আমাদের সত্য উল্টো: **জাগ্রত-হওয়া-ই ব্যয়বহুল** — তাই আমাদের ইনগ্রেস webhook (Telegram-নিজের-কাছে-জাগ্রত), আর আমাদের cold-start-অচেতনতা Telegram-এর retry-then-drop-ই সামলায়। এই "প্রতিপক্ষের-অবকাঠামোকে-আমার-কিউ-বানাও" দর্শনই zero-cost-এর শ্রেষ্ঠ-রূপ — এবং activation-gate-এর ন্যায্যতা: যে-ইনগ্রেস বাইরের-কারো-হাতে-পুশ-করা, তার প্রথম-লাইনই হবে পরিচয়-যাচাই।

## Part 1.5 — Gate 0 Reconciliation

| লেগেসি-ডক | স্ট্যাটাস | সিদ্ধান্ত |
|---|---|---|
| docs/plans/features/messaging_bots_telegram_and_whatsapp_architecture.md | historical (body-header স্টেল 'ACTIVE' L10 — স্টেল-নোট) | '৩-মুখ' চার্টার ঐতিহাসিক; WhatsApp-ডিরেক্টরি অস্তিত্বহীন — দ্বিতীয়-চ্যানেল-বিস্তার এই নীলনকশার পরিসর-বাইরে |
| Module 15 (সিরিজ) | published | telegram_security English-only-ফাঁক সেখানে উন্মোচিত — এখানে পূর্ণ-অঙ্গ-প্রেক্ষাপটে P-H-সংযোগ |
| Module 17 (সিরিজ) | published | P-E-বাহক-স্থান (admin_handlers এক-হ্যান্ডলার) নথিভুক্ত — ডিজাইন সেখানে, বাহক-বাস্তবায়ন এখানে (P-A-gated) |
| free_tier_federation/master-plan-canonical | active | zero-cost topology-তে টেলিগ্রাম-উল্লেখ সংগত — কোনো নতুন-সার্ভিস-দাবি এই ডকে নেই |
| n8n_workflow/curated_open_source/unified_fastmcp_tower/CONFIG_REGISTRY_V2 | historical | tower-এর notify_send_telegram পৃথক অঙ্গ (mission-control গ্রাহক) — সীমানা-নোট |

## Part 2 — Six-Field Analysis

### ২.১ কী আছে

- **শুদ্ধ নির্ভরতা-শৃঙ্খলা**: কোনো বট-ফ্রেমওয়ার্ক নেই — কেবল httpx; মূল-অ্যাপ-স্টার্টআপ বট-ব্যর্থতায় কখনো crash নয় (configured=False graceful)
- **বাস্তব সম্পদ**: RFC 6238 TOTP constant-time; TelDrive Fernet+gzip ব্যাকআপ; MCP bearer-auth HTTP; ৫-ধাপ dispatcher (injection-guard প্রতিটি বার্তায়); WebApp-initData-HMAC যাচাইকারী (লিখিত-টেস্টেড, ব্যবহার-অপেক্ষমাণ)
- **মাউন্ট-সত্য**: router মাউন্টেড (L240-244); টেস্ট ২-স্তর (235L+123L)

### ২.২ কী নেই

- **ইনগ্রেস-সত্য**: webhook-অনিবন্ধিত + secret-যাচাই-শূন্য; polling-অচালিত
- **পরিচয়-সত্য**: হার্ডকোডেড-দ্বৈত-চেক chat_id + মুদ্রণ; গ্রুপ-সদস্য-বাইপাস
- **স্মৃতি**: সংলাপ-অবস্থা শূন্য (docstring-দাবি মিথ্যা); security_guard restart-বিস্মারক + অবাউন্ডেড
- **transport-সত্য**: 429/4096-অবহেলা; ৪ instance; fire-and-forget-নীরব-ব্যর্থতা
- **সত্য-টেলিমেট্রি**: ৫+ জাল-KPI/জাল-audit-লাইন (V6-মতবাদ-লঙ্ঘন)
- **i18n-কাঠামো**: inline-মিশ্র-স্ট্রিং; ক্যাটালগ নেই

### ২.৩ কী করতে হবে

আটটি প্রস্তাব (ক্রম সুরক্ষা→সত্য→স্বাস্থ্য; সব ফাউন্ডার-রিভিউযোগ্য):

- **P-A (পূর্বশর্ত)**: webhook secret-token যাচাই — TELEGRAM_WEBHOOK_SECRET config + router-প্রথম-লাইন তুলনা (charset-বৈধতা); set_webhook dormant-ফাংশনকে secret-সেট-সহ জাগরণ; docstring-এর manual-curl-পথ সংশোধন (activation-gate: secret-বিহীন নিবন্ধন-অসম্ভব)
- **P-B**: admin-পরিচয়-সত্য — হার্ডকোডেড chat_id দ্বৈত-চেক ও মুদ্রণ অবসান (env/vault-শুধু); গ্রুপে from.id-যাচাই; admin-বোতামে TOTP-বাহক-সমতা (কঠোরতম-যাচাই সব-অ্যাডমিন-পথে)
- **P-C**: telemetry-সত্য — জাল KPI → বাস্তব health/cost পাঠ বা 'not measured'; জাল audit-লাইন অবসান; ব্যবহারকারী-বার্তা-লগ রেডাকশন
- **P-D**: security_guard স্বাস্থ্য — TTL sweep + dict-বাউন্ড (B-11); restart-স্থায়িত্ব ঐচ্ছিক pending_tasks-প্যাটার্নে (founder-gated)
- **P-E**: Module-17 HITL-বাহক — approve/reject inline-keyboard এক-হ্যান্ডলার (P-A-gated); resume-URL-টোকেন গ্রহণ
- **P-F**: transport-স্বাস্থ্য — 429 retry_after-সম্মান + 4096-chunk + শেয়ার্ড AsyncClient + ৪→১ lazy handler-provider; fire-and-forget ব্যর্থতায় loud-log
- **P-G**: orchestrator-সেতু-সত্য — বাস্তব processor-inject বা মৃত-ফলব্যাক অপসারণ (ERR-F02 zero-caller-প্রমাণ)
- **P-H**: বার্তা-ক্যাটালগ ডেটা-ফাইল (EN+BN কী-গঠিত) + /session-সত্য (বাস্তবায়ন বা পুনঃলেবেল) — চক্র ১৯ i18n-ভিত্তি
- **P-I**: জরুরি HITL ইন্টারঅ্যাকশন ও রান ক্যান্সেলেশন কন্ট্রোল (High-Urgency HITL Bridge & CancellationToken Telegram Abort):
  - Module 17 HITL অ্যালার্টের সাথে টেলিগ্রাম ইনলাইন কীবোর্ড ইন্টিগ্রেশন (অনুমোদন বা বাতিলের ওয়ান-ক্লিক বাটন)।
  - `/abort <run_id>` টেলিগ্রাম কমান্ড যা তাৎক্ষণিকভাবে Run Fabric ও LLM Gateway-তে `CancellationToken` ট্রিগার করবে এবং রানিং এজেন্টের ইন-ফ্লাইট টাস্ক হত্যা করবে।

### ২.৪ কীভাবে করব

ক্রম P-A→P-B→P-C→P-D→P-F→P-G→P-E→P-H→P-I (P-E ও P-I পূর্বশর্ত-পরেই); প্রতিটি P = আলাদা ছোট execution-প্ল্যান (Gate 2-পরবর্তী); P-A-তে secret-অমিল-টেস্ট-প্রথম; P-B-তে env-absence = কোনো-admin (fail-closed); P-F-এ rate-limit-মান data-file; P-H-এ ক্যাটালগ-লোড-fail→last-known-good; সব env V5.1-সংগত

### ২.৫ বেনিফিট

- টেলিগ্রাম-চ্যানেল প্রথমবার সৎভাবে সক্রিয়যোগ্য — spoof-অসম্ভব ইনগ্রেসে
- বাংলা-প্রথম ব্যবহারকারীর মুখ্য-চ্যানেল সুস্থ: বন্যায় বার্তা-হারানি, cold-start-পরেও সমন্বিত
- অনুমোদন-মোবাইল-মুক্তি (Module-17 সেতুর প্রধান-বাহক জীবন্ত)
- তাৎক্ষণিক ইমার্জেন্সি কিল-সুইচ: মোবাইল থেকেই রানঅ্যাওয়ে এজেন্টের কাজ(`/abort`) বাতিল করার ক্ষমতা।
- রক্ষণ-পৃষ্ঠ ৪→১ instance; জাল-KPI শূন্য (V6-সংবিধান-সম্পূর্ণ)
- চক্র ১৯-এর i18n-ক্যাটালগ-ভিত্তি স্থাপিত

### ২.৬ ক্ষতি/ঝুঁকি

- P-A ভুলে secret-অমিল → বট-নীরব (fail-closed সঠিক); runbook-এ নিবন্ধন-ধাপ
- P-B env-absence-এ admin-শূন্য → প্রত্যাশিত fail-closed; migration-নোট
- P-F কিউ-জটিলতা → সরল ইন-মেমরি-বাউন্ডেড; নতুন-নির্ভরতা নিষিদ্ধ
- P-E অনুমোদন-স্পুফিং-অবশিষ্টাংশ → P-A-গেট-অবধি নিষ্ক্রিয়
- লগ-রেডাকশনে ডিবাগ-ক্ষমতা-হ্রাস → রেডাকশন-স্তর env-চালিত (dev পূর্ণ, prod রেডাক্ট)

## Part 3 — Out of Scope

- hitl-অনুমোদন-ডিজাইন (Module 17); security-organ-অডিট (Module 15-এ telegram_security-র অন্য-দিক)
- WhatsApp/অন্য-চ্যানেল-বিস্তার; পেইড-মেসেজিং; polling-সার্ভিস-হোস্ট
- i18n-অঙ্গ-পূর্ণ-নীলনকশা (চক্র ১৯); TelDrive-অভ্যন্তর (নিজস্ব 600L টেস্ট)
- নতুন-নির্ভরতা-আদান (aiogram/grammY শেপ-মাত্র)

## Part 4 — ৯-নিয়ম ও Constitution-সংগতি

| নিয়ম | এই নীলনকশার অবস্থান |
|---|---|
| Single-plan execution | প্রস্তাব-পাইপলাইন; একসময়ে একটিই active |
| Evidence-first | file:line + core.telegram.org-প্রাথমিক-উৎস |
| Extend-not-replace | httpx-ডিজাইন বহাল; ৪→১ lazy-provider; ERR-F02 |
| Founder gates | webhook-সক্রিয়করণ founder-gated (activation-gate) |
| Zero-false-positive | জাল-KPI→'not measured' বিকল্পসহ |
| Branch discipline | docs-only; execution আলাদা ব্রাঞ্চ+PR |

## Part 5 — Verification & Rollback

- **Gate 4 (proof)**: P-A secret-মিল/অমিল/charset টেস্ট; P-B env-only admin টেস্ট (হার্ডকোড-অনুপস্থিতি-প্রমাণ); P-F 429/4096/শেয়ার্ড-ক্লায়েন্ট টেস্ট; P-E টোকেন-gated approve টেস্ট; P-C জাল-স্ট্রিং-শূন্য grep-টেস্ট
- **Gate 5 (measurement)**: 429-ঘটনা-গণনা (হ্রাস-লক্ষ্য); বার্তা-হারানি-অনুপাত; handler-instance-গণনা (৪→১); জাল-KPI-গণনা (→০)
- **Gate 6 (rollback)**: P-A secret-bypass env (dev-শুধু, স্পষ্ট-লেবেল); P-F কিউ disable → পূর্ব-সরল-পাঠ; প্রতিটি P এক-ফাইল-রোলব্যাক

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Audit)

| প্রস্তাব | Zero Cost | Lightweight | Fast Smooth | Zero Hardcode |
|---|---|---|---|---|
| P-A secret-গেট | ✓ | ✓ এক-তুলনা | ✓ প্রথম-লাইন | ✓ env |
| P-B পরিচয়-সত্য | ✓ | ✓ | ✓ | ✓✓ env-শুধু |
| P-C telemetry-সত্য | ✓ | ✓ | ✓ | ✓✓ |
| P-D guard-স্বাস্থ্য | ✓ | ✓ বাউন্ডেড | ✓ | ✓ env-TTL |
| P-E HITL-বাহক | ✓ | ✓ এক-হ্যান্ডলার | ✓ | ✓ |
| P-F transport-স্বাস্থ্য | ✓ | ✓ ৪→১ | ✓✓ latency-হ্রাস | ✓ ডেটা-সীমা |
| P-G সেতু-সত্য | ✓ | ✓ কম-কোড | ✓ | n/a |
| P-H ক্যাটালগ | ✓ | ✓ json | ✓ | ✓✓ |
| aiogram/SMS/polling-সার্ভিস প্রত্যাখ্যান | ✓✓ | ✓✓ | ✓ | n/a |

**জন্মগত-সংগতি-ঘোষণা**: প্রতিপক্ষের-অবকাঠামো-আমার-কিউ (Telegram-রিট্রাই) = zero-cost-দর্শনের গভীরতম রূপ; activation-gate নিশ্চিত করে সুরক্ষা-দর্শন ও ব্যবহার-দর্শন কখনো বিচ্ছিন্ন নয়।

## Part 6 — পরবর্তী মডিউল লাইনেজ

- **চক্র ১৯-প্রার্থী**: i18n/বাংলা-অ্যাডাপ্টার অঙ্গ (P-H ক্যাটালগ-ভিত্তির উপরে; LLM-পথ-বাদে ক্যাটালগ-প্রথম) — ৩য়-পক্ষ-প্রস্তুতি: ICU MessageFormat, plural/gender rules for bn, unicode-normalization (NFC), date/number bn-লোকেল
- **চক্র ২০-প্রার্থী**: notification/delivery-অঙ্গ (email_agent + core/messaging dispatcher + tower-notify) — ৩য়-পক্ষ: outbox-প্যাটার্ন, SMTP-free রেল (resend-ফ্রি-টিয়ার-বনাম smtp)
- কিউ-পুনঃর‍্যাঙ্ক: Gate 5-পরিমাপে; প্রতিটি চক্র ৩য়-পক্ষ-গবেষণা-চুক্তি বহাল
## Part 7 — বাস্তবায়ন প্রমাণ (Implementation Evidence, dated — living-plan sync)

> ২০২৬-০৯-১৯-এ fresh `main` (`52fa97da`) থেকে কোড-যাচাইকৃত; নিচের প্রতিটি দাবি ফাইল/টেস্ট-প্রমাণসহ, কোনোটি পরিকল্পনা-থেকে-অনুমিত নয়।

| প্রস্তাব | প্রকৃত অবস্থা (2026-09-19) | প্রমাণ |
|---|---|---|
| **P-A** webhook secret-টোকেন যাচাই | ✅ **আগেই বাস্তবায়িত** (Wave-1) — plan-এর "grep-শূন্য" দাবি এখন বাসি | `backend/tools/social/telegram_bot/router.py` — fail-closed + `hmac.compare_digest`, `/health` honest (identity-লিক বন্ধ) |
| **P-B** admin-পরিচয়-সত্য | ✅ **বাস্তবায়িত 2026-09-19** | `handler.py` `_configured_admin_ids()` + `is_admin(chat_id, user_id)` (env/vault-শুধু, fail-closed, `from.id`-authoritative); `updates.py` callback-এ `sender_id`; `keyboards.py`/`conversations.py` sender-aware; `admin_handlers.py`-এ হার্ডকোড-ID মুদ্রণ বন্ধ; টেস্ট `backend/tests/security/test_telegram_admin_identity.py` (12/12 PASS) |
| **P-C** telemetry-সত্য | ❌ **এখনো খোলা** — জাল KPI বর্তমান | `handler.py` `COMMANDS["/telemetry"]` ("38ms", "142 Tasks", "99.99% Uptime") ও `/quick` self-healer/audit-এর fabricated ফিগার (`conversations.py`) |
| **P-D/P-E/P-F/P-G/P-H/P-I** | ⬜ শুরু হয়নি | — (P-I-এর `/abort <run_id>` এখনো অস্তিত্বহীন; `cancel_run` API বিদ্যমান → ভবিষ্যতের সেতু) |

**পরবর্তী atomic লক্ষ্য (সুপারিশ):** **P-C (telemetry-সত্য)** — একই মডিউলে, স্পষ্টভাবে সীমিত (স্ট্রিং/ডেটা), Four-Pillar-অনুসারী, এবং বর্তমানের সবচেয়ে বড় honesty-ঋণ: `/telemetry` ব্যবহারকারীকে বানানো মেট্রিক দেখায়। বাস্তবায়ন-বিকল্প: বাস্তব `/api/v1/health/*`/cost-পাঠ, অথবা সৎ "not measured"।

**P-B-এর অস্তিত্ব-ঝুঁকি (সৎ ঘোষণা):** gate এখন fail-closed — প্রোডাকশনে `ADMIN_TELEGRAM_CHAT_ID` সেট না থাকলে কেউ admin নয়। `.env`/`.env.example`/`.env.clean`-এ কী বর্তমান (স্থানীয় প্রমাণ), কিন্তু Render-এর runtime-env এই সেশনে যাচাই করা সম্ভব হয়নি (control-tower provider অনুপলব্ধ) → মানব-অনুমোদন-আইটেম `docs/plans/PENDING_APPROVALS.md` §TASK-002।
