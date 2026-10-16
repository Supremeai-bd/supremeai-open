# SupremeAI SDKs — publishable packages

Official, registry-ready SDK clients for the **SupremeAI MCP Tower**, packaged
per the issue-#338 contract from the validated reference implementations in
[`examples/`](https://github.com/Supremeai-bd/supremeai-open/tree/main/examples)
(PR #318 TypeScript, PR #319 Python).

| Package | Path | Registry name | Status |
| ------- | ---- | ------------- | ------ |
| Python  | [`sdk/python/`](./python/)   | [`supremeai-sdk-py`](https://pypi.org/project/supremeai-sdk-py/) | packaging complete, publish pending |
| TypeScript | [`sdk/typescript/`](./typescript/) | [`@supremeai/sdk`](https://www.npmjs.com/package/@supremeai/sdk) | packaging complete, publish pending |

## Shared contract (both SDKs)

- **Zero runtime dependencies** — Python: stdlib `asyncio` only; TypeScript:
  `fetch`/`globalThis` only (no `@types/node`).
- **SSE streaming** aligned with `docs/MCP_CONNECT.md` §3 frame grammar;
  terminal frames (`agent:done` / `agent:error`) end streams; a seq gap is
  the consumer's resync signal per `api-schemas/websocket-events.schema.json`.
- **Tool calling** via JSON-RPC `tools/call` with `invocation_id` correlation
  echoed on every result envelope.
- **Honest error taxonomy** — 401 auth / 403 forbidden (default-deny RBAC) /
  404 not-found / 429 rate-limited carrying `Retry-After`; transport failures
  surface as retryable envelopes, never silent.
- **Transport etiquette** — `?client=` identity, credentials never in URLs,
  offline-safe module load (network I/O only on awaited client methods).

## Verification (issue #338 Verification Contract)

```bash
# Boot smoke (contract path; see sdk/python/client.py shim note)
python -m py_compile sdk/python/client.py

# Python test harness (SSE parsing, tool serialization, error translation)
pytest sdk/tests

# TypeScript dual-build + node:test harness
cd sdk/typescript && npm install && npm test
```

> Publishing to PyPI/npm is an operator action requiring registry credentials;
> this change ships the complete package configuration (metadata, dual builds,
> typed exports, test harnesses) so publishing is a single `twine upload` /
> `npm publish` away.
