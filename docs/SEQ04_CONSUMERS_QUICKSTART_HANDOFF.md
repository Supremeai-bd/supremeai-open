# Seq 0.4 — CONSUMERS Quickstart Overhaul & Link-Integrity Hand-off (#404, r2)

> Task: `bridge-20261017-seq04-consumers-quickstart-r2` · Issue: #404 (P2-medium,
> handoff:coder, repo:open; claim: operator-set `status:claimed` label AND
> `<!-- atomic-claim -->` marker comment on #404 — both planes of
> `has_active_claim()` PASS per invariant #430) · Parent epic: #400 (Commercial
> Market Launch Master Roadmap, Phase 0) · Base: `8e5ed59` (origin/main at
> build time; CONSUMERS.md md5 `726232f2…` byte-identical since `30cb827` —
> verified) · Lane: pure-new-file payload (2 files) + byte-exact operator
> blocks (proven 2×-landed pattern: studio de-prefix r2, zero-issue doctrine).

## §0 r1 → r2 delta log (why this order was resubmitted)

r1 (`bridge-20261017-seq04-consumers-quickstart`, WO #434) was rejected with
two independent, measured causes; both are structural lessons, not content
defects — the payload itself passed every gate:

1. **Two-Tier Ingress Invariant (#430) violation.** r1 was submitted with NO
   active claim on task #404 (no `status:claimed`/`status:in-progress` label,
   no `<!-- atomic-claim -->` comment). Admin rejection, wave 1: "No claim →
   No branch; No branch → No push." r2 rides the operator-set claim planes:
   after the stale releaser expired the r1-era labels, the operator re-set
   `status:claimed` AND posted a fresh `<!-- atomic-claim -->` marker comment
   on #404 (live-verified at r2 build — both planes PASS `has_active_claim()`;
   fresh marker also satisfies the 30-min stale-expiry rule). The tower's
   atomic-claim step (`claimTaskIssue`) is merged as a hand-off (control-plane
   PR #8: doc+test only) but its `bridge.tools.ts` §2 diff is pending operator
   application — NOT live on the deployed schema, so this order does not
   depend on it.
2. **Private-main filename collision.** The intake bot rejected r1's patch
   with `scripts/ci/validate_links.py: already exists in working directory`
   on Supremeai-bd/supremeai@main — a parallel fleet agent landed the same
   generic filename first (public main does NOT have the file; private ≠
   public state). r2 renames the tool to `scripts/ci/validate_md_links_seq04.py`
   — scoped, collision-proof naming; zero references to the old name remain
   in the payload.

3. **delta-3 (r2 battery improvement):** the error-shape JSON example carried
   its Bengali comment INSIDE the `json` fence (`// …`) — strictly invalid
   JSON. r1's battery did not json-validate; r2's does, it caught the drift,
   and the comment moved out of the fence as a markdown lead-in (block now
   strictly valid). Everything else is unchanged content discipline: §2
   below is spliced byte-identically from the committed r1 branch doc (same
   proposed replacement, minus delta-3), and all audits/probes were re-run
   fresh at r2 build time.

## §1 Defect evidence (all measured on `8e5ed59`)

**(a) docs/CONSUMERS.md capability gaps vs the #404 contract:**

| #404 requirement | State before this order |
|---|---|
| curl single-command chat test | ABSENT — contract is prose-only (§১ code block has no runnable call) |
| Python drop-in `OpenAI(base_url=…, api_key=…)` + streaming | ABSENT — only the zero-dependency `gateway_client` path exists |
| TypeScript native fetch / official SDK snippet | ABSENT entirely |
| List available models | Passing mention of `/v1/models` only; no endpoint section, no response shape |
| Rate-limit header explanations | `Retry-After` mentioned in §৩ table only; no consumer guidance |
| Error response schemas | Status table only; no body-shape note, no OpenAPI traceability |

**(b) Stale reference (obsolete repo reference class):** `docs/CONSUMERS.md`
line 13 cites `SECRETS_MODEL.md` — the file does not exist anywhere in this
repository (`git grep SECRETS_MODEL` → only that one hit; `ls` confirms absent).
It reads like a local doc link but is a private-monolith doc name. Fixed in §2
by rewording to "monolith SECRETS_MODEL চুক্তি" (no pseudo-path).

**(c) Live-gateway probe (honesty evidence; r1 build 2026-10-16T20:09Z,
re-verified at r2 build 2026-10-16T23:28Z):**

```text
GET  /healthz                  → 404
GET  /v1/models                → 404
POST /v1/chat/completions      → 404
response header: x-render-routing: no-server   ← Render service UNBOUND
```

The Render deployment behind `https://supremeai-api.onrender.com` is still
not serving at r2 build time — the gateway fix (PR #283, /healthz + CORS) is
merged but has not reached the Render runtime yet (deployment cadence,
pipeline Rule 17: scheduled auto-deploy). Consequence for this order is
unchanged from r1: the §0 quickstart ships **contract-true** (byte-accurate
to `api-schemas/gateway.openapi.yaml`) with an explicit live-status note;
**no snippet claims a verified live call** (that belongs to Seq 0.3's E2E
suite, #403, with real keys). Fabricating "verified working" evidence would
violate the fail-honest doctrine and the 3-tier verification contract. When
the deploy lands, this note self-expires — the quickstart text is
deployment-state-agnostic by design.

**(d) Scoped files README.md / ECOSYSTEM_MAP.md:** link audit CLEAN (§4) —
**no edits required**; they are intentionally untouched (scope discipline:
only docs/CONSUMERS.md changes in this order).

## §2 Byte-exact full replacement — `docs/CONSUMERS.md`

Apply the block between the BEGIN/END markers as the ENTIRE new file content
(no merging with the old body; the old §১–§৭ content is preserved inside with
numbering intact and exactly two deltas: added §০ quickstart part and the
§1(b) stale-reference rewording; internal cross-references — §০.৪ in §১, §০.৬
in §৩, §০ checklist entry in §৭ — are updated consistently).

#### BEGIN docs/CONSUMERS.md

```markdown
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
```

#### END docs/CONSUMERS.md

## §3 Operator actions (required to land without a red parity gate)

1. **Apply §2** to `docs/CONSUMERS.md` on the branch the bridge opens (or in a
   follow-up operator commit — content is self-contained).
2. **MIRROR-PARITY WARNING (read before merge):** README's artifact table
   declares `docs/CONSUMERS.md` as a **byte-mirror of
   `supremeai-api/docs/CONSUMERS.md`**, and README's drift-protection section
   says the federation integration CI fails closed when a mirror drifts. If
   this public-side replacement lands alone, the private-side mirror will
   drift by definition. Operator must either (a) apply the identical content
   to `supremeai-api/docs/CONSUMERS.md` in the same window, or (b) update the
   mirror registry/row so the parity check tracks the new SSOT. Choosing
   neither will turn a docs improvement into a red CI gate — this warning is
   the reason the whole change rides a reviewable hand-off instead of a
   silent hunk.
3. No README.md / ECOSYSTEM_MAP.md action (audit clean — §4).
4. Optional: apply §6 appendix fixes (outside this order's declared scope).

## §4 Link audit results (scripts/ci/validate_md_links_seq04.py, verbatim)

**Scoped run (the #404 three files):**

```text
validate_md_links_seq04: files=3 dead_links=0 external_probes=off
```

**Scoped run + external probes:**

```text
validate_md_links_seq04: files=3 dead_links=1 external_probes=on
DEAD external  /home/z/workspace/supremeai-open/README.md: https://supremeai-api.onrender.com
```

**Full-repository run (36 markdown files):**

```text
validate_md_links_seq04: files=36 dead_links=5 external_probes=off
DEAD file      /home/z/workspace/supremeai-open/examples/curl-tests/README.md: ../docs/CONSUMERS.md
DEAD file      /home/z/workspace/supremeai-open/examples/curl-tests/README.md: ../docs/AGENT_PORTAL_SPEC.md
DEAD file      /home/z/workspace/supremeai-open/examples/curl-tests/README.md: ../docs/AGENT_PORTAL_SPEC.md
DEAD file      /home/z/workspace/supremeai-open/examples/curl-tests/README.md: ../docs/ZERO_ADMIN_GUIDE.md
DEAD file      /home/z/workspace/supremeai-open/examples/curl-tests/README.md: ../docs/FAQ.md
```

The scoped+external single finding is the live-status fact documented in
§1(c) — the URL is the canonical platform address; deployment unavailability
is tracked by Seq 0.1 / issue #401. The full-repo findings are in
`examples/curl-tests/README.md` — **outside the #404 scope boundary**
(README.md, docs/CONSUMERS.md, ECOSYSTEM_MAP.md); they are documented with
ready-made fix blocks in §6 rather than patched here (atomic-slice
discipline; a follow-up issue can claim them in one sitting).

## §5 3-tier verification contract (as delivered, r2)

| Tier | Contract requirement | Delivered evidence |
|---|---|---|
| Reflection | `git grep -n "CONSUMERS.md" README.md` | README artifact-table row + pointer — both intact and truthful after this order (no README edit needed) |
| Link integrity | `python3 scripts/ci/validate_md_links_seq04.py` | §4: scoped 3 files = 0 dead relative links; repo-wide 5 dead (all out-of-scope, §6); scoped+external = 1 true finding (gateway deploy pending, §1(c)) |
| Docs formatting | snippets parse cleanly | Round-trip: §2 extracted between BEGIN/END markers (12881 B) → all ```python blocks pass `ast.parse` (×2); bash blocks pass `bash -n` (×2); TypeScript blocks pass bun transpile (×2, top-level await accepted); JSON blocks `json.loads` OK (×2); YAML block is the pre-existing §৬ example, unchanged; with replacement applied scoped links 0 dead, original restored byte-identical (md5 `726232f2…` before == after) |

Round-trip discipline: the verification consumed the §2 block **as extracted
from this document**, not the staging copy — what an operator applies is what
was verified.

## §6 Appendix (out-of-scope, ready-made): examples/curl-tests/README.md

Five links use `../docs/…` from `examples/curl-tests/` (resolves to
`examples/docs/…` — nonexistent). Correct depth is `../../docs/…`. Byte-exact
repairs (line : corrected):

```text
:66  ../docs/CONSUMERS.md           → ../../docs/CONSUMERS.md
:69  ../docs/AGENT_PORTAL_SPEC.md   → ../../docs/AGENT_PORTAL_SPEC.md
:74  ../docs/AGENT_PORTAL_SPEC.md   → ../../docs/AGENT_PORTAL_SPEC.md
:75  ../docs/ZERO_ADMIN_GUIDE.md    → ../../docs/ZERO_ADMIN_GUIDE.md
:76  ../docs/FAQ.md                 → ../../docs/FAQ.md
```

After applying, `python3 scripts/ci/validate_md_links_seq04.py` exits 0
repo-wide.

## §7 Non-goals

- No live-call verification of the gateway (deploy pending at build time,
  §1(c); Seq 0.1 #401 owns the repair; Seq 0.3 #403 owns the E2E suite with
  real keys).
- No edits to README.md or ECOSYSTEM_MAP.md (audit clean; scope boundary).
- No curl-tests patch in this order (§6 appendix only; out of scope).
- No rate-limit header invention: only `Retry-After` is contractual per the
  stable OpenAPI; §০.৫ explicitly warns consumers off undeclared headers.
- No auth-header drift: both snippets send the SSOT-declared
  `X-SupremeAI-Key` (the SDK variant additionally sends it via
  `default_headers`; the doc does NOT promise `Authorization: Bearer`
  because the stable contract does not declare it). Provider keys are never
  consumer-visible — Unified Gateway Shield rules 18–22.
