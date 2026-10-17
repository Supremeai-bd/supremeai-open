/**
 * Federation Cockpit — telemetry service.
 *
 * Zero-dependency client for the MCP Tower monitoring surfaces: HTTP
 * snapshot polling plus SSE live-tail parsing. Pure helpers are exported
 * separately so the cockpit test battery can exercise them without a
 * network or a component renderer.
 */

import type {
  CiStatus,
  FederationSnapshot,
  RawTowerSnapshot,
  RunwayEntry,
  RunwayStage,
  SatelliteHealth,
  SwarmDefenseState,
  SatelliteId,
} from '../types/federation';
import { SATELLITE_IDS as SATELLITE_ID_LIST } from '../types/federation';

const VALID_STAGES: readonly RunwayStage[] = ['queued', 'in-gates', 'landed', 'self-healing'];
const VALID_CI: readonly CiStatus[] = ['green', 'red', 'amber'];

export class TelemetryError extends Error {
  readonly status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = 'TelemetryError';
    this.status = status;
  }
}

/** Map a raw Tower payload onto the cockpit snapshot contract. */
export function normalizeSnapshot(raw: RawTowerSnapshot, now = new Date()): FederationSnapshot {
  const satellites: SatelliteHealth[] = SATELLITE_ID_LIST.map((id) => {
    const entry = raw.satellites?.[id] ?? {};
    return {
      id: id as SatelliteId,
      displayName: id.charAt(0).toUpperCase() + id.slice(1),
      healthy: entry.healthy === true,
      latestSha: entry.sha,
      lastSyncedAt: entry.lastSyncedAt,
      activeClaims: entry.activeClaims ?? 0,
      latencyMs: entry.latencyMs,
    };
  });

  const runway: RunwayEntry[] = (raw.workOrders ?? [])
    .filter((w): w is typeof w & { taskId: string } => typeof w.taskId === 'string' && w.taskId.length > 0)
    .map((w) => ({
      taskId: String(w.taskId),
      title: w.title ?? w.taskId,
      stage: VALID_STAGES.includes(w.stage as RunwayStage) ? (w.stage as RunwayStage) : 'queued',
      ciStatus: VALID_CI.includes(w.ciStatus as CiStatus) ? (w.ciStatus as CiStatus) : 'amber',
      diagnostics: w.diagnostics,
      prNumber: w.prNumber,
      updatedAt: w.updatedAt,
    }));

  const defense: SwarmDefenseState = {
    activeClaims: raw.defense?.activeClaims ?? 0,
    claimRejections: raw.defense?.claimRejections ?? 0,
    rateLimitCapacity: raw.defense?.rateLimitCapacity ?? 0,
    taskVelocityPerHour: raw.defense?.taskVelocityPerHour ?? 0,
  };

  return { capturedAt: raw.capturedAt ?? now.toISOString(), satellites, runway, defense };
}

/** Minimal SSE frame parser: multi-line data, CRLF, [DONE] sentinel. */
export class CockpitSSEParser {
  private buffer = '';
  private dataLines: string[] = [];

  push(chunk: string): string[] {
    this.buffer += chunk;
    const out: string[] = [];
    let idx = this.buffer.search(/\r?\n|\r/);
    while (idx !== -1) {
      const line = this.buffer.slice(0, idx);
      const sep = this.buffer.startsWith('\r\n', idx) ? 2 : 1;
      this.buffer = this.buffer.slice(idx + sep);
      if (line === '') {
        if (this.dataLines.length) {
          out.push(this.dataLines.join('\n'));
          this.dataLines = [];
        }
      } else if (!line.startsWith(':') && line.startsWith('data:')) {
        this.dataLines.push(line.slice(5).replace(/^ /, ''));
      }
      idx = this.buffer.search(/\r?\n|\r/);
    }
    return out;
  }

  finish(): string[] {
    if (this.buffer !== '') {
      const line = this.buffer;
      this.buffer = '';
      if (!line.startsWith(':') && line.startsWith('data:')) {
        this.dataLines.push(line.slice(5).replace(/^ /, ''));
      }
    }
    const rest = this.dataLines;
    this.dataLines = [];
    return rest.length ? [rest.join('\n')] : [];
  }
}

export interface TelemetryClientOptions {
  /** Tower base URL; falsy means same-origin paths (reverse-proxy setups). */
  baseUrl?: string;
  /** Snapshot poll interval in milliseconds. Default 15000. */
  pollIntervalMs?: number;
  fetchImpl?: typeof fetch;
}

type SnapshotListener = (snapshot: FederationSnapshot) => void;

/** Polling telemetry client with manual-tick support for tests. */
export class TelemetryClient {
  private readonly baseUrl: string;
  private readonly pollIntervalMs: number;
  private readonly fetchImpl: typeof fetch;
  private timer: ReturnType<typeof setInterval> | undefined;
  private readonly listeners = new Set<SnapshotListener>();

  constructor(options: TelemetryClientOptions = {}) {
    const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
    this.baseUrl = (options.baseUrl ?? env?.SUPREMEAI_TOWER_URL ?? '').replace(/\/+$/, '');
    this.pollIntervalMs = options.pollIntervalMs ?? 15000;
    this.fetchImpl = options.fetchImpl ?? fetch.bind(globalThis);
  }

  async fetchSnapshot(): Promise<FederationSnapshot> {
    const response = await this.fetchImpl(this.baseUrl + '/monitoring/federation', {
      headers: { accept: 'application/json' },
    });
    if (!response.ok) {
      throw new TelemetryError('tower snapshot request failed', response.status);
    }
    const raw = (await response.json()) as RawTowerSnapshot;
    return normalizeSnapshot(raw);
  }

  /** Subscribe to snapshots; fires immediately with a fresh fetch. */
  async subscribe(listener: SnapshotListener): Promise<() => void> {
    this.listeners.add(listener);
    await this.tick();
    this.timer = setInterval(() => {
      void this.tick();
    }, this.pollIntervalMs);
    return () => {
      this.listeners.delete(listener);
      if (this.timer) {
        clearInterval(this.timer);
        this.timer = undefined;
      }
    };
  }

  /** One poll cycle; exported for deterministic tests. */
  async tick(): Promise<void> {
    try {
      const snapshot = await this.fetchSnapshot();
      for (const listener of this.listeners) {
        listener(snapshot);
      }
    } catch {
      /* degrade honestly: cockpit keeps the last good snapshot */
    }
  }

  dispose(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = undefined;
    }
    this.listeners.clear();
  }
}
