import { describe, it, expect, beforeEach, vi } from 'vitest';
import { resolveLandingPath, readAdminJwtClaims, getAdminJwtRole, canAccessAdminContext, getCanonicalRole } from './identity';

vi.mock('../store/authStore', () => ({
  useAuthStore: {
    getState: vi.fn(),
    setState: vi.fn(),
  },
}));

const { useAuthStore } = await import('../store/authStore');

function setAdminJwt(payload: Record<string, unknown> | null) {
  if (!payload) {
    sessionStorage.removeItem('supreme_admin_jwt');
    return;
  }
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url');
  sessionStorage.setItem('supreme_admin_jwt', `${header}.${body}.sig`);
}

describe('identity', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.clearAllMocks();
  });

  describe('resolveLandingPath', () => {
    it('redirects guest to /login', () => {
      expect(resolveLandingPath(false)).toBe('/login');
    });

    it('redirects authenticated admin to /admin', () => {
      (useAuthStore.getState as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ role: 'admin' });
      expect(resolveLandingPath(true)).toBe('/admin');
    });

    it('redirects authenticated user to /workspace', () => {
      (useAuthStore.getState as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ role: 'user' });
      expect(resolveLandingPath(true)).toBe('/workspace');
    });
  });

  describe('readAdminJwtClaims', () => {
    it('returns null when no token is stored', () => {
      expect(readAdminJwtClaims()).toBeNull();
    });

    it('decodes a valid admin JWT', () => {
      setAdminJwt({ role: 'admin', sub: 'u1' });
      const claims = readAdminJwtClaims();
      expect(claims?.role).toBe('admin');
      expect(claims?.sub).toBe('u1');
    });

    it('returns null for malformed tokens', () => {
      sessionStorage.setItem('supreme_admin_jwt', 'not-a-jwt');
      expect(readAdminJwtClaims()).toBeNull();
    });
  });

  describe('getAdminJwtRole', () => {
    it('returns null when no admin JWT exists', () => {
      expect(getAdminJwtRole()).toBeNull();
    });

    it('normalizes the role from admin JWT', () => {
      setAdminJwt({ role: 'superadmin' });
      expect(getAdminJwtRole()).toBe('admin');
    });

    it('returns null for expired tokens', () => {
      setAdminJwt({ role: 'admin', exp: Math.floor(Date.now() / 1000) - 60 });
      expect(getAdminJwtRole()).toBeNull();
    });
  });

  describe('canAccessAdminContext', () => {
    it('returns true when store role is admin', () => {
      (useAuthStore.getState as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ role: 'admin' });
      expect(canAccessAdminContext()).toBe(true);
    });

    it('returns true when admin JWT role is admin', () => {
      (useAuthStore.getState as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ role: null });
      setAdminJwt({ role: 'admin' });
      expect(canAccessAdminContext()).toBe(true);
    });

    it('returns false when neither source grants admin', () => {
      (useAuthStore.getState as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ role: 'user' });
      setAdminJwt({ role: 'user' });
      expect(canAccessAdminContext()).toBe(false);
    });
  });

  describe('getCanonicalRole', () => {
    it('prefers the store role over the JWT role', () => {
      (useAuthStore.getState as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ role: 'admin' });
      setAdminJwt({ role: 'user' });
      expect(getCanonicalRole()).toBe('admin');
    });

    it('falls back to JWT role when store role is null', () => {
      (useAuthStore.getState as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ role: null });
      setAdminJwt({ role: 'admin' });
      expect(getCanonicalRole()).toBe('admin');
    });
  });
});
