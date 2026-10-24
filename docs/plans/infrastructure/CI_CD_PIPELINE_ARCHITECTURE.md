---
id: ci-cd-pipeline-architecture
subject: "SupremeAI Production CI/CD Pipeline Architecture & Optimization Specification"
document_role: architecture
planning_authority: DevEx / CI Circle
status: active
plan_lifecycle: living — permanent single source of truth
target_scope: supremeai_internal
last_verified: 2026-09-19
supersedes: []
---

# SupremeAI Production CI/CD Pipeline Architecture

> **Living Architecture Asset:** এটি SupremeAI প্ল্যাটফর্মের কেন্দ্রীয় CI/CD পাইপলাইনের ক্যানোনিকাল আর্কিটেকচার। এই ডকুমেন্টটি বাস্তব কোডবেসের লাইভ রিয়ালিটির সাথে সমন্বয় করে তৈরি এবং ভবিষ্যতে সিআই/সিডি সংক্রান্ত সমস্ত সিদ্ধান্তের একক রেফারেন্স।

---

## 1. Executive Summary & Operational Reality

SupremeAI-এর CI/CD পাইপলাইন (`.github/workflows/ci.yml`) একটি উচ্চ-গতির, মাল্টি-লেয়ার এন্টারপ্রাইজ ভেরিফিকেশন ইঞ্জিন। প্রাথমিক স্টেজে ম্যাট্রিক্স রানারের অপচয় এবং সেটআপ ট্যাক্স সংক্রান্ত যে পারফরম্যান্স রিগ্রেশন ছিল, তা দূর করে এটিকে একটি **"Prepare Once ➔ Immutable Restore ➔ Adaptive Parallel Test"** মডেলে রূপান্তর করা হয়েছে।

### 1.1 Core Metrics & Current Baseline
* **Pipeline Version:** v5.0 Hardened (Modularized with SHA Pinning & Reusable Workflows).
* **Zero-Gap Gate:** `stub-blocker` গেট পিআর-এ যেকোনো ফেক মক বা স্টাব কোড প্রবেশ শতভাগ ব্লক করে (`--fail-on HIGH`)।
* **Governance Gate:** `plan-governance` প্রতি পিআর-এ প্ল্যান স্প্রল ও ফ্রন্টম্যাটার যাচাই করে `docs/plans/plan_registry.json` রিফ্রেশ করে।
* **Supply-Chain Security:** ১০০% গিটহাব অ্যাকশন ফুল কমিট SHA-দ্বারা পিন করা (জিরো ফ্লোটিং ট্যাগ)।
* **Layered Execution Time:** ব্যাকএন্ড ও ফ্রন্টএন্ড সেটআপ ওভারহেড ২.৫ মিনিট থেকে নেমে এসেছে ৩–৫ সেকেন্ডে (ইমিউটেবল আর্টিফ্যাক্ট রিস্টোরেশন)।

---

## 2. The 5 Hardened Principles of the Pipeline

```text
GitHub Runner VM (Ubuntu Latest)
│
├── Layer 1: OS Native Prerequisites (Lightweight libpq5, Docker)
│            -> Zero build tools on test runners; only installed on prepare
│
├── Layer 2: Pinned Toolchain (Python 3.11 + Poetry 2.4.1 + Node 24)
│            -> Installed via SHA-pinned composite actions
│
├── Layer 3: Restored Immutable Dependency Artifact (.venv / node_modules)
│            -> Downloaded & restored in 3-5 seconds
│
├── Layer 4: Hardened Security & Anti-Stub Gates
│            -> find_stub_data.py & Trivy/Gitleaks security scans
│
└── Layer 5: Adaptive Parallel Test Suites & Mission Scoreboard
             -> pytest, vitest, and contract verification
```

### 2.1 Immutable Dependency Artifacts Over Shared Environments
প্রতিটি রানার একটি সম্পূর্ণ আইসোলেটেড ভার্চুয়াল মেশিন। তাই প্রতিটি রানারে বারবার `poetry install` বা `pnpm install` না চালিয়ে:
$$\text{Prepare Once} \longrightarrow \text{Publish Immutable Environment Artifact} \longrightarrow \text{Parallel Runners Restore (3s)}$$

### 2.2 Decoupled OS vs Python Runtime Layers
সিস্টেমের নেটিভ লাইব্রেরি (`libpq`) ভার্চুয়াল এনভায়রনমেন্টের বাইরে থাকে। তাই:
* `mode: prepare` এ `libpq-dev` ও `build-essential` রান করে হুইল বিল্ড করা হয়।
* `mode: runtime` ও `mode: artifact` এ হালকা রানটাইম `libpq5` ইনস্টল করা হয়, কোনো ভারী কম্পাইলার ছাড়া।

### 2.3 Zero-Gap Stub Blocker Gate (Pre-Test Enforcement)
কোনো ডেভেলপার বা এআই এজেন্ট যেন অসম্পূর্ণ মক, প্লেসহোল্ডার বা ফেক টেস্ট কমিট করতে না পারে, সেজন্য টেস্ট চালুর আগেই `stub-blocker` গেট পরিচালিত হয়:
```bash
python scripts/find_stub_data.py --path backend --fail-on HIGH
python scripts/find_stub_data.py --path frontend/src --fail-on HIGH
python scripts/find_stub_data.py --path scripts --fail-on HIGH
```

### 2.4 Strict Full SHA Pinning (Supply Chain Armor)
সকল ডিপেনডেন্ট অ্যাকশন ফ্লোটিং ট্যাগ (যেমন `@v4`) পরিহার করে পূর্ণাঙ্গ কমিট হ্যাশ ব্যবহার করে:
* `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1)
* `actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97` (v7.0.0)
* `snok/install-poetry@972a0e78ffdebf9e98f6fe404b77831716cdd4aa` (v1.4.0)

### 2.5 Dynamic Path Filtering & Historical Failure Detection
`.github/scripts/detect-previous-failures.py` ব্যবহারের মাধ্যমে সিআই বুদ্ধিমানভাবে শনাক্ত করে কোন কোন ফাইল পরিবর্তিত হয়েছে এবং পূর্ববর্তী রানে কোনো ব্যর্থতা ছিল কিনা। ফলে অপ্রয়োজনীয় ডোমেইনে রানার খরচ হয় না।

---

## 3. Active CI Workflow Topography

| Phase | Job Name | Responsibility & Quality Gate |
|---|---|---|
| **Gate 0** | `stub-blocker` | Zero-Gap scanner; blocks all fake code / mocks / stubs. |
| **Gate 0** | `plan-governance` | Verifies `docs/plans/` integrity; updates `plan_registry.json`. |
| **Stage 1** | `changes` | Detects modified paths + auto-carries forward previous failures (incl. per-group backend failure memory, #470). |
| **Stage 1** | `security` | Trivy CVE vulnerability scan + Gitleaks secret leak detection. |
| **Stage 1** | `constitution-audit` | Rule compliance scan; uploads SARIF security reports. |
| **Stage 1.5** | `backend-test-planner` | Maps the diff to matrix groups and emits the dynamic matrix JSON (`scripts/ci/plan_backend_test_groups.py` — single source of truth; FULL-mode default = coverage-gate contract, #470). |
| **Stage 2** | `backend-tests` | Planner-driven parallel pytest groups (fast / core-unit / core-support / services) with coverage aggregation; core split gives the ~215-file bottleneck its own runner (#470). |
| **Stage 2** | `frontend-tests` | TypeScript type-check (`tsc --noEmit`), ESLint, and Vitest suite. |
| **Stage 3** | `backend-aggregate` | Coverage-only merge + FAIL-CLOSED tier gate (no containers). |
| **Stage 3** | `backend-contract` | OpenAPI schema validation, Canonical Startup (AUD-1.1), pgvector verification (parallel to coverage gate). |
| **Stage 3** | `backend-passk` | Mission pass^k reliability scoreboard (main-only, non-gating, parallel). |
| **Stage 3** | `build` | Next.js/Vite frontend production bundle compilation. |
| **Stage 4** | `deploy-frontend` | Deploys validated bundle to Firebase Hosting. |
| **Stage 4** | `render-deploy-preflight`| Validates service quotas, health probes, and deployment triggers. |

---

## 4. Maintenance & Evolution Rules

1. **Never Reintroduce Setup Tax:** টেস্ট রানারে নতুন প্যাকেজ যুক্ত করতে হলে `.github/actions/setup-backend/` বা ডকার বেস লেয়ারে যুক্ত করতে হবে; টেস্ট স্ক্রিপ্টে সরাসরি `apt-get` চালানো নিষিদ্ধ।
2. **Coverage Gate Invariant:** 
   * `MIN_BACKEND_COVERAGE: 30%`
   * `MIN_FRONTEND_COVERAGE: 16%`
   কভারেজ এর নিচে নামলে পিআর স্বয়ংক্রিয়ভাবে ব্যর্থ হবে।
3. **Plan Asset Discipline:** সিআই সংক্রান্ত যেকোনো স্থাপত্য পরিবর্তন এই ফাইলে ইন-প্লেস আপডেট হবে। কোনো `CI_PIPELINE_v2` বা ডেটেড ফাইল তৈরি করা যাবে না।
