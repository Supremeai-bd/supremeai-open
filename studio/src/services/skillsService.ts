// apps/studio-client/src/services/skillsService.ts
// বাংলা মন্তব্য: ব্যাকএন্ডের /api/skills/catalog এন্ডপয়েন্ট থেকে
// রোল-ভিত্তিক স্কিল ক্যাটালগ ফেচ করার সার্ভিস লেয়ার।

import { apiClient, ApiError } from './apiClient';
import { eventBus, Events } from '../lib/componentEventBus';

export type SkillStatus = 'active' | 'deprecated' | 'experimental' | 'coming_soon';

export interface SkillManifest {
  skill_id: string;
  name: string;
  description: string;
  version: string;
  category: string;
  status: SkillStatus;
  tags: string[];
  allowed_roles: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
}

export interface CatalogResponse {
  skills: SkillManifest[];
  total: number;
  user_role: string;
}

// বাংলা মন্তব্য: /api/skills/catalog এন্ডপয়েন্ট থেকে স্কিল লিস্ট ফেচ করে।
// ব্যাকএন্ড নিজেই JWT রোল পার্স করে ফিল্টার করা স্কিল রিটার্ন করে।
export const fetchSkillCatalog = async (): Promise<CatalogResponse> => {
  try {
    const response = await apiClient.get<CatalogResponse>('/api/skills/catalog');
    
    eventBus.emit(Events.METRICS_UPDATE_AVAILABLE, {
      source: 'skills_catalog',
      timestamp: Date.now(),
    });
    
    return response;
  } catch (error) {
    if (error instanceof ApiError && error.status === 429) {
      // Rate limited - notify user
      eventBus.emit(Events.RATE_LIMIT_HIT, {
        service: 'skills_catalog',
        retryAfter: undefined,
        timestamp: Date.now(),
      });
    }
    throw error;
  }
};

// বাংলা মন্তব্য: লাইভনেস প্রোব — UI হার্টবিট থেকে /api/v1/live চেক করে
export const checkLiveness = async (): Promise<boolean> => {
  // Issue #2522: raw fetch → apiClient.get — timeout, retry, queue সব ক্লায়েন্ট থেকে আসে।
  // non-ok হলে ApiError throw হয় → catch এ false, আগের ok-check সেমান্টিকস অটুট।
  try {
    await apiClient.get('/api/v1/live', { headers: { 'Cache-Control': 'no-cache' } });
    return true;
  } catch {
    return false;
  }
};

// বাংলা মন্তব্য: রেডিনেস প্রোব — DB ও Redis সহ সম্পূর্ণ dependency চেক
export const checkReadiness = async (): Promise<{ ready: boolean; subsystems: Record<string, string> }> => {
  // Issue #2522: raw fetch → apiClient.get — non-ok/parse fail উভয়ই degraded রিপোর্ট করে।
  try {
    const data = await apiClient.get<{ subsystems?: Record<string, string> }>('/api/v1/ready', {
      headers: { 'Cache-Control': 'no-cache' },
    });
    return { ready: true, subsystems: data.subsystems || {} };
  } catch {
    return { ready: false, subsystems: {} };
  }
};

// বাংলা মন্তব্য: স্কিল ক্যাটালগের স্ট্যাটাস রঙ ম্যাপিং হেল্পার
export const getStatusBadge = (status: SkillStatus): { label: string; color: string } => {
  const map: Record<SkillStatus, { label: string; color: string }> = {
    active: { label: '✅ Active', color: 'var(--supremeai-color-success, #22c55e)' },
    experimental: { label: '🧪 Experimental', color: 'var(--supremeai-color-warning, #f59e0b)' },
    deprecated: { label: '⚠️ Deprecated', color: 'var(--supremeai-color-danger, #ef4444)' },
    coming_soon: { label: '🔜 Coming Soon', color: 'var(--supremeai-color-neutral-400, #9ca3af)' },
  };
  return map[status] ?? { label: status, color: '#6b7280' };
};

export interface InstallResult {
  success: boolean;
  skillId: string;
  installedVersion: string;
  message: string;
}

interface InstallApiResponse {
  status: string;
  skill: string;
  version?: string;
  installed_at?: string;
  message: string;
}

export const installSkill = async (skillId: string): Promise<InstallResult> => {
  // ERR-H02 FIX: the backend contract is POST /api/skills/install?skill=<id>
  // (skills.py has no /{id}/install path segment) — the old URL 404'd.
  const response = await apiClient.post<InstallApiResponse>(
    `/api/skills/install?skill=${encodeURIComponent(skillId)}`
  );

  // Notify evolution system about new skill
  eventBus.emit(Events.SKILL_AUTO_CREATED, {
    skillId,
    source: 'manual_install',
    timestamp: Date.now(),
  });

  return {
    success: response.status === 'installed',
    skillId: response.skill,
    installedVersion: response.version ?? '',
    message: response.message,
  };
};

// ERR-B05 FIX (defect register 2026-09-15): user-facing marketplace search —
// the admin-buried EnhancedSkillMarketplace used /api/skills/search; now the
// normal user marketplace gets the same keyword search (server-side).
export const searchSkills = async (query: string): Promise<SkillManifest[]> => {
  return apiClient.get<SkillManifest[]>(
    `/api/skills/search?query=${encodeURIComponent(query)}`,
  );
};

export const listInstalledSkills = async (): Promise<SkillManifest[]> => {
  // installed_only=true filters against the backend's persisted install state.
  return apiClient.get<SkillManifest[]>(`/api/skills/search?installed_only=true`);
};

export const uninstallSkill = async (skillId: string): Promise<void> => {
  // ERR-H02 FIX: backend route is DELETE /api/skills/uninstall?skill=<id>
  // (the old /{id}/uninstall path never existed → 404, uninstall was broken).
  await apiClient.delete(`/api/skills/uninstall?skill=${encodeURIComponent(skillId)}`);
};
