// Admin operations service for SupremeAI 2.0 Command Center
// বাংলা মন্তব্য: অ্যাডমিন কমান্ড সেন্টার, ইউজার ম্যানেজমেন্ট ও খরচ মনিটর করার সার্ভিস।

import { apiClient } from './apiClient';

export interface AdminUser {
  username: string;
  role: string;
  permissions: string[];
}

export const adminService = {
  getHealthMap: async (): Promise<unknown> => {
    return apiClient.get<unknown>('/admin-api/health-map');
  },

  getCostsReport: async (): Promise<{ report: string }> => {
    return apiClient.get<{ report: string }>('/admin-api/costs');
  },

  listUsers: async (): Promise<AdminUser[]> => {
    return apiClient.get<AdminUser[]>('/admin-api/users');
  },

  createUser: async (user: AdminUser): Promise<AdminUser> => {
    return apiClient.post<AdminUser>('/admin-api/users', user);
  },

  deleteUser: async (username: string): Promise<{ status: string }> => {
    return apiClient.delete<{ status: string }>(`/admin-api/users/${username}`);
  },

  triggerDeploy: async (): Promise<{ status: string }> => {
    return apiClient.post<{ status: string }>('/admin-api/deploy');
  },
};
