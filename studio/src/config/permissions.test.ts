import { describe, it, expect } from 'vitest';
import { isRole, normalizeRole, hasPermission, PERMISSIONS } from './permissions';

describe('permissions', () => {
  describe('isRole', () => {
    it('accepts canonical roles', () => {
      expect(isRole('user')).toBe(true);
      expect(isRole('admin')).toBe(true);
    });

    it('rejects unknown strings', () => {
      expect(isRole('superadmin')).toBe(false);
      expect(isRole('')).toBe(false);
    });

    it('rejects non-string values', () => {
      expect(isRole(null)).toBe(false);
      expect(isRole(undefined)).toBe(false);
      expect(isRole(42)).toBe(false);
    });
  });

  describe('normalizeRole', () => {
    it('returns user for user-like values', () => {
      expect(normalizeRole('user')).toBe('user');
      expect(normalizeRole('viewer')).toBe('user');
      expect(normalizeRole('operator')).toBe('user');
      expect(normalizeRole('developer')).toBe('user');
    });

    it('returns admin for admin-like values', () => {
      expect(normalizeRole('admin')).toBe('admin');
      expect(normalizeRole('god')).toBe('admin');
      expect(normalizeRole('superadmin')).toBe('admin');
    });

    it('is case-insensitive', () => {
      expect(normalizeRole('Admin')).toBe('admin');
      expect(normalizeRole('USER')).toBe('user');
    });

    it('returns null for unknown values', () => {
      expect(normalizeRole('guest')).toBeNull();
      expect(normalizeRole(null)).toBeNull();
      expect(normalizeRole('')).toBeNull();
    });
  });

  describe('hasPermission', () => {
    it('defers to backend when permissions array is empty', () => {
      expect(hasPermission([], PERMISSIONS.ADMIN_READ)).toBe(true);
      expect(hasPermission(null, PERMISSIONS.ADMIN_READ)).toBe(true);
      expect(hasPermission(undefined, PERMISSIONS.ADMIN_READ)).toBe(true);
    });

    it('returns true when the required permission is present', () => {
      expect(hasPermission([PERMISSIONS.WORKSPACE_READ], PERMISSIONS.WORKSPACE_READ)).toBe(true);
    });

    it('returns false when the required permission is missing', () => {
      expect(hasPermission([PERMISSIONS.WORKSPACE_READ], PERMISSIONS.ADMIN_READ)).toBe(false);
    });
  });
});
