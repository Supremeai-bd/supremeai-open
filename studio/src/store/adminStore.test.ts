import { describe, it, expect, vi, beforeEach } from 'vitest';
import { eventBus, Events } from '../lib/componentEventBus';

const { adminLogin, adminTotpSetup, adminTotpVerify, adminLogout } = vi.hoisted(() => ({
  adminLogin: vi.fn(),
  adminTotpSetup: vi.fn(),
  adminTotpVerify: vi.fn(),
  adminLogout: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../services/authService', () => ({
  authService: {
    adminLogin,
    adminTotpSetup,
    adminTotpVerify,
    adminLogout,
  },
}));

import { useAdminStore } from './adminStore';
const reset = () =>
  useAdminStore.setState({
    adminAuthenticated: false,
    adminRole: null,
    adminError: '',
    actionStatus: '',
    adminSubTab: 'dashboard',
    adminEmail: '',
    otpRequired: false,
    adminOtp: '',
    totpSetupRequired: false,
    totpSecret: '',
    provisioningUri: '',
  });

const makeJwt = (payloadObj: Record<string, unknown>): string => {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64');
  const payload = Buffer.from(JSON.stringify(payloadObj)).toString('base64');
  return `${header}.${payload}.sig1234567890abcdef`;
};

describe('adminStore (Zero Firebase / Native Auth)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    reset();
  });

  it('sets scalar admin fields', () => {
    useAdminStore.getState().setAdminRole('superadmin');
    useAdminStore.getState().setAdminError('err');
    useAdminStore.getState().setActionStatus('busy');
    useAdminStore.getState().setAdminSubTab('users');
    useAdminStore.getState().setAdminEmail('a@b.com');
    useAdminStore.getState().setOtpRequired(true);
    useAdminStore.getState().setAdminOtp('123456');
    useAdminStore.getState().setTotpSetupRequired(true);
    useAdminStore.getState().setTotpSecret('secret');
    useAdminStore.getState().setProvisioningUri('uri');
    const s = useAdminStore.getState();
    expect(s.adminRole).toBe('superadmin');
    expect(s.adminError).toBe('err');
    expect(s.actionStatus).toBe('busy');
    expect(s.adminSubTab).toBe('users');
    expect(s.adminEmail).toBe('a@b.com');
    expect(s.otpRequired).toBe(true);
    expect(s.adminOtp).toBe('123456');
    expect(s.totpSetupRequired).toBe(true);
    expect(s.totpSecret).toBe('secret');
    expect(s.provisioningUri).toBe('uri');
  });

  it('returns early from login when email/password are missing', async () => {
    await useAdminStore.getState().handleAdminLogin();
    expect(adminLogin).not.toHaveBeenCalled();
  });

  it('records an auth error when login fails', async () => {
    useAdminStore.getState().setAdminEmail('a@b.com');
    adminLogin.mockRejectedValue({
      message: 'bad creds',
    });
    await useAdminStore.getState().handleAdminLogin('pw');
    expect(useAdminStore.getState().adminError).toContain('bad creds');
  });

  it('requires OTP when the backend reports otp_required', async () => {
    useAdminStore.getState().setAdminEmail('a@b.com');
    adminLogin.mockResolvedValue({ status: 'otp_required' });
    await useAdminStore.getState().handleAdminLogin('pw');
    expect(useAdminStore.getState().otpRequired).toBe(true);
  });

  it('starts TOTP setup when backend reports totp_setup_required', async () => {
    useAdminStore.getState().setAdminEmail('a@b.com');
    adminLogin.mockResolvedValue({ status: 'totp_setup_required' });
    adminTotpSetup.mockResolvedValue({ secret: 's3cr3t' });
    await useAdminStore.getState().handleAdminLogin('pw');
    const s = useAdminStore.getState();
    expect(s.totpSetupRequired).toBe(true);
    expect(s.totpSecret).toBe('s3cr3t');
    expect(s.provisioningUri).toContain('otpauth');
  });

  it('authenticates after verifying the TOTP code', async () => {
    useAdminStore.setState({ adminEmail: 'a@b.com', otpRequired: true, adminOtp: '123456' });
    const token = makeJwt({ role: 'admin', exp: Math.floor(Date.now() / 1000) + 3600 });
    adminTotpVerify.mockResolvedValue({ token });
    await useAdminStore.getState().handleAdminLogin('pw');
    const s = useAdminStore.getState();
    expect(s.adminAuthenticated).toBe(true);
    expect(s.adminRole).toBe('admin');
    expect(sessionStorage.getItem('supreme_admin_jwt')).toBe(token);
    expect(localStorage.getItem('supreme_admin_jwt')).toBe(token);
  });

  it('records an error when TOTP verification fails', async () => {
    useAdminStore.setState({ adminEmail: 'a@b.com', otpRequired: true, adminOtp: '000000' });
    adminTotpVerify.mockRejectedValue({ message: 'invalid code' });
    await useAdminStore.getState().handleAdminLogin('pw');
    expect(useAdminStore.getState().adminError).toContain('invalid code');
    expect(useAdminStore.getState().adminAuthenticated).toBe(false);
  });

  it('logs out, clears tokens and emits AUTH_LOGOUT', async () => {
    let emitted = false;
    const handler = () => {
      emitted = true;
    };
    eventBus.on(Events.AUTH_LOGOUT, handler);
    localStorage.setItem('supreme_admin_jwt', 'x');
    sessionStorage.setItem('supreme_admin_jwt', 'x');
    await useAdminStore.getState().handleAdminLogout();
    expect(localStorage.getItem('supreme_admin_jwt')).toBeNull();
    expect(sessionStorage.getItem('supreme_admin_jwt')).toBeNull();
    expect(adminLogout).toHaveBeenCalled();
    expect(emitted).toBe(true);
    expect(useAdminStore.getState().adminAuthenticated).toBe(false);
  });
});
