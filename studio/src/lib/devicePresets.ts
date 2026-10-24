/**
 * Device presets for mobile/tablet preview (#4148).
 *
 * বাংলা: বিল্ট-ইন মোবাইল প্রিভিউয়ের জন্য ডিভাইস ডাইমেনশন ডাটাবেস।
 * ৮টি key device + custom — BrowserPreview.tsx-এর existing desktop/tablet/mobile
 * presets extend করে।
 *
 * Design decisions (adapted from user's plan):
 * - lucide-react icons (NOT react-icons/fi — codebase convention)
 * - cyan/neutral colors (NOT indigo — AGENTS.md prohibits indigo/blue)
 * - 8 key devices (NOT 12 — consolidate to most-used)
 */

export interface DevicePreset {
  id: string;
  name: string;
  width: number;
  height: number;
  userAgent: string;
  deviceType: 'phone' | 'tablet';
  os: 'ios' | 'android' | 'other';
  pixelRatio: number;
  statusBarHeight: number;
  hasHomeIndicator: boolean;
}

export const DEVICE_PRESETS: DevicePreset[] = [
  // iPhones (2 — most common sizes)
  {
    id: 'iphone15',
    name: 'iPhone 15',
    width: 393,
    height: 852,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    deviceType: 'phone',
    os: 'ios',
    pixelRatio: 3,
    statusBarHeight: 47,
    hasHomeIndicator: true,
  },
  {
    id: 'iphone15promax',
    name: 'iPhone 15 Pro Max',
    width: 430,
    height: 932,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    deviceType: 'phone',
    os: 'ios',
    pixelRatio: 3,
    statusBarHeight: 47,
    hasHomeIndicator: true,
  },

  // Android (2 — Samsung + Pixel)
  {
    id: 'galaxyS24',
    name: 'Samsung Galaxy S24',
    width: 412,
    height: 915,
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    deviceType: 'phone',
    os: 'android',
    pixelRatio: 3.5,
    statusBarHeight: 24,
    hasHomeIndicator: false,
  },
  {
    id: 'pixel8',
    name: 'Google Pixel 8',
    width: 412,
    height: 915,
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    deviceType: 'phone',
    os: 'android',
    pixelRatio: 2.75,
    statusBarHeight: 24,
    hasHomeIndicator: false,
  },

  // iPads (2 — Air + Pro)
  {
    id: 'ipadAir',
    name: 'iPad Air (5th Gen)',
    width: 820,
    height: 1180,
    userAgent:
      'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    deviceType: 'tablet',
    os: 'ios',
    pixelRatio: 2,
    statusBarHeight: 0,
    hasHomeIndicator: false,
  },
  {
    id: 'ipadPro11',
    name: 'iPad Pro 11"',
    width: 834,
    height: 1194,
    userAgent:
      'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    deviceType: 'tablet',
    os: 'ios',
    pixelRatio: 2,
    statusBarHeight: 0,
    hasHomeIndicator: false,
  },

  // Small phone (SE-size — for testing minimal viewports)
  {
    id: 'iphoneSE',
    name: 'iPhone SE (3rd Gen)',
    width: 375,
    height: 667,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    deviceType: 'phone',
    os: 'ios',
    pixelRatio: 2,
    statusBarHeight: 20,
    hasHomeIndicator: false,
  },

  // Foldable (Galaxy Fold — for testing wide phone viewports)
  {
    id: 'galaxyFold',
    name: 'Samsung Galaxy Fold',
    width: 768,
    height: 1080,
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; SM-F946B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    deviceType: 'phone',
    os: 'android',
    pixelRatio: 3,
    statusBarHeight: 24,
    hasHomeIndicator: false,
  },

  // Custom (user-defined)
  {
    id: 'custom',
    name: 'Custom Device',
    width: 375,
    height: 667,
    userAgent: '',
    deviceType: 'phone',
    os: 'other',
    pixelRatio: 2,
    statusBarHeight: 20,
    hasHomeIndicator: false,
  },
];

export function getPresetById(id: string): DevicePreset | undefined {
  return DEVICE_PRESETS.find((d) => d.id === id);
}

export function getPresetsByType(type: 'phone' | 'tablet'): DevicePreset[] {
  return DEVICE_PRESETS.filter((d) => d.deviceType === type);
}
