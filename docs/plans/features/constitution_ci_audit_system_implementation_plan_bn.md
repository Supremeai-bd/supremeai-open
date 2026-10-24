---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto-constitution_ci_audit_system_implementation_plan_bn
subject: "চূড়ান্ত বাস্তবায়ন পরিকল্পনা: সুপ্রীম এআই আর্কিটেকচার ও ইঞ্জিনিয়ারিং সংবিধান সিআই অডিট সিস্টেম (SupremeAI Constitution CI Audit Engine)"
document_role: audit
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# চূড়ান্ত বাস্তবায়ন পরিকল্পনা: সুপ্রীম এআই আর্কিটেকচার ও ইঞ্জিনিয়ারিং সংবিধান সিআই অডিট সিস্টেম (SupremeAI Constitution CI Audit Engine)

এই রূপরেখাটি সুপ্রীম এআই-এর সিআই/সিডি (CI/CD) পাইপলাইনে **"কনস্টিটিউশন অডিট সিস্টেম"** বাস্তবায়নের চূড়ান্ত, নিশ্ছিদ্র এবং প্রোডাকশন-রেডি ব্লুপ্রিন্ট। আপনার নির্দেশিত ৮টি চূড়ান্ত পরিমার্জন, ক্যাটাগরিভিত্তিক স্টেবল রুল আইডি, মেটা-রুল (Rule 000), র‍্যাচেট বেইজলাইন এবং ফেজড রোলআউট (Phase A থেকে G) অন্তর্ভুক্ত করে এটি তৈরি করা হয়েছে।

---

## ১. ৫টি অপরিবর্তনীয় সিদ্ধান্ত (Locked Architectural Decisions)

1. **One Unified SPA Architecture:** আলাদা কাস্টমার/অ্যাডমিন এক্সপেরিয়েন্স থাকবে কিন্তু কোনো বিচ্ছিন্ন অ্যাপ্লিকেশন আর্কিটেকচার হবে না।
2. **Deterministic Engine Is Final Gate:** ডিটারমিনিস্টিক পাইথন রুল ইঞ্জিনই একমাত্র হার্ড ব্লকিং গেট; এআই কখনো প্রাথমিক ব্লকিং অথরিটি নয়।
3. **No External Remote Complexity (LaunchDarkly Removed):** সিআই গেট কোনো এক্সটার্নাল রিমোট নেটওয়ার্ক ফ্ল্যাগের উপর নির্ভর করবে না। রুল কনফিগ সম্পূর্ণ ডিক্লারেটিভ (`rules.yml`) এবং লোকাল এনভায়রনমেন্ট ওভাররাইড নির্ভর।
4. **Strict Ratchet Baseline + Expiring Exceptions:** বেইজলাইন কখনো নতুন ভায়োলেশন ঢাকতে পারবে না; এক্সেপশন ফাইলে `owner`, `reason`, এবং `expires` বাধ্যতামূলক।
5. **Capability Before Module & Meta-Rule (Rule 000):** মডিউলের আগে ক্যাপাবিলিটি রি-ইউজ এবং কনস্টিটিউশন অডিটর নিজেই যেন সংবিধানের কোনো নীতি লঙ্ঘন না করে।

---

## ২. মেটা-রুল ও ক্যাটাগরিভিত্তিক সুপ্রীম এআই রুল ট্রি

```text
SUPREMEAI CONSTITUTION
│
├── META
│   └── RULE-000  The Auditor Must Comply (অডিট ইঞ্জিন নিজেই কোনো আর্কিটেকচার ভাঙবে না)
│
├── ARCHITECTURE (ARCH)
│   ├── ARCH-001  No Local-Machine Dependency (প্রোডাকশনে localhost/127.0.0.1/উইন্ডোজ পাথ নিষিদ্ধ)
│   ├── ARCH-002  Reuse Before Create (২২৪-মডিউল একত্রীকরণ রক্ষা ও অপ্রয়োজনীয় ডুপ্লিকেশন রোধ)
│   ├── ARCH-003  Capability Before Module (মডিউল বৃদ্ধির আগে বিদ্যমান ক্যাপাবিলিটি কম্পোজিশন)
│   └── ARCH-004  No Unnecessary Duplication (আইসোলেটেড কোড ফ্র্যাগমেন্টেশন নিষিদ্ধ)
│
├── SECURITY (SEC)
│   ├── SEC-001   Backend Authorization Is Final (ক্লায়েন্ট-সাইড অনলি পারমিশন চেক নিষিদ্ধ)
│   ├── SEC-002   No Secret Hardcoding (টোকেন/কী/পাসওয়ার্ড কোডে হার্ডকোড নিষিদ্ধ)
│   └── SEC-003   No Unsafe Privilege Elevation (ন্যূনতম প্রিভিলেজ নীতি)
│
├── CONFIGURATION (CFG)
│   ├── CFG-001   Configuration/Policy Over Hardcoding (বিজনেজ লজিক ডাইনামিক কনফিগে থাকবে)
│   └── CFG-002   User Behavior Must Be Data-Driven
│
├── MCP & INTEGRATION (MCP)
│   ├── MCP-001   MCP Is Infrastructure, Not Customer UX (ইউজারের জন্য টেকনিক্যাল জটিলতা অদৃশ্য)
│   ├── MCP-002   Unified Capability Contract (প্রতিটি টুলের ইউনিফাইড ইন্টারফেস)
│   └── MCP-003   Connection Must Be Environment-Agnostic
│
├── RELIABILITY (REL)
│   ├── REL-001   No Silent Failure (খালি except: pass বা catch {} নিষিদ্ধ)
│   ├── REL-002   Errors Must Be Observable (লগিং ও টেলিমেট্রি বাধ্যতামূলক)
│   └── REL-003   New Features Must Be Testable (নতুন ফিচারের টেস্ট কভারেজ বাধ্যতামূলক)
│
├── COST (COST)
│   ├── COST-001  No Unapproved Paid Infrastructure ($0 ফ্রি-টায়ার সীমার সুরক্ষা)
│   └── COST-002  Resource Usage Must Be Observable
│
├── PERFORMANCE (PERF)
│   ├── PERF-001  Lightweight Dependencies (অপ্রয়োজনীয় ভারী লাইব্রেরি রোধ)
│   └── PERF-002  Bundle/Memory Limits (ব্রাউজার কনসোল এরর ও মেমোরি লিক রোধ)
│
└── CUSTOMER UX (UX)
    ├── UX-001    Zero / Near-Zero Complexity (১-ক্লিকে এক্সিকিউশন)
    ├── UX-002    Progressive Disclosure
    └── UX-003    Technical Infrastructure Hidden by Default
```

---

## ৩. চূড়ান্ত সিআই এক্সিকিউশন ফ্লো

```text
                       Git Push / PR
                            │
                            ▼
                   ┌─────────────────┐
                   │ Git Diff Scope  │  (শুধুমাত্র পরিবর্তিত ফাইল স্ক্যান)
                   └────────┬────────┘
                            │
                            ▼
                  ┌───────────────────┐
                  │   Constitution    │  (Lightweight, zero paid external dep)
                  │   Deterministic   │
                  │      Engine       │
                  └─────────┬─────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
     Security         Architecture           Cost
     (SEC-*)            (ARCH-*)           (COST-*)
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
                            ▼
                    Baseline / Ratchet
                 (পুরোনো কোড পাস, কিন্তু
                  লাইন বদলালে বা নতুন হলে ব্লক)
                            │
                   ┌────────┴────────┐
                   │                 │
                 FAIL               PASS
                   │                 │
                🛑 BLOCK             ▼
                              Normal CI
                                     │
                                     ▼
                            Tests / Build / Scan
                                     │
                                     ▼
                              SARIF Report Upload
                          (গিটহাব সিকিউরিটিতে ইনলাইন দাগ)
                                     │
                                     ▼
                            AI Architecture Review
                         (Advisory Only, Free Gemini/Groq;
                          API না থাকলে নিরবে SKIP করবে)
                                     │
                                     ▼
                                Deployment
```

---

## ৪. প্রস্তাবিত ডিরেক্টরি ও ফাইলসমূহ

```text
.github/
├── workflows/
│   └── ci.yml                          # 'constitution-audit' জব সংযোজন
│
├── constitution/                       # ডিক্লারেটিভ কনফিগারেশন ও বেইজলাইন
│   ├── rules.yml                       # ক্যাটাগরিভিত্তিক স্টেবল রুল তালিকা ও তীব্রতা
│   ├── exceptions.yml                  # owner, reason, expiry সহ ছাড়ের তালিকা
│   └── baseline.json                   # লিগ্যাসি কোডের ফিংগারপ্রিন্ট (Ratchet)
│
└── scripts/
    └── constitution/                   # মডুলার এবং লাইটওয়েট পাইথন ইঞ্জিন (No heavy deps)
        ├── __init__.py
        ├── engine.py                   # মূল CLI এন্ট্রি পয়েন্ট (--pr-diff, --fix-safe, --sarif)
        ├── models.py                   # RuleDefinition, AuditFinding, Severity, Exemption
        ├── reporters.py                # GitHub Step Summary, Sticky PR Comment, SARIF v2.1
        ├── rules/                      # পৃথক রুল হ্যান্ডলার
        │   ├── __init__.py
        │   ├── base.py                 # Abstract BaseRule (AST, Regex, Git Diff হেল্পার)
        │   ├── arch001_no_local_machine.py    # এনভায়রনমেন্ট-সচেতন লোকালহোস্ট ও পাথ চেকার
        │   ├── arch002_reuse_before_create.py # নতুন সার্ভিস/মডিউল শনাক্তকারী (Deterministic)
        │   ├── sec001_backend_auth.py         # ফ্রন্টেন্ড-অনলি পারমিশন বাইপাস চেকার
        │   ├── sec002_no_secret_hardcoding.py # হার্ডকোডেড টোকেন/প্রাইভেট কী চেকার
        │   ├── rel001_no_silent_failure.py    # খালি catch/except pass চেকার
        │   └── cost001_infra_cost.py          # পেইড ক্লাউড এসডিকে ও ভারী প্যাকেজ চেকার
        └── ai_reviewer.py              # অপশনাল অ্যাডভাইজরি রিভিউ (Gemini Flash free tier)
```

---

## ৫. বাস্তবায়ন ধাপসমূহ (Phased Implementation Plan)

### Phase A — Foundation (কোর ফ্রেমওয়ার্ক)
- [NEW] `.github/constitution/rules.yml`: স্টেবল ক্যাটাগরি আইডি (ARCH-001, SEC-001 ইত্যাদি), severity (`BLOCK`, `WARN`, `INFO`), এবং `fixable: true/false` মেটাডাটা।
- [NEW] `.github/scripts/constitution/models.py`: স্ট্রং টাইপড ডেটাক্লাস (`Finding`, `RuleDefinition`, `Exemption`)।
- [NEW] `.github/scripts/constitution/rules/base.py`: অ্যাবস্ট্রাক্ট বেস রুল ক্লাস।
- [NEW] `.github/scripts/constitution/engine.py`: Git Diff পার্সিং ও রানার ইঞ্জিন।
- [NEW] `.github/scripts/constitution/reporters.py`: মার্কডাউন সামারি ও কনসোল আউটপুট।

### Phase B — Core Deterministic Hard Rules (৪টি অত্যাবশ্যকীয় রুল)
- [NEW] `rules/arch001_no_local_machine.py`: এনভায়রনমেন্ট-সচেতন `localhost`, `127.0.0.1`, উইন্ডোজ ড্রাইভ পাথ ফিল্টার (টেস্ট ও মক ফাইল ছাড় পাবে)।
- [NEW] `rules/sec002_no_secret_hardcoding.py`: হাই-এনট্রপি সিক্রেট ও হার্ডকোডেড কী চেকার।
- [NEW] `rules/rel001_no_silent_failure.py`: AST দিয়ে পাইথন `except: pass` এবং টাইপস্ক্রিপ্ট `catch (e) {}` ব্লকে সাইলেন্ট ফেইলিউর ধরা।
- [NEW] `rules/sec001_backend_auth.py`: ক্রিটিক্যাল অপারেশনে ব্যাকএন্ড অথরাইজেশন নিশ্চিতকরণ।

### Phase C — Strict Ratchet Baseline & Expiring Exceptions
- [NEW] `.github/constitution/baseline.json`: বর্তমান রিপোজিটরির বিদ্যমান ওয়ার্নিং স্ন্যাপশট জেনারেট করা।
- [NEW] `.github/constitution/exceptions.yml`: প্রতিটি ছাড়ের জন্য `owner`, `reason`, এবং `expires` ফিল্ড এনফোর্স করা।

### Phase D — Safe Auto-Remediation (`--fix-safe`)
- নিরাপদ রুলগুলোর জন্য (যেমন: ডিপেনডেন্সি ফরম্যাটিং, মিসিং স্কিমা ট্যাগ, কমন লগার প্যাটার্ন) অটোমেটিক সেফ রিপ্লেসমেন্ট যুক্ত করা। সিকিউরিটি বা আর্কিটেকচারাল রুল কখনোই স্বয়ংক্রিয়ভাবে বদলাবে না।

### Phase E — GitHub CI Integration & SARIF Output
- [MODIFY] `.github/workflows/ci.yml`: `constitution-audit` জব যোগ করা।
- SARIF আউটপুট তৈরি এবং গিটহাবের CodeQL/Security ট্যাবে আপলোড।
- পিআরে ১২টি রুলের স্টিকি মার্কডাউন চেকলিস্ট পোস্ট করা।

### Phase F — Reuse & Architecture Intelligence
- [NEW] `rules/arch002_reuse_before_create.py`: পিআরে নতুন ডিরেক্টরি/সার্ভিস যোগ হলে ওয়ার্নিং দেওয়া এবং বিদ্যমান ২২৪-মডিউল কনসোলিডেশন তালিকার সাথে মিলিয়ে সাজেস্ট করা।
- `ARCH-003`: Capability Before Module গাইডলাইন এনফোর্স করা।

### Phase G — Optional Advisory AI Architecture Reviewer
- [NEW] `.github/scripts/constitution/ai_reviewer.py`: সম্পূর্ণ অপশনাল ফলব্যাক-সেফ স্ক্রিপ্ট। এপিআই কী না থাকলে বা ফেইল করলে সিআই গেট কোনোভাবেই আটকে থাকবে না (`status: SKIPPED`)।

---

## ৬. ভেরিফিকেশন ও টেস্ট পরিকল্পনা

### অটোমেটেড টেস্ট:
1. **ইউনিট টেস্ট (`pytest .github/scripts/constitution/tests/`):**
   - টেস্ট ডিরেক্টরিতে `localhost` পাস করবে।
   - প্রোডাকশন কোডে `localhost` ধরা পড়বে এবং ব্লক করবে।
   - বেইজলাইনে থাকা লিগ্যাসি ভায়োলেশন ব্লক করবে না; কিন্তু সেই লাইনে হাত দিলে বা নতুন ভায়োলেশন দিলে ব্লক করবে।
   - এক্সপায়ার্ড এক্সেপশন থাকলে সিআই এরর দেবে।
   - সাইলেন্ট ফেইলিউর (খালি ক্যাচ ব্লক) নির্ভুলভাবে ধরা পড়বে।

### ম্যানুয়াল ও পাইপলাইন ড্রাই-রান:
- লোকাল মেশিনে `python -m .github.scripts.constitution.engine --pr-diff` চালিয়ে শূন্য ফলস-পজিটিভ নিশ্চিত করা।
- গিটহাব একশনে রান করে স্টেপ সামারি এবং পিআর চেকলিস্টের আউটপুট যাচাই করা।