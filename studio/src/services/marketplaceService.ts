// marketplaceService — #1523 Marketplace MVP (MCP plugins tab)
// Talks to the control plane's /mcp JSON-RPC surface (streamable-http):
// initialize -> Mcp-Session-Id -> tools/call. Uses the EXISTING governed
// tools — `marketplace.*` for catalog/connect and `client.discover_mcp_server`
// for descriptor pinning — so the UI adds zero new trust surfaces.
// Zero-plaintext invariant: the UI passes only vault REFERENCES; a
// client-side plaintext guard mirrors the server-side one (fail first, locally).

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
  endpointTemplate: string | null;
  protocol: string;
  credentialFields: MarketplaceCredentialField[];
  trustLevel: string;
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

export interface DiscoverResult {
  serverId: string;
  toolCount: number;
  tools: Array<{ name: string; description?: string }>;
}

// Bundled mirror of the Phase-1 catalog (control-plane
// src/registry/marketplace-plugins.ts + SQL migration 20261030). Used as an
// OFFLINE snapshot — always rendered with an explicit offline notice, never
// silently substituted for a live read.
export const BUNDLED_PLUGINS: readonly MarketplacePlugin[] = Object.freeze([
  {
    pluginId: 'github',
    name: 'GitHub',
    category: 'devtools',
    description:
      'Official remote GitHub MCP server: repos, issues, pull requests and workflows under governed tool relay.',
    provider: 'github',
    endpointTemplate: 'https://api.githubcopilot.com/mcp/',
    protocol: 'streamable-http',
    credentialFields: [
      { name: 'github-token', label: 'GitHub personal access token (vault ref)', required: true, secret: true },
    ],
    trustLevel: 'untrusted',
    docsUrl: 'https://github.com/github/github-mcp-server',
  },
  {
    pluginId: 'telegram',
    name: 'Telegram',
    category: 'messaging',
    description:
      'Bring your own Telegram bot gateway MCP server for message send/receive automation inside your tenant.',
    provider: 'telegram',
    endpointTemplate: null,
    protocol: 'streamable-http',
    credentialFields: [
      { name: 'bot-token', label: 'Telegram bot token (vault ref)', required: true, secret: true },
    ],
    trustLevel: 'untrusted',
    docsUrl: null,
  },
  {
    pluginId: 'web-search',
    name: 'Web Search',
    category: 'research',
    description:
      'Bring your own web-search MCP server (SearXNG, Brave-compatible relays, or any compatible endpoint).',
    provider: 'web-search',
    endpointTemplate: null,
    protocol: 'streamable-http',
    credentialFields: [
      { name: 'search-api-key', label: 'Search API key (vault ref)', required: true, secret: true },
    ],
    trustLevel: 'untrusted',
    docsUrl: null,
  },
  {
    pluginId: 'google-drive',
    name: 'Google Drive',
    category: 'productivity',
    description:
      'Bring your own Google Drive MCP server for file listing, reading and sharing workflows.',
    provider: 'google',
    endpointTemplate: null,
    protocol: 'streamable-http',
    credentialFields: [
      { name: 'drive-token', label: 'Google OAuth token (vault ref)', required: true, secret: true },
    ],
    trustLevel: 'untrusted',
    docsUrl: null,
  },
  {
    pluginId: 'notion',
    name: 'Notion',
    category: 'productivity',
    description:
      'Official hosted Notion MCP server: pages, databases and comments under governed tool relay.',
    provider: 'notion',
    endpointTemplate: 'https://mcp.notion.com/mcp',
    protocol: 'streamable-http',
    credentialFields: [
      { name: 'notion-token', label: 'Notion integration token (vault ref)', required: true, secret: true },
    ],
    trustLevel: 'untrusted',
    docsUrl: 'https://developers.notion.com/docs/mcp',
  },
]);

// Client-side mirror of the server's plaintext-secret families: reject
// live-token-shaped input BEFORE it ever leaves the page.
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

const controlPlaneBase = (): string =>
  (import.meta.env.VITE_MCP_CONTROL_PLANE_URL as string | undefined)?.replace(/\/+$/, '') ?? '';

interface JsonRpcResponse {
  result?: { content?: Array<{ type: string; text?: string }> };
  error?: { code: number; message: string };
}

async function callControlPlaneTool<T>(tool: string, args: Record<string, unknown>): Promise<T> {
  const base = controlPlaneBase();
  if (!base) throw new Error('MCP control plane URL is not configured.');

  const initRes = await fetch(`${base}/mcp`, {
    method: 'POST',
    headers: { Accept: 'application/json, text/event-stream', 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: '2025-03-26',
        capabilities: {},
        clientInfo: { name: 'supremeai-marketplace', version: '1.0.0' },
      },
    }),
    signal: AbortSignal.timeout(10000),
  });
  if (!initRes.ok) throw new Error(`Control plane initialize failed: ${initRes.status}`);
  const sessionId = initRes.headers.get('mcp-session-id');

  const callRes = await fetch(`${base}/mcp`, {
    method: 'POST',
    headers: {
      Accept: 'application/json, text/event-stream',
      'Content-Type': 'application/json',
      ...(sessionId ? { 'Mcp-Session-Id': sessionId } : {}),
    },
    body: JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: tool, arguments: args } }),
    signal: AbortSignal.timeout(10000),
  });
  if (!callRes.ok) throw new Error(`Control plane tools/call failed: ${callRes.status}`);

  const contentType = callRes.headers.get('content-type') ?? '';
  let payload: JsonRpcResponse;
  if (contentType.includes('text/event-stream')) {
    const text = await callRes.text();
    const dataLine = text
      .split('\n')
      .filter((l) => l.startsWith('data: '))
      .map((l) => l.slice(6))
      .pop();
    payload = dataLine ? (JSON.parse(dataLine) as JsonRpcResponse) : {};
  } else {
    payload = (await callRes.json()) as JsonRpcResponse;
  }
  if (payload.error) throw new Error(payload.error.message || `Tool call failed: ${tool}`);
  const textBlock = payload.result?.content?.find((c) => c.type === 'text')?.text;
  if (typeof textBlock !== 'string') throw new Error(`Tool '${tool}' returned no text content.`);
  return JSON.parse(textBlock) as T;
}

export async function listMarketplacePlugins(): Promise<MarketplacePlugin[]> {
  const res = await callControlPlaneTool<{ count: number; plugins: MarketplacePlugin[] }>(
    'marketplace.list_plugins',
    {},
  );
  return res.plugins;
}

export async function connectMarketplacePlugin(input: {
  pluginId: string;
  credentialVaultRef: string;
  endpoint?: string;
}): Promise<{ connection: MarketplaceConnection; nextStep: string }> {
  const cleanRef = input.credentialVaultRef.trim();
  if (looksLikePlaintextSecret(cleanRef)) {
    throw new Error('That looks like a live token. Store it in your vault and pass the reference (vault:<key>).');
  }
  const res = await callControlPlaneTool<{
    connection: MarketplaceConnection;
    nextStep: string;
  }>('marketplace.connect_plugin', {
    pluginId: input.pluginId,
    credentialVaultRef: cleanRef,
    ...(input.endpoint ? { endpoint: input.endpoint } : {}),
  });
  return { connection: res.connection, nextStep: res.nextStep };
}

// Uses the EXISTING client.discover_mcp_server tool — descriptor pinning is
// what keeps every marketplace connection fail-closed (#1712).
export async function discoverMarketplaceServer(
  serverId: string,
): Promise<DiscoverResult> {
  const res = await callControlPlaneTool<{
    server: { id: string };
    tools: Array<{ name: string; description?: string }>;
    descriptorStatus?: unknown;
  }>('client.discover_mcp_server', { serverId });
  return {
    serverId: res.server?.id ?? serverId,
    toolCount: Array.isArray(res.tools) ? res.tools.length : 0,
    tools: Array.isArray(res.tools) ? res.tools : [],
  };
}
