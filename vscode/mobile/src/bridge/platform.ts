export type Platform = "tauri" | "capacitor" | "extension" | "web";

export function detectPlatform(): Platform {
  if (typeof window !== "undefined" && (window as any).__TAURI__) return "tauri";
  if (typeof window !== "undefined" && (window as any).Capacitor) return "capacitor";
  if (typeof (globalThis as any).acquireVsCodeApi === "function") return "extension";
  return "web";
}

export interface SecureStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

export function createSecureStore(): SecureStore {
  const platform = detectPlatform();
  if (platform === "capacitor") {
    return {
      async get(key) {
        const { Preferences } = await import("@capacitor/preferences");
        const { value } = await Preferences.get({ key });
        return value ?? null;
      },
      async set(key, value) {
        const { Preferences } = await import("@capacitor/preferences");
        await Preferences.set({ key, value });
      },
      async remove(key) {
        const { Preferences } = await import("@capacitor/preferences");
        await Preferences.remove({ key });
      },
    };
  }
  return {
    async get(key) {
      return sessionStorage.getItem(key);
    },
    async set(key, value) {
      sessionStorage.setItem(key, value);
    },
    async remove(key) {
      sessionStorage.removeItem(key);
    },
  };
}
