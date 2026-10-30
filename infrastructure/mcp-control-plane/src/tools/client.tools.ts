import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import {
  approveClient,
  changeClientProfile,
  changeClientProvider,
  changeClientRole,
  defaultClientScopes,
  listClients,
  registerClient,
  revokeClient,
  rotateClient,
  deleteClient,
} from "../policy/client-registry.js";
import { isGlobalAdmin, verifyTenantAdminToken } from "../tenancy/tenant.registry.js";
import { env } from "../lib/env.js";
import {
  connectPlugin,
  getMarketplacePlugin,
  listMarketplaceConnections,
  listMarketplacePlugins,
  marketplaceLicenseGate,
  registerMarketplacePlugin,
  listTenantRemoteServersForMarketplace,
} from "../registry/marketplace-plugins.js";

/**
 * Client Management Tools — "Bring Your Own AI".
 *
 * Позволяют admin/customer подключать ЛЮБОЙ AI-клиент
 * (Claude Desktop, Cursor, Gemini, VS Code, custom MCP client) к СВОЕМУ
 * изолированному tenant и менять роль клиента на лету.
 *
 * Auth model:
 *  - global admin (MCP_ADMIN_KEY) → может всё для всех tenants;
 *  - tenant admin (tenant admin token + tenantId) → управляет ТОЛЬКО своим tenant;
 *  - обычный клиент → не может управлять чужими клиентами.
 */

function authTenantAdmin(tenantId?: string, adminToken?: string): boolean {
  return Boolean(tenantId && adminToken && verifyTenantAdminToken(tenantId, adminToken));
}

/** Admin-scope resolution shared with slot.tools.ts (#48). */
export function requireScope(args: { tenantId?: string; adminToken?: string }): { scope: string | undefined; error?: string } {
  if (isGlobalAdmin()) return { scope: "*" };
  if (authTenantAdmin(args.tenantId, args.adminToken)) {
    return { scope: args.tenantId! };
  }
  return {
    scope: undefined,
    error: "Tenant admin token required (pass tenantId + adminToken). Global admin requires only the bearer token.",
  };
}

export async function registerClientTools(server: McpServer): Promise<void> {
  server.tool(
    "client.register",
    "Register a NEW AI client (Claude, Cursor, Gemini, ChatGPT, VS Code, custom) into your tenant. Returns a one-time token + connection config. The client starts in 'pending' status until a tenant admin approves it.",
    {
      clientId: z.string().min(2).max(64).regex(/^[a-zA-Z0-9_-]+$/, "clientId must be alphanumeric, dashes, or underscores").optional().describe("Custom client ID, e.g. 'ide_cline'"),
      name: z.string().min(2).describe("Client name, e.g. 'My Claude Desktop'"),
      provider: z.string().optional().describe("AI provider: claude, cursor, gemini, chatgpt, vscode, custom, generic"),
      protocol: z.enum(["streamable-http", "sse", "stdio", "custom"]).optional().describe("Connection protocol"),
      role: z.enum(["viewer", "agent", "admin"]).optional().describe("Initial role (default: viewer)"),
      toolProfile: z.enum(["chatgpt", "readonly"]).optional().describe("Tool Exposure Policy: curated discovery surface ('chatgpt' read-mostly curated, 'readonly' strict no-write). Omit for the full RBAC surface."),
      expiresInDays: z.number().int().min(1).max(365).optional().describe("Token expiry in days"),
      tenantId: z.string().optional().describe("Your tenant ID (required when using tenant admin token)"),
      adminToken: z.string().optional().describe("Your tenant admin token (required for non-global-admin callers)"),
    },
    { readOnlyHint: false },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      const tenantId = scope === "*" ? (args.tenantId ?? "tenant_default") : scope;
      try {
        const expiresAt = args.expiresInDays
          ? new Date(Date.now() + args.expiresInDays * 86_400_000).toISOString()
          : undefined;
        const result = registerClient(
          args.name,
          args.role ?? "viewer",
          defaultClientScopes(args.role ?? "viewer"),
          expiresAt,
          args.provider ?? "generic",
          args.protocol ?? "streamable-http",
          tenantId,
          args.clientId,
          args.toolProfile
        );
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              message: "Client registered. Awaiting approval by the tenant admin.",
              client: result.client,
              token: result.token,
              tenantId,
              connection: {
                type: args.protocol ?? "streamable-http",
                endpoint: `${env.render.controlTower.url}/mcp`,
                configExample: args.protocol === "stdio"
                  ? { command: "npx", args: ["tsx", "infrastructure/mcp-control-plane/src/index.ts"], transport: "stdio" }
                  : { url: `${env.render.controlTower.url}/mcp`, headers: { Authorization: `Bearer ${result.token}` } },
              },
              note: "Store the token securely. It is shown only once.",
            }, null, 2),
          }],
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "client.list",
    "List AI clients registered in your tenant (or all tenants for global admin).",
    {
      tenantId: z.string().optional().describe("Tenant ID (tenant admin) — global admin may omit to see all"),
      adminToken: z.string().optional().describe("Tenant admin token"),
    },
    { readOnlyHint: true, idempotentHint: true },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      const clients = listClients(scope);
      return { content: [{ type: "text", text: JSON.stringify({ scope, count: clients.length, clients }, null, 2) }] };
    }
  );

  server.tool(
    "client.approve",
    "Approve a pending client so it can connect and use tools. Tenant admin scope enforced.",
    {
      clientId: z.string().describe("Client ID to approve"),
      tenantId: z.string().optional().describe("Your tenant ID"),
      adminToken: z.string().optional().describe("Your tenant admin token"),
    },
    { readOnlyHint: false },
    async ({ clientId, tenantId, adminToken }) => {
      const { scope, error } = requireScope({ tenantId, adminToken });
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      try {
        const client = approveClient(clientId, scope);
        if (!client) return { isError: true, content: [{ type: "text", text: `Client not found or not pending: ${clientId}` }] };
        return { content: [{ type: "text", text: JSON.stringify({ message: "Client approved and activated", client }, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "client.set_role",
    "Change a client's ROLE (viewer / agent / admin). Roles adjust scopes instantly.",
    {
      clientId: z.string().describe("Client ID"),
      role: z.enum(["viewer", "agent", "admin"]).describe("New role"),
      tenantId: z.string().optional().describe("Your tenant ID"),
      adminToken: z.string().optional().describe("Your tenant admin token"),
    },
    { readOnlyHint: false },
    async ({ clientId, role, tenantId, adminToken }) => {
      const { scope, error } = requireScope({ tenantId, adminToken });
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      try {
        const client = changeClientRole(clientId, role, scope);
        if (!client) return { isError: true, content: [{ type: "text", text: `Client not found or inactive: ${clientId}` }] };
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              message: `Role changed to ${role}`,
              client,
              newScopes: defaultClientScopes(role),
            }, null, 2),
          }],
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "client.set_profile",
    "Set a client's TOOL-SURFACE profile (Tool Exposure Policy). 'chatgpt' = curated read-mostly surface, 'readonly' = strict no-write subset. Profiles curate what the client SEES in tools/list; the RBAC call gate remains the security boundary. Pass 'clear' to restore the full surface.",
    {
      clientId: z.string().describe("Client ID"),
      toolProfile: z.enum(["chatgpt", "readonly", "clear"]).describe("Profile to apply ('clear' removes the profile and restores the full RBAC surface)"),
      tenantId: z.string().optional().describe("Your tenant ID"),
      adminToken: z.string().optional().describe("Your tenant admin token"),
    },
    { readOnlyHint: false },
    async ({ clientId, toolProfile, tenantId, adminToken }) => {
      const { scope, error } = requireScope({ tenantId, adminToken });
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      try {
        const client = changeClientProfile(clientId, toolProfile === "clear" ? null : toolProfile, scope);
        if (!client) return { isError: true, content: [{ type: "text", text: `Client not found or inactive: ${clientId}` }] };
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              message: toolProfile === "clear"
                ? "Tool profile cleared — client sees the full RBAC surface again."
                : `Tool profile set to '${toolProfile}' — the client's tools/list is now filtered to the '${toolProfile}' surface (RBAC still enforces every call).`,
              client,
            }, null, 2),
          }],
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "client.set_provider",
    "Update which AI provider a client is connected through (claude, cursor, gemini, chatgpt, vscode, custom).",
    {
      clientId: z.string().describe("Client ID"),
      provider: z.string().describe("New provider label"),
      tenantId: z.string().optional(),
      adminToken: z.string().optional(),
    },
    { readOnlyHint: false },
    async ({ clientId, provider, tenantId, adminToken }) => {
      const { scope, error } = requireScope({ tenantId, adminToken });
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      try {
        const client = changeClientProvider(clientId, provider, scope);
        if (!client) return { isError: true, content: [{ type: "text", text: `Client not found: ${clientId}` }] };
        return { content: [{ type: "text", text: JSON.stringify({ message: "Provider updated", client }, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "client.revoke",
    "Revoke (delete) a client's access immediately. Its token stops working.",
    {
      clientId: z.string().describe("Client ID to revoke"),
      tenantId: z.string().optional(),
      adminToken: z.string().optional(),
    },
    { readOnlyHint: false, destructiveHint: true },
    async ({ clientId, tenantId, adminToken }) => {
      const { scope, error } = requireScope({ tenantId, adminToken });
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      try {
        const ok = revokeClient(clientId, scope);
        return { content: [{ type: "text", text: ok ? `Client ${clientId} revoked.` : `Client not found: ${clientId}` }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "client.rotate_token",
    "Rotate a client's token (old token becomes invalid, new one issued once).",
    {
      clientId: z.string().describe("Client ID"),
      tenantId: z.string().optional(),
      adminToken: z.string().optional(),
    },
    { readOnlyHint: false, destructiveHint: true },
    async ({ clientId, tenantId, adminToken }) => {
      const { scope, error } = requireScope({ tenantId, adminToken });
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      try {
        const result = rotateClient(clientId, scope);
        if (!result) return { isError: true, content: [{ type: "text", text: `Client not found or not active: ${clientId}` }] };
        return { content: [{ type: "text", text: JSON.stringify({ message: "Token rotated", client: result.client, newToken: result.token }, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  // ── #1523 Marketplace MVP: plugin catalog + one-click BYO connect ────────
  // Zero-risk by construction: credentials are vault REFERENCES only (the
  // connect guard rejects plaintext), and every connection lands on the SAME
  // governed federation path as client.register_mcp_server — pending status,
  // descriptor pinning via client.discover_mcp_server, fail-closed remote.call.
  server.tool(
    "marketplace.list_plugins",
    "List the Marketplace MVP plugin catalog (Phase 1: GitHub, Telegram, Web-Search, Drive, Notion). Templates only — credential fields are SPECS (names/labels), never values.",
    {},
    { readOnlyHint: true, idempotentHint: true },
    async () => {
      // #1668: the catalog view carries each row's mechanical license +
      // provenance verdict so the trust boundary is machine-checkable, not
      // editorial. Seeds without pinned upstreams honestly show REJECT codes.
      const plugins = listMarketplacePlugins().map((p) => ({
        ...p,
        licenseGate: marketplaceLicenseGate(p),
      }));
      return {
        content: [{
          type: "text",
          text: JSON.stringify({ count: plugins.length, plugins }, null, 2),
        }],
      };
    }
  );

  server.tool(
    "marketplace.connect_plugin",
    "One-click BYO connect: register a marketplace plugin for your tenant through the SAME governed registry as client.register_mcp_server. Pass credentialVaultRef = 'vault:<key>' — NEVER a plaintext token. Follow up with client.discover_mcp_server to pin tool descriptors before any remote.call.",
    {
      pluginId: z.string().describe("Marketplace plugin ID (see marketplace.list_plugins)"),
      credentialVaultRef: z.string().describe("Vault REFERENCE for the plugin credential, e.g. 'vault:github-token'. Plaintext secrets are rejected."),
      endpoint: z.string().url().optional().describe("Override endpoint (required for self-hosted plugins without a hosted template)"),
      tenantId: z.string().optional().describe("Your tenant ID (required when using tenant admin token)"),
      adminToken: z.string().optional().describe("Your tenant admin token (required for non-global-admin callers)"),
    },
    { readOnlyHint: false },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      const tenantId = scope === "*" ? (args.tenantId ?? "tenant_default") : (scope ?? "tenant_default");
      const result = connectPlugin({
        pluginId: args.pluginId,
        tenantId,
        credentialVaultRef: (args.credentialVaultRef ?? "").trim(),
        endpoint: args.endpoint,
      });
      if (!result.ok) return { isError: true, content: [{ type: "text", text: `Connect failed: ${result.error}` }] };
      const plugin = getMarketplacePlugin(args.pluginId);
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            message: `Plugin '${plugin?.name ?? args.pluginId}' connected for tenant ${tenantId}. Status: ${result.connection.status} (pending discovery + descriptor approval).`,
            connection: result.connection,
            remoteServer: result.remote,
            nextStep: result.nextStep,
            security: "Credential stored as a vault reference only; tool relay stays fail-closed until descriptors are approved.",
          }, null, 2),
        }],
      };
    }
  );

  server.tool(
    "marketplace.list_connections",
    "List marketplace plugin connections in your tenant scope, with the live federation status of each backing remote server.",
    {
      tenantId: z.string().optional().describe("Tenant ID (tenant admin) — global admin may omit to see all"),
      adminToken: z.string().optional().describe("Tenant admin token"),
    },
    { readOnlyHint: true, idempotentHint: true },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      const tenantScope = scope ?? "tenant_default";
      const conns = listMarketplaceConnections(tenantScope);
      const remotes = listTenantRemoteServersForMarketplace(tenantScope);
      const remoteById = new Map(remotes.map((r) => [r.id, r]));
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            count: conns.length,
            connections: conns.map((c) => ({
              ...c,
              remote: remoteById.get(c.remoteServerId) ?? null,
            })),
          }, null, 2),
        }],
      };
    }
  );

  // ── #1668 License + provenance gate: catalog INGRESS (global admin) ─────
  // Third-party plugins enter the mcp_plugins registry ONLY through this
  // tool. The gate is mechanical and fail-closed: GPL-family licenses are
  // rejected (repo verdict rule), unknown/unverifiable licenses are rejected
  // (S10 doctrine), and the upstream must be a code-hosting repository URL
  // (vendor-marketing/distribution pages are the open-washing marker and
  // are rejected). Admissions land 'untrusted' — the governed connect path
  // (pending -> descriptor pinning -> fail-closed relay) is unchanged.
  server.tool(
    "marketplace.register_plugin",
    "Register a NEW third-party plugin into the mcp_plugins catalog (GLOBAL admin only). Runs the #1668 license + provenance gate first: GPL-family licenses, unknown licenses, and non-repository upstreams are rejected fail-closed. Pass the upstream's SPDX license expression and its code-hosting repository URL.",
    {
      pluginId: z.string().regex(/^[a-z0-9-]{2,64}$/, "pluginId must match ^[a-z0-9-]{2,64}$"),
      name: z.string().min(2).describe("Plugin display name"),
      description: z.string().min(20).describe("What the plugin does (templates-only catalog, never tenant data)"),
      category: z.string().optional().describe("Catalog category (default: productivity)"),
      provider: z.string().optional().describe("Provider/vendor identifier (default: pluginId)"),
      endpointTemplate: z.string().url().nullable().optional().describe("Official hosted endpoint, or null for self-hosted BYO"),
      protocol: z.enum(["streamable-http", "sse", "stdio"]).optional().describe("MCP transport protocol (default: streamable-http)"),
      credentialFields: z.array(z.object({
        name: z.string().min(1),
        label: z.string().min(1),
        required: z.boolean().optional(),
        secret: z.boolean().optional(),
      })).optional().describe("Credential FIELD SPECS only ({name,label,required,secret}) — never values"),
      docsUrl: z.string().url().nullable().optional().describe("Documentation URL"),
      license: z.string().nullable().describe("SPDX license expression of the upstream project (e.g. 'MIT', 'Apache-2.0') — null is rejected"),
      upstreamUrl: z.string().nullable().describe("Upstream repository URL (https, github/gitlab/bitbucket, owner/repo) — null is rejected"),
      tenantId: z.string().optional().describe("Ignored for catalog registration (global-admin plane)"),
      adminToken: z.string().optional().describe("Tenant admin token (not sufficient — catalog registration is global-admin only)"),
    },
    { readOnlyHint: false },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      if (scope !== "*") {
        return { isError: true, content: [{ type: "text", text: "marketplace.register_plugin is a global-admin plane: the mcp_plugins catalog is registry-wide (public catalog table), not tenant-scoped." }] };
      }
      const result = registerMarketplacePlugin({
        pluginId: args.pluginId,
        name: args.name,
        description: args.description,
        category: args.category ?? "productivity",
        provider: args.provider ?? args.pluginId,
        endpointTemplate: args.endpointTemplate ?? null,
        protocol: args.protocol ?? "streamable-http",
        credentialFields: (args.credentialFields ?? []).map((f) => ({
          name: f.name,
          label: f.label,
          required: f.required ?? true,
          secret: f.secret ?? true,
        })),
        docsUrl: args.docsUrl ?? null,
        license: args.license,
        upstreamUrl: args.upstreamUrl,
      });
      if (!result.ok) return { isError: true, content: [{ type: "text", text: `Registration failed: ${result.error}` }] };
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            message: `Plugin '${result.plugin.pluginId}' registered into the catalog (trust_level: untrusted).`,
            gate: result.gate,
            plugin: result.plugin,
          }, null, 2),
        }],
      };
    }
  );
}