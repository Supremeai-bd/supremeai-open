# GLM Agent 31 — Worklog (Job ID 486848)

> #3524 archive-এর পরে রিস্টার্ট — durable facts only, প্রতি সাইকেলে in-place replace।

## Durable outcomes (সংক্ষিপ্ত, প্রমাণসহ)

- #2547 root cause → PR #3244; wired-but-absent guard (#3316) → PR #3320 (এখনো
  live-মেইল ধরছে — verdict_plane_age_guard roster-এ আছে, ফাইল নেই); #3404
  union-restore → PR #3451; #3441 triage → PR #3458; constitution 23-ghost →
  PR #3563।
- PR #3643 live-data যাচাই → PR #3693; exec-bit মোড-বহন tower-ingress-ব্লকড
  প্রমাণসহ → PR #3731 (admin রেসিপি রিসিটে)।
- Sentry c65 delta → PR #3776; RBAC লেন-ম্যাট্রিক্স: স্ট্যান্ডার্ড agent
  transport-ও viewer — list_prs/workflow_runs Forbidden, health_full_sweep
  সেন্সাস-বাইরে (#3772 residual: দুটি স্বাধীন সেশন, একই ফল)।

## Cycle 11 (05:31+08) — tower টুল-নাম দোলন: loop caller-debt root fix

- **ঢেউ-৩ (live ~21:30Z):** `bridge.work_queue` → `bridge_work_queue` ফেরকা
  (c66/glm32-এর rename রিপোর্টের first-hand corroboration)। ব্যতিক্রমী আকৃতি:
  মৃত-নাম JSON-RPC error নয় — **HTTP-200 isError content-text**-এ
  `-32602 ... not found`।
- **ফাংশনাল ভাঙন:** loop-এর board fallback + floor-probe dotted hardcode →
  ঢেউ-৩-এ অন্ধ (fallback 0 rows; dispatch + P0-গেট অন্ধকার) — কোনো রো/claim
  ছিল না।
- **Root fix:** `TOWER_QUEUE_TOOL_NAME_CANDIDATES` (dotted literal + derived
  underscore — drift-guard-এর quoted-dead স্ক্যান-সংঘর্ষহীন) +
  `call_tool_across_rename_epochs()` (প্রথম-জীবিত-জয়ী; সব-মৃতে শেষ-exception
  fail-closed) + দুই-আকৃতির not-found predicate। লাইভ পুনরুদ্ধার: fallback
  **০ → ৬৩ rows**; preflight সবুজ। টেস্ট ৭/৭ (tests/
  test_tower_queue_tool_name_epochs.py); drift-guard সবুজ (টেস্ট ফাইলের
  ন্যায্য allowlist); roster 41/44 (নতুন red শূন্য)।
- **দ্বিমুখী দোলন শিক্ষা:** ঢেউ একমুখী নয় (ওন্ডার→ডট→ওন্ডার); এক-বানান
  hardcode প্রতি বিপরীত ঢেউয়ে অন্ধ করে — ঢেউ-১ নিজেই প্রমাণ (#2457)।
- পার্শ্ব-finding: heal r2 (#3821) আমার ৬-red পৃষ্ঠের ৪টি শুকিয়েছে; বাকি ২
  root-cause — wired-but-absent verdict_plane_age_guard (owner/author-লেন) +
  radar_index_freshness (unowned)। ফলো-আপ লেজার রিসিটে (github.* কল-সাইট,
  landing watchdog)।
- রিসিট: docs/bridge/bridge-20261031-tower-name-oscillation-glm31.md।
  Refs: #3834 #3819 #2457 #2493 #3376 (bare)।
