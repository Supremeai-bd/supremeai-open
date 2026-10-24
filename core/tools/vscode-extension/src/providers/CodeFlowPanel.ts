import * as vscode from 'vscode';
import { getSupremeAIService } from '../services/SupremeAIService';

export class CodeFlowPanel {
  private static active: CodeFlowPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];

  static createOrShow(extensionUri: vscode.Uri) {
    if (CodeFlowPanel.active) {
      CodeFlowPanel.active.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }
    const panel = vscode.window.createWebviewPanel('supremeaiCodeFlow', 'SupremeAI CodeFlow', vscode.ViewColumn.Beside, {
      enableScripts: true,
      retainContextWhenHidden: true,
    });
    CodeFlowPanel.active = new CodeFlowPanel(panel, extensionUri);
  }

  private constructor(panel: vscode.WebviewPanel, private readonly extensionUri: vscode.Uri) {
    this.panel = panel;
    panel.onDidDispose(() => {
      this.dispose();
      CodeFlowPanel.active = undefined;
    }, undefined, this.disposables);
    this.load();
  }

  private async load(): Promise<void> {
    this.panel.webview.html = this.getLoadingHTML();
    try {
      const service = getSupremeAIService();
      const dir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
      const files = await vscode.workspace.findFiles('**/*.{ts,js,py,java,go}', '**/node_modules/**', 500);
      const mapped = files.slice(0, 60).map(uri => ({
        path: uri.fsPath,
        query: this.labelForPath(uri.fsPath),
      }));
      const grid = this.inferGrid(mapped.map(f => f.query));
      const graph = {
        nodes: grid.nodes.map(n => ({ id: n, label: n, type: 'file' })),
        edges: grid.edges.map(e => ({ source: e.from, target: e.to, type: e.kind })),
      } as const;
      const summary = { filesAnalyzed: mapped.length, dependencies: graph.nodes.length, relationships: graph.edges.length };
      this.panel.webview.html = this.getHTML({ files: mapped, graph, summary });
    } catch (error: any) {
      this.panel.webview.html = this.getErrorHTML(error.message ?? 'Failed to load CodeFlow analysis');
    }
  }

  private labelForPath(path: string): string {
    const url = new URL('file:///dummy');
    const base = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
    const rel = path.replace(base, '').replace(/^[\\/]/, '');
    return rel.split(/[\\/]/).slice(0, 2).join('/');
  }

  private inferGrid(labels: string[]) {
    const byPrefix = new Map<string, string[]>();
    for (const label of labels) {
      const prefix = label.includes('/') ? label.split('/').slice(0, 2).join('/') : label;
      if (!byPrefix.has(prefix)) byPrefix.set(prefix, []);
      byPrefix.get(prefix)!.push(label);
    }
    const edges: { from: string; to: string; kind: 'calls' | 'imports' | 'depends' }[] = [];
    for (const [root, children] of byPrefix) {
      for (const child of children) {
        if (child !== root) edges.push({ from: root, to: child, kind: 'imports' });
      }
    }
    const nodes = Array.from(byPrefix.keys());
    const more = labels.filter(l => !nodes.includes(l)).slice(0, 20);
    for (const node of more) {
      nodes.push(node);
      const target = labels.find(l => l !== node && l.startsWith('src'));
      if (target) edges.push({ from: node, to: target, kind: 'calls' });
    }
    return { nodes, edges };
  }

  private getLoadingHTML(): string {
    return '<html><body><div style="padding:20px;color:var(--vscode-descriptionForeground)">Loading CodeFlow analysis...</div></body></html>';
  }

  private getErrorHTML(message: string): string {
    return `<html><body><div style="padding:20px;color:var(--vscode-errorForeground)">${this.escapeHtml(message)}</div></body></html>`;
  }

  private getHTML(data: { files: { path: string; query: string }[]; graph: any; summary: Record<string, unknown> }): string {
    const safe = encodeURIComponent(JSON.stringify(data.graph));
    const readiness = JSON.stringify(data.summary);
    const files = data.files.map(f => `<li>${this.escapeHtml(f.path)}</li>`).join('');
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline' https: vscode-webview-resource:; script-src 'unsafe-inline' 'unsafe-eval' https: vscode-webview-resource:; img-src 'self' data: https: vscode-webview-resource:;">
  <style>
    body { font-family: var(--vscode-font-family); background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); padding: 12px; }
    .section { margin: 12px 0; }
    ul { padding-left: 16px; max-height: 180px; overflow: auto; background: var(--vscode-textBlockQuote-background); border-radius: 6px; padding: 8px; }
    li { font-size: 12px; line-height: 1.6; }
  </style>
  <script>
    const vscode = acquireVsCodeApi();
    try {
      window.data = JSON.parse(decodeURIComponent("${safe}"));
    } catch {
      window.data = null;
      console.error("[SupremeAI] Invalid webview payload");
    }
  </script>
</head>
<body>
  <h2>CodeFlow Analysis</h2>
  <div class="section">
    <strong>Summary</strong>
    <pre>${this.escapeHtml(JSON.stringify(data.summary, null, 2))}</pre>
  </div>
  <div class="section">
    <strong>Open Tree</strong>
    <ul>${files}</ul>
  </div>
  <script>
    const graph = window.data;
    // Placeholder renderer; plug in cytoscape/d3 from an external build as needed
    console.log('CodeFlow graph', graph);
  </script>
</body>
</html>`;
  }

  private escapeHtml(value: string): string {
    return value.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', '\'': '&#39;' }[c] ?? c));
  }

  dispose() {
    this.disposables.forEach(d => d.dispose());
    this.disposables = [];
  }
}
