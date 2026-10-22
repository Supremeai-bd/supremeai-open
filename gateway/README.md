# SupremeAI Gateway — unified provider gateway reference (issue #336)

FastAPI/Starlette implementation of `api-schemas/gateway.openapi.yaml`:
one **SUPREMEAI_API_KEY** consumer credential, provider-agnostic responses,
provider credentials never leave the server side.

## Run

```bash
pip install -r gateway/requirements.txt
export SUPREMEAI_API_KEY_PYTEST="supremeai-key-..."   # key material per owner
uvicorn gateway.serve:app --port 8080  # see gateway/serve.py
```

The default app factory is offline-inert (`create_app(config)` with no
transport) — wire real providers via `SUPREMEAI_PROVIDER_BASE_<P>` /
`SUPREMEAI_PROVIDER_KEY_<P>` env vars; the stdlib asyncio transport then
performs honest HTTP/1.1 round-trips.

## Endpoints (OpenAPI-aligned)

| Route | Auth | Notes |
| ----- | ---- | ----- |
| `GET /health`, `GET /healthz` | none | credential-free probes (OpenAPI `security: []`) |
| `GET /v1/models` | key + `models` scope | enabled models from the routing policy |
| `POST /v1/chat/completions` | key + `chat` scope | OpenAI-compatible; `stream: true` → SSE |

## Wire contracts

- **SSE framing (AC1)** — `event: chat.completion.chunk` + `data: {json}`
  frames, terminal `event: done` + `data: [DONE]`, honest `event: error`
  frames; failover happens ONLY before the first chunk (restarting mid-stream
  would duplicate output — banned).
- **Rate limiting (AC2)** — per-key sliding window; on 429 the standardized
  JSON error contract (`error.type/param/code`) rides with `Retry-After` and
  `X-RateLimit-Limit/Remaining/Reset` headers; success responses carry the
  same `X-RateLimit-*` headers.
- **Provider failover** — config-ordered chain; 429/5xx/401/403 from a
  provider → next endpoint; exhaustion → **502 with a redacted ledger**
  (`providers_tried`), zero silent fallback.
- **Honesty** — `model` names the provider/model that ACTUALLY served the
  request; `usage` is echoed only when the provider reported it.

## Configuration (fail-closed)

`gateway/routing_policy.json` — validated at boot by `gateway/config.py`:
closed 7-provider enum (SSOT with `api-schemas/task-router.schema.json`),
non-empty ordered chains, positive rate limits, `supremeai-key-*` ids whose
SECRET material rides the environment (never committed). Any drift refuses
the boot.

## Tests

```bash
pytest tests/test_streaming_gateway.py -v          # issue Verification Contract
GW_BASE_URL=http://127.0.0.1:8080 sh examples/curl-tests/health.sh gateway
```
