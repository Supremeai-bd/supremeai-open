import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient, setApiConcurrency, pathRequiresIdempotencyKey, updateTokenCache } from './apiClient';

// Mock getApiBaseUrl
vi.mock('../utils/api', () => ({
  getApiBaseUrl: () => 'https://api.test-domain.com'
}));

// Mock useAdminStore
vi.mock('../store/adminStore', () => ({
  useAdminStore: {
    getState: vi.fn(() => ({
      adminAuthenticated: true,
      handleAdminLogout: vi.fn(),
    }))
  }
}));

describe('apiClient', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
    setApiConcurrency(3);
    // Issue #521: tokens live in sessionStorage — reset both tiers + the
    // module-level in-memory cache for test isolation.
    localStorage.clear();
    sessionStorage.clear();
    updateTokenCache(null);
  });

  it('should include credentials and process successful response', async () => {
    const mockResponse = { data: 'success' };
     
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    });

    const result = await apiClient.get('/test');

    expect(global.fetch).toHaveBeenCalledWith('https://api.test-domain.com/test', expect.objectContaining({
      credentials: 'include',
      headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      method: 'GET'
    }));
    expect(result).toEqual(mockResponse);
  });

  it('should throw ApiError with status 401 on unauthorized access', async () => {
     
    (global.fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Unauthorized' }),
    });

    await expect(apiClient.get('/secure')).rejects.toThrow('Unauthorized');
  });

  it('does not clear the persisted login for a feature endpoint 401', async () => {
    // Issue #521 (FE-04): the canonical token location is now sessionStorage.
    sessionStorage.setItem('supremeai_auth_token', 'persisted-token');

    // ERR-A05 fixture fix (defect register 2026-09-15): use a REAL backend feature route
    // (GET /api/agents/ exists in backend/api/routes/agents.py) instead of the phantom
    // /api/v1/projects route. The behavior under test is unchanged: non-session 401 must
    // not clear the persisted login.
    (global.fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 401,
      url: 'https://api.test-domain.com/api/agents/',
      json: async () => ({ detail: 'Unauthorized' }),
    });

    await expect(apiClient.get('/api/agents/')).rejects.toThrow('Unauthorized');
    expect(sessionStorage.getItem('supremeai_auth_token')).toBe('persisted-token');
  });

  it('clears the persisted login when auth validation returns 401', async () => {
    sessionStorage.setItem('supremeai_auth_token', 'expired-token');
     
    (global.fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 401,
      url: 'https://api.test-domain.com/api/v1/auth/me',
      json: async () => ({ detail: 'Unauthorized' }),
    });

    await expect(apiClient.get('/api/v1/auth/me')).rejects.toThrow('Unauthorized');
    expect(sessionStorage.getItem('supremeai_auth_token')).toBeNull();
  });

  it('should throw ApiError with status 429 on rate limit', async () => {
     
    (global.fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 429,
      json: async () => ({ detail: 'Too Many Requests' }),
    });

    await expect(apiClient.get('/rate-limit')).rejects.toThrow(/Rate limit exceeded/);
  });

  // FINAL-TEST FIX (2026-09-14): the Idempotency-Key header must ONLY be sent
  // on paths the backend actually requires it for (see IDEMPOTENCY_PATHS in
  // backend/api/middleware.py). Sending it anywhere else fails the CORS
  // preflight on the deployed backend (its allow-list omits the header),
  // which blocked production login with "Network Error".
  describe('pathRequiresIdempotencyKey', () => {
    it('returns true for the backend-required prefixes', () => {
      expect(pathRequiresIdempotencyKey('https://api.test-domain.com/api/task/run')).toBe(true);
      expect(pathRequiresIdempotencyKey('https://api.test-domain.com/api/github/webhook')).toBe(true);
      expect(pathRequiresIdempotencyKey('https://api.test-domain.com/api/auth/callback')).toBe(true);
      expect(pathRequiresIdempotencyKey('https://api.test-domain.com/api/pr/merge')).toBe(true);
      expect(pathRequiresIdempotencyKey('https://api.test-domain.com/api/agent/execute')).toBe(true);
    });

    it('returns false for auth, chat and other key-less routes', () => {
      expect(pathRequiresIdempotencyKey('https://api.test-domain.com/api/v1/auth/login')).toBe(false);
      expect(pathRequiresIdempotencyKey('https://api.test-domain.com/api/v1/auth/register')).toBe(false);
      expect(pathRequiresIdempotencyKey('https://api.test-domain.com/api/v1/chat/completions')).toBe(false);
      expect(pathRequiresIdempotencyKey('https://api.test-domain.com/api/v1/models')).toBe(false);
    });

    it('returns false for a malformed URL', () => {
      expect(pathRequiresIdempotencyKey('not a url at all')).toBe(false);
    });
  });

  describe('Idempotency-Key header injection', () => {
    const getFetchHeaders = (callIdx = 0): Record<string, string> => {
      const call = (global.fetch as any).mock.calls[callIdx];
      return call[1].headers as Record<string, string>;
    };

    it('does NOT send Idempotency-Key on POST /auth/login (production CORS blocker)', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: 'jwt' }),
      });

      await apiClient.post('/api/v1/auth/login', { email: 'a@b.c', password: 'x' });

      const headers = getFetchHeaders();
      expect(headers).not.toHaveProperty('Idempotency-Key');
    });

    it('DOES send Idempotency-Key on POST /api/task (backend-required route)', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ok: true }),
      });

      await apiClient.post('/api/task/run', { prompt: 'hi' });

      const headers = getFetchHeaders();
      expect(headers['Idempotency-Key']).toBeTruthy();
    });

    it('respects a caller-provided Idempotency-Key on a required route', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ok: true }),
      });

      await apiClient.post(
        '/api/agent/execute',
        {},
        { headers: { 'Idempotency-Key': 'caller-key-123' } },
      );

      const headers = getFetchHeaders();
      expect(headers['Idempotency-Key']).toBe('caller-key-123');
    });

    it('does NOT send Idempotency-Key on PUT of a key-less route', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ok: true }),
      });

      await apiClient.put('/api/v1/settings/profile', { theme: 'dark' });

      const headers = getFetchHeaders();
      expect(headers).not.toHaveProperty('Idempotency-Key');
    });
  });
});
