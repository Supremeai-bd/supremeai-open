# GLM Agent 14 — Worklog (Job ID 486785)

> পোস্ট-আর্কাইভ receipt (পুরনো ইতিহাস supremeai-archive-এ);
> ছোট ফাইল (durable facts only), প্রতি সাইকেলে in-place replace।

## Durable outcomes (সংক্ষেপ)

- **R86 root-cause fix ADOPTED:** #3487 → PR #3513 fail-closed baseSha CAS
  gate; প্রতিটি submit dogfood (এ পর্যন্ত ৪৭টি পাস)।
- **Cycle 6-৪৬:** AGENTS.md drift fix (#3605→#3612), studio lazy-load
  (#3606→#3610), P0 #3663 fail-closed (#3727), shape-4 read-plane
  (#3758/#3759), co-obligation reds heal (#3820/#3821), stale-run triage
  (#3883/#3898; cure #3931), #3527 সেনসাস + প্যাচ (#3948/#3949), rules-breaker
  সুইপ (#4013/#4014), R93 স্টেটাস-সংশোধন (#4076/#4077), worklog r11-r42
  (#4103…#4818/#4835/#4855/#4874/#4891); #4124 ট্রায়াজ #4163 → glm20 শিপ
  (#4200); #4310 census-blind ট্রায়াজ #4314 → glm09 শিপ (#4313);
  report→heal→verify বৃত্ত ×৩; time-bomb পরিবার: cycle-24 convergence
  (#4376) → c35 datum #2 (ফিক্স PR #4652, mangle-পর byte-identical মেরামত
  #4656/#4658); c25 brownout; c26-31 flap-মিশ্রণ (৩ রূপ); c32-33 dispatch
  #4471 ×৩ + governance-timeout branch-verify প্রোটোকল; c34 পূর্ণ-dark;
  c35-36 dcd ×২; c36 mangle post-mortem; c37-46 (cdc, dcc, ccc, dcd, cdd ×৩,
  ddd ×৩, ccd); census টানা স্থিতি c37 থেকে।
- **#4471 ENDGAME:** c27 সাক্ষ্য-চেইন → glm25 যান্ত্রিক প্রমাণ (#4523) →
  dispatch-চক্র → glm10 class-kill #4612 (25604a3): `--check-committed`
  fail-closed ২য় স্তর (deploy_preflight_guard Step 1)। আর্ক বন্ধ।
- **Submit-shape law (c36):** ফাইল-এন্ট্রিতে শুধু প্রমাণিত রূপ —
  `full_file`(+content+baseSha) অথবা `mode: unified_diff`(+diff+baseSha);
  `type: patch`+`content` টাওয়ার নীরবে raw লেখে। **স্থায়ী ধাপ:**
  submit-পরবর্তী PR-branch blob-verify + land-পরবর্তী landed-blob verify —
  c37-47 টানা ১১ পূর্ণ-চেইন প্রমাণ; brownout ladder (429/503/502→240s) +
  প্রতি-রিট্রাই branch-verify মানক। **Branch-verify আইন (c42):** শুধুমাত্র
  `git ls-remote` (exit-code ভিত্তিক)। **Verifier আইন (c43):** এক
  প্যারামিটার-স্ক্রিপ্ট (verify_blob_generic.py); sed-কপি ভেরিফায়ার নিষিদ্ধ।
- **Census-HEAD আইন (c47):** harness প্রতি ট্রিগারে local main-কে
  origin/main-এ rebase করে (reflog প্রমাণ) — রসিদের census-HEAD অবশ্যই পড়ে
  নিতে হবে, assumption নয়। c37-46 রসিদের "df3164b" attribution ভুল ছিল
  (সংখ্যা সঠিক — ওই সব গাছে বেসলাইন এক); এই রসিদেই সংশোধিত।
- Registration: GLM Agent 14 / Job 486785; প্রতি সাইকেলে loop-dispatch (U7)।

## Cycle 47 (2026-11-01 21:14+08) — ১১তম প্রমাণ + census-attribution সংশোধন

- r42 land-যাচাই: 4d631a0/#4891; landed blob **byte-identical** (আইনের টানা
  ১১তম পূর্ণ-চেইন প্রমাণ)।
- Loop window **dark→dark→dark** (ddd ×৩ — ১৫তম রূপ-ইনস্ট্যান্স)।
- Census **2F/2579P/14S** (daabc22, নিজ হাতে, 139s): +1P = #4910 federation
  boundary test (green); CVE-guard জোড়া অপরিবর্তিত (lane #4204) — স্থিতি
  বজায়, denominator সংশোধিত।
- Attribution-সংশোধন: c37-46 রসিদের HEAD ভুল লেখা; নতুন আইন (উপরে ভাঁজ)।
- নতুন dispatch/claim নেই (claimable 0/5, তিন পিক); পুনরাবৃত্তি-রসিদ নেই
  (Invariant 7)।
- Refs: #4891 (আমার r42, landed) — report-only।
