import { vi } from 'vitest';

export const window = {
  showInformationMessage: vi.fn(),
  showErrorMessage: vi.fn(),
  showWarningMessage: vi.fn(),
  showInputBox: vi.fn().mockResolvedValue('mock-api-key'),
  createOutputChannel: vi.fn().mockReturnValue({ appendLine: vi.fn(), show: vi.fn() }),
};

export const commands = {
  executeCommand: vi.fn().mockResolvedValue(undefined),
  registerCommand: vi.fn().mockReturnValue({ dispose: vi.fn() }),
};

export const workspace = {
  isTrusted: true,
  // এখানে আপডেট মেথডটি চেইনের ভেতরে সরাসরি ডিফাইন করা হয়েছে
  getConfiguration: vi.fn().mockReturnValue({
    get: vi.fn().mockReturnValue(undefined),
    update: vi.fn().mockResolvedValue(undefined),
  }),
  workspaceFolders: [],
  onDidSaveTextDocument: vi.fn().mockReturnValue({ dispose: vi.fn() }),
};

export const authentication = {
  getSession: vi.fn().mockResolvedValue(undefined),
};

export const EventEmitter = vi.fn().mockImplementation(() => ({
  event: vi.fn(),
  fire: vi.fn(),
  dispose: vi.fn(),
}));
