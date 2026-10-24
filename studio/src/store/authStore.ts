import { create } from 'zustand';
import { apiClient, updateTokenCache } from '../services/apiClient';
import { clearUserToken, getUserToken, setUserToken } from '../services/tokenStorage';
import { isRole, normalizeRole, type Role } from '../config/permissions';
import { useCustomerStore } from './customerStore';
import { clearLocalDataScope, setLocalDataScope } from './localFirstDb';

// বাংলা মন্তব্য: erasableSyntaxOnly সক্রিয় থাকায় enum-এর বদলে const object + union type ব্যবহার করা হচ্ছে
export const AuthStatus = {
  UNINITIALIZED: 'uninitialized',
  LOGGED_OUT: 'loggedOut',
  LOGGED_IN: 'loggedIn',
} as const;

export type AuthStatus = (typeof AuthStatus)[keyof typeof AuthStatus];

interface UserProfile {
  id: string;
  email: string;
  name: string;
  avatarUrl?: string;
}

// বাংলা মন্তব্য: Single-frontend migration (roadmap Phase 2) — authStore এখন canonical
// identity/session authority। role শুধুমাত্র backend response (login/register//auth/me)
// থেকে resolve হয় — localStorage role key, URL বা UI state থেকে কখনোই নয়।
interface AuthState {
  status: AuthStatus;
  user: UserProfile | null;
  /** Canonical role resolved from trusted backend state (never client-computed). */
  role: Role | null;
  /** Backend-provided permission strings; empty/unknown = defer to backend RBAC. */
  permissions: string[];
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, name: string, password: string) => Promise<void>;
  logout: () => void;
  initialize: () => Promise<void>;
}

// বাংলা (Issue #521 / FE-04): TOKEN_KEY আর সরাসরি localStorage-এ লেখা হয় না —
// টোকেন এখন services/tokenStorage.ts (sessionStorage + in-memory) দিয়ে যায়।
const USER_KEY = 'supremeai_auth_user';

/**
 * বাংলা: বাসি (stale) admin token key — legacy ডুপ্লিকেট। যেকোনো session পরিষ্কারের সময়
 * এটিও মুছে ফেলা হয় যাতে পুরোনো সাইন-ইন অবস্থা কোথাও জমা না থাকে।
 */
export const LEGACY_ADMIN_TOKEN_KEY = 'adminToken';

/**
 * বাংলা: একক সেশন-পরিষ্কার হেল্পার। apiClient (401 handler) ও দুই store-এর logout —
 * সবাই এটিই ব্যবহার করবে, যাতে token/cache/UI state কখনো একে অপরের থেকে সরে না যায়।
 * NOTE: এটি শুধু canonical USER session পরিষ্কার করে; admin step-up state
 * (supreme_admin_jwt + adminStore) আলাদা — handleAdminLogout তা-ই করে।
 */
export function clearCanonicalSession(): void {
  try {
    // Issue #521: token now lives in sessionStorage — clearUserToken sweeps both
    // storage tiers (sessionStorage + legacy localStorage migration sweep).
    clearUserToken();
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(LEGACY_ADMIN_TOKEN_KEY);
  } catch (e) {
    // localStorage unavailable (SSR / incognito) — নীরবে এগিয়ে যাওয়া।
    console.debug('clearCanonicalSession: localStorage unavailable', e);
  }
  updateTokenCache(null);
  persistUser(null);
  useAuthStore.setState({ status: AuthStatus.LOGGED_OUT, user: null, role: null, permissions: [] });
}

// বাংলা মন্তব্য: JWT payload নিরাপদে ডিকোড করা হয় (reload-এ token থেকেই ইউজার প্রোফাইল রিস্টোর করার জন্য)।
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split('.')[1];
    if (!part) return null;
    const base64 = part.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload) as Record<string, unknown>;
  } catch (e) {
    console.debug('decodeJwtPayload: failed to decode token', e);
    return null;
  }
}

function persistUser(user: UserProfile | null) {
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(USER_KEY);
  }
}

function restoreUser(): UserProfile | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as UserProfile;
    if (!parsed || typeof parsed !== 'object' || typeof parsed.email !== 'string') return null;
    return parsed;
  } catch (e) {
    console.debug('restoreUser: failed to restore user from storage', e);
    return null;
  }
}

// FINAL-TEST PRIVACY FIX: the user's email used to be sent to
// ui-avatars.com on every login/register/session-restore. The avatar is now a
// locally generated SVG data URL — no PII ever leaves the browser.
const AVATAR_PALETTE = ['#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316'];
const avatarUrl = (label: string) => {
  const name = (label || '?').trim();
  const initials = name.slice(0, 2).toUpperCase() || '?';
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  const color = AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><rect width="128" height="128" rx="64" fill="${color}"/><text x="64" y="64" dy="0.36em" text-anchor="middle" font-family="system-ui, sans-serif" font-size="52" font-weight="600" fill="#ffffff">${initials}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
};

export const useAuthStore = create<AuthState>((set) => ({
  status: AuthStatus.UNINITIALIZED,
  user: null,
  role: null,
  permissions: [],

  login: async (email, password) => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const response = await apiClient.post<any>('/api/v1/auth/login', {
        username: email,
        password: password
      });

      const token = response.access_token;
      // Issue #521 (FE-04): sessionStorage instead of localStorage — token no
      // longer survives the browser session. In-memory cache keeps this tab's
      // requests authenticated.
      setUserToken(token);
      updateTokenCache(token);

      const user: UserProfile = {
        id: response.user_id,
        email,
        name: email.split('@')[0], // Backend does not return name right now
        avatarUrl: avatarUrl(email),
      };
      persistUser(user);
      setLocalDataScope(user.id);

      set({
        status: AuthStatus.LOGGED_IN,
        user,
        // বাংলা: backend primary_role ("admin" | "user") — canonical role এখান থেকেই আসে।
        role: isRole(response.role) ? response.role : 'user',
        permissions: Array.isArray(response.permissions) ? response.permissions : [],
      });
    } catch (error) {
      console.error("Login failed:", error);
      throw error;
    }
  },

  register: async (email, name, password) => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const response = await apiClient.post<any>('/api/v1/auth/register', {
        username: email,
        password: password,
        name: name
      });

      const token = response.access_token;
      // Issue #521 (FE-04): sessionStorage instead of localStorage.
      setUserToken(token);
      updateTokenCache(token);

      const user: UserProfile = {
        id: response.user_id,
        email,
        name,
        avatarUrl: avatarUrl(name),
      };
      persistUser(user);
      setLocalDataScope(user.id);

      set({
        status: AuthStatus.LOGGED_IN,
        user,
        role: isRole(response.role) ? response.role : 'user',
        permissions: Array.isArray(response.permissions) ? response.permissions : [],
      });
    } catch (error) {
      console.error("Registration failed:", error);
      throw error;
    }
  },

  logout: () => {
    // বাংলা: unified clearing — token + cached profile + role/permissions একসাথে।
    // admin step-up state ইচ্ছাকৃতভাবে অক্ষত থাকে (সেটি আলাদা identity flow);
    // UI-তে admin context logout আলাদাভাবে handleAdminLogout() ডাকে।
    // Issue #521: clearUserToken sessionStorage + legacy localStorage দুটোই পরিষ্কার করে।
    clearUserToken();
    localStorage.removeItem(LEGACY_ADMIN_TOKEN_KEY);
    updateTokenCache(null);
    persistUser(null);
    // SECURITY FIX (audit P-7): clear customerStore to prevent PII leakage
    // between users on shared devices (profile, projects, chat history).
    useCustomerStore.getState().clearSession();
    void clearLocalDataScope();
    set({ status: AuthStatus.LOGGED_OUT, user: null, role: null, permissions: [] });
  },

  initialize: async () => {
    // Issue #521: read via tokenStorage — sessionStorage first, legacy
    // localStorage entries are migrated (and swept) on first read.
    const token = getUserToken();
    const adminToken = typeof window !== 'undefined'
      ? (sessionStorage.getItem('supreme_admin_jwt') || localStorage.getItem('supreme_admin_jwt'))
      : null;

    if (!token) {
      // 🛡️ ISSUE #495: যদি ইউজার টোকেন না থাকে কিন্তু বৈধ আন-এক্সপায়ার্ড admin JWT থাকে,
      // তবে সেশনকে অ্যাডমিন হিসেবে পুনরুদ্ধার করতে হবে (রিলোড ও ট্যাব নেভিগেশনে auto-logout ফিক্স)।
      if (adminToken) {
        const adminPayload = decodeJwtPayload(adminToken);
        const isAdminValid = Boolean(
          adminPayload &&
          adminPayload.role === 'admin' &&
          typeof adminPayload.exp === 'number' &&
          adminPayload.exp * 1000 > Date.now()
        );

        if (isAdminValid) {
          updateTokenCache(adminToken);
          const adminEmail = typeof adminPayload?.email === 'string' && adminPayload.email ? adminPayload.email : 'admin@supremeai.dev';
          const adminName = typeof adminPayload?.name === 'string' && adminPayload.name ? adminPayload.name : adminEmail.split('@')[0];
          const adminUser: UserProfile = {
            id: typeof adminPayload?.sub === 'string' ? adminPayload.sub : 'admin',
            email: adminEmail,
            name: adminName,
            avatarUrl: avatarUrl(adminEmail),
          };
          persistUser(adminUser);
          set({
            status: AuthStatus.LOGGED_IN,
            user: adminUser,
            role: 'admin',
            permissions: ['*'],
          });
          return;
        }
      }

      // ── Cookie-based session restore (production-readiness plan, item 3b) ──
      // বাংলা: localStorage টোকেন না থাকলেও httpOnly cookie-ভিত্তিক সেশন থাকতে
      // পারে (login এখন দুই মোডেই cookie সেট করে)। credentials: 'include' সহ
      // /auth/me কল করে cookie-session detect করা হয় — থাকলে সেশন রিস্টোর,
      // না থাকলে আগের মতোই LOGGED_OUT। Dual-mode transition (breaking change নয়)।
      updateTokenCache(null);
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const response = await apiClient.get<any>('/api/v1/auth/me');
        const cookieEmail = response.email || response.username || 'user@supremeai.dev';
        const cookieUser: UserProfile = {
          id: response.user_id || '',
          email: cookieEmail,
          name: response.name || cookieEmail.split('@')[0],
          avatarUrl: avatarUrl(cookieEmail),
        };
        persistUser(cookieUser);
        set({
          status: AuthStatus.LOGGED_IN,
          user: cookieUser,
          role: isRole(response.role) ? response.role : normalizeRole(response.role) ?? 'user',
          permissions: Array.isArray(response.permissions) ? response.permissions : [],
        });
        if (import.meta.env.DEV) {
          console.debug('Session restored from httpOnly cookie (no localStorage token)');
        }
      } catch {
        // বাংলা: cookie-session নেই বা মেয়াদ শেষ — স্বাভাবিক logged-out অবস্থা।
        persistUser(null);
        set({ status: AuthStatus.LOGGED_OUT, user: null });
      }
      return;
    }

    updateTokenCache(token);

    // বাংলা মন্তব্য: Optimistic restore — reload-এ নেটওয়ার্ক রেসপন্সের জন্য অপেক্ষা না করেই
    // token + cached profile দিয়ে সেশন পুনরুদ্ধার করা হয় (logout-on-reload ফিক্স)।
    const cachedUser = restoreUser();
    const payload = decodeJwtPayload(token);
    const payloadEmail =
      typeof payload?.email === 'string' && payload.email ? payload.email : '';
    const payloadName =
      typeof payload?.name === 'string' && payload.name
        ? payload.name
        : payloadEmail
          ? payloadEmail.split('@')[0]
          : 'User';

    const optimisticUser: UserProfile = cachedUser ?? {
      id: typeof payload?.sub === 'string' ? payload.sub : '',
      email: payloadEmail || 'user@supremeai.dev',
      name: payloadName,
      avatarUrl: avatarUrl(payloadEmail || payloadName),
    };

    // বাংলা: JWT payload-এর role claim থাকলে তা optimistic role — পরে /auth/me দিয়ে verify হয়।
    // এটি client-computed privilege নয় — backend-ই signed token-এ role বসায়।
    const optimisticRole = normalizeRole(payload?.role) ?? normalizeRole(cachedUser && (cachedUser as UserProfile & { role?: string }).role) ?? 'user';

    set({ status: AuthStatus.LOGGED_IN, user: optimisticUser, role: optimisticRole });

    // বাংলা মন্তব্য: E2E smoke test token হলে ব্যাকগ্রাউন্ড নেটওয়ার্ক ভ্যালিডেশন স্কিপ করা হবে
    if (token === 'demo-token' || (typeof window !== 'undefined' && (window as unknown as { __E2E_MOCK__?: boolean }).__E2E_MOCK__)) {
      return;
    }

    // বাংলা মন্তব্য: ব্যাকগ্রাউন্ডে token ভ্যালিডেট করা হয় — শুধুমাত্র নিশ্চিত 401/403-এ
    // logout হবে; নেটওয়ার্ক/কোল্ড-স্টার্ট/5xx এরর হলে সেশন অক্ষত থাকে।
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const response = await apiClient.get<any>('/api/v1/auth/me');
      const verifiedEmail = response.email || response.username || optimisticUser.email;
      const freshUser: UserProfile = {
        id: response.user_id || optimisticUser.id,
        email: verifiedEmail,
        // বাংলা: আগে response.role display-name fallback হিসেবে ভুল ব্যবহৃত হতো —
        // এখন role আলাদা state হিসেবে store হয়, name থাকে name।
        name: response.name || optimisticUser.name,
        avatarUrl: avatarUrl(verifiedEmail || optimisticUser.name),
      };
      persistUser(freshUser);
      set({
        status: AuthStatus.LOGGED_IN,
        user: freshUser,
        // বাংলা: verified canonical role — backend-ই source of truth।
        role: isRole(response.role) ? response.role : normalizeRole(response.role) ?? optimisticRole,
        permissions: Array.isArray(response.permissions) ? response.permissions : [],
      });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      const status = error?.status as number | undefined;
      if (status === 401 || status === 403) {
        // বাংলা মন্তব্য: Token সত্যিই invalid/revoked — শুধুমাত্র এই ক্ষেত্রেই সেশন মুছে দেওয়া হয়।
        // Issue #521: tokenStorage sweep (sessionStorage + legacy localStorage)।
        clearUserToken();
        updateTokenCache(null);
        persistUser(null);
        void clearLocalDataScope();
        set({ status: AuthStatus.LOGGED_OUT, user: null });
      } else {
        // বাংলা মন্তব্য: ক্ষণস্থায়ী ব্যর্থতা (নেটওয়ার্ক ডাউন / Render cold start / 5xx) — logout নয়।
        if (import.meta.env.DEV) {
          console.warn('Session validation deferred (transient error):', error?.message);
        }
      }
    }
  },
}));
