---
id: crown-jewel-module-13-security-middleware-truth-power-up-2026-09-17
title: "Crown Jewel Module Series — Module 13: Security Middleware Truth Power-Up (সুরক্ষা-মিডলওয়্যার স্ট্যাকের সত্য-মানচিত্র — মাউন্ট-বিহীন anti-hacking, config-বন্দি না-হওয়া সীমা, fail-open টেন্যান্ট-লিমিটার — পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Governance Circle (backend/middleware/ + backend/core/autonoguard_engine.py + backend/core/security/ — সুরক্ষা-স্তরের সত্যায়ন-স্তর)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ১৩ — একটি মডিউল (Security Middleware স্ট্যাক), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — branch crown-jewel-v2 base b895e67-এ spot-checkকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; ৪-স্তম্ভ-দর্শন Part 5.5-এ অডিটকৃত; কোনো নতুন CI-গেট প্রস্তাব নয় (dast-zap.yml বিদ্যমান)"
depends_on:
  - "backend/middleware/anti_hacking.py (158 লাইন — AntiHackingContextMiddleware: admin-only context-aware + JIT OTP; alert-only ডিফল্ট `settings.enforce_anti_hacking`; SECURITY_CONTEXT_TTL/SECURITY_CAUTION_LOG_TTL env-চালিত; caution-log ltrim 0..49 বাউন্ডেড; L183-এর কাছে OTP-pending TTL 300 স্থির)"
  - "MOUNT-প্রমাণ: backend/core/app.py L28 `app.add_middleware(MemoryAwareMiddleware)` — একমাত্র middleware-mount; backend-ব্যাপী grep-এ AntiHackingContextMiddleware-এর উৎস+টেস্ট ছাড়া কোনো mount/include নেই → টেস্ট-কভারড কিন্তু আনমাউন্টেড"
  - "টেস্ট-দ্বৈততা: backend/tests/middleware/test_anti_hacking.py + backend/tests/middleware/test_middleware_anti_hacking.py — একই মিডলওয়্যারের দুটি পৃথক টেস্ট-ফাইল"
  - "backend/core/autonoguard_engine.py (480 লাইন — 'Zero-Breakage Autonomous Governance Layer': JIT OTP + AST ImmuneSystemScanner + error remediation + circuit breaker; ব্যবহারকারী: backend/core/app_builder.py + backend/core/security/autonoguard_middleware.py → ওয়্যারড)"
  - "backend/middleware/rate_limiter.py (138 লাইন — AsyncRateLimiter Redis sliding-window + InMemoryFallbackLimiter; _MAX_KEYS=1000 বাউন্ডেড-সুইপ, Audit B-11 ফিক্স 2026-09-17; RATE_LIMIT_ENABLED env; _tier_limits ইন-কোড dict: free 60 / pro 600 / premium 1200 / enterprise 6000 প্রতি ৬০s; acquire() ডিফল্ট limit=100 window=60; near-limit warn ratio 0.8 স্থির)"
  - "backend/middleware/tenant_rate_limiter.py (59 লাইন — enforce_tenant_rate_limit: identity tenant>subject>ip (হেডার-নিয়ন্ত্রিত নয়); pipeline incr+expire 60s স্থির; `current_hits > 100` স্থির; Redis-অনুপস্থিতিতে fail-open, কোনো ইন-মেমরি fallback নেই)"
  - "কলার-প্রমাণ: backend/core/security/api_key_middleware.py + backend/tools/api_gateway.py AsyncRateLimiter ব্যবহার করে (operational); backend/core/config_fields.py L151 enforce_anti_hacking Field + OTP_COOLDOWN_SECONDS alias-সহ (config-চালিত)"
  - "লেগেসি-ডক: docs/plans/features/antihacking_security_defense_framework.md (439 লাইন, status: historical, V5-মাইগ্রেটেড) — ৪-স্তর 'security-as-a-service' ফ্রেমওয়ার্ক দাবি; L348-352 অযাচাইকৃত SLA (uptime >99.9%, detection 99%/১মিনিট)"
  - "CI-বাস্তবতা: .github/workflows/dast-zap.yml (DAST) + audit-release.yml বিদ্যমান — নতুন সুরক্ষা-CI-গেট এই নীলনকশার পরিসরে নয়"
  - "V5.1-প্রেসিডেন্ট (commit 177942c): backend/core/security/__init__.py is_token_revoked — env-aware fail-policy প্রতিষ্ঠিত (production/staging অ্যাডমিন fail-closed; dev/test fail-open + loud logger.error) → tenant-লিমিটারের fail-মোড-প্রস্তাবের (P-C) জন্য প্ল্যাটফর্ম-প্রতিষ্ঠিত নীতি-প্যাটার্ন"
implements:
  - "সুরক্ষা-স্তরের সত্য-মানচিত্র: ৪ উপাদানের (anti_hacking middleware / autonoguard / rate_limiters / api_key_middleware) mount-state + caller-state টেবিল — 'security theater' বনাম প্রকৃত-সুরক্ষা পৃথকীকরণ"
  - "zero-hardcode সংশোধন-প্রস্তাব: tier-limits, tenant-সীমা/জানালা, OTP TTL, warn-ratio — সব env/config-চালিত"
  - "tenant-লিমিটার resilience-প্রস্তাব: বাউন্ডেড ইন-মেমরি fallback (InMemoryFallbackLimiter-প্যাটার্ন পুনঃব্যবহার) + config-চালিত fail-মোড"
  - "মাউন্ট-সিদ্ধান্ত প্রস্তাব (ফাউন্ডার-গেটেড): alert-only-ডিফল্টে anti-hacking middleware মাউন্ট বা সুনির্দিষ্টভাবে mothball — দ্ব্যর্থহীন এক-রাষ্ট্র"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (branch crown-jewel-v2 base b895e67: anti_hacking.py 158-লাইন পূর্ণপাঠ; rate_limiter.py/tenant_rate_limiter.py পূর্ণপাঠ; app.py L28 mount-grep; autonoguard হেডার+কলার-grep; config_fields L151; লেগেসি-ডক L348-352)"
code_evidence:
  - "মাউন্ট-বিহীন সুরক্ষা — AntiHackingContextMiddleware সংজ্ঞায়িত (158 লাইন) + ডাবল-টেস্ট-কভারড কিন্তু app-এ মাউন্টেড নয় (app.py L28-এ কেবল MemoryAwareMiddleware) → এর JIT-OTP/context-চেক প্রোডাকশন-পথে চলে না; টেস্ট পাস করলেও বাস্তব-সুরক্ষা শূন্য — 'tested dormant' নতুন শ্রেণি"
  - "সীমা-কোডে-আটকে — rate_limiter.py _tier_limits dict + tenant_rate_limiter.py 100/60s: টিয়ার-মূল্য পরিবর্তনে কোড-ডিপ্লয় লাগবে (zero-hardcode লঙ্ঘন); বিপরীতে anti_hacking.py-র TTL-দুটি env-চালিত — একই স্ট্যাকে দুই-মান"
  - "fail-open অসামঞ্জস্য — tenant_rate_limiter Redis-ডাউনে সম্পূর্ণ bypass (logger.warning + return); অথচ rate_limiter-এ বাউন্ডেড ইন-মেমরি fallback আছে (B-11) → Redis-বিভ্রাটে টেন্যান্ট-সীমা সম্পূর্ণ অনুপস্থিত, কিন্তু API-key-সীমা কার্যকর — অভিন্ন ঝুঁকিতে দুই আচরণ"
  - "স্থির OTP-সাময়িকতা — anti_hacking.py OTP-pending `ex_seconds=300` ইন-লাইন (কমেন্ট: '৫ মিনিট') — একই ফাইলের অন্যান্য TTL env-চালিত হওয়ায় এটি ব্যতিক্রম"
  - "চলন্ত-ভালো-প্যাটার্ন — alert-only ডিফল্ট (ফাউন্ডার-গেটেড enforcement), identity কখনো টেন্যান্ট-হেডার-নিয়ন্ত্রিত নয়, Upstash ফ্রি-টিয়ার-সামঞ্জস্য (কেন্দ্রীয় redis_manager, অতিরিক্ত কানেকশন নয়) — এই তিনটি সংরক্ষণ-বাধ্য"
  - "লেগেসি-দাবি-ব্যবধান — লেগেসি-ডকের 'security-as-a-service + Admin Threat Dashboard + SLA' বনাম বাস্তব ৪-ফাইল স্ট্যাক: V5 ডকটিকে historical করেছে; এই নীলনকশা কোড-সত্যই ক্যানোনিকাল"
test_evidence: "বিদ্যমান — test_anti_hacking.py + test_middleware_anti_hacking.py (দ্বৈত, মাউন্ট-বিহীন কোড কভার করে); test_core_rate_limiter.py + test_api_key_middleware.py (operational পথ); execution প্রস্তাব: tier-config-লোড টেস্ট, tenant-fallback টেস্ট, fail-মোড দুই-মুখ টেস্ট; দ্বৈত টেস্ট-ফাইল একীকরণ (এক ক্যানোনিকাল)"
acceptance_criteria:
  - "প্রতিটি প্রস্তাব চার-স্তম্ভ-দর্শন-সংগত (Part 5.5)"
  - "সব সীমা/TTL/ratio env/config-চালিত — ইন-কোড স্থির অবশিষ্ট শূন্য (zero-hardcode)"
  - "মাউন্ট-সিদ্ধান্ত ফাউন্ডার-গেটেড; ডিফল্ট আচরণ alert-only বহাল"
  - "কোনো নতুন CI-গেট/workflow প্রস্তাব নয়; lint_plans.py 0 error / 0 warning"
---

# Module 13 — Security Middleware Truth Power-Up

## বাংলা সারসংক্ষেপ

প্ল্যাটফর্মের সুরক্ষা-স্তর চারটি উপাদানে বিতরণী: (১) `AntiHackingContextMiddleware` — admin-context + JIT-OTP, **টেস্ট-কভারড কিন্তু কোথাও মাউন্টেড নয়**; (২) `AutonoGuard Engine` (480 লাইন) — AST-স্ক্যান + স্ব-নিরাময়, app_builder-চালিত **ওয়্যারড**; (৩) `AsyncRateLimiter` — Redis sliding-window + বাউন্ডেড ইন-মেমরি fallback, operational; (৪) `enforce_tenant_rate_limit` — Redis-এ স্থির 100/৬০s সীমা, Redis-ডাউনে **ফলব্যাক-বিহীন fail-open**। সমস্যা তিনটি: **সত্য-ঘাটতি** (মাউন্ট-বিহীন সুরক্ষা 'থাকার' ভ্রম), **zero-hardcode লঙ্ঘন** (tier-limits/tenant-সীমা/OTP-TTL/warn-ratio কোডে আটকে), আর **resilience-অসামঞ্জস্য** (একই Redis-বিভ্রাটে এক লিমিটার fallback-পায়, অন্যটি সম্পূর্ণ অদৃশ্য)।

লেগেসি ডকুমেন্ট (`antihacking_security_defense_framework.md`, 439 লাইন) একটি বিস্তৃত ৪-স্তর framework ও অযাচাইকৃত SLA দাবি করে — V5 এটিকে `historical` করেছে; এই নীলনকশা কোড-সত্যকেই ক্যানোনিকাল করে। প্রস্তাবগুলো নতুন ব্যয় যোগ করে না: সব বিদ্যমান ফাইলে in-place, সব সীমা config-এ, নতুন সার্ভিস/কী/CI শূন্য।

**সততা-দাবি:** এটি `proposed` নীলনকশা — মাউন্ট/আনমাউন্ট সিদ্ধান্ত ফাউন্ডার Gate 2-সাপেক্ষ।

---

## Part 1 — Competitor Intelligence (প্রতিযোগী-বুদ্ধিমত্তা, dated evidence)

| উৎস | প্রমাণ (লেবেলযুক্ত) | তাৎপর্য |
|---|---|---|
| কোড-বাস্তবতা (base b895e67) | [measured] ৪ উপাদান, মোট ~৮৩৫ লাইন; mount-state মিশ্র; ২টি টেস্ট-ফাইল দ্বৈত | স্ট্যাক ছোট — সংশোধন-ব্যয় নিম্ন |
| লেগেসি-ডক (L348-352) | [vendor-published/দাবি-কেবল] SLA 99.9% uptime, detection 99%/১মিনিট — কোনো পরিমাপ-পাইপলাইন নেই | দাবি-বনাম-কোড ব্যবধান নথিভুক্ত; historical-স্ট্যাটাস বহাল |
| নিজস্ব অডিট-ঐতিহ্য | [measured] Audit B-11 ফিক্স (fallback-কী-লিক) ইতিমধ্যে rate_limiter-এ | স্ট্যাক ইতিমধ্যে অভ্যন্তরীণ-অডিট-পরিপক্ব — ধারাবাহিকতা সহজ |
| DAST-বাস্তবতা | [measured] dast-zap.yml বিদ্যমান workflow | গতানুগতিক DAST চলছে; নতুন গেটের প্রয়োজন প্রমাণিত নয় |

---

## Part 1.5 — Gate 0 Reconciliation

| সম্পর্কিত প্ল্যান | সম্পর্ক | মীমাংসা |
|---|---|---|
| `docs/plans/features/antihacking_security_defense_framework.md` (historical) | **একই ডোমেইন, ভিন্ন granularity** | সেটি ঐতিহাসিক-দৃষ্টিভঙ্গি; এই ডকুমেন্ট কোড-সত্য; কোনো দ্বন্দ্ব-সৃষ্টি নয় — historical-স্ট্যাটাস অক্ষত |
| `MODULE_09_DORMANT_TOOLS_POWER_UP_2026-09-17.md` | **সম্পূরক** | 'tested dormant' শ্রেণিটি Module 09-এর dormant-শ্রেণিবিন্যাসের সুরক্ষা-সংযোজন |
| `MODULE_10_FRONTEND_TIER_S_WIRING_POWER_UP_2026-09-17.md` | **মতবাদ-প্রেসিডেন্ট** | CI-gate-পূর্ব শূন্য-false-positive শর্ত এখানেও প্রযোজ্য — তাই নতুন গেটই প্রস্তাব নেই |
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` | cross-check | সুরক্ষা-স্তরে OPEN defect শূন্য; এই প্রস্তাব নতুন defect তৈরি করে না |

---

## Part 2 — Six-Field Analysis

### ২.১ কী আছে

1. **AntiHackingContextMiddleware** (anti_hacking.py): admin-কেবল context-মিল + caution-টিয়ার (same-ua/subnet/fingerprint) + OTP-কুলডাউন (`OTP_COOLDOWN_SECONDS` config) + alert-only ডিফল্ট; caution-log বাউন্ডেড।
2. **AutonoGuard Engine** (480 লাইন): JIT OTP + AST ImmuneSystemScanner + error_remediator + circuit-breaker; `backend/core/security/autonoguard_middleware.py` + `app_builder.py`-চালিত।
3. **AsyncRateLimiter**: Redis pipeline sliding-window; `RATE_LIMIT_ENABLED` env; TESTING-bypass; বাউন্ডেড (১০০০-কী) ইন-মেমরি fallback; api_key_middleware/api_gateway-চালিত।
4. **Tenant limiter**: হেডার-অনুপ्रবেশ-প্রতিরোধী identity-চেইন (tenant>subject>ip); atomic pipeline।
5. **Config-সংযোগ**: `enforce_anti_hacking` + `otp_cooldown_seconds` config_fields-এ।

### ২.২ কী নেই

1. anti-hacking middleware-এর **কোনো mount** নেই — JIT-OTP/context-চেক প্রোডাকশনে অকার্যকর।
2. tier-limits/tenant-সীমা/জানালা/warn-ratio/OTP-pending-TTL **config-চালিত নয়**।
3. tenant-লিমিটারের **কোনো fallback** নেই (fail-open) — Redis-বিভ্রাটে টেন্যান্ট-সীমা শূন্য।
4. দুই টেস্ট-ফাইলের **একীকরণ** নেই — একই আচরণের দ্বৈত সত্য-উৎস।
5. সুরক্ষা-স্তরের **mount-state মানচিত্র** কোথাও নেই — কী প্রকৃতপক্ষে চলছে তা কেবল grep-যোগ্য।

### ২.৩ কী করতে হবে

- **P-A মাউন্ট-সিদ্ধান্ত (ফাউন্ডার-গেটেড):** বিকল্প ১ — alert-only-ডিফল্টে মাউন্ট (admin-only বলে hot-path প্রভাব ন্যূনতম; বিদ্যমান টেস্ট প্রস্তুত); বিকল্প ২ — সুনির্দিষ্ট mothball (ডকুমেন্টেড, MODULES_LIST-সংগত)। দ্ব্যর্থহীনতাই লক্ষ্য।
- **P-B zero-hardcode:** `_tier_limits` → config/env-চালিত (per-tier requests/window); tenant 100/60s → config; OTP-pending 300s → `SECURITY_OTP_PENDING_TTL` (ডিফল্ট 300 নথিভুক্ত); warn-ratio 0.8 → config।
- **P-C tenant-resilience:** InMemoryFallbackLimiter-প্যাটার্ন পুনঃব্যবহার (বাউন্ডেড); fail-মোড config-চালিত, V5.1-এর env-aware fail-policy-প্যাটার্ন অনুসরণ করে (production fail-closed/বাউন্ডেড-fallback; dev fail-open+loud log) — V3 token_budget ও V5.1 revocation-এ প্রতিষ্ঠিত একই নীতি-ধারা।
- **P-D টেস্ট-একীকরণ:** দুই anti-hacking টেস্ট-ফাইল → এক ক্যানোনিকাল; মাউন্ট-সিদ্ধান্তের পথে প্রস্তুতি।
- **P-E সত্য-মানচিত্র ডকুমেন্টেশন:** এই ডকুমেন্টের ২.১-টেবিল ধারায় mount-state রেকর্ড; ভবিষ্যৎ-পরিবর্তনে আপডেট-দায়।
- **P-F জিরো-বাইপাস ইনফ্যারেন্স সিকিউরিটি ও ডুয়াল-ড্রাইভেন টেলিমেট্রি (AGENTS.md Rule 7):**
  - **Zero-Bypass Route Guard:** কোনো আনঅথেনটিকেটেড বা অবৈধ টেন্যান্ট যেন মডেল ইনফ্যারেন্স ইনজেক্ট করতে না পারে, সেজন্য মিডলওয়্যার লেভেলেই `InferenceContext` টোকেন স্কোপ ও আরবিএসি রোল প্রি-ভ্যালিডেট করা হবে।
  - **Dual-Driven Security Experience:** সাধারণ কাস্টমার দেখবে সহজ-সরল রেট লিমিট স্ট্যাটাস ও টু-ফ্যাক্টর নিরাপত্তা; আর সুপার অ্যাডমিন পাবে লাইভ থ্রেট ড্যাশবোর্ড, ব্রুট-ফোর্স থ্রটলিং ট্র্যাকার ও JIT OTP অডিট লগ।

### ২.৪ কীভাবে করব

1. **Phase 1 (config-ize):** সব স্থির → config/env, ডিফল্ট-মান অপরিবর্তিত (আচরণ-নিরপেক্ষ)।
2. **Phase 2 (tenant-fallback):** বাউন্ডেড fallback + fail-মোড config; ডিফল্ট = বর্তমান fail-open (কোনো আচরণ-পরিবর্তন নয়, ক্ষমতা-সংযোজন কেবল)।
3. **Phase 3 (টেস্ট-একীকরণ):** দ্বৈত টেস্ট এক-ফাইলে; সব বিদ্যমান টেস্ট সবুজ।
4. **Phase 4 (মাউন্ট-সিদ্ধান্ত ও ইনফ্যারেন্স গার্ড):** ফাউন্ডার Gate 2 — মাউন্ট হলে alert-only-ডিফল্ট + flag; Zero-Bypass মিডলওয়্যার ফিল্টারিং সক্রিয়করণ।
5. প্রতিটি ধাপে kill-switch; কোনো workflow/কোড-পথ নতুন যোগ নয়।

### ২.৫ বেনিফিট

1. **সুরক্ষা-সত্য:** 'সুরক্ষা আছে' বনাম 'সুরক্ষা চলছে' পৃথক — অডিটযোগ্য মানচিত্র।
2. **অপারেশনাল-চপলতা:** tier-মূল্য/সীমা পরিবর্তন কোড-ডিপ্লয় ছাড়া config-এ।
3. **ইনফ্যারেন্স বাউন্ডারি নিরাপত্তা:** টোকেন বাজেটের কোনো অবৈধ বাইপাস বা ক্রস-টেন্যান্ট লিক মিডলওয়্যার স্তর পেরোতে পারবে না।
4. **বিভ্রাট-সহনশীলতা:** Redis-ডাউনেও টেন্যান্ট-সীমা বাউন্ডেড-ভাবে বর্তমান (ঐচ্ছিক)।
5. **শূন্য-মার্জিনাল-ব্যয়:** নতুন সার্ভিস/কী/ডিপেন্ডেন্সি শূন্য।

### ২.৬ ক্ষতি/ঝুঁকি

1. মাউন্ট করলে admin-অভিজ্ঞতায় OTP-প্রম্পট (alert-only-তে কেবল লগ) — প্রশমন: alert-only ডিফল্ট; enforcement ফাউন্ডার-গেটেড।
2. config-ভুলে সীমা-বিকৃতি — প্রশমন: ভ্যালিডেশন + ডিফল্ট-ফলব্যাক + টেস্ট।
3. fallback-মেমরি-বৃদ্ধি — প্রশমন: B-11-প্যাটার্ন বাউন্ডেড-সুইপ উত্তরাধিকার।
4. টেস্ট-একীকরণে কভারেজ-অন্তর্বর্তী হ্রাস — প্রশমন: একীকরণ-পূর্বে দুই-ফাইলের ইউনিয়ন-কেস তালিকা।

---

## Part 3 — Out of Scope

- নতুন WAF/IDS/পেইড সুরক্ষা-সার্ভিস নয় (zero-cost লঙ্ঘন)।
- নতুন CI-গেট/workflow নয় (dast-zap বিদ্যমান; Module 10-মতবাদ)।
- লেগেসি framework-ডকের বিস্তার বা পুনরুজ্জীবন নয় — historical বহাল।
- AuthN/AuthZ স্ট্যাক (JWT/roles) রিডিজাইন নয় — কেবল middleware-স্তর।

---

## Part 4 — ৯-নিয়ম ও Constitution-সংগতি

| নিয়ম | অবস্থান |
|---|---|
| duplicate subsystem নয় | fallback-পুনঃব্যবহার (নতুন লিমিটার-সিস্টেম নয়); টেস্ট-একীকরণ |
| Playwright replacement নয় | সম্পর্কহীন |
| Free-tier quota-trick নিষেধ | সম্পর্কহীন — সীমা স্থানীয়-পলিসি |
| API process-এ Chromium নয় | সম্পর্কহীন |
| এক মডিউল = এক ডকুমেন্ট | কেবল security-middleware স্ট্যাক |
| single-plan execution discipline | proposed; Gate 2-পূর্বে execution নয় |
| docs-only শাখা-প্রোটোকল | ডকুমেন্ট docs-only; কোড-পরিবর্তন ভবিষ্যৎ execution-এ |
| pull-before-push | অনুসৃত (branch `crown-jewel-v2`) |
| প্রমাণ-শৃঙ্খলা | path/line-ভিত্তিক; SLA-দাবি 'দাবি-কেবল' লেবেল |

---

## Part 5 — Verification & Rollback

- **Gate 4:** config-লোডার টেস্ট (সব ক্ষেত্রে positive/negative); tenant-fallback টেস্ট; দুই-মুখ fail-মোড টেস্ট।
- **Gate 5:** ইন-কোড স্থির-সীমার সংখ্যা → 0; Redis-বিভ্রাট-ড্রিলে tenant-সীমা বর্তমান (fallback-মোডে); বিদ্যমান টেস্ট-সুইট শূন্য-ব্যর্থতা।
- **Gate 6:** সব পরিবর্তন config-flag/kill-switch-যোগ্য; মাউন্ট = এক-লাইন include/অনুপস্থিতি; fallback off-যোগ্য; কোনো ডেটা-মাইগ্রেশন নয়।

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Audit)

| স্তম্ভ | মূল্যায়ন | প্রমাণ |
|---|---|---|
| **Zero cost** | ✅ সংগত | বিদ্যমান Redis/Upstash ফ্রি-টিয়ার; নতুন সার্ভিস/কী শূন্য; DAST ইতিমধ্যে বিদ্যমান |
| **Lightweight** | ✅ সংগত | fallback বাউন্ডেড (১০০০-কী উত্তরাধিকার); নতুন প্যাকেজ শূন্য; admin-only চেক-ব্যাপ্তি |
| **Fast smooth** | ✅ সংগত | ডিফল্ট আচরণ-পরিবর্তন শূন্য (config-ডিফল্ট = বর্তমান মান); alert-only ডিফল্ট; সাধারণ-ব্যবহারকারী পথে শূন্য-ব্যয় |
| **Zero hardcode** | ✅ সংগত (সংশোধন-মূলক) | এই নীলনকশাই স্ট্যাকের স্থির-সীমাগুলো (tier/tenant/OTP-TTL/ratio) config-এ সরানোর প্রস্তাব — বর্তমান কোডের লঙ্ঘন স্বীকৃত ও সংশোধন-প্রস্তাবিত |

## Part 6 — পরবর্তী মডিউল লাইনেজ

- **Cycle 14:** `MODULE_14_USER_FACING_CAPABILITY_TRUTH_POWER_UP_2026-09-17.md` — ইউজার-মুখী ক্ষমতা-সত্য (voice-স্টাব-চেইন লাইভ-মাউন্টেড; P2P-স্টাব)।
- **Cycle 15-প্রার্থী:** AutonoGuard-গভীর-অডিট (480-লাইন ইঞ্জিনের গেট-সেমান্টিকস), billing-gateway, HITL-নীলনকশা — কিউ-পুনঃর‍্যাঙ্ক-অধীন।
