# LESSONS_LEARNED

> **[🤖 AI AGENT INSTRUCTION]** 
> This is a core SupremeAI "Brain" file. When adding a new lesson:
> 1. Add it to the TOP of the list (reverse chronological).
> 2. Include Date, Issue, Fix, and Lesson.
> 3. DO NOT delete or overwrite past historical entries.
> 4. Keep it concise and technical.

## 2026-09-28 — 🏛️ Rules vs. Architecture Conflation: কন্সটিটিউশনে পাইপলাইন অটোমেশন ঢুকিয়ে এজেন্টদের কনফিউজ করা এবং 'The 101% Benefit Principle'

- **সমস্যা:** `AGENTS.md`-তে Rule 28 হিসেবে "Cascade Hold" (আগের ধাপে সমস্যা থাকলে পেছনের সব PR অটো-হোল্ড) এবং Rule 27 হিসেবে "Dynamic Queue Insertion (+1 শিফট)" অন্তর্ভুক্ত করা হয়েছিল। এটি ছিল এজেন্টের জন্য বড় বিভ্রান্তি: Cascade Hold বা Queue Shifting হলো সিআই/মার্জ ট্রেনের **আর্কিটেকচার ও ইঞ্জিন অটোমেশন** (`scripts/ci/issue_queue_manager.py`), যা এজেন্টের নিজের আচরণ বা কোড লেখার কোনো রুল নয়। এর ফলে আর্কিটেকচার ও রুলসের সীমানা গুলিয়ে সিস্টেম আবার স্ফীত ও জটিল হচ্ছিল।
- **Root Cause:** আর্কিটেকচারাল মেকানিজম (ইঞ্জিন কীভাবে কাজ করে) এবং এজেন্টের কন্সটিটিউশনাল রুলস (এজেন্ট কী আচরণ করবে/কী করবে না)-এর মধ্যে স্পষ্ট সীমারেখা না টানা।
- **The 101% Benefit Principle:**  
  > **“সমস্যা পেলে শুধু কোড ফিক্স করা ১% লাভ; কিন্তু সেই সমস্যা ভবিষ্যতে আর কখনোই যেন না ঘটতে পারে তা রুট লেভেলে বন্ধ করা ১০১% লাভ।”**  
  - রুলসের কাজ হলো ১০১% সুরক্ষাকবচ তৈরি করা যাতে ভুলের রুট-কজ সমূলে বিনাশ হয়।
  - আর্কিটেকচারের কাজ হলো সিস্টেমকে টেকনিক্যালি রান করানো (মার্জ ট্রেন, ডিস্ট্রিবিউটেড লকিং ইত্যাদি)।
- **ফিক্স:**
  - `AGENTS.md` থেকে Rule 27 ও Rule 28 অপসারণ করে সিআই আর্কিটেকচারে স্থানান্তর করা হয়েছে।
  - `AGENTS.md`-তে শুধুমাত্র এজেন্টের বাস্তব কার্যকরী আচরণ রুলস হিসেবে রাখা হয়েছে:
    1. **Slot Isolation:** `acquire_role_slot.py` + `<lane>-<N>-<issue#>-<slug>`.
    2. **Atomic Claim Lock & File Declaration:** কাজ শুরুর আগে ক্লেইম ও কমেন্টে `Touching files: ...` ঘোষণা।
    3. **3-Tier Verification First:** অনুমানে ডিলিট/এডিট নিষিদ্ধ। (১) Reflection check, (২) Boot smoke test, (৩) Pytest.
    4. **Atomic Blast Radius:** ১ PR = ১ ইস্যু, সর্বোচ্চ ১–২ ফাইল।
    5. **The Dual-State Game (Solver ➔ Peer Reviewer):** আনক্লেইমড কাজ থাকলে কোডার (State A); কাজ শেষ হলে সহকর্মীর PR অডিটকারী পিয়ার রিভিউয়ার (State B)।
- **লেসন:** রুলস সবসময় সংক্ষেপ, সরাসরি এবং ভুলের রুট-কজ নির্মূলকারী হতে হবে। ইঞ্জিনের মেকানিক্সকে রুলস বানিয়ে এজেন্টের কনটেক্সট বা ব্রেন জ্যাম করা আত্মঘাতী।

## 2026-09-28 — 🔁 Duplicate PRs: 12টি Branch-এ Issue-Number না থাকায় ও `has-pr` Label-বিহীন PR খোলায় ১টি Issue-এ ৪টি পর্যন্ত PR (GAP-DUPLICATE-01) (#2296)

- **সমস্যা:** Step 1 execution-এ Issue #2252, #2253, #2255, #2256, #2248-এর জন্য ২-৪টি করে duplicate PR তৈরি হয়। মোট ১২টি `coder-1`, `coder-2` ইত্যাদি generic slot-only branch name ব্যবহার করায় কোনো agent-ই detect করতে পারেনি যে সেই issue-এ আগে কাজ চলছে।
- **Root Causes (4টি):**
  1. **Branch name-এ issue number নেই** — `coder-1`, `coder-4` শুধু slot; দ্বিতীয় agent-এর কাছে collision signal ছিল না।
  2. **PR open করার পর `has-pr` label issue-এ যোগ করা হয়নি** — `atomic_claim.sh` শুধু `status:in-progress` check করে, `has-pr` চেক করেনি।
  3. **Concurrent agents race** — একাধিক agent একই মিলিসেকেন্ডে একই issue unclaimed দেখে দুজনেই PR খুলেছে।
  4. **Pre-PR duplicate check নেই** — `gh pr create` করার আগে কেউ check করেনি "এই issue-এ কোনো open PR আছে কি?"
- **ফিক্স:**
  - `AGENTS.md` Rule **#24**: `gh pr create` সফল হওয়ার সাথে সাথে `gh issue edit <N> --add-label 'has-pr'` বাধ্যতামূলক (zero-tolerance)।
  - `AGENTS.md` Rule **#25**: Branch name format MUST be `<lane>-<N>-<issue_number>-<slug>` — generic slot-only (`coder-1`) strictly forbidden।
  - `atomic_claim.sh` update: `has-pr` label দেখলেই claim abort (exit 1); open PR search করে backfill করে। `BRANCH_NAME` env var চেক করে issue number আছে কিনা।
- **লেসন:** **"একটা লেবেল সব duplicate ঠেকায়।"** PR খোলার সাথে সাথে `has-pr` label = পরবর্তী সব agent-এর জন্য hard stop। Branch name-এ issue number = collision-detection trivial। এই দুটো নিয়ম এক সাথে থাকলে ৪টি root cause-এর ৩টিই আপনা-আপনি বন্ধ হয়।

## 2026-09-27 — 🧭 Lane Boundary: Planner Opens PRs (L1 Violation — Rule Gap, Closed) (#1864)


- **সমস্যা:** `agent-1-planner` দুটি PR (#1805, #1851) খুলেছিল — planner lane-এর ম্যান্ডেট হলো audit + GitHub issues only, PR নয়। Root cause ছিল agent-এর স্মৃতিভ্রংশতা নয় বরং **rule gap**: charter-এর planner row-তে `docs/plans/` ownership দেওয়া ছিল কিন্তু "Forbidden" কলামে PR খোলা নিষিদ্ধ ছিল না — "plan-doc ownership" কে "plan-doc PR authority" হিসেবে পড়া সম্ভব ছিল।
- **ফিক্স:** (১) Charter hardening — planner = **issue-output lane**, branch slot নেই, PR খোলা স্পষ্টভাবে forbidden; প্ল্যান ডকুমেন্ট `handoff:coder` issue-এর মাধ্যমে coder lane land করবে (charter §1 planner row + new invariant #23)। (২) **Machine guard** (আলাদা issue): PR gate এখন `planner-*` branch থেকে খোলা PR ব্লক করবে — নিয়ম এখন enforcement-নির্ভর, memory-নির্ভর নয়। (৩) এই ledger entry — ভুল একবার, শিক্ষা স্থায়ী।
- **লেসন:** সীমানা-নিয়ম (lane boundary) চার্টারে "allowed" লেখা যথেষ্ট নয় — যে behavior নিষিদ্ধ, সেটা Forbidden কলামে + machine guard-এ স্পষ্ট থাকতে হবে। **"Allowed scope" ≠ "authority to land"**: discovery/specification authority আর landing authority ভিন্ন জিনিস — ecosystem-এ এক lane খুঁজে দেয়, অন্য lane বানায়, আরেক lane বসায়।

## 2026-09-27 — 🧩 Monkeypatch-Proof Dependency Resolution: function-level `from`-import শ্যাডো-attribute বাইপাস (#2098)

- **Issue:** #2098 — CI-only 4× `"Event loop is closed"` failure in core-unit rate-limit tests; local runs সবসময় pass করত।
- **সমস্যা:** `_check_rate_limit`-এর ভেতরে function-level `from core.cache.redis_manager import redis_manager` লেখা হয়েছিল। `core/cache/__init__.py` singleton-টিকে submodule-এর নিজ নামে re-export করে, ফলে CI-র import sequence-এ import টি **shadowed package attribute** resolve করে — test-এর module-attr monkeypatch সম্পূর্ণ বাইপাস হয়ে গিয়ে REAL singleton-এ পৌঁছায়। প্রমাণ: CI log-এ `⚡ Serverless Upstash Redis REST Provider Active` পুরো run-এ ঠিক ১ বার, সেটাও *টেস্টের ভেতরেই* — fake-এর `eval_calls == 0`।
- **Fix:** `backend/core/middleware/security.py`-এ sys.modules-first resolution (`_get_redis_manager()`) — call-time-এ সবসময় আসল module object-এর (patch-করা) attribute দেয়; production-এ দুই পথই একই singleton, behavior identical। PR #2110।
- **লেসন:** (১) `package/__init__`-এ same-name re-export থাকলে function-level `from package.module import name` **patch-proof নয়** — test যা monkeypatch করে সেটি বাইপাস হতে পারে; (২) monkeypatch-target dependency call-site-এ `sys.modules` lookup বা `import package.module as m; m.name` আকারে resolve করো; (৩) "dependency-র init log ঠিক টেস্টের ভেতরে ১ বার" মানেই real dependency টেস্ট চলাকালীন initialize হয়েছে — patch bypass-এর smoking gun।
