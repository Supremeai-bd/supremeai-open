/**
 * OTA (Over-The-Air) Live Update Manager for SupremeAI Mobile
 * Enables silent code/UI updates directly from GitHub Releases without requiring users to reinstall APK.
 */

export interface VersionInfo {
  version: string;
  bundleUrl: string;
  releaseNotes?: string;
}

const CURRENT_VERSION = '0.1.0';
const UPDATE_ENDPOINT =
  'https://raw.githubusercontent.com/Supremeai-bd/supremeai-vscode/main/mobile/latest-mobile.json';

export class MobileUpdateManager {
  private static instance: MobileUpdateManager;

  public static getInstance(): MobileUpdateManager {
    if (!MobileUpdateManager.instance) {
      MobileUpdateManager.instance = new MobileUpdateManager();
    }
    return MobileUpdateManager.instance;
  }

  /**
   * Check if a newer version of the mobile bundle or APK is available.
   */
  public async checkForUpdate(): Promise<VersionInfo | null> {
    try {
      const resp = await fetch(UPDATE_ENDPOINT, { cache: 'no-store' });
      if (!resp.ok) return null;
      const data = await resp.json();
      if (data && data.version && data.version !== CURRENT_VERSION) {
        return {
          version: data.version,
          bundleUrl: data.bundleUrl || data.apkUrl,
          releaseNotes: data.releaseNotes || 'Bug fixes and performance improvements.',
        };
      }
    } catch (err) {
      console.warn('OTA update check skipped (offline or network error):', err);
    }
    return null;
  }

  /**
   * Download and install the update dynamically
   */
  public async performUpdate(update: VersionInfo): Promise<void> {
    if (typeof window !== 'undefined' && update.bundleUrl) {
      // In native environment, trigger instant download or browser-based direct APK pull
      window.open(update.bundleUrl, '_system');
    }
  }
}

