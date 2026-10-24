// apps/studio-client/src/services/adminTokenStore.ts
// 🚨 CRITICAL CHECK: No external imports allowed here to bypass Vite Rollup blocks
//
// বাংলা (#3223): আগে এখানে সরাসরি `localStorage.getItem('supreme_admin_jwt')` পড়া হতো
// — XSS-exposed residual token persistence (#3154 closed-incomplete)। এখন
// `tokenStorage.getAdminToken()` ব্যবহার করা হয় যা sessionStorage-first
// (নিরাপদ), localStorage-এ কখনো write করে না। Legacy localStorage read
// path সম্পূর্ণ সরানো হয়েছে।

// বাংলা (#3223): adminTokenStore একটি "no external imports" সীমাবদ্ধ মডিউল
// (Vite Rollup block এড়াতে)। তাই tokenStorage কে dynamic import ছাড়া সরাসরি
// inline করতে হয়েছে — কিন্তু sessionStorage-first logic একই চুক্তি follow করে।
// localStorage.getItem কখনো call হয় না (root-cause fix)।

const ADMIN_TOKEN_KEY = 'supreme_admin_jwt';

const readAdminToken = (): string | null => {
  // বাংলা (#3223): sessionStorage-first — localStorage কখনো পড়া হয় না।
  // এটি tokenStorage.readToken-এর একই নিরাপদ চুক্তি, কিন্তু inline
  // (no external import — Vite Rollup constraint)। Legacy localStorage
  // migration/sweep এখানে নেই — সেটি tokenStorage-এর দায়িত্বে থাকবে।
  try {
    const session = typeof window === 'undefined' ? undefined : window.sessionStorage;
    if (!session) return null;
    return session.getItem(ADMIN_TOKEN_KEY);
  } catch {
    // sessionStorage অপ্রাপ্য (privacy mode / SSR) — null return
    return null;
  }
};

export const adminTokenStore = {
  getRawToken: (): string | null => {
    return readAdminToken();
  },
  getDecodedToken: (): Record<string, unknown> | null => {
    const token = readAdminToken();
    if (!token) return null;

    try {
      // 🛡️ Zero-Dependency Pure Native JWT Decoder
      const tokenParts = token.split('.');
      if (tokenParts.length !== 3) {
        throw new Error("Malformed JWT string structure.");
      }

      const base64Url = tokenParts[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');

      // UTF-8 Compliant Native Base64 Parsing
      const jsonPayload = decodeURIComponent(
        window.atob(base64)
          .split('')
          .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
          .join('')
      );

      return JSON.parse(jsonPayload);
    } catch (error: unknown) {
      const errObj = error as { message?: string };
      console.warn("⚠️ [TOKEN_STORE_LEAK]: Failed to safely parse or decode admin JWT token natively.", {
        error_message: errObj?.message || 'Invalid base64 payload matrix',
        token_length: token.length,
        timestamp: new Date().toISOString()
      });

      return null;
    }
  }
};
