import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.supremeai.mobile",
  appName: "SupremeAI Companion",
  webDir: "dist",
  server: { androidScheme: "https" },
  plugins: {
    Preferences: {},
  },
};

export default config;
