---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:evolution_patch_v3_implementation_plan
subject: 🧬 SupremeAI Evolution Patch (v3.0) Implementation Plan
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# 🧬 SupremeAI Evolution Patch (v3.0) Implementation Plan

আমি আপনার দেয়া `supremeai-evolution.patch` ফাইলটি অ্যানালাইসিস করেছি। এটি একটি চমৎকার আর্কিটেকচারাল আপগ্রেড যা সিস্টেমে বেশ কিছু প্রোডাকশন-গ্রেড রেজিলিয়েন্স ফিচার যুক্ত করবে। তবে প্যাচ ফাইলটিতে কিছু ফরম্যাটিং ইস্যু থাকায় `git apply` দিয়ে এটি সরাসরি অ্যাপ্লাই করা যাচ্ছে না। 

তাই আমি ম্যানুয়ালি ফাইলগুলো তৈরি ও এডিট করে এই আপগ্রেডগুলো আপনার কোডবেসে ইমপ্লিমেন্ট করার প্ল্যান করেছি। 

## 🚀 Proposed Changes

এই ইভোলিউশন আপগ্রেডে ৪টি নতুন কোর মডিউল যুক্ত হবে এবং ৮টি এক্সিস্টিং ফাইলে পরিবর্তন আসবে:

### 1. New Core Modules (Resilience & Detection)
- **[NEW] `backend/core/health.py`**: Kubernetes-স্টাইল `/health`, `/ready`, ও `/live` প্রোব যুক্ত করবে যাতে সিস্টেমের হেলথ সবসময় মনিটর করা যায়।
- **[NEW] `backend/core/config_validator.py`**: স্টার্টআপের সময় সমস্ত Environment Variable স্কিমা-ভ্যালিডেট করবে (Fail-Fast অ্যাপ্রোচ)।
- **[NEW] `backend/core/circuit_breaker.py`**: এক্সটার্নাল API (Gemini/Groq) ফেইল করলে পুরো সিস্টেম যেন ক্র্যাশ না করে সেজন্য Circuit Breaker প্যাটার্ন। 
- **[NEW] `backend/utils/platform_detect.py`**: সিস্টেম অটোমেটিক বুঝতে পারবে সে Render, Vercel নাকি Firebase-এ চলছে এবং সে অনুযায়ী অ্যাডাপ্ট করবে।

### 2. Integration (Backend)
- **[MODIFY] `backend/main.py`**: নতুন হেলথ রাউটার ও স্টার্টআপ কনফিগ ভ্যালিডেটর ইন্টিগ্রেট করা।
- **[MODIFY] `backend/core/config.py`**: Platform Detection লজিক যুক্ত করা।
- **[MODIFY] `Dockerfile`**: কন্টেইনার হেলথ চেক করার জন্য `HEALTHCHECK` ইন্সট্রাকশন যুক্ত করা।

### 3. Integration (Frontend & Infrastructure)
- **[MODIFY] `frontend/src/utils/api.ts`**: API কলগুলোতে Retry ও সার্কিট ব্রেকার হ্যান্ডেলিং যুক্ত করা।
- **[MODIFY] `frontend/src/lib/queryClient.ts`**: গ্লোবাল Error Boundary যুক্ত করা।
- **[MODIFY] `render.yaml`**: Render-এর জন্য হেলথ চেক পাথ যুক্ত করা।
- **[MODIFY] `frontend/vite.config.ts`**: বিল্ডের সময় কনফিগ ডাম্প করা (ডিবাগিংয়ের জন্য)।
- **[MODIFY] `scripts/render_build_frontend.sh`**: বিল্ড ভ্যালিডেশন স্টেপ যুক্ত করা।

---

> [!WARNING]  
> **User Review Required:**
> এই প্যাচটি ইমপ্লিমেন্ট করার পর কিছু এনভায়রনমেন্ট ভ্যারিয়েবল (যেমন: `JWT_SECRET`, `ENV`, `BACKEND_URL`) না থাকলে সিস্টেম স্টার্টআপেই ক্র্যাশ করবে (Fail-Fast)। আপনার লোকাল ও ক্লাউড সার্ভারে সঠিক `.env` ভ্যালুগুলো বসানো আছে কিনা তা নিশ্চিত করতে হবে।

## 🔍 Verification Plan
1. ম্যানুয়ালি সমস্ত নতুন ফাইল তৈরি করব ও এক্সিস্টিং ফাইলগুলো এডিট করব।
2. `pnpm` এবং পাইথন স্ক্রিপ্ট দিয়ে বিল্ড ও হেলথ চেক রান করে দেখব কোনো স্টার্টআপ ক্র্যাশ হচ্ছে কিনা।
3. `/health` এন্ডপয়েন্টে কল করে চেক করব।

আপনি কি আমাকে এই ইভোলিউশন আপগ্রেডটি ইমপ্লিমেন্ট করা শুরু করার অনুমতি দিচ্ছেন? (Approve/Proceed বাটনে ক্লিক করুন)