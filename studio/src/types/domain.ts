export type RunStatus =
  | "draft"
  | "queued"
  | "planning"
  | "awaiting_approval"
  | "running"
  | "verifying"
  | "succeeded"
  | "failed"
  | "canceled";

export type SupportingStatus = "retrying" | "cancel_requested" | "needs_input" | "timed_out";

export interface Conversation {
  id: string;
  workspaceId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  retentionStatus: string;
}

export interface Message {
  id: string;
  conversationId: string;
  author: string;
  contentParts: string[];
  attachmentRefs: string[];
  timestamp: string;
  status: string;
}

export interface Run {
  id: string;
  workspaceId: string;
  conversationId: string;
  goal: string;
  status: RunStatus;
  version: number;
  policySummary: string;
  resultRefs: string[];
}

export interface RunEvent {
  id: string;
  runId: string;
  eventType: string;
  serverTimestamp: string;
  safeSummary: string;
  detailRef: string;
}

export interface Agent {
  id: string;
  displayName: string;
  purpose: string;
  capabilities: string[];
  state: string;
  heartbeatAt: string;
  activeRunRef: string;
}

export interface Approval {
  id: string;
  runId: string;
  proposedAction: string;
  scope: string;
  riskLevel: string;
  isReversible: boolean;
  state: string;
  expiresAt: string;
  version: number;
}

export interface Artifact {
  id: string;
  type: string;
  metadata: Record<string, unknown>;
  version: number;
  authorizedEndpoint: string;
}

export const RUN_TRANSITIONS: Record<RunStatus, RunStatus[]> = {
  draft: ["queued", "canceled"],
  queued: ["planning", "canceled"],
  planning: ["awaiting_approval", "running", "failed", "canceled"],
  awaiting_approval: ["running", "canceled", "failed"],
  running: ["verifying", "failed", "canceled"],
  verifying: ["succeeded", "failed"],
  succeeded: [],
  failed: ["queued"],
  canceled: [],
};
