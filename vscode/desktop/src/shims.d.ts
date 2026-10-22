declare module "@monaco-editor/react" {
  const MonacoEditor: any;
  export default MonacoEditor;
}
declare module "xterm" {
  export class Terminal {
    constructor(options?: any);
    open(el: HTMLElement): void;
    writeln(line: string): void;
    dispose(): void;
    loadAddon(addon: any): void;
  }
}
declare module "xterm-addon-fit" {
  export class FitAddon {
    fit(): void;
  }
}
declare module "@tauri-apps/api/core" {
  export function invoke<T = unknown>(cmd: string, args?: Record<string, unknown>): Promise<T>;
}
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
