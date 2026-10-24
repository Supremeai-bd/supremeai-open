import { describe, it, expect, vi, beforeEach } from 'vitest';

const { mockEmit, mockEvents } = vi.hoisted(() => ({
  mockEmit: vi.fn(),
  mockEvents: {
    METRICS_UPDATE_AVAILABLE: 'METRICS_UPDATE_AVAILABLE',
    RATE_LIMIT_HIT: 'RATE_LIMIT_HIT',
    SKILL_AUTO_CREATED: 'SKILL_AUTO_CREATED',
  },
}));

vi.mock('../lib/componentEventBus', () => ({
  eventBus: { emit: (...args: unknown[]) => mockEmit(...args) },
  Events: mockEvents,
}));

vi.mock('../utils/api', () => ({
  getApiBaseUrl: () => 'https://api.test',
}));

vi.mock('./apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    headers?: Record<string, string>;
    constructor(message: string, status = 0, headers?: Record<string, string>) {
      super(message);
      this.status = status;
      this.headers = headers;
    }
  },
}));

import {
  fetchSkillCatalog,
  checkLiveness,
  checkReadiness,
  getStatusBadge,
  installSkill,
  uninstallSkill,
} from './skillsService';
import { apiClient, ApiError } from './apiClient';

describe('skillsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockEmit.mockClear();
    global.fetch = vi.fn();
  });

  it('fetchSkillCatalog returns data and emits a metrics event', async () => {
    (apiClient.get as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ skills: [], total: 0, user_role: 'user' });
    const res = await fetchSkillCatalog();
    expect(apiClient.get).toHaveBeenCalledWith('/api/skills/catalog');
    expect(res.total).toBe(0);
    expect(mockEmit).toHaveBeenCalledWith(mockEvents.METRICS_UPDATE_AVAILABLE, expect.any(Object));
  });

  it('fetchSkillCatalog emits RATE_LIMIT_HIT and rethrows on 429', async () => {
    (apiClient.get as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError('rate', 429)
    );
    await expect(fetchSkillCatalog()).rejects.toThrow('rate');
    expect(mockEmit).toHaveBeenCalledWith(mockEvents.RATE_LIMIT_HIT, expect.any(Object));
  });

  it('getStatusBadge maps every status and falls back for unknowns', () => {
    expect(getStatusBadge('active').label).toContain('Active');
    expect(getStatusBadge('experimental').label).toContain('Experimental');
    expect(getStatusBadge('deprecated').label).toContain('Deprecated');
    expect(getStatusBadge('coming_soon').label).toContain('Coming Soon');
    expect(getStatusBadge('weird' as never).label).toBe('weird');
  });

  // Issue #2522: probes now go through apiClient.get (timeout/retry/queue) —
  // mocks updated from global.fetch stubs to the apiClient contract.
  it('checkLiveness returns true when the endpoint is ok', async () => {
    (apiClient.get as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'ok',
    });
    expect(await checkLiveness()).toBe(true);
  });

  it('checkLiveness returns false when the request throws', async () => {
    (apiClient.get as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('network')
    );
    expect(await checkLiveness()).toBe(false);
  });

  it('checkReadiness returns subsystems when ready', async () => {
    (apiClient.get as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      subsystems: { db: 'up' },
    });
    const res = await checkReadiness();
    expect(res.ready).toBe(true);
    expect(res.subsystems).toEqual({ db: 'up' });
  });

  it('checkReadiness returns not-ready on failure', async () => {
    (apiClient.get as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('down')
    );
    const res = await checkReadiness();
    expect(res.ready).toBe(false);
    expect(res.subsystems).toEqual({});
  });

  it('installSkill posts to the real contract and emits SKILL_AUTO_CREATED', async () => {
    (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 'installed', skill: 's1', version: '1.0', message: 'ok' });
    const res = await installSkill('s1');
    expect(apiClient.post).toHaveBeenCalledWith('/api/skills/install?skill=s1');
    expect(res.success).toBe(true);
    expect(res.skillId).toBe('s1');
    expect(res.installedVersion).toBe('1.0');
    expect(mockEmit).toHaveBeenCalledWith(mockEvents.SKILL_AUTO_CREATED, expect.any(Object));
  });

  it('uninstallSkill deletes via the real contract', async () => {
    (apiClient.delete as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      undefined
    );
    await uninstallSkill('s1');
    expect(apiClient.delete).toHaveBeenCalledWith('/api/skills/uninstall?skill=s1');
  });
});
