import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./apiClient', () => ({
  apiClient: {
    post: vi.fn(),
  },
}));

import { authService } from './authService';
import { apiClient } from './apiClient';

describe('authService (Native / Zero-Firebase)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('adminLogin posts email and password', async () => {
    (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'ok',
      token: 'admin-jwt-token',
      uid: 'admin-1',
      email: 'admin@supremeai.com',
    });
    const res = await authService.adminLogin('admin@supremeai.com', 'secret');
    expect(apiClient.post).toHaveBeenCalledWith('/api/admin/login', {
      email: 'admin@supremeai.com',
      password: 'secret',
    });
    expect(res.token).toBe('admin-jwt-token');
  });

  it('adminTotpSetup posts to /api/admin/totp-setup', async () => {
    (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      secret: 's3cr3t',
      provisioning_uri: 'otpauth://...',
      recovery_codes: ['code1'],
    });
    const res = await authService.adminTotpSetup();
    expect(apiClient.post).toHaveBeenCalledWith('/api/admin/totp-setup', {});
    expect(res.secret).toBe('s3cr3t');
  });

  it('adminTotpVerify posts otp and remember_browser flag', async () => {
    (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'ok',
      token: 'verified-jwt',
    });
    const res = await authService.adminTotpVerify('123456');
    expect(apiClient.post).toHaveBeenCalledWith('/api/admin/totp-verify', {
      otp: '123456',
      remember_browser: false,
    });
    expect(res.token).toBe('verified-jwt');

    await authService.adminTotpVerify('123456', true);
    expect(apiClient.post).toHaveBeenCalledWith('/api/admin/totp-verify', {
      otp: '123456',
      remember_browser: true,
    });
  });

  it('adminLogout posts to /api/admin/logout', async () => {
    (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await authService.adminLogout();
    expect(apiClient.post).toHaveBeenCalledWith('/api/admin/logout', {});
  });
});
