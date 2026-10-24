---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:phase_1_execution_patch_notes
subject: SupremeAI মাস্টার প্ল্যান — ফেজ ১ কমপ্লিশন প্যাচ (Phase 1 Completion Patch)
document_role: roadmap
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI মাস্টার প্ল্যান — ফেজ ১ কমপ্লিশন প্যাচ (Phase 1 Completion Patch)

**Date:** 2026-09-13 · **Base:** `main @ c4d4ec4` · **Type:** feature + governance close-out

> বাংলা: এই প্যাচটি MASTER_PLAN-এর **Phase 1 — Capability Completion** এর মূল
> ওয়্যারগুলো সংযুক্ত করে। প্রতিটি পরিবর্তন পুরোনো পরিকল্পনা-কর্পাসের প্রতিশ্রুতি
> পূরণ করে — কোনো নতুন সাবসিস্টেম নয় (Constitution #3: Reuse Before Creation)।

## কী কী শিপ হলো (What shipped)

### ১. Scout goes live (specs/002 close-out) — B2 battlefield fuel
- `api/routes/deep_research.py`: `_web_search` এখন **scout-first** — টেন্যান্টের
  সক্রিয় `CrawlPolicy` দিয়ে governed crawl (robots.txt, rate pacing, SSRF gate,
  dedup, zero-token summary); ফাঁকা হলে পুরোনো browser-agent fallback।
- `scout/persistence.py` (নতুন): DB-first, memory-fallback স্টোর।
- Alembic `2026_09_13_090000_add_crawler_persistence.py`: `crawl_policies`,
  `crawl_history`, `crawl_events` টেবিল + index।
- `api/routes/crawler_admin.py`: সম্পূর্ণ CRUD — `PATCH /policies/{id}`,
  `POST /policies/{id}/enable|disable`, `DELETE /policies/{id}`;
  `GET /events` এখন সত্যিকারের telemetry (hardcoded placeholder সরানো হয়েছে)।
- `core/orchestration/{capability_adapters,conversation_orchestrator}.py`:
  governed `research` capability (risk=medium, fail-closed ছাড়া policy নেই)।

### ২. Reasoning stream — visible intelligence
- `core/observability/reasoning_stream.py` (নতুন): `emit_reasoning_step()`
  যেকোনো agent/pipeline ডাকতে পারে।
- `core/observability/log_batcher.py`: SSE-only `publish()` — DB schema poisoning
  ছাড়া fanout।
- `api/routes/session_stream.py`: `reasoning` চ্যানেল।
- `frontend/src/store/sessionCockpitStore.ts`: `addReasoningEntry` (২০০-ক্যাপ) —
  `ReasoningLog.tsx` অবশেষে সত্যিকারের চিন্তা-প্রক্রিয়া দেখায়।
- deep research pipeline প্রতিটি ধাপ reasoning হিসেবে স্ট্রিম করে।

### ৩. Admin surface — 404 শেষ
- `api/routes/admin_v1.py`: `GET /api/v1/admin/stats`, `/admin/users`,
  `/admin/audit-logs` — সৎ সংখ্যা, degrade হলে `*_degraded` চিহ্ন, ভুয়া ডেটা নেই।

### ৪. Config hardening (specs/001 close-out)
- `core/config_validation.py`: `ConfigValidationReport` +
  `build_config_validation_report()` — required vars, ফরম্যাট, CORS wildcard check।
- `api/server.py`: CORS allow-list এখন `middleware/cors_policy` resolver-চালিত
  (single source of truth; wildcard-proof)।
- `api/routes/config_routes.py`: `GET /config/validation-report` (admin-only)।
- `tests/api/routes/test_config_contract.py` (নতুন): চুক্তি লক করা টেস্ট।

### ৫. One connection registry (Zero-Complexity close-out)
- `api/routes/connections.py`: `/register` এখন `ConnectionRegistry`-তে
  write-through করে (durable `supremeai_connections`) এবং সত্যিকারের record id
  ফেরত দেয়; ব্যর্থ হলে capability path চালু থাকে (Graceful Degradation)।

### ৬. Mission suite + pass^k (Phase 2 সেতু)
- `tests/missions/` (নতুন): ৫টি মিশন, ১২ টেস্ট — governed research, reasoning
  visibility, admin truth, config honesty, pass^k math।
- `scripts/ci/mission_passk.py` (নতুন): স্যুট k বার চালিয়ে
  `pass^k = C(s,k)/C(n,k)` ছাপে; `reports/mission_passk.json` artifact।
- `.github/workflows/ci.yml`: "Mission suite pass^k scoreboard" স্টেপ
  (এখন non-blocking; Phase 2-তে promotion gate)।
- `tests/conftest.py`: mission suite Important tier-এ।

### ৭. Governance docs
- `docs/SKIPPED_TESTS.md` পুনরায় তৈরি — 125-মার্কার baseline, ট্রায়াজ পরিকল্পনা
  (Phase 2 শেষে <30)।
- `STATUS.md`, `MASTER_PLAN.md` হালনাগাদ।
- `MASTER_PLAN_BANGLA.md` (নতুন) — সম্পূর্ণ মাস্টার প্ল্যানের বাংলা সংস্করণ।

## ভেরিফিকেশন (Verification)

| যাচাই | ফলাফল |
|---|---|
| সব পরিবর্তিত Python ফাইল `py_compile` | ✅ PASS |
| `tests/missions` + `test_config_contract` + connections + scout tests | ✅ 45 passed |
| pass^k harness (k=3) | ✅ pass^3 = 1.0000 (n=12) |
| Frontend `tsc --noEmit` ডেল্টা | ✅ 0 নতুন এরর (১৮ প্রি-এক্সিস্টিং, আগে-পরে সমান) |
| DB migration chain | `…190000 (user_execution_mode) → 2026_09_13_090000` |

## প্রয়োগ করার নিয়ম (How to apply)

```bash
git clone https://github.com/SaifulHaqueNiloy/supremeai.git
cd supremeai
git apply --stat supremeai_master_plan_phase1_complete.patch   # preview
git apply --check  supremeai_master_plan_phase1_complete.patch # dry-run
git apply          supremeai_master_plan_phase1_complete.patch # apply
cd backend && alembic upgrade head                            # crawl tables
```

## Phase 1-এ এখনও খোলা (Remaining open items)

- Capability health-probe promotion (lifecycle `IDEA` → `MEASURED`)।
- Settings-এ execution-mode UI।
- ফ্রন্টএন্ডে `SCRAPER_BACKEND_URL` resolver।
- নাইটলি লাইভ zero-cost chain-এ pass^k।