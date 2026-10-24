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
      const legacy = local.getItem(key);
      if (legacy) {
        if (hasStorage(session)) {
          try {
            session.setItem(key, legacy);
          } catch (err) {
            console.warn('[tokenStorage] legacy token migration to sessionStorage failed:', err);
          }
        }
        local.removeItem(key);
        return legacy;
      }
    } catch (err) {
      console.warn('[tokenStorage] localStorage read failed:', err);
    }
  }

  return null;
};

const writeToken = (key: string, token: string): void => {
  const session = getSession();
  if (hasStorage(session)) {
    try {
      session.setItem(key, token);
    } catch (err) {
      console.warn('[tokenStorage] sessionStorage write failed, token kept in memory only:', err);
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

// User session token
export const getUserToken = (): string | null => readToken(USER_TOKEN_KEY);
export const setUserToken = (token: string): void => writeToken(USER_TOKEN_KEY, token);
export const clearUserToken = (): void => clearToken(USER_TOKEN_KEY);

// Admin step-up JWT
export const getAdminToken = (): string | null => readToken(ADMIN_TOKEN_KEY);
export const setAdminToken = (token: string): void => writeToken(ADMIN_TOKEN_KEY, token);
export const clearAdminToken = (): void => clearToken(ADMIN_TOKEN_KEY);
