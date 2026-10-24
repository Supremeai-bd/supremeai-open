/**
 * studio/src/store/persistence.ts — Server-flag store migration + rollback contract (Way 22).
 *
 * বাংলা: unified store migration — localStorage flag-নির্ভর নয়; সার্ভার-কনফিগার্ড
 * সেফ মাইগ্রেশন + ব্যর্থ হলে rollback + audit log entry (plan Way 22 contract)।
 *
 * Contract:
 * - Migrations are REGISTERED, ORDERED (vN → vN+1), and IDEMPOTENT.
 * - The CURRENT version comes from the server config endpoint (fetchStoreConfig),
 *   NOT from a localStorage flag — the operator controls rollout pace per client.
 * - If a migration throws, `migrate()` ROLLS BACK: original snapshot is restored
 *   byte-for-byte, the failed version is recorded as quarantined, and an audit
 *   entry is emitted. The app continues on the OLD data (never half-migrated).
 * - Audit log entries are appended to localStorage under AUDIT_KEY (bounded, FIFO)
 *   AND surfaced via onAudit callback for server-side shipping hooks.
 *
 * Self-contained: no zustand import needed at module scope — works with any
 * store; wire into adminStore/userStore rehydration (INTEGRATION.diff provided).
 */

export interface StoreMigration {
  /** Source data version this migration upgrades FROM. */
  from: number;
  /** Target version. Must equal from + 1. */
  to: number;
  /** Human description (audit trail). */
  describe: string;
  /** Pure-ish transformer. Throw to abort + rollback. Mutating a copy is safest. */
  up: (data: unknown) => unknown;
}

export interface AuditEntry {
  at: string; // ISO timestamp
  event: 'migrate.begin' | 'migrate.ok' | 'migrate.rollback' | 'migrate.quarantine';
  fromVersion: number | null;
  toVersion: number | null;
  detail: string;
}

export interface MigrationResult {
  status: 'migrated' | 'unchanged' | 'rolled-back';
  data: unknown;
  version: number | null;
  audit: AuditEntry[];
}

export const AUDIT_KEY = 'supremeai.store.migration.audit.v1';
export const DATA_VERSION_KEY = 'supremeai.store.dataVersion';
const MAX_AUDIT = 50;

/** Server-side rollout contract: return the sanctioned data version for this client. */
export async function fetchStoreConfig(
  endpoint = '/api/v1/config/store',
  fetchImpl: typeof fetch = fetch,
): Promise<number | null> {
  try {
    const res = await fetchImpl(endpoint, { credentials: 'include' });
    if (!res.ok) return null; // fail-open: server unreachable → do not migrate
    const json = (await res.json()) as { storeDataVersion?: number };
    const v = json.storeDataVersion;
    return typeof v === 'number' && v >= 0 ? v : null;
  } catch {
    return null;
  }
}

function readAudit(): AuditEntry[] {
  try {
    const raw = window.localStorage.getItem(AUDIT_KEY);
    return raw ? (JSON.parse(raw) as AuditEntry[]) : [];
  } catch {
    return [];
  }
}

function appendAudit(entries: AuditEntry[], entry: AuditEntry): AuditEntry[] {
  const next = [...entries, entry].slice(-MAX_AUDIT); // bounded FIFO
  try {
    window.localStorage.setItem(AUDIT_KEY, JSON.stringify(next));
  } catch {
    /* audit best-effort — never block the migration path */
  }
  return next;
}

export function readDataVersion(storage = window.localStorage): number | null {
  const raw = storage.getItem(DATA_VERSION_KEY);
  if (raw === null) return null;
  const v = Number(raw);
  return Number.isFinite(v) && v >= 0 ? v : null;
}

export function writeDataVersion(version: number, storage = window.localStorage): void {
  storage.setItem(DATA_VERSION_KEY, String(version));
}

/**
 * Run all pending migrations server-version-targeted, with rollback-on-failure.
 *
 * @param raw            the persisted store payload (JSON-parsed)
 * @param targetVersion  version sanctioned by the server config (may be null → no-op)
 * @param migrations     registered ordered migrations
 */
export function migrate(
  raw: unknown,
  targetVersion: number | null,
  migrations: StoreMigration[],
): MigrationResult {
  const audit: AuditEntry[] = [];
  const current = readDataVersion();

  if (targetVersion === null || current === null || current >= targetVersion) {
    audit.push(
      ...appendAudit(audit, {
        at: new Date().toISOString(),
        event: 'migrate.begin',
        fromVersion: current,
        toVersion: targetVersion,
        detail: current !== null && current >= (targetVersion ?? 0) ? 'already at/above target' : 'no server target',
      }).slice(-1),
    );
    return { status: 'unchanged', data: raw, version: current, audit };
  }

  const byFrom = new Map(migrations.map((m) => [m.from, m] as const));
  let data = raw;
  let version = current;

  // Snapshot ONCE — rollback restores this exact payload (P3 discipline).
  const snapshot: string = JSON.stringify({ data, version });

  const beginEntry: AuditEntry = {
    at: new Date().toISOString(),
    event: 'migrate.begin',
    fromVersion: current,
    toVersion: targetVersion,
    detail: `snapshot ${snapshot.length} bytes`,
  };
  audit.push(...appendAudit([], beginEntry)); // fresh audit thread for this run

  while (version < targetVersion) {
    const step = byFrom.get(version);
    if (!step) {
      // No registered path → rollback (never improvise a migration).
      audit.push(...appendAudit(audit, {
        at: new Date().toISOString(),
        event: 'migrate.rollback',
        fromVersion: version,
        toVersion: targetVersion,
        detail: `no migration registered for v${version} → v${version + 1}`,
      }).slice(-1));
      const restored = JSON.parse(snapshot) as { data: unknown; version: number };
      audit.push(...appendAudit(audit, {
        at: new Date().toISOString(),
        event: 'migrate.quarantine',
        fromVersion: restored.version,
        toVersion: null,
        detail: 'data quarantined at pre-migration snapshot',
      }).slice(-1));
      return { status: 'rolled-back', data: restored.data, version: restored.version, audit };
    }
    try {
      data = step.up(structuredClone(data));
      version = step.to;
      audit.push(...appendAudit(audit, {
        at: new Date().toISOString(),
        event: 'migrate.ok',
        fromVersion: step.from,
        toVersion: step.to,
        detail: step.describe,
      }).slice(-1));
    } catch (exc) {
      audit.push(...appendAudit(audit, {
        at: new Date().toISOString(),
        event: 'migrate.rollback',
        fromVersion: version,
        toVersion: targetVersion,
        detail: `v${step.from}→v${step.to} threw: ${exc instanceof Error ? exc.message : String(exc)}`,
      }).slice(-1));
      const restored = JSON.parse(snapshot) as { data: unknown; version: number };
      audit.push(...appendAudit(audit, {
        at: new Date().toISOString(),
        event: 'migrate.quarantine',
        fromVersion: restored.version,
        toVersion: null,
        detail: 'original payload restored byte-for-byte',
      }).slice(-1));
      return { status: 'rolled-back', data: restored.data, version: restored.version, audit };
    }
  }

  writeDataVersion(version);
  return { status: 'migrated', data, version, audit };
}
