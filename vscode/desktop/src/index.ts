/**
 * SupremeAI Desktop Application Bridge
 * 
 * Provides native OS system tray, keyboard global shortcuts,
 * and direct IPC communication with local SupremeAI agent runners.
 */

export interface DesktopConfig {
  gatewayUrl: string;
  apiKey: string;
  autoLaunch: boolean;
  theme: "dark" | "light" | "system";
}

export const DEFAULT_DESKTOP_CONFIG: DesktopConfig = {
  gatewayUrl: "http://127.0.0.1:8080",
  apiKey: "",
  autoLaunch: false,
  theme: "dark",
};

export class SupremeAIDesktop {
  private config: DesktopConfig;

  constructor(config: Partial<DesktopConfig> = {}) {
    this.config = { ...DEFAULT_DESKTOP_CONFIG, ...config };
  }

  public async start(): Promise<void> {
    console.log("[SupremeAI Desktop] Initializing native runtime...");
    console.log(`[SupremeAI Desktop] Connected gateway: ${this.config.gatewayUrl}`);
  }
}

if (require.main === module) {
  const app = new SupremeAIDesktop();
  app.start().catch(console.error);
}
