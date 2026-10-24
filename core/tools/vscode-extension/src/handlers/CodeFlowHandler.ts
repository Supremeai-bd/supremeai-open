/**
 * CodeFlow Handler - Code Analysis and Visualization
 * Handles CodeFlow analysis requests and visualization
 */

import * as vscode from 'vscode';
import { SupremeAIService, getSupremeAIService } from '../services/SupremeAIService';
import {
  CodeFlowAnalysisRequest,
  CodeFlowAnalysisResponse,
  ErrorResolutionRequest,
  SecurityIssue,
  HealthScore,
  DependencyGraph
} from '../types';

export class CodeFlowHandler {
  private context: vscode.ExtensionContext;
  private supremeAIService: SupremeAIService;
  private statusBarItem: vscode.StatusBarItem;
  private outputChannel: vscode.OutputChannel;

  constructor(context: vscode.ExtensionContext) {
    this.context = context;
    this.supremeAIService = getSupremeAIService();
    this.outputChannel = vscode.window.createOutputChannel('SupremeAI CodeFlow');

    // Create status bar item for health score
    this.statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    this.statusBarItem.text = '$(graph) CodeFlow';
    this.statusBarItem.tooltip = 'SupremeAI CodeFlow Analysis';
    this.statusBarItem.command = 'supremeai.openCodeFlowDashboard';
  }

  public register(): void {
    this.context.subscriptions.push(
      vscode.commands.registerCommand('supremeai.resolveError', this.resolveError.bind(this)),
      vscode.commands.registerCommand('supremeai.showSecurityIssues', this.showSecurityIssues.bind(this)),
      vscode.commands.registerCommand('supremeai.showDependencies', this.showDependencies.bind(this)),
      vscode.commands.registerCommand('supremeai.openCodeFlowDashboard', this.openCodeFlowDashboard.bind(this)),
      vscode.commands.registerCommand('supremeai.refreshCodeFlow', this.refreshAnalysis.bind(this)),
      vscode.workspace.onDidSaveTextDocument(this.onFileSave.bind(this)),
      this.statusBarItem
    );

    this.statusBarItem.show();

    // Zero-Lag Architecture: ব্যাকগ্রাউন্ড ইনডেক্সিং ডিফল্টভাবে নিষ্ক্রিয় (Disabled by default)
    // এবং টার্মিনাল সেশন খালি থাকলে অন-ডিমান্ড আইডিলে কাজ করবে।
    const config = vscode.workspace.getConfiguration('supremeai');
    const enableBackgroundSync = config.get<boolean>('enableBackgroundSync', false);

    if (enableBackgroundSync) {
      setTimeout(() => {
        this.syncWorkspaceToMemory();
      }, 30000);
    }

  }

  /**
   * Analyze current workspace or file with CodeFlow
   */
  public async analyzeCodeFlow(uri?: vscode.Uri): Promise<void> {
    try {
      vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'Running CodeFlow Analysis...',
        cancellable: true
      }, async (progress, token) => {
        progress.report({ increment: 0, message: 'Preparing files...' });

        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders) {
          vscode.window.showErrorMessage('No workspace folder open');
          return;
        }

        const files = await this.collectFiles(workspaceFolders[0].uri);

        progress.report({ increment: 30, message: `Analyzing ${files.length} files...` });

        const request: CodeFlowAnalysisRequest = {
          files: files.map(f => ({ path: f.path, content: f.content })),
          options: {
            includePatterns: true,
            includeSecurity: true,
            includeDependencies: true,
            depth: 3
          }
        };

        token.onCancellationRequested(() => {
          this.outputChannel.appendLine('Analysis cancelled by user');
        });

        const response = await this.supremeAIService.startCodeFlowAnalysis(request);

        if (response && response.success && response.data) {
          progress.report({ increment: 40, message: 'Processing results...' });

          await this.storeAnalysisResults(response.data);
          await this.updateHealthScore(response.data.healthScore);

          progress.report({ increment: 30, message: 'Displaying results...' });

          this.displayAnalysisResults(response.data);

          vscode.window.showInformationMessage(
            `CodeFlow Analysis Complete! Health Score: ${response.data.healthScore.grade} (${response.data.healthScore.score}/100)`,
            'View Dashboard',
            'View Security Issues'
          ).then(selection => {
            if (selection === 'View Dashboard') {
              this.openCodeFlowDashboard();
            } else if (selection === 'View Security Issues') {
              this.showSecurityIssues();
            }
          });
        } else {
          throw new Error(response?.message || 'Analysis failed');
        }
      });
    } catch (error: any) {
      vscode.window.showErrorMessage(`CodeFlow Analysis Failed: ${error.message}`);
      this.outputChannel.appendLine(`Error: ${error.message}`);
    }
  }

  /**
   * Resolve error with AI-powered suggestions
   */
  public async resolveError(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor');
      return;
    }

    const document = editor.document;
    const selection = editor.selection;
    const codeSnippet = document.getText(selection);

    if (!codeSnippet) {
      vscode.window.showWarningMessage('Please select the code with the error');
      return;
    }

    const errorMessage = await vscode.window.showInputBox({
      prompt: 'Enter the error message or description',
      placeHolder: 'e.g., TypeError: Cannot read property of undefined'
    });

    if (!errorMessage) {
      return;
    }

    const request: ErrorResolutionRequest = {
      errorType: 'runtime',
      errorMessage,
      codeSnippet,
      filePath: document.uri.fsPath,
      context: `File: ${document.fileName}\nLanguage: ${document.languageId}\nLine: ${selection.start.line + 1}`
    };

    try {
      vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'Analyzing error...',
        cancellable: false
      }, async () => {
        const response = await this.supremeAIService.resolveError(request);

        if (response && response.success && response.suggestedFixes.length > 0) {
          this.displayErrorResolution(response);
        } else {
          vscode.window.showInformationMessage('No fixes available. Try manual debugging.');
        }
      });
    } catch (error: any) {
      vscode.window.showErrorMessage(`Error resolution failed: ${error.message}`);
    }
  }

  /**
   * Show security issues in a table
   */
  public async showSecurityIssues(): Promise<void> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
      return;
    }

    const repositoryId = this.getRepositoryId(workspaceFolders[0].uri);
    const issues = await this.supremeAIService.getRepositorySecurityIssues(repositoryId);

    if (issues.length === 0) {
      vscode.window.showInformationMessage('No security issues found!');
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'securityIssues',
      'Security Issues',
      vscode.ViewColumn.One,
      { enableScripts: true }
    );

    panel.webview.html = this.getSecurityIssuesHtml(issues);
  }

  /**
   * Show dependency graph
   */
  public async showDependencies(): Promise<void> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
      return;
    }

    const repositoryId = this.getRepositoryId(workspaceFolders[0].uri);
    const graph = await this.supremeAIService.getDependencyGraph(repositoryId);

    if (!graph) {
      vscode.window.showInformationMessage('Run analysis first to generate dependency graph');
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'dependencyGraph',
      'Dependency Graph',
      vscode.ViewColumn.One,
      { enableScripts: true }
    );

    panel.webview.html = this.getDependencyGraphHtml(graph);
  }

  /**
   * Open CodeFlow dashboard
   */
  public async openCodeFlowDashboard(): Promise<void> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
      return;
    }

    const repositoryId = this.getRepositoryId(workspaceFolders[0].uri);
    const analysis = await this.supremeAIService.getCodeFlowAnalysis(repositoryId);

    if (!analysis) {
      const runAnalysis = await vscode.window.showInformationMessage(
        'No analysis found. Run CodeFlow analysis?',
        'Run Analysis',
        'Cancel'
      );

      if (runAnalysis === 'Run Analysis') {
        await this.analyzeCodeFlow();
      }
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'codeFlowDashboard',
      'CodeFlow Dashboard',
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true
      }
    );

    panel.webview.html = this.getDashboardHtml(analysis);
  }

  /**
   * Refresh analysis
   */
  public async refreshAnalysis(): Promise<void> {
    await this.analyzeCodeFlow();
  }

  /**
   * পুরো ওয়ার্কস্পেস স্ক্যান করে ফাইল ভেক্টর মেমোরিতে সিঙ্ক করার মেথড
   */
  private async syncWorkspaceToMemory(): Promise<void> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) return;

    try {
      const files = await this.collectFiles(workspaceFolders[0].uri);
      this.outputChannel.appendLine(`[SupremeAI] প্রারম্ভিক ইনডেক্সিং শুরু (ব্যাকগ্রাউন্ড ও লো-প্রায়োরিটি): ${files.length} ফাইল পাওয়া গেছে`);

      for (const file of files) {
        const ext = file.path.split('.').pop() || 'txt';
        try {
          await this.supremeAIService.sendCodeAnalysis(file.path, file.content, ext);
        } catch (fileErr: any) {
          this.outputChannel.appendLine(`[SupremeAI] ফাইল সিঙ্ক ব্যর্থ: ${file.path} (${fileErr.message})`);
        }
        // পিসি মন্থর না করতে প্রতি ফাইলের মাঝে ১.৫ সেকেন্ড বিরতি
        await new Promise(resolve => setTimeout(resolve, 1500));
      }
      this.outputChannel.appendLine('[SupremeAI] প্রারম্ভিক ইনডেক্সিং সফলভাবে সম্পন্ন হয়েছে');
    } catch (err: any) {
      this.outputChannel.appendLine(`[SupremeAI] প্রারম্ভিক ইনডেক্সিং ব্যর্থ হয়েছে: ${err.message}`);
    }
  }

  /**
   * Handle file save event
   */
  private async onFileSave(e: vscode.TextDocument): Promise<void> {
    // ফাইলটি ভেক্টর মেমোরিতে সিঙ্ক করার ব্যাকগ্রাউন্ড টাস্ক
    const allowedLanguages = ['javascript', 'typescript', 'python', 'go', 'rust', 'java', 'cpp', 'c'];
    if (allowedLanguages.includes(e.languageId)) {
      this.supremeAIService.sendCodeAnalysis(
        vscode.workspace.asRelativePath(e.uri),
        e.getText(),
        e.languageId
      ).then(res => {
        if (res && res.success) {
          console.log(`[SupremeAI] ভেক্টর মেমোরি অটো-সিঙ্ক সম্পন্ন: ${e.fileName}`);
        }
      }).catch(err => {
        console.error(`[SupremeAI] ভেক্টর মেমোরি অটো-সিঙ্ক ব্যর্থ: ${err.message}`);
      });
    }

    const config = vscode.workspace.getConfiguration('supremeai');
    const autoAnalyze = config.get<boolean>('autoAnalyzeOnSave', false);

    if (autoAnalyze && (e.languageId === 'javascript' || e.languageId === 'typescript')) {
      // Debounced analysis
      setTimeout(() => {
        this.analyzeCodeFlow(e.uri);
      }, 1000);
    }
  }

  /**
   * Collect files from workspace
   */
  private async collectFiles(workspaceUri: vscode.Uri): Promise<Array<{ path: string; content: string }>> {
    const files: Array<{ path: string; content: string }> = [];
    const patterns = ['**/*.js', '**/*.ts', '**/*.py', '**/*.go', '**/*.rs', '**/*.java', '**/*.rb', '**/*.cpp', '**/*.c'];

    const skippedFiles: string[] = [];

    for (const pattern of patterns) {
      const uris = await vscode.workspace.findFiles(new vscode.RelativePattern(workspaceUri.fsPath, pattern), '**/node_modules/**');

      for (const uri of uris) {
        try {
          const document = await vscode.workspace.openTextDocument(uri);
          files.push({
            path: vscode.workspace.asRelativePath(uri),
            content: document.getText()
          });
        } catch (error: any) {
          // Skip files that can't be read but log it to output channel/console
          const relPath = vscode.workspace.asRelativePath(uri);
          skippedFiles.push(relPath);
          console.warn(`[CodeFlow] Skipped reading file: ${relPath}. Error: ${error.message}`);
        }
      }
    }

    if (skippedFiles.length > 0) {
      console.warn(`[CodeFlow] Analysis completed with ${skippedFiles.length} skipped files:`, skippedFiles);
    }

    return files.slice(0, 100); // Limit to 100 files for performance
  }

  /**
   * Store analysis results
   */
  private async storeAnalysisResults(data: any): Promise<void> {
    await this.context.workspaceState.update('codeflow.lastAnalysis', data);
    await this.context.workspaceState.update('codeflow.lastAnalysisTime', new Date().toISOString());
  }

  /**
   * Update health score in status bar
   */
  private async updateHealthScore(score: HealthScore): Promise<void> {
    const color = this.getScoreColor(score.score);
    this.statusBarItem.color = color;
    this.statusBarItem.text = `$(graph) ${score.grade} ${score.score}/100`;
    this.statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
  }

  /**
   * Get color based on score
   */
  private getScoreColor(score: number): string {
    if (score >= 90) return '#00ff9d';
    if (score >= 80) return '#00d4ff';
    if (score >= 70) return '#ffd700';
    if (score >= 60) return '#ff8c00';
    return '#ff4444';
  }

  /**
   * Display analysis results
   */
  private displayAnalysisResults(data: any): void {
    this.outputChannel.clear();
    this.outputChannel.appendLine('=== CodeFlow Analysis Results ===\n');
    this.outputChannel.appendLine(`Health Score: ${data.healthScore.grade} (${data.healthScore.score}/100)`);
    this.outputChannel.appendLine(`Files Analyzed: ${data.files.length}`);
    this.outputChannel.appendLine(`Security Issues: ${data.securityIssues.length}`);
    this.outputChannel.appendLine(`Patterns Found: ${data.patterns.length}\n`);

    if (data.securityIssues.length > 0) {
      this.outputChannel.appendLine('--- Security Issues ---');
      data.securityIssues.forEach((issue: SecurityIssue) => {
        this.outputChannel.appendLine(`  [${issue.severity.toUpperCase()}] ${issue.type} in ${issue.file}:${issue.line}`);
      });
    }

    this.outputChannel.show();
  }

  /**
   * Display error resolution
   */
  private displayErrorResolution(response: any): void {
    const panel = vscode.window.createWebviewPanel(
      'errorResolution',
      'Error Resolution',
      vscode.ViewColumn.Beside,
      { enableScripts: true }
    );

    panel.webview.html = this.getErrorResolutionHtml(response);
  }

  /**
   * Get repository ID
   */
  private getRepositoryId(uri: vscode.Uri): string {
    const workspacePath = vscode.workspace.getWorkspaceFolder(uri)?.uri.fsPath || '';
    return Buffer.from(workspacePath).toString('base64');
  }

  /**
   * Generate HTML for security issues
   */
  private getSecurityIssuesHtml(issues: SecurityIssue[]): string {
    return `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; background: #0a0a0c; color: #f0f0f2; }
          h1 { color: #00ff9d; }
          .issue { background: #1a1a1f; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid #ff4444; }
          .issue.critical { border-left-color: #ff0000; }
          .issue.high { border-left-color: #ff4444; }
          .issue.medium { border-left-color: #ff8c00; }
          .issue.low { border-left-color: #ffd700; }
          .severity { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; margin-right: 10px; }
          .severity.critical { background: #ff0000; color: white; }
          .severity.high { background: #ff4444; color: white; }
          .severity.medium { background: #ff8c00; color: white; }
          .severity.low { background: #ffd700; color: black; }
          code { background: #2a2a30; padding: 2px 6px; border-radius: 4px; font-family: 'Consolas', monospace; }
          .fix { background: #00ff9d15; padding: 10px; border-radius: 4px; margin-top: 10px; border-left: 3px solid #00ff9d; }
        </style>
      </head>
      <body>
        <h1>🔒 Security Issues (${issues.length})</h1>
        ${issues.map(issue => `
          <div class="issue ${issue.severity}">
            <span class="severity ${issue.severity}">${issue.severity.toUpperCase()}</span>
            <strong>${issue.type}</strong> in <code>${issue.file}:${issue.line}</code>
            <p>${issue.description}</p>
            <pre><code>${issue.code}</code></pre>
            <div class="fix">
              <strong>💡 Fix:</strong> ${issue.fix}
            </div>
          </div>
        `).join('')}
      </body>
      </html>
    `;
  }

  /**
   * Generate HTML for dependency graph
   */
  private getDependencyGraphHtml(graph: DependencyGraph): string {
    return `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; background: #0a0a0c; color: #f0f0f2; }
          h1 { color: #00ff9d; }
          #graph { width: 100%; height: 600px; border: 1px solid #2a2a30; border-radius: 8px; }
          .node { cursor: pointer; }
          .node circle { stroke: #00ff9d; stroke-width: 2px; }
          .node text { font-size: 12px; fill: #f0f0f2; }
          .link { stroke: #00d4ff; stroke-opacity: 0.6; stroke-width: 1.5px; }
        </style>
        <script src="https://d3js.org/d3.v7.min.js"></script>
      </head>
      <body>
        <h1>📊 Dependency Graph</h1>
        <div id="graph"></div>
        <script>
          const graphData = ${JSON.stringify(graph)};

          const width = document.getElementById('graph').clientWidth;
          const height = 600;

          const svg = d3.select('#graph')
            .append('svg')
            .attr('width', width)
            .attr('height', height);

          const simulation = d3.forceSimulation(graphData.nodes)
            .force('link', d3.forceLink(graphData.edges).id(d => d.id).distance(100))
            .force('charge', d3.forceManyBody().strength(-300))
            .force('center', d3.forceCenter(width / 2, height / 2));

          const link = svg.append('g')
            .selectAll('line')
            .data(graphData.edges)
            .enter().append('line')
            .attr('class', 'link');

          const node = svg.append('g')
            .selectAll('g')
            .data(graphData.nodes)
            .enter().append('g')
            .attr('class', 'node');

          node.append('circle')
            .attr('r', d => Math.sqrt(d.metrics?.linesOfCode || 1) * 2 + 5)
            .attr('fill', d => {
              if (d.type === 'file') return '#00ff9d';
              if (d.type === 'function') return '#00d4ff';
              if (d.type === 'class') return '#ffd700';
              return '#ff8c00';
            });

          node.append('text')
            .attr('dx', 12)
            .attr('dy', 4)
            .text(d => d.label);

          simulation.on('tick', () => {
            link
              .attr('x1', d => d.source.x)
              .attr('y1', d => d.source.y)
              .attr('x2', d => d.target.x)
              .attr('y2', d => d.target.y);

            node
              .attr('transform', d => 'translate(' + d.x + ',' + d.y + ')');
          });
        </script>
      </body>
      </html>
    `;
  }

  /**
   * Generate HTML for dashboard
   */
  private getDashboardHtml(analysis: any): string {
    return `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; background: #0a0a0c; color: #f0f0f2; margin: 0; }
          h1 { color: #00ff9d; margin-top: 0; }
          .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
          .score { font-size: 48px; font-weight: bold; }
          .score.A { color: #00ff9d; }
          .score.B { color: #00d4ff; }
          .score.C { color: #ffd700; }
          .score.D { color: #ff8c00; }
          .score.F { color: #ff4444; }
          .metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }
          .metric { background: #1a1a1f; padding: 15px; border-radius: 8px; text-align: center; }
          .metric-value { font-size: 24px; font-weight: bold; color: #00ff9d; }
          .metric-label { font-size: 12px; color: #888; margin-top: 5px; }
          .section { background: #1a1a1f; padding: 15px; border-radius: 8px; margin: 15px 0; }
          .section h3 { color: #00ff9d; margin-top: 0; }
          .issue { background: #2a2a30; padding: 10px; margin: 5px 0; border-radius: 4px; border-left: 3px solid #ff4444; }
          .pattern { background: #2a2a30; padding: 10px; margin: 5px 0; border-radius: 4px; border-left: 3px solid #00d4ff; }
          button { background: #00ff9d; color: #0a0a0c; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-weight: bold; }
          button:hover { background: #00e68a; }
        </style>
      </head>
      <body>
        <div class="header">
          <h1>📊 CodeFlow Dashboard</h1>
          <div class="score ${analysis.healthScore.grade}">${analysis.healthScore.score}</div>
        </div>

        <div class="metrics">
          <div class="metric">
            <div class="metric-value">${analysis.files.length}</div>
            <div class="metric-label">Files</div>
          </div>
          <div class="metric">
            <div class="metric-value">${analysis.securityIssues.length}</div>
            <div class="metric-label">Security Issues</div>
          </div>
          <div class="metric">
            <div class="metric-value">${analysis.patterns.length}</div>
            <div class="metric-label">Patterns</div>
          </div>
        </div>

        <div class="section">
          <h3>Health Score Breakdown</h3>
          ${Object.entries(analysis.healthScore.breakdown).map(([key, value]) => `
            <div style="margin: 5px 0;">
              <span style="text-transform: capitalize;">${key}</span>: ${value}%
            </div>
          `).join('')}
        </div>

        ${analysis.securityIssues.length > 0 ? `
          <div class="section">
            <h3>Security Issues</h3>
            ${analysis.securityIssues.slice(0, 5).map((issue: any) => `
              <div class="issue">
                <strong>${issue.type}</strong> in ${issue.file}:${issue.line}<br>
                <small>${issue.description}</small>
              </div>
            `).join('')}
            ${analysis.securityIssues.length > 5 ? `<p>... and ${analysis.securityIssues.length - 5} more</p>` : ''}
          </div>
        ` : ''}

        ${analysis.patterns.length > 0 ? `
          <div class="section">
            <h3>Design Patterns Detected</h3>
            ${analysis.patterns.slice(0, 5).map((pattern: any) => `
              <div class="pattern">
                <strong>${pattern.type}</strong> in ${pattern.file}:${pattern.line}<br>
                <small>${pattern.description}</small>
              </div>
            `).join('')}
          </div>
        ` : ''}

        <button onclick="acquireVsCodeApi().postMessage({ command: 'refresh' })">🔄 Refresh Analysis</button>
      </body>
      </html>
    `;
  }

  /**
   * Generate HTML for error resolution
   */
  private getErrorResolutionHtml(response: any): string {
    return `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; background: #0a0a0c; color: #f0f0f2; margin: 0; }
          h1 { color: #00ff9d; }
          .root-cause { background: #1a1a1f; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #ff8c00; }
          .fix { background: #00ff9d15; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #00ff9d; }
          .fix.easy { border-left-color: #00ff9d; }
          .fix.medium { border-left-color: #ffd700; }
          .fix.hard { border-left-color: #ff8c00; }
          code { background: #2a2a30; padding: 2px 6px; border-radius: 4px; font-family: 'Consolas', monospace; }
          pre { background: #1a1a1f; padding: 15px; border-radius: 4px; overflow-x: auto; }
        </style>
      </head>
      <body>
        <h1>🔧 Error Resolution</h1>

        <div class="root-cause">
          <h3>Root Cause</h3>
          <p>${response.rootCause}</p>
          <p><strong>Confidence:</strong> ${Math.round(response.confidence * 100)}%</p>
        </div>

        ${response.affectedFiles.length > 0 ? `
          <div class="root-cause">
            <h3>Affected Files</h3>
            ${response.affectedFiles.map((file: string) => `<code>${file}</code>`).join('<br>')}
          </div>
        ` : ''}

        <h3>Suggested Fixes</h3>
        ${response.suggestedFixes.map((fix: any) => `
          <div class="fix ${fix.difficulty}">
            <h4>${fix.description} <span style="font-size: 12px; color: #888;">(${fix.difficulty})</span></h4>
            <p>${fix.explanation}</p>
            <pre><code>${fix.code}</code></pre>
            <p><strong>Impact:</strong> ${fix.impact}</p>
          </div>
        `).join('')}
      </body>
      </html>
    `;
  }
}

let codeFlowHandler: CodeFlowHandler;

export function getCodeFlowHandler(): CodeFlowHandler {
  return codeFlowHandler;
}

export function setCodeFlowHandler(handler: CodeFlowHandler): void {
  codeFlowHandler = handler;
}
