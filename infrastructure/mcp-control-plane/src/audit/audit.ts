export interface AuditLogEntry {
  correlationId: string;
  provider: string;
  action: string;
  status: "SUCCESS" | "FAILURE";
  timestamp: string;
  details: any;
  error?: string;
}

export class AuditLogger {
  private logs: AuditLogEntry[] = [];

  /**
   * Logs an action execution outcome.
   * Currently stores in memory and flushes to console.
   */
  public log(entry: Omit<AuditLogEntry, "timestamp">): void {
    const logEntry: AuditLogEntry = {
      ...entry,
      timestamp: new Date().toISOString(),
    };
    
    this.logs.push(logEntry);
    
    const statusColor = entry.status === "SUCCESS" ? "✅" : "❌";
    console.log(`[AUDIT] ${statusColor} [${logEntry.correlationId}] ${entry.provider}.${entry.action} -> ${entry.status}`);
    if (entry.error) {
      console.error(`[AUDIT] Error Details: ${entry.error}`);
    }
  }

  /**
   * Retrieves the most recent logs (in-memory).
   */
  public getLogs(limit: number = 50): AuditLogEntry[] {
    return this.logs.slice(-limit);
  }
}

export const globalAuditLogger = new AuditLogger();
