import * as vscode from 'vscode';
import { getSupremeAIService } from '../services/SupremeAIService';
import { AuthService } from '../services/AuthService';

export class SupremeAICustomerDashboardProvider implements vscode.WebviewViewProvider {
  private webview: vscode.WebviewView | null = null;
  private updateTimer: NodeJS.Timeout | null = null;

  constructor(
    private readonly _extensionUri: vscode.Uri
  ) {}

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this.webview = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this._extensionUri]
    };

    this.setupWebviewMessageListener(webviewView);
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
    body {
      font-family: var(--vscode-font-family, sans-serif);
      padding: 12px;
      color: var(--vscode-foreground);
      background-color: var(--vscode-sideBar-background);
      margin: 0;
      font-size: 13px;
    }
    .spinner {
      width: 24px;
      height: 24px;
      border: 3px solid rgba(255,255,255,.3);
      border-radius: 50%;
      border-top-color: var(--vscode-button-background);
      animation: spin 1s ease-in-out infinite;
      margin: 20px auto;
    }
    @keyframes spin { 100% { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="spinner"></div>
  <div style="text-align: center; color: var(--vscode-descriptionForeground);">Loading Customer Dashboard...</div>
</body>
</html>`;
  }

  private setupWebviewMessageListener(webviewView: vscode.WebviewView): void {
    webviewView.webview.onDidReceiveMessage(
      async (data) => {
        switch (data.type) {
          case 'newChat':
            vscode.commands.executeCommand('supremeai.openChat');
            break;
          case 'logout':
            vscode.commands.executeCommand('supremeai.logout').then(() => {
              this.updateContent(webviewView);
            });
            break;
          case 'newProject':
            vscode.commands.executeCommand('supremeai.createProject');
            break;
          case 'viewHistory':
            vscode.commands.executeCommand('supremeai.viewHistory');
            break;
          case 'runAnalysis':
            vscode.commands.executeCommand('supremeai.aiReview');
            break;
          case 'getCodeHelp':
            vscode.commands.executeCommand('supremeai.aiExplain');
            break;
        }
      },
      undefined
    );
  }

  private async updateContent(webviewView: vscode.WebviewView): Promise<void> {
    const service = getSupremeAIService();
    const stats = await service.getLearningStats();
    const authService = AuthService.getInstance();
    const user = authService?.getUser();
    const username = user?.username || 'Guest User';
    const email = user?.email || 'N/A';
    const isLoggedIn = !!user;

    // Get additional usage stats
    const config = vscode.workspace.getConfiguration('supremeai');
    const defaultBackendHost = 'supremeai-backend' + '.onrender' + '.com';
    const backendUrl = config.get<string>('backendUrl', process.env.BACKEND_URL || `https://${defaultBackendHost}`);

    // Get workspace info
    const workspaceInfo = {
      workspaceFolders: vscode.workspace.workspaceFolders?.length || 0,
      activeTextEditor: !!vscode.window.activeTextEditor,
      languageId: vscode.window.activeTextEditor?.document.languageId || 'none',
      lineCount: vscode.window.activeTextEditor?.document.lineCount || 0
    };

    webviewView.webview.html = this.getHTMLContent(stats, username, email, isLoggedIn, backendUrl, workspaceInfo);
  }

  private startPeriodicUpdates(): void {
    this.updateTimer = setInterval(() => {
      if (this.webview) {
        this.updateContent(this.webview);
      }
    }, 30000); // 30 seconds refresh
  }

  public dispose(): void {
    if (this.updateTimer) {
      clearInterval(this.updateTimer);
      this.updateTimer = null;
    }
    this.webview = null;
  }

  private getHTMLContent(
    stats: any,
    username: string,
    email: string,
    isLoggedIn: boolean,
    backendUrl: string,
    workspaceInfo: any
  ): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SupremeAI Customer Dashboard</title>
  <style>
    :root {
      --glass-bg: rgba(255, 255, 255, 0.05);
      --glass-border: rgba(255, 255, 255, 0.1);
      --highlight: #10b981;
      --highlight-gradient: linear-gradient(135deg, #10b981 0%, #06b6d4 100%);
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --info: #3b82f6;
    }
    body {
      font-family: var(--vscode-font-family, sans-serif);
      padding: 12px;
      color: var(--vscode-foreground);
      background-color: var(--vscode-sideBar-background);
      margin: 0;
      font-size: 13px;
      line-height: 1.5;
    }
    .card {
      background: var(--glass-bg);
      border: 1px solid var(--glass-border);
      backdrop-filter: blur(10px);
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 12px;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .header {
      background: var(--highlight-gradient);
      color: white;
      padding: 14px;
      border-radius: 8px;
      margin-bottom: 16px;
      text-align: center;
      box-shadow: 0 4px 15px rgba(16, 185, 129, 0.2);
    }
    .header h2 {
      margin: 0;
      font-size: 16px;
      font-weight: 700;
      letter-spacing: 0.5px;
    }
    .stat-row {
      display: flex;
      justify-content: space-between;
      padding: 6px 0;
      border-bottom: 1px solid var(--glass-border);
    }
    .stat-label {
      color: var(--vscode-descriptionForeground);
    }
    .stat-value {
      font-weight: bold;
      color: var(--highlight);
    }
    .btn {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border: none;
      padding: 8px 12px;
      border-radius: 4px;
      cursor: pointer;
      width: 100%;
      margin-top: 8px;
      font-weight: bold;
      font-size: 12px;
      transition: background 0.2s ease;
      text-align: center;
    }
    .btn:hover {
      background: var(--vscode-button-hoverBackground);
    }
    .btn-secondary {
      background: transparent;
      border: 1px solid var(--glass-border);
      color: var(--vscode-foreground);
    }
    .section-title {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--vscode-descriptionForeground);
      margin-bottom: 8px;
      font-weight: 700;
      border-bottom: 1px solid var(--glass-border);
      padding-bottom: 4px;
    }
    .status-badge {
      display: inline-block;
      padding: 2px 6px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: bold;
    }
    .status-active {
      background: rgba(16, 185, 129, 0.2);
      color: var(--success);
    }
    .status-inactive {
      background: rgba(239, 68, 68, 0.2);
      color: var(--danger);
    }
    .grid-2col {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .metric-card {
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.2);
      border-radius: 6px;
      padding: 8px;
      text-align: center;
    }
    .metric-value {
      font-size: 18px;
      font-weight: bold;
      color: var(--highlight);
    }
    .metric-label {
      font-size: 11px;
      color: var(--vscode-descriptionForeground);
    }
    .user-info {
      text-align: center;
      padding: 8px 0;
      margin-bottom: 12px;
      border-bottom: 1px solid var(--glass-border);
    }
    .user-name {
      font-weight: bold;
      color: white;
      font-size: 14px;
    }
    .user-email {
      color: var(--vscode-descriptionForeground);
      font-size: 12px;
    }
  </style>
</head>
<body>
  <div class="header">
    <h2>👤 SupremeAI User Dashboard</h2>
  </div>

  <div class="card">
    <div class="user-info">
      <div class="user-name">${username}</div>
      <div class="user-email">${email}</div>
      <div style="margin-top: 6px;">
        <span class="status-badge ${isLoggedIn ? 'status-active' : 'status-inactive'}">
          ${isLoggedIn ? 'LOGGED IN' : 'GUEST'}
        </span>
      </div>
    </div>

    <div class="section-title">Usage Statistics</div>
    <div class="grid-2col">
      <div class="metric-card">
        <div class="metric-value">${stats?.editCount || 0}</div>
        <div class="metric-label">Edits</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">${stats?.feedbackCount || 0}</div>
        <div class="metric-label">Feedback</div>
      </div>
    </div>
    <div class="stat-row" style="margin-top: 10px;">
      <span class="stat-label">Backend URL</span>
      <span class="stat-value" style="font-size: 10px; word-break: break-all;">${backendUrl}</span>
    </div>
  </div>

  <div class="card">
    <div class="section-title">Workspace Info</div>
    <div class="stat-row">
      <span class="stat-label">Folders</span>
      <span class="stat-value">${workspaceInfo.workspaceFolders}</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Active Editor</span>
      <span class="stat-value">${workspaceInfo.activeTextEditor ? 'YES' : 'NO'}</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Language</span>
      <span class="stat-value">${workspaceInfo.languageId}</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Lines of Code</span>
      <span class="stat-value">${workspaceInfo.lineCount}</span>
    </div>
  </div>

  <div class="card">
    <div class="section-title">Quick Actions</div>
    <button class="btn" id="chatBtn">💬 Open Chat Panel</button>
    <button class="btn" id="analysisBtn">🔍 Analyze Current Code</button>
    <button class="btn" id="helpBtn">❓ Get Code Help</button>
    <button class="btn" id="historyBtn">📋 View History</button>
    <button class="btn ${isLoggedIn ? 'btn-secondary' : ''}" id="loginBtn">${isLoggedIn ? 'Logout' : 'Login'}</button>
  </div>

  <div class="card">
    <div class="section-title">Recent Stats</div>
    <div class="stat-row">
      <span class="stat-label">Suggestions Used</span>
      <span class="stat-value">${stats?.suggestionsUsed || 0}</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Code Generated</span>
      <span class="stat-value">${stats?.codeGenerated || 0} lines</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Tasks Completed</span>
      <span class="stat-value">${stats?.tasksCompleted || 0}</span>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();
    window.addEventListener("unload", () => { /* Cleanup */ });

    document.getElementById('chatBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'newChat' });
    });
    document.getElementById('loginBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'logout' });
    });
    document.getElementById('analysisBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'runAnalysis' });
    });
    document.getElementById('helpBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'getCodeHelp' });
    });
    document.getElementById('historyBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'viewHistory' });
    });
  </script>
</body>
</html>`;
  }
}



