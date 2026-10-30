import { registerRemoteServer, listRemoteServers, type RemoteMcpServer } from "./remote-mcp-servers.js";
import { mcpTrustLevelSchema, mcpProtocolSchema, type McpProtocol, type McpTrustLevel } from "./mcp.contracts.js";
import { evaluateLicenseProvenance, type LicenseGateVerdict } from "./license-gate.js";

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
  /** SPDX expression of the upstream project, or null when not pinned. */
  license: string | null;
  /** Upstream repository URL, or null when not pinned (#1668 provenance). */
  upstreamUrl: string | null;
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
  license: string | null,
  upstreamUrl: string | null,
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
    license,
    upstreamUrl,
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
    "MIT",
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
    null,
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
    null,
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
    null,
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
    null,
    null,
  ),
]);

export function getMarketplacePlugin(pluginId: string): MarketplacePlugin | undefined {
  return (
    MARKETPLACE_PLUGINS.find((p) => p.pluginId === pluginId) ??
    marketplaceRegistryExtras.find((p) => p.pluginId === pluginId)
  );
}

/** Runtime additions from #1668 catalog ingress (seeds stay frozen/SQL-synced). */
const marketplaceRegistryExtras: MarketplacePlugin[] = [];

/** Combined catalog view: frozen Phase-1 seeds + gate-admitted registrations. */
export function listMarketplacePlugins(): MarketplacePlugin[] {
  return [...MARKETPLACE_PLUGINS, ...marketplaceRegistryExtras];
}

/** #1668 — mechanical license + provenance verdict for any catalog row. */
export function marketplaceLicenseGate(plugin: MarketplacePlugin): LicenseGateVerdict {
  return evaluateLicenseProvenance({ license: plugin.license, upstreamUrl: plugin.upstreamUrl });
}

export interface RegisterMarketplacePluginInput {
  pluginId: string;
  name: string;
  category: string;
  description: string;
  provider: string;
  endpointTemplate: string | null;
  protocol: McpProtocol;
  credentialFields: MarketplaceCredentialField[];
  docsUrl: string | null;
  license: string | null;
  upstreamUrl: string | null;
}

export type RegisterMarketplacePluginResult =
  | { ok: true; plugin: MarketplacePlugin; gate: LicenseGateVerdict }
  | { ok: false; error: string; gate: LicenseGateVerdict | null };

/**
 * #1668 — Catalog ingress. Third-party plugins enter the registry ONLY
 * through this gate: GPL-family licenses, unknown/unverifiable licenses,
 * and non-repository upstreams are rejected fail-closed (S10 doctrine);
 * every admission lands 'untrusted' and is never merged into the frozen
 * seed list (which must stay in sync with the SQL migration).
 */
export function registerMarketplacePlugin(input: RegisterMarketplacePluginInput): RegisterMarketplacePluginResult {
  const pluginId = (input.pluginId ?? "").trim();
  if (!/^[a-z0-9-]{2,64}$/.test(pluginId)) {
    return { ok: false, error: `pluginId must match ^[a-z0-9-]{2,64}$ (got '${pluginId}').`, gate: null };
  }
  if (getMarketplacePlugin(pluginId)) {
    return { ok: false, error: `Plugin already registered in the catalog: ${pluginId}.`, gate: null };
  }
  // Gate FIRST — a rejected plugin never reaches catalog state.
  const gate = evaluateLicenseProvenance({ license: input.license, upstreamUrl: input.upstreamUrl });
  if (gate.verdict === "REJECT") {
    return { ok: false, error: `License/provenance gate rejected plugin '${pluginId}': ${gate.reason}`, gate };
  }
  if (!input.name || input.name.trim().length < 2) {
    return { ok: false, error: "name must be a real plugin name (>=2 chars).", gate };
  }
  if (!input.description || input.description.trim().length < 20) {
    return { ok: false, error: "description must be substantive (>=20 chars) — the catalog is templates-only, never tenant data.", gate };
  }
  for (const field of input.credentialFields ?? []) {
    if (!field?.name || !/^[a-zA-Z0-9._:-]+$/.test(field.name)) {
      return { ok: false, error: `credential field name invalid: '${field?.name}'`, gate };
    }
    if (looksLikePlaintextSecret(field.label ?? "")) {
      return { ok: false, error: `credential field '${field.name}' label looks like a live token value — specs only (name/label), never values.`, gate };
    }
  }
  mcpProtocolSchema.parse(input.protocol);
  const plugin: MarketplacePlugin = {
    pluginId,
    name: input.name.trim(),
    category: input.category?.trim() || "productivity",
    description: input.description.trim(),
    provider: input.provider?.trim() || pluginId,
    endpointTemplate: input.endpointTemplate,
    protocol: input.protocol,
    credentialFields: (input.credentialFields ?? []).map((f) => ({ ...f })),
    trustLevel: "untrusted",
    docsUrl: input.docsUrl,
    license: input.license,
    upstreamUrl: input.upstreamUrl,
  };
  marketplaceRegistryExtras.push(plugin);
  return { ok: true, plugin, gate };
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

/** Test hygiene: drop runtime registrations (frozen seeds are untouched). */
export function clearMarketplaceRegistry(): void {
  marketplaceRegistryExtras.length = 0;
}
