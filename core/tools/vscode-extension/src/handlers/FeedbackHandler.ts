/**
 * Feedback Handler - Captures user accept/reject of AI suggestions
 * Sends feedback to backend to improve future suggestions
 */

import * as vscode from 'vscode';
import { getSupremeAIService } from '../services/SupremeAIService';
import { SuggestionFeedback } from '../types';

export class FeedbackHandler {
  private context: vscode.ExtensionContext;
  private pendingSuggestions: Map<string, SuggestionFeedback>; // suggestionId -> feedback

  constructor(context: vscode.ExtensionContext) {
    this.context = context;
    this.pendingSuggestions = new Map();
  }

  register(): void {
    // Register commands for accept/reject
    const acceptCommand = vscode.commands.registerCommand('supremeai.acceptSuggestion', async () => {
      await this.handleAccept();
    });

    const rejectCommand = vscode.commands.registerCommand('supremeai.rejectSuggestion', async () => {
      await this.handleReject();
    });

    const sendFeedbackCommand = vscode.commands.registerCommand('supremeai.sendFeedback', async () => {
      await this.showFeedbackDialog();
    });

    this.context.subscriptions.push(acceptCommand, rejectCommand, sendFeedbackCommand);
    console.log('[SupremeAI] FeedbackHandler registered');
  }

  /**
   * Capture suggestion context before showing inline action
   */
  captureSuggestionContext(
    suggestionId: string,
    taskId: string,
    originalCode: string,
    suggestedCode: string,
    context: string,
    position: vscode.Position // Capture position
  ): void {
    const feedback: SuggestionFeedback = {
      suggestionId,
      taskId,
      accepted: false, // Will be set when user acts
      context,
      originalPosition: position,
      timestamp: new Date().toISOString(),
    };

    this.pendingSuggestions.set(suggestionId, feedback);
    console.log(`[SupremeAI] Captured suggestion context: ${suggestionId}`);
  }

  private async handleAccept(): Promise<void> {
    const activeEditor = vscode.window.activeTextEditor;
    if (!activeEditor) {
      vscode.window.showWarningMessage('No active editor to accept suggestion');
      return;
    }

    // Find pending suggestion for this file/context
    const suggestionId = this.findRelevantSuggestion(activeEditor.document.uri, activeEditor.selection.active);

    if (suggestionId && this.pendingSuggestions.has(suggestionId)) {
      const feedback = this.pendingSuggestions.get(suggestionId)!;
      feedback.accepted = true;
      feedback.modifiedCode = activeEditor.document.getText();

      await this.sendFeedback(feedback);
      vscode.window.showInformationMessage('✅ Feedback sent: Suggestion accepted');

      this.pendingSuggestions.delete(suggestionId);
    } else {
      // No tracked suggestion - create generic accept for current file
      await this.sendGenericFeedback(true, activeEditor.document);
      vscode.window.showInformationMessage('✅ Feedback sent: Changes accepted');
    }
  }

  private async handleReject(): Promise<void> {
    const activeEditor = vscode.window.activeTextEditor;
    if (!activeEditor) {
      vscode.window.showWarningMessage('No active editor to reject suggestion');
      return;
    }

    const suggestionId = this.findRelevantSuggestion(activeEditor.document.uri, activeEditor.selection.active);

    if (suggestionId && this.pendingSuggestions.has(suggestionId)) {
      const feedback = this.pendingSuggestions.get(suggestionId)!;
      feedback.accepted = false;

      await this.sendFeedback(feedback);
      vscode.window.showInformationMessage('✅ Feedback sent: Suggestion rejected');

      this.pendingSuggestions.delete(suggestionId);
    } else {
      await this.sendGenericFeedback(false, activeEditor.document);
      vscode.window.showInformationMessage('✅ Feedback sent: Suggestion rejected');
    }
  }

  private async showFeedbackDialog(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      return;
    }

    const accepted = await vscode.window.showQuickPick(['Yes, it helped', 'No, not useful'], {
      placeHolder: 'Did the AI suggestion improve your code?',
    });

    if (accepted) {
      const feedback: SuggestionFeedback = {
        suggestionId: `manual-${Date.now()}`,
        taskId: `manual-task-${Date.now()}`,
        accepted: accepted === 'Yes, it helped',
        context: `File: ${editor.document.uri.fsPath}`,
        timestamp: new Date().toISOString(),
      };

      await this.sendFeedback(feedback);
    }
  }

  private findRelevantSuggestion(uri: vscode.Uri, position: vscode.Position): string | null {
    let bestMatch: string | null = null;
    let minDistance = Infinity;

    // Find the suggestion whose context is closest to the current cursor position
    for (const [id, feedback] of this.pendingSuggestions.entries()) {
      // A more robust context would include the URI and position/range
      if (feedback.context.includes(uri.fsPath) && feedback.originalPosition) {
        const distance = Math.abs(position.line - feedback.originalPosition.line);
        if (distance < minDistance) {
          minDistance = distance;
          bestMatch = id;
        }
      } else if (feedback.context.includes(uri.fsPath) && !bestMatch) {
        // Fallback for older suggestions without position
        return id;
      }
    }
    return null;
  }

  private async sendFeedback(feedback: SuggestionFeedback): Promise<void> {
    try {
      const service = getSupremeAIService();
      const result = await service.sendSuggestionFeedback(feedback);
      if (result.success) {
        console.log('[SupremeAI] Feedback sent successfully');
      }
    } catch (error: any) {
      console.error(`[SupremeAI] Failed to send feedback: ${error.message}`);
    }
  }

  private async sendGenericFeedback(accepted: boolean, document: vscode.TextDocument): Promise<void> {
    const feedback: SuggestionFeedback = {
      suggestionId: `generic-${Date.now()}`,
      taskId: `generic-task-${Date.now()}`,
      accepted,
      context: `File: ${document.uri.fsPath}, Language: ${document.languageId}`,
      timestamp: new Date().toISOString(),
    };

    await this.sendFeedback(feedback);
  }

  /**
   * Clear pending suggestions (for testing)
   */
  clear(): void {
    this.pendingSuggestions.clear();
  }
}
