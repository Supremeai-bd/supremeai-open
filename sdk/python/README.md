# supremeai-sdk-py

Official async Python SDK for the **SupremeAI MCP Tower** — the publishable,
packaged form of the validated reference implementation
[`examples/sdk-client-py`](https://github.com/Supremeai-bd/supremeai-open/tree/main/examples/sdk-client-py)
(issue #33, landed by PR #319), delivered per the issue-#338 packaging
contract.

## Install

```bash
pip install supremeai-sdk-py
```

Zero runtime dependencies: stdlib `asyncio` only (Python ≥ 3.11). Fully
typed (PEP 561 `py.typed` shipped).

## Quick start

```python
import asyncio
from supremeai_sdk import SupremeAIClient, TaskDispatchRequest, ToolInvocation

async def main():
    client = SupremeAIClient()  # tower URL via SUPREMEAI_MCP_TOWER_URL or default

    health = await client.health()          # credential-free probe
    print(health)

    res = await client.dispatch_task(TaskDispatchRequest(
        task_id="task-1",
        issue="1",
        objective="Ship the smallest safe change",
        touching_files=("src/feature.py",),
    ))
    print(res.tier, res.route)              # router decision, primary provider first

    tool = await client.invoke_tool(ToolInvocation(
        tool="repo_read", arguments={"path": "docs/"},
    ))
    print(tool.status, tool.duration_ms)

asyncio.run(main())
```

## Streaming status (SSE)

```python
async for frame in client.stream_sse("task-1"):
    print(frame.seq, frame.event)   # terminal agent:done / agent:error end the stream
```

## Error taxonomy (honest failures)

| Status | Exception       | Notes                              |
| ------ | --------------- | ---------------------------------- |
| 401    | `SdkAuthError`  | credential invalid — do not retry  |
| 403    | `SdkForbidden`  | default-deny RBAC                  |
| 404    | `SdkNotFound`   | stale session — re-initialize      |
| 429    | `SdkRateLimited`| carries `retry_after_s`            |

Transport-level failures (`OSError`) surface as **retryable** error envelopes
from `invoke_tool` — never silent.

## CLI

```bash
supremeai-sdk --self-test              # offline mock-MCP harness (15 checks)
python -m supremeai_sdk.client --health --base-url https://...
```

## Tests

```bash
pytest sdk/tests        # from the repository root
```
