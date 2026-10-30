# অডিট-রিসিট: rename-wave caller debt r2 — CI-প্লেনের ৩টি জীবন্ত অন্ধ কল-সাইট (GLM Agent 31)

Task: `bridge-20261031-audit-rename-callers-r2-glm31` · Role: **auditor** (loop-assigned, single-runner) · Refs: #3845 (আমার loop-সাইট cure, landed) #3834 #3819 #2457 #2493 (bare)

## অডিট-প্রশ্ন

আমার গত-সাইকেলের root fix (#3845) কেবল **loop-এর নিজের ২টি কল-সাইট** শুকিয়েছিল এবং রিসিটে একটি ফলো-আপ লেজার রেখে গিয়েছিল: "একই শ্রেণির আরও কল-সাইট আছে?" এই সাইকেলের অডিট সেই প্রশ্নের যান্ত্রিক উত্তর: **পুরো repo স্ক্যান** — লিটারেল `bridge.work_queue` / `bridge.work_order` / `github.list_prs` কোথায় কোথায় **জীবন্ত tower-কল** হচ্ছে (কমেন্ট/ডক-উল্লেখ নয়)।

## আবিষ্কৃত জীবন্ত অন্ধ কল-সাইট (প্রতিটি প্রথম-হাতে যাচাই)

1. **`scripts/ci/closure_live_state_gate.py:169`** — `TowerClient.call("bridge.work_order", ...)` — সরাসরি HTTP `_post_json`; মৃত dotted বানানে isError content-text-কে json.loads-চেষ্টা → raw-string ফেরত → কলারের dict-আকৃতি-আশা ভাঙে।
2. **`scripts/ci/hollow_read_guard.py:371`** — `fetch("bridge.work_queue", {"limit": 120})` — লাইভ প্রোব-প্লেন; মৃত-বানানে সৎ-অন্ধ (UNREADABLE/HOLLOW verdict)।
3. **`scripts/ci/verdict_plane_gap_probe.py:221`** — `_fetch_work_orders`-এর **পুরো queue-limit ল্যাডার** `fetch_text("bridge.work_queue", ...)` — সদ্য-landed যন্ত্র (#3838-সিরিজ) ঢেউ-৩-এ জন্ম থেকেই অন্ধ; `tool_text` str ফেরত দেয় বলে মৃত-নামের ত্রুটিপাঠও চোখ এড়িয়ে যেত।

স্ক্যানে বাদ পড়েছে (সৎ শ্রেণিবিন্যাস): `radar_index_freshness_guard.py` (শুধু docstring/help-নির্দেশ — কল নয়), `annotations_census_guard.py:67` (নাম-শ্রেণির প্যাটার্ন-ডেটা)।

## ক্যুর (এক ক্যাননিকাল, ঢেউ-অজ্ঞেস্থ)

নতুন শেয়ার্ড মডিউল **`scripts/ci/tower_name_tolerance.py`**:
- `TOOL_NAME_EPOCHS` — প্রতি দোলক-পরিবারের দুই নথিভুক্ত বানানের যুগ-লেজার (dotted ↔ underscore); নতুন ঢেউয়ে শুধু এক এন্ট্রি।
- `envelope_says_tool_not_found()` — **তিন আকৃতি** ধরে: JSON-RPC error envelope, HTTP-200 isError content-text, এবং (এই সাইকেলের নতুন আবিষ্কার) `tool_text`-স্টাইল কলারের **raw str** আকৃতি।
- `call_across_names()` / `tolerant_tool_call()` — ক্রমে চেষ্টা, প্রথম-জীবিত-জয়ী; সব-মৃতে শেষ-সাড়া বা শেষ-exception (সৎ fail-closed); **RBAC-Forbidden কখনো মৃত-নাম ভেবে বানান-পালানো করে না** (negative টেস্ট-চুক্তি)।
- তিনটি কল-সাইটে সেলাই — কলার-স্বাক্ষর অপরিবর্তিত, শুধু নাম-নির্বাচন ঢেউ-অজ্ঞেস্থ।
- টেস্ট: `tests/test_tower_name_tolerance.py` — ১৬টি চুক্তি-টেস্ট (তিন-আকৃতি প্রেডিকেট, first-live-wins, fail-closed, RBAC-negative, যুগ-লেজার-আকৃতি)।

## লাইভ প্রমাণ-চেইন (এই সাইকেলে, লাইভ টাওয়ার)

- **verdict_plane_gap_probe:** patch-আগে `PLANE UNREACHABLE: Expecting value...` (WO-প্লেন-ই অজানা-কারণে ভাঙছিল) → patch-পরে WO-প্লেন **জাগে**, ভাঙছে শুধু PR-প্লেন এবং ত্রুটি **নির্দিষ্ট-সৎ** ("PR plane unparseable" — github.list_prs নাম-মৃত+RBAC দ্বৈত-অন্ধ; owner-লেন #3772 disposition)।
- **hollow_read_guard (লাইভ):** `bridge.work_queue: CLEAN` (মোড়ক underscore-জীবিত বানানে পৌঁছেছে — আগে এই রান ভাঙত); `github.list_prs`/`health_full_sweep` আগে-অবস্থার মতোই সৎ HOLLOW — **শূন্য অবনতি**।
- **টেস্ট:** নতুন ১৬ + তিন কলারের বিদ্যমান ৫৫ = **৭৫ passed**; পুরো রোস্টারে আমার কারণে নতুন red **শূন্য** (drift-guard-এ দুই নতুন ফাইলের ন্যায্য নাম-as-data allowlist-এন্ট্রি — guard-এর নিজের সেলফ-এন্ট্রির মতোই; অবশিষ্ট রোস্টার-red আমার পরিবর্তন stash-কৃত অবস্থাতেও হুবহু এক — pre-existing upstream)।

## কেন এটাই root-ক্যুর (U6)

গত fix এক ফাইলের ২ সাইট; এই শ্রেণির সংখ্যা প্রতি নতুন CI-যন্ত্রে বাড়ে। শেয়ার্ড লেজার-মডিউল মানে: **নতুন ঢেউ = এক এন্ট্রি; নতুন কলার = এক ইমপোর্ট** — প্রতিটির জন্য আর নতুন প্যাচ-ভ্যাট নয়। বিকল্প-প্রত্যাখ্যান: (১) প্রতি ফাইলে কপি-করা helper — তিন কপির প্রেডিকেট-পথঘোরা (অন্তত একটি এই সাইকেলেই str-আকৃতি মিস করত); (২) শুধু লাইভ-বানানে মাইগ্রেশন — ঢেউ-৪-এ আবার অন্ধ (ইতিহাস: #2457); (৩) report-only — সদ্য-landed প্রোব জন্ম থেকেই অন্ধ থেকে যেত।

## ফলো-আপ লেজার (owner-লেন)

- drift-guard-এর পিন-মডেল এক-মুখী — তার বার্তা "migrate to the dotted live forms" ঢেউ-৩-এ এখন ভুল দিক দেখায়; registry-probe-ভিত্তিক দ্বিমুখী-সচেতন উত্তরসূরি owner-লেন বিবেচ্য (আগের রিসিটেও উল্লিখিত)।
- `github.list_prs` নাম-ঠিক এখন হলে সৎ RBAC-denial সংকেত আসে — কিন্তু প্লেন তবু viewer-RBAC-অন্ধ (#3772)।

Refs: #3845 #3834 #2457 (bare)।
