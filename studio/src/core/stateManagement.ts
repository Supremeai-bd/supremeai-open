// apps/studio-client/src/core/stateManagement.ts
// বাংলা মন্তব্য: ক্লায়েন্ট-সাইড সেলফ-হিলিং স্টেট ম্যানেজার — অনলাইন/অফলাইন নেটওয়ার্ক কানেকশন রিকভারি ও এরর ট্র্যাকিং হ্যান্ডেল করে।

export interface AppErrorEvent {
  id: string;
  message: string;
  type: string;
  timestamp: string;
}

class SelfHealingStateManager {
  private errors: AppErrorEvent[] = [];
  private isOnline: boolean = typeof navigator !== 'undefined' ? navigator.onLine : true;
  private listeners: Array<() => void> = [];
  // বাংলা মন্তব্য: সেলফ-হিলিং টগল — backend/AppDefaults থেকে সেট হয়। false হলে recovery/retry নিষ্ক্রিয়।
  private enabled: boolean = true;

  public setEnabled(value: boolean): void {
    this.enabled = Boolean(value);
    this.notify();
  }

  public isEnabled(): boolean {
    return this.enabled;
  }

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', this.handleOnline);
      window.addEventListener('offline', this.handleOffline);
    }
  }

  private handleOnline = () => {
    console.warn('[Self-Healing] Device back online. Restoring network connection state.');
    this.isOnline = true;
    this.notify();
  };

  private handleOffline = () => {
    console.warn('[Self-Healing] Device offline. Network state paused.');
    this.isOnline = false;
    this.notify();
  };

  public reportError(message: string, type: string = 'FRONTEND_ERROR') {
    const errorEvent: AppErrorEvent = {
      id: Math.random().toString(36).substring(2, 9),
      message,
      type,
      timestamp: new Date().toISOString(),
    };
    this.errors.unshift(errorEvent);
    if (this.errors.length > 50) {
      this.errors.pop();
    }
    console.warn(`[Self-Healing] Frontend error recorded: ${type} - ${message}`);
    this.notify();
  }

  public getErrors(): AppErrorEvent[] {
    return [...this.errors];
  }

  public getIsOnline(): boolean {
    return this.isOnline;
  }

  public subscribe(listener: () => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  private notify() {
    this.listeners.forEach((listener) => listener());
  }
}

export const selfHealingState = new SelfHealingStateManager();
export default selfHealingState;
