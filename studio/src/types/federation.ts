/**
 * Federation Cockpit — Satellite & Runway data schemas.
 *
 * Canonical telemetry contracts shared by the cockpit components and the
 * telemetry service. Mirrors the MCP Tower monitoring surfaces.
 */

export const SATELLITE_IDS = [
  'open',
  'studio',
  'browser',
  'command',
  'skills',
  'vscode',
  'agents',
  'api',
  'infra',
  'sdk',
  'core',
  'archive',
] as const;

export type SatelliteId = (typeof SATELLITE_IDS)[number];

export interface SatelliteHealth {
  id: SatelliteId;
  displayName: string;
  healthy: boolean;
  /** Short commit SHA of the satellite tip, when reported. */
  latestSha?: string;
  /** ISO timestamp of the last Nightly Train sync. */
  lastSyncedAt?: string;
  /** Count of atomic work-order claims currently held. */
  activeClaims?: number;
  /** Round-trip latency in milliseconds, when probed. */
  latencyMs?: number;
}

export type RunwayStage = 'queued' | 'in-gates' | 'landed' | 'self-healing';

export type CiStatus = 'green' | 'red' | 'amber';

export interface RunwayEntry {
  /** Bridge task id, e.g. bridge-YYYYMMDD-slug. */
  taskId: string;
  title: string;
  stage: RunwayStage;
  ciStatus: CiStatus;
  /** Human-readable failure diagnostics shown on hover when ciStatus is red. */
  diagnostics?: string;
  prNumber?: number;
  updatedAt?: string;
}

export interface SwarmDefenseState {
  /** Work orders currently under atomic claim across the fleet. */
  activeClaims: number;
  /** Cumulative claim-contention rejections (Swarm DoS immunity telemetry). */
  claimRejections: number;
  /** Configured concurrent-claim ceiling. */
  rateLimitCapacity: number;
  /** Incoming WO creations per hour. */
  taskVelocityPerHour: number;
}

export interface FederationSnapshot {
  capturedAt: string;
  satellites: SatelliteHealth[];
  runway: RunwayEntry[];
  defense: SwarmDefenseState;
}

/** Row shape the Tower health surface serves before normalization. */
export interface RawTowerSnapshot {
  capturedAt?: string;
  satellites?: Record<string, { healthy?: boolean; latencyMs?: number; sha?: string; lastSyncedAt?: string; activeClaims?: number }>;
  workOrders?: Array<{ taskId?: string; title?: string; stage?: string; ciStatus?: string; diagnostics?: string; prNumber?: number; updatedAt?: string }>;
  defense?: Partial<SwarmDefenseState>;
}
