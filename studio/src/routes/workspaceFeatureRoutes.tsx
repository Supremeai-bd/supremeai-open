import { lazy, Suspense } from 'react';
import type { RouteObject } from 'react-router-dom';
import { ProtectedRoute } from '../components/core/AuthGuards';
import { WorkspaceLayout } from '../components/layout/WorkspaceLayout';

// ─── Lazy load Tier-S pages ─────────────────────────────────────────────

const SharedConversationPage = lazy(
  () => import('../pages/SharedConversationPage'),
);
const PromptTemplatePage = lazy(
  () => import('../pages/PromptTemplatePage'),
);
// FIX(nav-truth 2026-10-24): these page files existed but were never registered
// here — every nav/dashboard link to them 404'd into the guest landing. All of
// them self-wrap WorkspaceLayout EXCEPT WorkspaceSettingsPage (adapter), which
// is wrapped below.
const ProjectsPage = lazy(() => import('../pages/ProjectsPage'));
const ActivityPage = lazy(() => import('../pages/ActivityPage'));
const MarketplacePage = lazy(() => import('../pages/MarketplacePage'));
const RunsPage = lazy(() => import('../pages/RunsPage'));
const FilesPage = lazy(() => import('../pages/FilesPage'));
const BillingPage = lazy(() => import('../pages/BillingPage'));
const ProfilePage = lazy(() => import('../pages/ProfilePage'));
const WorkspaceSettingsPage = lazy(
  () => import('../pages/user/WorkspaceSettingsPage'),
);
// FIX(#1521 Phase 0 last-mile 2026-10-28): DeepResearchPanel/ScheduledTasksPanel
// were backend-wired (api/routers.py: deep_research, scheduled_tasks) and nav-
// advertised (/research, /scheduled-tasks) but never registered here — every
// nav/dashboard link 404'd into the guest landing. Neither panel self-wraps
// WorkspaceLayout (same adapter situation as WorkspaceSettingsPage), so both
// are wrapped below.
const DeepResearchPanel = lazy(
  () => import('../components/research/DeepResearchPanel'),
);
const ScheduledTasksPanel = lazy(
  () => import('../components/schedule/ScheduledTasksPanel'),
);

// ─── Route definitions ───────────────────────────────────────────────────

/**
 * Tier-S user-facing route definitions.
 * Spread these into the <Routes> block inside App.tsx.
 *
 * NOTE: /share/:shareId is intentionally a GUEST route (no ProtectedRoute
 * wrapper) so that anyone with a share link can view the conversation.
 * বাংলা (single-frontend migration): /prompt-library আগে UNGUARDED ছিল — এখন
 * ProtectedRoute দিয়ে wrap করা হলো (roadmap security matrix: সব authenticated
 * user context route protected হবে)।
 */
function protectedPage(label: string, node: React.ReactNode) {
  return (
    <ProtectedRoute>
      <Suspense
        fallback={
          <div className="flex items-center justify-center min-h-screen bg-slate-950 text-slate-400">
            <div className="animate-pulse">Loading {label}…</div>
          </div>
        }
      >
        {node}
      </Suspense>
    </ProtectedRoute>
  );
}

export const workspaceFeatureRoutes: RouteObject[] = [
  {
    path: '/share/:shareId',
    element: (
      <Suspense
        fallback={
          <div className="flex items-center justify-center min-h-screen bg-slate-950 text-slate-400">
            <div className="animate-pulse">Loading shared conversation…</div>
          </div>
        }
      >
        <SharedConversationPage />
      </Suspense>
    ),
  },
  {
    path: '/prompt-library',
    element: (
      <ProtectedRoute>
        <Suspense
          fallback={
            <div className="flex items-center justify-center min-h-screen bg-slate-950 text-slate-400">
              <div className="animate-pulse">Loading prompt library…</div>
            </div>
          }
        >
          <WorkspaceLayout>
            <PromptTemplatePage />
          </WorkspaceLayout>
        </Suspense>
      </ProtectedRoute>
    ),
  },
  // FIX(nav-truth 2026-10-24): registered existing self-wrapping feature pages
  // so user nav/dashboard links stop 404-ing into the guest landing.
  { path: '/projects', element: protectedPage('projects', <ProjectsPage />) },
  { path: '/activity', element: protectedPage('activity', <ActivityPage />) },
  { path: '/marketplace', element: protectedPage('marketplace', <MarketplacePage />) },
  { path: '/runs', element: protectedPage('runs', <RunsPage />) },
  { path: '/files', element: protectedPage('files', <FilesPage />) },
  { path: '/billing', element: protectedPage('billing', <BillingPage />) },
  { path: '/profile', element: protectedPage('profile', <ProfilePage />) },
  {
    path: '/settings',
    element: protectedPage(
      'settings',
      <WorkspaceLayout>
        <WorkspaceSettingsPage />
      </WorkspaceLayout>,
    ),
  },
  // FIX(#1521 Phase 0 last-mile 2026-10-28): backend-ready engines finally
  // reachable in the UI — guest visitors are redirected to /login by
  // ProtectedRoute (roadmap security matrix: authenticated user context),
  // matching navigationRegistry's user-context entries for these paths.
  {
    path: '/research',
    element: protectedPage(
      'research',
      <WorkspaceLayout>
        <DeepResearchPanel />
      </WorkspaceLayout>,
    ),
  },
  {
    path: '/scheduled-tasks',
    element: protectedPage(
      'scheduled tasks',
      <WorkspaceLayout>
        <ScheduledTasksPanel />
      </WorkspaceLayout>,
    ),
  },
];

/** @deprecated Use workspaceFeatureRoutes instead. */
export const tierSUserRoutes = workspaceFeatureRoutes;

// ─── Integration Guide ───────────────────────────────────────────────────

/**
 * Comprehensive integration guide for wiring all 12 Tier-S features
 * into the existing SupremeAI codebase.  Follow each section in order.
 */
export const TierSIntegrationGuide = `
=========================================================================
  SUPREMEAI TIER-S — INTEGRATION GUIDE
=========================================================================

This guide covers wiring all 12 Tier-S features (S1–S12) into the
existing SupremeAI app.  All backend route files, frontend components,
and the Zustand store have already been created.  You only need to
connect them.

=========================================================================
  STEP 1 — NPM Dependencies
=========================================================================

  cd frontend
  npm install jspdf file-saver
  npm install -D @types/file-saver

=========================================================================
  STEP 2 — Backend Router Registration
=========================================================================

All 12 Tier-S routers are ALREADY registered individually in
backend/api/routers.py (share, reasoning, artifacts, chat_upload,
slash_commands, chat_search, chat_export, global_memory,
prompt_templates, branch_conversations, scheduled_tasks,
deep_research). No action needed — do NOT invent a second registry
(single source of truth: api/routers.py ALL_ROUTERS).

=========================================================================
  STEP 3 — Frontend Route Integration (App.tsx)
=========================================================================

Open frontend/src/App.tsx and make the following changes:

--- 3a. Add the import at the top (with other lazy imports) ---

  import { workspaceFeatureRoutes } from './routes/workspaceFeatureRoutes';

--- 3b. Inside the USER PORTAL <Routes> block ---

  Add the Tier-S routes BEFORE the catch-all 404.  The share route
  must come first because <Route path="*" /> matches everything:

  {/* ═══ Tier-S Feature Routes ═══ */}
  {workspaceFeatureRoutes.map((r, i) => <Route key={i} path={r.path!} element={r.element} />)}

  {/* Catch-all 404 Route — keep this LAST */}
  <Route path="*" element={<ErrorPage code={404} />} />

=========================================================================
  STEP 4 — Component Integration (ChatInterface.tsx)
=========================================================================

The main chat interface needs 6+ Tier-S components wired in.
Open frontend/src/components/chat/ChatInterface.tsx.

--- 4a. Add imports ---

  import { ShareDialog } from '../share/ShareDialog';
  import { ThinkingPanel } from '../reasoning/ThinkingPanel';
  import { ArtifactsPanel } from '../artifacts/ArtifactsPanel';
  import { ImageUploadButton } from './ImageUploadButton';
  import ExportMenu from '../export/ExportMenu';
  import BranchButton from '../branch/BranchButton';
  import { SlashCommandMenu } from '../commands/SlashCommandMenu';
  import { ChatSearchDialog } from '../search/ChatSearchDialog';
  import { useTierSStore } from '../../store/workspaceUiStateStore';

--- 4b. Inside the component body, destructure store values ---

  const {
    shareDialogOpen, shareConversationId, closeShareDialog,
    openShareDialog,
    showReasoning, reasoningSteps, isThinking,
    artifactsPanelOpen, activeArtifactId, artifacts,
    selectArtifact, setArtifactsPanelOpen,
    slashMenuOpen, closeSlashMenu, slashFilter, slashPosition,
    searchDialogOpen, closeSearchDialog, openSearchDialog,
  } = useTierSStore();

--- 4c. In the toolbar / action-bar area, add these buttons ---

  {/* S1: Share Button */}
  <button onClick={() => openShareDialog(currentConversationId)}>
    <Share2 className="w-4 h-4" />
  </button>

  {/* S7: Export Menu */}
  <ExportMenu conversationId={currentConversationId} />

  {/* S4: Image Upload */}
  <ImageUploadButton
    conversationId={currentConversationId}
    onUploadComplete={(attachment) => { /* handle */ }}
  />

  {/* S11: Branch Button (per message bubble) */}
  <BranchButton
    conversationId={currentConversationId}
    messageId={msg.id}
    onBranchCreated={(newId) => { /* navigate to branched conv */ }}
  />

--- 4d. Render overlay/dialog components at the bottom of the JSX ---

  {/* Tier-S Overlays */}
  <ShareDialog
    conversationId={shareConversationId || ''}
    isOpen={shareDialogOpen}
    onClose={closeShareDialog}
  />

  {showReasoning && (
    <ThinkingPanel steps={reasoningSteps} isThinking={isThinking} />
  )}

  {artifactsPanelOpen && (
    <ArtifactsPanel
      artifacts={artifacts}
      activeId={activeArtifactId}
      onSelect={(id) => selectArtifact(id)}
      onClose={() => setArtifactsPanelOpen(false)}
    />
  )}

  <ChatSearchDialog isOpen={searchDialogOpen} onClose={closeSearchDialog} />

  <SlashCommandMenu
    isOpen={slashMenuOpen}
    filter={slashFilter}
    position={slashPosition}
    onSelect={(cmd) => {
      closeSlashMenu();
      setInput((prev) => prev.replace(/\\/\\S*$/, cmd.insertText || ''));
    }}
    onClose={closeSlashMenu}
  />

=========================================================================
  STEP 5 — Keyboard Shortcut: Cmd+K for Chat Search (S6)
=========================================================================

Add a global keyboard listener inside ChatInterface.tsx:

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (searchDialogOpen) {
          closeSearchDialog();
        } else {
          openSearchDialog();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [searchDialogOpen, openSearchDialog, closeSearchDialog]);

=========================================================================
  STEP 6 — Slash Command Detection in Chat Input (S5)
=========================================================================

In the chat input onChange handler, detect when the user types '/'
at the beginning of the input (or after a space) and open the slash menu:

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);

    // Slash command detection
    const slashMatch = value.match(/(^|\\s)\\/(\\S*)$/);
    if (slashMatch) {
      const rect = e.target.getBoundingClientRect();
      openSlashMenu(slashMatch[2], {
        top: rect.top - 10,
        left: rect.left + 20,
      });
    } else {
      closeSlashMenu();
    }
  };

Then attach this handler to your textarea:

  <textarea
    value={input}
    onChange={handleInputChange}
    onKeyDown={handleKeyDown}
    placeholder="Type a message… (/ for commands)"
  />

=========================================================================
  API ENDPOINT SUMMARY
=========================================================================

  Feature  Prefix                      Endpoints
  ──────  ────────────────────────────  ────────────────────────────────────
  S1      /api/share                   POST /generate, GET /{share_id},
                                       GET /list, DELETE /{share_id}
  S2      /api/reasoning               POST /think, POST /think/stream
  S3      /api/artifacts                GET /, POST /, GET /{id},
                                       PUT /{id}, DELETE /{id}
  S4      /api/chat/upload              POST / (multipart file upload)
  S5      /api/slash-commands           GET / (list all commands)
  S6      /api/chat/search              GET /?q=...&conversation_id=...
  S7      /api/chat/export              GET /{id}/markdown,
                                       GET /{id}/json, GET /{id}/pdf
  S8      /api/global-memory            GET /, POST /, DELETE /{id}
  S9      /api/prompt-templates         GET /, POST /, PUT /{id},
                                       DELETE /{id}, POST /{id}/use
  S10     /api/scheduled-tasks         GET /, POST /, PUT /{id},
                                       DELETE /{id}, POST /{id}/run
  S11     /api/branch-conversations     POST / (branch from message)
  S12     /api/deep-research            POST /start, GET /{id}/status,
                                       GET /{id}/report

=========================================================================
  FILE CHECKLIST
=========================================================================

  Backend route files (12):
    backend/api/routes/share.py
    backend/api/routes/reasoning.py
    backend/api/routes/artifacts.py
    backend/api/routes/chat_upload.py
    backend/api/routes/slash_commands.py
    backend/api/routes/chat_search.py
    backend/api/routes/chat_export.py
    backend/api/routes/global_memory.py
    backend/api/routes/prompt_templates.py
    backend/api/routes/branch_conversations.py
    backend/api/routes/scheduled_tasks.py
    backend/api/routes/deep_research.py

  Backend infrastructure (2):
    backend/api/routes/tier_s_routes.py    (centralised registry)
    backend/alembic_migrations/versions/tier_s_features.py  (DB migration)

  Frontend components (8):
    frontend/src/components/share/ShareDialog.tsx
    frontend/src/components/reasoning/ThinkingPanel.tsx
    frontend/src/components/artifacts/ArtifactsPanel.tsx
    frontend/src/components/chat/ImageUploadButton.tsx
    frontend/src/components/export/ExportMenu.tsx
    frontend/src/components/branch/BranchButton.tsx
    frontend/src/components/commands/SlashCommandMenu.tsx
    frontend/src/components/search/ChatSearchDialog.tsx

  Frontend pages (2):
    frontend/src/pages/SharedConversationPage.tsx
    frontend/src/pages/PromptTemplatePage.tsx

  Frontend store & routes (2):
    frontend/src/store/workspaceUiStateStore.ts
    frontend/src/routes/workspaceFeatureRoutes.tsx    (this file)

=========================================================================
`;
