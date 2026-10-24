/**
 * VsCodePlatformAdapter - Bridges shared-services to VS Code APIs
 * 
 * This adapter implements the TokenProvider interface from shared-services
 * using VS Code's authentication API.
 */
import * as vscode from 'vscode';
import type { TokenProvider } from '@supremeai/shared-services';

export class VsCodePlatformAdapter implements TokenProvider {
  private cachedToken: string | null = null;

  getToken(): string | null {
    return this.cachedToken;
  }

  async getAccessToken(): Promise<string> {
    const session = await vscode.authentication.getSession(
      'supremeai',
      ['openid', 'profile', 'email'],
      { createIfNone: true }
    );
    this.cachedToken = session.accessToken;
    return session.accessToken;
  }

  async getRefreshToken(): Promise<string | undefined> {
    // VS Code handles refresh internally; this may not be needed
    return undefined;
  }

  async isAuthenticated(): Promise<boolean> {
    try {
      const token = await this.getAccessToken();
      return !!token;
    } catch {
      return false;
    }
  }

  /**
   * Show VS Code-specific error message using showErrorMessage
   */
  showError(message: string): void {
    vscode.window.showErrorMessage(`[SupremeAI] ${message}`);
  }

  /**
   * Show VS Code information message
   */
  showInfo(message: string): void {
    vscode.window.showInformationMessage(`[SupremeAI] ${message}`);
  }

  /**
   * Get VS Code workspace context for telemetry
   */
  getContext(): Record<string, unknown> {
    return {
      workspaceFolders: vscode.workspace.workspaceFolders?.map(f => f.uri.fsPath) || [],
      editorLanguage: vscode.window.activeTextEditor?.document.languageId,
      extensionVersion: vscode.extensions.getExtension('supremeai.supremeai')?.packageJSON.version,
    };
  }
}
