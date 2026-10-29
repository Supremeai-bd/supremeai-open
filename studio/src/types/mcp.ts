export interface McpServerInfo {
  name: string;
  version: string;
}

export interface McpCapabilities {
  tools?: { listChanged?: boolean };
  resources?: { listChanged?: boolean };
  prompts?: { listChanged?: boolean };
  roots?: { listChanged?: boolean };
  sampling?: Record<string, any>;
}

export interface McpHandshakeResponse {
  success: boolean;
  status?: number;
  statusText?: string;
  latencyMs: number;
  sessionId?: string | null;
  serverInfo?: McpServerInfo;
  capabilities?: McpCapabilities;
  protocolVersion?: string;
  headers?: {
    contentType?: string | null;
    cfRay?: string | null;
    renderOrigin?: string | null;
    server?: string | null;
  };
  error?: string;
  rawResponse?: string;
}

export interface HealthService {
  id: string;
  displayName: string;
  url?: string;
  status: 'healthy' | 'degraded' | 'unreachable' | 'unconfigured';
  httpStatus?: number;
  latencyMs?: number;
  deployStatus?: string;
  monthlyBuildMinutes?: number;
  freeLimitRemainingMinutes?: number;
  freeLimitExhausted?: boolean;
  error?: string;
}

export interface SystemHealthData {
  summary: string;
  timestamp: string;
  services: HealthService[];
}

export interface McpTool {
  name: string;
  description?: string;
  inputSchema?: {
    type?: string;
    properties?: Record<string, any>;
    required?: string[];
  };
  execution?: {
    taskSupport?: string;
  };
}

export interface CodebaseSyncState {
  workspaceRoot: string;
  totalFiles: number;
  mcpTargetServer: string;
  mcpConfigFile: string;
  mcpConfigLoaded: boolean;
  mcpConfig: any;
  lastSyncTimestamp: string;
  activeSessionId: string | null;
  connectedNodeRole: string;
  files: Array<{ path: string; size: number; modified: string }>;
}
