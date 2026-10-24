/**
 * Error Handler - Captures errors from VS Code diagnostics
 * Reports compilation, lint, and runtime errors to SupremeAI backend
 */

import * as vscode from 'vscode';
import { getSupremeAIService } from '../services/SupremeAIService';
import { ErrorReport } from '../types';

export class ErrorHandler {
  private context: vscode.ExtensionContext;
  private reportedErrors: Set<string>; // Deduplication using file:line:col hash

  constructor(context: vscode.ExtensionContext) {
    this.context = context;
    this.reportedErrors = new Set<string>();
  }

  register(): void {
    // Listen to diagnostic collection changes
    vscode.languages.onDidChangeDiagnostics(this.onDiagnosticsChanged, this);

    console.log('[SupremeAI] ErrorHandler registered');
  }

  private onDiagnosticsChanged(event: vscode.DiagnosticChangeEvent): void {
    for (const uri of event.uris) {
      const diagnostics = vscode.languages.getDiagnostics(uri);
      for (const diagnostic of diagnostics) {
        this.processDiagnostic(uri, diagnostic);
      }
    }
  }

  private processDiagnostic(uri: vscode.Uri, diagnostic: vscode.Diagnostic): void {
    const filePath = uri.fsPath;
    const range = diagnostic.range;
    const lineNumber = range.start.line + 1;
    const columnNumber = range.start.character + 1;

    // Create unique key for deduplication
    const errorKey = `${filePath}:${lineNumber}:${columnNumber}:${diagnostic.message}`;

    if (this.reportedErrors.has(errorKey)) {
      return; // Already reported
    }

    const severity = this.mapSeverity(diagnostic.severity);
    const errorType = this.classifyError(diagnostic);

    const report: ErrorReport = {
      errorType,
      errorMessage: diagnostic.message,
      errorCode: diagnostic.code?.toString(),
      filePath,
      lineNumber,
      columnNumber,
      severity,
      timestamp: new Date().toISOString(),
    };

    // Send to backend
    this.sendErrorReport(report);
    this.reportedErrors.add(errorKey);
  }

  private pendingReports: ErrorReport[] = [];

  private async sendErrorReport(report: ErrorReport): Promise<void> {
    try {
      const service = getSupremeAIService();
      const result = await service.reportError(report);
      if (result.success) {
        console.log(`[SupremeAI] Error reported: ${report.filePath}:${report.lineNumber}`);
      }
    } catch (error: any) {
      console.error(`[SupremeAI] Failed to send error report: ${error?.message || error}`);
      this.pendingReports.push(report);
      vscode.window.setStatusBarMessage('$(cloud-offline) SupremeAI: Error reporting failed (offline)', 4000);
    }
  }


  private mapSeverity(severity?: vscode.DiagnosticSeverity): 'error' | 'warning' | 'info' {
    switch (severity) {
      case vscode.DiagnosticSeverity.Error: return 'error';
      case vscode.DiagnosticSeverity.Warning: return 'warning';
      case vscode.DiagnosticSeverity.Information: return 'info';
      default: return 'info';
    }
  }

  private classifyError(diagnostic: vscode.Diagnostic): 'compilation' | 'runtime' | 'lint' | 'security' | 'performance' {
    const source = diagnostic.source?.toLowerCase() || '';
    const message = diagnostic.message.toLowerCase();

    // Use error codes for more specific classification
    const code = typeof diagnostic.code === 'object' && 'value' in diagnostic.code ? String((diagnostic.code as any).value) : String(diagnostic.code);
    if (code?.startsWith('ts')) {
      return 'compilation';
    }

    if (source.includes('ts') || source.includes('eslint') || source.includes('compiler')) {
      return 'compilation';
    }
    if (source.includes('lint') || source.includes('eslint') || source.includes('style')) {
      return 'lint';
    }
    if (source.includes('security') || message.includes('security') || message.includes('vulnerability')) {
      return 'security';
    }
    if (message.includes('performance') || message.includes('slow') || message.includes('memory')) {
      return 'performance';
    }

    return 'compilation'; // Default to compilation for syntax errors
  }

  /**
   * Manually report an error (called from commands)
   */
  async reportManualError(
    filePath: string,
    lineNumber: number,
    message: string,
    errorType: ErrorReport['errorType'] = 'compilation'
  ): Promise<void> {
    const report: ErrorReport = {
      errorType,
      errorMessage: message,
      filePath,
      lineNumber,
      severity: 'error',
      timestamp: new Date().toISOString(),
    };

    await this.sendErrorReport(report);
  }

  /**
   * Clear reported errors cache (useful for testing)
   */
  clearCache(): void {
    this.reportedErrors.clear();
  }
}
