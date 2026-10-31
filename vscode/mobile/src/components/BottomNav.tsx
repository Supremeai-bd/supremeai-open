import React from "react";

export type NavTab = "chat" | "runs" | "agents" | "inbox" | "more";

const TABS: { id: NavTab; label: string; icon: string }[] = [
  { id: "chat", label: "Chat", icon: "💬" },
  { id: "runs", label: "Runs", icon: "⚡" },
  { id: "agents", label: "Agents", icon: "🤖" },
  { id: "inbox", label: "Inbox", icon: "📥" },
  { id: "more", label: "More", icon: "⚙️" },
];

export interface BottomNavProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
}

export const BottomNav: React.FC<BottomNavProps> = ({ activeTab, onSelectTab }) => {
  return (
    <nav
      style={{
        display: "flex",
        borderTop: "1px solid #1e293b",
        backgroundColor: "#0f172a",
        padding: "6px 0",
      }}
    >
      {TABS.map((t) => {
        const isActive = activeTab === t.id;
        return (
          <button
            key={t.id}
            onClick={() => onSelectTab(t.id)}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "2px",
              padding: "4px 0",
              background: "none",
              border: "none",
              cursor: "pointer",
              color: isActive ? "#38bdf8" : "#94a3b8",
              fontSize: "11px",
              fontWeight: isActive ? 600 : 400,
            }}
          >
            <span style={{ fontSize: "16px" }}>{t.icon}</span>
            <span>{t.label}</span>
          </button>
        );
      })}
    </nav>
  );
};
