// SupremeAI — UnifiedAppShell (single-frontend migration, roadmap Phase 3)
// বাংলা মন্তব্য: একটাই application shell — GlobalHeader + RoleAwareNavRail +
// DashboardLayout foundation। User ও Admin উভয়ই এখানে রেন্ডার হয়; দুটি আলাদা
// shell তৈরি করা নিষিদ্ধ (roadmap §8: "Do not create two complete application shells")।
//
// Reused (not re-created): layout/DashboardLayout (low-level foundation),
// contexts/ThemeProvider, layout/CommandBar (global), contexts/ToastProvider।

import React from 'react';
import { DashboardLayout } from '../layout/DashboardLayout';
import { GlobalHeader, type HeaderNotification } from './GlobalHeader';
import { RoleAwareNavRail } from './RoleAwareNavRail';
import { useWorkspaceSettings } from '../../hooks/useWorkspaceSettings';

export interface UnifiedAppShellProps {
  /** Which runtime context renders inside the shell. */
  context: 'user' | 'admin';
  children: React.ReactNode;
  /** Admin context: currently active subtab id. */
  activeActionId?: string;
  /** Admin context: subtab switch handler. */
  onAction?: (actionId: string) => void;
  /** Context-specific logout handler (admin passes handleAdminLogout). */
  onLogout?: () => void;
  /** Contextual header notifications. */
  notifications?: HeaderNotification[];
  /** Contextual right-side header actions. */
  headerActions?: React.ReactNode;
}

export function UnifiedAppShell({
  context,
  children,
  activeActionId,
  onAction,
  onLogout,
  notifications,
  headerActions,
}: UnifiedAppShellProps) {
  const isSidebarCollapsed = useWorkspaceSettings((s) => s.isSidebarCollapsed);

  return (
    <DashboardLayout
      header={
        <GlobalHeader
          context={context}
          onLogout={onLogout}
          notifications={notifications}
          actions={headerActions}
        />
      }
      sidebar={
        <RoleAwareNavRail
          context={context}
          collapsed={isSidebarCollapsed}
          activeActionId={activeActionId}
          onAction={onAction}
          onToggleCollapsed={useWorkspaceSettings.getState().toggleSidebar}
        />
      }
      isSidebarCollapsed={isSidebarCollapsed}
    >
      {children}
    </DashboardLayout>
  );
}
