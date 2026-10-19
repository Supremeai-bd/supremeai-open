# SupremeAI VS Code Extension

Lightweight AI coding assistant + federation bridge for SupremeAI.

## Quick Start

1. Install dependencies: `npm install`
2. Compile: `npm run compile`
3. Run tests: `npm test`
4. Press F5 in VS Code to launch the Extension Development Host.

## Configuration

Open Settings → SupremeAI:

- `supremeai.gatewayUrl` — Gateway base URL (default `http://127.0.0.1:8080`)
- `supremeai.apiKey` — `X-SupremeAI-Key` (default test key)
- `supremeai.model` — default model (`auto`, `llama-3.1-8b-instant`, `gpt-4o-mini`, `claude-sonnet-4-5`)
- `supremeai.towerUrl` — MCP Control Tower URL
- `supremeai.autoRefreshSeconds` — status bar poll cadence

For a zero-cost local run, start the gateway in mock mode:

```
SUPREMEAI_GATEWAY_MOCK_PROVIDER=1 python -m uvicorn gateway.serve:app --port 8080
```

## Features

- **Chat Sidebar** (activity bar → SupremeAI) with model selector.
- **Ask about Selection** (`Ctrl+Shift+I` / `Cmd+Shift+I`) — sends selection + question to the gateway; offers to apply a returned code block.
- **Code Actions** — "SupremeAI: Explain/Fix selection" on any selection.
- **Federation Bridge** — dispatch tasks, view PR runway, emergency kill-switch.
- **Status Bar** — live federation health & latency.

## Run the gateway (real providers)

Set `SUPREMEAI_PROVIDER_BASE_<PROVIDER>` and `SUPREMEAI_PROVIDER_KEY_<PROVIDER>` env vars (groq/openai/anthropic/gemini), then:

```
python -m uvicorn gateway.serve:app --port 8080
```

## License

Proprietary — SupremeAI Federation.
EOF