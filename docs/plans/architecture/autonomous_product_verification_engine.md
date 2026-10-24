---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:autonomous_product_verification_engine
subject: SupremeAI Autonomous Product Verification Engine (Master Architecture Blueprint)
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI Autonomous Product Verification Engine (Master Architecture Blueprint)
**Document:** `docs/plans/architecture/autonomous_product_verification_engine.md`  
**Status:** 🎯 **PROPOSED / ADOPTED BLUEPRINT**  
**Priority:** CRITICAL (P0)  
**Domain Circle:** Circle C1 (Code & Quality Gate) + Circle C4 (Frontend UI) + Circle C3 (DevOps & CI)  
**Governing Rule:** *AGENTS.md Clause 2 (Operational Zero-Gap), Clause 3 (Evidence-Gated Improvement) & Clause 7 (End-to-End Dual-Driven Full-Stack Principle)*

---

## 🏛️ 1. Executive Intent: "Full Automation System, Not Just a Checklist"

একটি বড় স্কেল সফটওয়্যার এবং ফুল-স্ট্যাক এআই সিস্টেমে একজন একক নির্মাতার (Solo Architect) পক্ষে প্রতিবার রিলিজ বা কমিটে ২০০-৩০০টি ইউআই ও ব্যাকএন্ড ফিচার ম্যানুয়ালি চেক করা অসম্ভব এবং অবাস্তব।

এই আর্কিটেকচারের লক্ষ্য ম্যানুয়াল চেকলিস্টকে একটি সাধারণ টেক্সট বা ডক ফাইলে সীমাবদ্ধ না রেখে একটি **সম্পূর্ণ স্বয়ংক্রিয় প্রোডাক্ট ভেরিফিকেশন ইঞ্জিন (Automated Product Verification System)**-এ রূপান্তরিত করা:
1. **Checklist is Executable Data (Single Source of Truth):** চেকলিস্ট কোনো বিবরণ নয়, এটি মেশিন-রিডেবল স্পেসিফিকেশন (`qa/checklist/*.yaml`)।
2. **Three-Tier Role Project Isolation (Playwright):** Guest, Customer, এবং Admin তিনটি আলাদা সিকিউরিটি প্রজেক্ট হিসেবে ব্রাউজারে স্বয়ংক্রিয়ভাবে এক্সিকিউট হবে।
3. **True End-to-End Zero-Gap (UI PASS ≠ Feature PASS):** শুধুমাত্র বাটনে ক্লিক করা যথেষ্ট নয়; ব্যাকএন্ড API, ডেটাবেস/রেডিস স্টেট, এবং রিফ্রেশ পারসিসটেন্স নিশ্চিত করতে হবে।
4. **AI-Powered Automated Diagnosis:** কোনো টেস্ট ফেইল করলে স্ক্রিনশট, ট্রেস এবং নেটওয়ার্ক লগ বিশ্লেষণ করে এআই রুট কজ (Root Cause) ও সম্ভাব্য ফিক্স প্রস্তাব করবে।

---

## 📐 2. The 4-Tier SupremeAI QA Engine Topology

```text
                           SUPREMEAI QA ENGINE
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
  Static Checks               Browser E2E               Runtime Checks
        │                           │                           │
  - Turbo Build / Typecheck   - Guest Persona           - API Health (/health)
  - Biome / Ruff Linter       - Customer Persona        - Supabase DB / RLS
  - Route Inventory Audit     - Admin Mission Control   - Redis / Memory Sync
  - Secret & Dependency Scan  - Visual Regression       - FastMCP 10 Circles
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
                            RESULT AGGREGATOR
                                    │
             ┌──────────────────────┴──────────────────────┐
             │                                             │
      GitHub Summary / PR Gate                        QA Dashboard
      - Machine JSON Artifact                       - Live Score & History
      - Release Gate: PASS / BLOCK                  - AI Diagnostic Summary
```

---

## 📂 3. Repository Structure & Single Source of Truth

```text
qa/
├── checklist/                     # Machine-Readable Contracts (YAML)
│   ├── guest.yaml                 # Public routes, landing, guest chat, auth limits
│   ├── customer.yaml              # Workspace, chat, IDE, files, agents, billing
│   ├── admin.yaml                 # Mission control, 3D telemetry, user manager, MCP
│   ├── security.yaml              # RLS isolation, CSRF, TOTP 2FA, token expiry
│   ├── integrations.yaml          # Supabase, Redis, Cloudflare, Telegram, WhatsApp
│   └── production.yaml            # Canary smoke, live deployment preflight
│
├── playwright/                    # Playwright E2E Test Suites
│   ├── guest/                     # Guest persona journeys
│   ├── customer/                  # Customer persona journeys (authenticated)
│   ├── admin/                     # Admin persona journeys (step-up auth + 2FA)
│   ├── security/                  # Tenant boundary & privilege escalation tests
│   └── fixtures/                  # Auth state fixtures, storage state, mocks
│
├── runner/                        # Core Test Execution Engine
│   ├── index.ts                   # Unified CLI runner (npm run qa)
│   ├── yaml-to-spec.ts            # Dynamic test runner directly from YAML data
│   ├── parity-checker.ts          # UI ➔ API ➔ DB state verifier
│   └── visual-diff.ts             # Pixelmatch / Playwright visual snapshot engine
│
├── reporters/                     # Result Formatting & Aggregation
│   ├── github-summary.ts          # Step summary & status checks formatter
│   ├── ai-diagnostician.ts        # AI failure analyzer (log + trace ➔ root cause)
│   └── dashboard-exporter.ts      # Push stats to internal telemetry cockpit
│
└── policies/                      # Release & Gate Rules
    ├── severity-matrix.yaml       # P0, P1, P2, P3 definitions & thresholds
    └── coverage-contract.yaml     # Mandatory test coverage per feature
```

---

## 👥 4. Three Playwright Personas (Projects)

Playwright-এর `projects` কনফিগারেশন ব্যবহার করে ৩টি ভিন্ন আইডেন্টিটি স্টেট টেস্ট করা হবে:

### 1. Guest Project (`qa/playwright/guest/`)
* **State:** সম্পূর্ণ আনঅথেন্টিকেটেড (No cookies/localStorage)।
* **Journeys:**
  - পাবলিক ল্যান্ডিং পেজ স্পিড ও রেন্ডারিং।
  - গেস্ট চ্যাট লিমিটেশন টেস্ট।
  - সাইন-আপ / লগইন রিডাইরেকশন।
  - প্রোটেক্টেড রুট ব্লক নিশ্চিতকরণ (`/admin`, `/workspace` রিডাইরেক্ট করে `/login` এ পাঠায় কি না)।

### 2. Customer Project (`qa/playwright/customer/`)
* **State:** স্ট্যান্ডার্ড কাস্টমার একাউন্ট অ্যাথরাইজড স্টেট (`storageState: 'qa/fixtures/customer-state.json'`)।
* **Journeys:**
  - ওয়ার্কস্পেস তৈরি ও ফাইল ম্যানেজমেন্ট।
  - এআই চ্যাট ও মাল্টি-টার্ন রেসপন্স এক্সিকিউশন।
  - আইসিডিই (IDE) কোড এডিটর রান ও লাইভ আউটপুট।
  - মেমরি রিট্রিভাল (Supabase + Qdrant)।
  - সেটিংস ও বিলিং সাবস্ক্রিপশন প্রিভিউ।
  - লগআউট এবং সেশন ইনভ্যালিডেশন।

### 3. Admin Project (`qa/playwright/admin/`)
* **State:** সুপার-অ্যাডমিন রোল স্টেট + Step-up 2FA টোকেন (`storageState: 'qa/fixtures/admin-state.json'`)।
* **Journeys:**
  - মিশন কন্ট্রোল ড্যাশবোর্ড ও ৩ডি টেলিমেট্রি গ্রাফ।
  - ইউজার ম্যানেজমেন্ট ও রোল অ্যাসাইনমেন্ট।
  - সেন্ট্রাল FastMCP কন্ট্রোল টাওয়ার সুইপ (১০টি সার্কেল টেস্ট)।
  - মডেল পলিসি কনফিগারেশন ও ফলব্যাক রাউটিং।
  - সিস্টেম অডিট লগ এবং এআই কোড অ্যানালাইসিস।
  - ইমার্জেন্সি কিল-সুইচ টেস্ট (Dry-run mode)।

---

## ⚡ 5. Verification Depth: UI PASS ≠ Feature PASS (True End-to-End)

যেকোনো অ্যাকশন সফল হওয়ার জন্য ৩টি লেয়ার একযোগে পাস করতে হবে:

```text
Step 1: UI Trigger
   [Click 'Create Workspace']
            │
            ▼
Step 2: API Contract
   [POST /api/v1/workspaces returns 201 Created]
            │
            ▼
Step 3: Database & State Isolation
   [Supabase row exists with correct tenant_id & RLS blocks user_b]
            │
            ▼
Step 4: Persistence & UI Refresh
   [Page reload shows the workspace in UI list]
```
এই ৪টি ধাপ সম্পন্ন হলেই কেবল একটি টেস্টকে **`PASS`** ঘোষণা করা হবে।

---

## 🚦 6. Multi-Level Pipeline & Release Gates

| লেভেল | ট্রিগার | রান করা হবে | সময়সীমা | ব্যর্থতার প্রভাব |
|---|---|---|---|---|
| **Level 1: PR Preflight** | প্রতিটি PR / Commit | Build, Typecheck, Lint, Route Audit, Guest/Customer/Admin Smoke | < 3 মিনিট | PR মার্জ ব্লক |
| **Level 2: Merge to Main** | Main ব্রাঞ্চে মার্জ হলে | Full Playwright Suite (সব রুট ও রোল), API Parity, Security Gate | ~ 8-10 মিনিট | Release Candidate ব্লক |
| **Level 3: Production Preflight** | Staging / Pre-deploy | Production Bundle Build, Staging Health Check, MCP Transports | ~ 5 মিনিট | ডিপ্লয়মেন্ট স্থগিত |
| **Level 4: Post-Deploy Canary** | প্রোডাকশন ডিপ্লয়ের পরে | Live `/health`, Auth Ping, Canary Prompt, 2FA Validation | 60 সেকেন্ড | স্বয়ংক্রিয় সতর্কবার্তা / রোলব্যাক |

---

## 🚨 7. Severity Matrix & Release Governance

```yaml
P0 (Production Blocker):
  - লগইন ব্যর্থতা / অথেনটিকেশন বাইপাস
  - টেন্যান্ট ডেটা লিকেজ (User A-র ডেটা User B দেখতে পাওয়া)
  - অ্যাডমিন রুটে অননুমোদিত অ্যাক্সেস
  - ব্যাকএন্ড ক্র্যাশ / 500 Internal Error অন ক্রিটিক্যাল রুট
  - পলিসি: ১টি P0 ফেইল হলে RELEASE কঠোরভাবে BLOCKED।

P1 (Critical User Flow):
  - এআই চ্যাট বা মেসেজ প্রসেসিং ব্যর্থ
  - ফাইল আপলোড বা মেমরি সেভ ব্যর্থ
  - প্রজেক্ট তৈরি করতে না পারা
  - পলিসি: রিলিজ ব্লক (যদি না স্পেশাল হটফিক্স এক্সেম্পশন দেওয়া হয়)।

P2 (Important Feature):
  - নন-ব্লকিং সেটিংস পেজ সমস্যা
  - চার্ট বা ৩ডি গ্রাফ রেন্ডারে সামান্য ল্যাগ
  - পলিসি: সতর্কবার্তা (Warning) কিন্তু রিলিজ অ্যালাউড।

P3 (Cosmetic):
  - ডার্ক মোড কালার কন্ট্রাস্ট বা টাইপো
  - পলিসি: ব্যাকলগে অটো-লগ হবে, কোনো রিলিজ আটকাবে না।
```

---

## 🧠 8. Automated AI QA Analyzer (Post-Failure Engine)

যখন কোনো টেস্ট ব্যর্থ হবে, সিস্টেম স্বয়ংক্রিয়ভাবে ডায়াগনোসিস করবে:

```text
                    TEST FAILURE OCCURRED
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
        Console Logs     Screenshots      Network Traces
             │                │                │
             └────────────────┼────────────────┘
                              ▼
                     AI QA ANALYZER
                              ▼
         ┌─────────────────────────────────────────┐
         │ 1. Root Cause Identification            │
         │ 2. Exact Layer Pinpointing (UI vs API)  │
         │ 3. Proposed Fix & Code Pointer          │
         └─────────────────────────────────────────┘
```

*উদাহরণ AI আউটপুট:*
> ❌ **Test Failed:** `CUST-42 (Upload Workspace Document)`  
> 🔍 **Diagnostic Summary:** ব্রাউজার ইন্টারঅ্যাকশন পুরোপুরি সফল ছিল এবং ফাইল সাবমিট হয়েছিল। কিন্তু ব্যাকএন্ড `POST /api/v1/files/upload` এন্ডপয়েন্ট `500 Server Error` রিটার্ন করেছে।  
> 💡 **Root Cause:** ফাইল সাইজ ভ্যালিডেশন মিডলওয়্যার `storage_bucket` নাল পেয়ে এক্সেপশন থ্রো করেছে (`backend/api/routes/files.py:124`)।  
> 🛠️ **Remediation:** `SUPABASE_STORAGE_BUCKET` এনভায়রনমেন্ট ভেরিয়েবল চেক করুন।

---

## 📊 9. Feature Coverage Matrix (Automated Drift Sentinel)

কোনো নতুন ফিচার কোডবেসে যোগ হলে এই মেটাদাতা বাধ্যতামূলক হবে:
```yaml
feature: dynamic-agent-discovery
roles: [customer, admin]
coverage:
  ui: true
  api: true
  e2e: true
  security: true
  production_smoke: true
```
যদি কোড যোগ হয় কিন্তু E2E বা Security স্পেক না থাকে, CI স্বয়ংক্রিয়ভাবে সতর্ক করবে:
`⚠️ QA DRIFT: Feature 'dynamic-agent-discovery' lacks role-isolated E2E tests.`

---

## 📖 11. Living Documentation + Automation Boundary (The Golden Rule)

> 💡 **মাস্টার প্রিন্সিপল:**  
> **"ডকুমেন্টেশন ১০০% থাকবে (Zero Magic Boxes), কিন্তু এক্সিকিউশন হবে যেখানে অটোমেশন সম্ভব সেখানে স্বয়ংক্রিয় (Automate where possible, document everything)."**

1. **ডকুমেন্টেশন সবার জন্য বাধ্যতামূলক (Living Source of Truth):**
   - প্রতিটি ফিচার, রুট, সিকিউরিটি বাউন্ডারি এবং ইউজারের জার্নির স্পষ্ট ডকুমেন্টেশন ও চেকলিস্ট স্পেক থাকবে। ডকুমেন্টেশন বাদ দিয়ে সরাসরি কোড বা টেস্টে ঝাঁপিয়ে পড়া যাবে না।
   - এর ফলে যেকোনো মানুষ বা যেকোনো নতুন এআই এজেন্ট তাৎক্ষণিকভাবে বুঝতে পারবে সিস্টেমের কোথায় কী কাজ হচ্ছে এবং প্রত্যাশিত আউটপুট কী।
2. **অটোমেশন যেখানে যেখানে টেকনিক্যালি সম্ভব (80–90% Coverage):**
   - যে কাজগুলো মেশিন নির্ভুলভাবে করতে পারে (রুট রিডাইরেকশন, অথেনটিকেশন স্টেট, ফর্ম ভ্যালিডেশন, এপিআই রেসপন্স কোড, ডেটাবেস আইসোলেশন, ডার্ক মোড টগল, ব্রাউজার ই২ই) সেগুলোতে মানুষ সময় নষ্ট করবে না—সেগুলো প্লে-রাইট এবং সিআই রোবট স্বয়ংক্রিয়ভাবে যাচাই করবে।
3. **হিউম্যান রিভিউ শুধুমাত্র যেখানে মানুষের বুদ্ধিমত্তা অপরিহার্য (10–20% Judgment):**
   - এআই উত্তরের ভাষা কতটা মানবিক ও আকর্ষণীয়, ইউআই লেআউট দেখতে চোখে কতটা প্রিমিয়াম লাগছে, প্রোডাক্টের অনুভূতি কেমন—শুধুমাত্র এই সীমিত অংশে মানুষের স্পর্শ থাকবে।

---

## 📅 12. Execution Roadmap

1. **Phase 1: Foundation & Data Architecture**
   - `qa/checklist/` ডিরেক্টরিতে ডকুমেন্ট স্পেসিফিকেশন সংরক্ষণ (`guest.yaml`, `customer.yaml`, `admin.yaml`, `security.yaml`)।
   - `scripts/ci/validate_qa_checklist.mjs` দিয়ে ডেটা স্পেসিফিকেশনের শতভাগ শুদ্ধতা নিশ্চিত করা।
2. **Phase 2: Playwright Multi-Project Setup (Automating the Feasible)**
   - রুট `playwright.config.ts` এবং `frontend/playwright.config.ts` এর মিসম্যাচ দূর করে Guest, Customer, Admin রোল প্রজেক্ট তৈরি করা।
3. **Phase 3: CI/CD Pipeline Alignment**
   - GitHub Actions-এ প্রিফ্লাইট ও ডিপ QA পাইপলাইন কার্যকর করা।