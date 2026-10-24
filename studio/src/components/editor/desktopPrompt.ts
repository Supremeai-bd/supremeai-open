/**
 * Desktop JIT OTP Prompt — shared singleton।
 * Non-component file হিসেবে আলাদা রাখা হয়েছে যাতে react-refresh
 * শুধু component export-এর নিয়ম ভঙ্গ না হয়।
 */
import type { PlatformPrompt } from "@supremeai/shared-services";
export interface PendingInput {
  options: {
    title?: string;
    prompt?: string;
    placeHolder?: string;
    password?: boolean;
    validateInput?: (value: string) => string | null | undefined;
  };
  resolve: (value: string | undefined) => void;
}

export interface PendingConfirm {
  message: string;
  resolve: (value: boolean) => void;
}

export type PendingState =
  | { kind: "input"; data: PendingInput }
  | { kind: "confirm"; data: PendingConfirm }
  | null;

class DialogQueue implements PlatformPrompt {
  private listener: ((pending: PendingState) => void) | null = null;
  private pendingInput: PendingInput | null = null;
  private pendingConfirm: PendingConfirm | null = null;

  setListener(fn: (pending: PendingState) => void): void {
    this.listener = fn;
    this.notify();
  }

  private notify(): void {
    if (!this.listener) return;
    if (this.pendingInput) {
      this.listener({ kind: "input", data: this.pendingInput });
    } else if (this.pendingConfirm) {
      this.listener({ kind: "confirm", data: this.pendingConfirm });
    } else {
      this.listener(null);
    }
  }

  async showInputBox(options: NonNullable<typeof this.pendingInput>["options"]): Promise<string | undefined> {
    return new Promise<string | undefined>((resolve) => {
      this.pendingInput = { options, resolve };
      this.notify();
    });
  }

  async showConfirm(message: string): Promise<boolean> {
    return new Promise<boolean>((resolve) => {
      this.pendingConfirm = { message, resolve };
      this.notify();
    });
  }

  async withProgress(_title: string, task: () => Promise<void>): Promise<void> {
    await task();
  }

  submit(value: string): void {
    const input = this.pendingInput;
    this.pendingInput = null;
    this.notify();
    input?.resolve(value);
  }

  cancel(): void {
    const input = this.pendingInput;
    const confirm = this.pendingConfirm;
    this.pendingInput = null;
    this.pendingConfirm = null;
    this.notify();
    input?.resolve(undefined);
    confirm?.resolve(false);
  }

  confirmWith(yes: boolean): void {
    const confirm = this.pendingConfirm;
    this.pendingConfirm = null;
    this.notify();
    confirm?.resolve(yes);
  }
}

/** মডিউল-লেভেল singleton — পুরো app এই একটাই prompt ব্যবহার করে। */
export const desktopPrompt: PlatformPrompt & {
  setListener(fn: (pending: PendingState) => void): void;
  submit(value: string): void;
  cancel(): void;
  confirmWith(yes: boolean): void;
} = new DialogQueue();
