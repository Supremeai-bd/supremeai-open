import * as vscode from 'vscode';

export class SupremeAIActionProvider implements vscode.CodeActionProvider<vscode.CodeAction> {
    // Map to keep track of lines that have an active SupremeAI patch.
    // In a real implementation, you might map filePath -> array of patched lines.
    // We will keep it simple and register globally, but the UI should only trigger on active patches.
    // Since we are applying a diff view, the original file hasn't changed.

    public provideCodeActions(document: vscode.TextDocument, range: vscode.Range | vscode.Selection, context: vscode.CodeActionContext, token: vscode.CancellationToken): any {
        // We only provide this action if there are diagnostics indicating an error
        const hasError = context.diagnostics.some(d => d.severity === vscode.DiagnosticSeverity.Error);

        if (!hasError) {
            return [];
        }

        const action = new vscode.CodeAction('💡 Ask SupremeAI to explain this fix', vscode.CodeActionKind.QuickFix);
        action.command = {
            command: 'supremeai.explainFix',
            title: 'Explain Fix',
            arguments: [document.uri, range.start.line]
        };
        action.isPreferred = true;

        return [action];
    }
}

