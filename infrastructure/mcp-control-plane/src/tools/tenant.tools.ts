import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import {
  canManageTenants,
  createTenant,
  listTenants,
  updateTenant,
  suspendTenant,
  activateTenant,
  rotateTenantAdminToken,
} from "../tenancy/tenant.registry.js";

/**
 * Tenant Management Tools.
 *
 * Multi-tenant MCP Server: каждый admin/customer имеет собственный
 * изолированный MCP setup. Эти инструменты вызываются ТОЛЬКО
 * глобальным админом SupremeAI (MCP_ADMIN_KEY / admin role).
 */
export async function registerTenantTools(server: McpServer): Promise<void> {
  server.tool(
    "tenant.create",
    "Create a new isolated tenant (admin/customer). Each tenant gets its own admin token and can connect its own AI clients. Global-admin only.",
    {
      name: z.string().min(2).describe("Tenant name, e.g. 'Saiful's Startup'"),
      ownerEmail: z.string().email().describe("Owner email — unique per tenant"),
      type: z.enum(["admin", "customer"]).describe("'admin' for internal teams, 'customer' for external users"),
      plan: z.enum(["admin", "free", "pro", "enterprise"]).optional().describe("Billing plan (default: free)"),
      description: z.string().optional().describe("Optional tenant description"),
      maxClients: z.number().int().min(1).max(1000).optional().describe("Client limit override"),
      maxToolsPerMinute: z.number().int().min(1).max(10000).optional().describe("Rate limit override"),
    },
    async (args) => {
      try {
        const result = createTenant({
          name: args.name,
          ownerEmail: args.ownerEmail,
          type: args.type,
          plan: args.plan,
          description: args.description,
          limits: {
            ...(args.maxClients ? { maxClients: args.maxClients } : {}),
            ...(args.maxToolsPerMinute ? { maxToolsPerMinute: args.maxToolsPerMinute } : {}),
          },
        });
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              message: "Tenant created successfully",
              tenant: result.tenant,
              adminToken: result.adminToken,
              note: "Share the adminToken securely with the tenant owner ONCE. It is NOT stored in plaintext.",
            }, null, 2),
          }],
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "tenant.list",
    "List all tenants (admin & customer) with their status, plan, and limits. Global-admin only.",
    {},
    async () => {
      try {
        // #698: tenant.list was the only tenant tool without the admin gate.
        if (!canManageTenants()) {
          return { isError: true, content: [{ type: "text", text: "Forbidden: only the global SupremeAI admin can list tenants" }] };
        }
        const tenants = listTenants();
        return { content: [{ type: "text", text: JSON.stringify({ count: tenants.length, tenants }, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "tenant.update",
    "Update a tenant's name, description, plan, status, limits, or settings. Global-admin only.",
    {
      tenantId: z.string().describe("Tenant ID"),
      name: z.string().optional().describe("New name"),
      description: z.string().optional().describe("New description"),
      status: z.enum(["active", "suspended"]).optional().describe("New status"),
      plan: z.enum(["admin", "free", "pro", "enterprise"]).optional().describe("New plan"),
      maxClients: z.number().int().min(1).optional().describe("Client limit override"),
      maxToolsPerMinute: z.number().int().min(1).optional().describe("Rate limit override"),
    },
    async (args) => {
      try {
        const tenant = updateTenant(args.tenantId, {
          name: args.name,
          description: args.description,
          status: args.status,
          plan: args.plan,
          limits: {
            ...(args.maxClients ? { maxClients: args.maxClients } : {}),
            ...(args.maxToolsPerMinute ? { maxToolsPerMinute: args.maxToolsPerMinute } : {}),
          },
        });
        return { content: [{ type: "text", text: JSON.stringify(tenant, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "tenant.suspend",
    "Suspend a tenant — all its AI clients immediately lose access. Global-admin only.",
    { tenantId: z.string().describe("Tenant ID to suspend") },
    async ({ tenantId }) => {
      try {
        const tenant = suspendTenant(tenantId);
        if (!tenant) return { isError: true, content: [{ type: "text", text: `Tenant not found: ${tenantId}` }] };
        return { content: [{ type: "text", text: JSON.stringify({ message: "Tenant suspended", tenant }, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "tenant.activate",
    "Re-activate a suspended tenant. Global-admin only.",
    { tenantId: z.string().describe("Tenant ID to activate") },
    async ({ tenantId }) => {
      try {
        const tenant = activateTenant(tenantId);
        if (!tenant) return { isError: true, content: [{ type: "text", text: `Tenant not found: ${tenantId}` }] };
        return { content: [{ type: "text", text: JSON.stringify({ message: "Tenant activated", tenant }, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "tenant.rotate_admin_token",
    "Rotate a tenant's admin token (old token stops working immediately). Global-admin only.",
    { tenantId: z.string().describe("Tenant ID") },
    async ({ tenantId }) => {
      try {
        const result = rotateTenantAdminToken(tenantId);
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              message: "Tenant admin token rotated",
              tenant: result.tenant,
              newAdminToken: result.adminToken,
              note: "Share the new token securely; the old token is now invalid.",
            }, null, 2),
          }],
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );
}