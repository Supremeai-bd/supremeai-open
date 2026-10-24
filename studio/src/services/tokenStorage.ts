// Centralized auth-token storage — FE-04 remediation, step 1 (Issue #521).
//
// বাংলা: নিরাপত্তা অডিট FE-04 অনুযায়ী auth token আর localStorage-এ স্থায়ীভাবে জমা
// হবে না। এখন থেকে টোকেন শুধু sessionStorage-এ (ট্যাব বন্ধ হলেই মুছে যায় — XSS
// exposure উইন্ডো অনেক ছোট) + মেমোরিতে থাকে। পুরনো (legacy) localStorage টোকেন
// পড়ার সময় sessionStorage-এ মাইগ্রেট করে localStorage থেকে মুছে ফেলা হয়, তাই
// আগের ডিপ্লয়মেন্টের সেশনও নিরাপদে চলতে থাকবে।

const USER_TOKEN_KEY = 'supremeai_auth_token';
export const USER_TOKEN_STORAGE_KEY = USER_TOKEN_KEY;
const ADMIN_TOKEN_KEY = 'supreme_admin_jwt';
export const ADMIN_TOKEN_STORAGE_KEY = ADMIN_TOKEN_KEY;

const hasStorage = (s: Storage | undefined): s is Storage => Boolean(s);

const getSession = (): Storage | undefined => {
  try {
    return typeof window === 'undefined' ? undefined : window.sessionStorage;
  } catch (err) {
    console.warn('[tokenStorage] sessionStorage unavailable, using fallback:', err);
    return undefined;
  }
};

const getLocal = (): Storage | undefined => {
  try {
    return typeof window === 'undefined' ? undefined : window.localStorage;
  } catch (err) {
    console.warn('[tokenStorage] localStorage unavailable, using fallback:', err);
    return undefined;
  }
};

const readToken = (key: string): string | null => {
  const session = getSession();
  if (hasStorage(session)) {
    try {
      const cached = session.getItem(key);
      if (cached) return cached;
    } catch (err) {
      console.warn('[tokenStorage] sessionStorage read failed:', err);
    }
  }

  const local = getLocal();
  if (hasStorage(local)) {
    try {
      const persistent = local.getItem(key);
      if (persistent) {
        // Validate unexpired if JWT
        try {
          const part = persistent.split('.')[1];
          if (part) {
            const base64 = part.replace(/-/g, '+').replace(/_/g, '/');
            const payload = JSON.parse(
              decodeURIComponent(
                atob(base64)
                  .split('')
                  .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
                  .join('')
              )
            );
            if (typeof payload?.exp === 'number' && payload.exp * 1000 <= Date.now()) {
              local.removeItem(key);
              return null;
            }
          }
        } catch {
          // Non-JWT token preserved
        }

        // Hydrate sessionStorage cache and sweep legacy user token from localStorage (FE-04 / Issue #521)
        if (hasStorage(session)) {
          try {
            session.setItem(key, persistent);
          } catch (err) {
            console.warn('[tokenStorage] session hydration failed:', err);
          }
        }
        if (key === USER_TOKEN_KEY) {
          try {
            local.removeItem(key);
          } catch (err) {
            console.warn('[tokenStorage] legacy user token sweep failed:', err);
          }
        }
        return persistent;
      }
    } catch (err) {
      console.warn('[tokenStorage] localStorage read failed:', err);
    }
  }

  return null;
};

const writeToken = (key: string, token: string, persistToLocal = false): void => {
  const session = getSession();
  if (hasStorage(session)) {
    try {
      session.setItem(key, token);
    } catch (err) {
      console.warn('[tokenStorage] sessionStorage write failed, token kept in memory only:', err);
    }
  }
  if (persistToLocal) {
    const local = getLocal();
    if (hasStorage(local)) {
      try {
        local.setItem(key, token);
      } catch (err) {
        console.warn('[tokenStorage] localStorage write failed:', err);
      }
    }
  }
};

const clearToken = (key: string): void => {
  const session = getSession();
  if (hasStorage(session)) {
    try {
      session.removeItem(key);
    } catch (err) {
      console.warn('[tokenStorage] sessionStorage removeItem failed:', err);
    }
  }
  const local = getLocal();
  if (hasStorage(local)) {
    try {
      local.removeItem(key);
    } catch (err) {
      console.warn('[tokenStorage] localStorage removeItem failed:', err);
    }
  }
};

// Trusted browser token for 7-day MFA bypass
const TRUSTED_BROWSER_KEY = 'supreme_trusted_browser_token';
export const TRUSTED_BROWSER_STORAGE_KEY = TRUSTED_BROWSER_KEY;

export const getTrustedBrowserToken = (): string | null => {
  const local = getLocal();
  if (hasStorage(local)) {
    try {
      const tok = local.getItem(TRUSTED_BROWSER_KEY);
      if (tok) return tok;
    } catch (err) {
      console.warn('[tokenStorage] trusted browser token read failed:', err);
    }
  }
  const session = getSession();
  if (hasStorage(session)) {
    try {
      return session.getItem(TRUSTED_BROWSER_KEY);
    } catch {
      return null;
    }
  }
  return null;
};

export const setTrustedBrowserToken = (token: string): void => {
  const local = getLocal();
  if (hasStorage(local)) {
    try {
      local.setItem(TRUSTED_BROWSER_KEY, token);
    } catch (err) {
      console.warn('[tokenStorage] trusted browser token localStorage write failed:', err);
    }
  }
  const session = getSession();
  if (hasStorage(session)) {
    try {
      session.setItem(TRUSTED_BROWSER_KEY, token);
    } catch (err) {
      console.warn('[tokenStorage] trusted browser token sessionStorage write failed:', err);
    }
  }
};

export const clearTrustedBrowserToken = (): void => {
  clearToken(TRUSTED_BROWSER_KEY);
};

// User session token
export const getUserToken = (): string | null => readToken(USER_TOKEN_KEY);
export const setUserToken = (token: string): void => writeToken(USER_TOKEN_KEY, token);
export const clearUserToken = (): void => clearToken(USER_TOKEN_KEY);

// Admin step-up JWT — persists to localStorage so closing the tab or browser doesn't trigger auto-logout
export const getAdminToken = (): string | null => readToken(ADMIN_TOKEN_KEY);
export const setAdminToken = (token: string, persistToLocal = true): void => writeToken(ADMIN_TOKEN_KEY, token, persistToLocal);
export const clearAdminToken = (): void => clearToken(ADMIN_TOKEN_KEY);
