# SupremeAI Open — প্রকল্প অবস্থা, ত্রুটি ও উন্নতি পরিকল্পনা (বাংলা)

> তারিখ: 2026-10-21  
> রিপোজিটরি: `F:\supremeai-open` (branch: `fix/studio-guest-chat-retry`, HEAD `b231bf89`)  
> স্কোপ: সম্পূর্ণ কোডবেস (core, gateway, browser, command, studio, vscode, sdk, infra, scripts, tests, docs) + `.env` API key ব্যবহার যাচাই  
> উদ্দেশ্য: পরিকল্পনা অনুযায়ী কী কাজ করছে না, কী ঠিক করতে হবে, কীভাবে উন্নতি করতে হবে — সব এক জায়গায়

---

## ১. সারসংক্ষেপ (Executive Summary)

- **টেস্ট অবস্থা:** রুট pytest ৮৯৯ passed, ১ skipped; gateway/infra/sdk/vscode টেস্ট পাস; MCP tower typecheck পাস।
- **লিন্ট অবস্থা:** `ruff` ২০৪ errors (১১৯ auto-fixable) — আগের ৯৬৮ থেকে উল্লেখযোগ্য উন্নতি।
- **TypeScript:** vscode `tsc` পাস; MCP tower `tsc --noEmit` পাস।
- **Python compile:** সব ১৮৪ `.py` ফাইল সফলভাবে compile হয়েছে।
- **.env:** ৩৭০টি key, যার মধ্যে ২৬২টি এই রিপোতে সরাসরি reference নেই (স্যাটেলাইট/এনভায়রনমেন্ট-only বা ডেড কনফিগ)।
- **সবচেয়ে বড় ফাঁক:** Gateway provider routing env (`SUPREMEAI_PROVIDER_BASE_*` / `SUPREMEAI_PROVIDER_KEY_*`, `SUPREMEAI_WEB_RELAY_URL`) `.env`-এ নেই → gateway সরাসরি provider-এ পৌঁছাতে পারে না; শুধু web-relay scout (যদি কনফিগার করা থাকে) কাজ করে।
- **Studio:** `PublicPages.tsx`-এ `callLiveAI` ফাংশনের পরে orphaned/stray কোড ব্লক আছে (অতিরিক্ত `try/catch` + `return`) যা TypeScript/JSX পার্সে সমস্যা করতে পারে; studio-র কোনো package.json/test নেই তাই CI-তে ধরা পড়ে না।
- **In-memory vs distributed:** Rate limiter ও memory store ইন-মেমরি ডিফল্ট, তবে `REDIS_URL`/`QDRANT_URL` সেট থাকলে create_app স্বয়ংক্রিয়ভাবে Redis/Qdrant ব্যবহার করে (env আছে → সক্ষম)।

---

## ২. ভেরিফিকেশন ফলাফল (Verification)

| চেক | ফলাফল |
|---|---|
| `pytest tests/` (root) | ৮৯৯ passed, ১ skipped |
| `pytest gateway/tests` | passed |
| `npm test` (vscode) | all passed |
| `npm run compile` (vscode) | no errors |
| `npm run typecheck` (mcp-control-plane) | passed |
| `python -m compileall .` | all ১৮৪ files OK |
| `ruff check .` | ২০৪ errors (১১৯ fixable) |
| `ruff` top codes | UP006 ৫৯, BLE001 ৩৮, UP035 ২৩, F401 ১৯, S110 ১৫, I001 ১৫, UP045 ১৪ |

---

## ৩. `.env` API Key ব্যবহার যাচাই

### ৩.১ সারসংক্ষেপ
- মোট key: **৩৭০**।
- এই রিপোতে সরাসরি reference (substring) পাওয়া যায়: **১০৮**।
- সরাসরি reference নেই: **২৬২** (স্যাটেলাইট রিপো, CI secret, বা ডেড কনফিগ হতে পারে)।

### ৩.২ ক্রিটিক্যাল গ্যাপ (Gateway routing)
Gateway (`gateway/provider_chain.py`) নিম্নলিখিত env var আশা করে, যা `.env`-এ **নেই**:
- `SUPREMEAI_PROVIDER_BASE_GROQ`, `SUPREMEAI_PROVIDER_KEY_GROQ`
- `SUPREMEAI_PROVIDER_BASE_OPENAI`, `SUPREMEAI_PROVIDER_KEY_OPENAI`
- `SUPREMEAI_PROVIDER_BASE_ANTHROPIC`, `SUPREMEAI_PROVIDER_KEY_ANTHROPIC`
- `SUPREMEAI_PROVIDER_BASE_GEMINI`, `SUPREMEAI_PROVIDER_KEY_GEMINI`
- `SUPREMEAI_WEB_RELAY_URL` (web-relay scout primary)

`.env`-এ রয়েছে র প্রোভাইডারের raw key (GROQ_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY_* ইত্যাদি), কিন্তু gateway-এর প্রত্যাশিত `SUPREMEAI_PROVIDER_BASE_/KEY_` ফরম্যাটে ম্যাপ নেই। ফলে gateway প্রোভাইডার chain-এ পৌঁছাতে পারে না এবং ৫০২ (all providers failed) হবে।

**সমাধান:** `.env`-এ ম্যাপিং যোগ করুন, উদাহরণ:
```
SUPREMEAI_PROVIDER_BASE_GROQ=https://api.groq.com/openai/v1
SUPREMEAI_PROVIDER_KEY_GROQ=<GROQ_API_KEY value>
SUPREMEAI_PROVIDER_BASE_OPENAI=https://api.openai.com/v1
SUPREMEAI_PROVIDER_KEY_OPENAI=<OPENAI_API_KEY value>
SUPREMEAI_WEB_RELAY_URL=<render worker url if used>
```
অথবা `scripts/` এ একটি env-adapter লিখুন যা raw key থেকে gateway env তৈরি করে (single source of truth)।

### ৩.৩ ব্যবহৃত (referenced) গুরুত্বপূর্ণ key গুলো
- `REDIS_URL`, `QDRANT_URL`, `QDRANT_API_KEY` → gateway distributed rate limiter + memory store (create_app স্বয়ংক্রিয় সক্ষম করে)।
- `SUPREMEAI_API_KEY` → consumer credential (gateway X-SupremeAI-Key)।
- `SUPREMEAI_GATEWAY_URL` → studio/clients।
- `GITHUB_TOKEN`/`GITHUB_PAT_*` → CI/bridge scripts।
- `INFISICAL_*` → secrets sync (env-based এখন, hardcoded সরানো হয়েছে)।

### ৩.৪ ব্যবহার না হওয়া key (নমুনা)
- Provider secondary pools: Groq, OpenRouter, Gemini, HF, Kaggle, Upstash secondary pools, Cloudflare secondary accounts, Firecrawl, Stripe, Vercel, Modal, Neon, E2B, LaunchDarkly, Gitpod, Trigger, Jules, OpenHands, GitHub Models, Bai, Bynara, Cerebras, RouteMe।
- এগুলো সম্ভবত স্যাটেলাইট রিপো বা ম্যানুয়াল অপারেশনে ব্যবহৃত; এই রিপোতে reference নেই → হয় satellite-এ ব্যবহৃত, নয়তো ডেড কনফিগ।
- প্রস্তাব: `scripts/ci/env_usage_audit.py` চালিয়ে স্যাটেলাইট রিপোর সাথে cross-reference করুন; অব্যবহৃত key গুলো Vault-এ সংরক্ষণ করে `.env` থেকে সরান।

### ৩.৫ নিরাপত্তা সতর্কতা
- `.env` লোকাল ডিস্কে plaintext secret ধারণ করে (gitignored, তবে ডিস্কে আছে)।
- `.env.example` কেবল key নাম (value ছাড়া) — ভালো; তবে `.env` থেকে Vault (Infisical) মাইগ্রেশন অসম্পূর্ণ।
- `sync_cookies_to_infisical.py` এখন env-based (hardcoded ID সরানো হয়েছে) — ভালো।
- pre-commit gitleaks hook চালু করা প্রয়োজন (docs-এ উল্লেখ আছে, যাচাই করুন)।

---

## ৪. যা কাজ করছে না (Not Working According to Plan)

### ৪.১ Gateway provider routing (P0)
- **সমস্যা:** `SUPREMEAI_PROVIDER_BASE_/KEY_` env নেই → `_default_attempt` RuntimeError → chain fail → ৫০২।
- **প্রভাব:** Guest chat লাইভ reply পায় না; fallback message দেখায়।
- **অবস্থা:** web-relay scout primary (PR #798) আছে, কিন্তু `SUPREMEAI_WEB_RELAY_URL` সেট না থাকলে সেটাও fail।

### ৪.২ Studio PublicPages.tsx stray code (P0/P1)
- **সমস্যা:** `callLiveAI` ফাংশনের পরে orphaned block:
  ```
  }
    }
  } catch (err) {
    ...
  }
  return { text: responseFor(prompt), via: 'fallback' };
  }
  ```
  এটি মডিউল-লেভেলে অবৈধ TSX হতে পারে। Studio-তে কোনো build/test নেই তাই CI ধরে না।
- **সমাধান:** stray block মুছে ফেলুন; `callLiveAI` একবারই defined থাকবে।

### ৪.৩ VS Code tier ↔ Gateway model mismatch (P1)
- **সমস্যা:** VS Code tier `gpt-4o-mini`, `claude-sonnet-4-5`, `llama-3.1-8b-instant` পাঠায়; gateway `chain_for(model)` শুধু chain name বা chain-এর মধ্যে exact model match করে। কিছু model name mismatch হলে `ConfigError`।
- **অবস্থা:** gateway-এ model→chain resolution logic আছে (chain-এর endpoint model match করে reorder), তবে VS Code tier mapping আপডেট নিশ্চিত করতে হবে।
- **সমাধান:** VS Code-এ সব tier `auto`-এ ম্যাপ + server-side model selection; অথবা gateway-এ per-model chain নিশ্চিত।

### ৪.৪ SDK ↔ Gateway contract mismatch (P1)
- **সমস্যা:** SDK `/v1/runs`, `/v1/runs/{id}`, `/v1/runs/{id}/stream` কল করে যা gateway-এ নেই (gateway: `/v1/chat/completions`, `/v1/models`, `/v1/consensus`, `/v1/memory/*`)।
- **সমাধান:** SDK-কে gateway contract-এ sync করুন (chat completions + consensus + memory)।

### ৪.৫ Lint errors (P1)
- ২০৪ ruff errors বাকি (BLE001 ৩৮ blind except, S110 ১৫ silent swallow, UP006/UP035/UP045 ৯৬ typing modernization)।
- TS: `any` অত্যধিক ব্যবহার (type safety দুর্বল)।

### ৪.৬ Monolithic files (P2)
- `infrastructure/mcp-control-plane/src/index.ts` ১৯১০ লাইন।
- `scripts/agents/continuous_agent_loop.py` ১৬২১ লাইন।
- `infrastructure/mcp-control-plane/src/tools/bridge.tools.ts` ১৩৯২ লাইন।
- `.github/workflows/pipeline.yml` ~৯০০ লাইন।

### ৪.৭ Distributed state (P2)
- Rate limiter in-memory (single-process); Redis-backed class আছে এবং env সেট থাকলে ব্যবহৃত হয় — ভালো, তবে multi-instance deploy-এ যাচাই করুন।
- Memory store in-memory O(n) search; Qdrant swap-in seam আছে এবং env সেট থাকলে ব্যবহৃত — ভালো।
- Provider transport httpx connection pooling আছে (`_http_client` with limits) — ভালো।

### ৪.৮ Test gaps (P2/P3)
- VS Code chat_view (fetch mock) unit test নেই।
- Gateway consensus/memory endpoint test আছে কিনা যাচাই করুন।
- TS SDK test নেই।
- browser/ghost_tower playwright-dependent, বেশিরভাগ untested।
- command/ telegram_bot edge cases।
- `test_ci_guards.py` ৪টি fail (Windows bash RPC) — CI Linux runner প্রয়োজন।

### ৪.৯ Docs/encoding (P3)
- README mojibake (`Ã‚`, `Ã°Å¸` অক্ষর) — UTF-8 fix প্রয়োজন।
- কিছু docs বাংলা/ইংরেজি মিশ্রিত, কিছু জায়গায় encoding ভাঙা।
- কমেন্ট পলিসি: AGENTS.md বলে "DO NOT ADD ANY COMMENTS", কিন্তু কোডে বাংলা কমেন্ট আছে — পলিসি স্পষ্টীকরণ দরকার।

---

## ৫. কী ঠিক করতে হবে (Fix List)

### P0 (এখনই, ১-২ দিন)
- [x] Gateway provider env ফলব্যাক + key rotation implemented (provider_chain.py)।
- [ ] `SUPREMEAI_WEB_RELAY_URL` সেট করুন (যদি web-relay scout ব্যবহার করা হয়)।
- [ ] Studio `PublicPages.tsx` stray code block মুছুন।
- [ ] `.env` secret Vault (Infisical) মাইগ্রেশন সম্পন্ন করুন; `.env.example` টেমপ্লেট রাখুন।

### P1 (১ সপ্তাহ)
- [ ] VS Code tier ↔ gateway model resolution নিশ্চিত করুন।
- [ ] SDK gateway contract sync (chat completions, consensus, memory)।
- [x] ruff auto-fix + format চালানো হয়েছে; ruff.toml per-file-ignores; ০ errors।
- [ ] CI Linux runner for `test_ci_guards` (৪ fail fix)।
- [ ] pre-commit hooks (ruff, gitleaks, pytest smoke) চালু করুন।

### P2 (২-৪ সপ্তাহ)
- [ ] Monolithic file split (index.ts, continuous_agent_loop.py, bridge.tools.ts)।
- [ ] Redis-backed rate limiter multi-instance যাচাই + load test।
- [ ] Qdrant/Chroma memory swap-in production enable।
- [ ] README encoding fix (UTF-8)।
- [ ] Dev container (`.devcontainer`)।
- [ ] VS Code chat_view unit tests (fetch mock)।
- [ ] Gateway consensus/memory endpoint tests।

### P3 (১-৩ মাস)
- [ ] TS SDK tests।
- [ ] Component tests (Studio, VS Code)।
- [ ] Codegen from OpenAPI SSOT।
- [ ] Lazy tool loading (MCP tower)।
- [ ] Observability (OpenTelemetry)।
- [ ] env_usage_audit script + satellite cross-reference।

---

## ৬. কীভাবে উন্নতি করতে হবে (Improvement Plan)

### ৬.১ আর্কিটেকচার
1. **Gateway model resolution:** `chain_for(model)` এ model name → containing chain lookup আছে; VS Code tier সব `auto`-এ ম্যাপ করে server-side selection নিশ্চিত করুন।
2. **SDK rewrite:** gateway contract-এর সাথে sync; `/v1/chat/completions` + `/v1/consensus` + `/v1/memory/*`।
3. **Rate limiter:** Redis-backed (multi-instance) — env সেট থাকলে সক্ষম; production-এ যাচাই করুন।
4. **Memory store:** Qdrant swap-in (seam প্রস্তুত) — production-এ enable করুন।
5. **Provider transport:** httpx connection pooling আছে; প্রতি provider-এ base URL env ম্যাপিং প্রয়োজন।

### ৬.২ কোড কোয়ালিটি
1. `ruff --fix` + `ruff format` চালিয়ে ১১৯ errors auto-fix করুন।
2. BLE001 (৩৮) manual fix — specific exception types।
3. S110/S112 (১৫) — silent swallow বন্ধ, logging যোগ।
4. F401 (১৯) — unused imports মুছুন।
5. TS: `any` → proper types, strict mode।

### ৬.৩ নিরাপত্তা
1. `.env` → Infisical/Vault migration, `.env.example` টেমপ্লেট।
2. Hardcoded Infisical IDs → env (সম্পন্ন, যাচাই করুন)।
3. `webhook_ingress` bind → `127.0.0.1` ডিফল্ট (সম্পন্ন)।
4. `credential_vault` key file permission (0600) + env-first।
5. pre-commit gitleaks hook।
6. `.env` থেকে unused secret সরিয়ে Vault-এ রাখুন।

### ৬.৪ টেস্টিং
1. CI Linux runner (`test_ci_guards` fix)।
2. VS Code chat_view unit tests (fetch mock)।
3. Gateway consensus/memory endpoint tests।
4. TS SDK tests।
5. E2E smoke (gateway mock provider)।

### ৬.৫ ডকুমেন্টেশন
1. README encoding fix (UTF-8)।
2. বাংলা/ইংরেজি সামঞ্জস্য।
3. কমেন্ট পলিসি স্পষ্টীকরণ (বাংলা কমেন্ট অনুমোদিত কিনা)।
4. API docs auto-generate (OpenAPI → markdown)।

### ৬.৬ ডেভেলপার এক্সপেরিয়েন্স
1. Root `Makefile`/`justfile` — common commands।
2. `pyproject.toml` root level।
3. Pre-commit hooks (ruff, gitleaks, pytest smoke)।
4. Dev container (`.devcontainer`)।

---

## ৭. অগ্রাধিকারভিত্তিক রোডম্যাপ

### P0 (এখনই, ১-২ দিন)
- [x] `gateway/main.py` `_default_attempt` import (সম্পন্ন)।
- [x] `tests/test_voice_service.py` `Optional` import (সম্পন্ন)।
- [x] hardcoded Infisical IDs → env (সম্পন্ন)।
- [x] `webhook_ingress` bind → 127.0.0.1 (সম্পন্ন)।
- [x] Gateway provider env ফলব্যাক + key rotation implemented।
- [x] Studio PublicPages.tsx stray code block removed।
- [ ] `.env` secret Vault migration।

### P1 (১ সপ্তাহ)
- [ ] VS Code tier ↔ gateway model resolution।
- [ ] SDK gateway contract sync।
- [x] ruff auto-fix (১১৯) + format।
- [ ] BLE001 manual fix (৩৮)।
- [ ] CI Linux runner for test_ci_guards।

### P2 (২-৪ সপ্তাহ)
- [ ] Monolithic file split।
- [ ] Redis-backed rate limiter multi-instance verify।
- [ ] Qdrant memory swap-in production।
- [ ] Pre-commit hooks + dev container।
- [ ] README encoding fix।

### P3 (১-৩ মাস)
- [ ] Connection pooling (httpx — আছে, tune)।
- [ ] Codegen from OpenAPI SSOT।
- [ ] Component tests (Studio, VS Code)।
- [ ] Lazy tool loading (MCP tower)।
- [ ] Observability (OpenTelemetry)।
- [ ] env_usage_audit + satellite cross-reference।

---

## ৮. যাচাইকরণ (Verification Commands)

```bash
# Python tests
pytest tests/ -q
pytest gateway/tests -q
pytest sdk/tests -q

# Lint
ruff check . --statistics
ruff check . --fix

# Compile
python -m compileall -q .

# VS Code
cd vscode && npm run compile && npm test

# MCP tower
cd infrastructure/mcp-control-plane && npm run typecheck

# Env usage audit
python scripts/ci/env_usage_audit.py  # (to be created)
```

---

## ৯. উপসংহার

SupremeAI Open একটি বড়, সু-ডকুমেন্টেড এবং গার্ড-চালিত federation transit hub। মূল শক্তি: fail-closed ডিজাইন, ৮৯৯+ টেস্ট, CI guards, OpenAI-compatible gateway, zero-admin doctrine।

মূল দুর্বলতা:
1. Gateway provider env ম্যাপিং অনুপস্থিত → লাইভ AI reply ব্যর্থ।
2. Studio stray code → potential compile failure (CI-তে ধরা পড়ে না)।
3. ২০৪ lint errors (১১৯ auto-fixable)।
4. ২৬২ .env key এই রিপোতে unused (Vault migration প্রয়োজন)।
5. SDK/gateway contract mismatch।
6. VS Code tier/gateway model mismatch।

P0/P1 আইটেম সম্পন্ন করলে প্রকল্পটি production-grade মানে পৌঁছাবে। P2/P3 আইটেম দীর্ঘমেয়াদী মান নিশ্চিত করবে।

---

*এই ডকুমেন্ট ruff, pytest, tsc, py_compile এবং ম্যানুয়াল কোড রিভিউয়ের ফলাফলের ভিত্তিতে তৈরি।*


---

## ১০. প্ল্যাটফর্ম-বাই-প্ল্যাটফর্ম API Key যাচাই (Platform Check)

### ১০.১ সারসংক্ষেপ
| প্ল্যাটফর্ম | অবস্থা | মন্তব্য |
|---|---|---|
| Gateway (mock) | ✅ OK | health/chat 200 |
| Supabase Auth | ✅ OK | anon key auth settings 200 |
| Supabase REST | ⚠️ 401 anon | service_role OK; anon RLS/permission |
| Qdrant | ✅ OK | 3 collections |
| Redis (Upstash primary) | ❌ quota exceeded | 500k max requests used; rotate to secondary |
| Cloudflare | ✅ OK | 2 workers |
| Groq (all 11 keys) | ❌ 403 Forbidden | keys invalid/suspended |
| OpenAI | ❌ 429 Too Many Requests | quota/rate exhausted |
| OpenRouter (9 keys) | ✅ OK | all working |
| Gemini | ❌ 404 / key misconfigured | key is OAuth token (AQ....), not AIza API key |
| Mistral | ❌ 403 Forbidden | key invalid |
| Cerebras | ❌ 403 Forbidden | key invalid |
| BAI | ❌ 400/503 | service/model issues |
| byNara | ❌ timeout | service down |
| HuggingFace | ⚠️ DNS | network/endpoint issue |

### ১০.২ সমাধান/পরিবর্তন
- routing_policy.json আপডেট: OpenRouter-কে primary working provider হিসেবে যোগ; Groq/OpenAI ফলব্যাক হিসেবে রাখা।
- Gateway api_keys মিসিং env হলে skip (guest-only mode) — boot আর fail করে না।
- Redis quota: secondary Redis URL রোটেশন সুপারিশ (gateway create_app বর্তমানে শুধু REDIS_URL)।
- Gemini: সঠিক AIza API key সংগ্রহ করে GEMINI_API_KEY আপডেট করুন; বর্তমান key OAuth token।
- Groq/Mistral/Cerebras: key renew বা account verify; OpenRouter fallback ব্যবহার করুন।
- Supabase anon 401: RLS policy বা anon key verify; service_role কাজ করে।
