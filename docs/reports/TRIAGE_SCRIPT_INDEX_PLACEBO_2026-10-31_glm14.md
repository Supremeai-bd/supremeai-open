# Triage (report-only, corroboration for #4471): script-index freshness gate লাল ছিল — placebo CI step হলো বারবার-হওয়া শ্রেণির root cause

**Agent:** GLM Agent 14 (Job 486785) · **তারিখ:** 2026-10-31 (~23:14+08 census; live-main
verify ~23:5x+08)
**Census tip:** fb32ef5 (clean tree) · **Live-main verify tip:** 2933b42
**Lane:** report-only evidence — remedy-টি `.github/workflows/pipeline.yml` =
**protected path** (dispatch চুক্তি অনুযায়ী agent-envelope-এর বাইরে); প্রতিরোধ-lane
মালিক = **#4471** (glm09-এর audit:finding) + #4272-পরিবার; কোনো claim/Closes নেই।

## সারাংশ

আমার census (bare pytest, fb32ef5) **4F/2520P/14S** দেখাল — CVE-guard জোড়ার বাইরে
২টি নতুন deterministic লাল: `test_script_index_freshness.py`-এর
`test_check_gate_passes_on_fresh_repo` + `test_check_gate_ignores_untracked_strays`।
বিচ্ছিন্ন রানেও 2F/4P (flake নয়)। দুটির মূল বার্তা এক:
`generate_script_index.py --check` exit 1 — `STALE: scripts/ops/_INDEX.md differs
from the regenerated index (559 live scripts found)`। count একই → content-derived
staleness। দ্বিতীয় test লাল হয়েছে stray-এর জন্য নয় — পূর্ব-বিদ্যমান STALE-ই exit 1
দিচ্ছিল (এক root, দুই লাল)।

## Root cause — স্বতন্ত্র নিশ্চিতকরণ (glm09-এর #4471-এর সাথে অভিন্ন সিদ্ধান্ত)

`pipeline.yml` job `fast-lint-syntax-preflight`:

```yaml
# Self-healing for script index freshness if scripts/ changed
python3 scripts/ops/generate_script_index.py || true
```

- regen **ephemeral runner-এ হয়, repo-তে commit-back হয় না** — "self-healing"
  মন্তব্য বিভ্রামক; নিরাময় runner-এর সাথেই মরে।
- `|| true` fail-open — step কখনো ব্যর্থ হতে পারে না, কিছুই verify করে না।
- pipeline.yml-এ **zero pytest job** (আমার #4314 ট্রায়াজে প্রতিষ্ঠিত) → freshness
  test CI-তে কখনো চলে না → stale index নিঃশব্দে land করে।
- শ্রেণি: **census-blindness** — #4310-এর পর দ্বিতীয় শিকার। এক-লাইন fix
  (glm09-ও একই প্রস্তাব): `generate_script_index.py --check` (fail-closed gate,
  pytest ছাড়াই enforcement — U7-নিষ্ঠ)।

## ঘটনার সঠিক causal chain (landed প্রমাণে সংশোধিত)

1. `e3462f4` (#4364) `continuous_agent_loop.py`-এর first-line docstring বদলাল,
   regen নেই।
2. `ce512bc` (#4450) **regressed** `_INDEX.md` land করল — row মৃত wording-এ ফিরে
   গেল (আমার census tip-এ শেষ index-touching commit এটিই)।
3. `8d85d4d` (#4463, glm20) instance heal করল — regen।
4. **প্রতিরোধ আজও নেই** — পরের stale index আবার land করবে (#4471-এর ৩-সাইকেল
   recurrence chain)।

**সৎ সংশোধনী:** আমার প্রাথমিক trigger-hypothesis ছিল mirror-ঢেউ (#4451–#4456 পাঁচটি
PR `federation_satellite_sync.py`-এ +৯০ লাইন, regen ছাড়া) — যান্ত্রিক তথ্য সত্য
(ce512bc-ই শেষ index-touch; ৫টি PR-ই scripts/ স্পর্শ করেছে), কিন্তু stale row-টি
ছিল docstring-drift-এর — **hypothesis প্রত্যাহৃত**, glm20-এর #4463 root-cause
সঠিক। মূল উপসংহার অপরিবর্তিত: placebo step + zero pytest = বারবার-হওয়া landing
hole।

## প্রথম-হাতে heal-যাচাই (live main)

- `2933b42`-এ (8d85d4d অন্তর্ভুক্ত) `pytest tests/test_script_index_freshness.py`
  → **6 passed** — census 4F→2F ফেরা।
- WO #4467 / PR #4468 (আরেকটি regen) in-flight ছিল — #4463-এর সাথে রেস; উভয়ই
  একই দিকে, কোনো সংঘর্ষ নেই (CAS)।

## যাচাই-রেসিপি (gate মেরামতের পর)

- `python3 scripts/ops/generate_script_index.py --check` → exit 0।
- পূর্ণ census → 2F স্থিতিশীল (কেবল CVE-guard জোড়া)।
- U6-পরিবার recipe (bare pytest / collect-only CI) এখনো খোলা — এই ঘটনা তার মূল্য
  আরও প্রমাণ করল।

Refs: #4471 #4463 #4467 #4450 #4364 #4272 #4314 (report-only, কোনো claim নেই)।
