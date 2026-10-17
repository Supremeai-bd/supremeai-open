# SupremeAI VS Code / Cursor Extension

Official developer workflow bridge and federation telemetry indicator for SupremeAI autonomous agents.

## Features

- **$(cloud) Live Federation Telemetry:** Real-time status bar indicator showing active PR runway status, atomic claim pressure, and autonomous agent tasks.
- **$(play) Palette Task Dispatch:** Dispatch tasks directly from your active editor or workspace to the SupremeAI MCP Control Tower (`supremeai.dispatchTask`).
- **$(list-unordered) PR Runway Viewer:** Inspect active pull requests, CI gate statuses, and self-healing triage directly inside VS Code (`supremeai.viewRunway`).
- **$(stop) Emergency Kill-Switch:** Instant safety kill-switch to pause autonomous execution across the entire federation (`supremeai.emergencyStop`).

## Extension Settings

This extension contributes the following settings:

* `supremeai.towerUrl`: The endpoint URL of the SupremeAI MCP Control Tower (default: `https://supremeai-mcp-tower.onrender.com/mcp`).
* `supremeai.autoRefreshSeconds`: Interval in seconds between telemetry heartbeat checks (default: `30`).
* `supremeai.enableNotifications`: Enable desktop notifications when PR runway gates change state (default: `true`).

## Keybindings & Commands

| Command | Title | Default Shortcut |
|---|---|---|
| `supremeai.dispatchTask` | SupremeAI: Dispatch Task to Federation | `Ctrl+Alt+S D` |
| `supremeai.viewRunway` | SupremeAI: View Active PR Runway | `Ctrl+Alt+S R` |
| `supremeai.emergencyStop` | SupremeAI: Trigger Emergency Autonomy Kill-Switch | `Ctrl+Alt+S K` |

## Architecture & Communication

The extension communicates strictly with the public/authenticated MCP endpoint using JSON-RPC 2.0. Zero sensitive internal monorepo secrets or direct database credentials are bundled.
