/**
 * Command: SupremeAI: Dispatch Task to Federation
 */

import * as vscode from "vscode";
import { McpBridge, TaskDispatchRequest } from "../mcp_bridge";

const FEDERATION_REPOSITORIES = [
  "Supremeai-bd/supremeai-open",
  "Supremeai-bd/supremeai-studio",
  "Supremeai-bd/supremeai-api",
  "Supremeai-bd/supremeai-command",
  "Supremeai-bd/supremeai-skills",
  "Supremeai-bd/supremeai-browser",
  "Supremeai-bd/supremeai-sdk",
  "Supremeai-bd/supremeai-infrastructure",
  "Supremeai-bd/supremeai-vscode",
  "Supremeai-bd/supremeai-core",
  "Supremeai-bd/supremeai",
];

export async function submitTaskCommand(bridge: McpBridge): Promise<void> {
  // 1. Select target repository
  const selectedRepo = await vscode.window.showQuickPick(FEDERATION_REPOSITORIES, {
    placeHolder: "Select target federation repository for this task",
    title: "SupremeAI: Dispatch Task (Step 1/4)",
  });
  if (!selectedRepo) return;

  // 2. Enter task title / summary
  const title = await vscode.window.showInputBox({
    prompt: "Enter task title (e.g. feat(gateway): add token bucket rate limiter)",
    placeHolder: "feat(scope): concise summary of work",
    title: "SupremeAI: Dispatch Task (Step 2/4)",
    validateInput: (text) => (text.trim().length < 5 ? "Title must be at least 5 characters" : null),
  });
  if (!title) return;

  // 3. Enter scope paths (optional auto-populated from active editor)
  const activeDoc = vscode.window.activeTextEditor?.document;
  const defaultPath = activeDoc ? vscode.workspace.asRelativePath(activeDoc.uri) : "";

  const scopeInput = await vscode.window.showInputBox({
    prompt: "Enter declared scope paths (comma-separated)",
    value: defaultPath,
    placeHolder: "src/tools/example.ts, tests/test_example.ts",
    title: "SupremeAI: Dispatch Task (Step 3/4)",
  });
  if (scopeInput === undefined) return;

  const scopePaths = scopeInput
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  // 4. Enter task description / acceptance criteria
  const description = await vscode.window.showInputBox({
    prompt: "Enter task mission and acceptance criteria",
    placeHolder: "Detailed specification for the autonomous agent...",
    title: "SupremeAI: Dispatch Task (Step 4/4)",
  });
  if (!description) return;

  // Dispatch via progress indicator
  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: `Dispatching task to ${selectedRepo}...`,
      cancellable: false,
    },
    async () => {
      const req: TaskDispatchRequest = {
        repo: selectedRepo,
        title,
        scopePaths,
        description,
        priority: "P1-high",
      };

      const result = await bridge.dispatchTask(req);
      if (result.success) {
        vscode.window.showInformationMessage(
          `✅ Task successfully queued on ${selectedRepo} (${result.taskId || "dispatched"}).`
        );
      } else {
        vscode.window.showErrorMessage(`❌ Failed to dispatch task: ${result.error || "Unknown error"}`);
      }
    }
  );
}
