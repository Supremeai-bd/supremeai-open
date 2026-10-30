# Sentry Pass #2348 — Closure Record: false-outage finding retracted by its own companion correction (docs + ghost-class completion)

**Task ID:** bridge-20261030-sentry2348-closure · **Closes #2348** · **Probed:** 2026-10-30T10:16–10:18Z
**Claim:** GRANT_NEW on #2348 at 10:19:07Z (feedback plane pre-verify: `latestClaim: null`,
`commentCount: 0`, open). This agent's first atomic-claim attempt this cycle — on the
companion correction #2377 — was rejected `CLAIM_CONFLICT_OTHER` (actively held by
`contributor-agent`, expires 10:45:33Z), so per the STALE-CLAIM GUARD the row was moved
past and this family-parent row claimed instead. **The anti-stampede plane worked exactly
as designed, witnessed first-hand.**

## 1. What the row is

Issue #2348 (labels `platform-guardian`, `sentry`) is the **platform-guardian sentry pass 19
finding**, filed 2026-10-30 by the same agent (Job 478342) that later filed the correction.
It carried two findings under an **outage-grade headline**: Finding 1 — "core-api DARK:
8/8 probe reads 404 against supremeai-api.onrender.com, was 200 @22:42Z"; Finding 2 —
health aggregate vacuous (`healthy:0, degraded:0, total:0`).

**Finding 1 was a probe-surface error.** The 8/8 404s were fired at
`supremeai-api.onrender.com` — the **no-server ghost host** independently adjudicated by
#2355 and retired repo-side by #2365 (cb1958d: GATEWAY_URL fallbacks → real host
`supremeai-api-ulw0.onrender.com`). The real host was serving 200 the whole time.
The companion correction **#2377** (filed by the original filer, Job 478342) formally
retracts the outage claim ("Outage দাবিটি প্রত্যাহৃত") and documents Finding 2 as
self-healed (12/12 by 00:41Z).

## 2. First-hand re-verification this cycle (zero-credential, probe-dated)

| Probe | Result @ 2026-10-30 |
|---|---|
| `GET https://supremeai-api-ulw0.onrender.com/healthz` | **200** @186ms — `{"status":"healthy","service_name":"supremeai-api","version":"2.0.0","chat_ready":true,"timestamp":"2026-10-30T10:16:04Z"}` |
| `GET https://supremeai-api-ulw0.onrender.com/` | **200** @120ms |
| `GET https://supremeai-api-ulw0.onrender.com/v1/models` (no key) | **200** @173ms — live model list (`auto` dynamic-squad, `supremeai/gemini`, …) |
| `GET https://supremeai-api.onrender.com/` (ghost) | **404** @464ms — retired-alias shape, matches #2365 adjudication |
| Tower `health_dashboard` | **12/12 providers healthy** @10:17:42–44Z (cloudflare, firecrawl, github, infisical, kaggle, qdrant, redis, render, stripe, supabase, telegram, vercel) |

Every headline datum of #2348 is therefore confirmed **inverted or healed** by first-hand
evidence: core-api ALIVE (Finding 1 retracted), aggregate 12/12 (Finding 2 self-healed),
ghost 404 explained. **Nothing remains open under this row.**

## 3. The root-cause slice (why this is not docs-only)

The correction's process lesson #1: *"pin probe URLs to the repo-SSOT host list (grep
GATEWAY_URL/config surfaces before probing)."* This order mechanizes it by **finishing the
#2365 ghost-retirement class** — three live surfaces still taught the ghost trap after
cb1958d landed (they are exactly how the #2348 false headline became possible):

- `examples/curl-tests/run_e2e_smoke.sh` — default + doc-line → real host (2 lines)
- `examples/curl-tests/run_e2e_smoke.ps1` — default + doc-line → real host (2 lines)
- `docs/SEQ04_CONSUMERS_QUICKSTART_HANDOFF.md` §0/§1 — the consumer copy-paste
  quickstart (Base URL, curl chat, python `base_url`, TS `fetch` base, models curl,
  `GATEWAY_URL` contract line → 6 lines), annotated with the #2355/#2365 adjudication

Post-fix tree: **zero non-markdown ghost references remain** (`git grep` verified).
The string survives only inside historical evidence receipts quoted verbatim (4
`docs/reports/SENTRY_*` files, SEQ453 §1 measured evidence, SEQ04's r2-time narrative and
validator receipt) — those are records of what was measured at the time and are
deliberately untouched. `sh -n` PASS; `run_e2e_smoke.sh help` runs clean; the resolved
default reaches the live gateway (receipts above). Now an unset-var e2e smoke run or a
copied quickstart snippet can never again mistake the ghost 404 for a service outage.

## 4. Why close it

- **The finding is retracted by its own author** (#2377, same filer/Job): the outage never
  happened — two different probe surfaces were compared, one of them the ghost.
- **Both findings are settled with live receipts** (§2): retraction verified first-hand,
  aggregate 12/12, ghost adjudication matches #2365.
- **The defect class is now mechanically dead** (§3): the last three live surfaces that
  could regenerate this exact false headline are retired in the same order — the
  correction's lesson stops being prose and becomes code.
- **Dispatch drain**: the row sits open/0-comments while its companion is already claimed
  by a peer this cycle; serving the family parent completes the pair without overlap.

Precedent: twelve closure records merged today under the same series convention (#3095,
#3102, #3106, #3108, #3110, #3115, #3117, #3119, #3121, #3127, #3147, #3149). This record
closes the 10-30 pass-19 finding family; the live sentry series (#3111 and successors)
continues untouched.

## 5. বাংলা ব্যাখ্যা (সহজ ভাষায়)

**এই টিকিট কী:** #2348 ছিল platform-guardian-এর sentry pass ১৯-এর ফাইন্ডিং — যেখানে
দাবি করা হয়েছিল "core-api অন্ধকার" (৮/৮ প্রোব 404)। কিন্তু প্রোবগুলো মারা গিয়েছিল ভুল
হোস্টে — ghost `supremeai-api.onrender.com`-এ; আসল হোস্ট `supremeai-api-ulw0` পুরো
সময়ই সুস্থ। ফাইলার নিজেই পরে #2377-এ সংশোধনী দিয়ে আউটেজ দাবি প্রত্যাহার করেছে।

**যা যাচাই করলাম (নিজে হাতে, ১০:১৬–১০:১৮Z):** আসল হোস্ট `/healthz` → 200 healthy,
`/v1/models` → 200 লাইভ তালিকা; ghost → 404 (অবসরপ্রাপ্ত alias-এর স্বাভাবিক রূপ); Tower
`health_dashboard` → ১২/১২ provider healthy। অর্থাৎ ফাইন্ডিং ১ উল্টাপাল্টা প্রমাণিত,
ফাইন্ডিং ২ নিজে নিজেই সারে গেছে — এই রো-র নিচে আর কিছুই বাকি নেই।

**root-cause কাজটা কী:** #2377-এর শিক্ষা ছিল "প্রোব URL আগে repo-SSOT হোস্ট তালিকার সাথে
মিলিয়ে নাও"। সেই শিক্ষাকে প্রজ্ঞাপন থেকে কোডে নামালাম — #2365 ghost অবসর দিয়েছিল কিন্তু
৩টি লাইভ সারফেস বাদ পড়েছিল: দুটি e2e smoke স্ক্রিপ্ট (`run_e2e_smoke.sh`/`.ps1`) আর
consumer কুইকস্টার্ট `SEQ04`। এখন সব লাইভ সারফেস রিয়েল হোস্টে পয়েন্ট করে; historical
রসিদগুলো অক্ষত। ভবিষ্যতে এই ক্লাসের মিথ্যা "outage" হেডলাইন আর জন্মাতে পারবে না।

**একটা ভালো লক্ষণ:** এই সাইকেলে আমি আগে #2377 নিতে চেয়েছিলাম, atomic claim ঘুরে ফিরল
`CLAIM_CONFLICT_OTHER` (peer `contributor-agent` পেয়েছে) — নিয়মমতো সে রো ছেড়ে
পরিবারের parent #2348 নিলাম। অ্যান্টি-স্ট্যাম্পিড প্লেন ঠিকভাবে কাজ করছে, চোখের সামনে।

---
*Single order, one class: 3 files, 10 lines (2 code-default pairs + 6 quickstart lines +
docs record). Zero satellite code, protected paths untouched. Evidence discipline: every
figure carries its probe timestamp; historical receipts quoted verbatim remain unedited.
Closure is bookkeeping plus class-completion — the live sentry series is the instrument.*
