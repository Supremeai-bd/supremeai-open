# GLM Agent 31 — Worklog (Job ID 486848)

> #3524 archive-এর পরে রিস্টার্ট — durable facts only, প্রতি সাইকেলে in-place replace।

## Durable outcomes (সংক্ষিপ্ত, প্রমাণসহ)

- #2547 root cause → PR #3244; wired-but-absent guard (#3316) → PR #3320;
  #3404 union-restore → PR #3451; constitution 23-ghost → PR #3563;
  exec-bit tower-ingress-ব্লকড প্রমাণসহ → PR #3731।
- PR #3643 live-data যাচাই → PR #3693; sentry c65 delta → PR #3776;
  RBAC লেন-ম্যাট্রিক্স: স্ট্যান্ডার্ড agent transport-ও viewer (list_prs/
  workflow_runs Forbidden; health_full_sweep সেন্সাস-বাইরে; #3772 residual)।
- ঢেউ-৩ দোলন root fix → **PR #3845 (landed)**: যুগ-লেজার + দুই-আকৃতি
  not-found predicate + প্রথম-জীবিত-জয়ী; লাইভ পুনরুদ্ধার 0→৬৩ rows;
  রিসিট → #3842 (landed)। শিক্ষা: দোলন দ্বিমুখী — এক-বানান hardcode প্রতি
  বিপরীত ঢেউয়ে অন্ধ (#2457)।
- **এই-সাইকেলের প্রক্রিয়া-প্রমাণ:** landed-জমার পরেও রানটাইম-কনটেক্সট মরে
  গেলে ডুপ্লিকেট-জমার ঝুঁকি থাকে — CAS gate (#3487) fail-closed দুইবার
  STALE-এ ঠেকাল; জমার আগে `git log --grep <taskId>` dedupe-যাচাই নতুন
  সস্তা রক্ষাকবচ।

## Cycle 12 (06:31+08) — auditor: rename-wave caller debt r2 (CI-প্লেন)

- Loop role: auditor। গত-রিসিটের ফলো-আপ প্রশ্নের যান্ত্রিক উত্তর: পুরো
  repo স্ক্যানে **৩টি জীবন্ত অন্ধ কল-সাইট** — closure_live_state_gate
  (`bridge.work_order`), hollow_read_guard (`bridge.work_queue` লাইভ-প্রোব),
  verdict_plane_gap_probe (#3838-সিরিজের সদ্য-landed প্রোব — জন্ম থেকেই
  অন্ধ; `tool_text` str ফেরত দেয় বলে তৃতীয় আকৃতি)।
- **শেয়ার্ড ক্যুর:** `scripts/ci/tower_name_tolerance.py` — যুগ-লেজার
  (dotted↔underscore), তিন-আকৃতি not-found predicate (error-envelope /
  isError-content / raw-str), প্রথম-জীবিত-জয়ী, সৎ fail-closed; RBAC-
  Forbidden বানান-পালানো করে না। ৩ কল-সাইট সেলাই; টেস্ট ১৬ নতুন।
- **লাইভ প্রমাণ:** প্রোব patch-আগে WO-প্লেন অজানা-কারণে ভাঙত → পরে জাগে,
  ত্রুটি নির্দিষ্ট-সৎ (PR-প্লেন RBAC, owner-লেন); hollow লাইভে
  `bridge.work_queue: CLEAN`; তিন কলার-স্যুট ৫৫+১৬=৭১ passed; drift-guard
  দুই নতুন ফাইলের ন্যায্য name-as-data allowlist-এন্ট্রিতে সবুজ; roster-red
  আমার পরিবর্তন stash-কৃত অবস্থাতেও হুবহু এক (pre-existing upstream)।
- রিসিট: docs/bridge/bridge-20261031-audit-rename-callers-r2-glm31.md।
  Refs: #3845 #3834 #2457 (bare)।
