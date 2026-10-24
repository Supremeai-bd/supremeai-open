// বাংলা মন্তব্য: Connection Contract — "Connection = HOW we reach something"।
// ব্যবহারকারী কখনো এই টাইপ সরাসরি দেখে না; এটি backend `/api/v1/connections/*`
// response-এর canonical vocabulary। কোনো secret (API key/token) এখানে কখনোই থাকবে না।

export type ConnectionProtocol = 'mcp' | 'oauth' | 'rest' | 'custom' | 'internal';

export type ConnectionHealth = 'healthy' | 'degraded' | 'unreachable' | 'pending';

export interface ConnectionContract {
  connectionId: string;
  /** Human-readable name — UI-তে দেখানোর জন্য (যেমন "My GitHub") */
  name: string;
  protocol: ConnectionProtocol;
  health: ConnectionHealth;
  /** কন tenant/workspace-এ স্কোপড — backend-authoritative */
  tenantId: string | null;
  /** এই connection থেকে আবিষ্কৃত capability-গুলোর id (capability-focused UX) */
  capabilityIds: string[];
  createdAt: string;
  lastUsedAt: string | null;
}

/** POST /api/v1/connections/detect response */
export interface ConnectionDetection {
  detected: boolean;
  protocol: ConnectionProtocol;
  /** ব্যবহারকারী-বান্ধব নাম (যেমন "GitHub") — কখনো protocol টেকনিক্যাল নাম নয় */
  providerLabel: string;
  /** Detection যেসব নিয়মে মিলেছে (audit/debug-এর জন্য) */
  reasons: string[];
}

/** POST /api/v1/connections/register request — কোনো secret নয়, শুধু stable identifier */
export interface ConnectionRegisterRequest {
  name: string;
  url: string;
  /** Advanced/manual setup-এ user-supplied label (optional) */
  label?: string;
}
