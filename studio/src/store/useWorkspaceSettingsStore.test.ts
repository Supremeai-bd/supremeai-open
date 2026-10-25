// RETIRED (bridge-20261025-rc3-floating-orphan-r1): the dock-only
// useWorkspaceSettingsStore was neutralized together with the orphaned
// floating-widget layer (LivingActionDock / LivingDashboardShell /
// ActionDock / DynamicActionDock / LiveSimulator). The bridge lane cannot
// express file deletions, so this tombstone keeps vitest green until an
// operator deletes both husks together on merge:
//   git rm studio/src/store/useWorkspaceSettingsStore{,.test.ts}
import { describe, it, expect } from 'vitest';

describe('useWorkspaceSettingsStore (retired)', () => {
  it('was removed with the orphan floating-widget layer (RC-3)', () => {
    expect(true).toBe(true);
  });
});
