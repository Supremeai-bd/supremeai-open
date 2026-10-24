/**
 * SupremeAI Sidebar Provider - Webview-based sidebar panels
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { getSupremeAIService } from '../services/SupremeAIService';
import { AuthService } from '../services/AuthService';

export class SupremeAISidebarProvider implements vscode.WebviewViewProvider {
  private webview: vscode.WebviewView | null = null;
  private updateTimer: NodeJS.Timeout | null = null;
  private globalCss: string = '';

  constructor(
    private readonly _extensionUri: vscode.Uri,
    private readonly _viewId: string
  ) {
    this.loadGlobalCss();
  }

  private loadGlobalCss() {
    try {
      // Load the generated CSS tokens from the design-tokens package
      const cssPath = path.join(this._extensionUri.fsPath, '..', 'packages', 'design-tokens', 'outputs', 'tokens-vscode.css');
      if (fs.existsSync(cssPath)) {
        this.globalCss = fs.readFileSync(cssPath, 'utf8');
      }
    } catch (e) {
      console.error('Failed to load global CSS for webview', e);
    }
  }

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this.webview = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this._extensionUri]
    };

    this.setupWebviewMessageListener(webviewView);

    // Set initial loading state to avoid blank screen
    webviewView.webview.html = this.getLoadingHTML();

    this.updateContent(webviewView);
    this.startPeriodicUpdates();
  }

  private getLoadingHTML(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline' https: vscode-webview-resource:; script-src 'unsafe-inline' 'unsafe-eval' https: vscode-webview-resource:; img-src 'self' data: https: vscode-webview-resource:;">
  <style>
    ${this.globalCss}
    body {
      font-family: var(--supremeai-font-family-body, var(--vscode-font-family));
      padding: 20px;
      color: var(--supremeai-color-text-primary-dark, var(--vscode-descriptionForeground));
      background-color: var(--supremeai-color-bg-void-dark, var(--vscode-sideBar-background));
    }
    .skeleton-box {
      background-color: var(--vscode-sideBarSectionHeader-background);
      border-radius: 4px;
      position: relative;
      overflow: hidden;
      margin-bottom: 12px;
    }
    .skeleton-box::after {
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      left: 0;
      transform: translateX(-100%);
      background-image: linear-gradient(
        90deg,
        rgba(255, 255, 255, 0) 0,
        rgba(255, 255, 255, 0.05) 20%,
        rgba(255, 255, 255, 0.1) 60%,
        rgba(255, 255, 255, 0)
      );
      animation: shimmer 2s infinite;
      content: '';
    }
    @keyframes shimmer {
      100% {
        transform: translateX(100%);
      }
    }
  </style>
</head>
<body>
  <div class="skeleton-box" style="width: 60%; height: 24px;"></div>
  <div class="skeleton-box" style="width: 100%; height: 120px; margin-top: 20px;"></div>
  <div class="skeleton-box" style="width: 80%; height: 20px; margin-top: 20px;"></div>
  <div class="skeleton-box" style="width: 90%; height: 20px;"></div>
</body>
</html>`;
  }

  private setupWebviewMessageListener(webviewView: vscode.WebviewView): void {
    webviewView.webview.onDidReceiveMessage(
      async (data) => {
        switch (data.type) {
          case 'forceLearn':
            await this.handleForceLearn();
            break;
          case 'login':
            vscode.commands.executeCommand('supremeai.login').then(() => {
              this.updateContent(webviewView);
            });
            break;
          case 'openSettings':
            vscode.commands.executeCommand('workbench.action.openSettings', 'supremeai');
            break;
          case 'refresh':
            this.updateContent(webviewView);
            break;
        }
      },
      undefined
    );
  }

  private async handleForceLearn(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor to learn from');
      return;
    }

    const filePath = editor.document.uri.fsPath;
    const code = editor.document.getText();

    vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: 'SupremeAI Learning',
        cancellable: false,
      },
      async (progress) => {
        progress.report({ increment: 0, message: 'Analyzing code...' });
        const service = getSupremeAIService();
        const result = await service.sendCodeAnalysis(filePath, code, editor.document.languageId);
        progress.report({ increment: 100, message: 'Complete!' });

        if (result.success) {
          vscode.window.showInformationMessage('✅ Code analysis sent to SupremeAI learning engine');
          this.updateContent(this.webview!);
        } else {
          vscode.window.showErrorMessage(`❌ Learning failed: ${result.message}`);
        }
      }
    );
  }

  private async updateContent(webviewView: vscode.WebviewView): Promise<void> {
    const authService = AuthService.getInstance();
    if (!authService || !authService.isAuthenticated()) {
      webviewView.webview.html = this.getLoginHTML();
      return;
    }

    const service = getSupremeAIService();
    const stats = await service.getLearningStats();

    const content = this.getHTMLContent(stats);
    webviewView.webview.html = content;
  }

  private getLoginHTML(): string {
    return `<!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <style>
    ${this.globalCss}
    body {
      font-family: var(--supremeai-font-family-body, var(--vscode-font-family));
      padding: 20px;
      color: var(--supremeai-color-text-primary-dark, var(--vscode-foreground));
      background-color: var(--supremeai-color-bg-void-dark, var(--vscode-sideBar-background));
      text-align: center;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      height: 80vh;
    }
    .logo {
      font-size: 50px;
      margin-bottom: 20px;
    }
    .title {
      font-size: 18px;
      font-weight: bold;
      margin-bottom: 10px;
    }
    .desc {
      font-size: 13px;
      color: var(--vscode-descriptionForeground);
      margin-bottom: 24px;
      line-height: 1.5;
    }
    .btn {
      background: linear-gradient(135deg, color-mix(in srgb, var(--supremeai-color-brand-primary-dark) 15%, transparent), color-mix(in srgb, var(--supremeai-color-brand-secondary-dark) 15%, transparent));
      border: 1px solid var(--supremeai-color-brand-primary-dark);
      color: var(--supremeai-color-text-primary-dark);
      padding: 10px 20px;
      border-radius: var(--supremeai-radius-md);
      cursor: pointer;
      font-size: 14px;
      font-weight: bold;
      width: 100%;
      max-width: 200px;
      transition: all var(--supremeai-motion-duration-fast) var(--supremeai-motion-easing-bounce);
      box-shadow: 0 0 12px color-mix(in srgb, var(--supremeai-color-brand-primary-dark) 20%, transparent);
    }
    .btn:hover {
      background: linear-gradient(135deg, color-mix(in srgb, var(--supremeai-color-brand-primary-dark) 30%, transparent), color-mix(in srgb, var(--supremeai-color-brand-secondary-dark) 30%, transparent));
      box-shadow: 0 0 20px color-mix(in srgb, var(--supremeai-color-brand-primary-dark) 50%, transparent);
      transform: translateY(-2px);
    }
  </style>
</head>
<body>
  <div class="logo">🤖</div>
  <div class="title">SupremeAI-তে লগইন করুন</div>
  <div class="desc">আপনার কোড অ্যাসিস্ট্যান্ট ব্যবহার করতে এবং রিয়েল-টাইম এআই মেমোরি সিঙ্ক চালু করতে সাইন-ইন করা প্রয়োজন।</div>
  <button class="btn" id="loginBtn">লগইন করুন</button>

  <script>
    const vscode = acquireVsCodeApi();
    window.addEventListener("unload", () => { /* Cleanup */ });
    document.getElementById('loginBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'login' });
    });
  </script>
</body>
</html>`;
  }

  private startPeriodicUpdates(): void {
    this.updateTimer = setInterval(() => {
      if (this.webview) {
        this.updateContent(this.webview);
      }
    }, 30000); // Update every 30 seconds
  }

  public dispose(): void {
    if (this.updateTimer) {
      clearInterval(this.updateTimer);
      this.updateTimer = null;
    }
    this.webview = null;
  }

  private getHTMLContent(stats: any): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    ${this.globalCss}
    body {
      font-family: var(--supremeai-font-family-body, var(--vscode-font-family));
      padding: 16px;
      color: var(--supremeai-color-text-primary-dark, var(--vscode-foreground));
      background-color: var(--supremeai-color-bg-void-dark, var(--vscode-sideBar-background));
    }
    .header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--vscode-panel-border);
    }
    .icon {
      font-size: 24px;
    }
    .title {
      font-size: 16px;
      font-weight: bold;
      margin: 0;
    }
    .section {
      margin-bottom: 16px;
    }
    .section-title {
      font-size: 12px;
      text-transform: uppercase;
      color: var(--vscode-descriptionForeground);
      margin-bottom: 8px;
      font-weight: 600;
    }
    .stat-item {
      display: flex;
      justify-content: space-between;
      padding: 6px 0;
      border-bottom: 1px solid var(--vscode-sideBarSectionHeader-border);
    }
    .stat-label {
      color: var(--vscode-descriptionForeground);
    }
    .stat-value {
      font-weight: bold;
      color: var(--vscode-foreground);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      background-color: var(--supremeai-color-brand-success-dark);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--supremeai-color-brand-success-dark);
      animation: pulse 2s infinite var(--supremeai-motion-easing-smooth);
    }
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--supremeai-color-brand-success-dark) 70%, transparent); }
      70% { box-shadow: 0 0 0 6px rgba(0, 255, 102, 0); }
      100% { box-shadow: 0 0 0 0 rgba(0, 255, 102, 0); }
    }
    .button {
      background: color-mix(in srgb, var(--supremeai-color-bg-elevated-dark) 100%, transparent);
      color: var(--supremeai-color-text-secondary-dark);
      border: 1px solid var(--supremeai-color-border-accent-dark);
      padding: 8px 12px;
      border-radius: var(--supremeai-radius-md);
      cursor: pointer;
      width: 100%;
      margin: 4px 0;
      font-size: 13px;
      transition: all var(--supremeai-motion-duration-fast) var(--supremeai-motion-easing-bounce);
    }
    .button:hover {
      border-color: var(--supremeai-color-brand-primary-dark);
      background: color-mix(in srgb, var(--supremeai-color-brand-primary-dark) 8%, transparent);
      color: var(--supremeai-color-text-primary-dark);
      transform: translateY(-1px);
    }
    .status {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: bold;
    }
    .status.active {
      background: var(--vscode-testing-iconPassed);
      color: white;
    }
    .status.inactive {
      background: var(--vscode-errorBackground);
      color: white;
    }
    .activity-item {
      padding: 8px;
      margin: 4px 0;
      background: var(--vscode-list-hoverBackground);
      border-radius: 4px;
      font-size: 12px;
    }
    .empty-state {
      color: var(--vscode-descriptionForeground);
      text-align: center;
      padding: 20px;
      font-style: italic;
    }
  </style>
</head>
<body>
  <div class="header">
    <span class="icon">$(circuit-board)</span>
    <span class="title">SupremeAI</span>
    <span class="status ${stats?.enabled ? 'active' : 'inactive'}">${stats?.enabled ? 'Active' : 'Disabled'}</span>
  </div>

  <div class="section">
    <div class="section-title">Learning Statistics</div>
    <div class="stat-item">
      <span class="stat-label">Patterns Learned</span>
      <span class="stat-value">${stats?.learningCount || 0}</span>
    </div>
    <div class="stat-item">
      <span class="stat-label">System Status</span>
      <span class="stat-value"><div class="pulse-dot"></div> Online</span>
    </div>
    <div class="stat-item">
      <span class="stat-label">Code Edits</span>
      <span class="stat-value">${stats?.editCount || 0}</span>
    </div>
    <div class="stat-item">
      <span class="stat-label">Errors Reported</span>
      <span class="stat-value">${stats?.errorCount || 0}</span>
    </div>
    <div class="stat-item">
      <span class="stat-label">Feedback Given</span>
      <span class="stat-value">${stats?.feedbackCount || 0}</span>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Actions</div>
    <button class="button" id="forceLearn">$(sync) Force Learn Current File</button>
    <button class="button" id="reportError">$(error) Report Error</button>
    <button class="button" id="sendFeedback">$(comment) Send Feedback</button>
    <button class="button" id="openSettings">$(settings) Settings</button>
  </div>

  <div class="section">
    <div class="section-title">Recent Activity</div>
    <div id="activity">
      ${this.renderActivity(stats)}
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();
    window.addEventListener("unload", () => { /* Cleanup */ });

    document.getElementById('forceLearn').addEventListener('click', () => {
      vscode.postMessage({ type: 'forceLearn' });
    });

    document.getElementById('reportError').addEventListener('click', () => {
      vscode.postMessage({ type: 'reportError' });
    });

    document.getElementById('sendFeedback').addEventListener('click', () => {
      vscode.postMessage({ type: 'sendFeedback' });
    });

    document.getElementById('openSettings').addEventListener('click', () => {
      vscode.postMessage({ type: 'openSettings' });
    });
  </script>
</body>
</html>`;
  }

  private renderActivity(stats: any): string {
    if (!stats?.recentActivity || stats.recentActivity.length === 0) {
      return '<div class="empty-state">No recent activity</div>';
    }

    return stats.recentActivity
      .map((activity: any) => {
        const icon = this.getActivityIcon(activity.type);
        const time = this.formatTime(activity.timestamp);
        return `<div class="activity-item">
          <span>${icon}</span> ${this.escapeHtml(activity.message)} • ${this.escapeHtml(time)}
        </div>`;
      })
      .join('');
  }

  private escapeHtml(value: string): string {
    return String(value).replace(/[&<>"']/g, (c) => {
      switch (c) {
        case '&':
          return '&amp;';
        case '<':
          return '&lt;';
        case '>':
          return '&gt;';
        case '"':
          return '&quot;';
        case '\'':
          return '&#39;';
        default:
          return c;
      }
    });
  }

  private getActivityIcon(type: string): string {
    switch (type) {
      case 'CODE_EDIT': return '$(edit)';
      case 'ERROR_REPORT': return '$(error)';
      case 'SUGGESTION_FEEDBACK': return '$(thumbsup)';
      default: return '$(info)';
    }
  }

  private formatTime(timestamp: string): string {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);

    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${minutes}m`;
    if (hours < 24) return `${hours}h`;
    return date.toLocaleDateString();
  }
}



