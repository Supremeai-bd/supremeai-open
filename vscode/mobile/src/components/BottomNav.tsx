import React from "react";

export type MobileTab = "chat" | "runs" | "agents" | "inbox" | "more";

const TABS: { id: MobileTab; label: string }[] = [
  { id: "chat", label: "Chat" },
  { id: "runs", label: "Runs" },
  { id: "agents", label: "Agents" },
  { id: "inbox", label: "Inbox" },
  { id: "more", label: "More" },
];

export interface BottomNavProps {
  active: MobileTab;
  onChange: (tab: MobileTab) => void;
}

export function BottomNav({ active, onChange }: BottomNavProps) {
  return (
    <nav className="fixed bottom-0 left-0 right-0 flex border-t border-slate-800 bg-slate-900">
      {TABS.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`flex-1 py-2 text-xs ${active === t.id ? "text-sky-400" : "text-slate-400"}`}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}
