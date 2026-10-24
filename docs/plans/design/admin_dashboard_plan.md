---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto-admin_dashboard_plan
subject: "SupremeAI Admin Dashboard: Mission Command Plan"
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI Admin Dashboard: Mission Command Plan

## Phase 1: Overview Tab Overhaul (Mission Command Center)

### 1. Visual Architecture
- **Theme**: "True Dark" (`#050505`) with Glassmorphism overlays (`backdrop-filter: blur(20px)`).
- **Layout**: 4-level hierarchical grid using `grid-template-areas`.
  - **Level 1 (Top)**: `TelemetryBar` - High-level system vitals (Uptime, Latency, Load, Active Nodes).
  - **Level 2 (Stats)**: `GlassKPICard` row - 5 distinct KPI cards (Neural Capacity, Active Agents, Throughput, System Latency, Active Ports).
  - **Level 3 (Main)**: `NeuralTerminal` (Left/Center) + `ResourceGauges` (Right Sidebar).
  - **Level 4 (Footer)**: `SystemHealthMatrix` - Low-level node status indicators.

### 2. Functional Improvements
- **Zero-Overlap Guarantee**: Use fixed-height containers with `overflow: hidden` or `custom-scrollbar` to prevent layout shifts.
- **Dynamic Data Injection**: Transition from hardcoded demo stats to real data from the `/api/admin/dashboard/contract` endpoint.
- **Micro-Animations**: Implement subtle glitch effects and hover-scaling for premium feel.

### 3. Component Tasks
- [ ] Stabilize `dashboard-grid` CSS in `index.css`.
- [ ] Refactor `AdminDashboardUnified.tsx` to use the standardized grid areas.
- [ ] Implement `SystemHealthMatrix` for high-density node status viewing.
- [ ] Connect `NeuralTerminal` to the WebSocket stream (`/topic/notifications`).

---

## Phase 2: Dynamic AI Provider Hub (Zero-Hardcoding)

### 1. Core Paradigm
- **Registry-First**: No model names are hardcoded in the frontend or backend.
- **Internet Discovery**: Integrated search that queries public AI registries (e.g., OpenRouter, HuggingFace, ModelSearch API) to fetch metadata.
- **Life-Cycle Tracking**:
  - `ACTIVE`: Key validated and working.
  - `LIMIT_EXCEEDED`: API returning 429.
  - `DEAD`: Key revoked or provider offline.
- **Accountability**: Each API key entry is tagged with the user's email for tracing ownership.

### 2. Implementation Strategy
- **Frontend (`APIManagement.tsx`)**:
  - Multi-step wizard for adding new models (Search -> Select -> Configure -> Test).
  - Live Telemetry Table showing usage vs limits per model.
  - "Pulse Check" button to manually trigger a connectivity test.
- **Backend (`AIProviderDiscoveryService.java`)**:
  - `discover(String query)`: Proxy search to internet registries.
  - `validate(ApiKey key)`: Perform a "hello world" request to verify the key.
  - `trackUsage(ApiKey key)`: Log usage timestamps and response status for dead/alive detection.

---

## Technical Targets
- **Font**: Inter for UI, JetBrains Mono for data/terminal.
- **Colors**: 
  - Primary: Emerald-500 (`#10b981`)
  - Info: Blue-500 (`#3b82f6`)
  - Warning: Amber-500 (`#f59e0b`)
  - Error: Red-500 (`#ef4444`)
- **Performance**: Virtualized list for the terminal to handle high-frequency log updates without lag.