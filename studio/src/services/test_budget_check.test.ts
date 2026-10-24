import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from './apiClient';

vi.mock('../utils/api', () => ({
  getApiBaseUrl: () => '<backend-url>'
}));

describe('Budget Check & Cost Guard (402) Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  it('should throw ApiError with status 402 when CostGuard rejects request', async () => {
     
    (global.fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 402,
      json: async () => ({ detail: 'Insufficient budget for model execution' }),
    });

    await expect(apiClient.post('/expensive-op')).rejects.toThrow(/Budget Limit Exceeded/);
  });
});
