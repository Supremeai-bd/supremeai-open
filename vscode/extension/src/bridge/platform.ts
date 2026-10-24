export interface SecureStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

export function createSecureStore(): SecureStore {
  const vscode = (globalThis as any).acquireVsCodeApi?.();
  return {
    async get(key: string) {
      if (!vscode) {
        try {
          return (globalThis as any).localStorage?.getItem(key) ?? null;
        } catch {
          return null;
        }
      }
      return new Promise<string | null>((resolve) => {
        let done = false;
        const handler = (event: MessageEvent) => {
          const m = (event as any)?.data;
          if (m && m.type === "secure_value" && m.key === key) {
            done = true;
            window.removeEventListener("message", handler);
            resolve(m.value ?? null);
          }
        };
        window.addEventListener("message", handler);
        vscode.postMessage({ type: "secure_get", key });
        setTimeout(() => {
          if (!done) {
            window.removeEventListener("message", handler);
            resolve(null);
          }
        }, 1000);
      });
    },
    async set(key: string, value: string) {
      if (!vscode) {
        try { (globalThis as any).localStorage?.setItem(key, value); } catch { /* ignore */ }
        return;
      }
      vscode.postMessage({ type: "secure_set", key, value });
    },
    async remove(key: string) {
      if (!vscode) {
        try { (globalThis as any).localStorage?.removeItem(key); } catch { /* ignore */ }
        return;
      }
      vscode.postMessage({ type: "secure_remove", key });
    },
  };
}

export function detectPlatform() {
  return "extension" as const;
}
