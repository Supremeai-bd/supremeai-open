# MCP Tower cURL / HTTP Test Suite

Ready-to-run scripts that exercise the **real** SupremeAI MCP Tower HTTP
endpoints — no SDK, no credentials. Task: #49.

| File | Platform | Runner |
|---|---|---|
| `health.sh` | Linux · macOS | `bash health.sh [command] [tool-name]` |
| `health.ps1` | Windows PowerShell 5.1+ | `powershell -ExecutionPolicy Bypass -File health.ps1 [-Cmd command] [-Tool tool-name]` |

Default target: `https://supremeai-mcp-tower.onrender.com` — override with
`MCP_TOWER_URL` (environment variable, honored by both scripts).

## What each command validates

| Command | Endpoint | Validates |
|---|---|---|
| `health` | `GET /health` | Service reachable; honest aggregate status present (`ok`/`degraded` → HTTP 200, `outage` → HTTP 503 — the Tower reports itself honestly, per graceful-degradation doctrine) |
| `sse` | `GET /sse` | Legacy SSE transport handshake: bounded session accepted and `event: endpoint` received (MCP SDK `SSEServerTransport`) |
| `tools` | `POST /mcp` | Streamable JSON-RPC handshake: `initialize` → `mcp-session-id` header captured → `notifications/initialized` → `tools/list` returns the tool registry; `bridge.guide` visibility proves the zero-credential guest scope |
| `call` | `POST /mcp` | `tools/call` with a real registered tool — default `system.summary`, second call `bridge.guide`; `isError:true` fails the test |

`all` (default) runs the full sequence: health → sse → tools → call
`system.summary` → call `bridge.guide`.

## Examples

```bash
bash health.sh                    # full suite
bash health.sh health             # single check
bash health.sh call bridge.guide  # one specific tool
MCP_TOWER_URL=http://localhost:8080 bash health.sh   # against a local Tower
```

```powershell
powershell -ExecutionPolicy Bypass -File health.ps1
powershell -ExecutionPolicy Bypass -File health.ps1 -Cmd call -Tool bridge.guide
```

## Exit codes

`0` all checks passed · `1` one or more checks failed · `2` usage error ·
`3` (`health.sh` only) curl missing / network failure.

## Notes

- **Zero credentials:** the Tower auto-registers tokenless connections as guest
  viewers with read-only scopes (zero-manual-registration) — these scripts
  never need an API key.
- **Dependencies:** `health.sh` needs only `curl` (present on macOS/Linux by
  default); `health.ps1` needs only built-in PowerShell cmdlets.
- The `mcp-session-id` capture mirrors what real MCP clients do
  (`initialize` → header → `notifications/initialized`), so a passing
  `tools`/`call` check proves the full streamable-MCP session lifecycle.
- Tool names are the server's registered names (`system.summary`,
  `bridge.guide`, `bridge.work_queue`, …) — see
  `infrastructure/mcp-control-plane/src/tools/`.
- **Known live quirk (documented by this suite):** `tools/list` advertises the
  dotted names (`bridge.guide`) while the call registry registers them
  underscore-sanitized (`bridge_guide` — the `server.tool` wrapper in
  `infrastructure/mcp-control-plane/src/index.ts` replaces `.` with `_`).
  The scripts therefore try the advertised name first and retry the
  call-registry variant on "not found", reporting the mismatch as a `NOTE`.
  Fixing that list/call divergence Tower-side is a maintainer follow-up.
