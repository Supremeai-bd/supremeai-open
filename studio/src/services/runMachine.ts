import { RUN_TRANSITIONS, type RunStatus, type Run } from "../types/domain";

export interface TransitionResult {
  ok: boolean;
  reason?: string;
}

export function canTransition(from: RunStatus, to: RunStatus): boolean {
  return (RUN_TRANSITIONS[from] ?? []).includes(to);
}

export function transition(run: Run, to: RunStatus): TransitionResult {
  if (run.status === to) {
    return { ok: true };
  }
  if (!canTransition(run.status, to)) {
    return { ok: false, reason: `invalid transition ${run.status} -> ${to}` };
  }
  return { ok: true };
}

export function applyTransition(run: Run, to: RunStatus): Run {
  if (!canTransition(run.status, to) && run.status !== to) {
    throw new Error(`invalid transition ${run.status} -> ${to}`);
  }
  return { ...run, status: to, version: run.version + 1 };
}

export function isTerminal(status: RunStatus): boolean {
  return status === "succeeded" || status === "failed" || status === "canceled";
}

export function isRetryable(run: Run): boolean {
  return run.status === "failed";
}
