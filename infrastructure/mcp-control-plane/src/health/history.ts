import { promises as fs } from "node:fs";
import * as path from "node:path";
import type { HealthSnapshot } from "./snapshot.js";
import type { IncidentAlert } from "./incident.js";

/**
 * Persistent health/incident history for the MCP control plane.
 *
 * Gap closure: health snapshots and incidents used to live only in the
 * process-local `HealthCache` / incident transitions. This store appends every
 * notable transition and every sweep summary to a durable, append-only JSONL
 * file so the history survives process restarts and can be queried/audited.
 *
 * Persistence is best-effort by design: a failure to write must never break the
 * live health engine, so all filesystem errors are caught and logged only.
 */
export interface HealthHistoryEntry {
  seq: number;
  provider: string;
  status: HealthSnapshot["status"] | "__sweep__";
  timestamp: string;
  incident?: IncidentAlert;
  snapshot?: HealthSnapshot;
  overallStatus?: SweepOverallStatus;
}

export type SweepOverallStatus = "healthy" | "degraded" | "down" | "unknown";

const DEFAULT_MAX_ENTRIES = 5000;
const DEFAULT_FILE = () =>
  process.env.MCP_HEALTH_HISTORY_FILE ||
  path.resolve(process.cwd(), ".data", "health-history.jsonl");

export class HealthHistoryStore {
  private filePath: string;
  private maxEntries: number;
  private entries: HealthHistoryEntry[] = [];
  private seq = 0;

  constructor(filePath?: string, maxEntries = DEFAULT_MAX_ENTRIES) {
    this.filePath = filePath ?? DEFAULT_FILE();
    this.maxEntries = maxEntries;
  }

  /** Loads any existing history file so in-memory state survives restarts. */
  public async init(): Promise<void> {
    const dir = path.dirname(this.filePath);
    try {
      await fs.mkdir(dir, { recursive: true });
    } catch {
      // Directory creation is best-effort; load may still work if it exists.
    }
    try {
      const raw = await fs.readFile(this.filePath, "utf8");
      const lines = raw.split(/\r?\n/).filter((l) => l.trim().length > 0);
      for (const line of lines.slice(-this.maxEntries)) {
        try {
          const entry = JSON.parse(line) as HealthHistoryEntry;
          this.entries.push(entry);
          this.seq = Math.max(this.seq, entry.seq ?? 0);
        } catch {
          // Skip corrupted lines rather than failing the whole history.
        }
      }
      console.log(
        `[HealthHistory] loaded ${this.entries.length} entries from ${this.filePath}`
      );
    } catch {
      // First run: no history file yet.
    }
  }

  /** Appends a history entry durably (best-effort) and keeps a bounded ring. */
  public async append(
    entry: Omit<HealthHistoryEntry, "seq" | "timestamp">
  ): Promise<HealthHistoryEntry> {
    const full: HealthHistoryEntry = {
      ...entry,
      seq: ++this.seq,
      timestamp: new Date().toISOString(),
    };
    this.entries.push(full);
    if (this.entries.length > this.maxEntries) {
      this.entries = this.entries.slice(-this.maxEntries);
    }
    try {
      await fs.appendFile(this.filePath, JSON.stringify(full) + "\n", "utf8");
    } catch (err: any) {
      console.error(
        `[HealthHistory] persist failed (best-effort, engine unaffected): ${err?.message}`
      );
    }
    return full;
  }

  /** Returns history entries, optionally filtered by provider (limit is tail). */
  public query(provider?: string, limit = 100): HealthHistoryEntry[] {
    const filtered = provider
      ? this.entries.filter((e) =>
          e.provider === provider || e.incident?.provider === provider
        )
      : this.entries;
    return filtered.slice(-limit);
  }

  /** Returns raw persisted entries (bounded in-memory window). */
  public getAll(): HealthHistoryEntry[] {
    return this.entries.slice();
  }

  public getEntryCount(): number {
    return this.entries.length;
  }

  public getFilePath(): string {
    return this.filePath;
  }
}

export const globalHealthHistoryStore = new HealthHistoryStore();