# 🔁 SupremeAI ট্রানজিট, অটো-প্রুন ও রিটায়ারমেন্ট পাইপলাইন ডায়াগ্রাম

এই ফাইলে এজেন্টদের প্যাচ সাবমিশন, মাল্টি-রিপো ডিসপ্যাচ, সেলফ-হিলিং ফেইলিউর হ্যান্ডলিং এবং আর্কাইভ/জিরো-রেসিডিউ ক্লিনআপের পূর্ণাঙ্গ জীবনচক্র ডায়াগ্রাম আকারে সংরক্ষিত আছে।

---

## 📑 সূচিপত্র
1. **১. এন্ড-টু-এন্ড ট্রানজিট ও প্যাচ লাইফসাইকেল ডায়াগ্রাম**
2. **২. আর্কাইভ ও রিটায়ারমেন্ট ফ্লো (Zero Residue Flow)**
3. **৩. সেলফ-হিলিং মেকানিজম (Fail-Closed Issue Creation)**

---

## 🚀 ১. এন্ড-টু-এন্ড ট্রানজিট ও প্যাচ লাইফসাইকেল ডায়াগ্রাম

```mermaid
flowchart TD
    %% Agent Action
    subgraph AGENT_TASK [" 🤖 এজেন্টের কাজের ধরন "]
        Agent["এজেন্ট এক্সিকিউশন"]
        TaskType{"কাজের ধরন কী?"}
        CreateIssue["📝 নতুন ইস্যু তৈরি<br/>(Create Issue on open)"]
        SubmitPatch["📦 প্যাচ সাবমিট<br/>(৭টি নির্দিষ্ট ফোল্ডারের ভেতরে পরিবর্তন)"]
        
        Agent --> TaskType
        TaskType -- "ইস্যু তৈরির কাজ" --> CreateIssue
        TaskType -- "কোড ফিক্সের কাজ" --> SubmitPatch
    end

    %% Tower PR & Dispatch
    subgraph TOWER_GATE [" 🏰 MCP Control Tower ও ওপেন রিপো গেট "]
        TowerPR["🚀 Tower স্বয়ংক্রিয় PR তৈরি করে<br/>(supremeai-open:main)"]
        CIPass{"PR ও CI গেট পাস করেছে?"}
        OpenIssueClose["✅ ওপেন রিপোর ইস্যু ক্লোজ হয়"]
        DispatchSat["🛰️ পরিবর্তিত ফোল্ডার অনুযায়ী<br/>নির্দিষ্ট স্যাটেলাইট রিপোতে কোড পৌঁছায়"]

        SubmitPatch --> TowerPR
        TowerPR --> CIPass
        CIPass -- "হ্যাঁ (Pass)" --> OpenIssueClose
        OpenIssueClose --> DispatchSat
    end

    %% Multi-Repo & Monorepo Merge
    subgraph SYNC_STAGE [" 🔄 স্যাটেলাইট ও মাস্টার মনোরেপো সিঙ্ক "]
        SatMerge["৬টি স্যাটেলাইট রিপোতে মার্জ"]
        MonoMerge["👑 মূল মনোরেপো (supremeai)-তে সিঙ্ক ও মার্জ"]
        PipelineCheck{"স্যাটেলাইট ও supremeai-এর<br/>পাইপলাইন সফল হয়েছে?"}

        DispatchSat --> SatMerge
        SatMerge --> MonoMerge
        MonoMerge --> PipelineCheck
    end

    %% Zero Residue Cleanup
    subgraph CLEANUP [" 🧹 জিরো-রেসিডিউ অটো-প্রুন (Clean State) "]
        PruneOpen["🗑️ supremeai-open থেকে:<br/>১. ট্রানজিট প্যাচ ফাইল রিমুভ<br/>২. ট্রানজিট ব্রাঞ্চ ডিলিট"]
        CleanState["✨ ক্লিন ও স্টেডি স্টেট বজায় থাকে"]

        PipelineCheck -- "হ্যাঁ (All Successful)" --> PruneOpen
        PruneOpen --> CleanState
    end

    %% Failure Self Healing
    subgraph SELF_HEALING [" 🚨 সেলফ-হিলিং ইনসিডেন্ট রিপোর্টার "]
        FailAlert["⚠️ CI / PR / পাইপলাইন ফেইল করেছে!"]
        AutoNewIssue["🚨 supremeai-open-এ স্বয়ংক্রিয়ভাবে<br/>নতুন P0 ফিক্স ইস্যু তৈরি হয়"]

        CIPass -- "না (Failed)" --> FailAlert
        PipelineCheck -- "না (Failed)" --> FailAlert
        FailAlert --> AutoNewIssue
    end

    %% Styling
    style Agent fill:#334155,stroke:#94a3b8,stroke-width:2px,color:#f8fafc
    style TaskType fill:#1e293b,stroke:#64748b,stroke-width:2px,color:#f8fafc
    style CreateIssue fill:#0f766e,stroke:#14b8a6,stroke-width:2px,color:#f0fdfa
    style SubmitPatch fill:#4338ca,stroke:#818cf8,stroke-width:2px,color:#e0e7ff
    
    style TowerPR fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#e0e7ff
    style CIPass fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#d1fae5
    style OpenIssueClose fill:#065f46,stroke:#34d399,stroke-width:2px,color:#ecfdf5
    style DispatchSat fill:#1e3a8a,stroke:#3b82f6,stroke-width:2px,color:#eff6ff
    
    style SatMerge fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style MonoMerge fill:#4c1d95,stroke:#a855f7,stroke-width:2px,color:#f8fafc
    style PipelineCheck fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fef3c7

    style PruneOpen fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#fef2f2
    style CleanState fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#d1fae5
    
    style FailAlert fill:#881337,stroke:#f43f5e,stroke-width:2px,color:#fff1f2
    style AutoNewIssue fill:#991b1b,stroke:#ef4444,stroke-width:3px,color:#ffffff
```

---

## 📦 ২. আর্কাইভ ও রিটায়ারমেন্ট ফ্লো (Zero-Residue Retirement)

যখন কোনো ফিচার বা লিগ্যাসি কোড রিটায়ার করে সরাসরি `supremeai-archive`-এ স্থানান্তর করা হয়:

```mermaid
flowchart TD
    ArchiveTrigger["📦 ফিচার বা স্পেক রিটায়ারমেন্ট<br/>(supremeai-open ➔ supremeai-archive)"]
    
    RemoveActive["🗑️ সংশ্লিষ্ট স্যাটেলাইট ও মূল মনোরেপো (supremeai)<br/>থেকে কোড পুরোপুরি মুছে সাফ (Remove)"]
    
    ArchiveVerify{"আর্কাইভ সিঙ্ক ও স্যাটেলাইটের<br/>পাইপলাইন সফল হয়েছে?"}
    
    PruneOpenArch["🧹 supremeai-open থেকে:<br/>১. প্যাচ মুছে সাফ<br/>২. ট্রানজিট ব্রাঞ্চ ডিলিট"]
    
    ArchFail["🚨 যেকোনো ধাপে ফেইল করলে:<br/>supremeai-open-এ নতুন ইস্যু তৈরি হয়"]

    ArchiveTrigger --> RemoveActive
    RemoveActive --> ArchiveVerify
    
    ArchiveVerify -- "হ্যাঁ (Success)" --> PruneOpenArch
    ArchiveVerify -- "না (Failed)" --> ArchFail

    style ArchiveTrigger fill:#1e293b,stroke:#94a3b8,stroke-width:2px,color:#f8fafc
    style RemoveActive fill:#7f1d1d,stroke:#f87171,stroke-width:2px,color:#fef2f2
    style ArchiveVerify fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fef3c7
    style PruneOpenArch fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#d1fae5
    style ArchFail fill:#991b1b,stroke:#ef4444,stroke-width:3px,color:#ffffff
```

---

## 🛡️ ৩. নিয়মের মূল সারসংক্ষেপ:
1. **টাস্ক স্প্লিট:** এজেন্টের কাজ যদি ইস্যু তৈরির হয় তবে সে কেবল ইস্যু বানাবে; আর কোড ফিক্সের কাজ হলে সে ৭টি নির্দিষ্ট ফোল্ডারের ভেতরে প্যাচ দেবে।
2. **অটো PR ও ক্লোজার:** MCP Tower নিজে PR বানাবে। PR পাস করার সাথে সাথে ওপেন রিপোর সংশ্লিষ্ট ইস্যু ক্লোজ হয়ে যাবে এবং ফাইলগুলো নির্দিষ্ট স্যাটেলাইটে ছড়িয়ে যাবে।
3. **দ্বৈত মার্জ ও পাইপলাইন ভেরিফিকেশন:** স্যাটেলাইটে মার্জের পর মূল `supremeai`-তেও মার্জ হবে। দুটি জায়গাতেই পাইপলাইন সাকসেসফুল হতে হবে।
4. **অটো-প্রুন (জিরো রেসিডিউ):** সমস্ত পাইপলাইন গ্রিন হলে `supremeai-open` থেকে ওই প্যাচ এবং ব্রাঞ্চ সম্পূর্ণ মুছে ফেলা হবে।
5. **ইউনিভার্সাল সেলফ-হিলিং:** PR, CI বা স্যাটেলাইট পাইপলাইনের যেকোনো একটি ধাপে যদি ব্যর্থ (Fail) হয়, সাথে সাথে স্বয়ংক্রিয়ভাবে `supremeai-open`-এ একটি নতুন P0 ইস্যু ক্রিয়েট হয়ে যাবে।
6. **আর্কাইভ রুল:** আর্কাইভে কোড যাওয়ার পর অ্যাক্টিভ স্যাটেলাইট ও মনোরেপো থেকে তা রিমুভ হবে এবং পাইপলাইন গ্রিন হওয়ার পরই ওপেন রিপোর ট্রানজিট ক্লিন হবে।

