/**
 * Command: SupremeAI: View Active PR Runway
 */

import * as vscode from "vscode";
import { McpBridge, RunwayItem } from "../mcp_bridge";

export async function runwayStatusCommand(bridge: McpBridge): Promise<void> {
  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "Querying SupremeAI PR Runway...",
      cancellable: false,
    },
    async () => {
      const items = await bridge.fetchRunway();
      if (!items || items.length === 0) {
        vscode.window.showInformationMessage("SupremeAI Runway: 0 active PRs in flight. Runway is clear.");
        return;
      }

      const quickPickItems = items.map((item: RunwayItem) => {
        let icon = "$(pass)";
        if (item.ciStatus === "fail") icon = "$(error)";
        if (item.ciStatus === "pending") icon = "$(sync~spin)";

        return {
          label: `${icon} [${item.stage.toUpperCase()}] ${item.repo}`,
          description: item.title,
          detail: `ID: ${item.id} | Author: ${item.author} | CI: ${item.ciStatus.toUpperCase()}`,
        };
      });

      vscode.window.showQuickPick(quickPickItems, {
        placeHolder: `SupremeAI Runway: ${items.length} active PR(s) in gates`,
        title: "Active Federation Pull Requests",
      });
    }
  );
}
