# ARCH-LIVING-PIPELINE-01 — বাস্তবায়ন রোডম্যাপ (Implementation Plan)

> **ডকুমেন্ট আইডি:** ARCH-LIVING-PIPELINE-01-IMPL
> **তারিখ:** ২০২৬-০৯-২৮ · **লেন:** coder-1 (agent-3) · **স্ট্যাটাস:** প্রস্তুত (credential restore হলে সঙ্গে সঙ্গে PR-able)
> **বেস:** main @ 9710b76 ("fix(observability): instrument 63 silent exception swallows (#1743) (#2175)")
> **পদ্ধতি:** প্রমাণভিত্তিক reality-check → gap register → ফেজড অ্যাটমিক PR পরিকল্পনা

---

## ০. বাস্তবতা-যাচাই (Reality Check — file:line evidence সহ)

মূল স্পেকের ৬টি স্তরের প্রতিটির রিপো-বাস্তবতা (main @ 9710b76-এ সরাসরি যাচাইকৃত):

| স্তর | স্পেকের দাবি | রিপো বাস্তবতা | রায় |
|---|---|---|---|
| **১. Slot Lease** | `acquire_role_slot.py`, ব্রাঞ্চ-as-lease | `scripts/agents/acquire_role_slot.py` — **৫১২ LOC, বিদ্যমান**; AGENTS.md:17 স্লট/ব্রাঞ্চ নামকরণ `<lane>-<N>-<issue#>-<slug>` নিশ্চিত | ✅ চালু |
| **২. Atomic Claim** | `atomic_claim.sh` + "Touching files:" | `scripts/ci/atomic_claim.sh` — **৩৬৭ LOC, বিদ্যমান**; AGENTS.md:20-এ "Touching files" ঘোষণা বাধ্যতামূলক | ✅ চালু |
| **৩. ৩-স্তর ভেরিফিকেশন** | reflection → boot smoke → pytest | AGENTS.md + ডকসে প্রটোকল-ফর্মে বর্তমান; প্রতি রাউন্ডে মানতে দেখা যাচ্ছে | ✅ চালু |
| **৪. ডুয়াল-স্টেট গেম** | State A/B অটো-ট্রানজিশন, Rule of 3 | `LIVING_PROMPT_SIMPLIFICATION_PLAN.md:88-89,126`-এ প্রটোকল আছে; Rule-of-3-এর **৩০-মিনিট ইঞ্জিন-ফলব্যাক** অপারেশনাল নোট দুর্বল | ⚠️ আংশিক |
| **৫. মার্জ ট্রেন** | seq ascending + contiguous rollup + ব্যাচ ল্যান্ডিং | **দুই-স্তর বাস্তবায়ন আছে:** (ক) `scripts/ci/issue_queue_manager.py` = GSPQ — contiguous seq claiming, ডাউনস্ট্রিম +1 shift, **cascade hold**; (খ) `scripts/ci/merge_train_rollup.py` = collision-gated ব্যাচ রোলআপ + CI-ব্যর্থতায় **অটো-বাইসেক্ট** (#1711) | ✅ চালু |
| **৬. জানিটর** | ৫-স্তর পরিষ্কারণ | `scripts/ci/group_closeout_janitor.py` — **২০৬ LOC, dry-run-by-default + logging সহ**; OPS-09 মাস্টার ডক বিদ্যমান | ✅ চালু |
| **সংবিধান-গেট** | (স্পেকের গেট-স্তর) | `.github/constitution/rules.yml`-এ **৭টি গেট সংজ্ঞায়িত**: lease_gate ✅wired, verification_gate ✅wired, scope_gate ✅wired, collision_gate ✅wired(strict #2002); **self_merge_gate ❌wired=false**, **test_guard_gate ❌wired=false**, **post_merge_watch ❌wired=false** — তিনটিই "follow-up issue" হিসেবে নিজেই নথিভুক্ত | ⚠️ ৪/৭ wired |

### হ্যান্ডঅফ রিটায়ারমেন্ট টেবিলের বাস্তবতা:

| কম্পোনেন্ট | স্পেক দাবি | রিপো বাস্তবতা (৯৭১০b৭৬) |
|---|---|---|
| `backend/core/orchestration/handoff_schema.py` | ১৮৯ লাইন → রিটায়ার | **ইতিমধ্যেই মুছে গেছে** ✅ |
| `backend/models/handoff_event.py` | ২৮ লাইন → রিটায়ার | **ইতিমধ্যেই মুছে গেছে** ✅ |
| `master_cognitive_orchestrator.py` | ১৯ লাইন → রিটায়ার | **এখনো জীবিত** — ১৯-লাইনের compat bridge (`cognitive_pipeline_dispatcher.py`-এর ৩১৫-LOC প্রকৃত বডি থেকে re-export); **২টি জীবন্ত কনজিউমার:** `tools/master_orchestrator.py:31`, `backend/tests/orchestration/test_master_cognitive_orchestrator.py:6`; সহ `tools/knowledge/card_builder.py`-এ metadata path রেফারেন্স |
| In-Memory Rollback Pipeline | ~৩০০ লাইন → `queue:hold` প্রটোকল | merge_train_rollup-এর collision-gate + auto-bisect এটিকে কার্যত প্রতিস্থাপন করেছে |

**সিদ্ধান্ত (verdict):** স্পেকটি ~৮৫% ক্ষেত্রে **ইতিমধ্যে-চলমান সিস্টেমের canonization** — এটা এর শক্তি। নতুন কোড লেখার ভার নয়; বাকি ১৫% হলো নিচের ৬টি গ্যাপ।

---

## ১. গ্যাপ রেজিস্টার (Gap Register)

| # | গ্যাপ | প্রমাণ | ঝুঁকি যদি না করা হয় |
|---|---|---|---|
| **G1** | স্পেক ডকুমেন্ট নিজেই রিপোতে নেই; AGENTS.md-এ তার রেফারেন্স নেই ("living prompt" = AGENTS.md-এ inject না হলে এজেন্টরা পড়বেই না) | `docs/architecture/`-এ ARCH-LIVING-PIPELINE-01 অনুপস্থিত | প্রটোকল = কাগজ; এজেন্ট-আচরণে বাঁধন নেই |
| **G2** | `master_cognitive_orchestrator.py` ব্রিজ এখনো জীবিত, ২ কনজিউমার সহ | উপরের টেবিল | ডেড-কোড দ্বৈত import-পথ, ভবিষ্যৎ বিভ্রান্তি |
| **G3** | `handoff:coder` / `handoff:planner` লেবেল-প্রটোকল অ্যাডপশন যাচাই করা হয়নি (API credential ছাড়া লেবেল দেখা যায়নি) | retirement টেবিলের প্রতিশ্রুতি | হ্যান্ডঅফ কোড গেছে কিন্তু লেবেল-প্রটোকল আদৌ ব্যবহৃত হচ্ছে কি না অনিশ্চিত |
| **G4** | `MERGE_TRAIN_AUTO_LAND` নামটি রিপোর কোথাও নেই — কে/কীভাবে ল্যান্ড করাবে অসংজ্ঞায়িত | grep: শূন্য ম্যাচ | ট্রেন "কে চালাবে" দ্ব্যর্থতা; নিজে-নিজে মার্জের ঝুঁকি |
| **G5** | Rule-of-3-এর ৩০-মিনিট ফলব্যাক ট্রিগার কোনো role-doc/স্ক্রিপ্টে অপারেশনাল নয় | `docs/agents/roles/pr-helper.md`-এ কোটা টেবিল নেই | PR রিভিউ-বঞ্চিত থেকে যেতে পারে |
| **G6** | সুফল-ম্যাট্রিক্সের দাবিগুলো (৭,০৮০+ লাইন ছাঁটাই ইত্যাদি) অপেক্ষিত — পরিমাপযোগ্য কাউন্টার নেই | জানিটর রিপোর্টে মেট্রিক্স নেই | "১০১% নীতি" অযাচাইকৃত থেকে যাবে |
| **G7** | সংবিধানের নিজস্ব ৩টি গেট unwired: `self_merge_gate`, `test_guard_gate`, `post_merge_watch` | rules.yml `gates:` সেকশনে wired=false + "follow-up issue" নোট | সেলফ-মার্জ, টেস্ট-ম্যানিপুলেশন, লাল-main-এর প্রটোকল-বাধা শুধু লিখিত, প্রয়োগহীন |

---

## ২. ফেজড বাস্তবায়ন পরিকল্পনা (প্রতিটি ফেজ = অ্যাটমিক ১-ইস্যু-১-ব্রাঞ্চ-১-PR)

> প্রতিটি PR নিজেই এই পাইপলাইন দিয়েই যাবে (dogfooding): `acquire_role_slot.py` → `atomic_claim.sh` + "Touching files:" → ৩-স্তর ভেরিফিকেশন → PR + `queue:hold` + `has-pr` → ডুয়াল-স্টেট রিভিউ → ট্রেন। **কখনোই সেলফ-মার্জ নয়।**

### **Phase 0 — Canonization** (docs-only, শূন্য কোড-ঝুঁকি) → `PR-α`
- `docs/architecture/ARCH-LIVING-PIPELINE-01.md` হিসেবে স্পেক কমিট (রিলেটিভ লিংকগুলো ইতিমধ্যেই `docs/architecture/` অবস্থান-সাপেক্ষে সঠিক: `./LIVING_PROMPT_SIMPLIFICATION_PLAN.md` ✓, `../master_docs/OPS-09-...` ✓, `../../AGENTS.md` ✓)
- `AGENTS.md`-এ ১-লাইনের রেফারেন্স যোগ (living-prompt injection point)
- `LIVING_PROMPT_SIMPLIFICATION_PLAN.md`-এর রেফারেন্স-হেডারে cross-link
- **ভেরিফিকেশন:** লিংক-চেক + md রেন্ডার; ৩-স্তর ট্রিভিয়াল
- **ইস্যু-লেবেল:** `docs`, `queue:hold`

### **Phase 1 — ব্রিজ রিটায়ারমেন্ট** (ছোট কোড, collision-checked) → `PR-β`
- `tools/master_orchestrator.py:31` + `backend/tests/orchestration/test_master_cognitive_orchestrator.py:6` → সরাসরি `core.orchestration.cognitive_pipeline_dispatcher` থেকে import
- `master_cognitive_orchestrator.py` (১৯ লাইন) ডিলিট
- `tools/knowledge/card_builder.py`-এর metadata path-string হালনাগাদ
- **৩-স্তর গেট:** (১) `grep -rn "master_cognitive_orchestrator"` → import-target হিসেবে শূন্য রেফ (metadata string ছাড়া); (২) `python -c "import main"` বুট-স্মোক; (৩) `pytest backend/tests/orchestration/ -q` ১০০% সবুজ
- **সতর্কতা:** card_builder-এর রেফগুলো ডেটা-স্ট্রিং — ভাঙবে না, তবে নির্ভুলতার জন্য হালনাগাদ

### **Phase 2 — গভর্নেন্স গেট** (প্রটোকল-সম্পূর্ণকরণ) → `PR-γ`, `PR-δ`
- **PR-γ (G4+G7-ক):** `MERGE_TRAIN_AUTO_LAND` রানবুক + `post_merge_watch` ওয়্যারিং — merge-train land job-এ merge-পরবর্তী ১৫-মিনিট main-লাল হলে auto-revert চেক; সংজ্ঞা: admin-gated `workflow_dispatch` **অথবা** ডকুমেন্টেড ম্যানুয়াল পদ্ধতি; "ঘুড়ি উড়ুক আকাশে, নাটাই অ্যাডমিনের হাতে" — ইঞ্জিন প্রস্তাব করবে, অ্যাডমিন ল্যান্ড করবে
- **PR-δ (G5+G7-খ):** `docs/agents/roles/pr-helper.md`-এ Rule-of-3 কোটা টেবিল + ৩০-মিনিট ইঞ্জিন-ফলব্যাক অপারেশনাল সংজ্ঞা + `self_merge_gate`/`test_guard_gate`-এর follow-up ইস্যু ফাইল ও স্কোপ-ড্রাফট (wiring-এর জন্য constitution audit engine extension)

> **গুরুত্বপূর্ণ আবিষ্কার (Phase-0-কে প্রভাবিত করে):** AGENTS.md একটি **GENERATED FILE** (`<!-- DO NOT EDIT BY HAND -->`, generator: `scripts/ci/generate_agents_md.py`, CI drift-check: `system-gates.yml → agents-md-sync`)। তাই স্পেক-রেফারেন্স AGENTS.md-তে যোগ করতে হলে পথ হলো: `.github/constitution/rules.yml` (যেমন `bootstrap` বা `living_protocols` সেকশন) সম্পাদনা → generator দিয়ে regen → `--check` পাস। হাতে AGENTS.md এডিট করলে CI drift-gate BLOCK করবে।

### **Phase 3 — পরিমাপযোগ্যতা ও লেবেল-মাইগ্রেশন** → `PR-ε`, `PR-ζ`
- **PR-ε (G6):** `group_closeout_janitor.py`-এর ক্লোজআউট রিপোর্টে কাউন্টার: মার্জ-হওয়া PR, ছাঁটাই লাইন, বাইসেক্ট-কাউন্ট, ডিটেক্টেড কনফ্লিক্ট (dry-run-safe ছোট পরিবর্তন)
- **PR-ζ (G3):** `handoff:coder`/`handoff:planner` লেবেল তৈরি + AGENTS.md-এ লেবেল-ভিত্তিক হ্যান্ডঅফ প্রটোকল নোট (ক্রেডেনশিয়াল ফিরলে প্রথমে বর্তমান লেবেল-সেট যাচাই)

---

## ৩. ক্রম ও প্যারালালিজম

```
P0 (PR-α) ──→ P1 (PR-β) ──→ P2 (PR-γ ∥ PR-δ) ──→ P3 (PR-ε ∥ PR-ζ)
 canonizer      কোড-রিটায়ার     গভর্নেন্স             মেট্রিক্স+লেবেল
```
- PR-α আগে: স্পেক ক্যানন হওয়া চাই, তারপর বাকি সব স্পেক-সাপেক্ষ
- PR-β স্বাধীন, তবে graph-carrying নয় (মাত্র ১ ফাইল ডিলিট + import re-point) → যেকোনো ট্রেনে ধরা যাবে
- PR-γ/δ/ε/ζ পারস্পরিক ফাইল-সেট বিচ্ছিন্ন → সমান্তরাল ক্লেইমযোগ্য

## ৪. রিস্ক রেজিস্টার

| ঝুঁকি | প্রশমন |
|---|---|
| ডক-বনাম-কোড দ্ব্যর্থতা (যেমন seq বনাম collision-batch) | doc-first: আচরণ পরিবর্তন নয়, আচরণ-বর্ণনা নির্ভুলীকরণ; GSPQ+train-এর দুই-স্তর বাস্তবতাই স্পেকের চেয়ে শক্তিশালী |
| ব্রিজ ডিলিটে ভাঙা import | ৩-স্তর গেট + reflection grep বাধ্যতমান; collision radar-এ "Touching files" ঘোষণা |
| সেলফ-মার্জ/অন্ধ অটোমেশন | `queue:hold` অপরিবর্তিত; MERGE_TRAIN_AUTO_LAND সর্বদা admin-gated |
| জানিটরের ধ্বংসাত্মক অপ | dry-run-default অটুট রাখা + অডিট-লগ |
| স্যান্ডবক্স-রিসেটে ক্রেডেনশিয়াল ক্ষতি (আজ ২ বার ঘটেছে) | সব আর্টিফ্যাক্ট `/home/z/my-project/handoff/`-এ persistent; push এক-কমান্ড-দূরত্বে প্রস্তুত |

## ৫. সফলতার মেট্রিক্স (যাচাইযোগ্য সংজ্ঞা)

1. PR-α মার্জ = স্পেক ক্যাননাইজড, AGENTS.md-লিংকড → "living" শব্দটি অর্থবহ
2. PR-β মার্জ = হ্যান্ডঅফ-রিটায়ারমেন্ট টেবিল **১০০% সত্য** (শূন্য জীবিত ব্রিজ)
3. PR-γ/δ = ট্রেন-ল্যান্ডিং ও রিভিউ-কোটার শূন্য দ্ব্যর্থতা
4. PR-ε = প্রতি গ্রুপ-ক্লোজআউটে পরিমাপকৃত সুফল-ম্যাট্রিক্স
5. সামগ্রিক: একই পাইপলাইন দিয়ে এই পরিকল্পনার প্রতিটি PR যাওয়াই প্রমাণ

---
*প্রস্তুতকারী: coder-1 (agent-3), প্রমাণ-ভিত্তি: main @ 9710b76 সরাসরি ফাইল-যাচাই*
