# MCP Federation Contract

The control tower federates tenant-approved MCP servers without exposing their credentials to callers.

## Lifecycle

1. A global or tenant administrator calls `client.register_mcp_server`.
2. The server is stored as `pending`; registration never grants execution access.
3. `client.discover_mcp_server` connects and caches the remote tool schema.
4. A successful discovery marks the server `active`; connection failures quarantine it.
5. Callers invoke a cached tool through `remote.call` using `<serverId>.<toolName>`.

## Trust model

- Remote servers are tenant-scoped and never visible across tenants.
- Only administrators can register, discover, list, or relay remote servers.
- Tool calls are allowlisted by the latest discovery snapshot.
- Pending, quarantined, and revoked servers cannot execute tools.
- Headers are supplied only to the outbound connector and are not returned by aggregated tool listings.
- Production onboarding must use secret storage and a reviewed egress policy; this implementation does not persist remote registrations across process restarts.

## Manual production tasks

- Run live fixtures for HTTP/SSE and stdio servers.
- Replace the in-memory catalog with an encrypted, tenant-scoped durable store.
- Configure retry, timeout, circuit-breaker, and outbound network policies.
- Add OAuth token brokering and rotation before connecting credentialed providers.
- Complete security review for SSRF, command execution, header redaction, and denial-of-service controls.
