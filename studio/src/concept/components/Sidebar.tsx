import { Activity, Blocks, Code2, Command, LayoutDashboard, Sparkles } from 'lucide-react';
import { BrandMark } from './BrandMark';
import type { NavigationItem, ViewKey } from '../types';

type SidebarProps = {
  active: ViewKey;
  onNavigate: (view: ViewKey) => void;
  onOpenCommand: () => void;
};

const items: NavigationItem[] = [
  { id: 'overview', label: 'Command room', hint: '1' },
  { id: 'studio', label: 'Studio', hint: '2' },
  { id: 'vscode', label: 'VSCode', hint: '3' },
  { id: 'devices', label: 'Device lab', hint: '4' },
];

const icons = {
  overview: LayoutDashboard,
  studio: Sparkles,
  vscode: Code2,
  devices: Blocks,
};

export function Sidebar({ active, onNavigate, onOpenCommand }: SidebarProps) {
  return (
    <aside className="sidebar" aria-label="Main navigation">
      <div className="sidebar-brand"><BrandMark /><span className="build-chip">LIVE CONCEPT</span></div>
      <button className="workspace-switch" type="button" aria-label="Current workspace: SupremeAI Federation">
        <span className="workspace-avatar">S</span>
        <span className="workspace-label"><strong>Federation</strong><small>SupremeAI workspace</small></span>
        <span className="chevron">⌄</span>
      </button>
      <div className="nav-caption">WORKSPACE <span>04</span></div>
      <nav className="primary-nav">
        {items.map((item) => {
          const Icon = icons[item.id];
          return (
            <button
              key={item.id}
              className={`nav-button ${active === item.id ? 'is-active' : ''}`}
              onClick={() => onNavigate(item.id)}
              aria-current={active === item.id ? 'page' : undefined}
              aria-keyshortcuts={item.hint}
            >
              <Icon size={17} strokeWidth={1.8} />
              <span>{item.label}</span>
              <kbd>{item.hint}</kbd>
            </button>
          );
        })}
      </nav>
      <div className="sidebar-spacer" />
      <div className="federation-mini">
        <div className="mini-orbit" aria-hidden="true"><span /><i /><b /></div>
        <div className="mini-orbit-copy"><span>FEDERATION SIGNAL</span><strong><i className="status-dot" /> Demo feed active</strong></div>
        <Activity size={16} className="mini-activity" aria-hidden="true" />
      </div>
      <button className="sidebar-command" type="button" onClick={onOpenCommand} aria-haspopup="dialog">
        <Command size={16} /><span>Quick switch</span><kbd>⌘ K</kbd>
      </button>
      <div className="profile-row">
        <div className="profile-avatar">SA</div>
        <span><strong>SupremeAI</strong><small>Product preview</small></span>
        <span className="profile-menu" aria-hidden="true">···</span>
      </div>
      <div className="mobile-safe-bottom" />
    </aside>
  );
}
