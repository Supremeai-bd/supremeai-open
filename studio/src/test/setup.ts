import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
  };
})();

Object.defineProperty(global, 'localStorage', {
  value: localStorageMock,
  writable: true
});

class EventSourceMock {
  onopen: (() => void) | null = null;

  onmessage: ((event: any) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  url: string;
  constructor(url: string) {
    this.url = url;
  }
}
Object.defineProperty(global, 'EventSource', {
  value: EventSourceMock,
  writable: true,
});

// বাংলা মন্তব্য: কিছু component (যেমন App root-এ mounted ThemeSyncProvider) mount হওয়ার সাথে সাথেই
// fetch কল করে। সততা নোট (honesty fix): SSE hook useServerStream এখন unmounted/dead
// (কোনো runtime importer নেই), তাই mount-কালীন SSE কল আসলে ঘটে না। যেসব টেস্ট ফাইল
// নিজে global.fetch mock করে না (যেমন App.test.tsx), সেখানে
// jsdom-এর AbortController-এর signal, Node-এর undici fetch-এর instanceof AbortSignal চেকে ফেল করে —
// "RequestInit: Expected signal (...) to be an instance of AbortSignal" এই error থ্রো করে এবং
// টেস্ট শেষ হওয়ার পরেও promise settle হওয়ায় "Unhandled Rejection" হিসেবে ধরা পড়ে (CI job fail করে)।
// তাই ডিফল্ট একটি resolved fetch mock দেওয়া হলো, যাতে real network/AbortSignal validation স্পর্শ না হয়।
// যেসব টেস্ট নিজে global.fetch = vi.fn(...) সেট করে (যেমন apiClient.test.ts), তারা এটিকে override করবে।
Object.defineProperty(global, 'fetch', {
  value: vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      headers: new Map(),
      json: async () => ({}),
      text: async () => '',
    } as unknown as Response)
  ),
  writable: true,
  configurable: true,
});
