import React, { Suspense, lazy } from 'react';
import { useCommandCenterStore } from '../state/useCommandCenterStore';
import { EmptyState } from '../kit';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Workspace Viewport
// বাংলা মন্তব্য: অ্যাক্টিভ মডিউল ভিউপোর্ট — React.lazy code-splitting
// ═══════════════════════════════════════════════════════════════════════════

// Lazy-loaded module components (code-splitting per module with defensive fallback)
// বাংলা মন্তব্য: মডিউলগুলো named export ব্যবহার করে — lazyModule হেল্পার `m.default || m[key]`
// ফলব্যাক সিমান্টিক্স ঠিক রেখে টাইপ-সেফ lazy লোড দেয়।
type ModuleNamespace<K extends string> = { [P in K]: React.ComponentType } & { default?: React.ComponentType };

function lazyModule<K extends string>(
  load: () => Promise<ModuleNamespace<K>>,
  key: K,
): React.LazyExoticComponent<React.ComponentType> {
  return lazy(() => load().then(m => ({ default: m.default || m[key] })));
}

const CommandDeck = lazyModule(() => import('../modules/deck/CommandDeck'), 'CommandDeck');
const LiveMetrics = lazyModule(() => import('../modules/observe/LiveMetrics'), 'LiveMetrics');
const LiveLogs = lazyModule(() => import('../modules/observe/LiveLogs'), 'LiveLogs');
const EventsExplorer = lazyModule(() => import('../modules/observe/EventsExplorer'), 'EventsExplorer');
const CICDPipelines = lazyModule(() => import('../modules/observe/CICDPipelines'), 'CICDPipelines');
const HealthMap = lazyModule(() => import('../modules/observe/HealthMap'), 'HealthMap');
const TrafficMonitor = lazyModule(() => import('../modules/observe/TrafficMonitor'), 'TrafficMonitor');
const EvolutionPanel = lazyModule(() => import('../modules/observe/EvolutionPanel'), 'EvolutionPanel');
const Agents = lazyModule(() => import('../modules/operate/Agents'), 'Agents');
const Swarm = lazyModule(() => import('../modules/operate/Swarm'), 'Swarm');
const TasksQueues = lazyModule(() => import('../modules/operate/TasksQueues'), 'TasksQueues');
const Sessions = lazyModule(() => import('../modules/operate/Sessions'), 'Sessions');
const TenantsUsers = lazyModule(() => import('../modules/operate/TenantsUsers'), 'TenantsUsers');
const ModelRouter = lazyModule(() => import('../modules/build/ModelRouter'), 'ModelRouter');
const Providers = lazyModule(() => import('../modules/build/Providers'), 'Providers');
const Skills = lazyModule(() => import('../modules/build/Skills'), 'Skills');
const MemoryKnowledge = lazyModule(() => import('../modules/build/MemoryKnowledge'), 'MemoryKnowledge');
const Threats = lazyModule(() => import('../modules/secure/Threats'), 'Threats');
const AuditExplorer = lazyModule(() => import('../modules/secure/AuditExplorer'), 'AuditExplorer');
const ApprovalQueue = lazyModule(() => import('../modules/secure/ApprovalQueue'), 'ApprovalQueue');
const RulesPolicy = lazyModule(() => import('../modules/secure/RulesPolicy'), 'RulesPolicy');
const SecretsHealth = lazyModule(() => import('../modules/secure/SecretsHealth'), 'SecretsHealth');
const RateLimits = lazyModule(() => import('../modules/secure/RateLimits'), 'RateLimits');
const CostAuditor = lazyModule(() => import('../modules/money/CostAuditor'), 'CostAuditor');
const UsageBilling = lazyModule(() => import('../modules/money/UsageBilling'), 'UsageBilling');
const ROISavings = lazyModule(() => import('../modules/money/ROISavings'), 'ROISavings');
const ConfigEditor = lazyModule(() => import('../modules/system/ConfigEditor'), 'ConfigEditor');
const FeatureFlags = lazyModule(() => import('../modules/system/FeatureFlags'), 'FeatureFlags');
const Workspaces = lazyModule(() => import('../modules/system/Workspaces'), 'Workspaces');
const Backups = lazyModule(() => import('../modules/system/Backups'), 'Backups');
const DeployGate = lazyModule(() => import('../modules/system/DeployGate'), 'DeployGate');

const MODULE_MAP: Record<string, React.LazyExoticComponent<React.ComponentType>> = {
  deck: CommandDeck,
  metrics: LiveMetrics,
  logs: LiveLogs,
  events: EventsExplorer,
  ci: CICDPipelines,
  health: HealthMap,
  traffic: TrafficMonitor,
  evolution: EvolutionPanel,
  agents: Agents,
  swarm: Swarm,
  tasks: TasksQueues,
  sessions: Sessions,
  tenants: TenantsUsers,
  router: ModelRouter,
  providers: Providers,
  skills: Skills,
  memory: MemoryKnowledge,
  threats: Threats,
  audit: AuditExplorer,
  approvals: ApprovalQueue,
  rules: RulesPolicy,
  secrets: SecretsHealth,
  ratelimits: RateLimits,
  cost: CostAuditor,
  usage: UsageBilling,
  roi: ROISavings,
  config: ConfigEditor,
  flags: FeatureFlags,
  workspaces: Workspaces,
  backups: Backups,
  deploy: DeployGate,
};

export function WorkspaceViewport() {
  const { activeModule } = useCommandCenterStore();
  const ModuleComponent = MODULE_MAP[activeModule];

  return (
    <main className="flex-1 overflow-y-auto p-4">
      <Suspense
        fallback={
          <div className="flex items-center justify-center h-full">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#00f3ff]/30 border-t-[#00f3ff]" />
          </div>
        }
      >
        {ModuleComponent ? (
          <ModuleComponent />
        ) : (
          <EmptyState title="মডিউল পাওয়া যায়নি" message="এই মডিউলটি এখনো তৈরি হয়নি।" />
        )}
      </Suspense>
    </main>
  );
}
