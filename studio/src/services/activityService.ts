// Activity Service — ERR-B03 fix (canonical defect register 2026-09-15)
// বাংলা মন্তব্য: /activity পেজ আগে স্ট্যাটিক মক কার্ড ছিল (ERR-B03)। এখন real
// Mission Orchestration API (/api/v1/missions) থেকে event timeline আসে —
// planned → approved → assigned → running → repairing → succeeded/failed/cancelled
// লাইফসাইকেল, owner-scoped।

import { apiClient } from './apiClient';

export const MISSION_STATES = [
  'planned',
  'approved',
  'assigned',
  'running',
  'repairing',
  'succeeded',
  'failed',
  'cancelled',
] as const;

export type MissionState = (typeof MISSION_STATES)[number];

export interface MissionActivity {
  id: string;
  title: string;
  goal_text: string;
  state: MissionState;
  priority: number;
  current_phase: number;
  phases: { name: string; status: string; note: string }[];
  agent_id: string | null;
  failure_reason: string | null;
  repair_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ActivityListResponse {
  items: MissionActivity[];
  count: number;
  skip: number;
  limit: number;
}

export const activityService = {
  listActivity: async (params?: { state?: MissionState; limit?: number }): Promise<ActivityListResponse> => {
    const query = new URLSearchParams();
    if (params?.state) query.set('state', params.state);
    query.set('limit', String(params?.limit ?? 50));
    return apiClient.get<ActivityListResponse>(`/api/v1/missions?${query.toString()}`);
  },
};
