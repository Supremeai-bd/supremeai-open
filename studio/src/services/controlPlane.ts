import { fetchWithRetry, getApiBaseUrl } from '../utils/api'

export type ServiceStatus = 'healthy' | 'degraded' | 'unconfigured' | 'timeout' | 'unreachable' | 'unhealthy'

export interface ServiceDefinition {
  id: string
  display_name: string
  role: string
  capabilities: string[]
  critical: boolean
  configured: boolean
  health_path: string
}

export interface CapabilityDefinition {
  id: string
  service_id: string
  available: boolean
}

export interface ControlPlaneRegistry {
  version: string
  timestamp: string
  services: ServiceDefinition[]
  capabilities: CapabilityDefinition[]
}

export interface ServiceHealth extends ServiceDefinition {
  status: ServiceStatus
  status_code?: number
  error?: string
  latency_ms?: number
  checked_at: string
}

export interface ControlPlaneHealth {
  version: string
  timestamp: string
  overall_status: 'healthy' | 'degraded'
  services: ServiceHealth[]
}

export interface McpHealthDashboard {
  snapshots: Record<string, Record<string, unknown>>
  dependencies: Record<string, string[]>
  timestamp: string
}

export interface McpHealthSummary {
  status: 'healthy' | 'degraded' | 'unknown'
  serviceCount: number
  unhealthyCount: number
  services: Array<{ provider: string; status: string; checkedAt: string; latencyMs?: number }>
  timestamp: string
}

export type ExternalClientRole = 'viewer' | 'agent' | 'admin'
export type ExternalClientProtocol = 'streamable-http' | 'sse' | 'stdio' | 'custom'

export interface ExternalClient {
  id: string
  name: string
  provider: string
  protocol: ExternalClientProtocol
  role: ExternalClientRole
  scopes: string[]
  status: 'pending' | 'active' | 'revoked' | 'expired'
  createdAt: string
  updatedAt: string
  expiresAt?: string
  lastSeenAt?: string
}

export interface CreatedExternalClient {
  client: ExternalClient
  token: string
}

export interface TenantCapability {
  name: string
  circle: string
  risk: string
  approval_required: boolean
  enabled: boolean
  version: string
}

export interface CapabilityExecutionResult {
  execution_id: string
  status: string
  data?: unknown
  response?: string
  error?: string
  error_code?: string
  error_message?: string
  capability: string
  verification?: { verified: boolean; method: string; details?: Record<string, unknown> }
  audit?: { event_type: string; policy_version: string; approval_id?: string }
}

import { getAuthHeaders } from './apiClient'

async function getJson<T>(path: string): Promise<T> {
  const correlationId = globalThis.crypto?.randomUUID?.() ?? `cp-${Date.now()}`
  const authHeaders = await getAuthHeaders().catch(() => ({}))
  const response = await fetchWithRetry(path.startsWith('http') ? path : `${getApiBaseUrl(path)}${path}`, {
    headers: { Accept: 'application/json', 'X-Correlation-ID': correlationId, ...authHeaders },
    signal: AbortSignal.timeout(10000),
  })
  if (!response.ok) throw new Error(`Control plane request failed: ${response.status}`)
  return response.json() as Promise<T>
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const correlationId = globalThis.crypto?.randomUUID?.() ?? `cp-${Date.now()}`
  const authHeaders = await getAuthHeaders().catch(() => ({}))
  const response = await fetchWithRetry(path.startsWith('http') ? path : `${getApiBaseUrl(path)}${path}`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId, ...authHeaders },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10000),
  })
  if (!response.ok) throw new Error(`Control plane request failed: ${response.status}`)
  return response.json() as Promise<T>
}

async function deleteJson<T>(path: string): Promise<T> {
  const correlationId = globalThis.crypto?.randomUUID?.() ?? `cp-${Date.now()}`
  const authHeaders = await getAuthHeaders().catch(() => ({}))
  const response = await fetchWithRetry(path.startsWith('http') ? path : `${getApiBaseUrl(path)}${path}`, {
    method: 'DELETE',
    headers: { Accept: 'application/json', 'X-Correlation-ID': correlationId, ...authHeaders },
    signal: AbortSignal.timeout(10000),
  })
  if (!response.ok) throw new Error(`Could not revoke connection: ${response.status}`)
  return response.json() as Promise<T>
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const correlationId = globalThis.crypto?.randomUUID?.() ?? `cp-${Date.now()}`
  const authHeaders = await getAuthHeaders().catch(() => ({}))
  const response = await fetchWithRetry(path.startsWith('http') ? path : `${getApiBaseUrl(path)}${path}`, {
    method: 'PATCH',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId, ...authHeaders },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10000),
  })
  if (!response.ok) throw new Error(`Could not change role: ${response.status}`)
  return response.json() as Promise<T>
}

  export interface TaskSubmission {
  goal: string
  metadata?: Record<string, unknown>
  }

  export interface TaskHandle {
  task_id: string
  status: string
  }

  export const controlPlane = {
  registry: () => getJson<ControlPlaneRegistry>('/api/v1/control-plane/registry'),
  capabilities: () => getJson<{ capabilities: TenantCapability[] }>('/api/v1/capabilities'),
  executeCapability: (payload: { capability: string; source: 'dashboard' | 'chat' | 'api'; payload?: Record<string, unknown> }) => postJson<CapabilityExecutionResult>('/api/v1/capabilities/execute', payload),
  health: () => getJson<ControlPlaneHealth>('/api/v1/control-plane/health'),
  mcpSummary: () => getJson<McpHealthSummary>(`${import.meta.env.VITE_MCP_CONTROL_PLANE_URL ?? ''}/health/summary`),
  mcpDashboard: () => getJson<McpHealthDashboard>(`${import.meta.env.VITE_MCP_CONTROL_PLANE_URL ?? ''}/health/dashboard`),
  mcpSweep: () => postJson<Record<string, unknown>>(`${import.meta.env.VITE_MCP_CONTROL_PLANE_URL ?? ''}/health/sweep`, {}),
  listExternalClients: () => getJson<{ clients: ExternalClient[] }>(`${import.meta.env.VITE_MCP_CONTROL_PLANE_URL ?? ''}/clients`),
  createExternalClient: (payload: { name: string; provider?: string; protocol?: ExternalClientProtocol; role: ExternalClientRole }) => postJson<CreatedExternalClient>(`${import.meta.env.VITE_MCP_CONTROL_PLANE_URL ?? ''}/clients`, payload),
  approveExternalClient: (id: string) => postJson<ExternalClient>(`${import.meta.env.VITE_MCP_CONTROL_PLANE_URL ?? ''}/clients/${encodeURIComponent(id)}/approve`, {}),
  changeExternalClientRole: (id: string, role: ExternalClientRole) => patchJson<ExternalClient>(`${import.meta.env.VITE_MCP_CONTROL_PLANE_URL ?? ''}/clients/${encodeURIComponent(id)}`, { role }),
  revokeExternalClient: (id: string) => deleteJson<{ revoked: boolean }>(`${import.meta.env.VITE_MCP_CONTROL_PLANE_URL ?? ''}/clients/${encodeURIComponent(id)}`),
  rotateExternalClient: (id: string) => postJson<CreatedExternalClient>(`${import.meta.env.VITE_MCP_CONTROL_PLANE_URL ?? ''}/clients/${encodeURIComponent(id)}/rotate`, {}),
  submitTask: (payload: TaskSubmission) => postJson<TaskHandle>('/api/v1/tasks', payload),
  taskStatus: (taskId: string) => getJson<TaskHandle>(`/api/v1/tasks/${encodeURIComponent(taskId)}`),
  cancelTask: (taskId: string) => postJson<TaskHandle>(`/api/v1/tasks/${encodeURIComponent(taskId)}/cancel`, {}),
  }

export function capabilityAvailable(registry: ControlPlaneRegistry | undefined, capability: string): boolean {
  return registry?.capabilities.some((item) => item.id === capability && item.available) ?? false
}
