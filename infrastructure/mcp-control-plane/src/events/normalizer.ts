export interface NormalizedEvent {
  source: string; // e.g., 'github', 'cloudflare', 'system'
  type: string;   // e.g., 'push', 'ping_failed', 'cron'
  severity: "INFO" | "WARNING" | "CRITICAL";
  message: string;
  payload: any;
  timestamp: string;
  /** GitHub `X-GitHub-Delivery` id (#69) — used for webhook idempotency. */
  deliveryId?: string;
}

export class EventNormalizer {
  /**
   * Normalizes a GitHub webhook payload.
   * `deliveryId` is the `X-GitHub-Delivery` header value (#69 idempotency).
   */
  public normalizeGitHubEvent(eventName: string, payload: any, deliveryId?: string): NormalizedEvent {
    let severity: "INFO" | "WARNING" | "CRITICAL" = "INFO";
    let message = `GitHub Event: ${eventName}`;

    if (eventName === "issues" && payload.action === "opened") {
       message = `New Issue Created: ${payload.issue?.title || "Unknown"}`;
       severity = "WARNING";
    }

    if (eventName === "push") {
       message = `Push to branch ${payload.ref || "unknown"}`;
    }

    return {
      source: "github",
      type: eventName,
      severity,
      message,
      payload,
      timestamp: new Date().toISOString(),
      deliveryId,
    };
  }

  /**
   * Normalizes a Cloudflare ping/uptime payload.
   */
  public normalizeCloudflareEvent(payload: any): NormalizedEvent {
    const isUp = payload.status === "up";
    return {
      source: "cloudflare",
      type: isUp ? "ping_ok" : "ping_failed",
      severity: isUp ? "INFO" : "CRITICAL",
      message: isUp 
        ? `Cloudflare Ping OK: ${payload.url}` 
        : `Cloudflare Ping FAILED: ${payload.url}`,
      payload,
      timestamp: new Date().toISOString()
    };
  }
}

export const globalEventNormalizer = new EventNormalizer();
