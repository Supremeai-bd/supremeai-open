import { describe, it, expect, vi } from 'vitest';

const apiClient = {
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
};

vi.mock('./apiClient', () => ({ apiClient }));

const { adminService } = await import('./adminService');

describe('adminService', () => {
  it('getHealthMap calls the health-map endpoint', async () => {
    apiClient.get.mockResolvedValueOnce({ ok: true });
    const res = await adminService.getHealthMap();
    expect(apiClient.get).toHaveBeenCalledWith('/admin-api/health-map');
    expect(res).toEqual({ ok: true });
  });

  it('getCostsReport calls the costs endpoint', async () => {
    apiClient.get.mockResolvedValueOnce({ report: 'r' });
    const res = await adminService.getCostsReport();
    expect(apiClient.get).toHaveBeenCalledWith('/admin-api/costs');
    expect(res.report).toBe('r');
  });

  it('listUsers calls the users endpoint', async () => {
    apiClient.get.mockResolvedValueOnce([{ username: 'a', role: 'god', permissions: [] }]);
    const res = await adminService.listUsers();
    expect(apiClient.get).toHaveBeenCalledWith('/admin-api/users');
    expect(res[0].username).toBe('a');
  });

  it('createUser posts a user', async () => {
    const user = { username: 'b', role: 'viewer', permissions: ['x'] };
    apiClient.post.mockResolvedValueOnce(user);
    const res = await adminService.createUser(user);
    expect(apiClient.post).toHaveBeenCalledWith('/admin-api/users', user);
    expect(res).toEqual(user);
  });

  it('deleteUser deletes by username', async () => {
    apiClient.delete.mockResolvedValueOnce({ status: 'ok' });
    const res = await adminService.deleteUser('b');
    expect(apiClient.delete).toHaveBeenCalledWith('/admin-api/users/b');
    expect(res).toEqual({ status: 'ok' });
  });

  it('triggerDeploy posts to deploy endpoint', async () => {
    apiClient.post.mockResolvedValueOnce({ status: 'queued' });
    const res = await adminService.triggerDeploy();
    expect(apiClient.post).toHaveBeenCalledWith('/admin-api/deploy');
    expect(res.status).toBe('queued');
  });
});
