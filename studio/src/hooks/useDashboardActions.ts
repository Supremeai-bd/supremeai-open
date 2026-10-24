import { useCallback } from 'react';
import { workspaceCapabilitiesApi } from '../utils/api';

export function useDashboardActions() {
  const runIntegrationAction = useCallback(async (id: string) => {
    // Wire to the real capability execution engine via workspace API.
    // health() POST triggers the capability's execution flow.
    try {
      await workspaceCapabilitiesApi.health(id);
      return { ok: true };
    } catch (error) {
      console.error('[Dashboard] Integration action failed:', error);
      return { ok: false, error: error instanceof Error ? error.message : 'Execution failed' };
    }
  }, []);

  return { runIntegrationAction };
}
