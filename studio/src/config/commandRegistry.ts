// SupremeAI Unified Command Registry
// বাংলা মন্তব্য: একটাই command source-of-truth — Admin ও User দুই context-ই এখান থেকে palette পায়।
// CommandBar এই registry consume করে; নতুন command যোগ করতে হলে শুধু এখানে entry দিন।
//
// বাংলা (single-frontend migration, roadmap Phase 6): user navigation commands এখন
// NAVIGATION_REGISTRY (navigationRegistry.ts) থেকে DERIVED হয় — দ্বিতীয় কোনো nav
// route definition এখানে নেই। শুধু palette-specific metadata (title/shortcut override)
// এখানে থাকে, কারণ সেটা command view-র বিষয়, navigation-এর নয়।

import {
  Terminal,
  Cpu,
  Shield,
  Zap,
  Sparkles,
  Layers,
  CreditCard,
  LayoutDashboard,
  Bell,
  HardDrive,
  Server,
  GitMerge,
  BarChart3,
  Settings,
  Users,
} from 'lucide-react';
import type { ElementType } from 'react';
import { getNavigationForContext, type NavEntry } from './navigationRegistry';

export type CommandCategory = 'Navigation' | 'Actions' | 'AI Models' | 'System';
export type PortalType = 'user' | 'admin';

export interface CommandDefinition {
  id: string;
  title: string;
  category: CommandCategory;
  icon: ElementType;
  /** Declarative route — CommandBar navigate() করবে। action না থাকলে required। */
  route?: string;
  /** Non-route custom action (self-heal trigger ইত্যাদি) */
  action?: () => void;
  shortcut?: string;
  /** কোন কোন portal-এ এই command দেখা যাবে */
  portals: PortalType[];
}

// ─── Palette view metadata (titles/shortcuts only — routes live in NAVIGATION_REGISTRY) ───
const NAV_COMMAND_VIEW: Record<string, { title: string; shortcut?: string }> = {
  'nav-workspace': { title: 'User Workspace & Dashboard', shortcut: 'Shift+W' },
  'nav-admin': { title: 'Admin Console (God Mode)', shortcut: 'Shift+M' },
  'nav-ai-studio': { title: 'AI Studio (Live Workspace)' },
  'nav-agents': { title: 'Agent Studio Workspace', shortcut: 'Shift+A' },
  'nav-ide': { title: 'Cloud IDE Workspace', shortcut: 'Shift+I' },
  'nav-swarm': { title: 'Swarm Telemetry & Heatmap', shortcut: 'Shift+S' },
  'nav-evolution-forge': { title: 'Evolution Forge & Genetic Tuning', shortcut: 'Shift+E' },
  'nav-architect-tower': { title: 'Architect Tower' },
  'nav-skills': { title: 'Skills Catalog & Marketplace', shortcut: 'Shift+K' },
  'nav-integrations': { title: 'Cloud Integrations & Vault' },
  'nav-billing': { title: 'Billing & Token Usage' },
  'nav-profile': { title: 'User Profile & Security' },
};

/**
 * বাংলা: registry → command mapping। শুধু implemented route item-ই command হয়;
 * planned item (যেমন /projects) কখনো palette-এ দেখাবে না — dead command নিষিদ্ধ।
 */
function navEntryToCommand(entry: NavEntry, portals: PortalType[]): CommandDefinition | null {
  if (entry.kind !== 'route') return null;
  const view = NAV_COMMAND_VIEW[entry.id];
  return {
    id: entry.id,
    title: view?.title ?? entry.label,
    category: 'Navigation',
    icon: entry.icon,
    route: entry.path,
    shortcut: view?.shortcut,
    portals,
  };
}

// Context-switch commands (shared) — এগুলো sidebar registry-তে নেই কারণ এগুলোর কাজ
// context switch; 'nav-home' (/workspace) ইতিমধ্যে 'nav-workspace' দিয়ে প্রকাশিত।
const SHARED_NAV_COMMANDS: CommandDefinition[] = [
  {
    id: 'nav-workspace',
    title: NAV_COMMAND_VIEW['nav-workspace'].title,
    category: 'Navigation',
    icon: LayoutDashboard,
    route: '/workspace',
    shortcut: NAV_COMMAND_VIEW['nav-workspace'].shortcut,
    portals: ['user', 'admin'],
  },
  {
    id: 'nav-admin',
    title: NAV_COMMAND_VIEW['nav-admin'].title,
    category: 'Navigation',
    icon: Shield,
    route: '/admin',
    shortcut: NAV_COMMAND_VIEW['nav-admin'].shortcut,
    portals: ['admin'],
  },
];

// User nav commands — NAVIGATION_REGISTRY থেকে generated (single source of truth)।
const USER_NAV_COMMANDS: CommandDefinition[] = getNavigationForContext('user')
  .flatMap((group) => group.items)
  .filter((entry) => !(entry.kind === 'route' && entry.id === 'nav-home')) // covered by nav-workspace
  .map((entry) => navEntryToCommand(entry, ['user']))
  .filter((c): c is CommandDefinition => c !== null);

export const COMMAND_REGISTRY: CommandDefinition[] = [
  // ─── Navigation: context switches + registry-derived user nav ──────
  ...SHARED_NAV_COMMANDS,
  ...USER_NAV_COMMANDS,

  // ─── Actions ──────────────────────────────────────────────────────
  {
    id: 'action-heal',
    title: 'Trigger Autonomous Self-Healer',
    category: 'Actions',
    icon: Zap,
    shortcut: 'Ctrl+H',
    action: () => { window.dispatchEvent(new CustomEvent('supremeai-command-action', { detail: 'self-heal' })); },
    portals: ['user', 'admin'],
  },
  {
    id: 'action-gap',
    title: 'Run Gap Finder Codebase Audit',
    category: 'Actions',
    icon: Shield,
    action: () => { window.dispatchEvent(new CustomEvent('supremeai-command-action', { detail: 'gap-finder' })); },
    portals: ['admin'],
  },
  {
    id: 'action-distill',
    title: 'Inject Multi-Model Knowledge Vector',
    category: 'Actions',
    icon: Layers,
    action: () => { window.dispatchEvent(new CustomEvent('supremeai-command-action', { detail: 'knowledge-injection' })); },
    portals: ['admin'],
  },

  // ─── AI Models ────────────────────────────────────────────────────
  {
    id: 'model-deepseek',
    title: 'Switch to SupremeAI Deep (Coding Expert)',
    category: 'AI Models',
    icon: Cpu,
    action: () => { console.warn('Switched to SupremeAI Deep'); },
    portals: ['user', 'admin'],
  },
  {
    id: 'model-kimi',
    title: 'Switch to SupremeAI Reason (Bangla & Reasoning)',
    category: 'AI Models',
    icon: Sparkles,
    action: () => { console.warn('Switched to SupremeAI Reason'); },
    portals: ['user', 'admin'],
  },

  // ─── Admin Console Modules (God Mode subtabs) ─────────────────────
  ...([
    ['admin-nav-dashboard', 'Admin: Dashboard Overview', LayoutDashboard],
    ['admin-nav-alerts', 'Admin: System Alerts & Diagnostics', Bell],
    ['admin-nav-interactive-chat', 'Admin: Interactive Chat (Browser & Terminal)', Terminal],
    ['admin-nav-command-center', 'Admin: SupremeAI Nexus (Canvas)', Layers],
    ['admin-nav-logs', 'Admin: Real-time Logs', Terminal],
    ['admin-nav-costs', 'Admin: Cost Auditor', CreditCard],
    ['admin-nav-health', 'Admin: Health Map', Zap],
    ['admin-nav-users', 'Admin: User Manager / Agents', Users],
    ['admin-nav-config', 'Admin: Config Editor', Settings],
    ['admin-nav-model-router', 'Admin: Model Router', Cpu],
    ['admin-nav-skills', 'Admin: Skill Marketplace', Sparkles],
    ['admin-nav-memory', 'Admin: Memory Browser', HardDrive],
    ['admin-nav-cloud', 'Admin: Cloud Orchestrator', Server],
    ['admin-nav-observability', 'Admin: Observability', BarChart3],
    ['admin-nav-threats', 'Admin: Threat Detection', Shield],
    ['admin-nav-rules', 'Admin: Rules Builder', Settings],
    ['admin-nav-cicd', 'Admin: CI/CD Pipelines', GitMerge],
    ['admin-nav-github', 'Admin: GitHub Integration', GitMerge],
    ['admin-nav-backups', 'Admin: Backup & Restore', HardDrive],
    ['admin-nav-rate-limits', 'Admin: Rate Limits', Zap],
    ['admin-nav-security-dashboard', 'Admin: Security & Memory Dashboard', Shield],
  ] as Array<[string, string, ElementType]>).map(([id, title, icon]) => ({
    id,
    title,
    category: 'System' as CommandCategory,
    icon,
    action: () => dispatchAdminSubtab(id.replace('admin-nav-', '')),
    portals: ['admin'] as PortalType[],
  })),
];

/** বাংলা মন্তব্য: Admin console-এর ভেতরের subtab navigation-এর জন্য shared event */
export const ADMIN_SUBTAB_EVENT = 'supremeai-admin-subtab';

export function dispatchAdminSubtab(tabId: string): void {
  window.dispatchEvent(new CustomEvent(ADMIN_SUBTAB_EVENT, { detail: tabId }));
}

/**
 * বাংলা মন্তব্য: নির্দিষ্ট portal-এর জন্য filtered command list।
 * CommandBar ও ভবিষ্যৎের অন্য consumer-রা এটাই ব্যবহার করবে।
 */
export function getCommandsForPortal(portal: PortalType): CommandDefinition[] {
  return COMMAND_REGISTRY.filter((cmd) => cmd.portals.includes(portal));
}

/**
 * বাংলা (single-frontend migration, roadmap Phase 1): এক বিল্ডে User + Admin দুইই থাকে,
 * তাই portal এখন BUILD-TIME env নয় — RUNTIME route context থেকে detect হয়।
 * /admin/* context-এ admin commands, বাকি সব জায়গায় user commands।
 */
export function getCurrentPortal(): PortalType {
  if (typeof window !== 'undefined' && window.location.pathname.startsWith('/admin')) {
    return 'admin';
  }
  return 'user';
}
