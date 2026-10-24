import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Puzzle, Network, BrainCircuit, ShieldAlert } from 'lucide-react';
import { cn } from '../../utils/cn';

const navItems = [
  { name: 'Workspace', path: '/workspace', icon: LayoutDashboard },
  { name: 'Integrations', path: '/integrations', icon: Puzzle },
  { name: 'Architect Tower', path: '/architect-tower', icon: ShieldAlert },
  { name: 'Swarm Map', path: '/swarm', icon: Network },
  { name: 'Evolution Forge', path: '/evolution-forge', icon: BrainCircuit },
];

export const Sidebar: React.FC = () => {
  return (
    <div className="flex flex-col h-full w-full py-4">
      <div className="px-6 mb-8 flex items-center space-x-2">
        <div className="bg-[var(--supremeai-color-brand-500)] h-8 w-8 rounded-lg flex items-center justify-center">
          <span className="text-white font-bold text-xs">SAI</span>
        </div>
        <span className="font-bold text-xl tracking-tight text-foreground">SupremeAI</span>
      </div>

      <nav className="flex-1 px-4 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.name}
            to={item.path}
            className={({ isActive }) =>
              cn(
                'flex items-center space-x-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                isActive
                  ? 'bg-[var(--supremeai-color-brand-50)] text-[var(--supremeai-color-brand-600)] dark:bg-[var(--supremeai-color-brand-500)]/10 dark:text-[var(--supremeai-color-brand-500)]'
                  : 'text-[var(--supremeai-color-neutral-500)] hover:text-foreground hover:bg-[var(--supremeai-color-neutral-100)] dark:hover:bg-[var(--supremeai-color-neutral-900)]'
              )
            }
          >
            <item.icon className="w-5 h-5" />
            <span>{item.name}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
};
