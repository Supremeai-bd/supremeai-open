import { randomUUID } from "node:crypto";
import { mcpProtocolSchema, mcpServerStatusSchema, mcpTrustLevelSchema, type McpProtocol, type McpServerStatus, type McpTrustLevel } from "./mcp.contracts.js";

export interface RemoteMcpServer {
  id: string;
  name: string;
  protocol: McpProtocol;
  endpoint?: string;
  command?: string;
  args?: string[];
  headers?: Record<string, string>;
  tenantId: string;
  scopes: string[];
  trustLevel: McpTrustLevel;
  status: McpServerStatus;
  createdAt: string;
  updatedAt: string;
  lastError?: string;
}

const servers = new Map<string, RemoteMcpServer>();

export function registerRemoteServer(input: Omit<RemoteMcpServer, "id" | "createdAt" | "updatedAt" | "status">): RemoteMcpServer {
  if (input.protocol !== "stdio" && !input.endpoint) throw new Error("endpoint is required for HTTP MCP servers");
  if (input.protocol === "stdio" && !input.command) throw new Error("command is required for stdio MCP servers");
  mcpProtocolSchema.parse(input.protocol);
  mcpTrustLevelSchema.parse(input.trustLevel);
  const now = new Date().toISOString();
  const server: RemoteMcpServer = { ...input, id: `remote_${randomUUID()}`, status: "pending", createdAt: now, updatedAt: now };
  servers.set(server.id, server);
  return { ...server };
}

export function listRemoteServers(tenantId = "*"): RemoteMcpServer[] {
  return [...servers.values()].filter((server) => tenantId === "*" || server.tenantId === tenantId).map((server) => ({ ...server }));
}

export function getRemoteServer(id: string, tenantId = "*"): RemoteMcpServer | undefined {
  const server = servers.get(id);
  return server && (tenantId === "*" || server.tenantId === tenantId) ? { ...server } : undefined;
}

export function updateRemoteServerStatus(id: string, status: McpServerStatus, lastError?: string): RemoteMcpServer | undefined {
  const server = servers.get(id);
  if (!server) return undefined;
  mcpServerStatusSchema.parse(status);
  const updated = { ...server, status, lastError, updatedAt: new Date().toISOString() };
  servers.set(id, updated);
  return { ...updated };
}

export function clearRemoteServerRegistry(): void { servers.clear(); }
