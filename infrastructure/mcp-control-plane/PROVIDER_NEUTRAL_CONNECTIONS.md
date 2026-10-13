# Provider-neutral MCP connections

SupremeAI exposes one provider-neutral MCP endpoint. Customers may connect any MCP-compatible AI client; the server does not assume Claude, Cursor, or a specific vendor.

## Admin flow

1. Create a client in the admin dashboard or `POST /clients`.
2. Set a descriptive `provider` value such as `generic`, `claude`, `cursor`, `openai`, `gemini`, or an internal client name.
3. Choose a protocol supported by the client: `streamable-http`, `sse`, `stdio`, or `custom`.
4. Start with `viewer` and read-only scopes.
5. Share the one-time bearer token through a secure channel.
6. Promote to `agent` or `admin` only when the customer explicitly needs those capabilities.
7. Revoke, rotate, expire, and audit every client from the admin control plane.

Provider labels are metadata only. Authorization is determined by the issued token, role, scopes, tenant policy, approval policy, and service health—not by the provider name supplied by a client.

## Client contract

Any MCP-compatible client should connect to the same endpoint with:

```text
Authorization: Bearer <admin-issued-token>
```

The default role is viewer. Write, destructive, and administrative operations require explicit role and scope grants plus the normal approval policy.

## Remote Streamable HTTP setup

Use the deployed MCP endpoint, not the health endpoint:

```text
https://<MCP_HOST>/mcp
```

Create a client token as an administrator:

```bash
curl -X POST "https://<MCP_HOST>/clients" \
  -H "Authorization: Bearer $MCP_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "External AI Assistant",
    "provider": "generic",
    "protocol": "streamable-http",
    "role": "viewer"
  }'
```

The response contains a one-time `token`. Store it in the AI client's secret configuration; do not commit it to Git, expose it in a URL, or paste it into prompts.

Generic client configuration:

```json
{
  "mcpServers": {
    "supremeai-control-tower": {
      "url": "https://<MCP_HOST>/mcp",
      "headers": {
        "Authorization": "Bearer mcp_<CLIENT_TOKEN>"
      }
    }
  }
}
```

## Local stdio setup

For clients running on the same machine as this repository:

```json
{
  "mcpServers": {
    "supremeai-control-tower": {
      "command": "node",
      "args": ["/absolute/path/to/infrastructure/mcp-control-plane/dist/index.js"],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "MCP_VIEWER_KEY": "<LOCAL_VIEWER_KEY>"
      }
    }
  }
}
```

Build the server before using the stdio configuration:

```bash
cd infrastructure/mcp-control-plane
npm install
npm run build
```

## Lifecycle operations

List clients without exposing token material:

```bash
curl -H "Authorization: Bearer $MCP_ADMIN_KEY" \
  "https://<MCP_HOST>/clients"
```

Rotate a token after suspected exposure:

```bash
curl -X POST \
  -H "Authorization: Bearer $MCP_ADMIN_KEY" \
  "https://<MCP_HOST>/clients/<CLIENT_ID>/rotate"
```

Revoke a client immediately:

```bash
curl -X DELETE \
  -H "Authorization: Bearer $MCP_ADMIN_KEY" \
  "https://<MCP_HOST>/clients/<CLIENT_ID>"
```

Verify the server before connecting an AI client:

```bash
curl "https://<MCP_HOST>/health"
curl -H "Authorization: Bearer $CLIENT_TOKEN" \
  "https://<MCP_HOST>/mcp"
```

A production deployment must define `MCP_ADMIN_KEY` or `MCP_API_KEY`. For safer separation of duties, define dedicated `MCP_VIEWER_KEY` and `MCP_AGENT_KEY`, and issue external clients through the admin-protected `/clients` endpoint.

## Role guidance

- `viewer`: health, system, and audit read access.
- `agent`: viewer access plus approved tool execution and approval requests.
- `admin`: client lifecycle, approvals, and emergency controls.

Provider names such as `claude`, `cursor`, `openai`, and `gemini` are labels only. Never use the provider field as an authorization mechanism.
