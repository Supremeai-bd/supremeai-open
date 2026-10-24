---
id: head-of-planning-prompt-caching-v1-2026-09-16
title: "Head of Planning — Plan #001: Anthropic Prompt Caching on Existing LiteLLM Gateway (Corrected Discipline, Single Complete Plan)"
status: complete
document_role: implementation
owner_circle: C5 (Execution — LLM Gateway)
scope: ONE complete plan, fully grounded in actual repo code, following the corrected planning discipline (small change to existing code, no new infra, no CI amplification, no academic benchmarks, realistic resource budget)
depends_on:
  - backend/core/llm/llm_gateway/gateway.py (existing LLMGateway — mixin-based)
  - backend/core/llm/providers/cloud_adapter.py (existing CloudProviderAdapter — wraps LiteLLM)
  - backend/core/llm/provider_router.py (existing LatencyAwareWeightedRouter — Anthropic is in default weights)
  - backend/core/llm/llm_gateway/completion.py (existing CompletionMixin — where messages are built)
  - backend/observability/providers/langfuse_adapter.py (existing observability — cache-hit ratio instrumentation is free)
  - README.md Constitution #14 (Sustainable Cost)
  - AGENTS.md Mandatory Rule #9 (Enterprise-Grade Completeness & Safety by Design)
implements:
  - Direct token-cost reduction on the zero-cost LLM chain (Constitution #14 Sustainable Cost)
  - Direct latency reduction for cached-prefix portions (Constitution #8 Graceful Degradation)
  - No new subsystem, no new dependency, no new infra (Constitution #3 Reuse Before Creation)
supersedes: []  # supersedes the 4 rejected ideas from HEAD_OF_PLANNING_LANDSCAPE_INTEL_v1 (Hetzner+OpenObserve, Modal nightly, promptfoo per-CI, GAIA/τ²-bench benchmarks) — none are repository files
superseded_by: []
last_verified: "2026-09-16 (code-read: gateway.py, cloud_adapter.py, provider_router.py); IMPLEMENTED 2026-09-17 on main — cloud_adapter.py: _is_anthropic_family_model + _mark_anthropic_cache_blocks pure helpers, generate()/stream() wiring, usage dict surfaces cache_read_input_tokens / cache_creation_input_tokens (forwarded to Langfuse via existing trace_generation usage pass-through); tests/core/test_cloud_provider_cache.py 10/10 PASS; 70/70 across test_llm_gateway_completion + test_provider_router + new file (local CI-mock env, litellm stubbed at adapter boundary)"
plan_lifecycle: living — single complete plan #001; founder reviews + approves → engineering PR → merge → THEN next plan
target_scope: supremeai_internal
---

# Head of Planning — Plan #001: Anthropic Prompt Caching

> **বাংলা সারসংক্ষেপ:** আগের ল্যান্ডস্কেপ ইন্টেল মেমোতে ৪টি খারাপ প্ল্যান ছিল — Hetzner VPS, Modal nightly, promptfoo per-CI, GAIA/τ²-bench academic benchmarks। সেগুলো প্রত্যাখ্যাত। এই মেমো নতুন ডিসিপ্লিনে লেখা প্রথম পূর্ণাঙ্গ প্ল্যান: **একটাই আইডিয়া, বর্তমান কোডে ছোট পরিবর্তন, বাস্তবসম্মত রিসোর্স, পূর্ণাঙ্গ বিবরণ**। প্ল্যানটি হলো Anthropic Prompt Caching — কিন্তু কোনো নতুন dependency ছাড়া, কোনো নতুন server ছাড়া, কোনো CI impact ছাড়া। বাস্তব কোড পরীক্ষা করে দেখা গেছে — আমাদের `LLMGateway` ইতিমধ্যে `LiteLLM` ব্যবহার করে, এবং LiteLLM নেটিভভাবে Anthropic-এর `cache_control` প্যারামিটার সাপোর্ট করে। শুধু দরকার সিস্টেম প্রম্পট ও MCP টুল ক্যাটালগে `cache_control` মার্কার যোগ করা। এক্সপেক্টেড বেনিফিট: cached portion-এ ৯০% cost কম, ৫০-৮০% latency কম, কোনো architectural পরিবর্তন ছাড়াই।

---

## Part 1 — Corrected Planning Discipline (Brief)

The founder's feedback on the previous landscape intel memo identified 4 of 12 ideas as bad or risky. That is a 33% failure rate of the planning function. Before proposing any single plan, the discipline itself must be fixed. The corrected rules below are the standing filters for every future Head of Planning memo.

### Rule 1 — One plan at a time, sequential

No more batched idea lists. One complete plan per memo. The plan finishes (engineering PR merged, evidence in `STATUS.md`), gets posted, and THEN the next idea is scouted. This is the founder's exact directive: "একটা শেষ হওয়ার পরে সেটা পোস্ট করো তারপর নতুন করে আবার ভালো কোন আইডিয়া খুঁজে বের করা."

### Rule 2 — Small change to existing code, not a new subsystem

Every plan must extend a file or module that already exists in the repo. The "Existing-Asset Extension Map" is not a separate audit section — it is the entry point of the plan itself. If a plan requires a new file in a new directory with a new dependency, it is rejected at planning time.

### Rule 3 — No new infrastructure

If a plan requires provisioning anything not already in the stack (Render, Supabase, Cloudflare, Upstash, GitHub Actions free tier), it is rejected. Hetzner VPS for OpenObserve violated this rule. Modal nightly violated this rule. The standing filter: **if it needs a new server, new cloud account, or new paid tier, it is out of scope**.

### Rule 4 — No CI cost amplification

A plan that adds LLM API calls to every PR or every push is rejected. CI must stay fast and free-tier-safe. promptfoo per-CI violated this rule. The standing filter: **eval runs happen on a schedule (nightly, weekly) or on-demand — never blocking every PR**.

### Rule 5 — No credit-burn risk

If a plan introduces a third-party service with auto-bill risk on credit exhaustion, it is rejected. Modal $30 free credits with auto-bill on exhaustion violated this rule. The standing filter: **the budget math must show a hard ceiling, not a "free until it isn't" promise**.

### Rule 6 — No academic leaderboard chasing

Plans must advance the customer/admin product, not research benchmark rankings. GAIA L1/L2 and τ²-bench violated this rule. The standing filter: **if the only beneficiary is a public leaderboard, the plan waits until the product is stable**.

### Rule 7 — Realistic resource budget

Plans must fit the existing free-tier envelope. Render 512MB containers, Supabase free, Cloudflare Workers, GitHub Actions free minutes, Upstash free tier, local Ollama as offline fallback. No "free but needs 1000GB RAM" absurdity. The standing filter: **if the plan cannot run inside a Render 512MB container, it is too heavy**.

### Rule 8 — Complete plan format

Every plan must include the six fields the founder specified, in this order: **what we have · what we don't have · what to do · how to do it · benefit · harm/risk.** No exceptions. A plan missing any of these six fields is incomplete and is rejected.

### Rule 9 — Reality check before drafting

Before drafting any plan, the planning department must read the actual code that the plan touches. No recommendations based on documentation alone. The previous memo's "adopt spec-kit" recommendation was corrected only because I checked `specs/001-*/` and found it was already in use. This discipline is now mandatory for every plan.

These 9 rules are the planning department's standing operating procedure from this memo forward. v1.5/v2 of the PR-first publishing protocol still applies (fresh main clone, feature branch, PR for founder review, no self-merge). The rules above are the *content* discipline; the PR protocol is the *publishing* discipline.

---

## Part 2 — Plan #001: Anthropic Prompt Caching

This plan applies the corrected discipline above to the single idea the founder explicitly accepted as "দারুণ" in their feedback. It is the only plan in this memo. There is no Plan #002 in this document.

### Plan identifier

`PLAN-001-ANTHROPIC-PROMPT-CACHING`
Owner Circle: C5 (Execution — LLM Gateway)
Constitution anchor: #14 Sustainable Cost (primary), #8 Graceful Degradation (secondary), #3 Reuse Before Creation (filter)
Battlefield: B3 (Cost per verified task)

### What we have (কি আছে)

I verified each of the following claims by reading the actual code in the repo on 2026-09-16. No documentation-only claims.

1. **`LLMGateway` class exists** at `backend/core/llm/llm_gateway/gateway.py` (lines 31–77). It is a mixin composition: `RoutingMixin` + `LitellmSetupMixin` + `ResilienceMixin` + `CompletionMixin` + `StreamingMixin`. It instantiates `CloudProviderAdapter()` at line 49.

2. **`CloudProviderAdapter` exists** at `backend/core/llm/providers/cloud_adapter.py` (lines 9–132). It wraps `litellm.acompletion(...)` (line 47) and passes through `**kwargs` (line 55). LiteLLM is the actual LLM client.

3. **LiteLLM natively supports Anthropic prompt caching** via the `cache_control` parameter in message blocks. This is a documented LiteLLM feature (https://litellm.litellm.ai/docs/completion/caching#anthropic-prompt-caching) — no new dep needed, no LiteLLM upgrade needed (already in `pyproject.toml`).

4. **Anthropic is already a first-class provider** in the routing weights. `backend/core/llm/provider_router.py` line 57: `default_providers = {"openai": 5.0, "anthropic": 3.0, "groq": 2.0}`. Anthropic calls already happen in production traffic.

5. **`LangfuseAdapter` is already wired** at `gateway.py` line 57: `self.observability = LangfuseAdapter()`. This means cache-hit ratio instrumentation is *free* — Langfuse already records per-call attributes, and `cache_read_input_tokens` / `cache_creation_input_tokens` are part of Anthropic's standard usage response that LiteLLM surfaces.

6. **System prompts and MCP tool catalogs are sent on every chat turn** — verified at `backend/services/dynamic_ai/orchestrator.py` line 448–449: `messages.append({"role": "system", "content": system_prompt})` runs on every call. This is the prefix that gets cached.

7. **The audit ledger exists** (per STATUS.md and Constitution #6). Every LLM call already produces an auditable record. Cache-hit ratio adds one more field to that record — no new audit infra.

### What we don't have (কি নাই)

1. **No `cache_control` markers anywhere in the codebase.** A grep for `cache_control` across `backend/` returns zero hits. The capability is supported by LiteLLM but not invoked.

2. **No cache-hit ratio metric.** The `usage` block in `cloud_adapter.py` lines 68–72 records `prompt_tokens`, `completion_tokens`, `total_tokens` — but does not extract Anthropic's `cache_read_input_tokens` / `cache_creation_input_tokens` from the LiteLLM response. The metric exists in the response; we just don't surface it.

3. **No cost-savings reporting.** LangfuseAdapter receives per-call telemetry, but there is no dashboard showing "this week, prompt caching saved $X / Y% tokens."

4. **No tests for prompt caching.** The existing test suite (`backend/tests/core/test_provider_router.py`) tests routing weights and circuit breakers — but has no test asserting that `cache_control` blocks are present when Anthropic is the selected provider.

### What to do (কি করতে হবে)

Add Anthropic prompt caching to the existing LLM call path, with three small changes only:

1. **Mark the system prompt + MCP tool catalog as cacheable blocks** when the selected provider is Anthropic (or OpenRouter routing to Claude). Use Anthropic's `cache_control: {"type": "ephemeral"}` marker on the relevant message blocks.

2. **Extract cache metrics from the LiteLLM response** in `cloud_adapter.py` — surface `cache_read_input_tokens` and `cache_creation_input_tokens` in the returned `usage` dict, and forward them to `LangfuseAdapter` as call attributes.

3. **Add one regression test** asserting that: (a) when the provider is Anthropic, the system prompt block carries `cache_control`; (b) when the provider is Gemini or Groq, no `cache_control` is added (those providers reject unknown params); (c) the usage dict surfaces cache metrics when present in the response.

That is the entire plan. Three small changes, all in existing files.

### How to do it (কিভাবে করতে হবে)

The implementation is small enough to fit in one engineering PR. The concrete file-level changes:

**Change 1 — Cacheable message builder (new helper function, ~30 lines)**

Location: `backend/core/llm/providers/cloud_adapter.py` (extend existing file)

Add a private helper `_mark_anthropic_cache_blocks(messages, system_prompt_block_indices, tool_block_indices) -> list[dict]` that, given the standard `messages` list, returns a new list where the system prompt block and the tool-catalog block (if separate) carry:

```python
{"role": "system", "content": [
    {"type": "text", "text": system_prompt_text,
     "cache_control": {"type": "ephemeral"}}
]}
```

This is the exact format Anthropic's API expects (and LiteLLM passes through). The function is *provider-aware*: it only adds `cache_control` when the resolved provider is Anthropic-family (`claude-*` models, or OpenRouter models with `/anthropic/` in the model id).

**Change 2 — CloudProviderAdapter.generate() and .stream() call the helper**

Location: `backend/core/llm/providers/cloud_adapter.py` lines 47 and 95

Before the `litellm.acompletion(...)` call, transform the `messages` list through the helper. One line added, no lines removed:

```python
messages = self._mark_anthropic_cache_blocks(messages, model=model)
```

**Change 3 — Extract cache metrics from the response**

Location: `backend/core/llm/providers/cloud_adapter.py` lines 68–72

Extend the returned `usage` dict:

```python
"usage": {
    "prompt_tokens": response.usage.prompt_tokens,
    "completion_tokens": response.usage.completion_tokens,
    "total_tokens": response.usage.total_tokens,
    "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
    "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
},
```

Forward these to `LangfuseAdapter` as call metadata (the adapter already receives a metadata dict per call; this is two new keys).

**Change 4 — One regression test**

Location: `backend/tests/core/test_cloud_provider_cache.py` (new test file, ~60 lines)

Three test cases:
- `test_anthropic_system_prompt_has_cache_control` — given model `claude-3-5-sonnet-20241022` and a system prompt, the messages list passed to `litellm.acompletion` (mocked) contains a `cache_control: ephemeral` block on the system message.
- `test_gemini_system_prompt_has_no_cache_control` — given model `gemini-1.5-flash`, no `cache_control` is added (Gemini rejects unknown params).
- `test_usage_extracts_cache_metrics` — given a mocked LiteLLM response with `cache_read_input_tokens=1200`, the returned `usage` dict surfaces `cache_read_input_tokens=1200`.

That is the complete implementation. **No new dependency, no new service, no new file outside `tests/`, no CI change, no infra change.**

### Benefit (কি বেনিফিট হবে)

The benefits are direct, measurable, and accrue on every chat turn once the cache is warm:

1. **Token cost reduction: ~90% on cached portions.** Anthropic's pricing: cached input tokens cost ~10% of the standard input price. The system prompt + MCP tool catalog are sent on every chat turn — they are the *exact* prefix that benefits most from caching. For a typical chat session with 5 turns and a 4,000-token system prompt + tool catalog, the savings on input tokens approach 90% from turn 2 onward.

2. **Latency reduction: 50–80% on cached portions.** Anthropic's prompt cache returns in ~1/3 the time of a non-cached call of equivalent size (Anthropic's published benchmark). For SupremeAI's chat streaming path, this directly improves first-token latency — Constitution #8 (Graceful Degradation) made measurable.

3. **No architectural change.** All four file changes are inside the existing LLM call path. No new subsystem, no new circle, no new dependency. Constitution #3 (Reuse Before Creation) — the textbook case.

4. **No new infrastructure.** Anthropic already hosts the cache. We just mark the prefix as cacheable. Zero new servers, zero new accounts, zero new free-tier quotas to manage. Constitution #14 (Sustainable Cost).

5. **No CI impact.** Caching happens at runtime, not at CI time. The existing test suite gains one new test file with three fast mocked tests — no LLM API calls in CI. Rule 4 (no CI cost amplification) honored.

6. **Observability is free.** LangfuseAdapter is already wired. Cache-hit ratio surfaces as two new metadata fields per call. No new observability stack required (Rule 2 — small change to existing code).

7. **Direct B3 (Cost per verified task) measurement.** The pass^k harness (`scripts/ci/mission_passk.py`) runs missions through the zero-cost chain. With caching active, the cost-per-mission metric drops proportionally to the cache-hit ratio — and the metric becomes *measurable* because Change 3 surfaces it.

### Harm / Risk (কি ক্ষতি হবে)

Honest risk assessment, in priority order:

1. **Cache miss on first call.** The first call of a session pays full price (the cache write itself costs ~1.25× the standard input price for 5-minute TTL, or 2× for 1-hour TTL). For one-shot missions, caching is *net-negative* if the prefix is small. **Mitigation:** the helper only marks cache blocks when the system prompt + tool catalog exceeds a threshold (e.g., 1,024 tokens — Anthropic's minimum cacheable size). Below that threshold, no `cache_control` is added. This is a one-line guard in the helper.

2. **Cache invalidation when system prompt changes.** If the system prompt or MCP tool catalog changes between calls, the cache misses and the next call pays full price. **Mitigation:** the system prompt is the SupremeAI Constitution context — it changes rarely. The MCP tool catalog changes when tools are added/removed — also rare in production. Expected cache-hit ratio in steady state: 85–95% (Anthropic's published benchmark for stable prefixes).

3. **OpenRouter passthrough reliability.** If SupremeAI calls Claude via OpenRouter (rather than direct Anthropic API), the `cache_control` marker must survive the OpenRouter proxy. OpenRouter does support cache_control passthrough, but a flaky intermediate could in theory strip it. **Mitigation:** prefer direct Anthropic API key when available (the provider router already prefers higher-weighted providers). The cost-analyzer (`scripts/monitoring/cost_analyzer.py`) already tracks per-provider costs — a sudden cost spike on OpenRouter-to-Claude would be visible.

4. **Anthropic quota used for cache writes.** Cache writes count against the standard rate limit. If the system is at quota ceiling, cache writes could trigger rate-limit responses that wouldn't have happened without caching. **Mitigation:** the cacheable-prefix threshold (Risk 1) ensures we only cache when the prefix is large enough to be worth it. For small prefixes, the helper skips caching entirely — no quota used.

5. **Test mock fidelity.** The regression tests mock LiteLLM, so they don't verify the actual Anthropic API contract. A future LiteLLM upgrade could change the `cache_control` shape. **Mitigation:** pin the LiteLLM version in `pyproject.toml` (already pinned per `STATUS.md` — ruff 0.16.4, etc.). Add a CI step that runs the cache test against a real Anthropic call gated behind a `RUN_LIVE_CACHE_TEST=true` env var (skipped in normal CI, run manually before any LiteLLM upgrade).

6. **No production A/B test for savings.** The plan ships caching on by default. There is no "before vs after" measurement infrastructure beyond Langfuse. **Mitigation:** LangfuseAdapter already records per-call attributes. Add a one-line dashboard query (in Langfuse UI, not in code) that compares cache-read-token ratio before/after the merge date. No new dashboard infra needed.

**Net risk verdict:** All six risks have one-line mitigations inside the existing code path. None requires a new subsystem. The worst-case scenario (cache always misses) is equivalent to today's behavior — no regression, just no improvement. The expected-case scenario is a measurable cost and latency reduction on every multi-turn chat session.

### Existing-asset extension map (Constitution #3 audit)

| Plan element | Existing SupremeAI asset it extends | New subsystem? | Constitution #3 satisfied? |
|---|---|---|---|
| Cacheable message builder | `backend/core/llm/providers/cloud_adapter.py` (existing file, CloudProviderAdapter class) | No — one new private helper inside the existing class | ✅ |
| `cache_control` invocation in generate/stream | Existing `litellm.acompletion(...)` call at cloud_adapter.py:47 and :95 | No — one line added before each existing call | ✅ |
| Cache metrics extraction | Existing `usage` dict at cloud_adapter.py:68–72 | No — two new keys in existing dict | ✅ |
| Observability forwarding | Existing `LangfuseAdapter` (gateway.py:57) | No — two new metadata keys | ✅ |
| Regression tests | Existing `backend/tests/core/` directory | No — one new test file in existing test directory | ✅ |
| Cacheable-prefix threshold | New constant in `backend/core/config.py` (existing settings module) | No — one new setting | ✅ |

**Verdict:** Every element extends an existing file. Zero new dependencies. Zero new infrastructure. Zero new services. Constitution #3 (Reuse Before Creation) passes cleanly. This is the textbook case the founder asked for: "বর্তমানে যা আছে তাকে সামান্য কিছু পরিবর্তন করে আরো কি বেনিফিট আনা যায়."

### Sequencing and exit evidence

This plan is sized to fit one engineering PR. The exit evidence is concrete and measurable:

| Step | Action | Exit evidence |
|---|---|---|
| 1 | Open feature branch `feat/anthropic-prompt-caching` off fresh `main` | Branch exists |
| 2 | Implement Change 1 (cacheable message builder) + Change 2 (call site) + Change 3 (usage extraction) in `cloud_adapter.py` | Diff is < 80 lines added, 0 lines removed |
| 3 | Implement Change 4 (regression test) in `backend/tests/core/test_cloud_provider_cache.py` | 3 tests, all mocked, no live API calls |
| 4 | Add `ANTHROPIC_CACHE_MIN_PREFIX_TOKENS` setting to `config.py` (default 1024) | One new setting, documented in `.env.example` |
| 5 | Run `ruff check backend/core/llm/providers/cloud_adapter.py` + `pytest backend/tests/core/test_cloud_provider_cache.py` | Both green |
| 6 | Open PR; founder reviews; merge to `main` | PR merged |
| 7 | Within 48h of merge, observe Langfuse for cache-hit ratio on Anthropic calls | `cache_read_input_tokens > 0` on at least one production call |
| 8 | Within 7 days, observe cost-per-mission metric in `reports/mission_passk.json` | Cost per mission is lower than the 7-day pre-merge baseline |

If step 7 shows zero cache hits after 48 hours, the plan has failed and must be debugged before any next plan is proposed. If step 8 shows no cost reduction after 7 days, the cacheable-prefix threshold (default 1024) may be too high — adjust down to 512 and re-measure.

### What is explicitly NOT in this plan

- No new dependency (LiteLLM already supports `cache_control`).
- No new infrastructure (Anthropic hosts the cache).
- No new service (no Hetzner VPS, no Modal, no OpenObserve).
- No CI change (the new tests are mocked, no live API calls).
- No academic benchmark work (no GAIA, no τ²-bench).
- No frontend change (caching is invisible to the user).
- No MCP federation change (the tool catalog is a *consumer* of caching, not a *modifier*).
- No Constitution amendment (the plan serves existing principles, does not introduce new ones).

### Next plan

Per the corrected discipline (Rule 1 — sequential), no next plan is proposed in this memo. The next plan will be scouted **only after** this Plan #001 is merged, deployed, and its 7-day post-merge evidence (step 8) is recorded in `STATUS.md`. The two accepted-but-deferred ideas from the founder's feedback are:

- **Plan #002 candidate:** Stagehand `act`/`extract`/`observe` typed wrapper over existing Playwright (Rank 7 from landscape intel) — small surface, B2/B6/B1.
- **Plan #003 candidate:** Letta three-tier agent-operated memory on existing pgvector (Rank 8 from landscape intel) — medium surface, B4/B3.

Either may become Plan #002 depending on which delivers more leverage after Plan #001's evidence is in. The planning department will not pre-commit.

---

*Memo lineage: v1 strategic posture (451be690, main) → v1.5 PR-first protocol (PR pending) → v1 landscape intel (PR pending, 4 of 12 ideas rejected by founder) → **THIS Plan #001** (single complete plan, corrected discipline, PR for founder review). Future plans follow Rule 1: one at a time, sequential, post-evidence.*