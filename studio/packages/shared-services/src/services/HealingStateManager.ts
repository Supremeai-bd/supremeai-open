/**
 * HealingStateManager — Self-Healing প্রক্রিয়ার State Machine
 * (platform-agnostic — TinyEventEmitter ব্যবহার করে, vscode.EventEmitter-এর বদলে)
 */

import { TinyEventEmitter } from '../platform';

export const HealingState = {
  IDLE: 'IDLE',
  ANALYZING_ERROR: 'ANALYZING_ERROR',
  GENERATING_PATCH: 'GENERATING_PATCH',
  APPLYING_DIFF: 'APPLYING_DIFF',
  SUCCESS: 'SUCCESS',
  FAILED: 'FAILED',
} as const;

export type HealingState = typeof HealingState[keyof typeof HealingState];

export interface HealingStateEvent {
  state: HealingState;
  message?: string;
}

export class HealingStateManager {
  private static instance: HealingStateManager | null = null;
  private currentState: HealingState = HealingState.IDLE;
  private readonly emitter = new TinyEventEmitter<HealingStateEvent>();

  private constructor() {}

  public static getInstance(): HealingStateManager {
    if (!HealingStateManager.instance) {
      HealingStateManager.instance = new HealingStateManager();
    }
    return HealingStateManager.instance;
  }

  public onDidChangeState(listener: (evt: HealingStateEvent) => void) {
    return this.emitter.on(listener);
  }

  public setState(state: HealingState, message?: string): void {
    this.currentState = state;
    this.emitter.emit({ state, message });
  }

  public getState(): HealingState {
    return this.currentState;
  }
}