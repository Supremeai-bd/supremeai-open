/* eslint-disable @typescript-eslint/no-explicit-any */
import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import type { AdminSubTab, ChatMessage } from '../../../types';
// বাংলা: Step-0 orphan cleanup-এ dead barrel (components/admin/index.ts) মোছা হয়েছিল,
// কিন্তু এই importer বাদ পড়েছিল → Vite build ভেঙে যাচ্ছিল (F-11 follow-through)।
// Barrel ফেরানোর বদলে প্রতিটি মডিউল সরাসরি import করা হলো — explicit dependency।
import { CommandCenter } from '../CommandCenter';
import { LiveLogs } from '../LiveLogs';
import { CostAuditor } from '../CostAuditor';
import { HealthMap } from '../HealthMap';
import { UserManager } from '../auth/UserManager';
import { ConfigEditor } from '../ConfigEditor';
import { ModelRouter } from '../ModelRouter';
import { EnhancedSkillMarketplace } from '../EnhancedSkillMarketplace';
import { MemoryBrowser } from '../MemoryBrowser';
import { CloudOrchestrator } from '../infra/CloudProviderHealth';
import { ObservabilityDashboard } from '../infra/ObservabilityDashboard';
import { ThreatDetection } from '../security/ThreatDetection';
import { VisualRulesBuilder } from '../VisualRulesBuilder';
import { CICDVisualizer } from '../CICDVisualizer';
import { GithubIntegration } from '../GithubIntegration';
import { BackupRestore } from '../BackupRestore';
import { SecurityDashboard } from '../security/SecurityDashboard';
import Dashboard from '../Dashboard';
import { RateLimitManager } from '../security/RateLimitManager';
import { InteractiveChatTab } from '../InteractiveChatTab';
import { AdminAlertsTab } from '../AdminAlertsTab';
import { ApprovalQueue } from '../../../commandcenter/modules/secure/ApprovalQueue';
// Issue #1831: the Audit tab now mounts the WORKING commandcenter audit UI
// (GET /admin-api/audit?limit= via useAuditLogs) — the old mapping pointed at
// the never-fed liveLogs LiveLogs view that showed a perpetual
// "Listening for incoming server logs..." placeholder.
import { AuditExplorer } from '../../../commandcenter/modules/secure/AuditExplorer';
import { GuardrailsPage } from '../../dashboard/GuardrailsPage';
import { HealingLogPanel } from '../../dashboard/HealingLogPanel';
import { SiteActionsPage } from '../../dashboard/SiteActionsPage';
import { LibrarianQueue } from '../LibrarianQueue';
import { TelemetryCockpitPage } from '../../../pages/user/TelemetryCockpitPage';
import { AutomationQueuePage } from '../../dashboard/AutomationQueuePage';
import ConnectedPlatformsVault from '../../dashboard/ConnectedPlatformsVault';
import { LlmGatewayPage } from '../../dashboard/LlmGatewayPage';
import { X } from 'lucide-react';

interface SubTabContentProps {
  adminSubTab: AdminSubTab;
  setAdminSubTab: (tab: AdminSubTab) => void;
  adminMessages: ChatMessage[];
  loading: boolean;
  adminInput: string;
  setAdminInput: (val: string) => void;
  handleSendAdmin: () => void;
  rulesJson: string;
  setRulesJson: (val: string) => void;
  saveStatus: string;
  handleSaveRules: () => void;
  liveLogs: string[];
  setLiveLogs: (logs: string[]) => void;
  costReport: string;
  /** Per-service health snapshot: { "<service>": { status, region, latency, ... } } */
  healthMap: Record<
    string,
    { status?: string; region?: string; latency?: string | number; [key: string]: unknown }
  >;
  newUsername: string;
  setNewUsername: (val: string) => void;
  newUserRole: string;
  setNewUserRole: (val: string) => void;
  newUserPerms: string;
  setNewUserPerms: (val: string) => void;
  handleSaveUser?: () => void;
  adminUsers?: Array<{ username: string; role?: string; [key: string]: unknown }>;
  handleDeleteUser?: (username: string) => void;
  envConfig?: Record<string, string>;
  setEnvConfig?: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  handleSaveConfig?: () => void;
  handleTriggerDeploy: () => void;
   
  [key: string]: any;
}

 
const MODULE_MAP: Record<string, React.FC<any>> = {
  'overview': Dashboard,
  'topology': CommandCenter, // Topology map
  'service-explorer': CloudOrchestrator,
  'agents-swarm': EnhancedSkillMarketplace, // Or ModelRouter depending on context
  'security': SecurityDashboard,
  'audit': AuditExplorer,
  'incidents': AdminAlertsTab,
  'approvals': ApprovalQueue,
  'guardrails': GuardrailsPage,
  'healing': HealingLogPanel,
  'site-actions': SiteActionsPage,
  'librarian': LibrarianQueue,
  'deployments': CICDVisualizer,
  'reliability': ObservabilityDashboard,
  'recovery': BackupRestore,
  'tenants-rbac': UserManager,
  'finops': CostAuditor,
  'rca-intelligence': ThreatDetection,
  'configuration': ConfigEditor,
  'telemetry': TelemetryCockpitPage,
  'automation-queue': AutomationQueuePage,
  'platform-vault': ConnectedPlatformsVault,
  'llm-gateway': LlmGatewayPage,
  
  // Keep legacy for fallback or command center
  'command-center': CommandCenter,
  'sandbox': SandboxView,
  'logs': LiveLogs,
  'costs': CostAuditor,
  'health': HealthMap,
  'users': UserManager,
  'config': ConfigEditor,
  'model-router': ModelRouter,
  'skills': EnhancedSkillMarketplace,
  'memory': MemoryBrowser,
  'cloud': CloudOrchestrator,
  'observability': ObservabilityDashboard,
  'threats': ThreatDetection,
  'rules': VisualRulesBuilder,
  'cicd': CICDVisualizer,
  'github': GithubIntegration,
  'backups': BackupRestore,
  'rate-limits': RateLimitManager,
  'security-dashboard': SecurityDashboard,
  'interactive-chat': InteractiveChatTab,
};

// বাংলা মন্তব্য: প্রতিটি admin tab-কে isolation-এর জন্য root-level ErrorBoundary-তে মোড়ানো হয়।
// কোনো module-এর render crash করলে পুরো dashboard নষ্ট না হয়ে শুধু সমস্যা module-টি graceful
// fallback দেখায়; "Reboot Module" বাটন বা অন্য tab-এ যাওয়ায় automatically reset হয়।
class ModuleErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[Dashboard Module ErrorBoundary] Module crashed:', error, info);
  }

  private reset = () => {
    this.setState({ hasError: false });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex-1 flex flex-col items-center justify-center p-8 min-h-[320px] bg-[var(--bg-main)]">
          <div className="text-[#ff0055] text-sm font-mono font-bold uppercase tracking-widest mb-2">
            ⚠ Module Crash Detected
          </div>
          <p className="text-slate-400 text-xs font-mono mb-4 text-center max-w-md">
            This dashboard module encountered a render error and was isolated.
            The rest of the system remains intact. Click below to reboot it.
          </p>
          <button
            onClick={this.reset}
            className="bg-[#00f3ff]/20 hover:bg-[#00f3ff]/40 text-[#00f3ff] hover:text-white font-mono font-bold py-2 px-4 rounded-lg transition-colors border border-[#00f3ff] uppercase text-xs"
          >
            Reboot Module
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function SubTabContent(props: SubTabContentProps) {
  const { adminSubTab, setAdminSubTab } = props;

  const SelectedModule: React.FC<SubTabContentProps> = MODULE_MAP[adminSubTab] || Dashboard;
  const isDashboardOrCanvas = adminSubTab === 'dashboard' || adminSubTab === 'command-center';

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[var(--bg-main)] relative transition-colors duration-500">
      {!isDashboardOrCanvas && (
        <div className="flex items-center justify-between border-b border-[var(--sa-border)] bg-[var(--sa-surface)] px-5 py-3 transition-colors duration-500">
          <div className="flex items-center gap-3"><span className="size-2 rounded-full bg-[var(--sa-primary)] shadow-[0_0_12px_var(--sa-primary)]" /><div><p className="sa-eyebrow">Admin module</p><span className="text-sm font-semibold capitalize text-[var(--sa-ink)]">{adminSubTab.replace('-', ' ')}</span></div></div>
          <button onClick={() => setAdminSubTab('command-center')} className="rounded-lg p-2 text-[var(--sa-ink-muted)] transition hover:bg-[var(--sa-primary-soft)] hover:text-[var(--sa-ink)]" title="Close module and return to canvas" aria-label="Close module and return to canvas"><X size={17} /></button>
        </div>
      )}

      <div className="flex-1 overflow-auto relative z-10 flex flex-col">
        {/* বাংলা মন্তব্য: শুধুমাত্র নির্বাচিত মডিউলটি মাউন্ট হবে, আগেরগুলো আনমাউন্ট হয়ে যাবে */}
<ModuleErrorBoundary key={adminSubTab}>
          <SelectedModule {...props} />
        </ModuleErrorBoundary>
        
      </div>
    </div>
  );
}

function SandboxView({
  adminMessages, loading, adminInput, setAdminInput, handleSendAdmin,
  rulesJson, setRulesJson, saveStatus, handleSaveRules,
}: {
  adminMessages: ChatMessage[];
  loading: boolean;
  adminInput: string;
  setAdminInput: (val: string) => void;
  handleSendAdmin: () => void;
  rulesJson: string;
  setRulesJson: (val: string) => void;
  saveStatus: string;
  handleSaveRules: () => void;
}) {
  return (
    <div className="flex-grow flex flex-row overflow-hidden">
      <div className="w-1/2 border-r border-[#00f3ff]/10 flex flex-col bg-[#05070a]/50">
        <div className="h-8 border-b border-slate-850 bg-[#0c0f17] px-4 flex items-center justify-between">
          <span className="text-[10px] font-bold text-slate-400 tracking-wider uppercase font-mono">Sandbox Terminal</span>
        </div>
        <SandboxMessages adminMessages={adminMessages} loading={loading} />
        <SandboxInput adminInput={adminInput} setAdminInput={setAdminInput} handleSendAdmin={handleSendAdmin} />
      </div>
      <div className="w-1/2 flex flex-col bg-[#050608]">
        <SandboxRulesHeader saveStatus={saveStatus} handleSaveRules={handleSaveRules} />
        <SandboxRulesEditor rulesJson={rulesJson} setRulesJson={setRulesJson} />
      </div>
    </div>
  );
}

function SandboxMessages({ adminMessages, loading }: { adminMessages: ChatMessage[]; loading: boolean }) {
  return (
    <div className="flex-grow p-4 overflow-y-auto flex flex-col gap-4">
      {adminMessages.map(msg => (
        <div key={msg.id} className={`max-w-[85%] flex flex-col gap-1 ${msg.sender === 'user' ? 'self-end items-end' : 'self-start'}`}>
          <div className={`p-3 rounded-xl text-xs leading-relaxed ${
            msg.sender === 'user'
              ? 'bg-[#00f3ff] text-[#020205] font-bold shadow-[0_4px_12px_rgba(0,243,255,0.2)]'
              : 'bg-white/[0.02] border border-slate-800 text-[#00ff66] font-mono'
          }`}>
            {msg.text}
          </div>
          <span className="text-[9px] text-slate-400 px-1 font-mono">{msg.timestamp}</span>
        </div>
      ))}
      {loading && (
        <div className="text-xs text-slate-400 animate-pulse font-mono flex items-center gap-2">
          <span className="w-1.5 h-1.5 bg-[#00f3ff] rounded-full animate-bounce"></span>
          Synchronizing Neural Link...
        </div>
      )}
    </div>
  );
}

function SandboxInput({ adminInput, setAdminInput, handleSendAdmin }: { adminInput: string; setAdminInput: (val: string) => void; handleSendAdmin: () => void }) {
  return (
    <div className="p-4 border-t border-slate-800 bg-black/30">
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Input direct testing command to God Layer..."
          value={adminInput}
          onChange={e => setAdminInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSendAdmin()}
          className="flex-grow bg-[#07090f] border border-slate-800 rounded-lg px-4 py-2.5 text-xs text-white focus:outline-none focus:border-[#00f3ff] transition-all font-mono"
        />
        <button
          onClick={handleSendAdmin}
          className="bg-[#00f3ff] text-black font-bold px-4 py-2.5 rounded-lg text-xs uppercase hover:bg-cyan-400 transition-colors font-mono"
        >
          RUN
        </button>
      </div>
    </div>
  );
}

function SandboxRulesHeader({ saveStatus, handleSaveRules }: { saveStatus: string; handleSaveRules: () => void }) {
  return (
    <div className="h-8 border-b border-slate-850 bg-[#0c0f17] px-4 flex items-center justify-between">
      <span className="text-[10px] font-bold text-slate-400 tracking-wider uppercase font-mono">Constitutional Rules</span>
      <div className="flex items-center gap-3">
        {saveStatus && <span className="text-[10px] text-slate-400 font-mono">{saveStatus}</span>}
        <button
          onClick={handleSaveRules}
          className="bg-emerald-500 hover:bg-emerald-400 text-black text-[10px] font-bold px-2 py-0.5 rounded transition-colors font-mono uppercase"
        >
          Apply
        </button>
      </div>
    </div>
  );
}

function SandboxRulesEditor({ rulesJson, setRulesJson }: { rulesJson: string; setRulesJson: (val: string) => void }) {
  return (
    <div className="flex-1 p-3">
      <textarea
        className="w-full h-full bg-black/40 border border-slate-900 rounded-lg p-4 text-[#00ff66] font-mono text-xs leading-relaxed outline-none resize-none focus:border-[#00f3ff]/30 focus:shadow-[0_0_15px_rgba(0,243,255,0.05)] transition-all"
        spellCheck="false"
        value={rulesJson}
        onChange={e => setRulesJson(e.target.value)}
      />
    </div>
  );
}
