import * as vscode from 'vscode';
import { getSupremeAIService } from '../services/SupremeAIService';
import { AuthService } from '../services/AuthService';

export class SupremeAIAdminDashboardProvider implements vscode.WebviewViewProvider {
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
  <div style="text-align: center; color: var(--vscode-descriptionForeground);">Loading Admin Dashboard...</div>
</body>
</html>`;
  }

  private setupWebviewMessageListener(webviewView: vscode.WebviewView): void {
    webviewView.webview.onDidReceiveMessage(
      async (data) => {
        switch (data.type) {
          case 'analyzeCodeFlow':
            vscode.commands.executeCommand('supremeai.analyzeCodeFlow');
            break;
          case 'runSecurityAudit':
            vscode.commands.executeCommand('supremeai.sendMessageToChat', 'Please run a security audit on my current active codebase.');
            break;
          case 'openSettings':
            vscode.commands.executeCommand('workbench.action.openSettings', 'supremeai');
            break;
          case 'refresh':
            this.updateContent(webviewView);
            break;
          case 'runHealthCheck':
            vscode.commands.executeCommand('supremeai.sendMessageToChat', 'Run a system health check and report status.');
            break;
          case 'optimizePerformance':
            vscode.commands.executeCommand('supremeai.sendMessageToChat', 'Analyze and optimize system performance.');
            break;
          case 'generateReport':
            vscode.commands.executeCommand('supremeai.sendMessageToChat', 'Generate a comprehensive system report.');
            break;
        }
      },
      undefined
    );
  }

  private async updateContent(webviewView: vscode.WebviewView): Promise<void> {
    const service = getSupremeAIService();
    const stats = await service.getLearningStats();
    const config = vscode.workspace.getConfiguration('supremeai');
    const apiProvider = config.get<string>('apiProvider') || 'supremeai';
    const model = config.get<string>('aiModel') || 'supreme-large';
    const enableRealTimeLearning = config.get<boolean>('enableRealTimeLearning', true);
    const autoReportErrors = config.get<boolean>('autoReportErrors', true);

    // Get additional system metrics
    const systemInfo = {
      extensionVersion: vscode.extensions.getExtension('supremeai.supremeai')?.packageJSON.version || 'unknown',
      vsCodeVersion: vscode.version,
      workspaceFolders: vscode.workspace.workspaceFolders?.length || 0,
      activeTextEditor: !!vscode.window.activeTextEditor,
      theme: vscode.workspace.getConfiguration('workbench').get('colorTheme') || 'default'
    };

    webviewView.webview.html = this.getHTMLContent(stats, systemInfo, apiProvider, model, enableRealTimeLearning, autoReportErrors);
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
    systemInfo: any,
    apiProvider: string,
    model: string,
    enableRealTimeLearning: boolean,
    autoReportErrors: boolean
  ): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SupremeAI Admin Dashboard</title>
  <style>
    :root {
      --glass-bg: rgba(255, 255, 255, 0.05);
      --glass-border: rgba(255, 255, 255, 0.1);
      --highlight: #a855f7;
      --highlight-gradient: linear-gradient(135deg, #a855f7 0%, #6366f1 100%);
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
      box-shadow: 0 4px 15px rgba(168, 85, 247, 0.2);
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
      background: rgba(168, 85, 247, 0.1);
      border: 1px solid rgba(168, 85, 247, 0.2);
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
  </style>
</head>
<body>
  <div class="header">
    <h2>🔱 SupremeAI Admin Dashboard</h2>
  </div>

  <div class="card">
    <div class="section-title">System Status</div>
    <div class="grid-2col">
      <div class="metric-card">
        <div class="metric-value">${stats?.editCount || 0}</div>
        <div class="metric-label">Code Edits</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">${stats?.feedbackCount || 0}</div>
        <div class="metric-label">Feedback</div>
      </div>
    </div>
    <div class="stat-row" style="margin-top: 10px;">
      <span class="stat-label">Active Provider</span>
      <span class="stat-value" style="text-transform: uppercase; font-size: 11px;">${apiProvider}</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Model</span>
      <span class="stat-value" style="font-size: 11px;">${model}</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Auto-Learn</span>
      <span class="stat-value"><span class="status-badge ${enableRealTimeLearning ? 'status-active' : 'status-inactive'}">${enableRealTimeLearning ? 'ACTIVE' : 'INACTIVE'}</span></span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Error Reporting</span>
      <span class="stat-value"><span class="status-badge ${autoReportErrors ? 'status-active' : 'status-inactive'}">${autoReportErrors ? 'ENABLED' : 'DISABLED'}</span></span>
    </div>
  </div>

  <div class="card">
    <div class="section-title">System Info</div>
    <div class="stat-row">
      <span class="stat-label">Extension Version</span>
      <span class="stat-value">${systemInfo.extensionVersion}</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">VS Code Version</span>
      <span class="stat-value">${systemInfo.vsCodeVersion}</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Workspace Folders</span>
      <span class="stat-value">${systemInfo.workspaceFolders}</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Active Editor</span>
      <span class="stat-value">${systemInfo.activeTextEditor ? 'YES' : 'NO'}</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Theme</span>
      <span class="stat-value" style="font-size: 11px;">${systemInfo.theme}</span>
    </div>
  </div>

  <div class="card">
    <div class="section-title">Admin Controls</div>
    <button class="btn" id="analyzeBtn">Run CodeFlow Analysis</button>
    <button class="btn" id="securityAuditBtn">Run Security Audit</button>
    <button class="btn" id="healthCheckBtn">Run Health Check</button>
    <button class="btn" id="perfOptimizeBtn">Optimize Performance</button>
    <button class="btn btn-secondary" id="reportBtn">Generate Report</button>
    <button class="btn btn-secondary" id="settingsBtn">Extension Settings</button>
  </div>

  <div class="card">
    <div class="section-title">Quick Actions</div>
    <div style="display: flex; gap: 6px; flex-wrap: wrap;">
      <button class="btn" style="flex: 1; padding: 6px; font-size: 11px;" id="refreshBtn">🔄 Refresh</button>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();
    window.addEventListener("unload", () => { /* Cleanup */ });

    document.getElementById('analyzeBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'analyzeCodeFlow' });
    });
    document.getElementById('securityAuditBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'runSecurityAudit' });
    });
    document.getElementById('settingsBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'openSettings' });
    });
    document.getElementById('healthCheckBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'runHealthCheck' });
    });
    document.getElementById('perfOptimizeBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'optimizePerformance' });
    });
    document.getElementById('reportBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'generateReport' });
    });
    document.getElementById('refreshBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'refresh' });
    });
  </script>
</body>
</html>`;
  }
}



