// SupremeAI — Navigation Registry (single-frontend migration, roadmap Phase 6)
// বাংলা মন্তব্য: এটিই একমাত্র navigation source of truth। User sidebar, Admin sidebar
// এবং command registry — সবাই এখান থেকে generate হয়। দ্বিতীয় কোনো nav definition লেখা
// যাবে না (roadmap Rule 8/§11)।
//
// নিয়ম:
// - প্রতিটি visible item অবশ্যই implemented route/action নির্দেশ করবে — মৃত লিংক নিষিদ্ধ।
// - status: 'implemented' আইটেম registry-তে থাকে কিন্তু রেন্ডার হয় না (roadmap §11:
//   "Do not silently leave dead navigation" + unauthorized/planned UI available
//   functionality হিসেবে দেখানো যাবে না)।
// - roles field শুধু কোন context-এ দেখানো হবে তা ঠিক করে — privilege দেয় না।

import {
  Home,
  MessageSquare,
  MessagesSquare,
  Library,
  Cpu,
  Box,
  Plug,
  Zap,
  CreditCard,
  Clock,
  KeyRound,
  Activity,
  Network,
  ServerCog,
  BrainCircuit,
  BookOpen,
  Shield,
  FileCheck2,
  AlertTriangle,
  GitMerge,
  RefreshCcw,
  Users,
  DollarSign,
  Search,
  Wrench,
  Terminal,
  type LucideIcon,
} from 'lucide-react';
import type { Role } from './permissions';

export type NavContext = 'user' | 'admin';

export type NavItemStatus = 'implemented' | 'planned' | 'deprecated';

export interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Route-target item — must match a real route in App.tsx. */
  kind: 'route';
  path: string;
  /** Which contexts may SEE this item (UX only; backend remains authoritative). */
  contexts: NavContext[];
  /** Admin step-up is enforced separately inside AdminShell. */
  requiredRole?: Role;
  requiredPermission?: string;
  status: NavItemStatus;
  /** Lower renders first within its group. */
  priority?: number;
}

export interface NavActionItem {
  id: string;
  label: string;
  icon: LucideIcon;
  /** In-context action (e.g. admin subtab switch) — no navigation. */
  kind: 'action';
  /** Event/action id dispatched to the owning context (admin subtab id). */
  actionId: string;
  contexts: NavContext[];
  requiredRole?: Role;
  requiredPermission?: string;
  status: NavItemStatus;
  priority?: number;
}

export type NavEntry = NavItem | NavActionItem;

export interface NavGroup {
  id: string;
  label: string;
  contexts: NavContext[];
  items: NavEntry[];
}

// ─────────────────────────────────────────────────────────────────────────
// Registry
// ─────────────────────────────────────────────────────────────────────────

export const NAVIGATION_REGISTRY: NavGroup[] = [
  {
    id: 'build',
    label: 'Build',
    contexts: ['user'],
    items: [
      { id: 'nav-home', label: 'Home', icon: Home, kind: 'route', path: '/workspace', contexts: ['user'], status: 'implemented', priority: 10 },
      // M10 (issue #453) বাংলা: Tier-S ChatInterface host — /chat রুটে মাউন্ট করা
      // হয়েছে; share/export/search/slash/branch ফিচারগুলোর প্রথম লাইভ হোম।
      // FIX(nav-truth 2026-10-24): user-context "Chat" pointed at the public guest
      // chat (/chat) — logged-in users landed on the guest surface with
      // Sign-in/Get-started chrome. It now targets the shared unified chat surface.
      { id: 'nav-chat', label: 'Chat', icon: MessagesSquare, kind: 'route', path: '/workspace/live', contexts: ['user'], status: 'implemented', priority: 15 },
      { id: 'nav-ai-studio', label: 'AI Studio', icon: MessageSquare, kind: 'route', path: '/workspace/live', contexts: ['user'], status: 'implemented', priority: 20 },
      // FIX(nav-truth 2026-10-24): no route for /workspace/agent in App.tsx or
      // workspaceFeatureRoutes — 'planned' (hidden) until a real route lands.
      { id: 'nav-agents', label: 'Agents', icon: Cpu, kind: 'route', path: '/workspace/agent', contexts: ['user'], status: 'planned', priority: 30 },
      // Planned features — routes not yet implemented; rendered হয় না (dead-link prevention)।
      { id: 'nav-projects', label: 'Projects', icon: Box, kind: 'route', path: '/projects', contexts: ['user'], status: 'implemented', priority: 40 },
      { id: 'nav-activity', label: 'Activity', icon: Activity, kind: 'route', path: '/activity', contexts: ['user'], status: 'implemented', priority: 50 },
      // Parity-audit fixes: Tier-S প্যানেলগুলো রাউটেড ছিল কিন্তু nav rail-এ ছিল না —
      // ইউজার শুধু সরাসরি URL দিয়ে পৌঁছাতে পারত। এখন implemented status-এ exposed।
      // FIX(nav-truth 2026-10-28 #1521): the promised route landed — /research
      // is now registered in workspaceFeatureRoutes (DeepResearchPanel inside
      // WorkspaceLayout, ProtectedRoute). Status flipped to 'implemented' per
      // this registry's own dead-link contract ('planned' only until a real
      // route lands); routeParity.test enforces the pairing from here on.
      { id: 'nav-research', label: 'Deep Research', icon: Search, kind: 'route', path: '/research', contexts: ['user'], status: 'implemented', priority: 60 },
      // FIX(nav-truth 2026-10-28 #1521): same landing as /research above —
      // /scheduled-tasks registered (ScheduledTasksPanel inside WorkspaceLayout,
      // ProtectedRoute); 'planned' → 'implemented'.
      { id: 'nav-scheduled-tasks', label: 'Scheduled Tasks', icon: Clock, kind: 'route', path: '/scheduled-tasks', contexts: ['user'], status: 'implemented', priority: 70 },
      // বাংলা মন্তব্য: Task-12 ghost activation — KnowledgePage আগে dead ছিল; এখন
      // /knowledge route + backend POST /api/knowledge/search|seed দুটিই real, তাই
      // implemented স্ট্যাটাসে registry-তে exposed করা হলো (dead-link prevention মেনে)।
      { id: 'nav-knowledge', label: 'Knowledge', icon: BookOpen, kind: 'route', path: '/knowledge', contexts: ['user'], status: 'implemented', priority: 80 },
      // M10 (issue #453) বাংলা: /prompt-library রুট ও পেজ বহুদিন ছিল, কিন্তু nav
      // entry ছিল না — navigation truth ফাঁক বন্ধ হলো।
      { id: 'nav-prompt-library', label: 'Prompt Library', icon: Library, kind: 'route', path: '/prompt-library', contexts: ['user'], status: 'implemented', priority: 85 },
    ],
  },
  {
    id: 'extend',
    label: 'Extend',
    contexts: ['user'],
    items: [
      // FIX(nav-truth 2026-10-24): no route for /skills-catalog in App.tsx or
      // workspaceFeatureRoutes — 'planned' (hidden) until a real route lands.
      { id: 'nav-skills', label: 'Skills', icon: Box, kind: 'route', path: '/skills-catalog', contexts: ['user'], status: 'planned', priority: 10 },
      // FIX(nav-truth 2026-10-24): no /integrations route or page exists yet —
      // dead-link prevention (registry header rule) moves it to 'planned' (hidden)
      // until a real route lands.
      { id: 'nav-integrations', label: 'Integrations', icon: Plug, kind: 'route', path: '/integrations', contexts: ['user'], status: 'planned', priority: 20 },
      { id: 'nav-marketplace', label: 'Marketplace', icon: Plug, kind: 'route', path: '/marketplace', contexts: ['user'], status: 'implemented', priority: 30 },
    ],
  },
  {
    id: 'observe',
    label: 'Observe',
    contexts: ['user'],
    items: [
      // Advanced operational surfaces remain routable for compatibility, but are
      // intentionally kept out of the regular user navigation during simplification.
      { id: 'nav-swarm', label: 'Swarm Map', icon: Network, kind: 'route', path: '/swarm', contexts: ['user'], status: 'deprecated', priority: 10 },
      { id: 'nav-evolution-forge', label: 'Evolution Forge', icon: Zap, kind: 'route', path: '/evolution-forge', contexts: ['user'], status: 'deprecated', priority: 20 },
      { id: 'nav-architect-tower', label: 'Architect Tower', icon: BrainCircuit, kind: 'route', path: '/architect-tower', contexts: ['user'], status: 'deprecated', priority: 30 },
      { id: 'nav-runs', label: 'Runs', icon: Zap, kind: 'route', path: '/runs', contexts: ['user'], status: 'deprecated', priority: 40 },
    ],
  },
  {
    id: 'govern',
    label: 'Govern',
    contexts: ['user'],
    items: [
      // FIX(nav-truth 2026-10-24): no route for /usage in App.tsx or
      // workspaceFeatureRoutes — 'planned' (hidden) until a real route lands.
      { id: 'nav-usage', label: 'Usage', icon: Activity, kind: 'route', path: '/usage', contexts: ['user'], status: 'planned', priority: 10 },
      { id: 'nav-billing', label: 'Billing', icon: CreditCard, kind: 'route', path: '/billing', contexts: ['user'], status: 'implemented', priority: 20 },
    ],
  },
  {
    id: 'account',
    label: 'Account',
    contexts: ['user'],
    items: [
      { id: 'nav-profile', label: 'Profile', icon: Users, kind: 'route', path: '/profile', contexts: ['user'], status: 'implemented', priority: 10 },
      // FIX(nav-truth 2026-10-24): no route for /workspace/ide in App.tsx or
      // workspaceFeatureRoutes — 'planned' (hidden) until a real route lands.
      { id: 'nav-ide', label: 'Code Editor', icon: Wrench, kind: 'route', path: '/workspace/ide', contexts: ['user'], status: 'planned', priority: 20 },
      { id: 'nav-settings', label: 'Settings', icon: Wrench, kind: 'route', path: '/settings', contexts: ['user'], status: 'implemented', priority: 30 },
      // FIX(nav-truth 2026-10-24): no route for /memory in App.tsx or
      // workspaceFeatureRoutes — 'planned' (hidden) until a real route lands.
      { id: 'nav-memory', label: 'Neural Memory', icon: BrainCircuit, kind: 'route', path: '/memory', contexts: ['user'], status: 'planned', priority: 40 },
      // BYOK & Collective Key Vault: registered in workspaceFeatureRoutes to BYOKPage
      { id: 'nav-api-keys', label: 'API Keys (BYOK)', icon: KeyRound, kind: 'route', path: '/settings/api-keys', contexts: ['user'], status: 'implemented', priority: 50 },
    ],
  },
  // বাংলা (P2 রিব্যালেন্স, 2026-10-25 ফ্রন্টএন্ড রিসার্চ রিপোর্ট §6.4/Table 8):
  // আগের ৪ গ্রুপ (Operations 9 / Security 8 / Governance 7 / Core 1) ছিল ভারসাম্যহীন —
  // সবচেয়ে বড় গ্রুপে ৯টি আইটেম স্ক্যান-গভীরতা বাড়াত আর ১-আইটেমের Core গ্রুপ অরফান-এর মতো দেখাত।
  // রিপোর্টের ৬-গ্রুপ মডেল (প্রতি গ্রুপে ২-৬টি, লক্ষ্য ৪-৫): Monitoring / Agents / Deploy /
  // Security / Finance / Config। সব ২৫টি অ্যাকশন এন্ট্রি (id, label, icon, actionId, status)
  // হুবহু অপরিবর্তিত — শুধু গ্রুপ-সদস্যতা ও priority পুনঃসজ্জিত; SubTabContent অপরিবর্তিত।
  {
    id: 'admin-monitoring',
    label: 'Monitoring',
    contexts: ['admin'],
    items: [
      { id: 'admin-nav-overview', label: 'Overview', icon: Activity, kind: 'action', actionId: 'overview', contexts: ['admin'], status: 'implemented', priority: 10 },
      { id: 'admin-nav-topology', label: 'Topology', icon: Network, kind: 'action', actionId: 'topology', contexts: ['admin'], status: 'implemented', priority: 20 },
      { id: 'admin-nav-telemetry', label: 'Telemetry Cockpit', icon: Activity, kind: 'action', actionId: 'telemetry', contexts: ['admin'], status: 'implemented', priority: 30 },
      { id: 'admin-nav-service-explorer', label: 'Service Explorer', icon: ServerCog, kind: 'action', actionId: 'service-explorer', contexts: ['admin'], status: 'implemented', priority: 40 },
      { id: 'admin-nav-rca-intelligence', label: 'RCA / Intelligence', icon: Search, kind: 'action', actionId: 'rca-intelligence', contexts: ['admin'], status: 'implemented', priority: 50 },
    ],
  },
  {
    id: 'admin-agents',
    label: 'Agents',
    contexts: ['admin'],
    items: [
      { id: 'admin-nav-agents-swarm', label: 'Agents / Swarm', icon: BrainCircuit, kind: 'action', actionId: 'agents-swarm', contexts: ['admin'], status: 'implemented', priority: 10 },
      { id: 'admin-nav-mesh-agents', label: 'Mesh Agents', icon: Network, kind: 'action', actionId: 'mesh-agents', contexts: ['admin'], status: 'implemented', priority: 20 },
      { id: 'admin-nav-automation-queue', label: 'Automation Queue', icon: Clock, kind: 'action', actionId: 'automation-queue', contexts: ['admin'], status: 'implemented', priority: 30 },
      { id: 'admin-nav-librarian', label: 'Librarian Queue', icon: FileCheck2, kind: 'action', actionId: 'librarian', contexts: ['admin'], status: 'implemented', priority: 40 },
    ],
  },
  {
    id: 'admin-deploy',
    label: 'Deploy',
    contexts: ['admin'],
    items: [
      // বাংলা: ডেপ্লয় + SRE রেমিডিয়েশন ক্লাস্টার — deploy → reliability → recovery → healing
      // একই অপারেশনাল জীবনচক্র, তাই এক গ্রুপে।
      { id: 'admin-nav-deployments', label: 'Deployments', icon: GitMerge, kind: 'action', actionId: 'deployments', contexts: ['admin'], status: 'implemented', priority: 10 },
      { id: 'admin-nav-site-actions', label: 'Site Actions', icon: Terminal, kind: 'action', actionId: 'site-actions', contexts: ['admin'], status: 'implemented', priority: 20 },
      { id: 'admin-nav-reliability', label: 'Reliability', icon: Zap, kind: 'action', actionId: 'reliability', contexts: ['admin'], status: 'implemented', priority: 30 },
      { id: 'admin-nav-recovery', label: 'Recovery', icon: RefreshCcw, kind: 'action', actionId: 'recovery', contexts: ['admin'], status: 'implemented', priority: 40 },
      { id: 'admin-nav-healing', label: 'Healing Review', icon: RefreshCcw, kind: 'action', actionId: 'healing', contexts: ['admin'], status: 'implemented', priority: 50 },
    ],
  },
  {
    id: 'admin-security',
    label: 'Security',
    contexts: ['admin'],
    items: [
      { id: 'admin-nav-security', label: 'Security', icon: Shield, kind: 'action', actionId: 'security', contexts: ['admin'], status: 'implemented', priority: 10 },
      { id: 'admin-nav-guardrails', label: 'Guardrails', icon: Shield, kind: 'action', actionId: 'guardrails', contexts: ['admin'], status: 'implemented', priority: 20 },
      { id: 'admin-nav-audit', label: 'Audit', icon: FileCheck2, kind: 'action', actionId: 'audit', contexts: ['admin'], status: 'implemented', priority: 30 },
      { id: 'admin-nav-incidents', label: 'Incidents', icon: AlertTriangle, kind: 'action', actionId: 'incidents', contexts: ['admin'], status: 'implemented', priority: 40 },
      { id: 'admin-nav-approvals', label: 'Approvals', icon: FileCheck2, kind: 'action', actionId: 'approvals', contexts: ['admin'], status: 'implemented', priority: 50 },
      { id: 'admin-nav-tenants-rbac', label: 'Tenants / RBAC', icon: Users, kind: 'action', actionId: 'tenants-rbac', contexts: ['admin'], status: 'implemented', priority: 60 },
    ],
  },
  {
    id: 'admin-finance',
    label: 'Finance',
    contexts: ['admin'],
    items: [
      { id: 'admin-nav-finops', label: 'FinOps', icon: DollarSign, kind: 'action', actionId: 'finops', contexts: ['admin'], status: 'implemented', priority: 10 },
      { id: 'admin-nav-platform-vault', label: 'Platform Vault', icon: KeyRound, kind: 'action', actionId: 'platform-vault', contexts: ['admin'], status: 'implemented', priority: 20 },
    ],
  },
  {
    id: 'admin-config',
    label: 'Config',
    contexts: ['admin'],
    items: [
      { id: 'admin-nav-configuration', label: 'Configuration', icon: Wrench, kind: 'action', actionId: 'configuration', contexts: ['admin'], status: 'implemented', priority: 10 },
      { id: 'admin-nav-llm-gateway', label: 'LLM Gateway', icon: BrainCircuit, kind: 'action', actionId: 'llm-gateway', contexts: ['admin'], status: 'implemented', priority: 20 },
      { id: 'admin-nav-command-center', label: 'Core Canvas', icon: Terminal, kind: 'action', actionId: 'command-center', contexts: ['admin'], status: 'implemented', priority: 30 },
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────────
// Selectors
// ─────────────────────────────────────────────────────────────────────────

export interface NavFilterOptions {
  /** Trusted role resolved by the backend; used for UX filtering only. */
  role?: Role | null;
  /** Extra permission strings the viewer holds (backend-resolved). */
  permissions?: string[];
  /** Include non-implemented items (defaults to false — never render dead nav). */
  includePlanned?: boolean;
}

/**
 * বাংলা: context অনুযায়ী registry filter — শুধু implemented + context-valid +
 * permission-valid আইটেম রিটার্ন করে। Role/permission এখানে শুধু visibility —
 * আসল authorization backend-এ হয়।
 */
// Viewer-first contract: keep the normal user navigation understandable. Advanced
// routes may remain reachable by direct URL for compatibility, but they must not
// become part of the viewer mental model without an explicit product requirement.
// OWNER DECISION (2026-10-24, 3-tab progressive disclosure): Home and Prompt
// Library are out of the visible user rail — the customer journey starts on
// Chat; users enable features themselves from Settings/Profile, and the team
// suggests features once they understand each customer's needs. The registry
// entries (and direct URLs) are kept for compatibility; they are simply not
// part of the default viewer model any more.
const SIMPLE_VIEWER_ENTRY_IDS = new Set([
  'nav-chat',
  // FIX(nav-truth 2026-10-24): removed — no /integrations route exists yet.
  'nav-profile',
  'nav-settings',
]);

export function getNavigationForContext(
  context: NavContext,
  options: NavFilterOptions = {}
): NavGroup[] {
  const { role, permissions, includePlanned = false } = options;
  return NAVIGATION_REGISTRY
    .filter((group) => group.contexts.includes(context))
    .map((group) => ({
      ...group,
      items: group.items
        .filter((item) => {
          if (!item.contexts.includes(context)) return false;
          if (context === 'user' && !SIMPLE_VIEWER_ENTRY_IDS.has(item.id)) return false;
          if (!includePlanned && item.status !== 'implemented') return false;
          if (item.requiredRole && role && item.requiredRole !== role) return false;
          if (item.requiredRole && !role) return false;
          if (item.requiredPermission && permissions && permissions.length > 0) {
            if (!permissions.includes(item.requiredPermission)) return false;
          }
          return true;
        })
        .sort((a, b) => (a.priority ?? 100) - (b.priority ?? 100)),
    }))
    .filter((group) => group.items.length > 0);
}

/** Registry entry lookup by id (guards against duplicate ids at dev time). */
export function getNavEntryById(id: string): NavEntry | undefined {
  for (const group of NAVIGATION_REGISTRY) {
    const hit = group.items.find((item) => item.id === id);
    if (hit) return hit;
  }
  return undefined;
}

/** All route paths referenced by implemented route items (used by CI nav gate). */
export function getImplementedRoutePaths(): string[] {
  return NAVIGATION_REGISTRY
    .flatMap((g) => g.items)
    .filter((i): i is NavItem => i.kind === 'route' && i.status === 'implemented')
    .map((i) => i.path);
}
