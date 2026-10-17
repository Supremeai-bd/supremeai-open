# Consumers — SupremeAI Gateway-তে সংযোগের চুক্তি (P3)

> **English Summary:** This document is the connection contract for the SupremeAI Gateway, now with a frictionless 5-minute quickstart (§0): a single-command `curl` test, drop-in Python (`openai` SDK) and TypeScript snippets with streaming, the model list endpoint, rate-limit semantics, and error response schemas. It also retains the 3-line contract, key lifecycle via the monolith vault, error handling semantics, and guidelines for Agent (§৫) and GitHub-automation (§৬) consumers.

> **বাংলা:** agent (§৫) ও GitHub-automation (§৬) কীভাবে গেটওয়ে খাওয়াবে — একটিমাত্র
> চুক্তি, একটিমাত্র header। Provider কে সামলালো তা আপনার জানার দরকার নেই (§২২)।
> নতুন consumer? §০-র কপি-পেস্ট কুইকস্টার্ট দিয়ে ৫ মিনিটেই শুরু করুন।

## §০. 5-minute Quickstart (copy-paste)

**Base URL:** `https://supremeai-api.onrender.com` — stable OpenAI-compatible surface.
Contract SSOT: [`api-schemas/gateway.openapi.yaml`](../api-schemas/gateway.openapi.yaml).

> **Live status (সৎ-নোট):** এই লেখার সময় Render deployment সব route-এ
> `x-render-routing: no-server` দিচ্ছে — deployment debugging Phase 0 Seq 0.1-এ
> ট্র্যাকড (#401)। Liveness প্রোব (auth ছাড়া): `GET /healthz` → `200` মানে লাইভ।
> নিচের snippet-গুলো OpenAPI চুক্তির সাথে শব্দে-শব্দে মিলে — deployment লাইভ হওয়ার
> সাথে সাথেই কাজ করবে। কোনো snippet লাইভ-কল দিয়ে "প্রমাণিত" দাবি করা হয়নি।

### §০.১ curl — এক কমান্ডে চ্যাট টেস্ট

```bash
# shell: export SUPREMEAI_API_KEY=... (কখনো কোড/git/log-এ হার্ডকোড নয়)
curl -sS https://supremeai-api.onrender.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-SupremeAI-Key: $SUPREMEAI_API_KEY" \
  -d '{"model":"auto","messages":[{"role":"user","content":"ping"}]}'
```

প্রতিক্রিয়া: OpenAI-compatible `chat.completion` অবজেক্ট — `choices[0].message.content`
পড়ুন (§৩.১-এ আকৃতি)।

### §০.২ Python — `openai` SDK drop-in (streaming সহ)

```python
# pip install openai
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://supremeai-api.onrender.com/v1",
    api_key=os.environ["SUPREMEAI_API_KEY"],
    default_headers={"X-SupremeAI-Key": os.environ["SUPREMEAI_API_KEY"]},
)

# সাধারণ কল
r = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "ping"}],
)
print(r.choices[0].message.content)

# স্ট্রিমিং (SSE)
stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "গল্প বলো"}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
```

> `default_headers`-এ `X-SupremeAI-Key` — এটাই চুক্তির header
> (`api-schemas/gateway.openapi.yaml` securitySchemes)। SDK নিজে `Authorization:
> Bearer` পাঠায়, কিন্তু stable চুক্তিতে শুধু `X-SupremeAI-Key` ঘোষিত — তাই
> দুটোই পাঠানো নিরাপদ ও স্বয়ংসম্পূর্ণ।

Zero-dependency পথ (SDK ছাড়া): §৪-র `examples/gateway_client.py`।

### §০.৩ TypeScript — native `fetch` (streaming সহ)

```typescript
// Node 18+ বা যেকোনো fetch runtime; কোনো dependency নেই
const base = "https://supremeai-api.onrender.com";
const key = process.env.SUPREMEAI_API_KEY!;

// এক কল (non-streaming)
const res = await fetch(`${base}/v1/chat/completions`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-SupremeAI-Key": key,
  },
  body: JSON.stringify({
    model: "auto",
    messages: [{ role: "user", content: "ping" }],
  }),
});
const json: any = await res.json();
console.log(json.choices?.[0]?.message?.content);
```

```typescript
// স্ট্রিমিং — OpenAI-compatible SSE (data: ফ্রেম, [DONE] সেন্টিনেল)
const stream = await fetch(`${base}/v1/chat/completions`, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-SupremeAI-Key": key },
  body: JSON.stringify({
    model: "auto",
    messages: [{ role: "user", content: "গল্প বলো" }],
    stream: true,
  }),
});
const reader = (await stream.body!).getReader();
const decoder = new TextDecoder();
let buf = "";
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  const lines = buf.split("\n");
  buf = lines.pop() ?? "";
  for (const line of lines) {
    const t = line.trim();
    if (!t.startsWith("data:")) continue;
    const payload = t.slice(5).trim();
    if (payload === "[DONE]") process.exit(0);
    const piece = JSON.parse(payload);
    process.stdout.write(piece.choices?.[0]?.delta?.content ?? "");
  }
}
```

`openai` npm SDK ব্যবহার করলে: `new OpenAI({ baseURL: base + "/v1", apiKey: key,
defaultHeaders: { "X-SupremeAI-Key": key } })` — বাকি সব §০.২-র মতোই।

### §০.৪ Models তালিকা

```bash
curl -sS https://supremeai-api.onrender.com/v1/models \
  -H "X-SupremeAI-Key: $SUPREMEAI_API_KEY"
```

```json
{ "object": "list", "data": [ { "id": "<model-id>", "object": "model", "owned_by": "supremeai" } ] }
```

- `model: "auto"` দিন — routing গেটওয়ের সিদ্ধান্ত (ডিফল্ট)। `/v1/models`-এ
  routing_policy-অনুযায়ী সক্রিয় তালিকা; তালিকার যেকোনো `id`-ও চলে।
- উত্তরের `model` ফিল্ড = যে মডেল সত্যিই সামলালো (provider-name দৃশ্যমান হতে
  পারে, key কখনো নয়)।

### §০.৫ Rate-limit semantics

| সংকেত | অর্থ | consumer-করণীয় |
|---|---|---|
| `429` | per-key quota/rate-limit ছাড় (config-driven) | **`Retry-After` header সম্মান করুন** — এটাই stable চুক্তির অংশ |

> সততা-নোট: `Retry-After` ছাড়া অন্য rate-limit header (যেমন `X-RateLimit-*`
> জাতীয়) stable চুক্তিতে এখনো ঘোষিত নয় — ওগুলোর উপর নির্ভর করবেন না।

### §০.৬ Error response schemas

HTTP status-এ শাখা দিন (body-ফিল্ডে নয়) — stable চুক্তিতে status-semantics পিন করা,
error-body আকৃতি এখনো SSOT-এ পিন করা নেই:

| HTTP | অর্থ (OpenAPI SSOT) | করণীয় |
|---|---|---|
| `401` | Invalid or missing SupremeAI key | retry নয় — key যাচাই (§২) |
| `403` | Key lacks required scope | সঠিক scope-সহ key চান |
| `429` | Quota/rate limit exceeded | `Retry-After` সম্মান (§০.৫) |
| `502` | All providers in fallback chain failed | কিছুক্ষণ পরে retry |

প্রত্যাশিত ন্যূনতম আকৃতি — OpenAI-compatible; অজানা ফিল্ড উপেক্ষা করুন:

```json
{ "error": { "message": "<মানবপাঠ্য কারণ>", "type": "<শ্রেণি>", "code": "<ঐচ্ছিক>" } }
```

> সততা-নোট: উপরের JSON আকৃতি OpenAI-compatible প্রথা; stable OpenAPI-তে যতক্ষণ
> না পিন হয়, শুধু HTTP status-এর উপর শাখা দেওয়াই চুক্তিনিরপেক্ষ আচরণ।

## §১. Consumer-চুক্তি (৩ লাইন)

```text
endpoint : POST {GATEWAY_URL}/v1/chat/completions   (OpenAI-compatible)
header   : X-SupremeAI-Key: <SUPREMEAI_API_KEY>
secret   : vault-ফিড env — কখনো কোড/git/log-এ নয় (monolith SECRETS_MODEL চুক্তি)
```

- `GATEWAY_URL` ডিফল্ট `https://supremeai-api.onrender.com` (Render live হলে)
- মডেল `"auto"` দিন — provider নির্বাচন gateway-র কাজ; নির্দিষ্ট মডেলও চলে
  (`/v1/models`-এ সক্রিয় তালিকা — §০.৪)

## §২. Key-জীবনচক্র (monolith key-plane-নিয়ন্ত্রিত)

1. **issue** — monolith admin UI (`/api/api-keys/create`, JWT-gated) → plaintext
   একবারই দেখাবে
2. **store** — Infisical vault-এ (`SUPREMEAI_API_KEY` বা `<CONSUMER>_SUPREMEAI_API_KEY`)
3. **consume** — Render/env/vault-injection → `X-SupremeAI-Key`
4. **rotate/revoke** — monolith-এই; gateway-তে ৩০০s ক্যাশ-TTL-এর মধ্যে প্রতিফলিত
   (keyplane ঐক্য — নতুন key-code নেই)

> নোট: vault-এর বর্তমান `SUPREMEAI_API_KEY` monolith key-plane-ইস্যুকৃত নয়
> (legacy) — প্রথম প্রকৃত consumer-নিবন্ধনের সময় key-plane-থেকে নতুন issue করে
> প্রতিস্থাপন করা হবে।

## §৩. Error-semantics (সৎ-চুক্তি)

| HTTP | অর্থ | consumer-করণীয় |
|---|---|---|
| 401 | key অবৈধ/বাতিল/মেয়াদোত্তীর্ণ | retry নয় — key যাচাই |
| 429 | per-key সীমা (`rate_limit_rps × window`) | Retry-After সম্মান |
| 502 | fallback-chain শেষ — সব provider ব্যর্থ | কিছুক্ষণ পরে retry |
| 503 | keyplane/অবকাঠামো অপ্রাপ্য | retry-যোগ্য (client নিজেই করে) |

বিস্তারিত status-সারণি ও error-body নোট: §০.৬।

## §৪. Python client (zero-dependency)

```python
import sys; sys.path.insert(0, "examples")
from gateway_client import chat
out = chat([{"role": "user", "content": "ping"}])   # env: SUPREMEAI_API_KEY
print(out["choices"][0]["message"]["content"])
```

CLI one-shot: `python3 examples/gateway_client.py --prompt "ping"`

## §৫. Agent-consumers

- agent-identity-প্রতি আলাদা key (`<AGENT>_SUPREMEAI_API_KEY`) — quota-অ্যাট্রিবিউশন
  monolith key-plane-এ (usage log-এ `key_id`)
- agent মারা গেলে key revoke — অন্য agent অপ্রভাবিত
- provider-key agent-এর হাতে কখনোই যায় না — এটাই gateway-র অস্তিত্বের কারণ

## §৬. GitHub-automation consumers

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

## §৭. Migration-checklist (নতুন consumer)

- [ ] monolith admin-এ key issue (scopes-সহ) → vault-এ রাখা
- [ ] §০ কুইকস্টার্টের যেকোনো একটি snippet দিয়ে smoke-test (`curl` বা
      `python3 examples/gateway_client.py --prompt ping`)
- [ ] consumer-এর error-handling §৩-এর টেবিল মেনেছে কিনা
- [ ] GitHub-automation হলে §৬-র non-blocking নীতি মেনেছে কিনা
