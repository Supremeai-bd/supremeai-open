import { connectOutbound } from "./outbound-client.js";
import { discoverServer, getDiscoverySnapshot, type DiscoveredTool } from "./server-discovery.js";
import { getRemoteServer, listRemoteServers, type RemoteMcpServer } from "../registry/remote-mcp-servers.js";

export interface AggregatedTool extends DiscoveredTool { qualifiedName: string; }

export function listAggregatedTools(tenantId = "*"): AggregatedTool[] {
  return listRemoteServers(tenantId).flatMap((server) => (getDiscoverySnapshot(server.id)?.tools ?? []).map((tool) => ({ ...tool, qualifiedName: `${server.id}.${tool.name}` })));
}

export async function refreshServer(server: RemoteMcpServer): Promise<AggregatedTool[]> {
  const snapshot = await discoverServer(server);
  return snapshot.tools.map((tool) => ({ ...tool, qualifiedName: `${server.id}.${tool.name}` }));
}

export async function callAggregatedTool(qualifiedName: string, args: Record<string, unknown>, tenantId = "*") {
  const separator = qualifiedName.indexOf(".");
  if (separator < 1) throw new Error("Tool name must use <serverId>.<toolName>");
  const serverId = qualifiedName.slice(0, separator);
  const toolName = qualifiedName.slice(separator + 1);
  const server = getRemoteServer(serverId, tenantId);
  if (!server || server.status !== "active") throw new Error("Remote MCP server is unavailable or not approved");
  const known = getDiscoverySnapshot(serverId)?.tools.some((tool) => tool.name === toolName);
  if (!known) throw new Error("Remote tool is not present in the discovery snapshot");
  const connection = await connectOutbound({ id: server.id, protocol: server.protocol, endpoint: server.endpoint, command: server.command, args: server.args, headers: server.headers });
  try { return await connection.client.callTool({ name: toolName, arguments: args }); }
  finally { await connection.close(); }
}
