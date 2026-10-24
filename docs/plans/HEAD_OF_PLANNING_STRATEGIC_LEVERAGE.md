---
id: head-of-planning-strategic-leverage
subject: "Strategic Leverage Master Directive (Timeless Living Plan)"
document_role: roadmap
planning_authority: Architecture Governance / Planning Circle
status: active
plan_lifecycle: living — permanent single source of truth
target_scope: supremeai_internal
last_verified: 2026-09-18
---

# Strategic Leverage Master Directive (Universal & Timeless)

> **কোর ফিলোসফি (চিরন্তন নীতি):** অতিরিক্ত নিয়ম নয়—বিদ্যমান রুলস ঠিক রেখে **সর্বোচ্চ রি-ইউজ**, **ওপেন-সোর্স (OSS) লিভারেজ** এবং **অডিট-ফার্স্ট সিদ্ধান্ত**। এই নির্দেশিকা আজ, ১০ দিন, ১০০ দিন বা ১০০০ দিন পরেও একইভাবে কার্যকর।

### 1. তিনটি চিরন্তন স্তম্ভ (The 3 Eternal Pillars)
1. **Internal Reuse First:** নতুন কোড নয়—কোডবেসের বিদ্যমান সমস্ত রুট (`docs/generated/route_inventory.md`), `backend/runs/` ফ্যাব্রিক এবং মেমোরি আগে রি-ইউজ করুন।
2. **External OSS Leverage:** চাকা নতুন করে আবিষ্কার না করে Aider (repo-map), Mem0/Letta (মেমোরি), Anthropic (ক্যাশিং), এবং FastMCP প্যাটার্ন অ্যাডপ্ট করুন।
3. **Audit First (Zero Waste):** কাজ শুরুর আগে অডিট চালান। কাজ ইতিমধ্যে থাকলে `[DONE]` দিন এবং পরের টাস্কে যান। ডুপ্লিকেট কাজ সম্পূর্ণ নিষিদ্ধ।

### 2. Live Priority Board (Audit ➔ Decide ➔ Execute)
| # | Priority | Audit Probe (ডাইনামিক অডিট কমান্ড) | Exit Criteria (কখন সম্পন্ন) | Status |
|---|---|---|---|---|
| **P1** | **Wire Existing Routes** | `python scripts/ci/generate_route_inventory.py` & `controlPlane.ts` | সমস্ত অর্ফান রুট UI/MCP-তে কানেক্টেড | `[IN_PROGRESS]` |
| **P2** | **Context & Prompt Caching** | Check `backend/context/` & prompt headers | Repo-map generator + caching active | `[READY]` |
| **P3** | **Memory Flywheel** | `pytest tests/unit/test_memory_consolidation.py` | ৩-টায়ার মেমোরি (SQLite+Supabase+Parquet) | `[READY]` |
| **P4** | **Mission Test Suite** | `pytest tests/missions/ -q` | সমস্ত মিশন টেস্ট ১০০% পাস ও রিগ্রেশন-মুক্ত | `[IN_PROGRESS]` |
| **P5** | **Compute Sovereignty** | Check compute dispatcher (`scripts/compute/`) | ইউজার এনভায়রনমেন্ট অনুযায়ী হেডলেস GPU/সার্ভার এক্সিকিউশন ভেরিফাইড | `[READY]` |

### 3. The 3-Agent Triad Protocol (Plan PR ➔ Build ➔ Auto-Merge ➔ Loop)
- **Agent 1 (Planner):** কোডবেস অডিট করে ১টি কাজের প্ল্যান ডকুমেন্ট (কী + কীভাবে) লিখে ডেডিকেটেড PR ওপেন করে।
- **Agent 2 (Builder):** প্ল্যানটি বাস্তবে যাচাই করে (ভুল থাকলে প্ল্যান শুধরে) সেই PR-এ ক্লিন কোড ও টেস্ট লিখে।
- **Agent 3 (Reviewer / Truth Judge):** নিরপেক্ষভাবে PR রিভিউ ও টেস্ট ভেরিফাই করে। সব পাস করলে **AUTO-MERGE PR** করে, বোর্ডে স্ট্যাটাস `[DONE]` করে এবং হ্যান্ডঅফ ফিরিয়ে দেয় **Agent 1**-এর কাছে।
- **Continuous Loop:** Agent 1 হ্যান্ডঅফ পেয়ে পরবর্তী কাজের জন্য নতুন প্ল্যান ডকুমেন্ট ও নতুন PR তৈরি করে ➔ চক্র চলমান থাকে।