/**
 * VS Code Platform Adapter — `vscode` module-কে platform.ts ইন্টারফেসে ম্যাপ করে।
 * VS Code extension যখন shared-services ব্যবহার করে, এই adapter inject করা হয়।
 */

import * as vscode from 'vscode';
import type {
  PlatformLogger,
  PlatformNotification,
  PlatformPrompt,
  PlatformSecretStorage,
  PlatformWorkspace,
  PlatformTextDocument,
} from '../platform';

export class VscodeLogger implements PlatformLogger {
  info = (...args: unknown[]) => console.log('[SupremeAI]', ...args);
  warn = (...args: unknown[]) => console.warn('[SupremeAI]', ...args);
  error = (...args: unknown[]) => console.error('[SupremeAI]', ...args);
}

export class VscodeNotification implements PlatformNotification {
  async showInformationMessage(message: string): Promise<void> {
    await vscode.window.showInformationMessage(message);
  }
  async showWarningMessage(message: string): Promise<void> {
    await vscode.window.showWarningMessage(message);
  }
  async showErrorMessage(message: string): Promise<void> {
    await vscode.window.showErrorMessage(message);
  }
}

export class VscodePrompt implements PlatformPrompt {
  async showInputBox(options: {
    title?: string;
    prompt?: string;
    placeHolder?: string;
    password?: boolean;
    validateInput?: (value: string) => string | null | undefined;
  }): Promise<string | undefined> {
    return vscode.window.showInputBox({
      title: options.title,
      prompt: options.prompt,
      placeHolder: options.placeHolder,
      password: options.password,
      ignoreFocusOut: true as const,
      validateInput:
        options.validateInput &&
        ((value: string) => options.validateInput!(value) ?? undefined),
    });
  }

  async showConfirm(message: string): Promise<boolean> {
    const answer = await vscode.window.showWarningMessage(message, { modal: true }, 'Yes');
    return answer === 'Yes';
  }

  async withProgress(title: string, task: () => Promise<void>): Promise<void> {
    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title, cancellable: false },
      async () => {
        await task();
      }
    );
  }
}

export class VscodeSecretStorage implements PlatformSecretStorage {
  private secrets: vscode.SecretStorage;
  constructor(secrets: vscode.SecretStorage) {
    this.secrets = secrets;
  }
  async get(key: string): Promise<string | undefined> {
    return this.secrets.get(key);
  }
  async store(key: string, value: string): Promise<void> {
    await this.secrets.store(key, value);
  }
  async delete(key: string): Promise<void> {
    await this.secrets.delete(key);
  }
}

export class VscodeWorkspace implements PlatformWorkspace {
  constructor(public readonly secrets: PlatformSecretStorage) {}

  get workspaceFolders(): string[] | null {
    return vscode.workspace.workspaceFolders?.map((f) => f.uri.fsPath) ?? null;
  }

  async findFiles(include: string, exclude?: string): Promise<string[]> {
    const uris = await vscode.workspace.findFiles(include, exclude);
    return uris.map((u) => u.fsPath);
  }
}

/** vscode.TextDocument → PlatformTextDocument adapter */
export function toPlatformTextDocument(doc: vscode.TextDocument): PlatformTextDocument {
  return {
    filePath: doc.uri.fsPath,
    getText: () => doc.getText(),
    lineCount: doc.lineCount,
    languageId: doc.languageId,
    lineAt: (line: number) => ({ text: doc.lineAt(line).text }),
  };
}

/** Singleton নির্মাণ helper — extension activate()-এ call করা যায়। */
export function createVscodePlatform(context: vscode.ExtensionContext): {
  notifications: VscodeNotification;
  prompt: VscodePrompt;
  secrets: VscodeSecretStorage;
  workspace: VscodeWorkspace;
} {
  const secrets = new VscodeSecretStorage(context.secrets);
  return {
    notifications: new VscodeNotification(),
    prompt: new VscodePrompt(),
    secrets,
    workspace: new VscodeWorkspace(secrets),
  };
}