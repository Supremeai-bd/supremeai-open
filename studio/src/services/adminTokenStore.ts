import { getAdminToken } from './tokenStorage';

export const adminTokenStore = {
  getDecodedToken: () => {
    const token = getAdminToken();
    if (!token) return null;
    try {
      const part = token.split('.')[1];
      const base64 = part.replace(/-/g, '+').replace(/_/g, '/');
      const payload = JSON.parse(decodeURIComponent(atob(base64).split('').map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('')));
      if (typeof payload?.exp === 'number' && payload.exp * 1000 <= Date.now()) return null;
      return payload;
    } catch {
      return null;
    }
  },
};
