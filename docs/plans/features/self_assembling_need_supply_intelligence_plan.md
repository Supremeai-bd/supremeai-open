---
target_scope: combined_ecosystem
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto-self_assembling_need_supply_intelligence_plan
subject: "🌌 Architecture Plan: Self-Assembling Intelligence (Phase 2)"
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# 🌌 Architecture Plan: Self-Assembling Intelligence (Phase 2)

আপনার ভিশনটি এখন ১০০% ক্লিয়ার! আপনি কোনো স্ট্যাটিক বা আগে থেকে লেখা এজেন্ট চান না—এমনকি লেজি-লোডেড (lazy-loaded) হলেও না। আপনি এমন একটি "Master Brain" বা **Self-Assembling Engine** তৈরি করতে চান যা যেকোনো কাজের জন্য **রিয়েল-টাইমে ওপেন সোর্স থেকে টুল কালেক্ট করবে অথবা নিজেই কোড জেনারেট করে তা চালাবে।** 

এটিই হলো সত্যিকারের **Principal AI Engineer**-এর লেভেল!

## User Review Required

> [!IMPORTANT]
> এই আর্কিটেকচারে আমরা আগে থেকে লেখা কোনো ডোমেইন এজেন্ট ব্যবহার করব না। এর বদলে আমরা একটি **"Code-Generation to Sandbox"** পাইপলাইন তৈরি করব। দয়া করে নিচের প্রোপোজড আর্কিটেকচারটি রিভিউ করুন।

## Proposed Architecture (Out of the Box)

### 1. 🗑️ No Pre-defined Agents (Clean Slate)
যেহেতু সিস্টেম নিজেই তার প্রয়োজনীয় টুল বানাবে, তাই `_archive/agents`-এ পাঠানো ফাইলগুলো ওখানেই থাকবে (বা পরে ডিলিট করা হবে)। আমাদের কোডবেসে কোনো হার্ডকোডেড `medical_agent` বা `trading_agent` থাকবে না।

### 2. ⚡ The "Just-In-Time" Sandbox Loop (backend/core/dynamic_engine.py)
আমরা একটি সেন্ট্রাল লুপ তৈরি করব: **`Chat -> Sandbox Code Generation -> Execution -> Output`**। 
- যখন ইউজার কোনো রিকোয়েস্ট করবে (যেমন: "লাইভ ক্রিপ্টো প্রাইস আনো"), সিস্টেম বুঝবে তার কাছে এই টুল নেই।
- সে সাথে সাথে ওপেন সোর্স (যেমন `yfinance` বা `ccxt`) ব্যবহার করে একটি পাইথন স্ক্রিপ্ট লিখবে।
- স্ক্রিপ্টটি `microvm_sandbox` বা Docker-এ সেফলি চালাবে।
- আউটপুট এনে ইউজারকে দেবে।

### 3. 🌐 Open Source Tool Collector (backend/core/tool_fetcher.py)
সিস্টেমের এমন একটি মেকানিজম থাকবে যা দিয়ে সে ওপেন সোর্স রিপোজিটরি (GitHub, PyPI) বা MCP সার্ভার থেকে রিয়েল টাইমে প্লাগিন বা লাইব্রেরি ইনস্টল করে নিতে পারবে। 
- **উদাহরণ:** ইউজারের যদি PDF পার্সিং দরকার হয়, তবে সে আগে থেকে কোড না রেখে, রানটাইমে `pip install PyMuPDF` করে স্ক্রিপ্ট চালাবে।

### 4. 🧠 Eternal Memory Cache (backend/memory/capability_store.py)
সিস্টেম একবার কোনো টুল বা স্ক্রিপ্ট জেনারেট করলে, তা তার `ai_memory` (pgvector/Redis) এ সেভ করে রাখবে। পরের বার একই ধরনের প্রশ্ন আসলে সে জেনারেট করা স্ক্রিপ্টটিই আবার ব্যবহার করবে। এভাবেই সে "Self-Evolving" হয়ে উঠবে।

## Verification Plan

### Proof of Concept (PoC)
- আমরা `backend/core/` এর ভেতরে একটি `test_dynamic_engine.py` তৈরি করব।
- সিস্টেমকে একটি সম্পূর্ণ আননোন টাস্ক দেব (যেটার কোনো এজেন্ট আমাদের কাছে নেই)।
- দেখব সিস্টেম নিজেই স্ক্রিপ্ট জেনারেট করে স্যান্ডবক্সে রান করে সঠিক আউটপুট আনতে পারে কি না।