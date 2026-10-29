import { connectOutbound } from "./outbound-client.js";
import { discoverServer, getDiscoverySnapshot, type DiscoveredTool } from "./server-discovery.js";
import { getRemoteServer, listRemoteServers, updateRemoteServerStatus, type RemoteMcpServer } from "../registry/remote-mcp-servers.js";
import { ToolDescriptorMutatedError, defaultReverifyTtlMs, isVerificationFresh, markVerified, verifyDescriptorsForCall, type PinInputTool } from "./descriptor-pinning.js";
import { recordSlotAudit } from "../policy/slot-audit.js";

export interface AggregatedTool extends DiscoveredTool { qualifiedName: string; }

export function listAggregatedTools(tenantId = "*"): AggregatedTool[] {
  return listRemoteServers(tenantId).flatMap((server) => (getDiscoverySnapshot(server.id)?.tools ?? []).map((tool) => ({ ...tool, qualifiedName: `${server.id}.${tool.name}` })));
}

export async function refreshServer(server: RemoteMcpServer): Promise<AggregatedTool[]> {
  const snapshot = await discoverServer(server);
  return snapshot.tools.map((tool) => ({ ...tool, qualifiedName: `${server.id}.${tool.name}` }));
}

/** Fetch the CURRENT tools/list from the remote (rug-pull detection needs the live surface, not the cache). */
export async function fetchFreshToolList(server: RemoteMcpServer): Promise<PinInputTool[]> {
  const connection = await connectOutbound({ id: server.id, protocol: server.protocol, endpoint: server.endpoint, command: server.command, args: server.args, headers: server.headers });
  try {
    const result = await connection.client.listTools();
    return (result.tools ?? []).map((tool) => ({ name: tool.name, description: tool.description, inputSchema: tool.inputSchema as Record<string, unknown> }));
  } finally { await connection.close(); }
}

/**
 * #1712 call gate: verify a freshly fetched tool surface against the approved
 * descriptor pins. ANY drift fails CLOSED — typed tool_descriptor_mutated
 * error, server quarantined (cross-tenant injection surface), slot-audit
 * denial recorded. Exported for direct testability without a live remote.
 */
export function applyCallGate(server: RemoteMcpServer, freshTools: PinInputTool[]): void {
  const verification = verifyDescriptorsForCall(server.id, freshTools);
  if (verification.ok) { markVerified(server.id); return; }
  const detail = verification.diffs.map((diff) => `${diff.toolName}:${diff.kind}`).join(", ");
  updateRemoteServerStatus(server.id, "quarantined", `tool_descriptor_mutated: ${detail}`);
  recordSlotAudit({ operation: "tool-call", tool: `${server.id}.*`, outcome: "denied", reason: `tool_descriptor_mutated: ${detail}`, tenantId: server.tenantId });
  throw new ToolDescriptorMutatedError(server.id, verification.diffs);
}

/** TTL-bounded re-verification: at most one extra tools/list round-trip per TTL window. */
export async function verifyDescriptorFreshness(server: RemoteMcpServer, ttlMs = defaultReverifyTtlMs()): Promise<void> {
  if (isVerificationFresh(server.id, ttlMs)) return;
  const freshTools = await fetchFreshToolList(server);
  applyCallGate(server, freshTools);
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
  // #1712: re-verify the live descriptor surface BEFORE executing — a server
  // that mutated its tools since approval is blocked here, fail-closed.
  await verifyDescriptorFreshness(server);
  const connection = await connectOutbound({ id: server.id, protocol: server.protocol, endpoint: server.endpoint, command: server.command, args: server.args, headers: server.headers });
  try { return await connection.client.callTool({ name: toolName, arguments: args }); }
  finally { await connection.close(); }
}
