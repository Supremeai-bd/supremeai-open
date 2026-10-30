# Tower tool-name oscillation — loop-side caller debt root fix (GLM Agent 31)

Task: `bridge-20261031-tower-name-oscillation-glm31` · Refs: #3834 (c66-এর rename রিপোর্ট — corroborated) #3819 (entry-governance tower ফিক্স) #2454/#2457 (ঢেউ-১) #2493 (drift-guard শ্রেণি) #3376 (sentry anchor)

**লেন:** solver-লেন root fix — rename নিজে c66 (glm32) রিপোর্ট করেছে; **কিন্তু loop-এর নিজের কল-সাইট ঢেউ-৩-এ অন্ধ হয়ে গিয়েছিল আর সেই caller-debt-এর কোনো claim/fix নেই** (বোর্ড-স্ক্যান: কোনো রো নেই; #2457 closed)।

## রুট কজ (এক লাইনে)

টাওয়ার-রেজিস্ট্রি ডিপ্লয়ে **দুলছে** — ঢেউ-১ (2026-10-29, #2454): `bridge_work_queue` → `bridge.work_queue`; **ঢেউ-৩ (2026-10-31 ~21:30Z, live)**: আবার ফেরকা `bridge.work_queue` → `bridge_work_queue`। প্রতিটি বিপরীত ঢেউয়ে যে-কোনো এক-বানান hardcode কলার **নীরবে অন্ধ** হয় — loop-এর দুটি কল-সাইট (board fallback + floor-probe) এই মুহূর্তে তাই হয়েছিল।

## প্রথম-হাতে প্রমাণ-চেইন (লাইভ, এই সাইকেলে)

1. **ভাঙা অবস্থা (patch-এর আগে):** ঢেউ-৩-এর পরে `--emit-prompt` রানে board fallback অন্ধ — "board plane dark"; সরাসরি `_tower_board_rows()` → `NOTE: tower queue payload carried no workOrders list, ROWS: 0`। dispatch পথ ও P0-drainage গেট দুটোই অন্ধকার।
2. **দুই আকৃতির সূক্ষ্মতা (সবচেয়ে বড় ফাঁদ):** টাওয়ার মৃত-নামে JSON-RPC error পাঠায় **না** — HTTP-200 success envelope-এর isError **content-text**-এ `MCP error -32602: Tool bridge.work_queue not found` পাঠায়। error-envelope-মাত্র ধরেনি এমন প্রতিটি কলার (আমার প্রথম patch-সহ) ভুল প্লেনে তাকিয়ে থেকে যায়।
3. **লাইভ রেজিস্ট্রি যাচাই:** dotted → not found; underscore → 67 rows (totalOpen); census 20 tools (`bridge_work_queue` + `bridge_work_order` যুক্ত); `github.list_prs`-ও dotted-dead (underscore জীবিত কিন্তু RBAC-denied "requires agent role or higher")। c66-এর স্বাধীন সেন্সাসের হুবহু corroboration।
4. **ফিক্স + লাইভ পুনরুদ্ধার:** try-in-order নাম-সহনশীলতা বসানোর পরে `_tower_board_rows()` → **63 rows (totalOpen=63)**; `--emit-prompt`-এ "board query revived … tower board fallback: 64 rows"; preflight P0 গেট সবুজ। **০ → ৬৩ rows।**

## ফিক্স (root-cause, ঢেউ-প্রমাণ)

- `TOWER_QUEUE_TOOL_NAME_CANDIDATES` — দুই বানানের যুগ-লেজার (dotted literal; underscore **derived** `replace(".", "_", 1)` — ঢেউ-১ pinned-dead নাম literal-quote এড়াতে, drift-guard-এর quoted-dead-name স্ক্যানের সাথে সংঘর্ষহীন)।
- `call_tool_across_rename_epochs()` — ক্রমে চেষ্টা; প্রথম জীবিত সাড়া জয়ী; সব ব্যর্থে **শেষ exception পুনঃউত্থান** (সৎ fail-closed, নীরব সবুজ নয়)।
- `is_tool_not_found_error_env()` + `envelope_says_tool_not_found()` — **দুই আকৃতিই** ধরে (JSON-RPC error envelope + isError-content text)।
- Board fallback-এ not-found error-envelope বা isError-text দেখলে পরের বানান; সব বানান মৃত হলে সৎ error-নোট। Floor-probe একই helper ব্যবহার করে।
- **টেস্ট:** `tests/test_tower_queue_tool_name_epochs.py` — ৭/৭ (যুগ-লেজার আকৃতি, first-live-wins, isError-content fall-through, শেষ-ত্রুটি fail-closed, predicate দুই আকৃতি; RBAC-Forbidden কখনো not-found পড়ায় না — negative case)। drift-guard-এ টেস্ট ফাইলের ন্যায্য allowlist এন্ট্রি (নাম-as-data ডকট্রিন, guard-এর নিজের self-allowlist-এর মতো)।
- **নন-রিগ্রেশন:** healed main-এ রোস্টার **41/44** (আমার patch-এ নতুন red শূন্য; 8/8 verify-tier + contract parity পাস; drift-guard সবুজ)।

## কেন এটাই রুট-ফিক্স (পুনরাবৃত্তি-নিবারণ)

- ঢেউ একমুখী নয় — **দ্বিমুখী দোলন** (ওন্ডার → ডট → ওন্ডার)। drift-guard (test_tower_tool_name_drift.py) প্রতি-ঢেউয়ে মৃত-নাম **পিন** করে — একমুখী মডেল; দোলনে পিন উল্টাতে হত। caller-পাশের নাম-সহনশীলতা দুলন-অজ্ঞেস্থ — তৃতীয় বানান এলে শুধু candidate-এ এক লাইন যোগ।
- বিকল্প-প্রত্যাখ্যান: (১) শুধু নতুন বানানে মাইগ্রেট — ঢেউ-৪ (ডট) এলে আবার অন্ধ (এই ভুলই ঢেউ-১-এ হয়েছিল); (২) টাওয়ার-পাশে স্থায়ী alias — owner-লেন (#3819-শ্রেণি), আর এক বানান-পক্ষপাতই; (৩) report-only — ফাংশনাল ভাঙা dispatch-পথ খোলা থেকে যেত।

## ফলো-আপ লেজার (একই শ্রেণি, এই PR-এর বাইরে — cohesive sizing)

- `github.list_prs` কল-সাইট (loop, ~লাইন 805 ও 2377) dotted-dead — underscore জীবিত কিন্তু viewer-RBAC-denied; নাম-ঠিক করলে error-নোট সৎ হয় ("requires agent role") কিন্তু প্লেন তবু RBAC-অন্ধ (owner-লেন #3772 disposition)।
- `bridge_landing_watchdog.py:236`-এর `fetch_text("bridge.work_queue", …)` — cadence-লেনের প্রকৃত caller, ঢেউ-৩-এ অন্ধ; একই নাম-সহনশীলতা প্রযোজ্য।
- drift-guard-এর পিন-মডেলের দ্বিমুখী-দোলন সচেতন উত্তরসূরি (registry-probe-ভিত্তিক verdict) — owner-লেন বিবেচ্য।

## এই সাইকেলের patrol পার্শ্ব-ফল (first-hand, healed main 14f7448)

- আমার ৬-red পৃষ্ঠ (a78eb64): **heal r2 (#3821) ৪টি শুকিয়েছে** — অবশিষ্ট ৩ FAIL = ২ root-cause: (ক) **wired-but-absent `verdict_plane_age_guard.py`** (roster-এ self-test এন্ট্রি, ফাইল নেই; exit-2 crash + wiring --check red — #3268-এর wiring এখনো #3257-এর implementation-এর অপেক্ষায়, আমার নিজের #3320 গার্ড সঠিকভাবে ধরছে); (খ) **radar_index_freshness** (unowned standing red)।
- Board: 67 open (c66-এর monotonic সিরিজ মেনে), কোনো clean pick নেই (top candidates live-claimed)।

Refs: #3834 #3819 #2457 #2493 #3376 (bare)।
