import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { isGlobalAdmin, verifyTenantAdminToken } from "../tenancy/tenant.registry.js";
import { registerRemoteServer, listRemoteServers } from "../registry/remote-mcp-servers.js";
import { callAggregatedTool, listAggregatedTools, refreshServer } from "../federation/aggregator.js";
import { getRemoteServer } from "../registry/remote-mcp-servers.js";

function scopeFor(tenantId?: string, adminToken?: string): { tenantId?: string; error?: string } {
  if (isGlobalAdmin()) return { tenantId: tenantId ?? "tenant_default" };
  if (tenantId && adminToken && verifyTenantAdminToken(tenantId, adminToken)) return { tenantId };
  return { error: "Tenant admin token required (pass tenantId + adminToken)." };
}

export async function registerFederationTools(server: McpServer): Promise<void> {
  server.tool("client.register_mcp_server", "Register a tenant-scoped remote MCP server for discovery and governed tool relay.", {
    name: z.string().min(2).max(128), protocol: z.enum(["stdio", "streamable-http", "sse"]), endpoint: z.string().url().optional(), command: z.string().min(1).optional(), args: z.array(z.string()).max(32).optional(), headers: z.record(z.string(), z.string()).optional(), tenantId: z.string().optional(), adminToken: z.string().optional(), scopes: z.array(z.string()).max(32).optional(), trustLevel: z.enum(["verified", "tenant", "untrusted"]).optional(),
  }, async (args) => {
    const scope = scopeFor(args.tenantId, args.adminToken);
    if (scope.error) return { isError: true, content: [{ type: "text", text: scope.error }] };
    try {
      const remote = registerRemoteServer({ name: args.name, protocol: args.protocol, endpoint: args.endpoint, command: args.command, args: args.args, headers: args.headers, tenantId: scope.tenantId!, scopes: args.scopes ?? [], trustLevel: args.trustLevel ?? "tenant" });
      return { content: [{ type: "text", text: JSON.stringify({ message: "Remote server registered and awaits discovery/approval.", server: remote }, null, 2) }] };
    } catch (error) { return { isError: true, content: [{ type: "text", text: `Registration failed: ${(error as Error).message}` }] }; }
  });

  server.tool("client.list_mcp_servers", "List registered remote MCP servers in the current tenant scope.", { tenantId: z.string().optional(), adminToken: z.string().optional() }, async (args) => {
    const scope = scopeFor(args.tenantId, args.adminToken);
    if (scope.error) return { isError: true, content: [{ type: "text", text: scope.error }] };
    return { content: [{ type: "text", text: JSON.stringify({ servers: listRemoteServers(scope.tenantId), tools: listAggregatedTools(scope.tenantId) }, null, 2) }] };
  });

  server.tool("client.discover_mcp_server", "Discover and cache the tools exposed by an approved remote MCP server.", { serverId: z.string(), tenantId: z.string().optional(), adminToken: z.string().optional() }, async (args) => {
    const scope = scopeFor(args.tenantId, args.adminToken);
    if (scope.error) return { isError: true, content: [{ type: "text", text: scope.error }] };
    const remote = getRemoteServer(args.serverId, scope.tenantId);
    if (!remote) return { isError: true, content: [{ type: "text", text: "Remote server not found." }] };
    try { return { content: [{ type: "text", text: JSON.stringify({ server: remote, tools: await refreshServer(remote) }, null, 2) }] }; }
    catch (error) { return { isError: true, content: [{ type: "text", text: `Discovery failed: ${(error as Error).message}` }] }; }
  });

  server.tool("remote.call", "Call a discovered remote MCP tool through the governed federation gateway.", { tool: z.string().min(3).describe("Qualified name: <serverId>.<toolName>"), arguments: z.record(z.string(), z.unknown()).default({}), tenantId: z.string().optional(), adminToken: z.string().optional() }, async (args) => {
    const scope = scopeFor(args.tenantId, args.adminToken);
    if (scope.error) return { isError: true, content: [{ type: "text", text: scope.error }] };
    try { const result = await callAggregatedTool(args.tool, args.arguments, scope.tenantId); return { content: [{ type: "text", text: JSON.stringify(result) }] }; }
    catch (error) { return { isError: true, content: [{ type: "text", text: `Remote call blocked: ${(error as Error).message}` }] }; }
  });
}
