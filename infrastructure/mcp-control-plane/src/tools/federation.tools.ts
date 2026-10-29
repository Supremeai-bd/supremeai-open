import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { isGlobalAdmin, verifyTenantAdminToken } from "../tenancy/tenant.registry.js";
import { registerRemoteServer, listRemoteServers } from "../registry/remote-mcp-servers.js";
import { callAggregatedTool, listAggregatedTools, refreshServer } from "../federation/aggregator.js";
import { getRemoteServer } from "../registry/remote-mcp-servers.js";
import { getDescriptorStatus, reapproveDescriptors } from "../federation/descriptor-pinning.js";
import { recordSlotAudit } from "../policy/slot-audit.js";

function scopeFor(tenantId?: string, adminToken?: string): { tenantId?: string; error?: string } {
  if (isGlobalAdmin()) return { tenantId: tenantId ?? "tenant_default" };
  if (tenantId && adminToken && verifyTenantAdminToken(tenantId, adminToken)) return { tenantId };
  return { error: "Tenant admin token required (pass tenantId + adminToken)." };
}

export async function registerFederationTools(server: McpServer): Promise<void> {
  server.tool("client.register_mcp_server", "Register a tenant-scoped remote MCP server for discovery and governed tool relay.", {
    name: z.string().min(2).max(128), protocol: z.enum(["stdio", "streamable-http", "sse"]), endpoint: z.string().url().optional(), command: z.string().min(1).optional(), args: z.array(z.string()).max(32).optional(), headers: z.record(z.string(), z.string()).optional(), tenantId: z.string().optional(), adminToken: z.string().optional(), scopes: z.array(z.string()).max(32).optional(), trustLevel: z.enum(["verified", "tenant", "untrusted"]).optional(),
  }, { readOnlyHint: false, destructiveHint: false },
    async (args) => {
    const scope = scopeFor(args.tenantId, args.adminToken);
    if (scope.error) return { isError: true, content: [{ type: "text", text: scope.error }] };
    try {
      const remote = registerRemoteServer({ name: args.name, protocol: args.protocol, endpoint: args.endpoint, command: args.command, args: args.args, headers: args.headers, tenantId: scope.tenantId!, scopes: args.scopes ?? [], trustLevel: args.trustLevel ?? "tenant" });
      return { content: [{ type: "text", text: JSON.stringify({ message: "Remote server registered and awaits discovery/approval.", server: remote }, null, 2) }] };
    } catch (error) { return { isError: true, content: [{ type: "text", text: `Registration failed: ${(error as Error).message}` }] }; }
  });

  server.tool("client.list_mcp_servers", "List registered remote MCP servers in the current tenant scope, including pinned tool-descriptor drift (#1712).", { tenantId: z.string().optional(), adminToken: z.string().optional() }, { readOnlyHint: true, idempotentHint: true },
    async (args) => {
    const scope = scopeFor(args.tenantId, args.adminToken);
    if (scope.error) return { isError: true, content: [{ type: "text", text: scope.error }] };
    const servers = listRemoteServers(scope.tenantId);
    const descriptorPins = servers.map((remote) => getDescriptorStatus(remote.id));
    return { content: [{ type: "text", text: JSON.stringify({ servers, tools: listAggregatedTools(scope.tenantId), descriptorPins }, null, 2) }] };
  });

  server.tool("client.discover_mcp_server", "Discover and cache the tools exposed by an approved remote MCP server. Pins SHA-256 tool-descriptor hashes; changed/added/removed descriptors become pending and block remote.call until reapprove:true (audited).", { serverId: z.string(), reapprove: z.boolean().optional().describe("Explicitly adopt pending descriptor changes as the new approved baseline (admin action, audit-logged)"), tenantId: z.string().optional(), adminToken: z.string().optional() }, { readOnlyHint: false, destructiveHint: false },
    async (args) => {
    const scope = scopeFor(args.tenantId, args.adminToken);
    if (scope.error) return { isError: true, content: [{ type: "text", text: scope.error }] };
    const remote = getRemoteServer(args.serverId, scope.tenantId);
    if (!remote) return { isError: true, content: [{ type: "text", text: "Remote server not found." }] };
    try {
      const tools = await refreshServer(remote);
      const descriptorStatus = getDescriptorStatus(remote.id);
      let reapproval: { approved: number } | undefined;
      if (args.reapprove) {
        reapproval = reapproveDescriptors(remote.id);
        recordSlotAudit({ operation: "admin", tool: "client.discover_mcp_server", outcome: "allowed", reason: `descriptor-reapprove: ${reapproval.approved} tool(s) adopted`, tenantId: scope.tenantId });
      }
      return { content: [{ type: "text", text: JSON.stringify({ server: remote, tools, descriptorStatus, ...(reapproval ? { reapproval } : {}) }, null, 2) }] };
    }
    catch (error) { return { isError: true, content: [{ type: "text", text: `Discovery failed: ${(error as Error).message}` }] }; }
  });

  server.tool("remote.call", "Call a discovered remote MCP tool through the governed federation gateway. Fail-closed: the live tool surface is re-verified against approved SHA-256 descriptor pins (default TTL 5 min); any mutation blocks execution with tool_descriptor_mutated until explicit re-approval.", { tool: z.string().min(3).describe("Qualified name: <serverId>.<toolName>"), arguments: z.record(z.string(), z.unknown()).default({}), tenantId: z.string().optional(), adminToken: z.string().optional() }, { readOnlyHint: false, destructiveHint: true, openWorldHint: true },
    async (args) => {
    const scope = scopeFor(args.tenantId, args.adminToken);
    if (scope.error) return { isError: true, content: [{ type: "text", text: scope.error }] };
    try { const result = await callAggregatedTool(args.tool, args.arguments, scope.tenantId); return { content: [{ type: "text", text: JSON.stringify(result) }] }; }
    catch (error) { return { isError: true, content: [{ type: "text", text: `Remote call blocked: ${(error as Error).message}` }] }; }
  });
}
