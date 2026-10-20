# SupremeAI — CI/CD ব্যর্থতা সমাধানের সম্পূর্ণ রোডম্যাপ (বাংলা)

> **উৎস:** `docs/CI_PIPELINES_AUDIT_REPORT.md` (Audit Timestamp 2026-10-20)  
> **স্কোপ:** `Supremeai-bd` অর্গানাইজেশনের ১৪টি রিপোজিটরির CI/CD পাইপলাইন।  
> **লক্ষ্য:** সব ব্যর্থ CI ও warning-এর root-cause সমাধান, যাতে federation-wide "green" অবস্থা পুনরুদ্ধার হয়।

---

## ০. সারসংক্ষেপ (Executive Summary)

অডিটে ৬টি **P0/P1 ব্যর্থতা** ও ৪টি **warning শ্রেণি** পাওয়া গেছে। এর মধ্যে:

- **২টি** সমস্যা সিক্রেট/ডিপ্লয়মেন্ট নির্ভর (Error 1, 2) — অ্যাডমিন অ্যাকশন প্রয়োজন।
- **৪টি** ইন-রিপো কোড/কনফিগ ফিক্স (Error 3, 4, 5, 6) — এই রিপোতেই সমাধানযোগ্য।
- **warnings** কোড-গুণগত ও ইনফ্রা-নোটিস — ব্লকিং নয়, তবে পরিষ্কার করা উচিত।

এই রোডম্যাপ ৫টি ফেজে বিভক্ত। প্রতিটি ফেজে কাজ, মালিক (owner), যাচাই (verification) ও ঝুঁকি উল্লেখ করা হয়েছে।

---

## ফেজ ১ — P0: সিক্রেট ও প্রোডাকশন স্বাস্থ্য (Admin Action)

### ১.১ Error 1 — `FEDERATION_PAT` রোটেশন
- **রিপো:** `Supremeai-bd/supremeai-infrastructure`
- **ওয়ার্কফ্লো:** `🔗 Federation Integration Check (§21)` → `Clone sibling federation repos (shallow)`
- **root cause:** `FEDERATION_PAT` এক্সপায়ার্ড/রিভোক্ড অথবা `supremeai` মনোরিপোতে read অ্যাক্সেস নেই → `fatal: Authentication failed` (exit 128)।
- **কাজ:**
  1. GitHub → `supremeai-infrastructure` → Settings → Secrets → `FEDERATION_PAT` আপডেট করুন।
  2. টোকেনে `repo` scope + `Supremeai-bd/supremeai` read অ্যাক্সেস থাকতে হবে।
  3. প্রয়োজনে Infisical/vault-এ সংরক্ষণ করুন (plaintext `.env` নয় — constraint: `no_plaintext_production_secrets`)।
- **যাচাই:** ওয়ার্কফ্লো ম্যানুয়াল রিরান → clone step সবুজ।
- **মালিক:** Admin (≤0.01% শ্রম)।

### ১.২ Error 2 — প্রোডাকশন হেলথ এন্ডপয়েন্ট 404
- **রিপো:** `Supremeai-bd/supremeai` (মনোরিপো)
- **ওয়ার্কফ্লো:** `🔧 Nightly Ops & Maintenance` → `🌐 Live Production Smoke (fail-closed)`
- **root cause:** `RENDER_CORE_URL` (Infisical prod) ম্যাপড ডিপ্লয়মেন্ট `/health/live`, `/health/ready`, `/api/billing/plans`-এ 404 ফেরত দেয়।
- **কাজ:**
  1. `RENDER_CORE_URL` যে Render সার্ভিসে পয়েন্ট করে, সেখানে রাউট রেজিস্ট্রেশন যাচাই করুন (`/health/live`, `/health/ready`)।
  2. অ্যাপ বিল্ড/ডিপ্লয় লগ চেক করুন; সর্বশেষ সফল ডিপ্লয় রিরোল করুন।
  3. Infisical-এ `RENDER_CORE_URL` সঠিক সার্ভিস URL কিনা নিশ্চিত করুন।
  4. ঐচ্ছিক: `STAGING_URL`, `PRODUCTION_URL`/`FIREBASE_PROJECT_ID` কনফিগার করে warning (§৩.২) দূর করুন।
- **যাচাই:** `live_smoke.py` লোকালি `RENDER_CORE_URL` দিয়ে চালানো → সব প্রোব 200।
- **মালিক:** DevOps/Backend।

---

## ফেজ ২ — P1: ইন-রিপো কোড/কনফিগ ফিক্স (এই রিপোতে)

### ২.১ Error 3 — `stale_claim_releaser.py` CLI মিসম্যাচ
- **রিপো:** `Supremeai-bd/supremeai-open`
- **ওয়ার্কফ্লো:** `CI — Open Unified Pipeline` → `agent-loop` → `2-Stage Graduated Claim Lease Gate`
- **root cause:** ওয়ার্কফ্লো `--auto-release --claim-to-branch-min 10.0 --branch-to-pr-min 30.0` পাস করে, কিন্তু স্ক্রিপ্ট শুধু `--self-test`/`--run` বোঝে → exit 2।
- **সমাধান (সম্পন্ন):** `scripts/ci/stale_claim_releaser.py`-এ argparse যোগ করা হয়েছে (`--auto-release`, `--claim-to-branch-min`, `--branch-to-pr-min`)।
- **যাচাই:** `python scripts/ci/stale_claim_releaser.py --auto-release --claim-to-branch-min 10.0 --branch-to-pr-min 30.0` → exit 0।
- **মালিক:** CI Fixer।

### ২.২ Error 4 — Federation CI Watchdog cross-repo 404
- **রিপো:** `Supremeai-bd/supremeai-open`
- **ওয়ার্কফ্লো:** `Federation CI Watchdog (Scheduled Poll)` → `Poll federation repos for CI failures`
- **root cause:** ডিফল্ট `GITHUB_TOKEN` রিপো-স্কোপড; প্রাইভেট স্যাটেলাইটে `/actions/runs` → HTTP 404; স্ক্রিপ্ট প্রতিটি 404-কে failure হিসেবে গণনা করে → exit 1।
- **সমাধান (সম্পন্ন):** `.github/workflows/federation-ci-watchdog.yml`-এ `GH_TOKEN: ${{ secrets.MERGE_PAT || secrets.OPEN_SYNC_PAT || secrets.GITHUB_TOKEN }}` ওয়্যার করা হয়েছে।
- **অতিরিক্ত (ঐচ্ছিক):** টোকেন না থাকলে 404-কে "skip with warning" হিসেবে গণনা করার জন্য `poll_federation_failures`-এ 404 branch আলাদা করা যেতে পারে (fail-open নয়, শুধু visibility)।
- **যাচাই:** ওয়ার্কফ্লো রিরান → সব ১২ রিপো reachable, exit 0।
- **মালিক:** CI Fixer。

### ২.৩ Error 5 — Satellite Board Audit সব unreachable
- **রিপো:** `Supremeai-bd/supremeai-open`
- **ওয়ার্কফ্লো:** `Satellite Board Audit (Scheduled)` → `Authenticated satellite board audit`
- **root cause:** ডিফল্ট টোকেনে ১১টি প্রাইভেট স্যাটেলাইট HTTP 404 → `decide_exit_code` → 2।
- **সমাধান (সম্পন্ন):** `.github/workflows/satellite-board-audit.yml`-এ PAT fallback ওয়্যার করা হয়েছে।
- **যাচাই:** ওয়ার্কফ্লো রিরান → ১২/১২ reachable, clean/violation ম্যাট্রিক্স।
- **মালিক:** CI Fixer。

### ২.৪ Error 6 — Auto-Prune non-fast-forward push rejection
- **রিপো:** `Supremeai-bd/supremeai-open`
- **ওয়ার্কফ্লো:** `Landing — Auto-Merge & Bridge Dispatch` → `Auto-Prune Ephemeral Transit Patches (#416)`
- **root cause:** transit patch ফাইল মুছে `git push origin main` করার আগে `git pull --rebase` নেই → concurrent landing-এ non-fast-forward rejection।
- **সমাধান (সম্পন্ন):**
  - `.github/workflows/landing.yml`-এ Auto-Prune step-এ `git pull --rebase origin main` যোগ করা হয়েছে।
  - `scripts/ci/federation_satellite_sync.py`-এর দুটি push-এর আগে `git pull --rebase origin main` যোগ করা হয়েছে।
- **যাচাই:** একাধিক PR একসাথে land করে দেখুন push সফল হয়।
- **মালিক:** CI Fixer / Bridge।

---

## ফেজ ৩ — P2: কোড গুণগত ও অপারেশনাল সতর্কতা

### ৩.১ ESLint warnings (`supremeai-studio`)
- **ফাইল:** `packages/shared-services/src/realtime/BaseWebSocketManager.ts` (unused `event` param ×4), `packages/shared-services/src/services/SelfHealingService.ts` (`any`), `platform/*.ts` (console.log)।
- **কাজ:** unused params `_event` রিনেম; `any` → proper type; `console.log` → logger method।
- **মালিক:** Studio maintainer (এই রিপোতে নয় — satellite)।

### ৩.২ Operational warnings (`supremeai`)
- `STAGING_URL` কনফিগার করুন (pgbouncer probe)।
- `PRODUCTION_URL` বা `FIREBASE_PROJECT_ID` কনফিগার করুন (UI origin resolution)।

### ৩.৩ Node.js 20 deprecation (সব রিপো)
- **কাজ:** `actions/checkout`, `setup-python`, `setup-node` নতুন major version-এ আপগ্রেড করুন যখন স্টেবল রিলিজ আসে; আপাতত warning, ব্লকিং নয়।

### ৩.৪ Ubuntu 26 runner migration notice
- **কাজ:** `ubuntu-latest` → `ubuntu-24.04` পিন করুন অথবা Ubuntu 26-এ টেস্ট করুন (Oct 19, 2026 মাইগ্রেশন)।

### ৩.৫ Punycode deprecation (watchdog)
- Node punycode module → userland alternative; নিম্ন-অগ্রাধিকার।

---

## ফেজ ৪ — যাচাই ও সার্টিফিকেশন

1. **Self-tests:**  
   - `python scripts/ci/stale_claim_releaser.py --self-test`  
   - `python scripts/ci/federation_ci_watchdog.py --self-test`  
   - `python scripts/ci/satellite_board_guard.py --self-test`  
   - `python scripts/ci/federation_satellite_sync.py --self-test`
2. **Pytest:** `python -m pytest -q tests/`
3. **YAML lint:** सभी workflow YAML parse যাচাই।
4. **Manual workflow rerun:** watchdog, satellite-board-audit, pipeline, landing।
5. **Evidence:** controller-run test exit 0 + git diff scope + SHA-256 (AGENT_RULES evidence verification)。

---

## ফেজ ৫ — পর্যবেক্ষণ ও স্থায়ী নিয়ম (Zero-Admin)

- ১৪-anchor hub (#761 CI Pipeline Failures) মনিটর করুন; নতুন incident এলে এই রোডম্যাপ আপডেট করুন।
- `satellite_board_guard.py` সাপ্তাহিক রানে ১২/১২ reachable নিশ্চিত করুন।
- প্রতিটি ফিক্সের পর AGENTS.md §3 "3-Second Preflight" চেকলিস্ট আপডেট করুন।

---

## রিস্ক ও নির্ভরতা

| ঝুঁকি | প্রশমন |
|---|---|
| PAT রোটেশন না হলে Error 1/4/5 থাকবে | Admin action ফেজ ১-এ সর্বোচ্চ অগ্রাধিকার |
| Render ডিপ্লয় ব্যর্থ হলে Error 2 থাকবে | রোলব্যাক + হেলথ রাউট যাচাই |
| Concurrent landing race | `git pull --rebase` (ফেজ ২.৪) |
| Private repo visibility | PAT fallback (ফেজ ২.২/২.৩) |

---

## পরিবর্তিত ফাইল (এই সেশনে)

- `scripts/ci/stale_claim_releaser.py` — CLI argparse যোগ।
- `.github/workflows/federation-ci-watchdog.yml` — PAT fallback।
- `.github/workflows/satellite-board-audit.yml` — PAT fallback।
- `.github/workflows/landing.yml` — Auto-Prune step-এ `git pull --rebase`।
- `scripts/ci/federation_satellite_sync.py` — push-এর আগে `git pull --rebase`।

---

> **নোট:** Error 1 ও Error 2 সিক্রেট/ডিপ্লয়মেন্ট নির্ভর; কোড পরিবর্তন ছাড়া শুধু অ্যাডমিন অ্যাকশনে সমাধান সম্ভব। বাকি সব ফিক্স এই রিপোতেই করা হয়েছে এবং self-test/pytest সবুজ।