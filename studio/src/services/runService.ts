// Run Observer Service — ERR-B04 fix (canonical defect register 2026-09-15)
// বাংলা মন্তব্য: /runs পেজ আগে স্ট্যাটিক মক ছিল (ERR-B04) — কোনো run observer,
// execution list, বা step retry ইন্টারফেস ছিল না। এই সার্ভিস real Mission
// Orchestration API-কে wrap করে: list = runs, trace = step observer,
// repair = failed run retry, cancel = active run বন্ধ।

import { apiClient } from './apiClient';

export interface MissionRun {
  id: string;
  title: string;
  goal_text: string;
  state: string;
  priority: number;
  current_phase: number;
  phases: { name: string; status: string; note: string }[];
  agent_id: string | null;
  failure_reason: string | null;
  repair_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface RunListResponse {
  items: MissionRun[];
  count: number;
  skip: number;
  limit: number;
}

export interface TraceEvent {
  id: string;
  mission_id: string;
  seq: number;
  phase: number;
  event: string;
  detail: Record<string, unknown> | null;
  created_at: string | null;
}

export interface TraceResponse {
  items: TraceEvent[];
  count: number;
  mission_id: string;
}

export const runService = {
  listRuns: async (params?: { state?: string; limit?: number }): Promise<RunListResponse> => {
    const query = new URLSearchParams();
    if (params?.state) query.set('state', params.state);
    query.set('limit', String(params?.limit ?? 50));
    return apiClient.get<RunListResponse>(`/api/v1/missions?${query.toString()}`);
  },

  getTrace: async (missionId: string): Promise<TraceResponse> => {
    return apiClient.get<TraceResponse>(`/api/v1/missions/${missionId}/trace`);
  },

  repairRun: async (missionId: string, reason?: string): Promise<MissionRun> => {
    return apiClient.post<MissionRun>(`/api/v1/missions/${missionId}/repair`, {
      reason: reason ?? 'Retry requested from runs observer',
    });
  },

  cancelRun: async (missionId: string, reason?: string): Promise<MissionRun> => {
    return apiClient.post<MissionRun>(`/api/v1/missions/${missionId}/cancel`, {
      reason: reason ?? 'Cancelled from runs observer',
    });
  },

  startRun: async (missionId: string): Promise<MissionRun> => {
    return apiClient.post<MissionRun>(`/api/v1/missions/${missionId}/start`);
  },
};
