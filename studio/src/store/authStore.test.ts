import { describe, it, expect, vi, beforeEach } from 'vitest';

const { postMock, getMock, updateTokenCache } = vi.hoisted(() => ({
  postMock: vi.fn(),
  getMock: vi.fn(),
  updateTokenCache: vi.fn(),
}));

vi.mock('../services/apiClient', () => ({
  apiClient: {
    post: (...args: unknown[]) => postMock(...args),
    get: (...args: unknown[]) => getMock(...args),
  },
  updateTokenCache,
}));

import { useAuthStore, AuthStatus } from './authStore';

const token = (payload: Record<string, unknown>) =>
  `header.${Buffer.from(JSON.stringify(payload)).toString('base64').replace(/=/g, '')}.sig`;

describe('authStore', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    useAuthStore.setState({ status: AuthStatus.UNINITIALIZED, user: null });
  });

  it('logs in, stores the token in sessionStorage (Issue #521) and sets the user', async () => {
    postMock.mockResolvedValue({ access_token: 'tok', user_id: 'u1' });
    await useAuthStore.getState().login('a@b.com', 'pw');
    expect(sessionStorage.getItem('supremeai_auth_token')).toBe('tok');
    expect(localStorage.getItem('supremeai_auth_token')).toBeNull();
    expect(updateTokenCache).toHaveBeenCalledWith('tok');
    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_IN);
    expect(useAuthStore.getState().user?.email).toBe('a@b.com');
  });

  it('registers and logs the user in', async () => {
    postMock.mockResolvedValue({ access_token: 'tok2', user_id: 'u2' });
    await useAuthStore.getState().register('a@b.com', 'Alice', 'pw');
    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_IN);
    expect(useAuthStore.getState().user?.name).toBe('Alice');
  });

  it('propagates login errors', async () => {
    postMock.mockRejectedValue(new Error('bad creds'));
    await expect(useAuthStore.getState().login('a@b.com', 'pw')).rejects.toThrow('bad creds');
    expect(useAuthStore.getState().status).toBe(AuthStatus.UNINITIALIZED);
  });

  it('logs out and clears persisted state', async () => {
    postMock.mockResolvedValue({ access_token: 'tok', user_id: 'u1' });
    await useAuthStore.getState().login('a@b.com', 'pw');
    useAuthStore.getState().logout();
    expect(sessionStorage.getItem('supremeai_auth_token')).toBeNull();
    expect(localStorage.getItem('supremeai_auth_token')).toBeNull();
    expect(updateTokenCache).toHaveBeenCalledWith(null);
    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_OUT);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('initializes as logged out when no token exists', async () => {
    await useAuthStore.getState().initialize();
    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_OUT);
  });

  it('restores a cookie-only session via /me when no localStorage token exists', async () => {
    // Production-readiness plan, item 3b: httpOnly-cookie session restore
    getMock.mockResolvedValue({ email: 'cookie@x.com', user_id: 'u-cookie', role: 'user' });
    await useAuthStore.getState().initialize();
    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_IN);
    expect(useAuthStore.getState().user?.email).toBe('cookie@x.com');
    expect(getMock).toHaveBeenCalledWith('/api/v1/auth/me');
    expect(localStorage.getItem('supremeai_auth_token')).toBeNull();
    expect(sessionStorage.getItem('supremeai_auth_token')).toBeNull();
  });

  it('stays logged out when neither token nor cookie session exists', async () => {
    getMock.mockRejectedValue({ status: 401 });
    await useAuthStore.getState().initialize();
    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_OUT);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('initializes optimistically from a valid token and refreshes via /me', async () => {
    const tok = token({ email: 'me@x.com', name: 'Me', sub: 'u9' });
    localStorage.setItem('supremeai_auth_token', tok);
    getMock.mockResolvedValue({ email: 'me@x.com', user_id: 'u9', role: 'admin' });
    await useAuthStore.getState().initialize();
    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_IN);
    expect(useAuthStore.getState().user?.email).toBe('me@x.com');
  });

  it('logs out on initialize when /me returns 401', async () => {
    const tok = token({ email: 'me@x.com' });
    localStorage.setItem('supremeai_auth_token', tok);
    getMock.mockRejectedValue({ status: 401 });
    await useAuthStore.getState().initialize();
    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_OUT);
  });

  it('keeps the session on a transient initialize error', async () => {
    const tok = token({ email: 'me@x.com', name: 'Me' });
    sessionStorage.setItem('supremeai_auth_token', tok);
    getMock.mockRejectedValue({ status: 500 });
    await useAuthStore.getState().initialize();
    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_IN);
    expect(sessionStorage.getItem('supremeai_auth_token')).toBe(tok);
  });

  it('migrates a legacy localStorage token into sessionStorage and sweeps it (Issue #521)', async () => {
    const tok = token({ email: 'me@x.com', name: 'Me', sub: 'u9' });
    localStorage.setItem('supremeai_auth_token', tok);
    getMock.mockRejectedValue({ status: 500 });
    await useAuthStore.getState().initialize();
    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_IN);
    expect(sessionStorage.getItem('supremeai_auth_token')).toBe(tok);
    expect(localStorage.getItem('supremeai_auth_token')).toBeNull();
  });

  it('restores the persisted profile after a browser restart', async () => {
    const tok = token({ email: 'me@x.com', name: 'Me', sub: 'u9' });
    sessionStorage.setItem('supremeai_auth_token', tok);
    localStorage.setItem('supremeai_auth_user', JSON.stringify({
      id: 'u9', email: 'me@x.com', name: 'Me', avatarUrl: 'avatar',
    }));
    getMock.mockRejectedValue(new Error('backend temporarily unavailable'));

    await useAuthStore.getState().initialize();

    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_IN);
    expect(useAuthStore.getState().user).toMatchObject({ id: 'u9', email: 'me@x.com', name: 'Me' });
    expect(sessionStorage.getItem('supremeai_auth_token')).toBe(tok);
  });

  it('does not clear a session for a non-authenticated request failure', async () => {
    const tok = token({ email: 'me@x.com' });
    localStorage.setItem('supremeai_auth_token', tok);
    getMock.mockRejectedValue({ status: 403 });
    await useAuthStore.getState().initialize();
    expect(useAuthStore.getState().status).toBe(AuthStatus.LOGGED_OUT);
  });
});
