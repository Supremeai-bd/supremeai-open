import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./apiClient', () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

import { agentService } from './agentService';
import { apiClient } from './apiClient';

describe('agentService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('executeAgentTask posts the instruction to the plural agents endpoint with task_id', async () => {
    // ERR-A02 contract fix (defect register 2026-09-15): plural /api/v1/agents/execute +
    // mandatory task_id per backend AgentTaskRequest.
    // ERR-H08 (2026-09-16): backend now honors auto_execute — execute sends TRUE.
    const uuid = 'fixed-uuid';
    vi.stubGlobal('crypto', { randomUUID: () => uuid });
    try {
      (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
        id: '1',
        name: 't',
        status: 'done',
      });
      const res = await agentService.executeAgentTask('a1', 'do it now please');
      expect(apiClient.post).toHaveBeenCalledWith('/api/v1/agents/execute', {
        task_id: `a1-${uuid}`,
        prompt: 'do it now please',
        auto_execute: true,
      });
      expect(res.status).toBe('done');
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('planAgentTask requests plan-only mode (auto_execute: false)', async () => {
    // ERR-H08: honest plan-only mode; nothing is executed on the backend.
    const uuid = 'fixed-uuid';
    vi.stubGlobal('crypto', { randomUUID: () => uuid });
    try {
      (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
        status: 'planned',
        result: 'Investigate issue, propose fix, apply fix, verify.\n1. investigate',
      });
      const res = await agentService.planAgentTask('a1', 'fix the login error please');
      expect(apiClient.post).toHaveBeenCalledWith('/api/v1/agents/execute', {
        task_id: `a1-plan-${uuid}`,
        prompt: 'fix the login error please',
        auto_execute: false,
      });
      expect(res.status).toBe('planned');
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('listAgents gets the agents endpoint', async () => {
    (apiClient.get as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      agents: [{ id: 'a' }],
    });
    const res = await agentService.listAgents();
    expect(apiClient.get).toHaveBeenCalledWith('/api/agents/');
    expect(res).toHaveLength(1);
  });

  it('getAgentStatus hits the status endpoint', async () => {
    (apiClient.get as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'running',
    });
    const res = await agentService.getAgentStatus('a1');
    expect(apiClient.get).toHaveBeenCalledWith('/api/agents/a1/status');
    expect(res.status).toBe('running');
  });
});
