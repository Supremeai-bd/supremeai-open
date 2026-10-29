import { connectOutbound, type OutboundServerConfig } from "./outbound-client.js";
import { updateRemoteServerStatus, type RemoteMcpServer } from "../registry/remote-mcp-servers.js";
import { pinDescriptors } from "./descriptor-pinning.js";

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
    // #1712: every discovery pins the observed tool surface (SHA-256 per
    // descriptor). Changes against an existing baseline become PENDING only —
    // they block remote.call until explicit re-approval (never auto-adopted).
    pinDescriptors(server.id, snapshot.tools);
    cache.set(server.id, snapshot);
    // Note: status "active" here is availability, not descriptor approval —
    // the call-time gate in aggregator.applyCallGate is the security boundary.
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
