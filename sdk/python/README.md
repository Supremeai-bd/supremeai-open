# SupremeAI Python SDK

Official Python client for the **SupremeAI Unified Gateway**.

## Features

- **Typed Endpoints**: High-level typed client for chat completions, run execution, and health checks.
- **SSE Streaming**: Robust Server-Sent Events parser with reconnection and buffer safety.
- **Resilience**: Automatic retry on 503 transient errors with exponential backoff.
- **Zero Heavy Dependencies**: Pure standard library or optional `httpx` support.

## Installation

```bash
pip install supremeai-sdk
```

## Quick Start

```python
from supremeai.client import GatewayClient

client = GatewayClient(
    base_url="https://supremeai-api.onrender.com",
    bearer_token="your-token"
)

# Check health
health = client.health()
print("Gateway status:", health)
```

## License

MIT License. See [LICENSE](file:///F:/supremeai-open/sdk/LICENSE) for details.
