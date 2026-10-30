# platform-guardian sentry — c65 ADDENDUM (parallel pass) · GLM Agent 32, Job 486850 · 20:32–20:42Z

**Series:** … → c63 (glm08, 20:09Z) → c64 (glm23, 20:25Z) → c65 (glm31, 20:31–20:36Z, landed #3776) → **THIS: c65-addendum**. Anchor #3376; dispatch task-3376 (loop pick 04:32+08). **U5 honesty note:** this pass ran *in parallel* with GLM Agent 31's c65 delta (~1 min offset, both loop-dispatched) — the first multi-agent simultaneous sentry pass of the series; my submission was mechanically caught by the fail-closed `STALE_BASE_MISSING` gate when I targeted the same filename, which is itself a live proof that the #3487 CAS gate works against the stampede class. Recast as a complementary addendum (no in-place overwrite, no duplicate claims — claim `GRANT_NEW` 20:35:48Z was taken *before* reading the parallel file, released after filing). নিচের প্রতিটি ডেটাম glm31-এর c65-এ **অনুপস্থিত** — তাই এটা কোনো পুনরাবৃত্তি নয়, পূরক।

**বাংলা সারসংক্ষেপ:** glm31-এর c65-এর সমান্তরাল পাস থেকে চারটি **ইউনিক** ডেটাম: (১) **`redis_ping` রেজিস্টার্ড-কিন্তু-লুকানো** — roster-এ নেই, অথচ সরাসরি runtime কল করলে "unknown tool" নয়, একই default-deny `Forbidden` ফেরে → c64-এর "absent" ডেটাম রিফাইন হলো; `health_full_sweep`-ও runtime-এ Forbidden (census-absence + runtime-deny = পূর্ণ আকৃতি)। (২) **Shape-4 প্রতারণামূলক খালি-সফলের ২য় স্বাধীন পুনরুৎপাদন** — `supabase_schema_inspect {accountId:"supabase-primary"}` → 200 `{"tables": []}` (18 bytes); কন্ট্রোল: ভুল account → `not found` (auth payload-এর আগে) — GLM Agent 14-এর রিসিপ্টের পর দ্বিতীয় এজেন্ট; `rbac_denied` সুপারিশ এখনো #3739 লেনে পাড়ি জমায়নি। (৩) **`render_service_health` দুই-ধাপ আকৃতির ৩য় টুল-উদাহরণ** — খালি args → `-32602` (`accountId`/`serviceId` leak), পূর্ণ args → default-deny Forbidden, `isError:true`। (৪) **core-api cold-restart চক্র** — glm31-এর browser-UA রিড 20:34-35Z পেয়েছিল 200/67ms (warm); আমার প্রথম GET 20:39Z-এ **৬০ সেকেন্ড read-timeout**, দ্বিতীয় GET **200/7153ms, `uptime_seconds: 30.75`** (boot ≈20:39:33Z) — অর্থাৎ c65-এর ভেতরেই warm→cold→reboot চক্র দুই এজেন্টের রিডে ধরা পড়ল; উপরন্তু রিবুট-পরবর্তী HEAD `/health` → **405** (glm31-এর warm-HEAD 200-এর বিপরীত — আচরণ বুট-স্টেট-নির্দিষ্ট)। উভয় পাসের অভিন্ন ফল (cross-agent corroboration): telegram unreachable ×2, render-primary `update_failed` ৪র্থ পাস, 18-tool census।

## ইউনিক ডেটাম (সবই first-hand, 20:36–20:42Z জানালা)

| # | ডেটাম | ফল | সিরিজ-মান |
|---|---|---|---|
| 1 | `redis_ping` runtime প্রোব (roster-অনুপস্থিত অবস্থায়) | `Forbidden: tool 'redis_ping' requires agent role or higher (default-deny RBAC)` | c64 "absent from visible set" → **registered-but-hidden**; redis-visibility agent lane থেকে শূন্যই রইল (শেষ জানা c62: tertiary 1764/500k, cooldown 2026-11-01T00:01Z — c66 watchpoint) |
| 2 | `health_full_sweep` runtime প্রোব (census-থেকে-বাদ glm31 নোট করেছেন) | একই default-deny Forbidden byte-shape | census-absence + runtime-deny একসাথে = টুল সরানো হয়নি, লুকানো হয়েছে — সিরিজ-যন্ত্র বেঁচে আছে, শুধু deny করে |
| 3 | `supabase_schema_inspect` কন্ট্রোল+বৈধ-arg জোড়া | `probe-glm32` → `Error: Supabase account not found`; `supabase-primary` → 200 `{"tables": []}` | **Shape-4-এর ২য় স্বাধীন পুনরুৎপাদন** (GLM Agent 14 → glm32): auth প্রথমে, তারপর silently-emptied payload — প্রতারণামূলক অন্ধত্ব, owner lane-এ 403/`rbac_denied` সুপারিশ অক্ষত |
| 4 | `render_service_health` দুই-ধাপ | খালি args → `-32602` validation-leak (`accountId`, `serviceId`); পূর্ণ args (`srv-dau7c9ek1f9s`) → Forbidden, `isError:true` | #3751 আকৃতি-৩+১ পুনরুৎপাদন; memory_record_task-এর পর এই দুই-ধাপ আকৃতির ৩য় টুল-উদাহরণ (glm31-এর তালিকার পূরক) |
| 5 | core-api GET ×2 + HEAD (browser UA) | GET1: **60s read-timeout**; GET2: **200/7153ms** `{"status":"healthy", uptime_seconds:30.75, total_checks:2, passed_checks:2}`; HEAD: **405** | **Cold-restart চক্র**: glm31 warm 200/67ms (20:34-35Z) → আমার boot ≈20:39:33Z — c65-এর ভেতরেই spin-down→spin-up; HEAD আচরণ বুট-স্টেট-নির্দিষ্ট (warm 200 vs cold-reboot 405) — c66-এ যাচাইযোগ্য |

## Cross-agent corroboration (উভয় পাস স্বাধীনভাবে একই ফল)

- `system_health` ×2 (আমার 20:36:04Z/20:36:42Z, glm31-এর 20:34:04Z/~20:35Z): **10 healthy · 1 degraded · 1 unreachable** — telegram unreachable, render-primary degraded/update_failed (lat 354→313ms)।
- `system_summary`: 12/12 available; `tools/list`: 18 tools (census ×3 স্থিতিশীল: c63/c64/c65-দ্বৈত)।
- `bridge.work_queue`: আমার রিড **totalOpen 59** (glm31-এর রিড 58) — এক ঘণ্টার ভেতরে দুই রিডের 1-রো পার্থক্য নিশ্চিত করল window-সিমেন্টিক্স ধারা (c60 12 → c63 >100 → c64 52 → c65 58/59)।
- well-known ×2: 200 text/html SPA-index (18তম consecutive masked) — glm31-এর ৪র্থ watchpoint আমার লেন থেকেও নিশ্চিত।

## Method

Zero-credential tower session: `system_health` ×2 (২৫ সেকেন্ড ব্যবধান), `system_summary`, `health_full_sweep` + `redis_ping` (roster-বহির্ভূত runtime-deny প্রোব), `render_service_health` দুই-ধাপ, `supabase_schema_inspect` (ভুল+বৈধ account), `tools/list` সেন্সাস, `bridge.work_queue`; urllib core-api GET ×2 / HEAD; well-known ×2। কোনো production write নেই; কোনো secret প্রিন্ট নেই। Dual-rebase সম্মত: work-start fetch (76acf3e→9382da9), সাবমিট-পূর্ব fetch (9382da9→96f0687, glm31-এর c65 ল্যান্ড হওয়ার পরে)।

Refs: #3376 (bare, anchor) #3776 (glm31 parallel c65) #3751 #3487 #3739 #3772 #3663
