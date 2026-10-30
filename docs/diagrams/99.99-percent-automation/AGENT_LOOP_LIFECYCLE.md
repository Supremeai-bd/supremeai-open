# 🔄 Continuous Agent Loop লাইফসাইকেল ও ডিসপ্যাচ ডায়াগ্রাম

এই ফাইলে SupremeAI অটোনোমাস এজেন্ট লুপের ডিসপ্যাচ লজিক, ইস্যু প্রায়োরিটাইজেশন এবং স্পেশালাইজড রোল অ্যাসাইনমেন্টের নিয়মাবলী তুলে ধরা হয়েছে।

---

## 📑 সূচিপত্র
1. **১. এজেন্ট লুপ ও ডিসপ্যাচ আর্কিটেকচার**
2. **২. লুপের সিদ্ধান্ত অ্যালগরিদম (Decision Steps)**
3. **৩. স্পেশালাইজড রোল ও ক্যাডেন্স টাইমার**

---

## 🚀 ১. এজেন্ট লুপ ও ডিসপ্যাচ আর্কিটেকচার

```mermaid
flowchart TD
    %% Agent Layer
    subgraph AGENTS [" 🤖 এজেন্ট আগমন ও সংযোগ "]
        AnyAgent["যেকোনো এজেন্ট<br/>(External, Internal, Web-based)"]
        Tower["🏰 MCP Control Tower<br/>(Single Door Proxy & Auth)"]
        SingleCommand["⚡ একক কমান্ড এক্সিকিউশন:<br/><code>python scripts/agents/continuous_agent_loop.py</code>"]
        
        AnyAgent -->|১. কানেক্ট করে| Tower
        Tower -->|২. এক্সিকিউট করে| SingleCommand
    end

    %% Loop Decision Layer
    subgraph LOOP [" 🔄 Continuous Agent Loop (The Decision Engine) "]
        CheckBoard["📋 গিটহাব ইস্যু বোর্ড স্ক্যান"]
        CadenceCheck{"⏰ ফিক্সড টাইম ক্যাডেন্স টাইমার ওভার?<br/>(Cadence Limit Exceeded?)"}
        
        IssueExist{"❓ ক্লেইম করার মতো কোনো ইস্যু আছে?<br/>(Any claimable issue exists?)"}
        PickTop["🎯 সর্টিং ও ফিল্টারিং:<br/>সর্বোচ্চ প্রায়োরিটির ইস্যু বাছাই<br/>(Find Top Priority / P0 Issue)"]

        SingleCommand --> CheckBoard
        CheckBoard --> CadenceCheck
        
        CadenceCheck -- "না (টাইম বাকি আছে)" --> IssueExist
        IssueExist -- "হ্যাঁ (ইস্যু আছে)" --> PickTop
    end

    %% Coder Dispatch
    subgraph CODER_DISPATCH [" 👨‍💻 Coder Agent ডিসপ্যাচ "]
        CoderAction["📦 মেশিন-রিডেবল JSON পে-লোড:<br/>• নির্বাচিত Top Issue (#Number)<br/>• ক্লেইম থেকে সাবমিট পর্যন্ত সব রুলস<br/>• ফাইল ও ডোমেইন স্কোপ"]
        CoderAgent["🚀 Coder Agent Execution<br/>(Claim ➔ Fix ➔ Verify ➔ Bridge Submit)"]
        
        PickTop --> CoderAction
        CoderAction --> CoderAgent
    end

    %% Specialized Roles Dispatch
    subgraph ROLE_DISPATCH [" 👥 অন্যান্য ৫-৬ টাইপ স্পেশালাইজড রোল ডিসপ্যাচ "]
        RoleAction["📦 মেশিন-রিডেবল JSON পে-লোড:<br/>• অ্যাসাইনকৃত রোলের রুলস ও গাইডলাইন<br/>• অডিট বা চেকের সুনির্দিষ্ট স্কোপ"]
        OtherAgents["🛡️ Specialized Roles Execution:<br/>• AUDITOR (কোডবেস অডিট)<br/>• SCOUT (ইকোসিস্টেম স্ক্যান)<br/>• CI_FIXER (পাইপলাইন সারাই)<br/>• REVIEWER (কন্ট্রাক্ট রিভিউ)"]
        
        CadenceCheck -- "হ্যাঁ (টাইমার ওভার, ইস্যু থাকলেও)" --> RoleAction
        IssueExist -- "না (কোনো ইস্যু নেই)" --> RoleAction
        RoleAction --> OtherAgents
    end

    %% Styling
    style AnyAgent fill:#334155,stroke:#94a3b8,stroke-width:2px,color:#f8fafc
    style Tower fill:#4338ca,stroke:#818cf8,stroke-width:2px,color:#f8fafc
    style SingleCommand fill:#0f172a,stroke:#38bdf8,stroke-width:3px,color:#38bdf8
    
    style CheckBoard fill:#1e293b,stroke:#64748b,stroke-width:2px,color:#f8fafc
    style CadenceCheck fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fef3c7
    style IssueExist fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#d1fae5
    style PickTop fill:#065f46,stroke:#34d399,stroke-width:2px,color:#ecfdf5

    style CoderAction fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#e0e7ff
    style CoderAgent fill:#1e3a8a,stroke:#3b82f6,stroke-width:2px,color:#eff6ff
    
    style RoleAction fill:#3f2c06,stroke:#eab308,stroke-width:2px,color:#fef08a
    style OtherAgents fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#f0fdf4
```

---

## ⚙️ ২. লুপের সিদ্ধান্ত অ্যালগরিদম (Decision Steps)

1. **একক কমান্ড:** যেকোনো এজেন্ট (External/Internal/Web-based) শুধুমাত্র `python scripts/agents/continuous_agent_loop.py` রান করে।
2. **ক্যাডেন্স টাইমার চেক:** বোর্ডে ইস্যু থাকা সত্ত্বেও যদি কোনো রোলের নির্দিষ্ট সময়সীমা (Cadence Timer) অতিক্রান্ত হয়, তবে লুপ সরাসরি সেই স্পেশালাইজড রোল ডিসপ্যাচ করে (অ্যান্টি-স্টারভেশন নীতি)।
3. **ইস্যু উপস্থিতি যাচাই:** টাইমার ঠিক থাকলে লুপ দেখে — "ক্লেইম করার মতো কোনো ইস্যু আছে কি না?"
4. **সর্বোচ্চ প্রায়োরিটি বাছাই:** একাধিক ইস্যু থাকলে স্বয়ংক্রিয়ভাবে সর্বোচ্চ প্রায়োরিটি (P0/Top) ইস্যু বাছাই করে।
5. **মেশিন-রিডেবল পে-লোড:** কোডার বা স্পেশালাইজড এজেন্টকে কাজের বিস্তারিত, নিয়মাবলী এবং স্কোপ সম্পূর্ণ JSON আকারে দেওয়া হয় যাতে এজেন্ট কোনো অনুমান ছাড়াই নিখুঁত কাজ করতে পারে।

