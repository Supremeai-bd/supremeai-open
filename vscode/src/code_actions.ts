/**
 * Code actions: Explain / Fix / Refactor selected code with SupremeAI.
 */

import * as vscode from "vscode";

class SupremeAICodeActionProvider implements vscode.CodeActionProvider {
    provideCodeActions(
      _document: vscode.TextDocument,
      range: vscode.Range
    ): vscode.CodeAction[] {
    if (range.isEmpty) return [];
    const explain = new vscode.CodeAction("SupremeAI: Explain selection", vscode.CodeActionKind.QuickFix);
    explain.command = { command: "supremeai.askSelection", title: "Explain" };
    const fix = new vscode.CodeAction("SupremeAI: Fix selection", vscode.CodeActionKind.QuickFix);
    fix.command = { command: "supremeai.askSelection", title: "Fix" };
    return [explain, fix];
  }
}

export function registerCodeActions(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider({ scheme: "file" }, new SupremeAICodeActionProvider(), {
      providedCodeActionKinds: [vscode.CodeActionKind.QuickFix],
    })
  );
}
