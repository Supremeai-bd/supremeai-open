/**
 * Tests for tokenStorage.ts
 *
 * Tests cover:
 * - Token save/load/clear (sessionStorage only — never localStorage)
 * - Legacy localStorage migration (one-time sweep on read)
 * - Admin token separate storage (supreme_admin_jwt) and isolation
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock sessionStorage and localStorage
const mockSessionStorage: Record<string, string> = {};
const mockLocalStorage: Record<string, string> = {};

beforeEach(() => {
  // Clear mocks
  Object.keys(mockSessionStorage).forEach(k => delete mockSessionStorage[k]);
  Object.keys(mockLocalStorage).forEach(k => delete mockLocalStorage[k]);

  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => mockSessionStorage[key] ?? null,
    setItem: (key: string, val: string) => { mockSessionStorage[key] = val; },
    removeItem: (key: string) => { delete mockSessionStorage[key]; },
    clear: () => { Object.keys(mockSessionStorage).forEach(k => delete mockSessionStorage[k]); },
  });

  vi.stubGlobal('localStorage', {
    getItem: (key: string) => mockLocalStorage[key] ?? null,
    setItem: (key: string, val: string) => { mockLocalStorage[key] = val; },
    removeItem: (key: string) => { delete mockLocalStorage[key]; },
    clear: () => { Object.keys(mockLocalStorage).forEach(k => delete mockLocalStorage[k]); },
  });
});

describe('tokenStorage', () => {
  it('should be importable', async () => {
    const mod = await import('./tokenStorage');
    expect(mod).toBeDefined();
  });

  it('should save and load user token from sessionStorage', async () => {
    const { setUserToken, getUserToken } = await import('./tokenStorage');
    const testToken = 'test-jwt-token-12345';

    setUserToken(testToken);
    expect(getUserToken()).toBe(testToken);
    // Should be in sessionStorage, NOT localStorage
    expect(sessionStorage.getItem('supremeai_auth_token')).toBe(testToken);
    expect(localStorage.getItem('supremeai_auth_token')).toBeNull();
  });

  it('should clear token on clearUserToken()', async () => {
    const { setUserToken, getUserToken, clearUserToken } = await import('./tokenStorage');
    setUserToken('test-token');
    expect(getUserToken()).toBeTruthy();

    clearUserToken();
    expect(getUserToken()).toBeNull();
    expect(sessionStorage.getItem('supremeai_auth_token')).toBeNull();
  });

  it('should sweep legacy localStorage token into sessionStorage on first read', async () => {
    const { getUserToken } = await import('./tokenStorage');
    // Simulate a legacy deployment's token in localStorage
    mockLocalStorage['supremeai_auth_token'] = 'legacy-token';

    // First read migrates: token returned, copied to sessionStorage,
    // and removed from localStorage (one-time sweep, FE-04 / issue #521).
    expect(getUserToken()).toBe('legacy-token');
    expect(sessionStorage.getItem('supremeai_auth_token')).toBe('legacy-token');
    expect(localStorage.getItem('supremeai_auth_token')).toBeNull();
    // The token remains readable after the sweep (session continuity).
    expect(getUserToken()).toBe('legacy-token');
  });

  it('should keep admin token isolated from the user token', async () => {
    const { setUserToken, setAdminToken, getAdminToken, clearAdminToken, getUserToken } =
      await import('./tokenStorage');

    setUserToken('user-jwt');
    setAdminToken('admin-jwt');
    // Admin token lives under its own key (supreme_admin_jwt), separate
    // from the user session token (supremeai_auth_token).
    expect(getAdminToken()).toBe('admin-jwt');
    expect(getUserToken()).toBe('user-jwt');
    expect(sessionStorage.getItem('supreme_admin_jwt')).toBe('admin-jwt');

    clearAdminToken();
    expect(getAdminToken()).toBeNull();
    // Clearing the admin token must not touch the user session.
    expect(getUserToken()).toBe('user-jwt');
  });
});
