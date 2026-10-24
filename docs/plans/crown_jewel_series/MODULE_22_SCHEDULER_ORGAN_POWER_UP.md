---
id: crown-jewel-module-22-scheduler-organ-power-up-2026-09-17
title: "Crown Jewel Module Series — Module 22: Scheduler & Cron Organ Power-Up (শিডিউলার-অঙ্গ: চাকা-বিহীন গাড়ি — S10 নিখুঁত CRUD, অথচ নির্বাহক-লুপ অনুপস্থিত; placebo auto-healer; UTC-অন্ধ সময় — supervisor-as-heartbeat মতবাদে পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Governance Circle (backend/api/routes/scheduled_tasks.py + backend/core/agent_supervisor.py + startup লুপ — শিডিউলার-অঙ্গ)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ২২ — একটি মডিউল (শিডিউলার/cron), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field); Part 1 = গভীর ৩য়-পক্ষ বুদ্ধিমত্তা (APScheduler-বিশ্লেষণ, cron-এর missed-run গর্ত, TZ-সচেতন শিডিউলিং সর্বোত্তম-অনুশীলন); branch crown-jewel-v2 base 4cfd21c9-এ spot-checkকৃত কোড-প্রমাণ"
depends_on:
  - "S10-সত্য (মূল-আবিষ্কার): backend/api/routes/scheduled_tasks.py (৬৩৩ লাইন, লাইভ routers.py L49) — নিখুঁত CRUD + manual-run; কিন্তু **নির্বাহক অনুপস্থিত**: scheduled_tasks সারণি নির্বাহের জন্য কেউ পড়ে না (schedule_type/scheduled_time/cron_expression শুধু-লেখা); একমাত্র manual POST /{id}/run llm_gateway-দিয়ে; ফ্রন্টএন্ড S10-প্যানেল লাইভ (App.tsx L203) কিন্তু next_run_at/executed_at কলাম রেন্ডার করে — এমন ফিল্ড backend কখনো ফেরতই দেয় না (চির-ফাঁকা কলাম, ERR-F02); store restart-অতিক্রমী, নির্বাহ নয়"
  - "বর্তমান-হৃদয়স্পন্দন: core/agent_supervisor.py (৪৪০ লাইন, লাইভ-সিঙ্গলটন) — backoff/restart-ইঞ্জিন (1s→30s, সর্বোচ্চ ৩-১০); core/startup/agents.py (৪২১ লাইন, lifespan L204) — ১৭ লুপ-নিবন্ধন, ১৩ env-gated; core/maintenance_pipeline.py ৩৪৫ লাইন সর্বদা-চালু ১২০s Immune-probe (startup/services.py L248); LearningStore flush 5s/50-event (agents.py L200); কিন্তু ২টি task shutdown-এ কখনো cancel হয় না"
  - "placebo-লুপ: services/auto_healer.py L415 — 'monitoring' বিশুদ্ধ sleep, docstring নিজেই no-op স্বীকার করে; double auto-healer start-প্যাটার্ন; inner try/except-লুপ চির-নীরবে ব্যর্থ; ৯০s dead-heartbeat কেবল লগ; **কোথাও missed-run catch-up নেই**"
  - "মৃত-ক্যানোনিকাল: core/orchestration/periodic_task_scheduler.py (২৭২ লাইন) — tick()-এর শূন্য কলার, /orchestrator রাউটার আনমাউন্টেড (imported-inert); core/automation/dispatcher.py (১৩৩ লাইন) — n8n_enabled ডিফল্ট False → সর্বদা SKIPPED (Module 06-এর AutomationDispatcher-orphan এখানেই); container_auditor/type_sync_bus/code_to_db_sync/integration_layer/task_queue_enhanced সব dormant"
  - "repo-cron: ৭ workflow / ৮ cron, সব UTC — e2e 01:30, maintenance 02:00, deep-audit 03:00, db-retention 03:30 দৈনিক; audit-release 03:00+04:00; governance 06:17; dast-zap 04:00 সোমবার — ৩টি দৈনিক ক্রন প্রায়-সময়ে (02:00/03:00/03:30) একই-রাতে-স্তূপ"
  - "TZ-অন্ধত্ব: ZoneInfo/pytz/Asia/Dhaka-হ্যান্ডলিং শূন্য (grep-প্রমাণ); cron_expression ব্যবহারকারী-প্রত্যাশা বনাম UTC-বাস্তবতার সংঘর্ষ — বাংলাদেশ (Asia/Dhaka) মুখ্য-ব্যবহারকারী-অঞ্চল অথচ প্রথম-শ্রেণি নয়"
  - "প্রতিদ্বন্দ্বী প্রক্রিয়া ≥৬: supervisor-লুপ / raw create_task-লুপ (দ্বৈত auto-healer সহ) / GH-cron ×৭ / GCS-webhook ×২ / n8n-অ্যাডাপ্টার / worker-BLPOP-সার্ভিস + mcp-control-plane TS-শিডিউলার — APScheduler অনুপস্থিত (poetry.lock মাত্র)"
  - "টেস্ট-ফাঁক: supervisor 35L, lifespan 267L, maintenance 212L... টেস্টেড; /api/schedule রুট-পরিবার **শূন্য টেস্ট-লাইন**"
  - "৩য়-পক্ষ গবেষণা-ভিত্তি (2026-02-17 ওয়েব-প্রমাণ): APScheduler-অগ্রগাম্য (sentry.io 2024-07-15; github fastapi#9143 — হালকা in-process, next-run দৃশ্যমালা) বনাম multi-worker-duplication-ঝুঁকি; cron-এর গর্ত — crontab shutdown-মিস পুষিয়ে দেয় না (opensuse forum), n8n-ক্যাচআপ-অনুরোধ (github 2026-05-17) → last_run_at-ক্যাচআপ-প্যাটার্ন; TZ-সর্বোত্তম — server-UTC + application-level-শিডিউলিং DST-সম্মান (inventivehq 2024-12-24; Airflow docs TZ-aware cron)"
implements:
  - "supervisor-as-heartbeat মতবাদ (অস্বাভাবিক-চিন্তার কেন্দ্র): নতুন শিডিউলার-প্রসেস নয় — বিদ্যমান AgentSupervisor-ই সব-লুপের হৃদয়; due-task sweep সেই-হৃদয়ের আরেক স্পন্দন; এক-হৃদয় = এক-জবাবদিহি, এক-শাটডাউন, এক-ব্যাকঅফ"
  - "last_run_at-ক্যাচআপ (P-A): cron-শিল্পের স্বীকৃত-গর্ত (shutdown-মিস = হারানো) — DB-স্থায়ী last_run_at + sweep-শুরুতে বয়স্ক-due-আগে; restart-পরেও কাজ হারায় না (S10-store-ই প্রস্তুত)"
  - "APScheduler-প্রত্যাখ্যান-নথি (anti-cargo-cult): নির্ভরতা-যোগ + multi-worker-ডুপ্লিকেশন-ঝুঁকি + supervisor-এর সাথে দ্বৈত-হৃদয় — stdlib asyncio sweep-ই যথেষ্ট (গবেষণা-সংগত: APScheduler-মূল্য স্বীকৃত, প্রসঙ্গ-অমিল)"
  - "schedules_policy.json rails-as-data (P-C): সব interval/cron-default/retry-সীমা/sweep-cadence ডেটা-ফাইলে; founder-gated নীতি (Module 15 P-B প্রেসিডেন্ট)"
  - "TZ-সত্য (P-H): প্রতি-ব্যবহারকারী timezone-সংরক্ষণ + application-level-গণনা (server-UTC বহাল); Asia/Dhaka প্রথম-শ্রেণি — ভাষা-কর-মতবাদের (Module 19) সময়-সমতুল্য"
  - "সেতু-শৃঙ্খলা: P-G sweep-ব্যর্থতা → Module 20 SystemAlert-স্টোর (স্টোর-আগে-বাহক-সংগত); P-D supervisor-এ-মাইগ্রেশনে shutdown-leak-সংশোধন"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (branch crown-jewel-v2 base 4cfd21c9: scheduled_tasks কাঠামো-পাঠ, agent_supervisor/startup-agents/maintenance/learning-store পূর্ণপাঠ, auto_healer L415, periodic_task_scheduler tick-grep, cron-yaml গণনা, TZ-grep, S10-ফ্রন্টএন্ড চুক্তি; ৩য়-পক্ষ দাবি 2026-02-17 ওয়েব-সার্চে তারিখ-চিহ্নিত)"
code_evidence:
  - "চাকা-বিহীন-গাড়ি — S10-এর দৃশ্যমান কেবিন (CRUD+প্যানেল) নিখুঁত, চাকা (নির্বাহক-লুপ) অনুপস্থিত; ফলে ব্যবহারকারী কাজ তালিকাভুক্ত করে, চির-অপেক্ষায় থাকে, ফাঁকা next_run_at দেখে — ত্রি-স্তরের ভাঙা-প্রতিশ্রুতি"
  - "placebo-স্বীকারোক্তি — auto_healer L415 docstring নিজেই no-op-মনিটর মানে; নাম-বনাম-আচরণ-ব্যবধান V6-মতবাদের কোড-স্তর-প্রমাণ; double-start অপসারণ P-D-র প্রথম-ফল"
  - "মৃত-ক্যানোনিকাল-সিদ্ধান্ত-প্রস্তাব — periodic_task_scheduler (tick শূন্য-কলার) mount-or-fold: mount করলে supervisor-নীতির সাথে দ্বৈত-হৃদয় — fold-ই ডিফল্ট-প্রস্তাব (ERR-F02 zero-caller-প্রমাণ)"
  - "ক্যাচআপ-গর্তের সংখ্যা — শিল্পে cron মিস পুষায় না (গবেষণা); আমাদের সুবিধা: S10-store ইতোমধ্যে স্থায়ী — last_run_at-যোগ = ক্যাচআপ-সক্ষমতা শূন্য-নতুন-স্টোরে"
  - "supervisor-সংযোগের নিরাপত্তা — backoff/max-restart ইতোমধ্যে টেস্টেড (35L); sweep-স্পন্দন সেই-সুরক্ষায় — নতুন-ব্যর্থতা-মোড নয়, বিদ্যমান-শৃঙ্খলার গ্রাহক"
test_evidence: "বিদ্যমান: supervisor/lifespan/maintenance/sentinel টেস্ট; /api/schedule রুট-পরিবার শূন্য-টেস্ট; প্রস্তাব-টেস্ট: sweep due/catch-up/disabled ত্রি-পথ, TZ-গণনা (Dhaka vs UTC), policy-লোড-fail→last-known-good, S10-চুক্তি ফিল্ড-মিল, shutdown-cancel-সম্পূর্ণতা"
acceptance_criteria:
  - "প্রতিটি প্রস্তাব চার-স্তম্ভ-দর্শন-সংগত (Part 5.5)"
  - "কোনো নতুন শিডিউলার-নির্ভরতা নয় (APScheduler প্রত্যাখ্যান-নথিভুক্ত); stdlib asyncio; 512MB-সংগত"
  - "সব interval/নীতি ডেটা-ফাইল+env; sweep async hot-path-বাইরে; extend-not-replace (supervisor-গ্রাহক, প্রতিস্থাপন নয়)"
  - "চির-ফাঁকা-কলাম/জাল-নাম অবশিষ্ট শূন্য; TZ প্রতি-ব্যবহারকারী-সংরক্ষিত; লিন্ট 0 error / 0 warning (সিরিজ)"
---

# Module 22 — Scheduler & Cron Organ Power-Up (শিডিউলার-অঙ্গ)

## বাংলা সারসংক্ষেপ

শিডিউলার-অঙ্গ সিরিজের সবচেয়ে স্পষ্ট "চাকা-বিহীন গাড়ি": S10 ScheduledTasks-প্যানেল লাইভ, CRUD নিখুঁত, store স্থায়ী — অথচ **কেউই কাজ চালায় না** (schedule_type/cron_expression শুধু-লেখা); ব্যবহারকারী দেখে চির-ফাঁকা next_run_at। ইতোমধ্যে **এক মহান হৃদয় আছে** — AgentSupervisor (backoff/restart-টেস্টেড) — কিন্তু তার বাইরে placebo auto-healer ("monitoring"=sleep, docstring-স্বীকার), মৃত periodic_task_scheduler (tick শূন্য-কলার), ≥৬ প্রতিদ্বন্দ্বী প্রক্রিয়া, আর **UTC-অন্ধত্ব** (Asia/Dhaka মুখ্য-অঞ্চল অথচ প্রথম-শ্রেণি নয়)। মতবাদ: **supervisor-as-heartbeat** — নতুন শিডিউলার নয়; due-task sweep বিদ্যমান হৃদয়ের আরেক স্পন্দন; cron-শিল্পের স্বীকৃত গর্ত (shutdown-মিস কখনো পুষায় না) `last_run_at`-ক্যাচআপে বন্ধ — শূন্য নতুন স্টোর (S10-ই প্রস্তুত)। APScheduler-নামক জনপ্রিয় ওষুধ স্বচ্ছভাবে প্রত্যাখৃত (নির্ভরতা+দ্বৈত-হৃদয়)।

## Part 1 — Third-Party & Competitor Intelligence (৩য়-পক্ষ বুদ্ধিমত্তা, তারিখ-চিহ্নিত ওয়েব-প্রমাণ)

### ১.১ গ্রহণযোগ্য প্যাটার্ন (গ্রহণ — প্যাটার্ন হিসেবে, নির্ভরতা নয়)

| উৎস (তারিখ) | ধারণা | আমাদের অঙ্গে প্রয়োগ | চার-স্তম্ভ-বিচার |
|---|---|---|---|
| **cron-গর্ত-সচেতনতা** (opensuse-forum; n8n-ক্যাচআপ-অনুরোধ github 2026-05-17) | crontab shutdown-মিস কখনো পুষিয়ে দেয় না; ক্যাচআপ-অপশন শিল্পে সদ্য-চাহিদা | P-A: `last_run_at` DB-স্থায়ী + sweep-শুরুতে বয়স্ক-due-আগে — গর্ত-মুক্ত নকশা; S10-store ইতোমধ্যে স্থায়ী | সংখ্যা-গঠন খরচ-শূন্য ✓ |
| **APScheduler-মূল্য-স্বীকৃতি** (sentry.io 2024-07-15; fastapi#9143 2024-07-29) | হালকা in-process, next-run দৃশ্যমালা, cancel-সহজ | মূল্য স্বীকার; কিন্তু আমাদের প্রসঙ্গে প্রত্যাখ্যান (১.২-সারি) — বিকল্প: stdlib-asyncio sweep + S10-store-এ next_run_at-গণনা (একই সুবিধা, নির্ভরতা-ছাড়া) | নির্ভরতা-প্রত্যাখ্যান, সুবিধা-গ্রহণ ✓ |
| **TZ-সর্বোত্তম-অনুশীলন** (inventivehq 2024-12-24; Airflow TZ-docs) | server-UTC বহাল + application-level-শিডিউলিং DST-সম্মান; TZ-aware cron | P-H: প্রতি-ব্যবহারকারী TZ-সংরক্ষণ (Asia/Dhaka প্রথম-শ্রেণি), গণনা application-স্তরে, server-UTC বহাল | stdlib ZoneInfo ✓ |
| **Supervisor-প্যাটার্ন-সম্মান** (আমাদেরই agent_supervisor backoff/restart) | সব-লুপ এক-জবাবদিহি-অঞ্চলে | মতবাদ-কেন্দ্র: sweep-স্পন্দন supervisor-নিবন্ধিত — এক-হৃদয়, এক-শাটডাউন, এক-ব্যাকঅফ | বিদ্যমান-টেস্টেড-শৃঙ্খলা ✓ |

### ১.২ প্রত্যাখৃত বিকল্প (কারণ-সহ)

| বিকল্প | কেন নয় |
|---|---|
| **APScheduler-আদান** | নির্ভরতা-যোগ (zero-dep-শৃঙ্খলা-লঙ্ঘন); multi-worker-ডুপ্লিকেশন-ঝুঁকি (একই কাজ দুই-ওয়ার্কারে); supervisor-এর সাথে **দ্বৈত-হৃদয়** — দুই জবাবদিহি-অঞ্চল, দুই শাটডাউন-পথ; আমাদের প্রয়োজন (due-sweep+catch-up+TZ) stdlib-এ সম্ভব |
| **Celery-beat/নতুন ব্রোকার** | আলাদা ব্রোকার/ওয়ার্কার — 512MB/zero-cost-লঙ্ঘন (Module 20 প্রত্যাখ্যান-পুনরাবৃত্তি) |
| **নতুন শিডিউলার-সার্ভিস/সাইডকার** | দ্বিতীয় always-on প্রক্রিয়া — ফ্রি-টিয়ার-লঙ্ঘন; supervisor-as-heartbeat-ই এক-প্রক্রিয়া-সত্য |
| **GCS-webhook ×২ বিস্তার** | মৃত-ক্যানোনিকাল-পথের প্রতি-অনুকরণ; প্রথমে mount-or-fold-সিদ্ধান্ত (P-E) |

### ১.৩ প্রতিযোগী-তুলনার অন্তর্দৃষ্টি (ভিন্নভাবে ভাবা)

শিল্পের শিডিউলার "কখন-চালাব" সমস্যা সমাধান করে। আমাদের প্রকৃত সমস্যা ভিন্ন: **"কী-চালাব" ইতোমধ্যে ডেটাবেসে আছে** (S10-store) — শুধু চাকা নেই। তাই আমরা শিডিউলার-ইঞ্জিন কিনব না; **হৃদয়ে স্পন্দন যোগ করব**। আর শিল্পের cron সময়-মাত্রা জানে না (UTC-অন্ধ); আমাদের ব্যবহারকারীর সময় হলো Dhaka-র ভোর — "সময়-অঞ্চল-প্রথম" ডিজাইন ভাষা-কর-মতবাদের (Module 19) সময়-রূপ: **ব্যবহারকারীর ঘড়িই সত্য**।

## Part 1.5 — Gate 0 Reconciliation

| লেগেসি-ডক | স্ট্যাটাস | সিদ্ধান্ত |
|---|---|---|
| শিডিউলার-সমর্পিত-প্ল্যান | অনুপস্থিত | **greenfield** — কোনো ডেডিকেটেড প্ল্যান নেই |
| PLATFORM_OSS | blocked | APScheduler-জাতীয় নির্ভরতা-প্রস্তাবের ঐতিহাসিক-স্থান; আমাদের stdlib-পথ তার চেয়ে কঠোর-সত্য |
| UNIFIED_ECOSYSTEM_ARCHITECTURE_PLAN | active | নোট-মাত্র — সংঘর্ষ নেই |
| Module 06 (run fabric) | published | boundary: AutomationDispatcher-orphan-রায় দাঁড়ায় — এখানে P-E-তে নিয়তি-নোট; run-সেমান্টিকস সেখানেই |
| Module 17 (HITL P-G TTL-sweep) | published | boundary: অনুমোদন-TTL-সুইপ সেখানে প্রস্তাবিত; এখানকার P-A-র সাধারণ-sweep-অঞ্চলে স্থাপন-নোট (এক-হৃদয়) |
| Module 20 (SystemAlert) | published | P-G-সেতু: sweep-ব্যর্থতা → সেই-স্টোর (স্টোর-আগে-বাহক-সংগত) |
| Module 10 (S10-লাইভ) | published | S10-রায় বহাল; এখানে চুক্তি-ফাঁক-বিস্তারিত (P-B) |

## Part 2 — Six-Field Analysis

### ২.১ কী আছে

- **মহান-হৃদয়**: AgentSupervisor (৪৪০ লাইন, টেস্টেড backoff/restart) — সব-লুপের জন্য প্রস্তুত-জবাবদিহি-কাঠামো
- **স্থায়ী-স্টোর**: scheduled_tasks সারণি restart-অতিক্রমী — ক্যাচআপের প্রস্তুত-ভিত
- **লাইভ-মুখ**: S10-প্যানেল (route+nav) — ব্যবহারকারী-সংযোগস্থল
- **সচেতন-লুপ-সংস্কৃতি**: ১৭ নিবন্ধনে ১৩ env-gated; maintenance/flush সর্বদা-চালু অথচ বাউন্ডেড

### ২.২ কী নেই

- **নির্বাহক-লুপ**: schedule ডেটা চালায় না কেউ; cron_expression শুধু-লেখা
- **ক্যাচআপ**: মিস-হারানো-চিরকালের-জন্য; কোনো last_run_at নেই
- **সত্য-চুক্তি**: next_run_at/executed_at ফিল্ড backend দেয় না — ফাঁকা কলাম
- **এক-হৃদয়**: ২ task shutdown-cancel-বঞ্চিত; placebo auto-healer; দ্বৈত-start; ≥৬ প্রতিদ্বন্দ্বী প্রক্রিয়া
- **TZ-সত্য**: ZoneInfo-শূন্য; Asia/Dhaka অদৃশ্য
- **টেস্ট**: /api/schedule শূন্য-টেস্ট-লাইন

### ২.৩ কী করতে হবে

নয়টি প্রস্তাব (ক্রম ভিত্তি→সত্য→একতা; সব ফাউন্ডার-রিভিউযোগ্য):

- **P-A (চাকা)**: due-task sweep-স্পন্দন AgentSupervisor-নিবন্ধিত (stdlib asyncio) — scheduled_tasks পড়ে due-নির্বাহ (manual-run-পথের llm_gateway পুনঃব্যবহার); last_run_at স্থায়ী → restart-ক্যাচআপ; sweep-cadence env/ডেটা
- **P-B (সত্য-চুক্তি)**: S10-ফিল্ড-সত্য — next_run_at/executed_at বাস্তবে-ফেরত (sweep-এ পূরণ) বা সৎ-কলাম-লুকানো; জাল-প্রতিশ্রুতি অবসান
- **P-C (নীতি-ডেটা)**: schedules_policy.json — ডিফল্ট-cadence/retry-সীমা/max-concurrent/TZ-ডিফল্ট; env-ওভাররাইড; founder-gated নীতি-সিদ্ধান্ত
- **P-D (এক-হৃদয়)**: maintenance/LearningStore-লুপ supervisor-নিবন্ধনে — shutdown-cancel-সম্পূর্ণতা; placebo auto-healer-নিয়তি (বাস্তব-কাজ বা সৎ-অপসারণ); double-start অবসান
- **P-E (মৃত-ক্যানোনিকাল-নিয়তি)**: periodic_task_scheduler mount-or-fold — fold-ডিফল্ট-প্রস্তাব (tick শূন্য-কলার, ERR-F02); dispatcher/container_auditor-জাত স্থগিত-নোট
- **P-F (repo-cron-সত্য)**: cron-তালিকা-নথি + ৩ দৈনিক-ক্রন-স্তূপ-বিন্যাস-প্রস্তাব (02:00/03:00/03:30 → বিচ্ছিন্ন) — ফাউন্ডার-গেটেড; এই ডক কোনো workflow সম্পাদনা করে না
- **P-G (সেতু)**: sweep-ব্যর্থতা → Module-20-SystemAlert-সারি (স্টোর-আগে-বাহক); ব্যবহারকারী-কাজ-ব্যর্থতায় বিজ্ঞপ্তি-পথ-নোট (চক্র ২০-বাহক)
- **P-H (TZ-সত্য)**: প্রতি-ব্যবহারকারী timezone-সংরক্ষণ + application-level due-গণনা (ZoneInfo, stdlib); Asia/Dhaka প্রথম-শ্রেণি; server-UTC বহাল (গবেষণা-সংগত)
- **P-I (৬-ক্যাগল অ্যাকাউন্ট ফেইলওভার ও ক্যানারি হ্যান্ডওভার শিডিউলার)**:
  - AgentSupervisor-এর অধীনে একটি বিশেষায়িত লাইফসাইকেল লুপ যা `KaggleEndpointPool`-এর ৬টি ক্যাগল নোডের সেশন বয়স মনিটর করবে।
  - প্রতিটি নোডের বয়স ৯ ঘণ্টা অতিক্রম করলেই শিডিউলার স্বয়ংক্রিয়ভাবে পরবর্তী নোডকে ট্রিগার করবে (**Overlapping Canary Handover**), যাতে পুরোনো নোড স্লিপে যাওয়ার আগেই নতুন নোড বুট হয়ে ক্লাউডফ্লেয়ার টানেল লাইভ রাখে।
  - এর ফলে ৩৬৫ দিন ২৪/৭ ল্যাব ইভ্যালুয়েশন ও অফলাইন আইডিই ইনফারেন্স সম্পূর্ণ নিরবচ্ছিন্ন থাকবে।

### ২.৪ কীভাবে করব

ক্রম P-A→P-B→P-C→P-D→P-H→P-G→P-I→P-E→P-F; প্রতিটি P = আলাদা ছোট execution-প্ল্যান (Gate 2-পরবর্তী); P-A-তে টেস্ট-প্রথম (due/disabled/catch-up ত্রি-পথ + দ্বৈত-নির্বাহ-প্রতিরোধ idempotency-কী); P-D-তে লুপ-প্রতি স্থানান্তর-টেস্ট (ERR-F02 শিম-প্রথম); P-H-তে TZ-গণনা-টেস্ট (Dhaka-ভোর বনাম UTC-রাত); P-I-তে ক্যানারি হ্যান্ডওভার সিমুলেশন টেস্ট; সব env V5.1-সংগত

### ২.৫ বেনিফিট

- S10 প্রথমবার সত্য: ব্যবহারকারীর কাজ আসলেই চলে, ফল দেখে — ত্রি-স্তর-ভাঙা-প্রতিশ্রুতি পুনরুদ্ধার
- মিস-হারানি-নয় (catch-up) — ফ্রি-টিয়ার cold-start-বাস্তবতায় শিডিউল-বিশ্বাসযোগ্য
- ১৮০ ঘণ্টার ৬-ক্যাগল জিপিইউ ক্লাস্টার সার্বক্ষণিক সচল ও অটো-হ্যান্ডওভার সক্ষম (P-I)
- এক-হৃদয়: শাটডাউন-লিক বন্ধ, placebo/দ্বৈত-অবসান, জবাবদিহি-একতা
- ব্যবহারকারীর ঘড়ি-সম্মান (Dhaka-প্রথম) — সময়-স্বাস্থ্য Module 19-এর সমতুল্য-লাভ
- repo-cron-স্তূপ-বিন্যাসে runner-চাপ-হ্রাস (P-F গ্রহণে)

### ২.৬ ক্ষতি/ঝুঁকি

- P-A-তে দ্বৈত-নির্বাহ (multi-worker ভবিষ্যতে) → idempotency-কী + এক-প্রক্রিয়া-সত্য-নথি; founder-gated মাপ-স্কেল
- sweep-অতি-দ্রুততায় চাপ → cadence-ডেটা + max-concurrent-সীমা
- P-D-স্থানান্তরে লুপ-বিঘ্ন → লুপ-প্রতি ধাপে + পুরনো-পথ-env-ফলব্যাক
- P-H-এ TZ-ভুল-গণনা → ZoneInfo-টেস্ট-ব্যাটারি; ডিফল্ট-UTC-স্থানান্তর-নীতি
- P-E fold-সিদ্ধান্তে ভবিষ্যৎ-প্রয়োজন → shim-রাখা (fold≠অপসারণ)

## Part 3 — Out of Scope

- run-fabric-সেমান্টিকস (Module 06); অনুমোদন-TTL-নির্দিষ্ট-ডিজাইন (Module 17 P-G)
- বিজ্ঞপ্তি-বাহক-ডিজাইন (Module 20); i18n (Module 19); telegram-লুপ (Module 18)
- APScheduler/Celery/নতুন-সাইডকার-আদান; workflow-ফাইল-সম্পাদনা (P-F শুধু প্রস্তাব)
- মিশন-কন্ট্রোল-নিজস্ব TS-শিডিউলার (পৃথক অ্যাপ)

## Part 4 — ৯-নিয়ম ও Constitution-সংগতি

| নিয়ম | এই নীলনকশার অবস্থান |
|---|---|
| Single-plan execution | প্রস্তাব-পাইপলাইন; একসময়ে একটিই active (P-A প্রথম) |
| Evidence-first | file:line; ৩য়-পক্ষ তারিখ-চিহ্নিত |
| Extend-not-replace | supervisor-গ্রাহক; S10-store পুনঃব্যবহার; ERR-F02 |
| Founder gates | P-C নীতি/P-F cron-বিন্যাস Gate 2-পরবর্তী |
| Zero-false-positive | sweep-টেস্ট ত্রি-পথ; idempotency |
| Zero-cost | stdlib-শুধু; APScheduler-প্রত্যাখ্যান-নথিভুক্ত |
| Branch discipline | docs-only; execution আলাদা ব্রাঞ্চ+PR |

## Part 5 — Verification & Rollback

- **Gate 4 (proof)**: P-A due/disabled/catch-up/idempotency টেস্ট; P-B ফিল্ড-চুক্তি-টেস্ট; P-D শাটডাউন-ক্লিন-আপ-টেস্ট; P-H TZ-টেস্ট-ব্যাটারি; P-C policy-fail→last-known-good
- **Gate 5 (measurement)**: catch-up-সংখ্যা (হারানো→০); ফাঁকা-কলাম-গণনা (→০); স্পন্দন-লেটেন্সি-পি৯৫; repo-cron-স্তূপ-মাত্রা
- **Gate 6 (rollback)**: sweep disable-env; P-D লুপ-প্রতি পুরনো-পথ-ফলব্যাক; প্রতিটি P এক-ফাইল-রোলব্যাক

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Audit)

| প্রস্তাব | Zero Cost | Lightweight | Fast Smooth | Zero Hardcode |
|---|---|---|---|---|
| P-A স্পন্দন+ক্যাচআপ | ✓ stdlib | ✓ এক-লুপ | ✓ hot-path-বাইরে | ✓ cadence-ডেটা |
| P-B চুক্তি-সত্য | ✓ | ✓ | ✓ | ✓✓ |
| P-C নীতি-ডেটা | ✓ | ✓ | ✓ | ✓✓ |
| P-D এক-হৃদয় | ✓ | ✓✓ কম-প্রক্রিয়া | ✓ | n/a |
| P-E নিয়তি | ✓ | ✓ | ✓ | n/a |
| P-F cron-বিন্যাস | ✓ | ✓ | ✓ runner-চাপ-হ্রাস | n/a |
| P-G সেতু | ✓ | ✓ | ✓ async | n/a |
| P-H TZ-সত্য | ✓ stdlib-ZoneInfo | ✓ | ✓ | ✓ প্রতি-ব্যবহারকারী |
| APScheduler/Celery প্রত্যাখ্যান | ✓✓ | ✓✓ | ✓ | n/a |

**জন্মগত-সংগতি-ঘোষণা**: নতুন-ইঞ্জিন-কেনা-নয়, বিদ্যমান-হৃদয়ে-স্পন্দন — চার-স্তম্ভের সবচেয়ে সারলীকৃত প্রকাশ; cron-গর্ত-গবেষণা ক্যাচআপ-নকশাকে শিল্প-প্রমাণে ভিত্তি-করে।

## Part 6 — পরবর্তী মডিউল লাইনেজ

- **চক্র ২৩-প্রার্থী**: knowledge-base/docs-অঙ্গ বা importer/exporter-পরিবার — ৩য়-পক্ষ-প্রস্তুতি: RAG-ingest-প্যাটার্ন, ডক-ছাঁট-নীতি
- **চক্র ২৪-প্রার্থী**: Gate 5-পরিমাপ-ভিত্তিক কিউ-পুনঃর‍্যাঙ্ক + প্রথম execution-চক্রের প্রস্তাব (ফাউন্ডার-অনুমোদিত P-গুলোর মধ্যে সর্বোচ্চ-লাভ/সর্বনিম্ন-ঝুঁকি নির্বাচন — সিরিজ-বিশ্লেষণ→সম্পাদন-রূপান্তরের প্রস্তুতি)
- প্রতিটি চক্র ৩য়-পক্ষ-গবেষণা-চুক্তি বহাল
