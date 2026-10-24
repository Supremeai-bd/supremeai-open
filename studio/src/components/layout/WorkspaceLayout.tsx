// SupremeAI — WorkspaceLayout (single-frontend migration, roadmap Phase 3)
// বাংলা মন্তব্য: User context এখন UnifiedAppShell-এর ভেতরে রেন্ডার হয়। শুধুমাত্র
// user-specific business অংশ (DnD dock, HITL modal) এখানে থাকে — shell/header/nav
// infra unified shell থেকে আসে। পুরোনো NAV_GROUPS + UserSidebar navigationRegistry.ts-
// তে সরানো হয়েছে (একক nav registry; এখানে দ্বিতীয় definition নেই)।

import { UnifiedAppShell } from '../shell/UnifiedAppShell';
import { CommandBar } from './CommandBar';

/**
 * Keep the default viewer shell boring and predictable. Feature-specific docks,
 * drag/drop, and approval UI belong inside the feature that explicitly needs it;
 * they must not be mounted for every read-only page.
 */
export function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <UnifiedAppShell context="user">
      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {children}
      </main>
      {/* RESTORE-AND-WIRE (2026-09-14): universal Ctrl+K command palette restored.
          Hidden until the hotkey is pressed, so the default shell stays boring
          and predictable per the FRONTEND_SIMPLICITY contract. */}
      <CommandBar />
    </UnifiedAppShell>
  );
}
