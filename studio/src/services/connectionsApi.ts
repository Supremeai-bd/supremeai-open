// বাংলা মন্তব্য: Centralized Connections API service — apiClient wrapper।
// কোনো secret হ্যান্ডল করে না। ইউজার স্কোপড ক্যাপাবিলিটি ও URL ডিটেকশন/রেজিস্ট্রেশন প্রদান করে।

import { apiClient } from './apiClient';
import type {
  ConnectionDetection,
  ConnectionRegisterRequest,
  MyWorkspaceContract,
  ExecutionMode,
} from '../types/contracts';

export interface RegisterConnectionResponse {
  connection_id: string;
  capability_id: string;
  health: string;
  message: string;
}

export interface SetModeResponse {
  user_id: string;
  mode: ExecutionMode;
  persisted: boolean;
  message: string;
}

export const connectionsApi = {
  /**
   * ব্যবহারকারীর স্কোপড ওয়ার্কস্পেস স্টেট আনে (authoritative capabilities + execution mode)
   */
  getMyWorkspace: async (): Promise<MyWorkspaceContract> => {
    return apiClient.get<MyWorkspaceContract>('/api/v1/connections/my-workspace');
  },

  /**
   * কোনো নেটওয়ার্ক কল ছাড়া URL পেস্ট করলেই টাইপ শনাক্ত করে (Acid Test 10)
   */
  detectConnection: async (url: string): Promise<ConnectionDetection> => {
    return apiClient.post<ConnectionDetection>('/api/v1/connections/detect', { url });
  },

  /**
   * নতুন কাস্টম টুল বা কানেকশন গভর্ন্ড পাথে রেজিস্টার করে
   */
  registerConnection: async (req: ConnectionRegisterRequest): Promise<RegisterConnectionResponse> => {
    return apiClient.post<RegisterConnectionResponse>('/api/v1/connections/register', req);
  },

  /**
   * ব্যবহারকারীর সেলফ-সার্ভিস এক্সিকিউশন মোড আপডেট করে
   */
  setExecutionMode: async (mode: ExecutionMode): Promise<SetModeResponse> => {
    return apiClient.post<SetModeResponse>('/api/v1/access/set-mode', { mode });
  },
};
