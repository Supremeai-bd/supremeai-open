/**
 * DEPRECATION SHIM (Wave 3.7, issue #1263): dashboardStore migrated into
 * unifiedStore's `dashboard` slice. `useDashboardStore` is now the SAME
 * store — every selector (`useDashboardStore((s) => s.systemStatus)` etc.)
 * keeps working because all dashboard fields live on UnifiedState.
 * New code should import { useUnifiedStore } from './unifiedStore'.
 */
import { useUnifiedStore } from './unifiedStore';

export const useDashboardStore = useUnifiedStore;
