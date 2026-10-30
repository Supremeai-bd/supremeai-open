# MCP Tower cURL / HTTP smoke tests (#49)

Ready-to-run endpoint checks for the SupremeAI MCP Control Tower — no SDK, no
credentials, no dependencies beyond `curl` (POSIX) or PowerShell 5.1+/7+
(Windows). Useful as a first diagnostic before any deeper integration work.

**Target:** `https://supremeai-mcp-tower.onrender.com` (override with
`BASE_URL`; local dev: `http://localhost:8080` or whatever `npm run dev` binds).

## Files

| File | Runtime | Covers |
|---|---|---|
| `health.sh` | POSIX sh + curl (Linux, macOS, WSL) | health, SSE handshake, tools/list, tools/call |
| `health.ps1` | PowerShell 5.1+/7+ (Windows) | same subcommands, same output contract |

Both scripts expose the **same subcommands** and the same fail-closed contract
(exit 0 = all requested checks passed, exit 1 = at least one failed — no
silent skips, matching repo doctrine).

## Quick start

```sh
# Linux / macOS / WSL
sh health.sh                # health check (default)
sh health.sh all            # full sweep: health + SSE + tools/list + 2 tool calls
```

```powershell
# Windows PowerShell
.\health.ps1                # health check (default)
.\health.ps1 all            # full sweep
```

## Subcommands

| Subcommand | What it proves |
|---|---|
| `health` | `GET /health` returns 200 with a status payload |
| `sse` | `GET /sse` opens the SSE transport and emits `event:`/`data:` frames (bounded read, no infinite hang) |
| `tools-list` | Streamable MCP handshake over `POST /mcp`: `initialize` → `notifications/initialized` → `tools/list` returns a tools frame |
| `tool-call <name>` | `initialize` → `tools/call` for a public zero-arg tool: `system_summary`, `bridge_guide` |
| `all` | everything above in one run |

## Environment overrides

| Variable | Default | Notes |
|---|---|---|
| `BASE_URL` | `https://supremeai-mcp-tower.onrender.com` | point at any tower deployment |
| `MCP_PROTOCOL_VERSION` | `2025-03-26` | MCP protocol revision negotiated in `initialize` |
| `CURL_TIMEOUT` | `20` | seconds per request (also bounds the SSE read) |

## Notes & troubleshooting

- The `POST /mcp` flow is the **Streamable MCP** transport: `initialize`
  captures the `mcp-session-id` response header and reuses it for subsequent
  calls. A stateless deployment simply omits the header and everything still
  works.
- `bridge_guide` is a static zero-network tool — it is listed even when the
  tower is degraded, which makes it the best liveness probe for the MCP layer
  specifically (vs `/health` for the HTTP layer).
- Per-IP rate limiting applies on `/mcp` (#695) — the suite issues at most a
  handful of requests per run and will not trip it under normal use.
- HTTP 4xx/5xx bodies are printed verbatim on failure; the tower's error
  semantics mirror the public Gateway contract (see
  [`docs/CONSUMERS.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/CONSUMERS.md)).
- For deeper, SDK-based flows (work orders, patches, live tool manifests) use
  the MCP connection itself — see [`AGENTS.md`](../../AGENTS.md) §2.1 and
  [`docs/AGENT_PORTAL_SPEC.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/AGENT_PORTAL_SPEC.md).

## Related

- [AGENTS.md](../../AGENTS.md) — submission pathways and agent loop
- [docs/AGENT_PORTAL_SPEC.md](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/AGENT_PORTAL_SPEC.md) — portal architecture
- [docs/ZERO_ADMIN_GUIDE.md](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/ZERO_ADMIN_GUIDE.md) — autonomous landing handbook
- [docs/FAQ.md](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/FAQ.md) — troubleshooting validation errors
