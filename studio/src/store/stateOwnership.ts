/**
 * Canonical frontend state ownership map.
 *
 * This is intentionally descriptive: it prevents new features from creating
 * another store for state already owned by an existing authority.
 */
export const STATE_OWNERSHIP = {
  identity: 'authStore',
  adminStepUp: 'adminStore',
  serverData: 'TanStack Query hooks',
  workspaceUi: 'useWorkspaceSettings',
  chat: 'chatStore',
  customerSession: 'customerStore',
  commandAccess: 'commandRegistry + route context',
} as const;

export type StateOwner = (typeof STATE_OWNERSHIP)[keyof typeof STATE_OWNERSHIP];
