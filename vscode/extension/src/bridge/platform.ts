export interface SecureStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

export function createSecureStore(): SecureStore {
  const vscode = (globalThis as any).acquireVsCodeApi?.();
  return {
    async get(_key: string) {
      return null;
    },
    async set(key: string, value: string) {
      vscode?.postMessage({ type: "secure_set", key, value });
    },
    async remove(key: string) {
      vscode?.postMessage({ type: "secure_remove", key });
    },
  };
}

export function detectPlatform() {
  return "extension" as const;
}
