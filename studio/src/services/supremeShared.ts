/**
 * SupremeAI Shared Services — Desktop (Electron) Integration Bootstrap
 *
 * `@supremeai/shared-services` প্যাকেজ থেকে কোর সার্ভিসগুলো desktop-এ
 * ব্যবহারের জন্য এখানে একবার initialize করা হয়।
 *
 * বাংলা নোট:
 * - Token Provider: services/tokenStorage (sessionStorage, Issue #521) থেকে token নেয়
 * - Backend URL: frontend-এর `BACKEND_URL` কনফিগ ব্যবহার করে
 * - SecretStorage: Electron adapter-এর localStorage-implementation
 */

import {
  SupremeAIService,
  SecurityScanner,
  PerformanceMonitor,
  SelfHealingService,
  TelemetryTracker,
  CrossAiObserverService,
  ScopeGuardService,
  createElectronPlatform,
  type PlatformPrompt,
} from '@supremeai/shared-services';
import { getApiBaseUrl } from '../utils/api';
import { apiClient } from './apiClient';
import { getAdminToken, getUserToken } from './tokenStorage';

// ---------- Platform ----------
const platform = createElectronPlatform();

/** একটি React custom prompt inject করার জন্য (JIT OTP modal)। */
export function setDesktopPrompt(prompt: PlatformPrompt): void {
  platform.prompt.setCustomPrompt(prompt);
}

// ---------- Token Provider ----------
class LocalStorageTokenProvider {
  getToken(): string | null {
    try {
      // Admin token প্রিফারেন্স (admin portal-এ), নাহলে user token
      // Issue #521: tokenStorage (sessionStorage-first, legacy localStorage swept)
      return getAdminToken() || getUserToken();
    } catch (storageError) {
      console.warn('[v0] Auth token storage is unavailable', storageError);
      return null;
    }
  }
}

// ---------- Shared Service Instance ----------
let _svc: {
  service: SupremeAIService;
  security: SecurityScanner;
  performance: PerformanceMonitor;
  healing: SelfHealingService;
  scope: ScopeGuardService;
} | null = null;

export function getSharedServices() {
  if (_svc) {
    return _svc;
  }

  const backendUrl = (getApiBaseUrl() || import.meta.env.VITE_BACKEND_URL || '').replace(/\/$/, '');
  if (!backendUrl) throw new Error('A backend URL must be configured via VITE_BACKEND_URL or VITE_API_URL.');

  const service = new SupremeAIService(
    {
      backendUrl,
      enableRealTimeLearning: true,
      autoReportErrors: true,
      enableChat: true,
    },
    new LocalStorageTokenProvider()
  );

  const security = new SecurityScanner(service);
  const performance = new PerformanceMonitor(service);
  const healing = SelfHealingService.initialize(service);
  const scope = ScopeGuardService.getInstance();

  // Cross-AI observer ও telemetry standby-তে রাখা হয়
  CrossAiObserverService.initialize();
  TelemetryTracker.initialize();

  _svc = { service, security, performance, healing, scope };
  return _svc;
}

/** Electron main process API (primary), নাহলে raw fetch-based fallback। */
export function apiCall(options: {
  endpoint: string;
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}) {
  if (typeof window !== 'undefined' && window.supremeDesktopAPI) {
    return window.supremeDesktopAPI.apiCall(options);
  }
  // Issue #2522: raw fetch -> apiClient.stream — timeout/queue/cold-start retry
  // পাওয়া যায়, আর {status, ok, data} কনট্র্যাক্ট অটুট থাকে (raw Response দরকার)।
  return apiClient.stream(options.endpoint, {
    method: options.method || 'GET',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: options.body ? JSON.stringify(options.body) : undefined,
  }).then(async (res) => {
    let data;
    try {
      data = await res.json();
    } catch {
      data = await res.text();
    }
    return { status: res.status, ok: res.ok, data };
  });
}

export { platform };
