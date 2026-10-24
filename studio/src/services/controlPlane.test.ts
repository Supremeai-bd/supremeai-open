import { describe, it, expect, vi, beforeEach } from 'vitest';
import { controlPlane, capabilityAvailable } from './controlPlane';
import type { ControlPlaneRegistry } from './controlPlane';
import * as apiUtils from '../utils/api';

vi.mock('../utils/api', () => ({
  fetchWithRetry: vi.fn(),
  getApiBaseUrl: vi.fn((_path: string) => `https://supremeai-primary-node.onrender.com`),
}));

vi.mock('./apiClient', () => ({
  getAuthHeaders: vi.fn().mockResolvedValue({ Authorization: 'Bearer test-token' }),
}));

describe('controlPlane service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('registry fetches and parses registry', async () => {
    const mockRegistry: ControlPlaneRegistry = {
      version: '2.0.0',
      timestamp: '2026-09-04T00:00:00Z',
      services: [{ id: 'core', display_name: 'Core', role: 'primary', capabilities: ['chat'], critical: true, configured: true, health_path: '/health' }],
      capabilities: [{ id: 'chat', service_id: 'core', available: true }],
    };

    vi.mocked(apiUtils.fetchWithRetry).mockResolvedValueOnce({
      ok: true,
      json: async () => mockRegistry,
    } as unknown as Response);

    const result = await controlPlane.registry();
    expect(apiUtils.fetchWithRetry).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/control-plane/registry'),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
          Accept: 'application/json',
        }),
      })
    );
    expect(result).toEqual(mockRegistry);
  });

  it('health throws an Error when response is not ok', async () => {
    vi.mocked(apiUtils.fetchWithRetry).mockResolvedValueOnce({
      ok: false,
      status: 503,
    } as unknown as Response);

    await expect(controlPlane.health()).rejects.toThrow('Control plane request failed: 503');
  });

  it('submitTask sends task payload via POST', async () => {
    const mockResponse = { task_id: 'task-123', status: 'queued' };
    vi.mocked(apiUtils.fetchWithRetry).mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    } as unknown as Response);

    const taskPayload = { goal: 'test goal', metadata: { run: 1 } };
    const result = await controlPlane.submitTask(taskPayload);

    expect(apiUtils.fetchWithRetry).toHaveBeenCalledWith(
      expect.stringContaining('/tasks'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(taskPayload),
      })
    );
    expect(result).toEqual(mockResponse);
  });

  it('taskStatus fetches task by id', async () => {
    const mockStatus = { task_id: 'task-123', status: 'completed' };
    vi.mocked(apiUtils.fetchWithRetry).mockResolvedValueOnce({
      ok: true,
      json: async () => mockStatus,
    } as unknown as Response);

    const result = await controlPlane.taskStatus('task-123');
    expect(apiUtils.fetchWithRetry).toHaveBeenCalledWith(
      expect.stringContaining('/tasks/task-123'),
      expect.anything()
    );
    expect(result).toEqual(mockStatus);
  });

  it('cancelTask sends cancel POST', async () => {
    const mockCancel = { task_id: 'task-123', status: 'cancelled' };
    vi.mocked(apiUtils.fetchWithRetry).mockResolvedValueOnce({
      ok: true,
      json: async () => mockCancel,
    } as unknown as Response);

    const result = await controlPlane.cancelTask('task-123');
    expect(apiUtils.fetchWithRetry).toHaveBeenCalledWith(
      expect.stringContaining('/tasks/task-123/cancel'),
      expect.objectContaining({ method: 'POST' })
    );
    expect(result).toEqual(mockCancel);
  });

  it('capabilityAvailable helper accurately checks availability', () => {
    const registry: ControlPlaneRegistry = {
      version: '2.0.0',
      timestamp: '2026-09-04T00:00:00Z',
      services: [],
      capabilities: [
        { id: 'scraping', service_id: 'scraper', available: true },
        { id: 'gpu_training', service_id: 'kaggle', available: false },
      ],
    };

    expect(capabilityAvailable(registry, 'scraping')).toBe(true);
    expect(capabilityAvailable(registry, 'gpu_training')).toBe(false);
    expect(capabilityAvailable(registry, 'unknown_feat')).toBe(false);
    expect(capabilityAvailable(undefined, 'scraping')).toBe(false);
  });
});
