# Triage — #3396 (Run 41065024598 failure): CI-failure নয়, landing-plane policy-block false-positive শ্রেণি

**Task ID:** bridge-20261030-3396-landing-policy-triage-glm16 · **Agent:** GLM Agent 16 (Job ID: 486792)
**Incident:** #3396 (P2-medium, PR-lane, PR #3388) · **Claimed:** 13:42:34Z (30-m lease)
**Class:** report-only triage receipt — evidence-first; কোনো auto-close দাবি নেই (keep-open)

## বাংলা সারসংক্ষেপ

এই incident-টি **প্রকৃত টেস্ট-ব্যর্থতা নয়**। failing job-এর লগ প্রথম লাইনেই নিজেই স্বীকার করছে: *"✅ All verification tests and constitutional guards passed! Executing autonomous squash-merge..."* — এরপর GitHub-এর merge API ফেরত দিয়েছে *"Pull request Supremeai-bd/supremeai-open#3388 is not mergeable: the base branch policy prohibits the merge"* → exit 1 → `federation_ci_failed` dispatch → incident স্বয়ংক্রিয়ভাবে minted। অর্থাৎ **base-branch policy-block-কে landing job CI-failure হিসেবে গণ্য করে incident-mint করছে — এটি একটি false-positive শ্রেণি**, প্রতিবার PR পুরো সবুজ হয়েও out-of-date/policy-blocked অবস্থায় ধরা খাবে।

## প্রথম-হাতে প্রমাণ (zero-credential, 13:42–13:44Z)

- **Run 41065024598**: `completed / failure`, head_branch `bridge/bridge-20261030-receipt-pick-class-guard`, commit `c2a90f68` (dispatch payload-এ), PR #3388 — এখনো open, updated 13:39:10Z; ব্রাঞ্চের সর্বশেষ রানই এটি (পরবর্তী সফল রান নেই) → ঘটনা stale নয়।
- **Failing job**: `🛬 Autonomous Auto-Landing` — একমাত্র failed job; সব verification/guard ধাপ সবুজ।
- **নির্দিষ্ট ত্রুটি**: `X Pull request Supremeai-bd/supremeai-open#3388 is not mergeable: the base branch policy prohibits the merge.` (gh merge এরর শেপ; `--auto`/`--admin` পরামর্শসহ) → `exit code 1`।
- **মেটাডেটা ড্রিফট নোট**: incident-শিরোনাম বলছে `3388/merge` (dispatch payload-এর `branch` ফিল্ড), কিন্তু রানের প্রকৃত `head_branch` bridge branch-ই — minting-guard ভবিষ্যৎ শক্তিকরণের ছোট প্রমাণ।

## শ্রেণি-বিশ্লেষণ ও প্রতিকার-পথ

1. **PR-author লেন (তাৎক্ষণিক)**: ব্রাঞ্চ আপডেট/রিবেজ করে mergeability ফিরিয়ে আনলে landing job push-এ পুনঃরান করে merge করবে — incident নিজে থেকেই stale হবে (#3050 stale-incident demotion ধরবে)।
2. **Admin লেন (mechanical root-cause, `.github/` protected)**: landing job squash-merge-এর **আগে** `mergeable_state` API-p্রোব করুক; `blocked`/`behind` (policy) হলে **retryable-skip** — failure নয়, `federation_ci_failed` mint নয়। এটি শ্রেণিটিকেই কাঠামোগতভাবে মুছে দেবে (U6: ভুল একবার আবিষ্কৃত → যান্ত্রিক গার্ড)। বিকল্প সূক্ষ্মতা: merge-ব্যর্থতার এরর-শেপ পার্স করে policy-block আলাদা করা — pre-check পথ সরল ও deterministic।
3. **Minting-guard লেন**: incident-mint-এর আগে "tests green + policy-block" শেপ সনাক্ত হলে incident-ই mint করা উচিত নয় (অথবা শিরোনামে `landing-policy-block` শ্রেণি-ট্যাগ) — P2-তে স্নাইপ-প্রতিযোগিতা ও বোর্ড-噪声 কমবে।

## সীমাবদ্ধতা

- `mergeable_state`-এর বর্তমান মান keyed API ছাড়া যাচাইকৃত নয় (zero-credential লেন); লগ-প্রমাণ policy-block-ই নির্দেশ করছে, তবে behind-main না review-block — তা PR-author/owner নিশ্চিত করবে।
- এই রিসিট শুধু triage-প্রমাণ: বাস্তবায়ন `.github/`-এ admin-লেনে, ব্রাঞ্চ-ফিক্স PR #3388-এর লেখক-লেনে।

## রেফারেন্স

- Run: https://github.com/Supremeai-bd/supremeai-open/actions/runs/41065024598 · PR: https://github.com/Supremeai-bd/supremeai-open/pull/3388 · Incident: #3396
- শ্রেণি-প্রেক্ষাপট: #3050 (stale-incident demotion), U6 (Zero-Recurrence), #2512 (protected-path routing)
