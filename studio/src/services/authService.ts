// Authentication Service for SupremeAI 2.0 (Zero-Firebase / Native Auth)
// বাংলা মন্তব্য: এটি পিওর নেটিভ অ্যাডমিন লগইন ও টিওটিপি অথেন্টিকেশন সার্ভিস প্রোভাইড করে।

import { apiClient } from './apiClient';

export const authService = {
  // Native (zero-firebase) admin auth endpoints
  adminLogin: async (email: string, password: string): Promise<{ status: string; token?: string; uid?: string; email?: string }> => {
    const response = await apiClient.post<{ status: string; token?: string; access_token?: string; jwt?: string; uid?: string; email?: string }>('/api/admin/login', { email, password });
    return { ...response, token: response.token ?? response.access_token ?? response.jwt };
  },

  adminTotpVerify: async (otp: string, rememberBrowser = false): Promise<{ status: string; token: string }> => {
    return apiClient.post<{ status: string; token: string }>('/api/admin/totp-verify', { otp, remember_browser: rememberBrowser });
  },

  adminTotpSetup: async (): Promise<{ secret: string; provisioning_uri: string; recovery_codes?: string[] }> => {
    return apiClient.post<{ secret: string; provisioning_uri: string; recovery_codes?: string[] }>('/api/admin/totp-setup', {});
  },

  adminLogout: async (): Promise<void> => {
    try {
      await apiClient.post('/api/admin/logout', {});
    } catch {
      // best-effort
    }
  },
};
