/**
 * SupremeExtensionBridge — Platform-Agnostic resilient API bridge.
 * Token ও 401-handling দুটোই injectable token provider / notification এর মাধ্যমে হয়,
 * ফলে VS Code ও Desktop দুজনেই একই ব্রিজ ব্যবহার করে।
 */

import axios from 'axios';
import type { AxiosInstance, AxiosError } from 'axios';
import type { SupremeAIConfig } from './../types';
import type { PlatformNotification } from '../platform';

// বাংলা মন্তব্য (#3078): মৃত Cloud Run host হার্ডকোড সরানো (সার্ভিস Render-এ স্থানান্তরিত — wrangler.toml:60)।
// ডিফল্ট এখন খালি — config.backendUrl সেট না থাকলে constructor-এ স্পষ্ট সতর্কতা;
// কোনো অজানা/মৃত host-এ নীরব ট্রাফিক যাবে না (Issue #526-এর "no fake default" নীতি)।
const DEFAULT_BACKEND_URL = '';

export interface EvolveCodeResult {
  evolvedCode: string;
  model?: string;
  tokensUsed?: number;
}

export interface BridgeRequestOptions {
  timeoutMs?: number;
  correlationId?: string;
}

/** Token সোর্স — desktop ও VS Code আলাদা storage থাকতে পারে। */
export interface BridgeTokenSource {
  getToken(): string | null;
}

/** OnUnauthorized callback — লগইন ফ্লো টা outside inject করা যায়। */
export type UnauthorizedHandler = () => Promise<void>;

export class SupremeExtensionBridge {
  private client: AxiosInstance;
  private readonly baseUrl: string;
  private readonly extSessionId: string;
  private readonly tokenSource?: BridgeTokenSource;
  private readonly notifications?: PlatformNotification;
  private readonly onUnauthorized?: UnauthorizedHandler;

  constructor(options?: {
    config?: SupremeAIConfig;
    tokenSource?: BridgeTokenSource;
    notifications?: PlatformNotification;
    onUnauthorized?: UnauthorizedHandler;
  }) {
    const config = options?.config;
    const configured = config?.backendUrl || undefined;
    this.baseUrl = (configured || DEFAULT_BACKEND_URL).replace(/\/$/, '');
    if (!this.baseUrl) {
      // বাংলা মন্তব্য (#3078): backendUrl অনুপস্থিত — স্পষ্ট সতর্কতা (ফেক ডিফল্ট নয়)।
      // eslint-disable-next-line no-console
      console.warn(
        '[SupremeExtensionBridge] backendUrl কনফিগার করা হয়নি — SupremeAIConfig.backendUrl সেট করুন। পুরনো Cloud Run ডিফল্ট অবসরপ্রাপ্ত (503, #3078)。'
      );
    }
    this.extSessionId = `${typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : Date.now()}`;
    this.tokenSource = options?.tokenSource;
    this.notifications = options?.notifications;
    this.onUnauthorized = options?.onUnauthorized;

    this.client = axios.create({
      baseURL: this.baseUrl,
      timeout: 10000,
      headers: { 'Content-Type': 'application/json' },
    });

    this.initializeInterceptors();
  }

  private initializeInterceptors(): void {
    this.client.interceptors.request.use(async (request) => {
      const token = this.tokenSource?.getToken();
      if (token) {
        request.headers.set('Authorization', `Bearer ${token}`);
      }
      const traceId = `platform-${this.extSessionId}-${Date.now()}`;
      request.headers.set('X-Correlation-ID', traceId);
      return request;
    });

    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        if (error.response?.status === 401 && this.onUnauthorized) {
          await this.onUnauthorized();
        } else if (error.response?.status === 401) {
          this.notifications?.showErrorMessage(
            'SupremeAI: Auth Token Expired. Please login again.'
          );
        }
        // eslint-disable-next-line no-console
        console.error('[SupremeAI Bridge] API Error:', error.message);
        return Promise.reject(error);
      }
    );
  }

  public async triggerCodeEvolution(codeSnippet: string, options?: BridgeRequestOptions): Promise<string> {
    try {
      const response = await this.client.post<EvolveCodeResult>(
        '/agents/evolve-code',
        { code: codeSnippet },
        { timeout: options?.timeoutMs }
      );
      return response.data.evolvedCode;
    } catch (error) {
      this.notifications?.showErrorMessage(
        'SupremeAI: Failed to evolve code. Check output channel.'
      );
      throw error;
    }
  }

  public async post<T = unknown>(path: string, payload: unknown, options?: BridgeRequestOptions): Promise<T> {
    const response = await this.client.post<T>(path, payload, { timeout: options?.timeoutMs });
    return response.data;
  }

  public async fetchTargetRepositories(): Promise<unknown[]> {
    try {
      const response = await this.client.get<unknown[]>('/admin-api/workspaces/targets');
      return response.data;
    } catch {
      return [
        {
          id: 'main-repository',
          name: 'SupremeAI Main Codebase',
          scope: 'READ_ONLY',
          is_read_only: true,
          can_write: false,
        },
      ];
    }
  }

  public async bindTargetRepository(payload: unknown, otpCode?: string): Promise<unknown> {
    const headers: Record<string, string> = {};
    if (otpCode) {
      headers['X-JIT-OTP'] = otpCode;
    }
    const response = await this.client.post<unknown>('/workspaces/bind-target', payload, { headers });
    return response.data;
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }
}

let _apiBridgeSingleton: SupremeExtensionBridge | null = null;

export function getApiBridge(options: ConstructorParameters<typeof SupremeExtensionBridge>[0] = {}): SupremeExtensionBridge {
  if (!_apiBridgeSingleton) {
    _apiBridgeSingleton = new SupremeExtensionBridge(options);
  }
  return _apiBridgeSingleton;
}