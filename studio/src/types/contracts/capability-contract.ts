// বাংলা মন্তব্য: Capability Contract — "Capability = WHAT the user can DO"।
// Customer UX-এ সবসময় capability দেখানো হয়, connection/protocol নয়।

export type CapabilityStatus = 'ready' | 'idle' | 'unavailable' | 'requestable';

export interface CapabilityContract {
  capabilityId: string;
  name: string;
  /** এক লাইনে ব্যবহারকারী-বান্ধব বর্ণনা */
  purpose: string;
  status: CapabilityStatus;
  category: string;
  /** 'unavailable'/'requestable' হলে human-readable কারণ (Explain-Why UX) */
  unavailableReason: string | null;
  /** অনুমতি চাওয়ার জন্য প্রয়োজনীয় permission label (admin দেখবে) */
  requiredPermission: string | null;
}

/** GET /api/v1/connections/my-workspace response — backend-authoritative */
export interface MyWorkspaceContract {
  userId: string;
  /** শুধু backend-এ অনুমোদিত context/workspace-গুলো; user এগুলোর বাইরে যেতে পারবে না */
  authorizedContexts: Array<{ id: string; label: string; active: boolean }>;
  /** এই user-এর জন্য বর্তমান execution mode */
  executionMode: import('./execution-mode').ExecutionMode;
  /** শুধু যা user ব্যবহার/enable করেছে — বাকি সব backend-ই পাঠায় না */
  capabilities: CapabilityContract[];
  connections: ConnectionSummary[];
  recentActivity: Array<{ id: string; summary: string; occurredAt: string }>;
}

interface ConnectionSummary {
  connectionId: string;
  name: string;
  health: import('./connection-contract').ConnectionHealth;
}
