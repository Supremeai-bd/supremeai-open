import { ActionContext } from "../risk.engine.js";
import { timestampDetails } from "../../lib/timestamps.js";

export type ApprovalState = "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";

export interface ApprovalRequest {
  id: string;
  context: ActionContext;
  state: ApprovalState;
  createdAtMs: number;
  expiresAtMs: number;
  metadata?: any;
  resolvedAtMs?: number;
}

export class ApprovalManager {
  private requests = new Map<string, ApprovalRequest>();
  public readonly storageMode = "process-memory-development-fallback" as const;
  private defaultTtlMs = 30 * 60 * 1000; // 30 minutes

  /**
   * Creates a new pending approval request.
   */
  public createRequest(context: ActionContext, metadata?: any): ApprovalRequest {
    const id = `REQ-${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 6)}`;
    const now = Date.now();
    
    const request: ApprovalRequest = {
      id,
      context,
      state: "PENDING",
      createdAtMs: now,
      expiresAtMs: now + this.defaultTtlMs,
      metadata
    };

    this.requests.set(id, request);
    return request;
  }

  /**
   * Retrieves a request by ID, handling expiration automatically.
   */
  public getRequest(id: string): ApprovalRequest | undefined {
    const request = this.requests.get(id);
    if (!request) return undefined;

    // Check expiration
    if (request.state === "PENDING" && Date.now() > request.expiresAtMs) {
      request.state = "EXPIRED";
      this.requests.set(id, request);
    }

    return request;
  }

  /**
   * Resolves a request (Approve or Reject).
   */
  public resolveRequest(id: string, decision: "APPROVED" | "REJECTED"): boolean {
    const request = this.getRequest(id);
    if (!request) throw new Error(`Approval Request ${id} not found.`);
    
    if (request.state !== "PENDING") {
      throw new Error(`Cannot resolve request ${id}. Current state is ${request.state}.`);
    }

    request.state = decision;
    request.resolvedAtMs = Date.now();
    this.requests.set(id, request);
    return true;
  }

  public getPendingRequests(): ApprovalRequest[] {
    const pending: ApprovalRequest[] = [];
    for (const req of this.requests.values()) {
      // Accessing via getRequest ensures expiration is evaluated
      const current = this.getRequest(req.id);
      if (current && current.state === "PENDING") {
        pending.push(current);
      }
    }
    return pending;
  }

  /**
   * Gets all requests (pending, approved, rejected, expired).
   */
  public getAllRequests(): ApprovalRequest[] {
    const all: ApprovalRequest[] = [];
    for (const req of this.requests.values()) {
      const current = this.getRequest(req.id);
      if (current) {
        all.push(current);
      }
    }
    return all.sort((a, b) => b.createdAtMs - a.createdAtMs);
  }
}

export const globalApprovalManager = new ApprovalManager();
