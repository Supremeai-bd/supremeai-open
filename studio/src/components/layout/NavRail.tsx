// apps/studio-client/src/components/layout/NavRail.tsx
// Smart Navigation Rail - Icon & Collapsible Drawer Navigation
// বাংলা মন্তব্য: স্মার্ট সাইড নেভিগেশন রেল — মিনিমাল আইকন মোড ও অটোম্যাটিক অ্যানিমেটেড এক্সপ্যানশন।

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Terminal,
  Folder,
  Cpu,
  Shield,
  Sparkles,
  Layers,
  ChevronLeft,
  ChevronRight,
  Settings,
  HelpCircle,
} from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';

interface NavItem {
  id: string;
  label: string;
  icon: React.ElementType;
  path: string;
}

interface NavGroup {
  id: string;
  label: string;
  items: NavItem[];
}

export const NavRail: React.FC = () => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  // বাংলা মন্তব্য: হোভার বা পিন (chevron) — যেকোনোটায় রেল এক্সপপান্ড হয়।
  const showLabels = isExpanded || isHovered;

  const navGroups: NavGroup[] = [
    {
      id: 'workspace',
      label: 'Workspace',
      items: [
        { id: 'agent', label: 'Agent Studio', icon: Terminal, path: '/workspace/agent' },
        { id: 'ide', label: 'Cloud IDE', icon: Folder, path: '/workspace/ide' },
        { id: 'swarm', label: 'Swarm Map', icon: Cpu, path: '/swarm' },
      ],
    },
    {
      id: 'discover',
      label: 'Discover',
      items: [
        { id: 'architect', label: 'Architect Tower', icon: Shield, path: '/architect-tower' },
        { id: 'skills', label: 'Skill Catalog', icon: Sparkles, path: '/skills-catalog' },
        { id: 'evolution', label: 'Evolution Forge', icon: Layers, path: '/evolution-forge' },
      ],
    },
  ];

  return (
    <motion.aside
      animate={{ width: showLabels ? 220 : 64 }}
      onHoverStart={() => setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      transition={{ type: 'spring', stiffness: 350, damping: 30 }}
      className="relative flex flex-col justify-between h-full border-r border-slate-800 bg-slate-950/95 p-3 select-none z-30"
      aria-label="Primary navigation"
    >
      {/* Top Header & Logo */}
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="h-9 w-9 min-w-9 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white shadow-lg shadow-cyan-500/20">
              S
            </div>
            {showLabels && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="font-semibold text-sm text-slate-100 whitespace-nowrap tracking-wide"
              >
                Supreme<span className="text-cyan-400">AI</span>
              </motion.span>
            )}
          </div>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            aria-label="Toggle Sidebar"
            aria-expanded={showLabels}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          >
            {isExpanded || isHovered ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </div>

        {/* Navigation Rail Items */}
        <nav className="flex flex-col gap-1.5">
          {navGroups.map((group) => (
            <div key={group.id} className="flex flex-col gap-1">
              {showLabels && (
                <span className="px-3 pt-2 text-[10px] uppercase tracking-widest text-slate-600 font-semibold">
                  {group.label}
                </span>
              )}
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname === item.path;

                return (
                  <button
                    key={item.id}
                    onClick={() => navigate(item.path)}
                    className={`relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                      isActive
                        ? 'bg-cyan-500/15 text-cyan-400 font-semibold shadow-inner'
                        : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                    }`}
                  >
                    <Icon className={`h-5 w-5 min-w-5 ${isActive ? 'text-cyan-400' : 'text-slate-400'}`} />
                    {showLabels && (
                      <motion.span
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="whitespace-nowrap overflow-hidden text-ellipsis"
                      >
                        {item.label}
                      </motion.span>
                    )}
                    {isActive && (
                      <motion.div
                        layoutId="activeIndicator"
                        className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-cyan-400"
                      />
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
      </div>

      {/* Bottom Actions */}
      <div className="flex flex-col gap-1 border-t border-slate-800/80 pt-3">
        <button
          onClick={() => navigate('/integrations')}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-slate-400 hover:bg-slate-900 hover:text-slate-200 transition-colors"
        >
          <Settings className="h-5 w-5 min-w-5" />
          {showLabels && (
            <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="whitespace-nowrap">
              Integrations
            </motion.span>
          )}
        </button>

        <button
          onClick={() => window.open('https://github.com/paykaribazaronline/supremeai', '_blank')}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-slate-400 hover:bg-slate-900 hover:text-slate-200 transition-colors"
        >
          <HelpCircle className="h-5 w-5 min-w-5" />
          {showLabels && (
            <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="whitespace-nowrap">
              Documentation
            </motion.span>
          )}
        </button>
      </div>
    </motion.aside>
  );
};

export default NavRail;
