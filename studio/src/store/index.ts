/**
 * R13 FIX: Unified Store Entry Point
 *
 * When UNIFIED_STORE=true env (or localStorage flag) is set, this file
 * re-exports the unified store under the names of the 12 legacy store hooks.
 * Existing imports `import { useChatStore } from '@/store/chatStore'` keep
 * working UNCHANGED because each legacy store file will be replaced with a
 * 1-line re-export shim in Phase 2.
 *
 * Phase 2 of R13 will delete the shim files entirely.
 *
 * Feature flag:
 *   - VITE_UNIFIED_STORE=true at build time, OR
 *   - localStorage.setItem('UNIFIED_STORE', 'true') at runtime (dev/test)
 */

export const isUnifiedStoreEnabled = (): boolean => {
  if (typeof window !== 'undefined' && window.localStorage) {
    return window.localStorage.getItem('UNIFIED_STORE') === 'true';
  }
  // Vite env fallback
  return import.meta?.env?.VITE_UNIFIED_STORE === 'true';
};

// Re-export unified store hooks (when flag is on)
export { useUnifiedStore } from './unifiedStore';

/**
 * Migration helper — call from ProfilePage "Try new unified store" button.
 * Verifies the unified store has all required slices before flipping the flag.
 */
export const tryEnableUnifiedStore = async (): Promise<boolean> => {
  try {
    const { useUnifiedStore } = await import('./unifiedStore');
    const state = useUnifiedStore.getState();
    const requiredSlices = ['auth', 'chat', 'workspace', 'theme', 'admin'];
    const missing = requiredSlices.filter((k) => !(k in state));
    if (missing.length > 0) {
      console.warn(`[R13] unifiedStore missing slices: ${missing.join(', ')}`);
      return false;
    }
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('UNIFIED_STORE', 'true');
    }
    return true;
  } catch (e) {
    console.error('[R13] Failed to enable unified store:', e);
    return false;
  }
};

/**
 * Disable unified store (rollback switch).
 */
export const disableUnifiedStore = (): void => {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem('UNIFIED_STORE');
  }
};
