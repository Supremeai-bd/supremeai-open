import React from 'react';
import { useCommandCenterStore } from '../state/useCommandCenterStore';
import { COMMAND_GROUPS } from './moduleIndex';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Left Rail Navigation
// বাংলা মন্তব্য: গ্রুপড নেভিগেশন রেইল — DECK/OPERATE/BUILD/OBSERVE/SECURE/MONEY/SYSTEM
// FIX(single-source): গ্রুপ ডেফিনিশন এখন ./moduleIndex.ts-এ — ⌘K Command
// Palette একই registry ব্যবহার করে, তাই দুই জায়গায় ড্রিফটের সুযোগ নেই।
// ═══════════════════════════════════════════════════════════════════════════

interface LeftRailProps {
  badges?: Partial<Record<string, number>>;
}

export function LeftRail({ badges = {} }: LeftRailProps) {
  const { activeModule, setActiveModule } = useCommandCenterStore();

  return (
    <nav className="w-52 border-r border-[var(--sa-line)] bg-[var(--sa-bg-1)] overflow-y-auto py-3">
      {COMMAND_GROUPS.map((group) => (
        <div key={group.title} className="mb-4">
          <div className="px-3 mb-1 text-[8px] font-mono font-bold tracking-widest text-[var(--sa-text-2)]">
            {group.title}
          </div>
          {group.items.map((item) => {
            const isActive = activeModule === item.module;
            const badge = badges?.[item.id] ?? item.badge;
            return (
              <button
                key={item.id}
                onClick={() => setActiveModule(item.module)}
                className={`w-full flex items-center gap-2.5 px-3 py-1.5 text-left transition-colors ${
                  isActive
                    ? 'bg-[#00f3ff]/10 text-[#00f3ff] border-r-2 border-[#00f3ff]'
                    : 'text-[var(--sa-text-1)] hover:bg-[var(--sa-bg-2)] hover:text-[var(--sa-text-0)]'
                }`}
              >
                <item.icon
                  size={14}
                  className={isActive ? 'text-[#00f3ff]' : 'text-[var(--sa-text-2)]'}
                />
                <span className="text-[10px] font-mono flex-1">{item.label}</span>
                {badge !== undefined && badge > 0 && (
                  <span className="text-[8px] font-mono px-1.5 py-0.5 rounded-full bg-[#ef4444]/20 text-[#ef4444]">
                    {badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
