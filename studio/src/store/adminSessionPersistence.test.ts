import { describe, it, expect, beforeEach } from 'vitest';
import { useAuthStore, AuthStatus } from './authStore';
import { canAccessAdminContext, getAdminJwtRole } from '../auth/identity';
import { clearAuthToken } from '../services/apiClient';

describe('Admin Session Persistence (Issue #495)', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    useAuthStore.setState({
      status: AuthStatus.UNINITIALIZED,
      user: null,
      role: null,
      permissions: [],
    });
  });

  const createMockJwt = (payloadObj: Record<string, unknown>): string => {
    const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
    const payload = btoa(JSON.stringify(payloadObj))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=/g, '');
    return `${header}.${payload}.mock-signature`;
  };

  it('restores a legacy localStorage supreme_admin_jwt on initialize() (Issue #521 keeps legacy reads)', async () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600 * 12; // 12 hours ahead
    const adminJwt = createMockJwt({
      sub: 'admin_123',
      role: 'admin',
      email: 'admin@supremeai.dev',
      exp: futureExp,
    });

    localStorage.setItem('supreme_admin_jwt', adminJwt);

    expect(canAccessAdminContext()).toBe(true);
    expect(getAdminJwtRole()).toBe('admin');

    await useAuthStore.getState().initialize();

    const state = useAuthStore.getState();
    expect(state.status).toBe(AuthStatus.LOGGED_IN);
    expect(state.role).toBe('admin');
    expect(state.user?.email).toBe('admin@supremeai.dev');
    expect(state.user?.id).toBe('admin_123');
  });

  it('restores admin session from sessionStorage supreme_admin_jwt on initialize()', async () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600 * 24;
    const adminJwt = createMockJwt({
      sub: 'admin_session_456',
      role: 'admin',
      email: 'chief@supremeai.dev',
      exp: futureExp,
    });

    sessionStorage.setItem('supreme_admin_jwt', adminJwt);

    expect(canAccessAdminContext()).toBe(true);

    await useAuthStore.getState().initialize();

    const state = useAuthStore.getState();
    expect(state.status).toBe(AuthStatus.LOGGED_IN);
    expect(state.role).toBe('admin');
    expect(state.user?.email).toBe('chief@supremeai.dev');
  });

  it('does not purge unexpired admin token when clearAuthToken() is called', () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600 * 24;
    const adminJwt = createMockJwt({
      sub: 'admin_keep_active',
      role: 'admin',
      exp: futureExp,
    });

    localStorage.setItem('supremeai_auth_token', 'user_expired_tok');
    localStorage.setItem('supreme_admin_jwt', adminJwt);
    sessionStorage.setItem('supreme_admin_jwt', adminJwt);

    clearAuthToken();

    // User token is cleared
    expect(localStorage.getItem('supremeai_auth_token')).toBeNull();
    // Valid admin token is safely preserved
    expect(localStorage.getItem('supreme_admin_jwt')).toBe(adminJwt);
    expect(sessionStorage.getItem('supreme_admin_jwt')).toBe(adminJwt);
    expect(canAccessAdminContext()).toBe(true);
  });

  it('purges expired admin token and returns false for canAccessAdminContext', () => {
    const pastExp = Math.floor(Date.now() / 1000) - 3600; // 1 hour expired
    const expiredJwt = createMockJwt({
      sub: 'admin_expired',
      role: 'admin',
      exp: pastExp,
    });

    localStorage.setItem('supreme_admin_jwt', expiredJwt);
    sessionStorage.setItem('supreme_admin_jwt', expiredJwt);

    expect(canAccessAdminContext()).toBe(false);
    expect(getAdminJwtRole()).toBeNull();

    clearAuthToken();

    expect(localStorage.getItem('supreme_admin_jwt')).toBeNull();
    expect(sessionStorage.getItem('supreme_admin_jwt')).toBeNull();
  });
});
