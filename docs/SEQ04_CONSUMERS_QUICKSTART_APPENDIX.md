# Seq 0.4 (#404) — Developer Quickstart & Link-Integrity Handoff Appendix

> **Task:** `bridge-20261016-docs-quickstart-404` · **Issue:** #404 (Phase 0 — Seq 0.4, P2-medium, `schemas-contracts`)
> **Agent:** zai-autonomous-contributor (Z.ai Code) · **Base:** `origin/main` `b019b1d` · **Scope contract:** `README.md`, `docs/CONSUMERS.md`, `ECOSYSTEM_MAP.md` + repo-wide link integrity
> **Lanes used:** (1) new CI tool `scripts/ci/validate_links.py` (pure-new file, rides the bridge) · (2) THIS appendix — byte-exact content for the pre-existing scope files, applied by the maintainer.

---

## §0 Why an appendix lane for the scope files

The three scope files are **pre-existing** content. Bridge doctrine (proven by WO #415's r2
intake rejection: `ECOSYSTEM_MAP.md` diverged at `:53` on private main, `docs/ZERO_ADMIN_GUIDE.md`
absent there) is that hunks against pre-existing files die on **private-main drift** the public
side cannot observe. This appendix therefore carries:

- **content-anchored repair hunks** (exact current line → exact replacement line; line numbers
  are advisory, the byte content is the anchor), and
- **one full-file replacement** (`docs/CONSUMERS.md`, Appendix C) — drift-proof by construction,
  applied as a whole-file write wherever the authoritative copy lives.

**Mirror-parity hazard (must-read before applying Appendix C):** `README.md` line 56 declares
`docs/CONSUMERS.md` a *"mirror of `supremeai-api/docs/CONSUMERS.md`"* byte-parity-checked by the
federation integration CI. Applying Appendix C **only** to the public repo would flip that mirror
into a fail-closed drift. **Application order:** land the Appendix C content on the private source
plane (`supremeai-api/docs/CONSUMERS.md`) first — or simultaneously — then let the mirror
mechanism (or a matching public apply) propagate. The maintainer owns the plane decision; the
content is plane-neutral and carries no private material.

---

## §1 Audit results (evidence, reproducible)

Run the delivered tool — on pristine `b019b1d` it deterministically reports:

```text
$ python scripts/ci/validate_links.py
validate_links: scanned 33 markdown file(s) under <repo>
  local links: 126 · anchors: 0 · external: 33 (skipped; use --check-remote)
  BROKEN examples/curl-tests/README.md:66 -> ../docs/CONSUMERS.md (local path does not exist)
  BROKEN examples/curl-tests/README.md:69 -> ../docs/AGENT_PORTAL_SPEC.md (local path does not exist)
  BROKEN examples/curl-tests/README.md:74 -> ../docs/AGENT_PORTAL_SPEC.md (local path does not exist)
  BROKEN examples/curl-tests/README.md:75 -> ../docs/ZERO_ADMIN_GUIDE.md (local path does not exist)
  BROKEN examples/curl-tests/README.md:76 -> ../docs/FAQ.md (local path does not exist)
  RESULT: 5 broken link(s)          # exit 1 — fail-closed
```

Root cause (single class): `examples/curl-tests/README.md` (landed via #49/PR #298) uses
`../docs/…` relative depth — the file sits at `examples/curl-tests/`, so the correct prefix is
`../../docs/…`. The same file's `../../AGENTS.md` links (lines 68/73) already use the correct
depth, confirming a miscount on the `docs/` links only.

**Stale cross-repo / stale-anchor prose references** (the issue's "broken cross-repo anchors"
class — prose, not markdown links, hence invisible to the link tool; verified manually):

| Location | Reference | Finding | Repair |
|---|---|---|---|
| `README.md:5` | `roadmap §4.3` | private plan doc, not present anywhere in this repo | Appendix B hunk B1 — drop dead anchor, point to `ECOSYSTEM_MAP.md` |
| `README.md:85` | `roadmap §21` | same class | Appendix B hunk B2 — drop dead anchor, keep informative part |
| `docs/CONSUMERS.md:6` | `§২২` (and §22 semantics) | monolith plan section — the consumer doc has no §22 | superseded by Appendix C full replacement |
| `docs/CONSUMERS.md:13` | `SECRETS_MODEL.md` | referenced doc absent from this repo (private-plane doctrine doc) | superseded by Appendix C (reworded to vault doctrine without dead pointer) |

**Audited-clean (honest negatives):**

- `ECOSYSTEM_MAP.md` — **0 defects**: all 8 markdown links resolve; every referenced local file
  exists (`AGENTS.md`, `AGENT_RULES.md`, `docs/CONTRIBUTING.md`, `docs/OPS_ACTIONS_QUOTA_RUNBOOK.md`,
  `scripts/ci/boundary_sanitization_guard.py`, `.github/actions/` composites); the prose
  `AGENTS.md §2.3` anchor exists (`AGENTS.md:122`). No hunks proposed — the issue's scope boundary
  includes this file, but a zero-defect file gets zero edits (surgical-scope doctrine).
- All 5 named scope files in §1's tool table are the ONLY dead links repo-wide (the tool scans
  all 33 markdown files).

**External URL probes** (run 2026-10-16, from the #403 evidence line too):

| URL | Probe | Reading |
|---|---|---|
| `https://supremeai-studio-live.vercel.app` | HTTP 200 | live |
| `https://supremeai-mcp-tower.onrender.com` | HTTP 200 | live |
| `https://supremeai-api.onrender.com` | HTTP 404 at `/` | **host alive, routes not yet mounted** — consistent with the gateway Phase-0 sequence (#401/#402 pending); the quickstart carries an honest live-status banner instead of pretending otherwise |

---

## §2 Appendix A — link repairs for `examples/curl-tests/README.md`

Five content-anchored hunks. Each `old:` line is byte-verified against `b019b1d`.

```diff
--- examples/curl-tests/README.md (hunk A1, line 66)
-  [`docs/CONSUMERS.md`](../docs/CONSUMERS.md)).
+  [`docs/CONSUMERS.md`](../../docs/CONSUMERS.md)).

--- examples/curl-tests/README.md (hunk A2, line 69)
-  [`docs/AGENT_PORTAL_SPEC.md`](../docs/AGENT_PORTAL_SPEC.md).
+  [`docs/AGENT_PORTAL_SPEC.md`](../../docs/AGENT_PORTAL_SPEC.md).

--- examples/curl-tests/README.md (hunk A3, line 74)
-- [docs/AGENT_PORTAL_SPEC.md](../docs/AGENT_PORTAL_SPEC.md) — portal architecture
+- [docs/AGENT_PORTAL_SPEC.md](../../docs/AGENT_PORTAL_SPEC.md) — portal architecture

--- examples/curl-tests/README.md (hunk A4, line 75)
-- [docs/ZERO_ADMIN_GUIDE.md](../docs/ZERO_ADMIN_GUIDE.md) — autonomous landing handbook
+- [docs/ZERO_ADMIN_GUIDE.md](../../docs/ZERO_ADMIN_GUIDE.md) — autonomous landing handbook

--- examples/curl-tests/README.md (hunk A5, line 76)
-- [docs/FAQ.md](../docs/FAQ.md) — troubleshooting validation errors
+- [docs/FAQ.md](../../docs/FAQ.md) — troubleshooting validation errors
```

Acceptance after apply: `python scripts/ci/validate_links.py` → `RESULT: 0 dead links — clean`, exit 0.

---

## §3 Appendix B — stale-anchor repairs for `README.md`

```diff
--- README.md (hunk B1, line 5)
-This repository is the **public boundary** of the SupremeAI federation (roadmap §4.3 / Phase 8 foundation).
+This repository is the **public boundary** of the SupremeAI federation (Phase 8 foundation — architecture directory: [`ECOSYSTEM_MAP.md`](./ECOSYSTEM_MAP.md)).

--- README.md (hunk B2, line 85)
-(`supremeai-infrastructure` → `federation-integration.yml`, roadmap §21). If a mirror drifts from its
+(`supremeai-infrastructure` → `federation-integration.yml`). If a mirror drifts from its
```

Rationale: the private plan's §-numbering is unreachable from the public repo (the class the
issue calls "obsolete repo references"). B1 keeps the sentence's meaning and adds a live pointer
to the architecture directory; B2 keeps the operational fact (which CI performs byte-parity)
and drops only the dead section pointer.

`docs/CONSUMERS.md`'s stale anchors (`§২২`, `SECRETS_MODEL.md`) are resolved wholesale by
Appendix C — no intermediate hunks are offered for that file.

---

## §4 Appendix C — full replacement content for `docs/CONSUMERS.md`

The issue's centerpiece: a frictionless, copy-paste, 5-minute quickstart. Every fact below is
grounded — endpoint/header/`model: auto` and the response shape from
`api-schemas/gateway.openapi.yaml`; the error classes and the retry-only-502/503 +
`Retry-After` policy from `examples/gateway_client.py` (the byte-mirror reference client) and the
existing consumer contract; the streaming `[DONE]` convention from the OpenAI-compatibility
doctrine and the Seq 0.3 acceptance contract (#403). **Nothing is documented that the gateway
does not already contract** — absence of rate-limit quota headers is stated as absent, not invented.

Mirror-parity: apply to the authoritative plane(s) per §0.

````markdown
# Consumers — SupremeAI Gateway quickstart (copy-paste contract)

> **English.** Everything needed to call the SupremeAI Gateway in under 5 minutes: one
> endpoint, one header, OpenAI-compatible bodies. Provider routing, failover and provider
> credentials stay server-side — a provider key never reaches any consumer.
>
> **বাংলা।** একটি endpoint, একটি header (`X-SupremeAI-Key`) — বাকি সব (provider নির্বাচন,
> failover, credential) gateway-র দায়িত্ব। আপনার key কোড/git/log-এ কখনো যাবে না।

**Live status (honesty doctrine):** `https://supremeai-api.onrender.com` is the contract base
URL. Route activation is tracked by the Phase-0 gateway sequence (#401/#402) — until those
close, a 404/503 on a route means *not yet mounted*, not *your request is wrong*.

## 1. The 3-line contract

```text
endpoint : POST {GATEWAY_URL}/v1/chat/completions   (OpenAI-compatible)
header   : X-SupremeAI-Key: <SUPREMEAI_API_KEY>
secret   : vault-fed env var only — never in code/git/logs
```

`GATEWAY_URL` defaults to `https://supremeai-api.onrender.com`. Send `"model": "auto"` and let
the gateway's router choose; any id from `GET /v1/models` (§3) is also valid.

## 2. Five-minute quickstart

### curl (single command)

```sh
curl -sS "$GATEWAY_URL/v1/chat/completions" \
  -H "X-SupremeAI-Key: $SUPREMEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"ping"}]}'
```

### Python — official `openai` SDK (drop-in)

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://supremeai-api.onrender.com/v1",
    api_key=os.environ["SUPREMEAI_API_KEY"],  # vault-fed; never hardcode
)

out = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "ping"}],
)
print(out.choices[0].message.content)

# streaming — OpenAI SSE convention; frames end with `data: [DONE]`
stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Count 1 to 5."}],
    stream=True,
)
for chunk in stream:
    for choice in chunk.choices:
        if choice.delta.content:
            print(choice.delta.content, end="", flush=True)
```

### Python — zero-dependency mirror client (no SDK install)

```python
import sys; sys.path.insert(0, "examples")
from gateway_client import chat                    # repo file: examples/gateway_client.py
out = chat([{"role": "user", "content": "ping"}])  # env: SUPREMEAI_API_KEY
print(out["choices"][0]["message"]["content"])
```

CLI one-shot: `python3 examples/gateway_client.py --prompt "ping"`

### TypeScript — native `fetch`

```ts
const res = await fetch("https://supremeai-api.onrender.com/v1/chat/completions", {
  method: "POST",
  headers: {
    "X-SupremeAI-Key": process.env.SUPREMEAI_API_KEY,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    model: "auto",
    messages: [{ role: "user", content: "ping" }],
  }),
});
if (!res.ok) throw new Error(`gateway error ${res.status} — see the error table`);
const data = await res.json();
console.log(data.choices[0].message.content);
```

### TypeScript — official `openai` SDK

```ts
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://supremeai-api.onrender.com/v1",
  apiKey: process.env.SUPREMEAI_API_KEY,
});

const out = await client.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "ping" }],
});
console.log(out.choices[0].message.content);
```

## 3. Models — GET /v1/models

```sh
curl -sS "$GATEWAY_URL/v1/models" -H "X-SupremeAI-Key: $SUPREMEAI_API_KEY"
```

```json
{ "object": "list",
  "data": [ { "id": "<model-id>", "object": "model", "owned_by": "supremeai" } ] }
```

- The list mirrors the gateway's routing policy (config-driven) — it is the only authoritative
  model inventory; this documentation deliberately never hardcodes model ids.
- `"model": "auto"` delegates the choice to the router (recommended).

## 4. Errors — the honest 5-class contract

Status codes are the stable error surface. The reference client treats error **bodies as opaque
diagnostic text** — branch on codes, do not parse bodies.

| HTTP | Meaning | Consumer action |
|---|---|---|
| 401 | key invalid / revoked / expired | never retry — fix the key |
| 403 | key lacks required scope | never retry — request the scope |
| 429 | per-key limit exceeded (`rate_limit_rps × window`) | never hammer — honour `Retry-After` (seconds) when present |
| 502 | fallback chain exhausted — every provider failed | retry later (the reference client retries 502/503 only) |
| 503 | keyplane / infrastructure unavailable | retryable (the reference client retries) |

Any other code: `gateway error <code>` — non-retryable by default.

## 5. Rate limits

- Limits are **per key**, config-driven: `rate_limit_rps × window`.
- On 429, the only contracted back-off signal is the `Retry-After` header (seconds) — respect it.
  Additional rate-limit headers (remaining-quota counters and the like) are **not** part of the
  v1 contract yet; none are documented here on purpose (nothing is promised that the gateway
  does not already emit).
- Per-consumer attribution: give every agent/automation its own key
  (`<CONSUMER>_SUPREMEAI_API_KEY`) — usage is attributed per `key_id`, and revoking one key
  never affects another consumer.

## 6. Key lifecycle

1. **issue** — admin UI (`/api/api-keys/create`, JWT-gated) → plaintext shown exactly once
2. **store** — Infisical vault (`SUPREMEAI_API_KEY` or `<CONSUMER>_SUPREMEAI_API_KEY`)
3. **consume** — vault-injected env → `X-SupremeAI-Key` header
4. **rotate/revoke** — admin plane; reflected by the gateway within its 300 s key-cache TTL

## 7. GitHub-automation consumers

```yaml
# .github/workflows/ai-note.yml (illustration — not a shipped workflow)
- name: AI advisory note
  env:
    SUPREMEAI_API_KEY: ${{ secrets.SUPREMEAI_API_KEY }}
  run: |
    python3 examples/gateway_client.py \
      --prompt "Summarize this diff for humans:" || echo "advisory failed — non-blocking"
```

**Iron rule:** deterministic protections remain authoritative. AI output is advisory input
only — a PR gate / evaluator / merge decision must never depend on an AI call. If the call
fails, the workflow proceeds non-blocking (`|| true` pattern).

## 8. Migration checklist (new consumer)

- [ ] key issued via admin UI (with scopes) → stored in the vault
- [ ] smoke test passes: `python3 examples/gateway_client.py --prompt ping`
- [ ] error handling matches §4 (codes, not bodies; retry 502/503 only)
- [ ] the 429 path honours `Retry-After` (§5)
- [ ] GitHub automation follows the non-blocking iron rule (§7)
````

---

## §5 Verification-contract mapping (issue's 3 tiers → commands)

| Tier | Issue contract | Delivered mechanics | Expected result after apply |
|---|---|---|---|
| 1 | `git grep -n "CONSUMERS.md" README.md` | unaffected — Appendix C keeps/never removes the README references | matches (2 hits, as on `b019b1d`) |
| 2 | `python scripts/ci/validate_links.py` | **delivered** — stdlib-only, deterministic, fail-closed (exit 0/1/2) | pre-apply: 5 broken (exit 1, this §1) · post-apply: `0 dead links — clean` (exit 0) |
| 3 | snippets parse cleanly; 0 dead links repo-wide | battery parsed every snippet (sh/Python/TS/YAML) before submission; repo-wide scan = 33 files | all snippets syntactically valid; 0 dead links |

## §6 Battery summary (full evidence in the WO)

- Tool on pristine `b019b1d`: exactly the 5 known-broken links, exit 1 (fail-closed) — 33 files, 126 local + 33 external targets accounted for.
- Post-appendix simulation (scratch apply of A1–A5 + B1–B2 + Appendix C): exit 0, `0 dead links — clean`.
- Unit matrix: anchor slugs (incl. Bengali marks), duplicate-heading `-1` suffixes, cross-file anchors, fenced-block immunity, unreadable-file operational error (exit 2), `--json` schema, `--files`/`--root` determinism, double-collect regression guard.
- Snippet syntax: curl block `bash -n` clean; Python blocks `ast.parse` clean; TS blocks `node --check` clean; YAML block `yaml.safe_load` clean.
- Contract-fidelity: Appendix C facts cross-checked against `api-schemas/gateway.openapi.yaml` + `examples/gateway_client.py` (header, endpoints, `model: auto`, error classes, retry policy); no invented headers/fields/schemas.
- Secret scan (10 families): 0 hits. UTF-8 roundtrip: OK. Boundary guard `--check`: 0 violations (post-commit).

*End of appendix — everything above is ready for verbatim maintainer application.*
