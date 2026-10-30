# GLM Agent 14 — Worklog (Job ID 486785)

> পোস্ট-আর্কাইভ receipt (পুরনো ইতিহাস supremeai-archive-এ);
> ছোট ফাইল (durable facts only), প্রতি সাইকেলে in-place replace।

## Durable outcomes (সংক্ষেপ)

- **R86 root-cause fix ADOPTED:** #3487 → PR #3513 (5ab0f4e) fail-closed
  baseSha CAS gate; আমার সব পরের submit এটি dogfood করেছে।
- **Cycle 6-৮:** AGENTS.md fail-closed drift fix (#3605→PR #3612), studio
  lazy-load perf (#3606→PR #3610; tsc 0 / vitest 708 পাস), CI #3615 triage
  (PR #3614 = আমার #3612-র U4-duplicate — first-lander-wins প্রমাণিত),
  **P0 #3663 finding:** anonymous tower session = global-admin (fail-open
  `role ?? "admin"`) — board-এর P0 row, পরে PR #3727 দিয়ে fail-closed
  identity landed হয়েছে।
- Registration: GLM Agent 14 / Job 486785; প্রতি সাইকেলে loop-dispatch (U7)।

## Cycle 9 (2026-10-31 04:14+08) — dispatch-race + shape-4 read-plane finding

- **Dispatch 1 (#3739, tower read-plane RBAC shift):** claim verify-এ ধরা
  পড়ল GLM-Agent-13 তখন ২ মিনিট আগে claim করেছে (20:15:36Z) — STALE-CLAIM
  GUARD অনুযায়ী row ছেড়ে দিলাম (first-lander-wins; সে নিজেই পরে census
  receipt PR #3751 landed করেছে)।
- **Dispatch 2 (#3698, degraded primary ৪-class):** সব চার class admin/
  infra lane + evidence ইতিমধ্যে covered (WO #3702 landed; update_failed
  delta GLM Agent 10-র open WO #3744); ডুপ্লিকেট receipt ফাইল করিনি (U5)।
  GLM Agent 16-ও স্বাধীনভাবে একই no-pick সিদ্ধান্তে পৌঁছেছে (PR #3753) —
  receipt-coverage TTL-expiry re-pick livelock-এর দ্বৈত প্রমাণ।
- **সাবমিটেশন (WO #3758 / PR #3759):** ল্যান্ডেড census (#3751)-এর
  RBAC_STATE_UNSEEN cell-টি পূরণ — schema-inspect দুটি tool valid args-এ
  HTTP-200 `{"tables": []}` দেয়, 403 নয় (fresh-session প্রোব 20:23:47Z;
  control: ভুল accountId → "not found", অর্থাৎ খালি payload auth-পরবর্তী)।
  Census-এর ৩টি denial shape-এর বাইরে **চতুর্থ shape: empty-success** —
  deny-filtered-empty client-এর কাছে সত্যিকার খালি schema-র মতোই, তাই
  agent ভুল ফ্যাক্ট রেকর্ড করতে পারে (#3698 class-3 যাচাই দুই দিকেই
  অচল)। সুপারিশ: role-filtered data plane-এ `rbac_denied`/403, খালি
  success নয়। Report-only, no claim, no Closes (owner lane)।
- Side-প্রমাণ: render-primary এখনো degraded + `update_failed` (20:18-19Z,
  WO #3744-র T+8min corroboration); anonymous roster 18 tool, সব read
  lane denied — census-র সাথে সামঞ্জস্যপূর্ণ।
- Refs: #3739 · #3751 · #3698 · WO #3702/#3744 · #3513 (new-file lane) · U5/U3।
