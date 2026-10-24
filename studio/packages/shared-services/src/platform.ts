/**
 * SupremeAI Platform Abstraction Layer
 *
 * VS Code extension এবং Electron desktop app দুটি আলাদা রানটাইম এনভায়রনমেন্ট।
 * এই ইন্টারফেসটি সেই প্ল্যাটফর্ম-নির্দিষ্ট API গুলোকে অ্যাবস্ট্রাক্ট করে,
 * যাতে কোর সার্ভিস লজিক দুটোতেই একই থাকে (DRY)।
 *
 * প্রতিটি প্ল্যাটফর্ম (VS Code / Electron / Web) একটি `SupremePlatformAdapter`
 * ইমপ্লিমেন্ট করে injected হয়। Core services তখন শুধুমাত্র এই ইন্টারফেসের
 * মাধ্যমে প্ল্যাটফর্মের সাথে কথা বলে।
 */

export interface PlatformLogger {
  info(...args: unknown[]): void;
  warn(...args: unknown[]): void;
  error(...args: unknown[]): void;
}

export interface PlatformNotification {
  showInformationMessage(message: string): Promise<void>;
  showWarningMessage(message: string): Promise<void>;
  showErrorMessage(message: string): Promise<void>;
}

export interface PlatformPrompt {
  /**
   * একটি ইনপুট বক্স দেখায়। `validateInput` কলব্যাক রিটার্ন করে string
   * means invalid (error message) অথবা null means valid।
   */
  showInputBox(options: {
    title?: string;
    prompt?: string;
    placeHolder?: string;
    password?: boolean;
    validateInput?: (value: string) => string | null | undefined;
  }): Promise<string | undefined>;

  /** Yes/No কনফার্মেশন ডায়ালগ দেখায়। */
  showConfirm(message: string): Promise<boolean>;

  /** অগ্রগতি নোটিফিকেশন সহ একটি async task রান করে। */
  withProgress(title: string, task: () => Promise<void>): Promise<void>;
}

export interface PlatformSecretStorage {
  get(key: string): Promise<string | undefined>;
  store(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
}

export interface PlatformTextDocument {
  /** ফাইলের অ্যাবসলুট পাথ (fsPath)। */
  filePath: string;
  /** ডকুমেন্টের সম্পূর্ণ টেক্সট। */
  getText(): string;
  /** লাইন সংখ্যা। */
  lineCount: number;
  /** ভাষা (monarch id অথবা vscode languageId)। */
  languageId: string;
  /** একটি নির্দিষ্ট লাইনের টেক্সট। */
  lineAt(line: number): { text: string };
}

export interface PlatformEditor {
  /** অ্যাক্টিভ এডিটর থেকে নির্বাচিত টেক্সট (নেইসপ্যাড হলে খালি string)। */
  getSelectedText(document: PlatformTextDocument | null): string;
  /** ডিফল্ট যুক্তভাবে current file এর ফুল টেক্সট। */
  getActiveDocument(): PlatformTextDocument | null;
}

export interface PlatformWorkspace {
  /** ওয়ার্কস্পেসের ফোল্ডারের পাথসমূহ। */
  workspaceFolders: string[] | null;

  /** glob pattern দিয়ে ফাইল খোঁজা। */
  findFiles(
    include: string,
    exclude?: string
  ): Promise<string[]>;

  /** সিকিউর স্টোরেজ (টোকেন ইত্যাদির জন্য)। */
  secrets: PlatformSecretStorage;
}

/**
 * কাস্টম ইনপুট ইভেন্ট এমিটার — VS Code-এর native EventEmitter-এর বদলে
 * একটি হালকা, প্ল্যাটফর্ম-অ্যাগনস্টিক ভার্সন।
 */
export class TinyEventEmitter<T> {
  private listeners: Array<(data: T) => void> = [];

  public on(listener: (data: T) => void): { dispose(): void } {
    this.listeners.push(listener);
    let disposed = false;
    return {
      dispose: () => {
        if (disposed) return;
        disposed = true;
        const idx = this.listeners.indexOf(listener);
        if (idx >= 0) this.listeners.splice(idx, 1);
      },
    };
  }

  /** একবার শোনা হয় — ভবিষ্যতের সাবস্ক্রিপশন অপশন। */
  public once(listener: (data: T) => void): void {
    const sub = this.on((data) => {
      sub.dispose();
      listener(data);
    });
  }

  /** ইভেন্ট ডিসপ্যাচ করে (প্ল্যাটফর্ম-অ্যাগনস্টিক emit)। */
  public emit(data: T): void {
    this.fire(data);
  }

  protected fire(data: T): void {
    // কপি করি — যাতে listener রদ করা (dispose) iteration এ break না করে
    [...this.listeners].forEach((l) => l(data));
  }

  public removeListener(listener: (data: T) => void): void {
    const idx = this.listeners.indexOf(listener);
    if (idx >= 0) this.listeners.splice(idx, 1);
  }
}

// টাইপ স্কোরে আনমুক্ত রেখে অ-প্ল্যাটফর্ম-নির্দিষ্ট কিছু সিম্পল হেল্পার
export function noop(): void {
  /* no-op */
}