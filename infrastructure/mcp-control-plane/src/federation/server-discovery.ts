import { connectOutbound, type OutboundServerConfig } from "./outbound-client.js";
import { updateRemoteServerStatus, type RemoteMcpServer } from "../registry/remote-mcp-servers.js";

export interface DiscoveredTool { name: string; description?: string; inputSchema: Record<string, unknown>; serverId: string; }
export interface DiscoverySnapshot { serverId: string; tools: DiscoveredTool[]; discoveredAt: string; }

const cache = new Map<string, DiscoverySnapshot>();

export async function discoverServer(server: RemoteMcpServer): Promise<DiscoverySnapshot> {
  const connection = await connectOutbound({
    id: server.id, protocol: server.protocol, endpoint: server.endpoint, command: server.command,
    args: server.args, headers: server.headers,
  } satisfies OutboundServerConfig);
  try {
    const result = await connection.client.listTools();
    const snapshot = {
      serverId: server.id,
      tools: (result.tools ?? []).map((tool) => ({ name: tool.name, description: tool.description, inputSchema: tool.inputSchema as Record<string, unknown>, serverId: server.id })),
      discoveredAt: new Date().toISOString(),
    };
    cache.set(server.id, snapshot);
    updateRemoteServerStatus(server.id, "active");
    return snapshot;
  } catch (error) {
    updateRemoteServerStatus(server.id, "quarantined", String(error));
    throw error;
  } finally { await connection.close(); }
}

export function getDiscoverySnapshot(serverId: string): DiscoverySnapshot | undefined { return cache.get(serverId); }
export function listDiscoverySnapshots(): DiscoverySnapshot[] { return [...cache.values()]; }
export function clearDiscoveryCache(): void { cache.clear(); }
