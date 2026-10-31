import React, { useState, useEffect } from "react";
import { BottomNav, NavTab } from "./components/BottomNav.js";

export interface MobileAppState {
  activeMissions: number;
  towerHealth: "HEALTHY" | "DEGRADED" | "DOWN";
  lastTelemetryTimestamp: number;
}

export const initialMobileState: MobileAppState = {
  activeMissions: 0,
  towerHealth: "HEALTHY",
  lastTelemetryTimestamp: Date.now(),
};

export function renderMobileStatus(state: MobileAppState = initialMobileState): string {
  return `SupremeAI Mobile Supervisor | Active Missions: ${state.activeMissions} | Health: ${state.towerHealth}`;
}

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>("chat");
  const [state, setState] = useState<MobileAppState>(initialMobileState);
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([
    { role: "assistant", content: "স্বাগতম! SupremeAI Mobile Companion-এ আপনাকে সাহায্য করতে প্রস্তুত।" },
  ]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);

  useEffect(() => {
    // Poll telemetry / health check
    const interval = setInterval(async () => {
      try {
        const res = await fetch("https://supremeai-primary-node.onrender.com/health");
        if (res.ok) {
          setState((prev) => ({ ...prev, towerHealth: "HEALTHY", lastTelemetryTimestamp: Date.now() }));
        } else {
          setState((prev) => ({ ...prev, towerHealth: "DEGRADED", lastTelemetryTimestamp: Date.now() }));
        }
      } catch {
        setState((prev) => ({ ...prev, towerHealth: "DOWN", lastTelemetryTimestamp: Date.now() }));
      }
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleSend = async () => {
    if (!input.trim() || isSending) return;
    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setIsSending(true);

    try {
      const res = await fetch("https://supremeai-api-ulw0.onrender.com/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "auto",
          messages: [{ role: "user", content: userMsg }],
        }),
      });
      if (res.ok) {
        const data = await res.json();
        const reply = data.choices?.[0]?.message?.content || "No response received.";
        setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `⚠️ Gateway error: ${res.statusText || res.status}` },
        ]);
      }
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `⚠️ Network error: ${err.message || "Failed to reach gateway"}` },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", backgroundColor: "#0b0f17", color: "#e2e8f0", fontFamily: "system-ui, sans-serif" }}>
      {/* Top Header */}
      <header style={{ padding: "12px 16px", borderBottom: "1px solid #1e293b", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div style={{ width: "10px", height: "10px", borderRadius: "50%", backgroundColor: state.towerHealth === "HEALTHY" ? "#10b981" : state.towerHealth === "DEGRADED" ? "#f59e0b" : "#ef4444" }} />
          <span style={{ fontWeight: 600, fontSize: "15px" }}>SupremeAI Mobile</span>
        </div>
        <span style={{ fontSize: "12px", color: "#94a3b8" }}>{state.towerHealth}</span>
      </header>

      {/* Main Tab Area */}
      <main style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
        {activeTab === "chat" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {messages.map((m, idx) => (
              <div
                key={idx}
                style={{
                  alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                  backgroundColor: m.role === "user" ? "#2563eb" : "#1e293b",
                  color: "#ffffff",
                  padding: "10px 14px",
                  borderRadius: "12px",
                  maxWidth: "85%",
                  fontSize: "14px",
                  lineHeight: 1.4,
                }}
              >
                {m.content}
              </div>
            ))}
          </div>
        )}

        {activeTab === "runs" && (
          <div>
            <h3 style={{ fontSize: "16px", marginBottom: "8px" }}>Active Runs & Agent Swarm</h3>
            <p style={{ color: "#94a3b8", fontSize: "14px" }}>Active Missions: {state.activeMissions}</p>
          </div>
        )}

        {activeTab === "agents" && (
          <div>
            <h3 style={{ fontSize: "16px", marginBottom: "8px" }}>Agent Supervision & Kill-Switch</h3>
            <p style={{ color: "#94a3b8", fontSize: "14px" }}>Emergency controls and remote supervision enabled.</p>
          </div>
        )}

        {activeTab === "inbox" && (
          <div>
            <h3 style={{ fontSize: "16px", marginBottom: "8px" }}>Notifications & Approvals</h3>
            <p style={{ color: "#94a3b8", fontSize: "14px" }}>No pending approval requests.</p>
          </div>
        )}

        {activeTab === "more" && (
          <div>
            <h3 style={{ fontSize: "16px", marginBottom: "8px" }}>Settings & Account</h3>
            <p style={{ color: "#94a3b8", fontSize: "14px" }}>SupremeAI Mobile Companion v0.2.0 (Capacitor/Android)</p>
          </div>
        )}
      </main>

      {/* Input Box (Only for Chat Tab) */}
      {activeTab === "chat" && (
        <div style={{ padding: "12px 16px", borderTop: "1px solid #1e293b", display: "flex", gap: "8px" }}>
          <input
            type="text"
            placeholder="Type a message or command..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            style={{
              flex: 1,
              backgroundColor: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "8px",
              padding: "8px 12px",
              color: "#ffffff",
              fontSize: "14px",
              outline: "none",
            }}
          />
          <button
            onClick={handleSend}
            disabled={isSending}
            style={{
              backgroundColor: "#2563eb",
              border: "none",
              borderRadius: "8px",
              padding: "8px 16px",
              color: "#ffffff",
              fontWeight: 600,
              fontSize: "14px",
              cursor: "pointer",
            }}
          >
            {isSending ? "..." : "Send"}
          </button>
        </div>
      )}

      {/* Bottom Navigation */}
      <BottomNav activeTab={activeTab} onSelectTab={setActiveTab} />
    </div>
  );
};

export default App;
