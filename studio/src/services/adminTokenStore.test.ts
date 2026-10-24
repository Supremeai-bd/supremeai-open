import { describe, it, expect, beforeEach } from 'vitest';

import { adminTokenStore } from './adminTokenStore';

function base64Url(obj: unknown): string {
  const json = JSON.stringify(obj);
  return Buffer.from(json)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

// বাংলা (#3223): পরীক্ষাগুলো এখন sessionStorage ব্যবহার করে (localStorage নয়) —
// নতুন নিরাপদ চুক্তি অনুসারে। Legacy localStorage path আর নেই।
describe('adminTokenStore', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it('getRawToken returns null when no token is stored', () => {
    expect(adminTokenStore.getRawToken()).toBeNull();
  });

  it('getRawToken returns the stored token from sessionStorage', () => {
    sessionStorage.setItem('supreme_admin_jwt', 'raw.jwt.value');
    expect(adminTokenStore.getRawToken()).toBe('raw.jwt.value');
  });

  it('getRawToken does NOT read from localStorage (#3223 security fix)', () => {
    // বাংলা (#3223): localStorage-এ token থাকলেও getRawToken null return করবে —
    // localStorage read path সম্পূর্ণ সরানো হয়েছে।
    localStorage.setItem('supreme_admin_jwt', 'should-not-be-read.jwt.value');
    expect(adminTokenStore.getRawToken()).toBeNull();
  });

  it('getDecodedToken returns null when no token is stored', () => {
    expect(adminTokenStore.getDecodedToken()).toBeNull();
  });

  it('getDecodedToken decodes a valid three-part JWT from sessionStorage', () => {
    const token = `header.${base64Url({ sub: 'u1', role: 'admin' })}.sig`;
    sessionStorage.setItem('supreme_admin_jwt', token);
    const decoded = adminTokenStore.getDecodedToken();
    expect(decoded).not.toBeNull();
    expect(decoded?.sub).toBe('u1');
    expect(decoded?.role).toBe('admin');
  });

  it('getDecodedToken returns null for a malformed token', () => {
    sessionStorage.setItem('supreme_admin_jwt', 'not-three-parts');
    expect(adminTokenStore.getDecodedToken()).toBeNull();
  });
});
