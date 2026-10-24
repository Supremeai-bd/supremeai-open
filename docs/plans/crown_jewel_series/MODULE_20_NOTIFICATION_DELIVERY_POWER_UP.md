---
id: crown-jewel-module-20-notification-delivery-power-up-2026-09-17
title: "Crown Jewel Module Series — Module 20: Notification & Delivery Organ Power-Up (নোটিফিকেশন-ডেলিভারি অঙ্গ: ১৩টি সমান্তরাল পাইপলাইন, মাত্র ৪টি জীবন্ত বাহক, জাল-'sent' প্রতারণা — 'স্টোর-আগে-বাহক' মতবাদে পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Governance Circle (backend/core/messaging/ + backend/services/email/ + in-app alert পথ — নোটিফিকেশন-ডেলিভারি অঙ্গ)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ২০ — একটি মডিউল (নোটিফিকেশন/ডেলিভারি), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field); Part 1 = গভীর ৩য়-পক্ষ বুদ্ধিমত্তা (transactional outbox, DLQ+backoff, ফ্রি-ইমেল-টিয়ার বাস্তবতা); branch crown-jewel-v2 base 8e2e32e8-এ spot-checkকৃত কোড-প্রমাণ"
depends_on:
  - "১৩টি সমান্তরাল পাইপলাইন, ৪টি জীবন্ত বাহক (মূল-আবিষ্কার): আজ মানুষ যা পায় = (১) Supabase auth-ইমেল (auth.py L361-384, প্ল্যাটফর্ম-পাশ), (২) JIT OTP (otp_router.py — Resend-HTTP+Discord-webhook, AuthMiddleware SENSITIVE_OPS-পথে, Module 15), (৩) skill-librarian Discord-webhook (L112, অনুমোদনে), (৪) /ws/cost-updates + admin log-tail SSE; বাকি সব কাউকে কিছুই দেয় না"
  - "ক্যানোনিকাল-বাই-ডিজাইন-কিন্তু-গ্রাহকহীন: core/messaging/service.py (১২২ লাইন) MessagingDispatcher + Protocol MessagingProvider + adapters.py (১০৪ লাইন) — messaging_dispatcher.send-এর শূন্য production কল-স্থল; MESSAGING_PROVIDER setting (config_fields.py L492) কেউ পড়ে না — প্রোভাইডার-নির্বাচন hardcoded টোকেন-উপস্থিতি-ক্রম Telegram→Email→Mock (service.py L72-106); সেমান্টিকস at-most-once fire-and-forget; Mock অ্যাডাপ্টার সৎ success=False (ERR-M01-ফিক্স — ভালো-প্রেসিডেন্ট)"
  - "বাস্তব-বাস (কিন্তু অপূর্ণ): error_event_bus (event_bus.py ৫০০ লাইন — thread-safe, bounded DLQ 1000, CancelledError-safe) ~১৫ emitter, ৬ listener; কিন্তু register_dead_letter_handler/process_dead_letter_queue-র শূন্য কলার → DLQ ভরে overflow-এ নিংড়ে যায়; producers≫consumers — ত্রুটি লগ-হয়, জানানো হয় না"
  - "জাল-সাফল্য (V6-মতবাদ-লঙ্ঘন): api/routes/webhooks_ai.py L33-60 — বিনা-পাঠায় 'sent' ফেরায় (orphan-ফ্ল্যাগড); email_service.py L66 api_key or 'mock-key-for-testing' — unconfigured ডিপ্লয় ভুয়া-কী দিয়ে Resend-এ POST → অবধারিত 401 + error-noise (mock-শাখা L70-73 অগম্য)"
  - "অগভীর-পথের-স্তূপ: /ws/dashboard swarm-bridge broadcast-task কখনো শুরুই হয় না (realtime_dashboard.py L44-63 — subscription-task start return-এর পরে); /admin-api/events চির-শূন্য (data/dashboard_events.jsonl — কেউ লেখে না); sseBridges.ts L45 অস্তিত্বহীন পাথ; supremeai-toast CustomEvent-এর ৬+ dispatcher কিন্তু শূন্য listener; GlobalHeader bell (L185-207)-এর notifications-prop কেউ পাস করে না"
  - "অপুষ্ট-স্টোর: SystemAlert মডেল + পূর্ণ CRUD (admin.py L390-431) + alembic-migration (2026_08_15) — কিন্তু producer-শূন্য ('AI Log Analyzer' POST-এর কলার নেই) ও frontend-reader-শূন্য; AdminAlertsTab 60s-পোল /admin-api/events (চির-খালি) — বাস্তব GET /admin/alerts বিদ্যমান অথচ অব্যবহৃত; 'resolve' local-state-মাত্র (AdminAlertsTab.tsx L26-31)"
  - "ইমেল-সত্য: অ্যাপে SMTP নেই (SMTP_PASSWORD .env.example L509-এ থাকলেও একমাত্র smtplib-ব্যবহারকার manual-script); বাস্তব রেল Resend-HTTP (resend_api_key SecretStr config_secrets L269-271, RESEND_FROM_EMAIL L511-513) + Supabase-নিজস্ব SMTP (২-৩ ইমেল/ঘণ্টা ফ্রি-সীমা admin-API-fallback-নোটসহ auth.py L369); EmailService-এর ৩ send-এর শূন্য কলার; ৩-রকম from-ইমেল ড্রিফট (config_fields L512 supremeai.dev বনাম .env.example L484 supremeai.app বনাম otp_router L133-fallback)"
  - "Discord-env-ড্রিফট: ৩ প্রতিদ্বন্দ্বী নাম — DISCORD_WEBHOOK_URL (skill_librarian L25, budget_guardian L51) / DISCORD_ALERT_WEBHOOK (sentinel L176) / DISCORD_OTP_WEBHOOK_URL (vault-বাউন্ড); performance_monitor.py L301-304 ফেব্রিকেটেড ফলব্যাক CPU 18.5/মেমরি 38.0 লিটারেল (V6-দ্বন্দ্ব)"
  - "৩য়-পক্ষ গবেষণা-ভিত্তি (2026-02-17 ওয়েব-প্রমাণ): Transactional Outbox (AWS Prescriptive Guidance; event-driven.io 2020-12-30; milanjovanovic.tech 2024-10-05 — at-least-once নিশ্চয়তা, dual-write সমাধান, exactly-once নয়); DLQ + exponential-backoff retry-topic (redpanda; dev.to 2026-01-23); ফ্রি-ইমেল-টিয়ার — Resend ~৩,০০০/মাস (~১০০/দিন), Brevo ৩০০/দিন (help.brevo.com) — বিদ্যমান-রেল-অগ্রাধিকার যাচাইকৃত"
implements:
  - "স্টোর-আগে-বাহক মতবাদ (অস্বাভাবিক-চিন্তার কেন্দ্র): বার্তা প্রথমে স্থায়ী-স্টোরে (SystemAlert), বাহকগণ কেবল দর্শন — বিপরীত বর্তমান-বাস্তবতা (বাহক অর্ধ-জীবিত, স্টোর অপুষ্ট); outbox-অন্তর্দৃষ্টির সরলীকৃত-রূপ: লেখা+emit এক-অপারেশনে, dispatcher drain-করে → at-least-once-ঘরানা, কোনো নতুন কিউ-অবকাঠামো নয়"
  - "৭→১ sender-একীকরণ (P-A): বিদ্যমান dispatcher-এর পেছনে; DiscordWebhookMessagingAdapter সংযোজন + notify_channels.json ডেটা-ফাইল-ফ্যানআউট + Discord-env ৩→১ (vault-বাউন্ড); Telegram-অ্যাডাপ্টার Module 18-অডিটেড handler-মোড়কে (৪র্থ instance → shared)"
  - "২-লাইন WS-জাগরণ (P-B): subscription-task start return-এর-আগে + SYSTEM_METRICS→metrics.update ম্যাপ — /ws/dashboard শূন্য-নতুন-অবকাঠামোয় জাগে"
  - "এক-CRITICAL-listener (P-C): error_event_bus → swarm 'critical_alert' broadcast + SystemAlert-সারি (async hot-path-বাইরে) — অপুষ্ট টেবিল + alerts.emergency এক-সাথে পুষ্ট"
  - "সেমান্টিকস-সত্য (P-G): এক dead-letter-handler + DLQ-drain বিদ্যমান always-on flush-লুপে + retry-নীতি ডেটা-ফাইলে — at-most-once-গর্ত বন্ধ; outbox-গবেষণা-সংগত"
  - "প্রত্যাখ্যান-নথি (anti-cargo-cult): NATS/GCP-PubSub প্রোডাকশন-আদান নয় (বিদ্যমান টেস্ট-অ্যাসেট, worker_node-সীমিত); নতুন ইমেল-ভেন্ডর নয় (Resend ইতোমধ্যে env-gated রেল; Supabase-ফ্রি ডিফল্ট); Celery/RQ-নয় (512MB; asyncio+বিদ্যমান লুপই)"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (branch crown-jewel-v2 base 8e2e32e8: service/adapters/event_bus/otp_router/email_service পূর্ণপাঠ, realtime_dashboard L44-63/L295-334, webhooks_ai L33-60, admin.py L390-431, AdminAlertsTab পাথ-যাচাই, ১৩-পাইপলাইন গণনা; ৩য়-পক্ষ দাবি 2026-02-17 ওয়েব-সার্চে তারিখ-চিহ্নিত)"
code_evidence:
  - "ERR-F02-এর সর্বোচ্চ-ঘনত্ব — ১৩ পাইপলাইনের মধ্যে ক্যানোনিকাল-বাই-ডিজাইন (dispatcher) গ্রাহকহীন, বাস্তব-ক্যানোনিকাল (otp_router) অক্ষত্য অভিপ্রেত-স্থাপত্যের বাইরে — 'স্টোর-আগে-বাহক' মতবাদে ভূমিকা-পুনর্বণ্টন"
  - "V6-মতবাদ-লঙ্ঘন-দ্বৈত — webhooks_ai জাল-'sent' + performance_monitor জাল-ফলব্যাক 18.5/38.0: উভয়ই অনুমোদন-ছাড়া সৃষ্ট উপস্থাপনা; P-H/P-C-তে সত্য-স্থাপন"
  - "২-লাইনে-সর্বোচ্চ-লাভ — /ws/dashboard-এর broadcast-task কখনোই শুরু হয়নি (start পড়েছে return-এর পরে): লাইভ হলেই swarm-metrics প্রবাহ জাগে — কোনো নির্মাণ নয়, কেবল ক্রম-সংশোধন"
  - "মজা-র-নোট — mock-key লিটারেল নিজেই mock-শাখাকে মেরেছে: যে-শাখা অনুপস্থিত-কী-সামলাবে, তার-আগেই ভুয়া-কী ঢুকে যায়; এক-লাইন অপসারণে honest-fail পুনরুদ্ধার"
  - "চক্র-সংযোগ — P-F ক্যাটালগ Module 19-এর P-A-র ভাগ; P-E-র Telegram-অ্যাডাপ্টার Module 18-এর shared-handler-পথ; P-C-র listener-মোড়ক Module 06-র run-failure ঘটনায় ভবিষ্যৎ-বিস্তারযোগ্য (নোট, ডিজাইন নয়)"
test_evidence: "বিদ্যমান: ~১,৯৩৭ টেস্ট-লাইন ৯ ফাইল (EmailService failure→error-event; OTP routing/fallback/missing-config 307L; NATS 439L; PubSub-পরিবার; SystemAlert CRUD); শূন্য-টেস্ট: dispatcher provider-নির্বাচন, উভয় বাস্তব-অ্যাডাপ্টার, WS/SSE এন্ডপয়েন্ট, DLQ-প্রবাহ, AdminAlertsTab-চুক্তি; প্রস্তাব-টেস্ট: fan-out প্রতি-চ্যানেল, DLQ-drain, retry-নীতি, ক্যাটালগ-লোড, mock-শাখা-পুনরুদ্ধার"
acceptance_criteria:
  - "প্রতিটি প্রস্তাব চার-স্তম্ভ-দর্শন-সংগত (Part 5.5)"
  - "কোনো নতুন পেইড-সার্ভিস/কিউ-অবকাঠামো নয় (512MB); বিদ্যমান রেলে (Supabase-ফ্রি-ডিফল্ট, Resend env-gated) অগ্রাধিকার"
  - "সব চ্যানেল/নীতি/বার্তা ডেটা-ফাইল+env; ডেলিভারি async — কোনো হট-পাথ লেটেন্সি-যোগ নয়; extend-not-replace (dispatcher-বাহুল্য, অপসারণ নয়)"
  - "জাল-'sent' ও জাল-ফলব্যাক অবশিষ্ট শূন্য; লিন্ট 0 error / 0 warning (সিরিজ)"
---

# Module 20 — Notification & Delivery Organ Power-Up (নোটিফিকেশন-ডেলিভারি অঙ্গ)

## বাংলা সারসংক্ষেপ

নোটিফিকেশন-অঙ্গ সিরিজের সবচেয়ে বিখ্যাত ERR-F02-প্যাটার্নের সর্বোচ্চ-ঘনত্ব: **১৩টি সমান্তরাল পাইপলাইন** — অথচ আজ মানুষ যা পায় তার তালিকা চার-লাইনের (Supabase auth-মেইল, JIT OTP, librarian-Discord, cost-updates-WS)। অভিপ্রেত-ক্যানোনিকাল dispatcher **গ্রাহকহীন**, বাস্তব-কার্যকর otp_router স্থাপত্যের বাইরে খাড়া; অপুষ্ট SystemAlert টেবিল বসে আছে পূর্ণ-CRUD-সহ; /ws/dashboard জাগেই নি কারণ subscription-task শুরু হয় **return-এর পরে** (২-লাইন-বাগ); webhooks_ai **বিনা-পাঠায় 'sent' বলে**। মতবাদ: **স্টোর-আগে-বাহক** — বার্তা প্রথমে স্থায়ী-স্টোরে, বাহক কেবল দর্শন; outbox-গবেষণার সরলীকৃত zero-infra রূপ। সাথে: ৭→১ sender-একীকরণ, ২-লাইন WS-জাগরণ, এক-CRITICAL-listener, mock-key-নিষ্ক্রিয়তা অবসান, en/bn ক্যাটালগ (চক্র ১৯-সংগতি), DLQ-drain। শূন্য নতুন ভেন্ডর — বিদ্যমান ফ্রি-রেলই ডিফল্ট।

## Part 1 — Third-Party & Competitor Intelligence (৩য়-পক্ষ বুদ্ধিমত্তা, তারিখ-চিহ্নিত ওয়েব-প্রমাণ)

### ১.১ গ্রহণযোগ্য প্যাটার্ন (গ্রহণ — প্যাটার্ন হিসেবে, নির্ভরতা নয়)

| উৎস (তারিখ) | ধারণা | আমাদের অঙ্গে প্রয়োগ | চার-স্তম্ভ-বিচার |
|---|---|---|---|
| **Transactional Outbox** (AWS Prescriptive Guidance; event-driven.io 2020-12-30; milanjovanovic.tech 2024-10-05) | ডেটাবেস-লেখা ও ইভেন্ট-প্রকাশ এক-অপারেশনে; at-least-once নিশ্চয়তা (exactly-once নয় — স্বীকারোক্তি) | P-G: SystemAlert-লেখা+dispatch-এনকিউ এক-প্রবাহে; drain-করে বিদ্যমান always-on লুপ; আমাদের স্কেলে সরলীকৃত (আলাদা outbox-টেবিল নয় — স্টোর-সারিই আউটবক্স) | কিউ-অবকাঠামো-প্রত্যাখ্যান, শেপ-গ্রহণ ✓ |
| **DLQ + exponential-backoff** (redpanda; dev.to 2026-01-23) | bounded DLQ অবশ্যই drain-হবে; retry-topic-ব্যাকঅফ নীতি-হিসেবে | আমাদের DLQ 1000 ইতোমধ্যে bounded কিন্তু নিংড়ে-যায় (কলার-শূন্য drain) — P-G-তে drain+retry-নীতি ডেটা-ফাইলে | stdlib/asyncio ✓ |
| **ফ্রি-ইমেল-টিয়ার বাস্তবতা** (help.brevo.com 300/দিন; resources.mailertogo.com 2026-06-19 — Resend ~৩,০০০/মাস) | ফ্রি-স্তরে ইমেল মিতব্যয়ী-রাখতে হয় | P-E: Supabase-ফ্রি (২-৩/ঘণ্টা, প্ল্যাটফর্ম-পাশ) = ডিফল্ট-রেল; Resend env-gated উন্নত-পথ (ইতোমধ্যে সংহত — নতুন ভেন্ডর নয়); OTP-মাত্রা মাপসই | zero-cost ✓✓ বিদ্যমান-রেল-অগ্রাধিকার |
| **at-least-once + idempotency** (outbox-পরিবার) | গ্রাহক-দিকে ডুপ্লিকেট-সহনশীলতা | P-G নোট: dispatch-এ dedup-কী (event-id) — ব্যবহারকারী এক-ঘটনায় দুই-টোস্ট দেখবে না | খরচ-শূন্য ✓ |

### ১.২ প্রত্যাখৃত বিকল্প (কারণ-সহ)

| বিকল্প | কেন নয় |
|---|---|
| **NATS/GCP-PubSub প্রোডাকশন-আদান** | sidecar/বাহ্যিক-নির্ভরতা — 512MB/zero-cost-লঙ্ঘন; NATS ইতোমধ্যে worker_node-সীমিত প্রসঙ্গে |
| **Celery/RQ/Dramatiq-নির্ভরতা** | আলাদা ব্রোকার/ওয়ার্কার প্রয়োজন; asyncio+বিদ্যমান flush-লুপই যথেষ্ট |
| **নতুন ইমেল-ভেন্ডর (Brevo ইত্যাদি)** | Resend ইতোমধ্যে সংহত env-gated; ভেন্ডর-সংযোজন = রক্ষণ-ভার; ফ্রি-টিয়ার-তুলনা কেবল ক্যাপাসিটি-নোটে |
| **সব-বার্তায়-সব-চ্যানেল ফ্যানআউট** | ব্যবহারকারী-বিরক্তি + ফ্রি-টিয়ার-সীমা-হারানি; notify_channels.json প্রতি-শ্রেণি-ম্যাপে মিতব্যয় |

### ১.৩ প্রতিযোগী-তুলনার অন্তর্দৃষ্টি (ভিন্নভাবে ভাবা)

শিল্পের নোটিফিকেশন-স্ট্যাক বিজ্ঞাপন-দেয় ("multi-channel fan-out!") — জটিলতা বিক্রি করে। আমাদের সত্য উল্টো: আমাদের ১৩-চ্যানেল-ই সমস্যা, সমাধান নয়। ভিন্ন-পথ: **স্টোর-আগে-বাহক** — এক পুষ্ট স্টোর (SystemAlert) + সাত-বাহকের শিম-ফ্যানআউট; বাহক সাময়িক-মৃত হলেও সত্য হারায় না (স্টোরে পড়ে থাকে, ব্যবহারকারী ফিরে দেখে) — "বাহক-বিশ্বস্ত-নয়, স্টোর-বিশ্বস্ত।" ফ্রি-টিয়ারে Telegram/Resend-ব্যর্থতা স্বাভাবিক; স্টোর-প্রথম স্থাপত্যে সেই ব্যর্থতা ঘটনা হয়, তথ্য-হারানো নয়।

## Part 1.5 — Gate 0 Reconciliation

| লেগেসি-ডক | স্ট্যাটাস | সিদ্ধান্ত |
|---|---|---|
| docs/plans/features/messaging_bots_telegram_and_whatsapp_architecture.md | historical (স্টেল-হেডার) | Module 18-এ Gate-0 সমাপ্ত; এখানে dispatcher-সম্পর্ক নোট-মাত্র |
| docs/plans/features/antihacking_security_defense_framework.md L322-326 | historical | প্রতিশ্রুত Email/Slack/SMS/Dashboard-চ্যানেল — SMS/Slack কখনো নির্মিত হয়নি; এই নীলনকশার P-A চ্যানেল-ম্যাপের পূর্বসূরি-নোট |
| docs/plans/features/n8n_workflow_automation_master_plan.md | historical | n8n-নোটিফিকেশন রেল (N8N_EVENT_DELIVERY_ENABLED ডিফল্ট False, outbound emitter-শূন্য) — ভবিষ্যৎ-ঐচ্ছিক-রেল-নোট |
| নোটিফিকেশন-সমর্পিত-প্ল্যান | অনুপস্থিত | **greenfield** — কোনো ডেডিকেটেড প্ল্যান নেই |
| Module 06/17/18/19 (সিরিজ) | published | boundary: run-fabric-emit নোট-মাত্র; HITL-SSE/ApprovalQueue পুনঃনিশ্চিত; telegram-transport সেখানেই; i18n-ক্যাটালগ P-F-সংযোগ-মাত্র |

## Part 2 — Six-Field Analysis

### ২.১ কী আছে

- **উদ্দেশ্যে-নির্মিত স্থাপত্য**: Protocol-based dispatcher + adapters + MessageEvent/Result মডেল (Plan §14 docstring) — কেবল কলার-শূন্য
- **বাস্তব বাস**: error_event_bus (bounded DLQ, thread-safe, ~১৫ emitter/৬ listener); otp_router (Resend+Discord, fallback, 5s timeout, env-চালিত from); /ws/cost-updates (সৎ-৩০s); Mock-অ্যাডাপ্টার-সততা (ERR-M01)
- **পুষ্টি-প্রস্তুত**: SystemAlert পূর্ণ-CRUD+migration; বাস্তব GET /admin/alerts; ToastProvider-লাইভ (client-side)
- **টেস্ট-সম্পদ**: ~১,৯৩৭ লাইন — ইমেল/OTP/queue-পরিবার ভালো-কভারড

### ২.২ কী নেই

- **সংযোগ**: dispatcher-কলার শূন্য; MESSAGING_PROVIDER-পাঠ শূন্য; /ws/dashboard-শুরু-অনুপস্থিত; bell-স্টোর-সংযোগ শূন্য
- **স্টোর-পুষ্টি**: SystemAlert-producer শূন্য; /admin-api/events-লেখক শূন্য
- **সেমান্টিকস**: at-most-once fire-and-forget; DLQ-drain শূন্য; retry শূন্য
- **সততা**: জাল-'sent' (webhooks_ai); mock-key-লিটারেল; জাল-ফলব্যাক 18.5/38.0; জাল ErrorContext 'tests.e2e'
- **একতা**: ৭ sender-path; Discord-env ৩ নাম; from-ইমেল ৩ রূপ
- **ক্যাটালগ**: সব বার্তা inline-EN

### ২.৩ কী করতে হবে

আটটি প্রস্তাব (ক্রম সস্তা-লাভ→কাঠামো; সব ফাউন্ডার-রিভিউযোগ্য):

- **P-B (২-লাইন, প্রথমেই)**: WS-জাগরণ — subscription-task start return-এর-আগে + SYSTEM_METRICS-ম্যাপ
- **P-D (শূন্য-backend)**: AdminAlertsTab-চুক্তি-সংশোধন — GET /admin/alerts-পোল (বাস্তব), resolve→বাস্তব-এন্ডপয়েন্ট, জাল local-ack অপসারণ
- **P-C**: এক-CRITICAL-listener — error_event_bus → swarm-broadcast + SystemAlert-সারি (async); অপুষ্ট-স্টোর পুষ্ট
- **P-E**: ইমেল-সত্য — mock-key-লিটারেল অপসারণ → সৎ-unconfigured শাখা; Supabase-ফ্রি-ডিফল্ট-রেল-নথি; from-ইমেল ৩→১; Resend env-gated-উন্নত-পথ-বহাল
- **P-A**: ৭→১ sender-একীকরণ — dispatcher-পেছনে; DiscordWebhookMessagingAdapter সংযোজন; notify_channels.json; Discord-env ৩→১; Telegram-অ্যাডাপ্টার Module-18-handler-মোড়ক
- **P-F**: notify-বার্তা-ক্যাটালগ (backend/config/notify_messages.{en,bn}.json + ক্ষুদ্র লোডার) — চক্র ১৯-ক্যাটালগ-ভাগ
- **P-G**: সেমান্তিকস-সত্য — DLQ-drain (এক listener সর্বদা-চলমান flush-লুপে) + retry-নীতি (attempts/backoff) ডেটা-ফাইলে + dispatch-dedup-কী; স্টোর-আগে-বাহক প্রবাহ
- **P-H**: ফাউন্ডার-গেটেড-পরিচ্ছন্নতা — webhooks_ai জাল-'sent' → বাস্তব Telegram-handler-সংযোগ বা deprecation-shim; internal.py 'tests.e2e' লিটারেল-ফিক্স; ২ অব্যবহৃত telegram-reporter → env-gated report-only supervisor-প্রস্তাব
- **P-I**: মাল্টি-টিয়ার চ্যানেল ফেইলওভার ও অ্যান্টি-ফ্লাড ব্যাচিং (Multi-Tier Channel Failover & Anti-Flood Batching):
  - এসক্যালেশন ম্যাট্রিক্স: জরুরি অ্যালার্ট প্রথমে ইন-অ্যাপ ওয়েবসকেটে যাবে; নির্দিষ্ট সময় অনিরীক্ষিত থাকলে টেলিগ্রাম -> ডিসকর্ড -> ইমেল (Resend) ক্রমানুসারে ফলব্যাক হবে।
  - অ্যান্টি-ফ্লাড উইন্ডো: ৬০ সেকেন্ডের মধ্যে একই ধরনের শত শত অ্যালার্ট পাঠিয়ে ফ্রি কোটা নষ্ট না করে রোল-আপ ডাইজেস্টে মার্জ করা হবে।

### ২.৪ কীভাবে করব

ক্রম P-B→P-D→P-C→P-E→P-A→P-F→P-G→P-H→P-I; প্রতিটি P = আলাদা ছোট execution-প্ল্যান (Gate 2-পরবর্তী); P-C-তে bounded-স্টোর-লেখা (ltrim/B-11-অভ্যাস); P-A-তে adapter-প্রতি টেস্ট + notify_channels.json-প্রতি-চ্যানেল disable-কী; P-G-তে drain-মেট্রিক; সব env V5.1-সংগত; ERR-F02 (শিম-প্রথম)

### ২.৫ বেনিফিট

- ব্যবহারকারী প্রথমবার বাস্তব অ্যালার্ট পাবে: CRITICAL-ঘটনা → স্টোর + WS + (ঐচ্ছিক) Telegram/Discord
- মাল্টি-টিয়ার ফলব্যাকে বার্তা কখনোই হারাবে না, চ্যানেল ডাউন থাকলেও বিকল্প মাধ্যমে পৌঁছাবে।
- অ্যান্টি-ফ্লাড নিয়ন্ত্রণের মাধ্যমে নোটিফিকেশন ক্ল্যাটার ও এপিআই কোটা নিঃশেষ হওয়া রোধ।
- বাহক-ব্যর্থতা আর তথ্য-হারানো নয় (স্টোর-আগে) — ফ্রি-টিয়ারের প্রকৃত-বাস্তবতা সামলানো
- রক্ষণ-পৃষ্ঠ ১৩→স্বচ্ছ-কয়েক; Discord/from-ইমেল ড্রিফট অবসান
- জাল-সাফল্য শূন্য (V6-সংবিধান-সম্পূর্ণ); অপুষ্ট-বিনিয়োগ (SystemAlert/CRUD/টেস্ট ~১,৯০০ লাইন) অবশেষে ফলপ্রসূ
- চক্র ১৭ (অনুমোদন) + ১৮ (telegram) + ১৯ (ক্যাটালগ) — সব পূর্ব-চক্রের সেতু-বাহক এক-জায়গায়

### ২.৬ ক্ষতি/ঝুঁকি

- P-C-তে অতি-বিজ্ঞপ্তি (noise) → severity-থ্রেশহোল্ড ডেটা-ফাইলে, ডিফল্ট CRITICAL-শুধু
- P-A-স্থানান্তরে ডুপ্লিকেট-বার্তা → এক-সময়ে-এক-বাহক cutover + dedup-কী
- P-G-তে retry-বন্যা → ব্যাকঅফ+সর্বোচ্চ-প্রচেষ্টা ডেটা-ফাইলে; ফ্রি-টিয়ার-সীমা-সম্মান
- P-F-ক্যাটালগ-মিস → fallback-EN-লাউড
- P-H shim-পিরিয়ডে বাহ্যিক-নির্ভরতা → দ্বৈত-লগ-নোট

## Part 3 — Out of Scope

- run-fabric-অভ্যন্তর (Module 06); telegram-transport (Module 18); i18n-কাঠামো (Module 19 — ক্যাটালগ-শেয়ার-মাত্র); HITL-অনুমোদন (Module 17)
- NATS/GCP/Celery-আদান; নতুন ইমেল-ভেন্ডর; SMS/Slack-নতুন-চ্যানেল-নির্মাণ
- tower-side notify (mission-control নিজস্ব অ্যাপ)
- কোনো workflow-ফাইল তৈরি

## Part 4 — ৯-নিয়ম ও Constitution-সংগতি

| নিয়ম | এই নীলনকশার অবস্থান |
|---|---|
| Single-plan execution | প্রস্তাব-পাইপলাইন; একসময়ে একটিই active |
| Evidence-first | file:line; ৩য়-পক্ষ তারিখ-চিহ্নিত |
| Extend-not-replace | dispatcher-বাহুল্য; shim; ERR-F02 |
| Founder gates | P-H নিয়তি-সিদ্ধান্ত; reporter-সুপারভাইজার Gate 2-পরবর্তী |
| Zero-false-positive | severity-ডিফল্ট CRITICAL-শুধু |
| Zero-cost সংবিধান | বিদ্যমান-ফ্রি-রেল-ডিফল্ট; নতুন-ভেন্ডর-নিষিদ্ধ |
| Branch discipline | docs-only; execution আলাদা ব্রাঞ্চ+PR |

## Part 5 — Verification & Rollback

- **Gate 4 (proof)**: P-B WS-প্রবাহ ইন্টিগ্রেশন-টেস্ট; P-C CRITICAL→স্টোর+broadcast টেস্ট; P-E mock-শাখা-পুনরুদ্ধার টেস্ট; P-A adapter-প্রতি+fan-out-নীতি টেস্ট; P-G DLQ-drain+retry টেস্ট; P-D চুক্তি-টেস্ট
- **Gate 5 (measurement)**: DLQ-গভীরতা (→০ নিয়মিত); বার্তা-হারানি-গণনা (→০); পাইপলাইন-গণনা (১৩→কয়েক); জাল-সাফল্য-গণনা (→০); SystemAlert-সারি-প্রবাহ
- **Gate 6 (rollback)**: প্রতি-চ্যানেল disable-কী (notify_channels.json); P-C listener kill-switch env; প্রতিটি P এক-ফাইল-রোলব্যাক

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Audit)

| প্রস্তাব | Zero Cost | Lightweight | Fast Smooth | Zero Hardcode |
|---|---|---|---|---|
| P-B WS-জাগরণ | ✓ | ✓ ২-লাইন | ✓✓ | n/a |
| P-D চুক্তি-সংশোধন | ✓ | ✓ frontend-শুধু | ✓ | n/a |
| P-C CRITICAL-listener | ✓ | ✓ এক-listener | ✓ async | ✓ থ্রেশহোল্ড-ডেটা |
| P-E ইমেল-সত্য | ✓✓ ফ্রি-রেল | ✓ | ✓ | ✓ env |
| P-A ৭→১ একীকরণ | ✓ | ✓✓ | ✓ | ✓ json-ম্যাপ |
| P-F ক্যাটালগ | ✓ | ✓ json | ✓ | ✓✓ |
| P-G সেমান্টিকস | ✓ | ✓ | ✓ async-drain | ✓ নীতি-ডেটা |
| P-H পরিচ্ছন্নতা | ✓ | ✓ | ✓ | n/a |
| NATS/Celery/ভেন্ডর প্রত্যাখ্যান | ✓✓ | ✓✓ | ✓ | n/a |

**জন্মগত-সংগতি-ঘোষণা**: স্টোর-আগে-বাহক ফ্রি-টিয়ার-বাস্তবতার সাথে সহজাত-সংগত — বাহক-অনিশ্চয়তা যেখানে স্বাভাবিক, সেখানে স্থায়িত্ব-দায়িত্ব স্টোরের।

## Part 6 — পরবর্তী মডিউল লাইনেজ

- **চক্র ২১-প্রার্থী**: simulated-class governance স্ক্রিপ্ট (মক/জাল-ক্ষমতা-শ্রেণি-সনাক্তকারী — V6-মতবাদের স্বয়ংক্রিয়-আয়না; zero-false-positive পূর্বশর্ত, Module-10/11-মতবাদ-সংগত; founder-gated, এই সিরিজের নিজ-সুযোগ-সনাক্তকরণ-অভ্যাসকে টুলে রূপান্তর)
- **চক্র ২২-প্রার্থী**: scheduler/cron-অঙ্গ (schedule-রুট পরিবার — S10-সংযোগ; ৩য়-পক্ষ: cron-সেমান্টিকস, APScheduler-বিকল্প-বিশ্লেষণ)
- কিউ-পুনঃর‍্যাঙ্ক: Gate 5-পরিমাপে; প্রতিটি চক্র ৩য়-পক্ষ-গবেষণা-চুক্তি বহাল
