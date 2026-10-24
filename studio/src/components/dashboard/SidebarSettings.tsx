// apps/studio-client/src/components/dashboard/SidebarSettings.tsx
// বাংলা মন্তব্য: Sessions / Vault-Secrets / Integrations ট্যাব — Integrations ট্যাব সরাসরি INTEGRATION_REGISTRY + toggleIntegration ব্যবহার করে
import { AnimatePresence, motion, type Variants } from 'framer-motion';
import { LayoutList, Vault, Plug, GitBranch, Hash, FileText } from 'lucide-react';
import {
  useWorkspaceSettings,
  INTEGRATION_REGISTRY,
  type SidebarTab,
  type IntegrationMeta,
} from '../../hooks/useWorkspaceSettings';
import { SessionsPage } from './SessionsPage';
import { VaultPage } from './VaultPage';

interface SidebarSettingsProps {
  onOpenSession: (id: string) => void;
}

const TABS: { id: SidebarTab; label: string; icon: React.ComponentType<{ size?: number }> }[] = [
  { id: 'sessions', label: 'Sessions', icon: LayoutList },
  { id: 'vault', label: 'Vault / Secrets', icon: Vault },
  { id: 'integrations', label: 'Integrations', icon: Plug },
];

const ICON_MAP: Record<IntegrationMeta['icon'], React.ComponentType<{ size?: number; className?: string }>> = {
  Github: GitBranch,
  Slack: Hash,
  FileText,
};

const panelVariants: Variants = {
  hidden: { opacity: 0, x: 8 },
  visible: { opacity: 1, x: 0, transition: { duration: 0.18, ease: 'easeOut' } },
  exit: { opacity: 0, x: -8, transition: { duration: 0.12 } },
};

function IntegrationsTab() {
  const enabledIntegrations = useWorkspaceSettings((s) => s.enabledIntegrations);
  const toggleIntegration = useWorkspaceSettings((s) => s.toggleIntegration);

  return (
    <ul className="flex flex-col gap-2 px-3 py-3">
      {INTEGRATION_REGISTRY.map((integration) => {
        const Icon = ICON_MAP[integration.icon];
        const isEnabled = enabledIntegrations[integration.id];

        return (
          <li
            key={integration.id}
            className="flex items-center justify-between rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5"
          >
            <div className="flex items-center gap-2.5">
              <Icon size={15} className="text-slate-300" />
              <div className="flex flex-col">
                <span className="text-xs font-medium text-slate-200">{integration.label}</span>
                {!integration.dagSupported && (
                  <span className="text-[10px] text-amber-500">Orchestrator DAG not wired yet</span>
                )}
              </div>
            </div>

            <button
              role="switch"
              aria-checked={isEnabled}
              aria-label={`Toggle ${integration.label} integration`}
              onClick={() => toggleIntegration(integration.id)}
              className={`relative w-9 h-5 rounded-full transition-colors duration-200 ${
                isEnabled ? 'bg-indigo-500' : 'bg-white/10'
              }`}
            >
              <motion.span
                layout
                transition={{ type: 'spring', stiffness: 500, damping: 32 }}
                className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow"
                style={{ x: isEnabled ? 16 : 0 }}
              />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function SidebarSettings({ onOpenSession }: SidebarSettingsProps) {
  const activeSidebarTab = useWorkspaceSettings((s) => s.activeSidebarTab);
  const setActiveSidebarTab = useWorkspaceSettings((s) => s.setActiveSidebarTab);

  return (
    <div className="flex flex-col h-full min-h-0">
      <nav className="flex border-b border-white/10 px-2 pt-1">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeSidebarTab === tab.id;
          return (
            <button
              key={tab.id}
              data-testid={`sidebar-tab-${tab.id}`}
              onClick={() => setActiveSidebarTab(tab.id)}
              className={`relative flex-1 flex flex-col items-center gap-1 px-2 py-2.5 text-[10px] font-medium transition-colors ${
                isActive ? 'text-indigo-400' : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              <Icon size={14} />
              {tab.label}
              {isActive && (
                <motion.div
                  layoutId="sidebar-tab-underline"
                  className="absolute bottom-0 left-2 right-2 h-[2px] bg-indigo-400 rounded-full"
                  transition={{ type: 'spring', stiffness: 500, damping: 34 }}
                />
              )}
            </button>
          );
        })}
      </nav>

      <div className="flex-1 min-h-0 overflow-y-auto">
        <AnimatePresence mode="wait">
          <motion.div key={activeSidebarTab} variants={panelVariants} initial="hidden" animate="visible" exit="exit" className="h-full">
            {activeSidebarTab === 'sessions' && <SessionsPage onOpenSession={onOpenSession} />}
            {activeSidebarTab === 'vault' && <VaultPage />}
            {activeSidebarTab === 'integrations' && <IntegrationsTab />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
