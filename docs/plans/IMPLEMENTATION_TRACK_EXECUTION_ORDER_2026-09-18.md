---
id: implementation-track-execution-order
subject: "Issue #453 Implementation Track — প্রমাণ-ভিত্তিক এক্সিকিউশন অর্ডার: ২৩ মডিউলের কোড-সত্য রিকনসিলিয়েশন, মালিকানা ডি-ডুপ্লিকেশন এবং ওয়েভ-ভিত্তিক বাস্তবায়ন ক্রম"
document_role: roadmap
owner_circle: Planning Circle / Head of Planning (docs/plans/ প্ল্যানিং কর্পাসের ধারাবাহিক মালিক)
status: active
target_scope: supremeai_internal
canonical: true
evidence_state: verified
disposition: retain
last_verified: 2026-09-18
supersedes: []
superseded_by: []
source_of_truth: true
---

# Issue #453 — প্রমাণ-ভিত্তিক এক্সিকিউশন অর্ডার (Evidence-Based Execution Order)

**Method (Gate-0 পদ্ধতি):** ২৩টি Crown Jewel মডিউল + Teleport প্ল্যান সম্পূর্ণ পাঠ → fresh main
(`4ac43642`) থেকে প্রতিটি দাবির কোড-যাচাই (file:line evidence)। এই ডকুমেন্টটি issue #453-এর
tier ordering-কে কোড-সত্যের সাথে reconcile করে এবং মালিকানা দ্বন্দ্ব মেটায়।

## ১. ক্রস-ডকুমেন্ট নাম-ড্রিফট সংশোধন (canonical module map)

`.agents/prompts/MASTER_KICKOFF_PROMPT.md` §7-এ কয়েকটি মডিউল-পরিচয় ভুল ছিল; সংশোধিত
ক্যানোনিক্যাল ম্যাপিং (frontmatter title অনুযায়ী):

| Module | Canonical identity (ভুল দাবি → সত্য) |
| --- | --- |
| M03 | **LLM Gateway & Model Routing** — 3-Tier GPU + Zero-Bypass এখানেই (ভুলভাবে M17-কে দেওয়া হয়েছিল) |
| M05 | **Self-Evolution & Learning Loop** (ভুলভাবে M12-কে "Self-Evolution" বলা হয়েছিল) |
| M07 | **Context Engine** (ভুলভাবে "Multi-Agent Swarm" — সেটি M02 Orchestration) |
| M12 | **Governed Skill Ecosystem** |
| M17 | **HITL & Approval Chain** (ভুলভাবে "3-Tier GPU" বলা হয়েছিল) |
| M22 | **Scheduler & Cron Organ** (supervisor heartbeat — "Autonomous SRE" নয়) |
| M18 | **Telegram Integration Organ** |

## ২. কোড-সত্য রিকনসিলিয়েশন (issue-এর tier order বনাম বাস্তবতা)

Issue #453 Tier-1-এর ১ নম্বরে থাকা **Supreme Teleport-এর কোড ০%** (শুধু plan; acceptance gate
নেই) — অথচ শক্তিশালী ভিত্তি অন্য জায়গায় প্রমাণিত:

- **HITL (M17):** ৩টি টেস্টেড সারফেস, atomic + tamper-proof state machine — সবচেয়ে শক্ত ভিত
- **LLM Gateway core (M03):** ১,৬১৬ LOC প্যাকেজ + ১,০০১ LOC টেস্ট (শুধু accounting contracts নেই)
- **Telegram organ (M18):** fail-closed secret-token webhook মাউন্টেড + টেস্টেড (শুধু `/abort` নেই)
- **Tier-S S1–S12 (M10):** ১২ backend router + migration + ৮ component তৈরি — শুধু অর্ধেক মাউন্টেড
- **Billing spine (M16):** wallet + ledger + idempotent webhook + fail-closed Redis mutex

## ৩. মালিকানা ডি-ডুপ্লিকেশন (এক দাবি, এক মালিক)

| Duplicated scope | Claimed by | Single owner |
| --- | --- | --- |
| Zero-bypass inference CI gate | M03 P0, M11 P-G, M15 P-I, M21 P-I | **M03** (contract) + **M11** (enforcement) |
| CancellationToken / `/abort` | M02, M06, M12, M18, Teleport | **M02** |
| 6x Kaggle canary handover | M03 §2.4.3, M22 P-I | **M03** (M22 only consumes heartbeat) |
| Bengali token estimator | M07 P-E, M19 P-D | **M19** (`bengali_text.py`) |
| tenant_rate_limiter fail-mode | M13, M15, M16 | **M15** (limiter authority), M13 config-izes |

## ৪. ওয়েভ-ভিত্তিক এক্সিকিউশন অর্ডার (benefit-per-effort × dependency)

**Wave 1 — দৃশ্যমান জয় (built-but-unwired জমাগুলো ফেরত চালু): ✅ সম্পন্ন (2026-09-18, commits 15ec3bc2/07991802/1a78db30/39bde84f):**
- **M10 P-A/P-B (Frontend Tier-S)** ✅: ChatInterface host মাউন্ট (`/chat` রুট +
  nav), ভুয়া `"current_conv"` প্লেসহোল্ডার সত্য ক্লায়েন্ট conversation_id দিয়ে প্রতিস্থাপন
  (backend ConversationCommand ক্লায়েন্ট-সরবরাহকৃত id গ্রহণ করে — `gateway_center.py:79`),
  S2 ThinkingPanel + S3 ArtifactsPanel মাউন্ট, `/prompt-library` nav truth, integration-guide
  প্যাথ-সত্য সংশোধন। টেস্ট: ৫টি নতুন চুক্তি-টেস্ট, frontend 532/532।
- **M16 P-A:** ✅ gateway/chat path-এ `record_spend` ফিড (spend_meter.py — streaming parity সহ) → ড্যাশবোর্ডের চিরস্থায়ী $0 সত্য হয়।
- **M20 P-B:** ✅ `/ws/dashboard` subscription-task জীবনচক্র ফিক্স।
- **M22 P-A:** ✅ due-task sweep (core/scheduled_task_sweep.py) — CAS দাবি + stale-পুনর্গ্রহ + restart-ক্যাচআপ; custom-cron সৎ-অসমর্থন (P-A সীমা); ১৭ টেস্ট।
- **M18 P-I:** ✅ `/abort <run_id>` (admin-only, প্রকৃত run_service.cancel) + ভুয়া /telemetry KPI → লাইভ পাঠ (supervisor health + সচল রান); CancellationToken গভীর-প্রপাগেশন M02 মালিকানায়।

**Wave 2 — ব্যাকবোন: ✅ সম্পন্ন (2026-09-18, commits bd0ab63a/3cba9cbe/0fcc1058/62fd5942):**
- **M23 P-A/P-C:** ✅ governance `__init__`-এ পুনরুত্থান (প্রতি-কলে 500 অবসান + case-mismatch 403 ফিক্স); coldstart→importer adapter — ১৩২-এন্ট্রি validate-clean (১১৮ বাংলা উত্তর), HITL draft-গেট, importer secret-scanner precision-ফিক্স।
- **M02 P-B (ERR-F01):** ✅ observe_task_run bridge + sweep-বাস্তব integration (রান REQUESTED→RUNNING→terminal সিল; observation-ব্যর্থে নির্বাহ-অব্যাহত, লাউড-লগ)।
- **M03 P0+P1+P2:** ✅ InferenceContext চুক্তি (context.py), স্ট্রাকচার্ড এরর ডোমেইন (errors.py), competitive_kit ভুয়া "[Response from …]" → গেটওয়ে-ডেলিগেশন, model_router "Hello World" → স্ট্রাকচার্ড এরর + সৎ SSE error-event, zero-bypass downward-ratchet গেট (বেসলাইন 0); streaming cost-parity M16 P-A-র সাথে ল্যান্ডেড। **P0 পূর্ণাংশ (2026-09-18):** ১৩ serving route-ফাইলের ১৪টি inference কল-সাইটে `context=InferenceContext(...)` বাধ্যতামূলক (chat/task_workspace/reasoning/slash_commands×3/stream_chat_sse×2/scheduled_tasks/browser_routes/deep_research/websocket_agent×2) — latency-বাগ ফিক্স: browser_routes-এর `llm_gateway.complete()` কলটি রানটাইম AttributeError দিত (গেটওয়েতে মেথডটিই নেই) → সত্য চুক্তিতে স্থানান্তর; নতুন ratchet গেট `scripts/ci/check_gateway_context.py` (বেসলাইন 0, pytest-wrapper CI-enforced)।

**Wave 2 পরবর্তী নোট:** উপরের ফিক্সগুলোতে vitest 532/532 (102 files), missions 62/62, STATUS_PROOF PASS অটুট — বেসলাইন পরিবর্তন হয়নি।

**Wave 3 — সত্য-স্তর (cheap governance credibility): আংশিক — M05 P-A সম্পন্ন (bf315947 + দ্বিতীয় অর্ধ):**
- **M05 P-A:** ✅ ENABLE_LEARNING_LOOP ডিফল্ট true (শূন্য-খরচ লুপ, HITL-only apply) + .env.example দৃশ্যমানতা। **দ্বিতীয় অর্ধ (2026-09-18):** ✅ exploration গেট সুইটেবল-ডিফল্ট true (`get_adaptive_routing_enabled` — শূন্য-অতিরিক্ত-খরচ চেইন-লেজ অন্বেষণ) + sample-tier guardrail (`exploration_candidate` কেবল normal-tier ≥50-observation প্রমাণে যায়; cautious/insufficient কখনো নয়) + kill-switch অক্ষত (false = আজকের আচরণ) + অজানা-মান fail-closed।
- **M13 (S):** ✅ সম্পন্ন (2026-09-18) — P-B zero-hardcode: `_tier_limits`/tenant 100-60s/OTP-pending 300s/warn-ratio 0.8/acquire ডিফল্ট-সব config-চালিত (ডিফল্ট অপরিবর্তিত, আচরণ-নিরপেক্ষ); P-C tenant-resilience: `TENANT_RATE_LIMIT_FAIL_MODE` config (open=ডিফল্ট আজকের আচরণ / fallback=বাউন্ডেড InMemoryFallbackLimiter-প্যাটার্ন / closed=429 fail-closed) — V5.1 env-aware fail-policy ধারা; অজানা-মান loud-open (নীরব পছন্দ নিষিদ্ধ)। middleware truth-map নিজে প্ল্যান-নথিতে ক্যানোনিকাল; P-A মাউন্ট-সিদ্ধান্ত founder-gated (ফাউন্ডার সিদ্ধান্তের অপেক্ষায়)।
- **M14 (S):** ✅ সম্পন্ন — P-A সৎ-সেমান্টিকস ও P-B SSE re-point ইতোমধ্যে ছিল (issue #445: জাল transcript/RIFF-বাইট প্রত্যাহার → Groq Whisper STT + edge-tts TTS বাস্তব পথ + unavailable-সেমান্টিকস; stream_voice_sse সৎ error-event); **P-C শূন্য-ব্যয় প্রথম-পথ (2026-09-18):** `webSpeechCapability.ts` — ব্রাউজার Web Speech capability-detection (TTS+STT, সৎ unsupportedReason); AudioPlaybackService fail-safe (নিখোঁজ speechSynthesis-এ crash → সৎ `ttsSupported=false` + play() স্পষ্ট false); ChatInterface TTS-ব্রাউজার-প্রথম (speechSynthesis উপলব্ধ হলে backend-ব্যয় শূন্য, অনুপস্থিতে backend fallback, কোনোটাই না হলে স্পষ্ট অসমর্থন-বার্তা); f32cc25b-এর typecheck-ভাঙা DeepResearchPanel TS-narrowing ফিক্স। vitest 538 (103 files)।

**Wave 4 — ভারী গঠন (তখনই যখন Wave 2-এর ভিত দাঁড়িয়েছে):**
- M01 memory consolidation, M06 ৮/৮ RunType adoption, M07 context budget, M08 SSE চুক্তি ফিক্স,
  M09 ReAct loop, M17 seven→one, M19 language loop, M11 architecture graph।
- **Supreme Teleport:** সর্বশেষ — এটি M18+M17+M06+M04-এর **composition**; আগে ভিতগুলো লাগবে।
  এর প্ল্যানে acceptance gate retrofit করা হয়েছে (এই commit-এ)।

## ৫. বেসলাইন আপডেট (এই ওয়েভ থেকে)

| Gate | আগে | এখন |
| --- | --- | --- |
| frontend vitest | 527 (101 files) | **532 (102 files)** — M10 চুক্তি-টেস্ট যোগ |
| frontend tsc (সঠিক গেট) | — | `tsc -p tsconfig.app.json --noEmit` = 0 errors |

⚠️ **গেট-সত্য সতর্কতা:** root `tsconfig.json` `"files": []` + references — ফলে খালি
`npx tsc --noEmit` **কিছুই চেক করে না**। প্রকৃত গেট: `pnpm typecheck`
(`tsc -p tsconfig.app.json --noEmit`)। CI ও golden loop-এ এটিই ব্যবহার করতে হবে।

## ৬. শৃঙ্খলা

প্রতি ওয়েভ = একাধিক atomic PR; প্রতি PR = এক মডিউলের এক phase (Plan → Code → Test →
Verification → Close Checkbox, issue #453 Rule #2)। ভুয়া "implemented" দাবি নিষিদ্ধ —
checkbox কেবল CI-প্রমাণিত অবস্থায় বন্ধ হবে।
