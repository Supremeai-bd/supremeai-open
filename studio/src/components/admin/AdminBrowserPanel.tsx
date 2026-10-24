// ════════════════════════════════════════════════════════════════════
// AdminBrowserPanel — public entry point.
//
// The original 1174-line component was split (mechanical refactor, no
// behavior change) into cohesive submodules under ./admin-browser/:
//   types.ts, defaultBookmarks.tsx, formatHelpers.ts,
//   useBrowserActions.ts, BrowserToolbar.tsx, BookmarksPanel.tsx,
//   BrowserViewport.tsx, AIAssistantPanel.tsx, DevToolsPanel.tsx,
//   StatusBar.tsx, HistoryPanel.tsx, CrownJewelBrowser.tsx
//
// Both named exports below are preserved so all existing imports
// (e.g. CommandCenter.tsx) keep working unchanged.
// ════════════════════════════════════════════════════════════════════

import { CrownJewelBrowser } from './admin-browser/CrownJewelBrowser';

export { CrownJewelBrowser };

export const AdminBrowserPanel = CrownJewelBrowser;
