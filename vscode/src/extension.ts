/**
 * SupremeAI VS Code Extension — Main Activation Entrypoint
 */

import * as vscode from "vscode";
import { McpBridge } from "./mcp_bridge";
import { FederationStatusBar } from "./status_bar";
import { SupremeAIChatViewProvider } from "./chat_view";
import { inlineChatCommand } from "./commands/inline_chat";
import { registerCodeActions } from "./code_actions";
import { submitTaskCommand } from "./commands/submit_task";
import { runwayStatusCommand } from "./commands/runway_status";

let statusBar: FederationStatusBar | null = null;
let bridge: McpBridge | null = null;

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration("supremeai");
  const towerUrl = config.get<string>("towerUrl", "https://supremeai-mcp-tower.onrender.com/mcp");
  const refreshSeconds = config.get<number>("autoRefreshSeconds", 30);

  // 1. Initialize MCP Client Bridge
  bridge = new McpBridge(towerUrl);

  // 2. Initialize Status Bar Telemetry
  statusBar = new FederationStatusBar(bridge);
  statusBar.startPolling(refreshSeconds);
  context.subscriptions.push(statusBar);

  // 3. Register Chat Sidebar Webview
  const chatProvider = new SupremeAIChatViewProvider(context);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(SupremeAIChatViewProvider.viewType, chatProvider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );

  // 3. Register Commands
  const dispatchDisposable = vscode.commands.registerCommand("supremeai.dispatchTask", () => {
    if (bridge) {
      submitTaskCommand(bridge);
    }
  });

  const runwayDisposable = vscode.commands.registerCommand("supremeai.viewRunway", () => {
    if (bridge) {
      runwayStatusCommand(bridge);
    }
  });

  const killSwitchDisposable = vscode.commands.registerCommand("supremeai.emergencyStop", async () => {
    const pin = await vscode.window.showInputBox({
      prompt: "Enter Superadmin Emergency PIN to halt all autonomous execution",
      password: true,
      placeHolder: "PIN (minimum 4 digits)",
      validateInput: (text) => (text.length < 4 ? "PIN must be at least 4 digits" : null),
    });

    if (!pin || !bridge) return;

    const confirmed = await vscode.window.showWarningMessage(
      "Are you sure you want to trigger the EMERGENCY KILL-SWITCH across the entire federation?",
      { modal: true },
      "HALT ALL AUTONOMY"
    );

    if (confirmed === "HALT ALL AUTONOMY") {
      const ok = await bridge.triggerEmergencyKill(pin);
      if (ok) {
        vscode.window.showErrorMessage("🚨 EMERGENCY KILL-SWITCH ACTIVATED: All autonomous agent runs paused.");
        if (statusBar) {
          statusBar.refresh();
        }
      } else {
        vscode.window.showErrorMessage("❌ Kill-switch request rejected (invalid PIN or server error).");
      }
    }
  });

  const askSelectionDisposable = vscode.commands.registerCommand("supremeai.askSelection", () => {
    inlineChatCommand();
  });

  const openChatDisposable = vscode.commands.registerCommand("supremeai.openChat", () => {
    vscode.commands.executeCommand("supremeai.chat.focus");
  });

  registerCodeActions(context);

  // 4. Listen to configuration updates
  const configDisposable = vscode.workspace.onDidChangeConfiguration((e) => {
    if (e.affectsConfiguration("supremeai")) {
      const updatedConfig = vscode.workspace.getConfiguration("supremeai");
      const newUrl = updatedConfig.get<string>("towerUrl", "https://supremeai-mcp-tower.onrender.com/mcp");
      const newRefresh = updatedConfig.get<number>("autoRefreshSeconds", 30);

      if (bridge) {
        bridge.updateConfig(newUrl);
      }
      if (statusBar) {
        statusBar.startPolling(newRefresh);
      }
    }
  });

  context.subscriptions.push(dispatchDisposable, runwayDisposable, killSwitchDisposable, askSelectionDisposable, openChatDisposable, configDisposable);
}

export function deactivate(): void {
  if (statusBar) {
    statusBar.dispose();
    statusBar = null;
  }
  bridge = null;
}
