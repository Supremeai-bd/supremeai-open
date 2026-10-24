export interface McpViewerData {
  server: Record<string, unknown>
  health: Record<string, unknown> | null
  dashboard: Record<string, unknown> | null
  capabilities: unknown[]
  resources: unknown[]
  tools: unknown[]
  raw: Record<string, unknown>
}

function normalizeUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, '')
  return trimmed.replace(/\/mcp$/i, '')
}

async function getJson(url: string, token: string): Promise<Record<string, unknown>> {
  // Justified raw fetch (Issue #2522): URL ইউজার-কনফিগার করা EXTERNAL MCP
  // সার্ভার — আমাদের backend নয়; নিজস্ব 10s AbortSignal.timeout আছে।
  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
      ...(token.trim() ? { Authorization: `Bearer ${token.trim()}` } : {}),
    },
    signal: AbortSignal.timeout(10000),
  })
  if (!response.ok) {
    const error = new Error(`MCP server returned ${response.status}`) as Error & { status?: number }
    error.status = response.status
    throw error
  }
  const payload: unknown = await response.json()
  return payload && typeof payload === 'object' ? payload as Record<string, unknown> : { value: payload }
}

function arrayFrom(payload: Record<string, unknown>, ...keys: string[]): unknown[] {
  for (const key of keys) {
    if (Array.isArray(payload[key])) return payload[key]
  }
  return []
}

export function normalizeMcpUrl(value: string): string {
  return normalizeUrl(value)
}

export async function loadMcpViewerData(value: string, token = ''): Promise<McpViewerData> {
  const baseUrl = normalizeUrl(value)
  if (!baseUrl) throw new Error('Enter an MCP server URL.')
  let health: Record<string, unknown> | null = null
  let dashboard: Record<string, unknown> | null = null
  let manifest: Record<string, unknown> = {}

  try {
    health = await getJson(`${baseUrl}/health/summary`, token)
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes('404')) throw error
  }

  try {
    dashboard = await getJson(`${baseUrl}/health/dashboard`, token)
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes('404')) throw error
  }

  try {
    manifest = await getJson(`${baseUrl}/manifest`, token)
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes('404')) {
      try {
        manifest = await getJson(`${baseUrl}/mcp/manifest`, token)
      } catch (err) {
        // health/dashboard data is still useful — log and continue without a manifest.
        console.warn('[mcp-viewer] /mcp/manifest fetch failed, continuing without manifest:', err)
      }
    }
  }

  if (!health && !dashboard && !Object.keys(manifest).length) throw new Error('This URL does not expose a readable MCP viewer endpoint.')

  const raw = { ...manifest, health, dashboard }
  return {
    server: manifest,
    health,
    dashboard,
    capabilities: arrayFrom(manifest, 'capabilities', 'tools', 'features'),
    resources: arrayFrom(manifest, 'resources'),
    tools: arrayFrom(manifest, 'tools'),
    raw,
  }
}

export function formatViewerValue(value: unknown): string {
  if (typeof value === 'string') return value
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
}
