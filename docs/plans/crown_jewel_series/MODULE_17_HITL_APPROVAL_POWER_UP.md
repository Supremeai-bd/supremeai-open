---
id: crown-jewel-module-17-hitl-approval-power-up-2026-09-17
title: "Crown Jewel Module Series — Module 17: HITL & Approval Chain Power-Up (মানব-অনুমোদন চেইন: ৭টি প্রতিযোগী স্টেট-মেশিন, নির্বাহক-বিহীন 'approved', জাল OTP — 'এক-সেতু-সাত-দরজা' মতবাদে পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Governance Circle (backend/services/hitl/ + backend/api/routes/approval_manager.py + hitl_admin.py — মানব-অনুমোদন অঙ্গ)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ১৭ — একটি মডিউল (HITL/অনুমোদন চেইন), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field); Part 1 = গভীর ৩য়-পক্ষ বুদ্ধিমত্তা (LangGraph interrupt+checkpointer, Temporal Approval Pattern, n8n Wait/resume-URL, four-eyes principle); branch crown-jewel-v2 base 7492f54e-এ spot-checkকৃত কোড-প্রমাণ"
depends_on:
  - "৭টি প্রতিযোগী অনুমোদন-স্টেট-মেশিন: services/hitl/engine.py (১৪৮ লাইন, HITLEngine, Firestore pending_approvals) / models/pending_tasks.py (৪৫৬ লাইন হার্ডেনড, create_pending_task শূন্য production কলার) / adaptive_engine/approval_workflow.py (৪৬৮ লাইন, ecosystem-স্কোপড জীবিত) / admin_dashboard/endpoints_approvals_mcp.py (MCP-প্রক্সি) / runs/hitl.py (hook=None, runs/api.py L45) / agents/governance/governance_agent.py (৫৮৪ লাইন সম্পূর্ণ dormant) / evolution CodeProposal (+ self_healer pending_review) — একটিরও ভাগ্য-নির্ধারণ নেই"
  - "দুটি সক্রিয় route-shadowing: approval_manager.py (২৫৬ লাইন, routers.py L314, AUD-4-হার্ডেনড trio) এর ৩/৫ রুট hitl_admin.py (৬৬ লাইন)-এর সংঘর্ষ-পাথ দ্বারা ছায়া-আচ্ছাদিত — শুধু /cancel + WS /ws/hitl পৌঁছায়; endpoints_approvals_mcp.py init-ক্রমে (L417 vs L426) pending-task-জোড়কে ছায়া-আচ্ছাদিত করে"
  - "ভাঙা-হাতবদল (মূল-আবিষ্কার): একমাত্র বাস্তব উৎপাদক-চেইন (auto_skill_creator L546) self.db=None পাস করে → HITLEngine.suspend_for_approval engine.py L40-এ crash (None.client) — governance+integrity পাসের পরে RuntimeError; আর যদি কাজও করত, hitl_admin.approve শুধু Firestore status-ফ্লিপ করে — 'approved' খেয়াল করে চালানো-নির্বাহক (executor) শূন্য (grep-প্রমাণিত)"
  - "জাল-নিয়ন্ত্রণ: frontend OTP পাঠায়; backend approval_manager.py L55-এ otp ঘোষণা করে এবং কখনোই যাচাই করে না — V5 fake-metrics মতবাদের নতুন প্রকাশ (fake control surface)"
  - "নমিনাল-লেজার: hitl_ledger.py L53-66 প্রতি-ব্লক SHA-256 চেইন বাস্তব, কিন্তু verify_chain_integrity/compute_merkle_root (cryptographic_ledger.py L86-101)-এর শূন্য কলার এবং কেবল in-memory chain পরীক্ষা করে যা HITLAuditLedger কখনো পূরণই করে না → সর্বদা True; init-ব্যর্থতায় index রিসেট 0 (নীরব চেইন-ফর্ক, L42-44); save-ব্যর্থতা log+continue (L75-76)"
  - "জীবনচক্র-শূন্যতা: pending_tasks 24h TTL কেবল decision-time-এ (L410); কোনো sweep-জব নেই → মেয়াদোত্তীর্ণ সারি চির-কাল PENDING; HITLEngine-পথে TTL নেই-ই; কোথাও auto-deny/auto-approve-on-timeout নেই"
  - "নীরব-পোলিং-নোটিফিকেশন: websocket_hitl.py (১৭৫ লাইন) routers.py L150-এ কমেন্ট-করা (dormant, টেস্টেড-কিন্তু-আনমাউন্টেড); stream_hitl_sse.py মাউন্টেড (L152) কিন্তু শূন্য frontend গ্রাহক; Telegram admin_handlers-এ কোনো approval-handler নেই; email নেই — অনুমোদককে কিউ-পোলিং ছাড়া কিছুই জানায় না"
  - "frontend চুক্তি-ভাঙা: ApprovalQueue.tsx (৭৬ লাইন, routed WorkspaceViewport L41,74 + AdminSubTab L78) 15s-পোল /api/v1/hitl/pending — কিন্তু বাস্তব রেকর্ডে status 'pending_approval' ≠ UI-গেট status==='pending' → বাস্তব-ডেটায় action-button কখনো রেন্ডার হয় না; HITLModal.tsx + HumanInTheLoopProtocol.tsx শূন্য-ইমপোর্টার (শেষোক্ত ক্লায়েন্ট-সাইডে জাল audit-trail বুনে L50-57)"
  - "hardcode-জরিপ: pending_tasks.py L22 TTL 24*60*60; approval_workflow.py L97-99 +24h, L125 cooldown 3600, L69-75 _MANDATORY_APPROVAL সেট; websocket_hitl.py L136 roles ['admin','supervisor'], L18 WS_MAX_CONNECTIONS=50; approval_manager.py L89-91 audit TTL 86400*30 + ltrim 999; self_healer.py L158 AUTO_APPLY_THRESHOLD=0.4"
  - "৩য়-পক্ষ গবেষণা-ভিত্তি (2026-02-17 ওয়েব-প্রমাণ): LangGraph interrupt+checkpointer (docs.langchain.com — interrupt/resume-দ্বিপদ, checkpointer-বাধ্যতামূলক); Temporal Approval Pattern (docs.temporal.io — Workflow Signal-এ ব্লক, Query-তে অবস্থা); n8n Wait node (docs.n8n.io — resume-URL জেনারেশন + webhook-ফিরত); four-eyes principle (flagsmith.com/t2informatik — দ্বৈত-নিয়ন্ত্রণ গভর্নেন্স-নিয়ম)"
implements:
  - "এক-সেতু-সাত-দরজা মতবাদ (অস্বাভাবিক-চিন্তার কেন্দ্র): ৮ম স্টেট-মেশিন নয় — একক ক্যানোনিকাল store + একক dispatch-table; প্রতিটি উৎপাদক পাতলা adapter/শিম দিয়ে সেতুতে (ERR-F02-সংগত)"
  - "resume-URL টোকেন প্যাটার্ন (n8n ধার): প্রতিটি pending-এর জন্য স্বাক্ষরিত এক-ক্লিক resume-URL — SSE/Telegram/email সব ঐচ্ছিক-বাহক একই URL-এর; নোটিফিকেশন-ব্যবস্থা নয়, এক-টোকেন-তিন-বাহক"
  - "নির্বাহক-বিহীন 'approved' অবসান: dispatch-table (data-file: target_resource → handler) — অনুমোদন-পরবর্তী কার্যকরী-অর্ধ জন্ম"
  - "লেজার-সত্যায়ন: /hitl/ledger/verify readback endpoint + init-ফর্ক-নীরবতা সংশোধন — নমিনাল থেকে প্রমাণযোগ্য tamper-evidence"
  - "expired টার্মিনাল-অবস্থা + TTL sweep (env-চালিত auto-deny) — চির-PENDING অবসান; four-eyes ঐচ্ছিক-নীতি critical-risk-এ (data-file)"
  - "প্রত্যাখ্যান-নথি (anti-cargo-cult): LangGraph/Temporal লাইব্রেরি-সার্ভার নয় (নির্ভরতা/infra), Firestore-বিস্তার-নয়, পেইড-অনুমোদন-SaaS নয় — রেডিস/Firestore-বিদ্যমান-স্টোর + ডেটা-ফাইল-নীতিই যথেষ্ট"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (branch crown-jewel-v2 base 7492f54e: hitl engine/ledger পূর্ণপাঠ, approval_manager L55/L58-96/L89-91/L138-179, hitl_admin পূর্ণপাঠ, routers.py L150/L152/L270/L314, pending_tasks L22/L410, ApprovalQueue/HITLModal grep, telegram admin_handlers grep; ৩য়-পক্ষ দাবি 2026-02-17 ওয়েব-সার্চে তারিখ-চিহ্নিত)"
code_evidence:
  - "অনুমোদন-থিয়েটার-নির্ণয় — সংবেদনশীল-ক্রিয়া আজ অনুমোদন চাইলে: উৎপাদক crash (engine.py L40 db=None) → কেউ pending নয়; যদি pending হতো → approve status-ফ্লিপ-মাত্র → নির্বাহক শূন্য → কিছুই চলে না; একমাত্র বাস্তব নির্বাহক (approval_manager L138-179 AICodeValidator+realpath-guard) ছায়া-আচ্ছাদিত + উৎপাদক-শূন্য sqlite store পড়ে"
  - "টেস্ট-অন্ধত্বের কারণ — approval_manager-টেস্ট ফাংশন-সরাসরি ডাকে (shadowing ধরতে অক্ষম); websocket_hitl-টেস্ট আনমাউন্টেড router টেস্ট করে; tests/hitl/test_hitl_engine.py সম্পূর্ণ skipped (never-built app.services.hitl প্যাকেজ — সৎ নোট)"
  - "চেইন-ফর্ক-ঝুঁকি — ledger init-ব্যর্থতায় index-রিসেট-০: পুরনো চেইনের সাথে নতুন চেইন শাখা-বিভক্ত হয় নীরবে; verify-কলার-শূন্যে কেউ জানবেই না — readback endpoint-ই একমাত্র সস্তা প্রতিষেধক"
  - "দ্বৈত-নির্ভরতা-সতর্কতা — Firestore pending_approvals (HITLEngine) vs sqlite pending_tasks vs Redis: একক-store মতবাদে migration-পথ দুই-ধাপে (dual-read → cutover) — ERR-F02"
  - "resume-URL-এর আসন — hitl_admin approve এন্ডপয়েন্ট ইতিমধ্যে টোকেন-যোগ্য; স্বাক্ষরিত-URL-স্ট্যাম্প এক-ফাংশন-সংযোজন; Telegram-বাহকের জন্য admin_handlers-এ inline-keyboard approve-কলব্যাক এক-হ্যান্ডলার-সংযোজন — শূন্য নতুন অবকাঠামো"
test_evidence: "বিদ্যমান: approval_manager state-machine AUD-4.1-4.7 (168L কঠোর); websocket_hitl টেস্ট (আনমাউন্টেড-বস্তু); test_ws_auth shared-helper; hitl_engine টেস্ট skipped; প্রস্তাব-টেস্ট: shadowing-ownership (route-map টেস্ট), dispatch-table প্রতি-target টেস্ট, verify-endpoint টেম্পার-টেস্ট, TTL sweep টেস্ট, resume-URL স্বাক্ষর/মেয়াদ টেস্ট, status-স্ট্রিং চুক্তি-টেস্ট"
acceptance_criteria:
  - "প্রতিটি প্রস্তাব চার-স্তম্ভ-দর্শন-সংগত (Part 5.5)"
  - "৭→১ store-একীকরণ ERR-F02-সংগত (শিম-প্রথম, zero-caller-প্রমাণ-পূর্ব অপসারণ); কোনো নতুন নির্ভরতা/সার্ভিস নয় (512MB)"
  - "auto-deny-শুধু নীতি (auto-approve কখনোই ডিফল্ট নয়); সব TTL/roles/mandatory-set ডেটা-ফাইল+env"
  - "জাল-নিয়ন্ত্রণ-অবসান: OTP বাস্তব-যাচাই বা সৎ-অপসারণ — কোনো মাঝামাঝি নয়; লিন্ট 0 error / 0 warning (সিরিজ)"
---

# Module 17 — HITL & Approval Chain Power-Up (মানব-অনুমোদন চেইন)

## বাংলা সারসংক্ষেপ

অনুমোদন-অঙ্গ প্রকল্পের সবচেয়ে বিভ্রান্তিকর সত্য বহন করে: **সাতটি প্রতিযোগী অনুমোদন-স্টেট-মেশিন** আছে (HITLEngine, pending_tasks ৪৫৬-লাইনের হার্ডেনড স্টোর, adaptive workflow, MCP-প্রক্সি, runs-hook, governance_agent, evolution proposals) — অথচ **একটিরও সম্পূর্ণ জীবনচক্র নেই**: একমাত্র বাস্তব উৎপাদক `db=None` পাস করায় crash করে; অনুমোদন হলে তা ফ্লিপ-হয় কিন্তু **'approved' খেয়াল করে চালানো কেউ নেই**; backend OTP **ঘোষণা করে, যাচাই করে না**; frontend-এর action-button status-স্ট্রিং-অমিলে কখনো রেন্ডার হয় না। এই নীলনকশার মতবাদ: **এক-সেতু-সাত-দরজা** — ৮ম মেশিন নয়; একক ক্যানোনিকাল store + dispatch-table, প্রতিটি পুরনো পথ শিমে। আর নোটিফিকেশনের জন্য শিল্পের সবচেয়ে সস্তা দান: **resume-URL টোকেন** (n8n প্যাটার্ন) — এক স্বাক্ষরিত URL, তিন ঐচ্ছিক বাহক (SSE/Telegram-keyboard/email); নতুন অবকাঠামো শূন্য। লেজার নমিনাল থেকে প্রমাণযোগ্যে (verify readback), চির-PENDING থেকে expired-টার্মিনালে, জাল-OTP থেকে সৎ-অবস্থায়।

## Part 1 — Third-Party & Competitor Intelligence (৩য়-পক্ষ বুদ্ধিমত্তা, তারিখ-চিহ্নিত ওয়েব-প্রমাণ)

### ১.১ গ্রহণযোগ্য প্যাটার্ন (গ্রহণ — প্যাটার্ন হিসেবে, নির্ভরতা নয়)

| উৎস (তারিখ) | ধারণা | আমাদের অঙ্গে প্রয়োগ | চার-স্তম্ভ-বিচার |
|---|---|---|---|
| **LangGraph interrupt + checkpointer** (docs.langchain.com, 2026) | interrupt() → বিরতি; resume-এ অবস্থা-পুনরুদ্ধার — checkpointer **বাধ্যতামূলক**: বিরতি-পরবর্তী অবস্থা স্থায়ী-স্টোরে | এক-সেতুর মূল-ন্যায্যতা: pending-অবস্থা ক্যানোনিকাল-স্টোরে স্থায়ী হতে হবে (pending_tasks ৪৫৬-লাইন হার্ডেনড-স্টোরই তৈরি-প্রস্তুত); interrupt/resume-দ্বিপদ API-শেপ আমাদের suspend/resolve-এ প্রতিফলিত হবে | লাইব্রেরি-প্রত্যাখ্যান, শেপ-গ্রহণ ✓ |
| **Temporal Approval Pattern** (docs.temporal.io) | Workflow Signal-এ ব্লক-হয় যতক্ষণ বাহ্যিক সিদ্ধান্ত; Query-তে অবস্থা; durability-নিশ্চয়তা | approve = সিগনাল-অভিন্ন-সিমান্টিকস (resolve-কল); অবস্থা-জিজ্ঞাসা = status-এন্ডপয়েন্ট; schedule-to-close-timeout → auto-deny সিমান্টিকস (P-G expired-অবস্থা) | সার্ভার-প্রত্যাখ্যান (infra), সিমান্টিকস-গ্রহণ ✓ |
| **n8n Wait node** (docs.n8n.io, 2026-07) | Wait নোড **resume-URL জেনারেট** করে — webhook/form/কোনো-বাহকেই ফেরা যায় | **মূল-ধার (P-E)**: প্রতি pending-এ স্বাক্ষরিত one-click resume-URL; SSE + Telegram inline-keyboard + email সব ঐচ্ছিক-বাহক একই URL-এর — নোটিফিকেশন-সিস্টেম নয়, টোকেন-স্ট্যাম্প | zero-cost ✓✓; hot-path-শূন্য ✓ |
| **Four-eyes principle** (flagsmith/t2informatik) | ক্রিটিক্যাল-ক্রিয়ায় দ্বৈত-অনুমোদন গভর্নেন্স-নিয়ম | P-G-র data-file-নীতি: risk-tier→min_approvers ম্যাপ (critical-এ ২, বাকি ১) — tool_gateway RISK_LEVELS-সংগত, ডিফল্ট নিষ্ক্রিয় (founder-gated) | ডেটা-ফাইল-নীতি ✓ |

### ১.২ প্রত্যাখৃত বিকল্প (কারণ-সহ)

| বিকল্প | কেন নয় |
|---|---|
| **LangGraph/Temporal লাইব্রেরি/সার্ভার-আদান** | হেভি-নির্ভরতা + চলমান-সার্ভার (512MB-লঙ্ঘন); আমাদের নিজস্ব store+dispatch-ই ক্ষুদ্র-স্কেলে সঠিক |
| **Firestore-বিস্তার-নতুন-কালেকশন-স্থাপত্য** | আরও-স্টোর = আরও-দরজা; মতবাদই দরজা-কমানো |
| **পেইড-অনুমোদন/ওয়ার্কফ্লো-SaaS (Humanloop হোস্টেড, approveapi জাতীয়)** | zero-cost স্তম্ভ-লঙ্ঘন; মালিকানা-ঝুঁকি |
| **নতুন WS-হাব-নির্মাণ** | websocket_hitl ইতিমধ্যে লেখা+টেস্টেড কিন্তু আনমাউন্টেড — নির্মাণ নয়, mount-বা-shim সিদ্ধান্ত (P-A-র অংশ) |

### ১.৩ প্রতিযোগী-তুলনার অন্তর্দৃষ্টি (ভিন্নভাবে ভাবা)

শিল্পের HITL "এজেন্টকে থামিয়ে মানুষের অপেক্ষা" — খরচ: এজেন্ট-রিসোর্স দখল। আমাদের ভিন্ন-পথ: **অনুমোদনকে বার্তা বানানো, অপেক্ষা নয়** — pending = স্বাক্ষরিত-URL-সহ এক বার্তা; অনুমোদক যে-কোনো বাহকে এক-ক্লিকে সিদ্ধান্ত দেয়; এজেন্ট-রিসোর্স মুক্ত। "মানুষ এজেন্টের কাছে আসে না — বার্তা মানুষের কাছে যায়।" এই উল্টো-দিকই আমাদের বাংলা-প্রথম, মোবাইল-প্রথম ব্যবহারকারী-বাস্তবতার সাথে সংগত।

## Part 1.5 — Gate 0 Reconciliation

| লেগেসি-ডক | স্ট্যাটাস | সিদ্ধান্ত |
|---|---|---|
| docs/plans/features/autonomous_capability_creation... | historical | request_approval (L777) দাবি বাস্তবে crash — এই নীলনকশা সংশোধন-প্রস্তাবে (P-C); historical-রায় অটুট |
| docs/plans/UNIFIED_ECOSYSTEM_ARCHITECTURE_PLAN | active | L471-অনুমোদন-উল্লেখ এক-সেতু-মতবাদের সহিত; বিরোধ নেই |
| PLAN_TO_CODE_TRACEABILITY_MATRIX | active | **মিথ্যা-দাবি-ধরা**: runs-HITL 116/116 পাস দাবি করে যখন hook=None (runs/api.py L45) — matrix-রো-সংশোধন-প্রস্তাব এই নীলনকশার পরিসরে (লিপি), traceability-matrix সম্পাদনা তার নিজ-মালিকানায় |
| PRE_PRODUCTION_GO_LIVE_MASTER_TODO L754-791 | active | HITL checkbox সব-unchecked — **সৎ**; এই নীলনকশা সেই বক্স-পূরণের পথ-মানচিত্র |
| Module 05/06/14/15 (সিরিজ) | published | boundary: evolution-approve/run-semantics/voice-p2p/middleware-audit পুনঃ-অডিট নয়; approval_manager-এর ইনলাইন _audit নোট Module 15-এ ছিল — এখানে P-A-সংশোধনে অন্তর্ভুক্ত |

## Part 2 — Six-Field Analysis

### ২.১ কী আছে

- **এক বাস্তব-জীবিত কোণ**: adaptive_engine/approval_workflow.py (৪৬৮ লাইন) — ecosystem-স্কোপড, বাস্তব decision-memory + cooldown
- **তৈরি-প্রস্তুত হার্ডওয়্যার**: pending_tasks.py ৪৫৬-লাইন হার্ডেনড স্টোর (কেবল কলার-শূন্য); websocket_hitl লেখা+টেস্টেড (কেবল আনমাউন্টেড); stream_hitl_sse মাউন্টেড; cryptographic_ledger ব্যবহৃত hitl_ledger-এ
- ** routed frontend**: ApprovalQueue বাস্তব-রুটেড ১৫s-পোল-সহ
- **রাষ্ট্র-হার্ডেনড টেস্ট-সংস্কৃতি**: AUD-4.1-4.7 state-machine টেস্ট কঠোর (কেবল shadowing-অন্ধ)

### ২.২ কী নেই

- **সম্পূর্ণ জীবনচক্র** — উৎপাদক-crash, নির্বাহক-শূন্য, চির-PENDING (কোনো sweep নেই)
- **একক ক্যানোনিকাল store** — ৭ মেশিন + ২ সক্রিয় route-shadowing
- **বাস্তব নোটিফিকেশন** — WS আনমাউন্টেড, SSE-গ্রাহক-শূন্য, Telegram/email-হ্যান্ডলার-শূন্য
- **প্রমাণযোগ্য লেজার** — verify-কলার-শূন্য, init-ফর্ক-নীরব, in-memory-only পরীক্ষা
- **সৎ-নিয়ন্ত্রণ** — OTP-ঘোষিত-অযাচাইকৃত; frontend status-স্ট্রিং-অমিলে বোতাম-অরেন্ডারেবল
- **নীতি-ডেটা** — TTL/roles/mandatory-set/cooldown/threshold সব ইন-কোড

### ২.৩ কী করতে হবে

আটটি প্রস্তাব (ক্রম ঝুঁকি-অবনম→সম্পূর্ণতা; সব ফাউন্ডার-রিভিউযোগ্য):

- **P-A**: route-shadow সংশোধন + ownership-টেস্ট — hitl_admin-বনাম-approval_manager পাথ-সংঘর্ষ নির্ধারণ (ক্যানোনিকাল নথিভুক্ত), endpoints_approvals_mcp init-ক্রম-সংশোধন; route-map টেস্টে shadowing আর অদৃশ্য নয়
- **P-C (দুই-লাইন, প্রথমেই)**: db=None হাতবদল-সংশোধন (auto_skill_creator L546) — উৎপাদক-চেইন জীবন্ত
- **P-B**: নির্বাহক-জন্ম — dispatch-table (data-file: target_resource → handler) approve-পরবর্তী কার্যকরী-অর্ধ; বিদ্যমান AICodeValidator+realpath-guard প্যাটার্ন পুনঃব্যবহৃত
- **P-D**: একক-store মতবাদ — pending_tasks ক্যানোনিকাল; HITLEngine/governance_agent-পথ শিমে; adaptive-workflow ecosystem-ভাগ প্রসারিত-সহিত; dual-read→cutover
- **P-E**: resume-URL সেতু (n8n-ধার) — স্বাক্ষরিত one-click approve/deny URL; SSE-গ্রাহক ApprovalQueue-তে; Telegram inline-keyboard approve-কলব্যাক (admin_handlers-এ এক-হ্যান্ডলার); সব ঐচ্ছিক-বাহক, এক-টোকেন
- **P-F**: /hitl/ledger/verify readback + init-ফর্ক-সংশোধন (নীরব index-রিসেট অবসান) — tamper-evidence প্রমাণযোগ্য
- **P-G (TTL sweep, নীতি-ফাইল ও প্রস্তাব সংরক্ষণ ডকট্রিন)**: 
  - rails-as-data নীতি-ফাইল (TTL/roles/mandatory-set/cooldown/threshold/four-eyes-ঐচ্ছিক)।
  - **AGENTS.md Section 3 মান্যতা — Approval timeout is not automatic rejection of good ideas:**
    - মানুষের অনুপস্থিতি বা টাইমআউটের কারণে গুরুত্বপূর্ণ কোনো উন্নয়নমূলক আইডিয়া বা টাস্ক যাতে চিরতরে হারিয়ে না যায়, সিস্টেম স্বয়ংক্রিয়ভাবে তার প্রস্তাব, এভিডেন্স, টেস্ট রেজাল্ট এবং পরবর্তী প্রস্তাবিত পদক্ষেপ একটি টেকসই আর্কাইভে (`expired_proposals_archive`) সংরক্ষণ করবে।
    - উচ্চ-ঝুঁকির ক্ষেত্রে টাইমআউটে আনঅথোরাইজড এক্সিকিউশন স্টপ থাকবে (Fail-Safe), কিন্তু মূল্যবান কাজ সাইলেন্টলি ড্রপ না হয়ে অ্যাডমিন ফিরে আসা পর্যন্ত সংরক্ষিত থাকবে।
- **P-H**: frontend-সত্য — status-স্ট্রিং-চুক্তি সংশোধন; জাল-OTP সত্য-যাচাই বা সৎ-অপসারণ (V5-মতবাদ); HITLModal/HumanInTheLoopProtocol নিয়তি-সিদ্ধান্ত (জাল-audit-trail-বিশিষ্ট ক্লায়েন্ট-ফেব্রিকেটর প্রথম-অপসারণ-প্রার্থী)

### ২.৪ কীভাবে করব

ক্রম P-A→P-C→P-B→P-H→P-F→P-G→P-D→P-E (P-E শেষে — সেতু ক্যানোনিকাল-পথের উপরেই দাঁড়ায়); প্রতিটি P = আলাদা ছোট execution-প্ল্যান (Gate 2-পরবর্তী); P-A-তে ownership-টেস্ট-প্রথম; P-D-তে dual-read→cutover (ERR-F02); P-E-তে টোকেন-স্বাক্ষর-মেয়াদ-টেস্ট; সব env V5.1-সংগত; baseline-N র‍্যাচেট (নতুন অনুমোদন-স্টেট-মেশিন = fail)

### ২.৫ বেনিফিট

- প্রথমবারের মতো **সম্পূর্ণ** অনুমোদন-চক্র: চাওয়া → জানানো → এক-ক্লিক সিদ্ধান্ত → সত্যিকারের চালানো
- অনুমোদক-মুক্তি: পোলিং-নয়, বার্তা-মানুষে-যায় (মোবাইল/টেলিগ্রাম-প্রথম বাস্তবতা)
- টাইমআউটে মূল্যবান প্রপোজাল ও টেস্ট এভিডেন্স সংরক্ষণ — সময় নষ্ট বন্ধ (P-G)
- চির-PENDING-অবসান → গভর্নেন্স-মেট্রিক (সিদ্ধান্ত-লেটেন্সি পরিমাপযোগ্য)
- tamper-evidence দাবি ↔ প্রমাণ একরেখায়; জাল-নিয়ন্ত্রণ-অবসান
- ৭-মেশিনের রক্ষণ-বোঝা → ১ (কম-কোড, কম-বাগ-পৃষ্ঠ)

### ২.৬ ক্ষতি/ঝুঁকি

- P-D-স্থানান্তরে অবস্থা-হারানো → dual-read + parity-টেস্ট + ধাপে-ধাপে cutover
- P-E-তে টোকেন-ফাঁস → স্বল্প-মেয়াদ + এককালীন-ব্যবহার + স্কোপড-সিদ্ধান্ত (শুধু ওই pending)
- P-G-তে auto-deny-ভুল-পরিসর → ডিফল্ট deny-on-timeout সৎ + নীতি-ফাইলে প্রতি-tier; founder-gated যেকোনো auto-approve (ডিফল্ট কখনোই নয়)
- P-B dispatch-ভুল-ম্যাপ → টেস্টেড data-file + অজানা-target হলে fail-closed loud
- P-H অপসারণে হঠাৎ-নির্ভরতা-আবিষ্কার → zero-importer-প্রমাণ-পূর্ব (ERR-F02)

## Part 3 — Out of Scope

- evolution-approve-অভ্যন্তর (Module 05); run-fabric pause/resume (Module 06)
- voice/p2p (Module 14); middleware-অডিট (Module 13/15); billing (Module 16)
- নতুন WS-হাব-নির্মাণ; Firestore-স্থাপত্য-বিস্তার; পেইড-অনুমোদন-SaaS
- traceability-matrix-সম্পাদনা (শুধু লিপি-প্রস্তাব)

## Part 4 — ৯-নিয়ম ও Constitution-সংগতি

| নিয়ম | এই নীলনকশার অবস্থান |
|---|---|
| Single-plan execution | প্রস্তাব-পাইপলাইন; একসময়ে একটিই active |
| Evidence-first | file:line প্রমাণ; ৩য়-পক্ষ তারিখ-চিহ্নিত |
| Extend-not-replace | P-D shim-প্রথম; P-A ownership-টেস্ট; ERR-F02 |
| Founder gates | auto-approve কখনোই ডিফল্ট নয়; store-cutover Gate 2-পরবর্তী |
| Zero-false-positive | ownership-টেস্ট warn-প্রথম |
| Branch discipline | docs-only; execution আলাদা ব্রাঞ্চ+PR |

## Part 5 — Verification & Rollback

- **Gate 4 (proof)**: P-A route-map টেস্ট-সবুজ; P-C উৎপাদক-ইন্টিগ্রেশন; P-B প্রতি-target dispatch টেস্ট + অজানা-target fail-closed; P-F টেম্পার-টেস্ট (হালকা-পরিবর্তনে verify False); P-G sweep টেস্ট; P-E টোকেন-স্বাক্ষর/মেয়াদ/এককালীন টেস্ট
- **Gate 5 (measurement)**: pending-চিরকাল-গণনা (→০ sweep-পরে); সিদ্ধান্ত-লেটেন্সি median; verify-কল-গণনা; Telegram-সিদ্ধান্ত-শেয়ার (গ্রহণ হলে)
- **Gate 6 (rollback)**: P-D dual-read-ফেরত; P-E বাহক-প্রতি kill-switch env; P-G sweep disable env; প্রতিটি P এক-ফাইল/শিম-রোলব্যাক

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Audit)

| প্রস্তাব | Zero Cost | Lightweight | Fast Smooth | Zero Hardcode |
|---|---|---|---|---|
| P-A route-shadow সংশোধন | ✓ | ✓ | ✓ সঠিক-হ্যান্ডলার | ✓ নীতি-নথি |
| P-C db=None ফিক্স | ✓ | ✓ দুই-লাইন | ✓ | n/a |
| P-B dispatch-table | ✓ | ✓ data-file | ✓ | ✓✓ |
| P-D ৭→১ store | ✓ | ✓✓ কম-কোড | ✓ | n/a |
| P-E resume-URL সেতু | ✓✓ শূন্য-অবকাঠামো | ✓ এক-টোকেন | ✓ এক-ক্লিক | ✓ মেয়াদ-env |
| P-F verify readback | ✓ | ✓ এক-এন্ডপয়েন্ট | ✓ on-demand | n/a |
| P-G TTL+নীতি-ফাইল | ✓ | ✓ | ✓ sweep-বাইরে-হট-পাথ | ✓✓ |
| P-H frontend-সত্য | ✓ | ✓ | ✓ | n/a |
| LangGraph/Temporal প্রত্যাখ্যান | ✓✓ | ✓✓ | ✓ | n/a |

**জন্মগত-সংগতি-ঘোষণা**: অনুমোদন-সত্যতা (গভর্নেন্স-স্তম্ভ) আর চার-স্তম্ভ-দর্শন এখানে এক-দিকেই যায় — কম-মেশিন, এক-টোকেন, ডেটা-নীতি, শূন্য-নতুন-অবকাঠামো।

## Part 6 — পরবর্তী মডিউল লাইনেজ

- **চক্র ১৮-প্রার্থী**: Telegram-ইন্টিগ্রেশন অঙ্গ (backend/tools/social/telegram_bot — ব্যবহারকারী-মুখী লাইভ পথ, admin_handlers এই চক্রের P-E-এর বাহক হবে) বা notification/delivery (email_agent পরিবার) — ৩য়-পক্ষ-প্রস্তুতি: Telegram Bot API rate/polling-বনাম-webhook বিনিময়, aiogram/telegraf প্যাটার্ন
- **চক্র ১৯-প্রার্থী**: i18n/বাংলা-অ্যাডাপ্টার অঙ্গ (বাংলা-প্রথম পরিচয়-স্তম্ভ) — ৩য়-পক্ষ: ICU MessageFormat, unicode-normalization প্যাটার্ন
- কিউ-পুনঃর‍্যাঙ্ক: Gate 5-পরিমাপে; প্রতিটি চক্র ৩য়-পক্ষ-গবেষণা-চুক্তি বহাল
