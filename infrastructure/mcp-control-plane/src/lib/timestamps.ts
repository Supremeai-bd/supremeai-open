export interface TimestampEnvelope {
  timestamp: string;
  timestampMs: number;
  timezone: "UTC";
}

export function nowTimestamp(): TimestampEnvelope {
  const timestampMs = Date.now();
  return { timestamp: new Date(timestampMs).toISOString(), timestampMs, timezone: "UTC" };
}

export function timestampDetails(createdAtMs: number, expiresAtMs?: number, updatedAtMs = createdAtMs) {
  const now = Date.now();
  return {
    createdAt: new Date(createdAtMs).toISOString(),
    createdAtMs,
    updatedAt: new Date(updatedAtMs).toISOString(),
    updatedAtMs,
    expiresAt: expiresAtMs === undefined ? undefined : new Date(expiresAtMs).toISOString(),
    expiresAtMs,
    ageMs: Math.max(0, now - createdAtMs),
    remainingMs: expiresAtMs === undefined ? undefined : Math.max(0, expiresAtMs - now),
    timezone: "UTC" as const,
  };
}

export function withTimestamp<T extends object>(payload: T): T & TimestampEnvelope {
  return { ...payload, ...nowTimestamp() };
}
