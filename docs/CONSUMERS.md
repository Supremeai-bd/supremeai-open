# Consumers — SupremeAI Gateway-তে সংযোগের চুক্তি (P3)

> **English Summary:** This document outlines the connection contract for the SupremeAI Gateway. It details the API endpoint, authentication header (`X-SupremeAI-Key`), key lifecycle management via the monolith vault, error handling semantics, and guidelines for Agent and GitHub-automation consumers.

> **বাংলা:** agent (§15) ও GitHub-automation (§16) কীভাবে গেটওয়ে খাওয়াবে — একটিমাত্র
> চুক্তি, একটিমাত্র header। Provider কে সামলালো তা আপনার জানার দরকার নেই (§২২)।

## ১. Consumer-চুক্তি (৩ লাইন)

```text
endpoint : POST {GATEWAY_URL}/v1/chat/completions   (OpenAI-compatible)
header   : X-SupremeAI-Key: <SUPREMEAI_API_KEY>
secret   : vault-ফিড env — কখনো কোড/git/log-এ নয় (SECRETS_MODEL.md)
```

- `GATEWAY_URL` ডিফল্ট `https://supremeai-api.onrender.com` (Render live হলে)
- মডেল `"auto"` দিন — provider নির্বাচন gateway-র কাজ; নির্দিষ্ট মডেলও চলে
  (`/v1/models`-এ সক্রিয় তালিকা)

## ২. Key-জীবনচক্র (monolith key-plane-নিয়ন্ত্রিত)

1. **issue** — monolith admin UI (`/api/api-keys/create`, JWT-gated) → plaintext
   একবারই দেখাবে
2. **store** — Infisical vault-এ (`SUPREMEAI_API_KEY` বা `<CONSUMER>_SUPREMEAI_API_KEY`)
3. **consume** — Render/env/vault-injection → `X-SupremeAI-Key`
4. **rotate/revoke** — monolith-এই; gateway-তে ৩০০s ক্যাশ-TTL-এর মধ্যে প্রতিফলিত
   (keyplane ঐক্য — নতুন key-code নেই)

> নোট: vault-এর বর্তমান `SUPREMEAI_API_KEY` monolith key-plane-ইস্যুকৃত নয়
> (legacy) — প্রথম প্রকৃত consumer-নিবন্ধনের সময় key-plane-থেকে নতুন issue করে
> প্রতিস্থাপন করা হবে।

## ৩. Error-semantics (সৎ-চুক্তি)

| HTTP | অর্থ | consumer-করণীয় |
|---|---|---|
| 401 | key অবৈধ/বাতিল/মেয়াদোত্তীর্ণ | retry নয় — key যাচাই |
| 429 | per-key সীমা (`rate_limit_rps × window`) | Retry-After সম্মান |
| 502 | fallback-chain শেষ — সব provider ব্যর্থ | কিছুক্ষণ পরে retry |
| 503 | keyplane/অবকাঠামো অপ্রাপ্য | retry-যোগ্য (client নিজেই করে) |

## ৪. Python client (zero-dependency)

```python
import sys; sys.path.insert(0, "examples")
from gateway_client import chat
out = chat([{"role": "user", "content": "ping"}])   # env: SUPREMEAI_API_KEY
print(out["choices"][0]["message"]["content"])
```

CLI one-shot: `python3 examples/gateway_client.py --prompt "ping"`

## ৫. §15 — Agent-consumers

- agent-identity-প্রতি আলাদা key (`<AGENT>_SUPREMEAI_API_KEY`) — quota-অ্যাট্রিবিউশন
  monolith key-plane-এ (usage log-এ `key_id`)
- agent মারা গেলে key revoke — অন্য agent অপ্রভাবিত
- provider-key agent-এর হাতে কখনোই যায় না — এটাই gateway-র অস্তিত্বের কারণ

## ৬. §16 — GitHub-automation consumers

```yaml
# .github/workflows/ai-note.yml (উদাহরণ — প্রকৃত workflow নয়)
- name: AI advisory note
  env:
    SUPREMEAI_API_KEY: ${{ secrets.SUPREMEAI_API_KEY }}
  run: |
    python3 examples/gateway_client.py \
      --prompt "Summarize this diff for humans:" || echo "advisory failed — non-blocking"
```

**লৌহদণ্ড: deterministic protections remain authoritative।** AI-আউটপুট = advisory
ইনপুট মাত্র — PR-gate/evaluator/merge-সিদ্ধান্ত কখনো AI-call-এর উপর নির্ভর করবে না
(প্রেসিডেন্ট: fork AI PR Evaluator সম্পূর্ণ deterministic)। AI-call fail হলে workflow
non-blocking-ভাবে এগোবে (`|| true` ধরন)।

## ৭. Migration-checklist (নতুন consumer)

- [ ] monolith admin-এ key issue (scopes-সহ) → vault-এ রাখা
- [ ] `gateway_client.py` দিয়ে smoke-test (`--prompt ping`)
- [ ] consumer-এর error-handling §৩-এর টেবিল মেনেছে কিনা
- [ ] GitHub-automation হলে §৬-র non-blocking নীতি মেনেছে কিনা
