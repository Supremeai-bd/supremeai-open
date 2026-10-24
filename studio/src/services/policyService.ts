import { apiClient } from './apiClient';

export interface EffectivePolicy {
  rules: Record<string, unknown>;
  features: Record<string, boolean>;
  sources: Record<string, string>;
}

export const policyService = {
  get: () => apiClient.get<EffectivePolicy>('/api/browser/policy'),
  updatePersonal: (rules: Record<string, unknown>) =>
    apiClient.put<EffectivePolicy>('/api/browser/policy', { rules }),
};
