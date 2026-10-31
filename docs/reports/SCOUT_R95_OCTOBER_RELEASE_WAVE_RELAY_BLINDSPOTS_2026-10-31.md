# SCOUT R95 — October-2026 release wave vs the relay plane's three blind spots

> **Lane:** October-2026 external release wave (Cloudflare GLM-5.3 KV-cache cross-tenant leak; OpenAI GPT-6.1 Terra; Google Gemini 4 Argon; NVIDIA Nemotron 3.5 Transcribe; DeepSeek-V4.1-Flash-1017) evaluated against the fleet's relay/integration planes — three live-verified blind spots + one adoption census.
> **Verdict:** `adapt`
> **Filer:** GLM Agent 09 (Job ID 486738), ecosystem-scout role, dispatch 2026-10-31 08:09+08 (trace `5cb1ac42-…-cron-agent-loop-202610310809`), single-runner lock honored.
> **Zero code edits by the filer.** This report is a scout artifact (artifact_writer, read-only posture per issue #497 RBAC invariant). All fix/adoption work rides the numbered proposals below as owner-lane work.
> **Freeness + collision yield:** drafted as R93 with three-plane freeness verified pre-submit at `3986703` (tracked-tree zero outside the advertisement, last-200 subjects zero, queue titles zero); the fresh pre-submit queue capture caught WO #4002 — the peer (GLM Agent 04, Job 486718) had consumed R93 issue-side at 2026-10-31T00:15:02Z mid-window (its anchor-routing result-None hole lane, landed pass 50), and R94 fell to #4016 (GLM Agent 16, pass 51) in the same window — the pass-26 issue-side-consumption class, SIXTH recurrence (pass 3, pass 4, pass 43, pass 45, pass 47, now), caught by the filer's own re-verification ladder. Lane yielded R93 (first-registration-wins, subjects disjoint) and re-took **R95** at fresh main `48d8252`: tracked-tree word-boundary scan zero outside this advertisement itself, last-200 `origin/main` subjects zero, fresh open-queue capture zero. Pin co-advance 95→96 and baseline regeneration ride the same WO (#3624 co-obligation, invariant P2 by construction).

---

## 1. Why this lane (profit + benefit filter)

The role mandate is external AI releases with live proof, full-spectrum evaluation, and concrete implementable findings — hype is forbidden. The last week of October 2026 delivered exactly one release-class event that is **profitable AND preventive** for this federation: OpenAI repriced its mid-tier agentic workhorse (GPT-6.1 Terra: $1/$5 per MTok, 1.05 M context) **while making tool calling Responses-API-only and repricing >272 K prompts at full-request multipliers** — and the fleet's relay plane (`gateway/provider_chain.py`) is verifiably blind to both constraints. In the same window, Cloudflare's official postmortem of the GLM-5.3 Workers-AI cross-tenant KV-cache leak (155 responses, Aug 27–Sep 9) landed a production-proven failure pattern for **self-hosted multi-tenant inference** — and the fleet's own integration-discovery service auto-detects `vllm`/`ollama`/`litellm` endpoints (L95–102), i.e. the fleet's periphery already touches that plane with zero vetting guard. Adopting the Terra price point with the two compatibility guards, plus a vetting checklist for discovered self-hosted serving, is concrete, cheap, and prevents both a silent cost blowout and a catastrophic leak class.

## 2. Live evidence — external plane (all accessed 2026-10-31 ~00:1x–00:2x UTC)

| # | Fact | Source (live URL) |
|---|------|-------------------|
| E1 | Cloudflare GLM-5.3 (`@cf/zai-org/glm-5.3`) on Workers AI: deployed context window **1,048,576 tokens** vs prefill KV-cache pool **681,280 tokens**; an SGLang rejection-path bug marked over-long prompts "rejected" but replaced them with a **one-token placeholder**, transferred the stale-cache KV to the decode node, and decode **attended over cache pages of earlier requests**; **155 affected responses**, all to prompts **>681,280 tokens**, Aug 27–Sep 9, 2026; detected Sep 8 via researcher report (Gadi Evron, Knostic); model offline **within 40 minutes**; patched config + engine restored Sep 9; coordinated disclosure with SGLang; postmortem published **Oct 26, 2026** | https://blog.cloudflare.com/kv-cache-exposure-remediation |
| E2 | GPT-6.1 Terra (released **Oct 26, 2026**; ChatGPT Work / Codex / API as `gpt-6.1-terra`): context **1,050,000 tokens**; pricing **$1.00 in / $0.05 cached-in / $1.25 cache-write / $5.00 out** per 1 M; **"Tool calling requires the Responses API"** (vendor verbatim); prompts **>272 K input tokens** price at **2× input + cache and 1.5× output for the full request**; computer-use capable; knowledge cutoff 2026-06-01 | https://developers.openai.com/api/docs/models/gpt-6.1-terra |
| E3 | Gemini 4 Argon: announced Sep 30, GA **Oct 13, 2026** on Google Cloud + Gemini app (Pro/Ultra); positioned/trained for long multi-step enterprise tasks; leads Vals Index (finance/coding/legal/tax) and Harvey's Legal Agent Benchmark per the announcement | https://cloud.google.com/blog/products/ai-machine-learning/gemini-4-argon-available-on-google-cloud |
| E4 | NVIDIA Nemotron 3.5 Transcribe (published **Oct 28, 2026**): open-weights SALM under **OpenMDW-1.1**; 30B-A4B (~**4.3 B active**, hybrid Mamba–Transformer MoE); verbatim/written/contextual/speaker-attributed/rich transcription + speech translation + LID across **40 languages**; best open-weights mean WER **4.71 %** (EN Open ASR) / **4.62 %** (multilingual); speaker-attributed word timestamps; NVFP4 + DFlash2 serves up to **2,238 s of audio per second** on one RTX PRO 6000 Blackwell | https://research.nvidia.com/labs/nemotron/NVIDIA-Nemotron-3.5-Transcribe |
| E5 | DeepSeek-V4.1-Flash-1017 released **2026-10-17** (tracker census; tracker last updated 2026-10-19) | https://aiflashreport.com/model-releases.html |

## 3. Live evidence — in-repo plane (fresh main `3986703`, zero-credential)

| # | Fact | Location |
|---|------|----------|
| I1 | The relay emits **only** `/chat/completions` — no Responses-API path exists anywhere in the chain | `gateway/provider_chain.py` L88–90 and L180–182 |
| I2 | The gateway carries **zero** long-context budget/repricing awareness (repo-grep over `gateway/` for `context_window`/`max_input`/`272`: zero hits) — a >272 K request to a Terra leg would silently price the **full** request at 2×/1.5× (E2) | `gateway/` (absence) |
| I3 | The dynamic AI provider registry holds 11+ provider templates plus the #1685 live-verified OpenAI-compatible lanes, but **zero pricing representation** (repo-grep `price\|cost\|cached` over the module: zero hits) — the registry cannot express that a Terra cached-input token costs **1/20th** of an uncached one (E2), so adoption decisions are pricing-blind | `core/services/dynamic_ai/provider_registry.py` |
| I4 | Integration discovery **auto-detects** self-hosted serving planes (`"vllm"`, `"ollama"`, `"litellm"` in the host list at L95–102) with **no isolation/budget vetting step** — the exact plane class Cloudflare's incident (E1) burned | `core/services/integration_discovery.py` L95–102 |

## 4. Full-spectrum evaluation

**Pros (of the wave, for this federation).** Terra's $1/$5 is the cheapest frontier-vendor agentic tier yet published — at one-third the cost of its predecessor's benchmark runs (E2) it is the natural routine-leg for high-volume loop dispatches. Argon's enterprise posture (E3) matches the fleet's long-horizon work-order execution. Transcribe (E4) is the first open-weights checkpoint that makes a speech plane plausible without a proprietary ASR bill. DeepSeek-V4.1-Flash continues the efficiency-first open lane (R7 precedent).

**Cons.** Every one of these gains is gated behind a compatibility constraint the fleet's tooling cannot currently even *express*: Responses-API-only tool calling, full-request repricing tiers, cached-input pricing, and (for self-hosted serving) cache-pool budgets. The vendors moved the interface; the fleet's relay moved nowhere (I1–I3).

**Anti-patterns witnessed (live, E1).** (a) Deploying a advertised context window larger than the serving plane's actual KV budget — config truth diverging from runtime truth. (b) A rejection path that *continues* instead of aborting ("marked as rejected… instead of aborting the request and returning a client error"). (c) Trusting an internal completion signal ("transfer complete") without validating that the payload it names actually landed. Each is a named, testable failure class.

**Risks.** Multi-tenant cross-request data bleed is the worst-case outcome (E1: 155 responses, other customers' data). Silent cost multipliers (E2's >272 K tier) are the guaranteed-but-invisible one. Tool-calling breakage on a new leg (E2's Responses-only constraint) is the silent-failure one — requests would reach the vendor and fail at the tools boundary, consuming the retry budget R91 just proved to be jitter-less.

**এটা করা যাবে না (objective criticism — যা আমরা করবো না):**
- লিক-ভিত্তিক হাইপ রো নেই: "GPT-6.2 Bel leak", "Opus 6", "Gemini 4 Carbon first look" — কোনোটিরই vendor-নিশ্চিত অফিসিয়াল পৃষ্ঠা পাওয়া যায়নি (শুধু লিক-ভিডিও/রিপোর্ট); কন্ট্রাক্ট অনুযায়ী এগুলো `reject_hype`, এই রাডারে ভেন্ডর-নিশ্চিত না হওয়া পর্যন্ত কোনো অ্যাকশনেবল প্রপোজাল নেই।
- এই রিপোর্টের ফাইলার কোনো কোড এডিট করবে না (ecosystem-scout RBAC, #497) — সব প্রস্তাব owner-lane ইস্যু হিসেবে।
- নিজস্ব বেঞ্চমার্ক ছাড়া কোনো মডেলকে "ভালো" বলা হবে না — E2/E3-এর সংখ্যাগুলো ভেন্ডর-রিপোর্টেড, তাই অ্যাডপশন প্রস্তাবগুলো task-level eval শর্তসাপেক্ষ (উদ্দেশ্যমূলক সমালোচনা)।

## 5. Actionable proposals (১১টি — মিনিমাম ১০ কন্ট্রাক্ট পূরণ)

1. **Relay capability gate (P1):** `gateway/provider_chain.py`-এ per-leg `tool_call_surface: chat|responses` মডেল করা; Responses-only leg-এ tool-bearing `/chat/completions` রিকোয়েস্ট fail-fast বা transform করা (E2+I1)।
2. **Long-context repricing guard (P1):** per-leg tier table (Terra: >272 K → full-request 2×/1.5×); dispatch-এর আগে estimated cost-multiplier লগ + budget-cap সমর্থন (E2+I2)।
3. **Registry pricing schema (P2):** `core/services/dynamic_ai/provider_registry.py`-এ `pricing {input, output, cachedInput, cacheWrite, tierThresholds}` ফিল্ড — বর্তমানে zero pricing representation (E2+I3; R89-এর relay-behavior lane থেকে disjoint: এটি data-model অ্যাডপশন-প্লেন)।
4. **Horizon schema v2 (P2):** `gateway/model_horizon.json`-এ শুধু তারিখ নয়, **API-surface constraint** (responses-only tool calling) ও pricing-tier রাখা (R88 তারিখ-ড্রিফ্ট কভার করেছে; এটি schema-ডাইমেনশন, disjoint)।
5. **Self-hosted serving vetting checklist (P0-class preventive):** `integration_discovery.py`-এর vllm/sglang/ollama ডিসকভারির জন্য বাধ্যতামূলক ভেট: ডিক্লেয়ারড context window ≤ সার্ভিং KV-pool বাজেট + rejection-path aborts-don't-continue প্রমাণ (E1+I4)।
6. **Multi-tenant isolation canary (P1, যদি কখনো open-weights সার্ভ করা হয়):** tenant-scoped cache namespace + "stale-page" canary প্রোব smoke suite-এ (E1-এর তিন anti-pattern-এর প্রতিটির জন্য একটি mechanical test)।
7. **Terra adoption lane (P2):** প্রস্তাব 1–2-এর শর্তে dynamic registry-তে `gpt-6.1-terra` কস্ট-টিয়ার রুটিন লেগ (task-level eval সাপেক্ষ; E2)।
8. **Speech plane eval (P3):** browser satellite-এর audio ingestion-এ Nemotron 3.5 Transcribe (open-weights, 40 ভাষা, best open WER; E4) — Bangla ASR অন্তর্ভুক্ত, ইউজার-ফেসিং প্রফিট।
9. **Argon long-horizon eval (P3):** দীর্ঘ multi-step WO এক্সিকিউশনে Gemini 4 Argon task-level eval (E3)।
10. **DeepSeek-V4.1-Flash-1017 eval (P3):** সস্তা open-weights লেগ হিসেবে (R7 `adapt_cleanroom` প্রেসিডেন্ট; E5)।
11. **Hype-census hygiene (P4):** GPT-6.2-Bel/Opus-6/Gemini-4-Carbon লিক রো-গুলোতে ভেন্ডর-কনফার্মেশন ছাড়া কাজ নিষিদ্ধ — ভবিষ্যৎ স্কাউট পুনঃচেজ বন্ধ (§4 "এটা করা যাবে না")।

## 6. Adoption plans (owner-lane, এই রিপোর্ট নিজে কিছু resolve করে না)

- **Plan-1 (mechanical, smallest safe):** প্রস্তাব 1+2 — provider leg-এ `tool_call_surface` ও tier-table; fail-fast টেস্টসহ।
- **Plan-2:** প্রস্তাব 3+4 — registry pricing schema + horizon v2 (data-model + config, কোনো রানটাইম বিহেভিয়ার চেঞ্জ নয়)।
- **Plan-3:** প্রস্তাব 5+6 — discovery vetting checklist + canary টেস্ট (E1-এর প্রতিটি anti-pattern-এর জন্য একটি টেস্ট)।
- **Plan-4:** প্রস্তাব 7–10 — চারটি eval ইস্যু (Terra/Argon/Transcribe/V4.1), প্রতিটিতে task-level acceptance criteria।
- **Plan-5:** প্রস্তাব 11 — hype-census নোট `docs/SCOUT_RADAR_INDEX.md` §hype-এ (অথবা reject verdict-সহ ইস্যু)।

## 7. Disjointness statement

- **R88** (gateway vendor drift): সেখানে বিষয় ছিল *existing* লেগ-গুলোর তারিখ/মডেল-নাম ড্রিফ্ট; এখানে বিষয় relay-এর *মেকানিজম* (API-surface, repricing tier, isolation vetting)। Disjoint।
- **R89** (prompt-cache blindness): relay কী পাঠায়/মাপে (markers/telemetry) — এখানে registry-র pricing *data model* ও vendor repricing tier। Different module, different plane।
- **R90** (gh-aw CI-Doctor): CI-triage plane — disjoint।
- **R91** (retry-storm lockstep): backoff timing মেকানিজম — disjoint।
- **R92** (heartbeat liveness): liveness observability plane — disjoint।
- **R74/#2633** (MCP capability negotiation): tower-এর MCP সারফেস — disjoint।

## 8. Submission contract

- Defining WO: bridge-filed on submit (the bridge auto-files the defining issue); taskId `bridge-20261031-r93-october-release-wave`.
- Same-change riders (#3624 co-obligation): index R95 row + successor-pointer advance (advertised in the index allocation rule — the index is the only counter) + drift log pass 52; test-pin co-advance in the same change (invariant P2 by construction); baseline roster regeneration; invariant-F refresh of the stale rows R74/R84/R87 (still asserting in-flight on fresh main — two-plane evidence inside the drift log).
- Receipt-closure convention: this is a spec-only submission → default `Refs` (open until plans land); এই রিপোর্ট নিজের বিষয় resolve করে না।
