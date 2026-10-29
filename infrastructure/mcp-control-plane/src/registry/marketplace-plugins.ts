import { registerRemoteServer, listRemoteServers, type RemoteMcpServer } from "./remote-mcp-servers.js";
import { mcpTrustLevelSchema, mcpProtocolSchema, type McpProtocol, type McpTrustLevel } from "./mcp.contracts.js";

/**
 * #1523 — Marketplace MVP: MCP plugin catalog + BYO connection ledger.
 *
 * Single control-plane source of truth for the Phase-1 plugin catalog. It
 * mirrors the `mcp_plugins` / `mcp_plugin_connections` Supabase schema
 * (core/database/migrations/20261030_mcp_plugins_registry.sql): same seed
 * rows, same unique(tenant, plugin) rule, same zero-plaintext-credential
 * invariant (vault REFERENCES only — the secret never crosses this plane).
 *
 * `connectPlugin` deliberately delegates to the SAME
 * `registerRemoteServer` registry that `client.register_mcp_server` uses,
 * so every marketplace connection lands on the existing governed path:
 * register (pending) -> `client.discover_mcp_server` (descriptor pins) ->
 * `remote.call` (fail-closed relay). No parallel trust surface is minted.
 */

export interface MarketplaceCredentialField {
  name: string;
  label: string;
  required: boolean;
  secret: boolean;
}

export interface MarketplacePlugin {
  pluginId: string;
  name: string;
  category: string;
  description: string;
  provider: string;
  /** Official hosted endpoint, or null for self-hosted BYO (user supplies). */
  endpointTemplate: string | null;
  protocol: McpProtocol;
  credentialFields: MarketplaceCredentialField[];
  trustLevel: McpTrustLevel;
  docsUrl: string | null;
}

export interface MarketplaceConnection {
  connectionId: string;
  pluginId: string;
  tenantId: string;
  remoteServerId: string;
  credentialVaultRef: string;
  endpointUsed: string;
  status: string;
  connectedAt: string;
}

const VAULT_REF_PATTERN = /^vault:[A-Za-z0-9._:-]+$/;

/** Secret-scan families (#539 ingress contract) — rejected before any state is touched. */
const PLAINTEXT_SECRET_PATTERNS: RegExp[] = [
  /^ghp_[A-Za-z0-9]/,
  /^ghs_[A-Za-z0-9]/,
  /^github_pat_[A-Za-z0-9]/,
  /^sk-[A-Za-z0-9]/,
  /^AKIA[0-9A-Z]/,
  /^xox[baprs]-/,
  /^AIza[0-9A-Za-z_-]/,
];

export function looksLikePlaintextSecret(value: string): boolean {
  return PLAINTEXT_SECRET_PATTERNS.some((re) => re.test(value));
}

function seed(
  pluginId: string,
  name: string,
  category: string,
  description: string,
  provider: string,
  endpointTemplate: string | null,
  credentialFields: MarketplaceCredentialField[],
  docsUrl: string | null,
): MarketplacePlugin {
  return {
    pluginId,
    name,
    category,
    description,
    provider,
    endpointTemplate,
    protocol: "streamable-http",
    credentialFields,
    trustLevel: "untrusted",
    docsUrl,
  };
}

const vaultField = (name: string, label: string): MarketplaceCredentialField => ({
  name,
  label,
  required: true,
  secret: true,
});

/** Phase-1 seed — must stay in sync with the 20261030 SQL migration. */
export const MARKETPLACE_PLUGINS: readonly MarketplacePlugin[] = Object.freeze([
  seed(
    "github",
    "GitHub",
    "devtools",
    "Official remote GitHub MCP server: repos, issues, pull requests and workflows under governed tool relay.",
    "github",
    "https://api.githubcopilot.com/mcp/",
    [vaultField("github-token", "GitHub personal access token (vault ref)")],
    "https://github.com/github/github-mcp-server",
  ),
  seed(
    "telegram",
    "Telegram",
    "messaging",
    "Bring your own Telegram bot gateway MCP server for message send/receive automation inside your tenant.",
    "telegram",
    null,
    [vaultField("bot-token", "Telegram bot token (vault ref)")],
    null,
  ),
  seed(
    "web-search",
    "Web Search",
    "research",
    "Bring your own web-search MCP server (SearXNG, Brave-compatible relays, or any compatible endpoint).",
    "web-search",
    null,
    [vaultField("search-api-key", "Search API key (vault ref)")],
    null,
  ),
  seed(
    "google-drive",
    "Google Drive",
    "productivity",
    "Bring your own Google Drive MCP server for file listing, reading and sharing workflows.",
    "google",
    null,
    [vaultField("drive-token", "Google OAuth token (vault ref)")],
    null,
  ),
  seed(
    "notion",
    "Notion",
    "productivity",
    "Official hosted Notion MCP server: pages, databases and comments under governed tool relay.",
    "notion",
    "https://mcp.notion.com/mcp",
    [vaultField("notion-token", "Notion integration token (vault ref)")],
    "https://developers.notion.com/docs/mcp",
  ),
]);

export function getMarketplacePlugin(pluginId: string): MarketplacePlugin | undefined {
  return MARKETPLACE_PLUGINS.find((p) => p.pluginId === pluginId);
}

const connections = new Map<string, MarketplaceConnection>();
let connectionSeq = 0;

export interface ConnectPluginInput {
  pluginId: string;
  tenantId: string;
  /** Vault REFERENCE (vault:<key>) — plaintext secrets are rejected. */
  credentialVaultRef: string;
  /** Required when the catalog plugin has no hosted endpoint template. */
  endpoint?: string;
}

export type ConnectPluginResult =
  | { ok: true; connection: MarketplaceConnection; remote: RemoteMcpServer; nextStep: string }
  | { ok: false; error: string };

export function connectPlugin(input: ConnectPluginInput): ConnectPluginResult {
  const plugin = getMarketplacePlugin(input.pluginId);
  if (!plugin) return { ok: false, error: `Unknown marketplace plugin: ${input.pluginId}` };

  for (const field of plugin.credentialFields) {
    if (field.required && !input.credentialVaultRef) {
      return { ok: false, error: `Missing credential field: ${field.name}` };
    }
  }
  // Plaintext check runs BEFORE the vault-ref shape check: a live-token-shaped
  // value deserves the specific "store it in a vault" message, not a generic
  // format error — and the two must never be reorderable into a leak path.
  if (looksLikePlaintextSecret(input.credentialVaultRef)) {
    return { ok: false, error: "credentialVaultRef looks like a live token value — store it in a vault and pass the reference instead." };
  }
  if (!VAULT_REF_PATTERN.test(input.credentialVaultRef)) {
    return {
      ok: false,
      error: "credentialVaultRef must be a vault reference (vault:<key>) — plaintext credentials are never accepted by the marketplace.",
    };
  }

  const endpoint = input.endpoint?.trim() || plugin.endpointTemplate || "";
  if (!endpoint) {
    return { ok: false, error: "This plugin is self-hosted: an endpoint is required (no hosted template exists)." };
  }
  try {
    new URL(endpoint);
  } catch {
    return { ok: false, error: `endpoint is not a valid URL: ${endpoint}` };
  }

  const duplicateKey = `${input.tenantId}::${input.pluginId}`;
  if (connections.has(duplicateKey)) {
    return { ok: false, error: `Plugin already connected in this tenant: ${input.pluginId} (unique per tenant/plugin).` };
  }

  mcpProtocolSchema.parse(plugin.protocol);
  mcpTrustLevelSchema.parse(plugin.trustLevel);

  // Same registry the existing client.register_mcp_server tool uses — the
  // marketplace adds a catalog layer, never a parallel trust surface.
  const remote = registerRemoteServer({
    name: `marketplace:${plugin.pluginId}`,
    protocol: plugin.protocol,
    endpoint,
    tenantId: input.tenantId,
    scopes: [],
    trustLevel: plugin.trustLevel,
  });

  connectionSeq += 1;
  const connection: MarketplaceConnection = {
    connectionId: `mpconn_${connectionSeq}_${remote.id.slice(-8)}`,
    pluginId: plugin.pluginId,
    tenantId: input.tenantId,
    remoteServerId: remote.id,
    credentialVaultRef: input.credentialVaultRef,
    endpointUsed: endpoint,
    status: remote.status,
    connectedAt: remote.createdAt,
  };
  connections.set(duplicateKey, connection);

  return {
    ok: true,
    connection,
    remote,
    nextStep: `Call client.discover_mcp_server with serverId=${remote.id} to pin tool descriptors; remote.call stays blocked until descriptors are approved.`,
  };
}

export function listMarketplaceConnections(tenantId: string): MarketplaceConnection[] {
  return [...connections.values()]
    .filter((c) => tenantId === "*" || c.tenantId === tenantId)
    .map((c) => ({ ...c }));
}

export function listTenantRemoteServersForMarketplace(tenantId: string): RemoteMcpServer[] {
  const ids = new Set(listMarketplaceConnections(tenantId).map((c) => c.remoteServerId));
  return listRemoteServers(tenantId).filter((s) => ids.has(s.id));
}

export function clearMarketplaceConnections(): void {
  connections.clear();
  connectionSeq = 0;
}
