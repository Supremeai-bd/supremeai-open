import { describe, it, expect, vi } from 'vitest';

const apiClient = {
  get: vi.fn(),
};

vi.mock('./apiClient', () => ({ apiClient }));

const { ciReportService } = await import('./ciReportService');

describe('ciReportService', () => {
  it('getCILogs fetches the ci-logs endpoint with the default limit', async () => {
    const reports = [{ id: 1, run_number: 5 }];
    apiClient.get.mockResolvedValueOnce(reports);
    const res = await ciReportService.getCILogs();
    expect(apiClient.get).toHaveBeenCalledWith('/admin-api/ci-logs?limit=20');
    expect(res).toEqual(reports);
  });

  it('getCILogs forwards a custom limit', async () => {
    const reports: unknown[] = [];
    apiClient.get.mockResolvedValueOnce(reports);
    const res = await ciReportService.getCILogs(3);
    expect(apiClient.get).toHaveBeenCalledWith('/admin-api/ci-logs?limit=3');
    expect(res).toEqual(reports);
  });
});
