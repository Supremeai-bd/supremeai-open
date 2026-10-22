import { create } from 'zustand';
import { authService } from '../services/authService';
import { updateTokenCache } from '../services/apiClient';
import { clearAdminToken, getAdminToken, setAdminToken } from '../services/tokenStorage';
import { LEGACY_ADMIN_TOKEN_KEY } from './authStore';
import { eventBus, Events } from '../lib/componentEventBus';

const decodeJwt = (token: string): Record<string, unknown> | null => {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
    }).join(''));
    const decoded = JSON.parse(jsonPayload);

    if (!decoded || typeof decoded !== 'object') {
      throw new Error('Decoded JWT payload is not a valid object');
    }

    return decoded;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } catch (e: any) {
    console.warn("⚠️ [JWT_DECODE_ERROR]: Failed to safely parse admin JWT token.", {
      error_message: e?.message || 'Malformed JWT structure',
      timestamp: new Date().toISOString(),
    });
    return null;
  }
};

const buildProvisioningUri = (email: string, secret: string): string =>
  `otpauth://totp/SupremeAI:${encodeURIComponent(email)}?secret=${secret}&issuer=SupremeAI&digits=6&period=30`;

const persistAdminToken = (token: unknown): token is string => {
  if (typeof token !== 'string' || token.trim().length < 20) return false;
  setAdminToken(token);
  updateTokenCache(token);
  return true;
};

interface AdminState {
  adminAuthenticated: boolean;
  adminRole: string | null;
  setAdminRole: (val: string | null) => void;
  adminError: string;
  setAdminError: (val: string) => void;
  handleAdminLogin: (password?: string) => Promise<void>;
  handleAdminLogout: () => void;
  actionStatus: string;
  setActionStatus: (val: string) => void;
  adminSubTab: string;
  setAdminSubTab: (tab: string) => void;
  adminEmail: string;
  setAdminEmail: (val: string) => void;
  otpRequired: boolean;
  setOtpRequired: (val: boolean) => void;
  adminOtp: string;
  setAdminOtp: (val: string) => void;
  rememberBrowser: boolean;
  setRememberBrowser: (val: boolean) => void;
  totpSetupRequired: boolean;
  setTotpSetupRequired: (val: boolean) => void;
  totpSecret: string;
  setTotpSecret: (val: string) => void;
  provisioningUri: string;
  setProvisioningUri: (val: string) => void;
  recoveryCodes: string[];
  recoveryCode: string;
  setRecoveryCode: (val: string) => void;
  recoverTotp: () => Promise<void>;
  resetTotpSetup: () => Promise<void>;
}

const getInitialAdminToken = (): string | null => {
  if (typeof window === 'undefined') return null;
  try {
    return getAdminToken();
  } catch (err) {
    console.warn('[adminStore] initial admin token read failed, using fallback:', err);
    return null;
  }
};

const initialToken = getInitialAdminToken();
const initialDecoded = initialToken ? decodeJwt(initialToken) : null;
const isInitialTokenValid = Boolean(
  initialDecoded &&
  typeof initialDecoded.exp === 'number' &&
  initialDecoded.exp * 1000 > Date.now()
);

if (isInitialTokenValid && initialToken) {
  updateTokenCache(initialToken);
}

export const useAdminStore = create<AdminState>((set, get) => ({
  adminAuthenticated: isInitialTokenValid,
  adminRole: isInitialTokenValid && initialDecoded?.role === 'admin' ? 'admin' : null,
  setAdminRole: (val) => set({ adminRole: val }),
  adminError: '',
  setAdminError: (val) => set({ adminError: val }),
  actionStatus: '',
  setActionStatus: (val) => set({ actionStatus: val }),
  adminSubTab: 'dashboard',
  setAdminSubTab: (tab) => set({ adminSubTab: tab }),
  adminEmail: '',
  setAdminEmail: (val) => set({ adminEmail: val }),
  otpRequired: false,
  setOtpRequired: (val) => set({ otpRequired: val }),
  adminOtp: '',
  setAdminOtp: (val) => set({ adminOtp: val }),
  rememberBrowser: false,
  setRememberBrowser: (val) => set({ rememberBrowser: val }),
  totpSetupRequired: false,
  setTotpSetupRequired: (val) => set({ totpSetupRequired: val }),
  totpSecret: '',
  setTotpSecret: (val) => set({ totpSecret: val }),
  provisioningUri: '',
  setProvisioningUri: (val) => set({ provisioningUri: val }),
  recoveryCodes: [],
  recoveryCode: '',
  setRecoveryCode: (val) => set({ recoveryCode: val }),
  recoverTotp: async () => {
    set({ adminError: 'TOTP recovery not available in native auth mode.' });
  },
  handleAdminLogin: async (password?: string) => {
    const { adminEmail, otpRequired, adminOtp, rememberBrowser } = get();
    const cleanEmail = adminEmail.trim();
    const cleanPassword = password?.trim() || '';

    if (!otpRequired && (!cleanEmail || !cleanPassword)) return;
    set({ adminError: '' });

    try {
      if (!otpRequired) {
        // Step 1+2: Native backend login (no Firebase)
        const data = await authService.adminLogin(cleanEmail, cleanPassword);

        if (data.status === 'trusted_browser' && persistAdminToken(data.token)) {
          const decoded = decodeJwt(data.token);
          set({ adminAuthenticated: true, adminRole: decoded?.role === 'admin' ? 'admin' : null });
          eventBus.emit(Events.AUTH_LOGIN, { source: 'admin_store', timestamp: Date.now() });
          return;
        }

        if (data.status === 'otp_required') {
          set({ otpRequired: true });
        } else if (data.status === 'totp_setup_required') {
          try {
            const setupData = await authService.adminTotpSetup();
            set({
              totpSetupRequired: true,
              otpRequired: true,
              totpSecret: setupData.secret,
              recoveryCodes: setupData.recovery_codes || [],
              provisioningUri: setupData.provisioning_uri || buildProvisioningUri(cleanEmail, setupData.secret || '')
            });
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          } catch (setupErr: any) {
            const errStr = typeof setupErr?.message === 'string' ? setupErr.message : 'Failed to setup TOTP.';
            set({ adminError: errStr });
          }
        } else if (persistAdminToken(data.token)) {
            const decoded = decodeJwt(data.token);
            if (!decoded) {
              set({ adminError: 'Authentication token is invalid. Please sign in again.' });
              return;
            }
            set({ adminAuthenticated: true, adminRole: decoded?.role === 'admin' ? 'admin' : null });
            eventBus.emit(Events.AUTH_LOGIN, { source: 'admin_store', timestamp: Date.now() });
        } else {
          set({ adminError: 'Not authorized as admin.' });
        }
      } else {
        // Step 3: Verify TOTP (native)
        try {
          const data = await authService.adminTotpVerify(adminOtp.trim(), rememberBrowser);
          if (persistAdminToken(data.token)) {
            const decoded = decodeJwt(data.token);
            if (decoded && typeof decoded.role === 'string') {
              set({ adminRole: decoded.role });
            }
          } else {
            set({ adminError: 'Authentication token missing. Please sign in again.' });
            return;
          }
          
          eventBus.emit(Events.AUTH_LOGIN, {
            source: 'admin_store',
            timestamp: Date.now()
          });
          
          set({ adminAuthenticated: true, otpRequired: false, totpSetupRequired: false, adminOtp: '' });
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
        } catch (verifyErr: any) {
          const errStr = typeof verifyErr?.message === 'string' ? verifyErr.message : 'Invalid verification code.';
          set({ adminError: errStr });
        }
      }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      const msg = err && typeof err === 'object' && err.message ? String(err.message) : (typeof err === 'object' ? JSON.stringify(err) : String(err));
      set({ adminError: 'Connection failed: ' + msg });
    }
  },
  handleAdminLogout: async () => {
    try {
      await authService.adminLogout();
      localStorage.removeItem(LEGACY_ADMIN_TOKEN_KEY);
      clearAdminToken();
      updateTokenCache(null);

      eventBus.emit(Events.AUTH_LOGOUT, {
        source: 'admin_store',
        timestamp: Date.now()
      });
    } catch(e) {
      console.error('Logout failed:', e);
    }
    set({ adminAuthenticated: false, adminRole: null, otpRequired: false, adminOtp: '', adminError: '', totpSetupRequired: false, totpSecret: '', provisioningUri: '' });
  },
  resetTotpSetup: async () => {
    set({ adminError: 'TOTP reset not available in native auth mode.' });
  },
}));
