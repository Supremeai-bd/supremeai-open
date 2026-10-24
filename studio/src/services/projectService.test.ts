import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import { projectService } from './projectService';
import { apiClient } from './apiClient';

const mockedClient = apiClient as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

describe('projectService (ERR-B01)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('listProjects GETs /api/v1/projects', async () => {
    mockedClient.get.mockResolvedValue({ items: [{ id: 'p1', name: 'A' }], total: 1 });
    const res = await projectService.listProjects();
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/projects');
    expect(res.total).toBe(1);
  });

  it('createProject POSTs name + description and unwraps project', async () => {
    mockedClient.post.mockResolvedValue({
      status: 'success',
      project: { id: 'p2', name: 'Q4', description: 'd', status: 'active' },
    });
    const res = await projectService.createProject({ name: 'Q4', description: 'd' });
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/projects', {
      name: 'Q4',
      description: 'd',
    });
    expect(res.id).toBe('p2');
  });

  it('renameProject PATCHes the project resource', async () => {
    mockedClient.patch.mockResolvedValue({
      status: 'success',
      project: { id: 'p2', name: 'Q4 v2', description: '', status: 'active' },
    });
    const res = await projectService.renameProject('p2', 'Q4 v2');
    expect(apiClient.patch).toHaveBeenCalledWith('/api/v1/projects/p2', { name: 'Q4 v2' });
    expect(res.name).toBe('Q4 v2');
  });

  it('deleteProject DELETEs the project resource', async () => {
    mockedClient.delete.mockResolvedValue({ status: 'success', message: 'Project deleted' });
    await projectService.deleteProject('p2');
    expect(apiClient.delete).toHaveBeenCalledWith('/api/v1/projects/p2');
  });
});
