import React, { useEffect, useState } from 'react';
import { ArrowRight, FileText, Plus, RefreshCw, Settings2, Sparkles, X, Zap } from 'lucide-react';
import AddNewWizard from './AddNewWizard';
import { CapabilityUnavailableExplainer, ManageItem } from './CapabilityCards';
import { capabilityFromModule, type UserCapability } from '../../types/contracts';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { useWorkspaceSettings, WORKSPACE_MODULES } from '../../hooks/useWorkspaceSettings';
import { connectionsApi } from '../../services/connectionsApi';
import { apiClient } from '../../services/apiClient';
import TaskAutomationCard from './TaskAutomationCard';

const quickStarts = [
  { label: 'Research a topic', detail: 'Get a clear answer with useful context.', icon: Sparkles, href: '/workspace/live' },
  { label: 'Analyze a file', detail: 'Bring a document into a focused workspace.', icon: FileText, href: '/files' },
  { label: 'Build a workflow', detail: 'Turn a repeatable task into a helper.', icon: Zap, href: '/agents' },
];

interface RecentConversation {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

function formatRelativeTime(iso: string) {
  const deltaMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(deltaMs / 60000);
  if (!Number.isFinite(minutes) || minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
};

export const UserDashboard: React.FC = () => {
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const [showTools, setShowTools] = useState(false);
  const [showAddWizard, setShowAddWizard] = useState(false);
  // FIX(intent-carryover): the ask-box used to navigate to /workspace/live
  // on Enter while discarding the typed text — the user's intent was lost
  // every time. It is now kept in state and forwarded to the Studio via a
  // URL param (consumed and stripped by AIStudio on mount).
  const [ask, setAsk] = useState('');
  const { enabledModules, toggleModule } = useWorkspaceSettings();
  const name = user?.name?.split(' ')[0] || 'there';

  const submitAsk = () => {
    const intent = ask.trim();
    if (!intent) return;
    navigate(`/workspace/live?intent=${encodeURIComponent(intent)}`);
  };

  // State-based capabilities from live backend (Phase 2 Progressive Disclosure)
  const [serverCapabilities, setServerCapabilities] = useState<UserCapability[]>([]);
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  // বাংলা: backend-এর Explain-Why payload (unavailableReason) — Explainer UX-এর জন্য
  const [capabilityReasons, setCapabilityReasons] = useState<Record<string, string>>({});
  // Recent work panel state: null = still loading, [] = honestly empty
  const [recentConversations, setRecentConversations] = useState<RecentConversation[] | null>(null);
  const [recentLoading, setRecentLoading] = useState(false);

  const fetchWorkspaceState = async () => {
    setLoadingWorkspace(true);
    try {
      const data = await connectionsApi.getMyWorkspace();
      if (data && Array.isArray(data.capabilities) && data.capabilities.length > 0) {
        const mapped: UserCapability[] = data.capabilities.map((c) => ({
          id: c.capabilityId,
          label: c.name,
          description: c.purpose,
          status: c.status,
          href: c.category === 'agent' ? '/agents' : undefined,
        }));
        setServerCapabilities(mapped);
        const reasons: Record<string, string> = {};
        for (const c of data.capabilities) {
          if (c.unavailableReason) reasons[c.capabilityId] = c.unavailableReason;
        }
        setCapabilityReasons(reasons);
      }
    } catch (err) {
      // Graceful degradation: fallback to client-enabled modules
      console.warn('Backend workspace fetch degraded; falling back to local module state:', err);
    } finally {
      setLoadingWorkspace(false);
    }
  };


  // FIX(recent-work): this section previously said "Nothing here yet" on a
  // hardcoded basis — it never asked the backend. It now lists the user's
  // most recent real conversations (GET /api/conversations, same API the
  // branch button uses) and degrades honestly to the empty state.
  const fetchRecentConversations = async () => {
    setRecentLoading(true);
    try {
      const data = await apiClient.get<RecentConversation[] | { data?: RecentConversation[] }>(
        '/api/v1/conversations/',
      );
      const rows = Array.isArray(data) ? data : (data?.data ?? []);
      setRecentConversations(rows.slice(0, 3));
    } catch {
      // Auth/permission or backend unavailable — show the honest empty state.
      setRecentConversations([]);
    } finally {
      setRecentLoading(false);
    }
  };
  useEffect(() => {
    fetchWorkspaceState();
    fetchRecentConversations();
  }, []);



  // Hybrid Progressive Disclosure:
  // Show server capabilities + local active modules (de-duplicated)
  const localCapabilities: UserCapability[] = WORKSPACE_MODULES
    .filter((module) => enabledModules.includes(module.id))
    .map(capabilityFromModule);

  const mergedCapabilities: UserCapability[] = [
    ...localCapabilities,
    ...serverCapabilities.filter((sc) => !localCapabilities.some((lc) => lc.id === sc.id)),
  ];

  return (
    <main className="min-h-full bg-[var(--sa-canvas)] text-[var(--sa-ink)]">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-5 py-8 sm:px-8 lg:py-10">
        <header className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="sa-eyebrow mb-3">Your workspace</p>
            <h1 className="text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
              Good morning, {name}.
            </h1>
            <p className="mt-2 max-w-xl text-[var(--sa-ink-muted)]">
              A simple place to think, make progress, and keep your work moving.
            </p>
          </div>
          <Link
            to="/settings"
            className="inline-flex items-center gap-2 self-start rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-4 py-2.5 text-sm font-medium transition hover:border-[var(--sa-primary)] hover:text-[var(--sa-primary)]"
          >
            <Settings2 size={16} /> Personalize
          </Link>
        </header>

        <TaskAutomationCard />

        <section className="sa-surface-raised p-5 sm:p-7" aria-labelledby="intent-heading">
          <p className="sa-eyebrow mb-2">Start anywhere</p>
          <h2 id="intent-heading" className="text-xl font-semibold">
            What would you like to do?
          </h2>
          <div className="mt-5 flex rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] bg-[var(--sa-canvas)] p-1.5 focus-within:border-[var(--sa-primary)] focus-within:ring-4 focus-within:ring-[var(--sa-primary-soft)]">
            <input
              type="text"
              aria-label="Ask SupremeAI what to accomplish"
              placeholder="Ask a question, describe a task, or share an idea..."
              className="min-w-0 flex-1 bg-transparent px-3 py-3 text-sm outline-none placeholder:text-[var(--sa-ink-muted)]"
              value={ask}
              onChange={(event) => setAsk(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.nativeEvent.isComposing && event.keyCode !== 229)
                  submitAsk();
              }}
            />
            <button
              type="button"
              aria-label="Open SupremeAI Studio"
              onClick={submitAsk}
              className="flex size-11 shrink-0 items-center justify-center rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] text-white transition hover:opacity-90"
            >
              <ArrowRight size={17} />
            </button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {quickStarts.map(({ label, icon: Icon, href }) => (
              <Link
                key={label}
                to={href}
                className="inline-flex items-center gap-2 rounded-full border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] transition hover:border-[var(--sa-primary)] hover:bg-[var(--sa-primary-soft)] hover:text-[var(--sa-primary)]"
              >
                <Icon size={13} />
                {label}
              </Link>
            ))}
          </div>
        </section>

        {/* Progressive Disclosure: Only Active / Added Capabilities Shown */}
        <section aria-labelledby="tools-heading">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="sa-eyebrow">Your tools</p>
              <h2 id="tools-heading" className="mt-1 text-xl font-semibold">
                Only what you need
              </h2>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label="Refresh capabilities"
                onClick={fetchWorkspaceState}
                className={`p-2 rounded-lg text-[var(--sa-ink-muted)] hover:bg-[var(--sa-surface-raised)] transition ${
                  loadingWorkspace ? 'animate-spin' : ''
                }`}
              >
                <RefreshCw size={14} />
              </button>
              <button
                type="button"
                onClick={() => setShowAddWizard(true)}
                className="inline-flex items-center gap-2 rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-3 py-2 text-xs font-medium hover:border-[var(--sa-primary)] hover:text-[var(--sa-primary)]"
              >
                <Plus size={14} /> Add new
              </button>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {mergedCapabilities.map((item) => (
              <ManageItem
                key={item.id}
                item={item}
                onUse={() => navigate(item.href || '/workspace/live')}
                onManage={() => navigate(item.href || '/settings')}
                onRemove={() => {
                  if (enabledModules.includes(item.id as typeof enabledModules[number])) {
                    toggleModule(item.id as typeof enabledModules[number]);
                  }
                  setServerCapabilities((prev) => prev.filter((c) => c.id !== item.id));
                }}
              />
            ))}
          </div>

          {/* বাংলা: Phase 4 Universal Manage Model — unavailable/requestable capability-র
              জন্য Explain-Why + Request Access। আগে কম্পোনেন্টটি ছিল কিন্তু কখনো render
              হতো না (dead UI)। */}
          {(() => {
            const unavailable = mergedCapabilities
              .filter((c) => c.status === 'unavailable' || c.status === 'requestable')
              .map((c) => ({
                id: c.id,
                label: c.label,
                reason:
                  capabilityReasons[c.id] ||
                  'This capability is not ready in your workspace yet.',
                requestable: c.status === 'requestable',
              }));
            if (unavailable.length === 0) return null;
            return (
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {unavailable.map((item) => (
                  <CapabilityUnavailableExplainer
                    key={item.id}
                    item={item}
                    onRequest={() => navigate('/settings')}
                  />
                ))}
              </div>
            );
          })()}
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <div className="sa-surface-raised p-5">
            <div className="flex items-center justify-between">
              <p className="sa-eyebrow">Recent work</p>
              {recentLoading && <RefreshCw size={13} className="animate-spin text-[var(--sa-ink-muted)]" />}
            </div>
            {recentConversations && recentConversations.length > 0 ? (
              <>
                <h2 className="mt-2 text-lg font-semibold">Pick up where you left off</h2>
                <ul className="mt-3 flex flex-col gap-2">
                  {recentConversations.map((conversation) => (
                    <li key={conversation.id}>
                      <Link
                        to="/workspace/live"
                        className="flex items-center justify-between gap-3 rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-3 py-2.5 text-sm transition hover:border-[var(--sa-primary)] hover:bg-[var(--sa-primary-soft)]"
                      >
                        <span className="min-w-0 flex-1 truncate font-medium">
                          {conversation.title?.trim() || 'Untitled conversation'}
                        </span>
                        <span className="shrink-0 text-xs text-[var(--sa-ink-muted)]">
                          {formatRelativeTime(conversation.updated_at)}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <>
                <h2 className="mt-2 text-lg font-semibold">Nothing here yet</h2>
                <p className="mt-2 text-sm text-[var(--sa-ink-muted)]">
                  {recentConversations === null
                    ? 'Loading your recent conversations…'
                    : 'Your conversations, projects, and completed tasks will appear here.'}
                </p>
              </>
            )}
          </div>
          <div className="sa-surface-raised p-5">
            <p className="sa-eyebrow">Need a starting point?</p>
            <h2 className="mt-2 text-lg font-semibold">Begin with a small task</h2>
            <p className="mt-2 text-sm text-[var(--sa-ink-muted)]">
              You can always add more tools later from Settings.
            </p>
          </div>
        </section>
      </div>

      {showAddWizard && (
        <AddNewWizard
          capabilities={mergedCapabilities}
          onClose={() => setShowAddWizard(false)}
          onRegistered={() => {
            fetchWorkspaceState();
          }}
          onAdd={(item) => {
            if (!enabledModules.includes(item.id as typeof enabledModules[number])) {
              toggleModule(item.id as typeof enabledModules[number]);
            }
            setShowAddWizard(false);
          }}
        />
      )}

      {showTools && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/30 p-4 sm:items-center"
          role="dialog"
          aria-modal="true"
          aria-labelledby="tools-dialog-title"
        >
          <div className="w-full max-w-lg rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-5 shadow-2xl">
            <div className="flex items-start justify-between">
              <div>
                <p className="sa-eyebrow">Personalize</p>
                <h2 id="tools-dialog-title" className="mt-1 text-xl font-semibold">
                  Choose your tools
                </h2>
                <p className="mt-1 text-sm text-[var(--sa-ink-muted)]">
                  Keep the workspace focused. You can change this any time.
                </p>
              </div>
              <button
                type="button"
                aria-label="Close tool picker"
                onClick={() => setShowTools(false)}
                className="rounded-lg p-2 text-[var(--sa-ink-muted)] hover:bg-[var(--sa-canvas)]"
              >
                <X size={17} />
              </button>
            </div>
            <div className="mt-5 flex flex-col gap-2">
              {WORKSPACE_MODULES.map((module) => (
                <label
                  key={module.id}
                  className="flex cursor-pointer items-center gap-3 rounded-xl border border-[var(--sa-border)] p-3 transition hover:border-[var(--sa-primary)]"
                >
                  <input
                    type="checkbox"
                    checked={enabledModules.includes(module.id)}
                    onChange={() => toggleModule(module.id)}
                    className="size-4 accent-[var(--sa-primary)]"
                  />
                  <span className="flex-1">
                    <span className="block text-sm font-medium">
                      {module.label}
                      {module.advanced && (
                        <span className="ml-2 rounded-full bg-[var(--sa-primary-soft)] px-2 py-0.5 text-[10px] text-[var(--sa-primary)]">
                          Optional developer tool
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-[var(--sa-ink-muted)]">
                      {module.description}
                    </span>
                  </span>
                </label>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setShowTools(false)}
              className="mt-5 w-full rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] px-4 py-2.5 text-sm font-semibold text-white"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </main>
  );
};

export default UserDashboard;
