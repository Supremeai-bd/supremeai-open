import { z } from "zod";

export const mcpProtocolSchema = z.enum(["stdio", "sse", "streamable-http"]);
export const mcpTrustLevelSchema = z.enum(["builtin", "verified", "tenant", "untrusted"]);
export const mcpServerStatusSchema = z.enum(["pending", "active", "quarantined", "revoked"]);
export const mcpCapabilityKindSchema = z.enum(["tool", "resource", "prompt"]);

export const mcpServerManifestSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1).max(128),
  version: z.string().min(1).max(64),
  protocol: mcpProtocolSchema,
  endpoint: z.string().url().optional(),
  trustLevel: mcpTrustLevelSchema,
  tenantId: z.string().min(1).optional(),
  status: mcpServerStatusSchema,
});

export const mcpCapabilitySchema = z.object({
  serverId: z.string().min(1),
  name: z.string().min(1).max(256),
  kind: mcpCapabilityKindSchema,
  inputSchema: z.record(z.string(), z.unknown()),
  outputSchema: z.record(z.string(), z.unknown()).optional(),
  requiredScopes: z.array(z.string().min(1)).max(32),
  riskLevel: z.string().min(1).max(32),
  approvalRequired: z.boolean(),
  dataClasses: z.array(z.string().min(1)).max(32),
});

export type McpProtocol = z.infer<typeof mcpProtocolSchema>;
export type McpTrustLevel = z.infer<typeof mcpTrustLevelSchema>;
export type McpServerStatus = z.infer<typeof mcpServerStatusSchema>;
export type McpCapabilityKind = z.infer<typeof mcpCapabilityKindSchema>;
export type McpServerManifest = z.infer<typeof mcpServerManifestSchema>;
export type McpCapability = z.infer<typeof mcpCapabilitySchema>;

export const BUILTIN_SERVER_ID = "supremeai-control-tower";
export const PUBLIC_MCP_SCOPES = new Set(["health:read", "system:read", "audit:read"]);

export function isPublicMcpScope(scope: string): boolean {
  return PUBLIC_MCP_SCOPES.has(scope);
}

export function isSafePublicManifest(manifest: McpServerManifest): boolean {
  return manifest.trustLevel === "builtin" && manifest.status === "active";
}

export function createBuiltinManifest(version: string): McpServerManifest {
  return {
    id: BUILTIN_SERVER_ID,
    name: "SupremeAI Control Tower",
    version,
    protocol: "streamable-http",
    trustLevel: "builtin",
    status: "active",
  };
}

export function validateMcpManifest(input: unknown): McpServerManifest {
  return mcpServerManifestSchema.parse(input);
}

export function validateMcpCapability(input: unknown): McpCapability {
  return mcpCapabilitySchema.parse(input);
}
