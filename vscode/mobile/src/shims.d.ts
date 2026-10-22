declare module "@capacitor/preferences" {
  export const Preferences: {
    get(options: { key: string }): Promise<{ value: string | null }>;
    set(options: { key: string; value: string }): Promise<void>;
    remove(options: { key: string }): Promise<void>;
  };
}
declare module "@capacitor/core" {
  export interface CapacitorConfig {}
}
