// vi is available as a global (globals: true in vitest.config.ts)
vi.mock('vscode', () => ({
  window: {
    showInformationMessage: vi.fn(),
    showErrorMessage: vi.fn(),
    showWarningMessage: vi.fn(),
  },
  commands: {
    executeCommand: vi.fn().mockResolvedValue(undefined),
  },
  authentication: {
    getSession: vi.fn(),
  },
  env: {
    openExternal: vi.fn().mockResolvedValue(true),
  },
  Uri: {
    parse: vi.fn().mockImplementation((val: string) => ({ toString: () => val })),
  },
  workspace: {
    getConfiguration: vi.fn().mockReturnValue({
      update: vi.fn().mockResolvedValue(undefined),
      get: vi.fn().mockReturnValue(''),
    }),
    isTrusted: true,
  },
  extensions: {
    getExtension: vi.fn().mockReturnValue({
      extensionKind: 1,
    }),
  },
  EventEmitter: class {
    event = vi.fn();
    fire = vi.fn();
    dispose = vi.fn();
  },
}));
