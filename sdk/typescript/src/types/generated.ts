/**
 * @supremeai/sdk — OpenAPI 3.1 derived contract types.
 *
 * Source of truth: api-schemas/gateway.openapi.yaml (supremeai-open).
 * Regenerate during releases via the OpenAPI sync workflow; do not edit
 * by hand for breaking changes — propose schema PRs instead.
 */

/** Unified task submission accepted by the gateway run endpoint. */
export interface TaskRunRequest {
  /** Logical skill or pipeline identifier to execute. */
  task: string;
  /** Free-form payload consumed by the executing agent. */
  input?: Record<string, unknown>;
  /** Preferred model id; gateway may fail over per its cascade policy. */
  model?: string;
  /** Stable idempotency key for safe retries. */
  idempotencyKey?: string;
  /** Optional key/value metadata echoed back on the run. */
  metadata?: Record<string, string>;
}

export type RunStatus =
  | 'queued'
  | 'planning'
  | 'executing'
  | 'streaming'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

/** A single atomic step inside a run's execution trace. */
export interface TraceStep {
  index: number;
  kind: 'plan' | 'tool_call' | 'observation' | 'token' | 'summary';
  label?: string;
  payload?: unknown;
  startedAt?: string;
  finishedAt?: string;
}

export interface TaskRunResponse {
  id: string;
  status: RunStatus;
  task: string;
  createdAt: string;
  updatedAt: string;
  steps?: TraceStep[];
  result?: unknown;
  error?: GatewayErrorShape;
}

export interface ModelInfo {
  id: string;
  provider: string;
  contextWindow?: number;
  /** Ordered preference for the failover cascade; lower wins. */
  priority?: number;
  healthy?: boolean;
}

export interface HealthResponse {
  ok: boolean;
  version?: string;
  uptimeSeconds?: number;
  satellites?: Record<string, { healthy: boolean; latencyMs?: number }>;
}

/** Normalized gateway error body. */
export interface GatewayErrorShape {
  code: string;
  message: string;
  /** Which upstream model/provider produced the failure, if any. */
  provider?: string;
  retryable?: boolean;
  details?: unknown;
}

/** Streaming deltas for incremental tool call assembly. */
export interface ToolCallDelta {
  index: number;
  id?: string;
  name?: string;
  /** Partial JSON text; concatenate across deltas then JSON.parse. */
  argumentsFragment?: string;
}

/** Server-sent event payloads emitted on a run stream. */
export type StreamEventData =
  | { type: 'token'; text: string }
  | { type: 'tool_call_delta'; delta: ToolCallDelta }
  | { type: 'run_status'; status: RunStatus; runId?: string }
  | { type: 'error'; error: GatewayErrorShape }
  | { type: 'done'; finishReason?: string };

/** Envelope produced by the SSE parser. */
export interface StreamEvent {
  event: string;
  /** Raw data line payload (joined across continuation lines). */
  data: string;
  id?: string;
  /** Parsed convenience view; undefined when data is not valid JSON. */
  parsed?: StreamEventData;
}
