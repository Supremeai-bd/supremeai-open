# 🛡️ SupremeAI অ্যান্টি-এরর গার্ড, হুক ও রুলস আর্কিটেকচার (Error Prevention & Guard System)

এজেন্টরা (বা যে কোনো ডেভেলপার) কোড করার সময় যাতে কোনো ধরণের ভুল, সিকিউরিটি লিকেজ, বাউন্ডারি লঙ্ঘন বা ডুপ্লিকেট কাজ করতে **না পারে**, সেজন্য আমাদের ৪-স্তরের মেকানিক্যাল ডিফেন্স সিস্টেমের পূর্ণাঙ্গ ডায়াগ্রাম নিচে দেওয়া হলো।

---

```mermaid
flowchart TD
    %% ========================================================
    %% AGENT INTENT
    %% ========================================================
    subgraph INTENT [" 🤖 এজেন্টের কোড পরিবর্তন ও কাজের চেষ্টা "]
        Agent["এজেন্ট এক্সিকিউশন"]
        AttemptAction["কাজের উদ্যোগ<br/>(ফাইল এডিট / ব্রাঞ্চ তৈরি / কমিট / পুশ)"]
        Agent --> AttemptAction
    end

    %% ========================================================
    %% TIER 1: IN-MEMORY & STATIC RULES
    %% ========================================================
    subgraph TIER1 [" 📜 স্তর ১: এজেন্টের মেমোরি রুলস (Constitutional Rules) "]
        R_Constitution["📜 <b>AGENTS.md & Single Door SSOT</b><br/>• নো ডিরেক্ট পুশ (No Direct Push)<br/>• নো রুট শ্যাডোয়িং (No Root Shadowing)<br/>• নো গোস্ট ফিক্স (No Ghost Fixes)"]
        R_Invariants["⚖️ <b>৫টি ইউনিভার্সাল ইনভ্যারিয়েন্ট</b><br/>• ডুয়েল রিবেস (Dual-Rebase 0 Behind)<br/>• বাউন্ডারি কঠোরতা (Approved Domains only)<br/>• সুপিরিয়র রিপ্লেসমেন্ট (Clean Code)"]
        
        AttemptAction --> R_Constitution
        AttemptAction --> R_Invariants
    end

    %% ========================================================
    %% TIER 2: LOCAL PRE-COMMIT HOOKS
    %% ========================================================
    subgraph TIER2 [" 🪝 স্তর ২: লোকাল গিট হুকস (Shift-Left Pre-Commit Hooks) "]
        Hook_Stale["⚠️ <b>Stale Branch Guard</b><br/>রিমোট মেইনের সাথে রিবেস ছাড়া কমিট ব্লক"]
        Hook_Boundary["🚧 <b>Boundary Sanitization Guard</b><br/>রুট ডিরেক্টরি বা অননুমোদিত ফোল্ডারে ফাইল সেভ ব্লক"]
        Hook_Dup["🚫 <b>No-Versioned-Duplicate Guard</b><br/>তারিখ বা সিকোয়েন্স দিয়ে ক্লোন ফাইল তৈরি ব্লক"]
        Hook_Index["📑 <b>Index Freshness Guard</b><br/>স্ক্রিপ্ট ইনডেক্স রিজেনারেট নিশ্চিতকরণ"]

        R_Constitution --> Hook_Stale
        R_Invariants --> Hook_Boundary
        Hook_Stale --> Hook_Dup
        Hook_Boundary --> Hook_Index
    end

    %% ========================================================
    %% TIER 3: TOWER MCP CAS & WORKSPACE GATE
    %% ========================================================
    subgraph TIER3 [" 🏰 স্তর ৩: MCP Control Tower ও CAS গেট (Fail-Closed) "]
        CAS_Gate["🔒 <b>Fail-Closed CAS Gate (baseSha Pin)</b><br/>লেটেস্ট ব্লব SHA পিন না থাকলে সাবমিশন রিজেক্ট"]
        Vault_Gate["🔐 <b>Credential Zero-Leak Gate</b><br/>প্লেইনটেক্সট সিক্রেট/টোকেন পাওয়া গেলে সাথে সাথে ব্লক"]
        Lease_Gate["⏱️ <b>30-Min Atomic Lease Lock</b><br/>ক্লেইম ছাড়া বা টাইমআউট হলে পুশ অসম্ভব"]
        Anti_Stampede["🛡️ <b>Anti-Stampede & Idempotency Guard</b><br/>একই টাস্কে ডুপ্লিকেট PR বা কনফ্লিক্ট অর্ডার ব্লক"]

        Hook_Dup --> CAS_Gate
        Hook_Index --> Vault_Gate
        CAS_Gate --> Lease_Gate
        Vault_Gate --> Anti_Stampede
    end

    %% ========================================================
    %% TIER 4: REMOTE CI VERIFICATION BATTERY
    %% ========================================================
    subgraph TIER4 [" 🧪 স্তর ৪: রিমোট CI ভেরিফিকেশন গেটস (pipeline.yml) "]
        CI_3Tier["🔍 <b>3-Tier Verification</b><br/>Reflection ➔ Smoke ➔ Automated Unit Tests"]
        CI_SAST["🛡️ <b>Bandit SAST & Secret Scanner</b><br/>জিরো ভালনারেবিলিটি র‍্যাচেট পলিসি"]
        CI_Parity["⚖️ <b>Test Parity Guard</b><br/>প্রতিটি স্ক্রিপ্টের জন্য টেস্ট থাকা বাধ্যতামূলক"]
        CI_Quarantine["🚨 <b>3-Strike Quarantine</b><br/>টানা ৩ বার ফেইল করলে টাস্ক অটো-কোয়ারেন্টিন"]

        Lease_Gate --> CI_3Tier
        Anti_Stampede --> CI_SAST
        CI_3Tier --> CI_Parity
        CI_SAST --> CI_Quarantine
    end

    %% ========================================================
    %% OUTCOMES
    %% ========================================================
    subgraph OUTCOME [" 🏁 ফলাফল ও চূড়ান্ত আউটপুট "]
        PassMerge["✅ <b>Autonomous Landing & Safe Dispatch</b><br/>সব গেট পাস করলে স্যাটেলাইটে নিরাপদে কোড যায়"]
        FailBlock["🛑 <b>Fail-Closed Block & Auto Incident</b><br/>যেকোনো গেটে ভুল ধরা পড়লে তাৎক্ষণিক ব্লক + নতুন ফিক্স ইস্যু তৈরি"]
    end

    CI_Parity -- "সব গার্ড সফল" --> PassMerge
    
    Hook_Stale -- "ভুল ধরা পড়লে" --> FailBlock
    Hook_Boundary -- "ভুল ধরা পড়লে" --> FailBlock
    CAS_Gate -- "ভুল ধরা পড়লে" --> FailBlock
    Vault_Gate -- "ভুল ধরা পড়লে" --> FailBlock
    CI_3Tier -- "ভুল ধরা পড়লে" --> FailBlock
    CI_SAST -- "ভুল ধরা পড়লে" --> FailBlock
    CI_Quarantine --> FailBlock

    FailBlock -.->|সেলফ-হিলিং নতুন ইস্যু| Agent

    %% Styling
    style Agent fill:#334155,stroke:#94a3b8,stroke-width:2px,color:#f8fafc
    style AttemptAction fill:#1e293b,stroke:#64748b,stroke-width:2px,color:#f8fafc

    style TIER1 fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#f8fafc
    style R_Constitution fill:#1e1b4b,stroke:#6366f1,stroke-width:1px,color:#e0e7ff
    style R_Invariants fill:#1e1b4b,stroke:#6366f1,stroke-width:1px,color:#e0e7ff

    style TIER2 fill:#0f172a,stroke:#f59e0b,stroke-width:2px,color:#f8fafc
    style Hook_Stale fill:#451a03,stroke:#d97706,stroke-width:1px,color:#fef3c7
    style Hook_Boundary fill:#451a03,stroke:#d97706,stroke-width:1px,color:#fef3c7
    style Hook_Dup fill:#451a03,stroke:#d97706,stroke-width:1px,color:#fef3c7
    style Hook_Index fill:#451a03,stroke:#d97706,stroke-width:1px,color:#fef3c7

    style TIER3 fill:#0f172a,stroke:#a855f7,stroke-width:2px,color:#f8fafc
    style CAS_Gate fill:#3b0764,stroke:#9333ea,stroke-width:1px,color:#f5d0fe
    style Vault_Gate fill:#3b0764,stroke:#9333ea,stroke-width:1px,color:#f5d0fe
    style Lease_Gate fill:#3b0764,stroke:#9333ea,stroke-width:1px,color:#f5d0fe
    style Anti_Stampede fill:#3b0764,stroke:#9333ea,stroke-width:1px,color:#f5d0fe

    style TIER4 fill:#0f172a,stroke:#06b6d4,stroke-width:2px,color:#f8fafc
    style CI_3Tier fill:#083344,stroke:#0891b2,stroke-width:1px,color:#cffafe
    style CI_SAST fill:#083344,stroke:#0891b2,stroke-width:1px,color:#cffafe
    style CI_Parity fill:#083344,stroke:#0891b2,stroke-width:1px,color:#cffafe
    style CI_Quarantine fill:#083344,stroke:#0891b2,stroke-width:1px,color:#cffafe

    style PassMerge fill:#064e3b,stroke:#10b981,stroke-width:3px,color:#ecfdf5
    style FailBlock fill:#881337,stroke:#ef4444,stroke-width:3px,color:#ffffff
```

---

### 🛡️ ৪-স্তরের মেকানিক্যাল ডিফেন্সের বিস্তারিত ব্যাখ্যা:

1. **স্তর ১: ইন-মেমোরি ও কনস্টিটিউশন রুলস (`AGENTS.md`):**
   - **উদ্দেশ্য:** এজেন্ট কাজ শুরু করার আগেই তার কনটেক্সটে রুলস ঢুকিয়ে দেওয়া।
   - **কীভাবে ঠেকায়:** সরাসরি পুশ করা নিষিদ্ধ, রুট ফোল্ডারে ফাইল রাখা নিষিদ্ধ, এবং পুরোনো ভুল কোড জোড়াতালি দেওয়া নিষিদ্ধ।

2. **স্তর ২: লোকাল প্রি-কমিট হুকস (Shift-Left Hooks):**
   - **উদ্দেশ্য:** ভুল কোড লোকাল মেশিন থেকেই যাতে গিট-এ কমিট হতে না পারে।
   - **কীভাবে ঠেকায়:**
     - *Stale Branch Guard:* রিমোট `origin/main`-এর থেকে পিছিয়ে থাকলে কমিট বন্ধ করে দেয়।
     - *Boundary Guard:* অনুমোদিত ৭টি ফোল্ডার ছাড়া অন্য কোথাও ফাইল পরিবর্তন করলে আটকে দেয়।
     - *No-Versioned-Duplicate Guard:* তারিখ দেওয়া কপি ফাইল বানালে সাথে সাথে আটকে দেয়।

3. **স্তর ৩: MCP Control Tower ও Fail-Closed CAS গেট:**
   - **উদ্দেশ্য:** ভুল বা পুরনো কোড দিয়ে অন্য কারো নতুন কোড ওভাররাইট হওয়া ঠেকানো।
   - **কীভাবে ঠেকায়:**
     - *CAS Gate (`baseSha` Pin):* এডিটেড ফাইলের ফ্রেশ কমিট SHA না মিললে রিজেক্ট করে (Stale-Base Error)।
     - *Zero-Leak Rule:* পাসওয়ার্ড বা এপিআই কি থাকলে রিজেক্ট করে।
     - *Atomic Lease:* ক্লেইম ছাড়া বা ৩০ মিনিটের বেশি দেরি করলে স্বয়ংক্রিয়ভাবে লক করে দেয়।

4. **স্তর ৪: রিমোট সিআই ভেরিফিকেশন গেটস (`pipeline.yml`):**
   - **উদ্দেশ্য:** সার্ভারে কোড মার্জ হওয়ার শেষ প্রতিরক্ষা।
   - **কীভাবে ঠেকায়:**
     - *3-Tier Verify:* রিফ্লেকশন ➔ স্মোক টেস্ট ➔ অটোমেটেড টেস্ট পাস হতে হবে।
     - *Test Parity:* নতুন কোডের সাথে টেস্ট না থাকলে বিল্ড লাল হয়ে যাবে।
     - *3-Strike Quarantine:* ৩ বার ফেইল করলে টাস্কটি কোয়ারেন্টিনে পাঠিয়ে দেয়।

