// RETIRED (bridge-20261025-orphan-layout-r1): layout/NavRail was an orphaned
// dead layout system - its only importer was this very test file (live nav
// rides RoleAwareNavRail inside UnifiedAppShell). Disposed together with
// Shell / MainLayout (layout/) and the dead customer chain (HomeFeed /
// CustomerSupportEditorStudio) per P1 item 2 (XS-2) of the verified
// 2026-10-25 frontend research report. The bridge lane cannot express file
// deletions, so this tombstone keeps vitest green until an operator deletes
// the husks together on merge:
//   git rm studio/src/components/layout/Shell.tsx
//   git rm studio/src/components/layout/MainLayout.tsx
//   git rm studio/src/components/layout/NavRail.tsx
//   git rm studio/src/components/layout/NavRail.test.tsx
//   git rm studio/src/components/customer/HomeFeed.tsx
//   git rm studio/src/components/customer/CustomerSupportEditorStudio.tsx
import { describe, it, expect } from 'vitest';

describe('NavRail (retired)', () => {
  it('was removed with the orphan layout systems (XS-2)', () => {
    expect(true).toBe(true);
  });
});
