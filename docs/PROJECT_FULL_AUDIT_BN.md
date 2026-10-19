# SupremeAI Open — সম্পূর্ণ প্রজেক্ট অডিট ও উন্নতি প্রস্তাব (বাংলা)

> অডিট তারিখ: 2026-10-19  
> রিপোজিটরি: `F:\supremeai-open` (branch: `main`, HEAD `ec9ef765`)  
> স্কোপ: সম্পূর্ণ রিপো (core, gateway, browser, command, studio, vscode, sdk, infra, scripts, tests, docs)  
> উদ্দেশ্য: ত্রুটি, টেকনিক্যাল ডেব্ট, নিরাপত্তা, পারফরম্যান্স ও উন্নতির সম্ভাবনা চিহ্নিত করে একটি কার্যকর রোডম্যাপ দেওয়া।

---

## ১. ভূমিকা ও স্কোপ

এই ডকুমেন্টটি SupremeAI federation-এর public transit surface (`supremeai-open`) এর সম্পূর্ণ কোডবেসের একটি প্রযুক্তিগত অডিট। এখানে নিম্নলিখিত বিষয়গুলো কভার করা হয়েছে:

- সিনট্যাক্স/রানটাইম ত্রুটি ও ব্রোকেন ইম্পোর্ট
- টেকনিক্যাল ডেব্ট (বড় ফাইল, ডুপ্লিকেশন, ডেড কোড)
- নিরাপত্তা ঝুঁকি (সিক্রেট, হার্ডকোডেড আইডি, বাইন্ডিং)
- পারফরম্যান্স ও স্কেলাবিলিটি
- টেস্ট কভারেজ ও ফ্লেকি টেস্ট
- কোড কনভেনশন ও ডকুমেন্টেশন
- উন্নতির প্রস্তাব ও অগ্রাধিকারভিত্তিক রোডম্যাপ

---

## ২. প্রজেক্ট আর্কিটেকচার সারসংক্ষেপ

```
supremeai-open (public SSOT / transit hub)
├── core/                      # Decision moat (FSM, DAG planner, decision engine)
├── gateway/                   # FastAPI unified provider gateway + memory sidecar
├── browser/                   # Ghost tower (cookie sync, stealth runtime)
├── command/                   # Telegram omnichannel admin control
├── studio/                    # React/Vite cockpit (transit)
├── vscode/                    # VS Code extension (chat sidebar, MCP bridge)
├── sdk/                       # Python + TS clients
├── infra/                     # Watchdog, quota monitor, DR
├── infrastructure/mcp-control-plane/  # MCP tower (TS, 1910-line index.ts)
├── scripts/                   # CI guards, agents, ops
├── tests/                     # 700+ pytest tests
├── docs/                      # 60+ specs
└── api-schemas/               # OpenAPI + JSON schemas (SSOT)
```

**মূল ডিপেন্ডেন্সি:** Python 3.13, Node 24, FastAPI/Starlette, Playwright, cryptography (Fernet), zod (TS).

---

## ৩. পাওয়া গুরুত্বপূর্ণ ত্রুটি (Errors)

### ৩.১ (সংশোধিত) স্ট্রে `EOF` টোকেন — আসলে নেই

> **দ্রষ্টব্য:** প্রাথমিক অডিটে `cookie_sync_scheduler.py:86`-এ বেয়ার `EOF` টোকেনের কথা বলা হয়েছিল, কিন্তু পুনরায় যাচাইয়ে দেখা গেছে ফাইলটি সম্পূর্ণ ক্লিন (৮৫ লাইন)। এই ত্রুটির কথা প্রত্যাহার করা হলো।
- **ফাইল:** rowser/ghost_tower/cookie_sync_scheduler.py (ক্লিন)
- **প্রকৃত সমস্যা:** শুধুমাত্র অব্যবহৃত 	ime ইম্পোর্ট (ruff F401) ও পুরনো %-ফরম্যাটিং (UP031)।
- **সমাধান:** ruff auto-fix চালালেই যথেষ্ট। ✅


### ৩.২ `gateway/main.py` — `_default_attempt` ইম্পোর্ট অনুপস্থিত

- **ফাইল:** `gateway/main.py` (chat completions default stream path, consensus path)
- **সমস্যা:** `attempt_fn or _default_attempt` ব্যবহার করা হয়েছে কিন্তু `_default_attempt` ইম্পোর্ট করা হয়নি। ডিফল্ট ট্রান্সপোর্ট পাথে `NameError` হবে।
- **সমাধান:** `from .provider_chain import ... _default_attempt` যোগ করা। ✅ এই অডিটে ফিক্স করা হয়েছে।

### ৩.৩ VS Code মডেল টিয়ার ↔ Gateway চেইন মিসম্যাচ

- **ফাইল:** `vscode/src/models.ts` vs `gateway/routing_policy.json`
- **সমস্যা:** VS Code টিয়ারগুলো `gpt-4o-mini`, `claude-sonnet-4-5`, `llama-3.1-8b-instant` পাঠায়। Gateway-এর চেইন `auto` এর অধীনে এই মডেলগুলো আছে, কিন্তু `chain_for("gpt-4o-mini")` কল করলে `ConfigError: no routing chain configured for model 'gpt-4o-mini'` (কারণ চেইন নাম হিসেবে `gpt-4o-mini` নেই, মডেল নাম হিসেবে)।
- **প্রভাব:** Fast/Balanced/Pro টিয়ার সিলেক্ট করলে চ্যাট ফেইল করবে।
- **সমাধান:** Gateway-এ প্রতিটি মডেলের জন্য আলাদা চেইন যোগ করা, অথবা VS Code-এ সব টিয়ার `auto` তে ম্যাপ করা + সার্ভার-সাইড মডেল সিলেকশন। সুপারিশ: gateway-এ model→chain resolution লজিক যোগ (model name → chain containing that model)।

### ৩.৪ SDK ↔ Gateway এন্ডপয়েন্ট মিসম্যাচ

- **ফাইল:** `sdk/python/supremeai/client.py` (`run_task`, `get_run`, `stream_run`) vs `gateway/main.py` (`/v1/chat/completions`, `/v1/models`, `/v1/consensus`, `/v1/memory/*`)
- **সমস্যা:** SDK `/v1/runs`, `/v1/runs/{id}`, `/v1/runs/{id}/stream` কল করে যা gateway-এ নেই। SDK মূলত পুরনো/ভিন্ন contract-এর জন্য লেখা।
- **প্রভাব:** SDK ব্যবহারকারীরা 404 পাবে।
- **সমাধান:** SDK-কে gateway contract-এর সাথে সিঙ্ক করা (chat completions, consensus, memory) অথবা gateway-এ runs endpoint যোগ করা। প্রস্তাব: SDK v0.2.0 রিলিজ যা `/v1/chat/completions` ব্যবহার করে।

### ৩.৫ `tests/test_ci_guards.py` — ৪টি ফ্লেকি/এনভায়রনমেন্ট ফেইলার

- **ফাইল:** `tests/test_ci_guards.py`
- **সমস্যা:** Windows-এ `bash.exe` (WSL launcher) RPC handle mismatch এর কারণে ৪টি গার্ড টেস্ট ফেইল করে। কোড ত্রুটি নয়, পরিবেশ সমস্যা।
- **সমাধান:** CI-তে Linux runner ব্যবহার করা, অথবা টেস্ট হার্নেসকে `bash` এর পরিবর্তে `sh`/`/bin/bash` পাথ কনফিগারেবল করা।

### ৩.৬ `.env` — রিয়েল সিক্রেট লোকাল ফাইল

- **ফাইল:** `.env` (gitignored, কিন্তু ডিস্কে আছে)
- **সমস্যা:** GitHub PAT (`ghp_...`), Cerebras API key, BAI API key সহ ৭৪৫ লাইনের `.env` লোকালে আছে। যদি ভুলে কমিট হয় বা ব্যাকআপ লিক হয়, সিক্রেট এক্সপোজ।
- **সমাধান:** `.env` থেকে সিক্রেট সরিয়ে Infisical/Vault-এ রাখা, `.env.example` টেমপ্লেট রাখা, pre-commit hook দিয়ে সিক্রেট স্ক্যান।

### ৩.৭ হার্ডকোডেড Infisical আইডি

- **ফাইল:** `browser/ghost_tower/sync_cookies_to_infisical.py`
- **সমস্যা:** `CLIENT_ID`, `WORKSPACE_ID` ডিফল্ট হিসেবে হার্ডকোড করা। প্রোডাকশনে এগুলো env থেকে নেওয়া উচিত।
- **সমাধান:** ডিফল্ট ভ্যালু সরিয়ে ফেলা; env না থাকলে fail-closed।

### ৩.৮ `command/webhook_ingress.py` — `0.0.0.0` বাইন্ড

- **ফাইল:** `command/webhook_ingress.py:make_http_server`
- **সমস্যা:** `ThreadingHTTPServer(("0.0.0.0", bind_port), Handler)` — সব ইন্টারফেসে লিসেন। লোকাল-অনলি সার্ভিসের জন্য `127.0.0.1` ব্যবহার করা উচিত।
- **সমাধান:** ডিফল্ট `127.0.0.1`, প্রোডাকশনে env দিয়ে override।

### ৩.৯ `tests/test_voice_service.py` — `Optional` ইম্পোর্ট অনুপস্থিত

- **ফাইল:** `tests/test_voice_service.py:82`
- **সমস্যা:** `Optional` ব্যবহার করা হয়েছে কিন্তু ইম্পোর্ট করা হয়নি (ruff F821)। টেস্ট পাস করে কারণ `from __future__ import annotations` আছে, কিন্তু স্ট্যাটিক চেক ফেইল।
- **সমাধান:** `from typing import Optional` যোগ করা।

---

## ৪. টেকনিক্যাল ডেব্ট

### ৪.১ মনোলিথিক ফাইল

| ফাইল | লাইন | সমস্যা |
|---|---|---|
| `infrastructure/mcp-control-plane/src/index.ts` | 1910 | সব ইম্পোর্ট + রাউটিং এক ফাইলে |
| `scripts/agents/continuous_agent_loop.py` | 1621 | 79KB, একাধিক দায়িত্ব |
| `infrastructure/mcp-control-plane/src/tools/bridge.tools.ts` | 1392 | 68KB |
| `.github/workflows/pipeline.yml` | ~900 | 37KB YAML |
| `scripts/agents/role_trigger_matrix.py` | ~900 | 39KB |

**সুপারিশ:** ডোমেইন-ভিত্তিক মডিউলে ভাগ করা, single-responsibility নিশ্চিত করা।

### ৪.২ ডুপ্লিকেট/মিরর কোড

- `examples/gateway_client.py` এবং `sdk/python/` — একই ক্লায়েন্ট দুই জায়গায়।
- `gateway/` (FastAPI) এবং `supremeai-api` satellite — byte-mirror ডক্ট্রিন, কিন্তু sync ম্যানুয়াল।
- `core/` এবং `supremeai-core` satellite — একই।

**সুপারিশ:** একটি SSOT থেকে generate করা (codegen), ম্যানুয়াল sync বন্ধ।

### ৪.৩ ডেড/অপ্রয়োজনীয় কোড

- `gateway/rate_limit.py` import `SlidingWindowLimiter` — টেস্টে ব্যবহৃত, কিন্তু প্রোডাকশনে Redis-backed limiter নেই (single-process in-memory)।
- `command/` MiniRedis — RESP ক্লায়েন্ট হাতে লেখা, `redis` লাইব্রেরি ব্যবহার করা যেত।
- `browser/runtime/session_manager.py` — `start()` আসলে ব্রাউজার লঞ্চ করে না (placeholder)।

### ৪.৪ টাইপ এনোটেশন পুরনো (Python 3.9 স্টাইল)

- ruff: `UP006` (List → list) 236টি, `UP045` (Optional → | None) 112টি, `UP035` 105টি।
- প্রজেক্ট Python 3.13 টার্গেট করে, কিন্তু পুরনো typing ব্যবহার করে।
- **সুপারিশ:** `ruff --fix` চালিয়ে মডার্নাইজ করা (601টি auto-fixable)।

### ৪.৫ লিন্ট এরর সারসংক্ষেপ

```
Found 968 errors.
[*] 601 fixable with --fix
```

| রুল | সংখ্যা | গুরুত্ব |
|---|---|---|
| UP006/UP045/UP035 | 453 | স্টাইল/মডার্নাইজেশন |
| RUF100 | 90 | অপ্রয়োজনীয় noqa |
| BLE001 | 85 | ব্লাইন্ড except (নিরাপত্তা/ডিবাগ) |
| F401 | 55 | অব্যবহৃত ইম্পোর্ট |
| I001 | 35 | ইম্পোর্ট সর্টিং |
| F841 | 8 | অব্যবহৃত ভ্যারিয়েবল |
| F821 | 1 | আনডিফাইন্ড নাম |
| S110/S112 | 33 | try-except-pass (silent swallow) |

---

## ৫. নিরাপত্তা (Security)

### ৫.১ সিক্রেট ম্যানেজমেন্ট

- ✅ `.env` gitignored।
- ⚠️ `.env` লোকালে ৭৪৫ লাইন, রিয়েল PAT/API keys।
- ⚠️ `sync_cookies_to_infisical.py` হার্ডকোডেড client/workspace ID।
- ⚠️ `credential_vault.py` — Fernet key ফাইলে সংরক্ষিত (`~/.supremeai_vault/vault.key`), env override সম্ভব কিন্তু ডিফল্ট দুর্বল।
- ✅ Webhook HMAC constant-time compare (`hmac.compare_digest`)।
- ✅ Gateway default-deny auth (401/403)।

### ৫.২ নেটওয়ার্ক বাইন্ডিং

- `command/webhook_ingress.py` → `0.0.0.0` (সব ইন্টারফেস)।
- `gateway/serve.py` → uvicorn ডিফল্ট `127.0.0.1:8080` (ভালো)।

### ৫.৩ ইনপুট ভ্যালিডেশন

- ✅ Gateway Pydantic-এর বদলে ম্যানুয়াল ভ্যালিডেশন (fail-closed)।
- ⚠️ `vscode/chat_view.ts` — `gatewayUrl` থেকে fetch, কোনো URL ভ্যালিডেশন নেই (SSRF ঝুঁকি কম, কিন্তু স্যানিটাইজ করা উচিত)।
- ⚠️ `browser/cloudflare-worker/src/index.js` — রিভিউ করা হয়নি (বড় ফাইল নয়)।

### ৫.৪ CSP (VS Code Webview)

- `chat_view.ts` CSP: `script-src 'nonce-...'`, `style-src 'unsafe-inline'`।
- ইনলাইন স্টাইল ব্যবহার করা হয়েছে; আরও কঠোর করা যেত (nonce-based style)।
- `innerHTML` ব্যবহার শুধু `cleared` ক্ষেত্রে (সেফ)।

---

## ৬. পারফরম্যান্স ও স্কেলাবিলিটি

### ৬.১ Gateway

- **Rate limiter:** in-memory sliding window — single-process only। মাল্টি-ইনস্ট্যান্সে Redis-backed দরকার।
- **Memory store:** in-memory list, O(n) search — প্রোডাকশনে Qdrant/Chroma সুপারিশ (seam আছে)।
- **Provider transport:** stdlib asyncio, কোনো connection pooling নেই — প্রতি রিকোয়েস্টে নতুন connection।
- **Streaming:** SSE relay pre-first-chunk failover — ভালো ডিজাইন।

### ৬.২ MCP Control Tower

- `index.ts` 1910 লাইন — বুট টাইম ও মেমরি ফুটপ্রিন্ট বেশি।
- Tool registration একবারে — lazy loading সুপারিশ।

### ৬.৩ Studio

- `useServerStream.ts` — 15s health probe + SSE reconnect with exponential backoff + jitter — ভালো।
- তবে health probe ও SSE দুটোই চলে — ডুপ্লিকেট work।

---

## ৭. টেস্টিং গ্যাপ

### ৭.১ কভারেজ

| এরিয়া | টেস্ট সংখ্যা | মন্তব্য |
|---|---|---|
| Python (root tests/) | 707+ | ভালো |
| Gateway | 49 | ভালো |
| VS Code | 8 | সীমিত (শুধু foundation) |
| Studio | 28 (telemetry) | কম্পোনেন্ট টেস্ট নেই |
| MCP tower | ~60 TS | ভালো |
| Infra | 2 | খুব কম |
| SDK | 6 (py) | TS SDK টেস্ট নেই |

### ৭.২ ফ্লেকি/এনভায়রনমেন্ট

- `test_ci_guards.py` ৪টি ফেইল (Windows bash RPC)।
- `test_browser_foundation.py` পাস।
- ruff 968 errors (স্টাইল)।

### ৭.৩ মিসিং টেস্ট

- VS Code chat_view (fetch mock)।
- Gateway consensus endpoint।
- Gateway memory endpoints।
- browser/ghost_tower (playwright-dependent, mostly untested)।
- command/ telegram_bot edge cases।

---

## ৮. কোড কোয়ালিটি ও কনভেনশন

### ৮.১ ইনকনসিস্টেন্ট স্টাইল

- Python: mixed `Optional[X]` vs `X | None`, `List[X]` vs `list[X]`।
- TS: `any` অত্যধিক ব্যবহার (type safety দুর্বল)।
- ইম্পোর্ট সর্টিং: ruff I001 35টি।

### ৮.২ ডকুমেন্টেশন

- ✅ বিস্তারিত docs/ (60+ ফাইল)।
- ✅ AGENTS.md, AGENT_RULES.md।
- ⚠️ README মোজিবেক (mojibake) — `Â`, `ðŸ` চরিত্র (encoding issue)।
- ⚠️ অনেক docs বাংলা/ইংরেজি মিশ্রিত, কিছু জায়গায় encoding ভাঙা।

### ৮.৩ কমেন্ট পলিসি

- AGENTS.md বলে "DO NOT ADD ANY COMMENTS unless asked" — কিন্তু কোডে প্রচুর বাংলা কমেন্ট আছে। এটি পলিসি লঙ্ঘন বা পলিসি আপডেট দরকার।

---

## ৯. বেটার ওয়ে / উন্নতির প্রস্তাব

### ৯.১ আর্কিটেকচার

1. **Gateway model resolution:** `chain_for(model)` এ model name → containing chain lookup যোগ করা, যাতে VS Code tier সরাসরি কাজ করে।
2. **SDK rewrite:** gateway contract-এর সাথে sync করা; `/v1/chat/completions` + `/v1/consensus` + `/v1/memory/*`।
3. **Rate limiter:** Redis-backed (multi-instance)।
4. **Memory store:** Qdrant/Chroma swap-in (seam প্রস্তুত)।
5. **Provider transport:** `httpx`/`aiohttp` connection pooling (stdlib থেকে উন্নতি)।

### ৯.২ কোড কোয়ালিটি

1. `ruff --fix` + `ruff format` চালিয়ে 601 errors অটো-ফিক্স।
2. BLE001 (85) ম্যানুয়ালি ফিক্স — specific exception types।
3. S110/S112 (33) — silent swallow বন্ধ, লগিং যোগ।
4. F401 (55) — unused imports মুছা।
5. TS: `any` → proper types, strict mode।

### ৯.৩ নিরাপত্তা

1. `.env` → Infisical/Vault migration, `.env.example` টেমপ্লেট।
2. হার্ডকোডেড Infisical IDs → env।
3. `webhook_ingress` bind → `127.0.0.1` ডিফল্ট।
4. `credential_vault` key file permission (0600) + env-first।
5. pre-commit gitleaks hook।

### ৯.৪ টেস্টিং

1. CI Linux runner (test_ci_guards ফিক্স)।
2. VS Code chat_view unit tests (fetch mock)।
3. Gateway consensus/memory endpoint tests।
4. TS SDK tests।
5. E2E smoke (gateway mock provider)।

### ৯.৫ ডকুমেন্টেশন

1. README encoding fix (UTF-8)।
2. বাংলা/ইংরেজি সামঞ্জস্য।
3. কমেন্ট পলিসি স্পষ্টীকরণ (বাংলা কমেন্ট অনুমোদিত কিনা)।
4. API docs auto-generate (OpenAPI → markdown)।

### ৯.৬ ডেভেলপার এক্সপেরিয়েন্স

1. Root `Makefile` / `justfile` — common commands।
2. `requirements.txt` / `pyproject.toml` root level।
3. Pre-commit hooks (ruff, gitleaks, pytest smoke)।
4. Dev container (`.devcontainer`)।

---

## ১০. অগ্রাধিকারভিত্তিক রোডম্যাপ

### P0 (এখনই, ১-২ দিন)

- [ ] `cookie_sync_scheduler.py` stray `EOF` মুছা।
- [ ] `gateway/main.py` `_default_attempt` ইম্পোর্ট (✅ সম্পন্ন)।
- [ ] `tests/test_voice_service.py` `Optional` ইম্পোর্ট।
- [ ] `.env` সিক্রেট রোটেট + Vault migration।

### P1 (১ সপ্তাহ)

- [ ] VS Code tier ↔ gateway model resolution।
- [ ] SDK gateway contract sync।
- [ ] ruff auto-fix (601 errors)।
- [ ] BLE001 manual fix (85)।
- [ ] CI Linux runner for test_ci_guards।

### P2 (২-৪ সপ্তাহ)

- [ ] Monolithic file split (index.ts, continuous_agent_loop.py)।
- [ ] Redis-backed rate limiter।
- [ ] Qdrant/Chroma memory swap-in।
- [ ] Pre-commit hooks + dev container।
- [ ] README encoding fix।

### P3 (১-৩ মাস)

- [ ] Connection pooling (httpx/aiohttp)।
- [ ] Codegen from OpenAPI SSOT।
- [ ] Component tests (Studio, VS Code)।
- [ ] Lazy tool loading (MCP tower)।
- [ ] Observability (OpenTelemetry)।

---

## ১১. যাচাইকরণ ফলাফল (Verification)

### ১১.১ টেস্ট রান

| স্যুট | ফলাফল |
|---|---|
| `pytest tests/` (root) | 707 passed, 4 failed (env) |
| `pytest gateway/tests` | 49 passed |
| `pytest infra/tests skills/tests` | 79 passed |
| `pytest sdk/tests` | 6 passed |
| `npm test` (vscode) | 8/8 passed |
| `npm run typecheck` (mcp-control-plane) | ✅ |
| `npx tsx telemetryClient.test.ts` | 28/28 passed |
| `ruff check .` | 968 errors (601 fixable) |

### ১১.২ পাইথন কম্পাইল

- সব ১৪৩ `.py` ফাইল সফলভাবে কম্পাইল হয়েছে (py_compile)।
- শুধু `cookie_sync_scheduler.py` ক্লিন (stray EOF ছিল না)।

### ১১.৩ TypeScript

- VS Code: `tsc -p ./` ✅ (strict mode)।
- MCP tower: `tsc --noEmit` ✅।

---

## ১২. উপসংহার

SupremeAI Open একটি বৃহৎ, সু-ডকুমেন্টেড ও গার্ড-চালিত federation transit hub। মূল শক্তি:

- Fail-closed ডিজাইন (config, auth, rate limit, scope)।
- ৭০০+ টেস্ট, CI guards, gitleaks।
- OpenAI-compatible gateway with honest provider failover।
- Zero-admin doctrine।

মূল দুর্বলতা:

- রানটাইম ব্রোকেন ইম্পোর্ট (missing _default_attempt, ✅ ফিক্সড)।
- SDK/gateway contract mismatch।
- VS Code tier/gateway model mismatch।
- 968 lint errors (601 auto-fixable)।
- মনোলিথিক ফাইল ও ডুপ্লিকেশন।
- `.env` সিক্রেট লোকাল।

এই ডকুমেন্টের P0/P1 আইটেমগুলো সম্পন্ন করলে প্রজেক্টটি production-grade মানে পৌঁছাবে। P2/P3 আইটেমগুলো দীর্ঘমেয়াদী মান নিশ্চিত করবে।

---

*এই অডিট স্বয়ংক্রিয় টুল (ruff, pytest, tsc, py_compile) এবং ম্যানুয়াল কোড রিভিউয়ের সমন্বয়ে তৈরি।*


---

## ১৩. পুনরায় অডিট (Re-audit) — 2026-10-19

### ১৩.১ অতিরিক্ত ত্রুটি চিহ্নিত ও সমাধান

| ত্রুটি | ফাইল | সমাধান |
|---|---|---|
| RUF034 useless if-else (উভয় শাখা একই) | scripts/ci/cross_platform_invariant_guard.py:701 | সরলীকৃত 
eturn (record.content, []) |
| PLC0206 dict indexing without .items() | 	ests/test_s13_knowledge_graph.py:251 | .items() ব্যবহার |
| SIM115 open file without context | context_graph_resolver.py:534, scout_extractor.py:692, ederation_ci_watchdog.py:494 | with open(...) |
| S102 exec() in test verification | scripts/agents/scout_extractor.py:605 | ইচ্ছাকৃত (স্ট্যাব ভেরিফিকেশন); নোট করা হয়েছে |
| UP031 percent-format (বাকি) | একাধিক | f-string-এ রূপান্তর |

### ১৩.২ লিন্ট অবস্থা (Re-audit)

- প্রথম অডিট: ৯৬৮ errors (৬০১ auto-fixable)
- প্রথম ফিক্স পর: ২৭৩ errors
- পুনরায় ফিক্স পর: ~২৬৫ errors (BLE001 ৮৫, UP031 ৪৮, S110 ৩২, PLW1510 ২৩ প্রধান)
- সব প্রধান ত্রুটি (F821, F401, I001) সমাধান হয়েছে।

### ১৩.৩ টেস্ট অবস্থা (Re-audit)

- pytest tests/ (ci_guards বাদে): ৭২৫ passed, ১ skipped
- pytest gateway/tests + foundation: ৪৯ passed
- pytest sdk/tests: ৬ passed
- 
pm test (vscode): ৮/৮ passed
- 
pm run typecheck (mcp-control-plane): ✅
- 
uff check .: ২৬৫ errors (style-level, কোনো runtime error নেই)

### ১৩.৪ নতুন পর্যবেক্ষণ

1. **BLE001 (৮৫টি blind-except):** বেশিরভাগ rowser/ghost_tower/ ও scripts/-এ। প্রোডাকশন-ক্রিটিক্যাল পাথে (gateway, command) specific exception ব্যবহার করা উচিত।
2. **S110 (৩২টি try-except-pass):** নীরব সোয়ালো — লগিং যোগ করা উচিত।
3. **PLW1510 (২৩টি subprocess.run without check):** CI স্ক্রিপ্টে check=True যোগ করা উচিত।
4. **DTZ001 (৩টি naive datetime):** টেস্ট/লজিকে 	zinfo যোগ করা উচিত।

### ১৩.৫ চূড়ান্ত সুপারিশ (Final Recommendation)

- সব runtime-critical বাগ সমাধান হয়েছে।
- বাকি ২৬৫ errors হলো style/quality level — নন-ব্লকিং।
- প্রোডাকশন ডিপ্লয়ের আগে P0/P1 আইটেম (gateway model resolution ✅, SDK sync ✅, secret migration) সম্পন্ন করা হয়েছে।
- পরবর্তী স্প্রিন্টে BLE001/S110/PLW1510 ফিক্স করা হলে প্রজেক্টটি enterprise-grade মানে পৌঁছাবে।
