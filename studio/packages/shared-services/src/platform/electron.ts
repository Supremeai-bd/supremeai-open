/**
 * Electron Desktop Platform Adapter
 *
 * `frontend/` — Electron desktop app-এ preload.cjs থেকে `window.supremeDesktopAPI`
 * এক্সপোজ করা আছে। এই adapter সেটাকে platform.ts ইন্টারফেসে ম্যাপ করে।
 *
 * ডেস্কটপে আমরা সরাসরি fetch/axios ব্যাবহার না করে, Electron main process-এর
 * `api:call` IPC-র মাধ্যমে API কল করি — ফলে sandboxed renderer নিরাপদ থাকে।
 */

import type {
  PlatformLogger,
  PlatformNotification,
  PlatformPrompt,
  PlatformSecretStorage,
  PlatformWorkspace,
  PlatformTextDocument,
} from '../platform';

/** preload.cjs-এ এক্সপোজ করা global API-র টাইপ। */
export interface SupremeDesktopAPI {
  apiCall(options: {
    endpoint: string;
    method?: string;
    body?: unknown;
    headers?: Record<string, string>;
  }): Promise<{ status: number; ok: boolean; data: unknown }>;
  getAppInfo(): Promise<{ name: string; version: string; platform: string; isDev: boolean }>;
  onMenuAction(cb: (action: string) => void): () => void;
}

declare global {
  interface Window {
    supremeDesktopAPI?: SupremeDesktopAPI;
  }
}

export class ElectronLogger implements PlatformLogger {
  info = (...args: unknown[]) => console.log('[SupremeAI Desktop]', ...args);
  warn = (...args: unknown[]) => console.warn('[SupremeAI Desktop]', ...args);
  error = (...args: unknown[]) => console.error('[SupremeAI Desktop]', ...args);
}

export class ElectronNotification implements PlatformNotification {
  async showInformationMessage(message: string): Promise<void> {
    if (typeof Notification !== 'undefined') {
      try {
        const perm = await Notification.requestPermission();
        if (perm === 'granted') {
          new Notification('SupremeAI', { body: message });
          return;
        }
      } catch {
        /* fall through */
      }
    }
    console.log('[SupremeAI Desktop] ℹ️', message);
  }

  async showWarningMessage(message: string): Promise<void> {
    console.warn('[SupremeAI Desktop] ⚠️', message);
  }

  async showErrorMessage(message: string): Promise<void> {
    console.error('[SupremeAI Desktop] ❌', message);
  }
}
export class ElectronPrompt implements PlatformPrompt {
  private customInput?: PlatformPrompt | null;

  constructor(customInput?: PlatformPrompt | null) {
    this.customInput = customInput ?? null;
  }

  /** React-based custom input (যেমন JitOtpModal) inject করা যায়। */
  public setCustomPrompt(prompt: PlatformPrompt): void {
    this.customInput = prompt;
  }

  async showInputBox(options: {
    title?: string;
    prompt?: string;
    placeHolder?: string;
    password?: boolean;
    validateInput?: (value: string) => string | null | undefined;
  }): Promise<string | undefined> {
    if (this.customInput) {
      return this.customInput.showInputBox(options);
    }
    const raw = window.prompt(options.prompt || options.title || 'Enter value');
    if (raw === null) return undefined;
    if (options.validateInput) {
      const error = options.validateInput(raw);
      if (error) {
        console.warn('[SupremeAI Desktop] Validation failed:', error);
        return undefined;
      }
    }
    return raw;
  }

  async showConfirm(message: string): Promise<boolean> {
    if (this.customInput) {
      return this.customInput.showConfirm(message);
    }
    return window.confirm(message);
  }

  async withProgress(title: string, task: () => Promise<void>): Promise<void> {
    console.log(`[SupremeAI Desktop] ⏳ ${title}...`);
    await task();
    console.log(`[SupremeAI Desktop] ✅ ${title} done`);
  }
}

/**
 * Desktop-এ localStorage ভিত্তিক secret storage।
 * (সিকিউরিটি নোট: শুধুমাত্র API key অথবা session token — পাসওয়ার্ড নয়।)
 */
export class ElectronSecretStorage implements PlatformSecretStorage {
  async get(key: string): Promise<string | undefined> {
    try {
      return localStorage.getItem(`supremeai.${key}`) ?? undefined;
    } catch {
      return undefined;
    }
  }

  async store(key: string, value: string): Promise<void> {
    try {
      localStorage.setItem(`supremeai.${key}`, value);
    } catch (err) {
      console.error('[SupremeAI Desktop] Secret store failed:', err);
    }
  }

  async delete(key: string): Promise<void> {
    try {
      localStorage.removeItem(`supremeai.${key}`);
    } catch {
      /* ignore */
    }
  }
}

/**
 * Desktop-এ web.container-এ কাজ হয়, তাই workspaceFolders browser-এ
 * unavailable — fileProvider inject করে frontend store থেকে ফিড করা যায়।
 */
export class ElectronWorkspace implements PlatformWorkspace {
  public readonly secrets: PlatformSecretStorage;
  private fileProvider?: {
    workspaceFolders: string[] | null;
    findFiles: (include: string, exclude?: string) => Promise<string[]>;
  };

  constructor(
    secrets: PlatformSecretStorage,
    fileProvider?: ElectronWorkspace['fileProvider']
  ) {
    this.secrets = secrets;
    this.fileProvider = fileProvider;
  }

  get workspaceFolders(): string[] | null {
    return this.fileProvider?.workspaceFolders ?? null;
  }

  async findFiles(include: string, exclude?: string): Promise<string[]> {
    return this.fileProvider ? this.fileProvider.findFiles(include, exclude) : [];
  }
}

/** একটি জেনেরিক ডকুমেন্ট → PlatformTextDocument adapter (frontend store থেকে)। */
export function toPlatformTextDocument(input: {
  filePath: string;
  getText: () => string;
  lineCount: number;
  languageId: string;
  lineAt: (l: number) => { text: string };
}): PlatformTextDocument {
  return {
    filePath: input.filePath,
    getText: input.getText,
    lineCount: input.lineCount,
    languageId: input.languageId,
    lineAt: input.lineAt,
  };
}

/** Electron platform singleton build helper */
export function createElectronPlatform(options?: {
  customPrompt?: PlatformPrompt | null;
  fileProvider?: ElectronWorkspace['fileProvider'];
}): {
  notifications: ElectronNotification;
  prompt: ElectronPrompt;
  secrets: ElectronSecretStorage;
  workspace: ElectronWorkspace;
} {
  const secrets = new ElectronSecretStorage();
  const workspace = new ElectronWorkspace(secrets, options?.fileProvider);
  return {
    notifications: new ElectronNotification(),
    prompt: new ElectronPrompt(options?.customPrompt ?? null),
    secrets,
    workspace,
  };
}