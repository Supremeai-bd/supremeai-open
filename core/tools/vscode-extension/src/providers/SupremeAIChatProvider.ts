import * as vscode from 'vscode';
import { StreamingChatProvider } from './StreamingChatProvider';
import { AuthService } from '../services/AuthService';
import { getSupremeAIService } from '../services/SupremeAIService';
import { ChatMessage, ChatSession, ChatRequest } from '../types';
import { SupremeAIChatView } from './SupremeAIChatView';

export class SupremeAIChatProvider implements vscode.WebviewViewProvider {
  private readonly viewId: string;
  private webview: vscode.WebviewView | null = null;
  private messageHistory: ChatMessage[] = [];
  private currentSession: ChatSession | null = null;
  private authListenerDisposable?: vscode.Disposable;

  constructor(context: vscode.ExtensionContext | string) {
    this.viewId = typeof context === 'string' ? context : 'supremeaiChat';
  }

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this.webview = webviewView;

    webviewView.webview.options = {
      enableScripts: true
    };

    this.setupWebviewMessageListener(webviewView);
    this.updateContent(webviewView);

    const authService = AuthService.getInstance();
    if (authService) {
      this.authListenerDisposable?.dispose();
      this.authListenerDisposable = authService.onAuthStateChanged(() => {
        if (this.webview) {
          this.updateContent(this.webview);
        }
      });
    }
  }

  private setupWebviewMessageListener(webviewView: vscode.WebviewView): void {
    webviewView.webview.onDidReceiveMessage(
      async (data) => {
        switch (data.type) {
          case 'sendMessage':
            await this.handleSendMessage(data.message, data.context);
            break;
          case 'newChat':
            await this.handleNewChat();
            break;
          case 'clearChat':
            await this.handleClearChat();
            break;
          case 'explainCode':
            await this.handleExplainCode();
            break;
          case 'fixCode':
            await this.handleFixCode();
            break;
          case 'refactorCode':
            await this.handleRefactorCode();
            break;
          case 'login':
            vscode.commands.executeCommand('supremeai.login');
            break;
          case 'loginAsGuest':
            vscode.commands.executeCommand('supremeai.loginAsGuest');
            break;
          case 'logout':
            vscode.commands.executeCommand('supremeai.logout');
            break;
          case 'openSettings':
            vscode.commands.executeCommand('workbench.action.openSettings', 'supremeai');
            break;
        }
      },
      undefined
    );
  }

  private async handleSendMessage(message: string, context?: any): Promise<void> {
    if (!message.trim()) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: new Date().toISOString()
    };

    this.addMessage(userMessage);
    this.webview?.webview.postMessage({ type: 'addMessage', message: userMessage });
    this.showThinkingIndicator();

    try {
      const service = getSupremeAIService();
      const editor = vscode.window.activeTextEditor;
      let codeContext = '';

      if (editor && context?.includeCode !== false) {
        const document = editor.document;
        const selection = editor.selection;
        const selectedText = document.getText(selection);
        const fullText = document.getText();

        codeContext = '\n\n--- Code Context ---\n' +
          `Language: ${document.languageId}\n` +
          `File: ${document.fileName}\n` +
          (selectedText ? `Selected: ${selectedText}\n` : '') +
          `Relevant code:\n${this.getRelevantCode(fullText, message)}`;
      }

      const request: ChatRequest = {
        message: message + codeContext,
        sessionId: service.getSessionId(),
        messages: this.messageHistory.filter(m => !m.thinking),
        context: {
          source: 'vscode',
          timestamp: new Date().toISOString()
        }
      };

      const res = await service.sendChatMessage(request);
      if (this.webview) {
        this.webview.webview.postMessage({ type: 'streamChunk', text: res.response });
      }
      const response = res.response;

      await this.removeThinkingIndicator();

      this.webview?.webview.postMessage({ type: 'streamEnd' });

      const aiMessage: ChatMessage = {
        id: Date.now().toString(),
        role: 'assistant',
        content: response,
        timestamp: new Date().toISOString()
      };

      this.addMessage(aiMessage);
      this.webview?.webview.postMessage({ type: 'addMessage', message: aiMessage });
    } catch (error: any) {
      await this.removeThinkingIndicator();
      const errorMessage: ChatMessage = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `Backend error: ${error.message}. Please log in with a SupremeAI account.`,
        timestamp: new Date().toISOString(),
        error: true
      };
      this.addMessage(errorMessage);
      this.webview?.webview.postMessage({ type: 'addMessage', message: errorMessage });
    }
  }

  private async sendChatRequest(message: string, codeContext: string = ''): Promise<string> {
    const service = getSupremeAIService();

    const history = this.messageHistory.filter(m => !m.thinking);
    const request: any = {
      message: message + codeContext,
      sessionId: service.getSessionId(),
      messages: history,
      context: {
        source: 'vscode',
        timestamp: new Date().toISOString()
      }
    };

    const response = await (service as any).sendChatMessage(request);
    return response.response || response.message || 'No response from backend.';
  }

  private getRelevantCode(fullText: string, _message: string): string {
    const lines = fullText.split('\n');
    const maxLines = 50;

    if (lines.length <= maxLines) {
      return fullText;
    }

    const firstPart = lines.slice(0, 25).join('\n');
    const lastPart = lines.slice(-25).join('\n');

    return `${firstPart}\n\n... [${lines.length - 50} lines omitted] ...\n\n${lastPart}`;
  }

  private async handleNewChat(): Promise<void> {
    this.messageHistory = [];
    this.currentSession = null;
    this.updateContent(this.webview!);
    vscode.window.showInformationMessage('New chat session started');
  }

  private async handleClearChat(): Promise<void> {
    this.messageHistory = [];
    this.updateContent(this.webview!);
    vscode.window.showInformationMessage('Chat history cleared');
  }

  private async handleExplainCode(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor to explain code from');
      return;
    }

    const selection = editor.selection;
    const code = editor.document.getText(selection);

    if (!code) {
      vscode.window.showWarningMessage('Please select code to explain');
      return;
    }

    await this.handleSendMessage(`Please explain this code:\n\n${code}`, { includeCode: false });
  }

  private async handleFixCode(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor to fix code from');
      return;
    }

    const selection = editor.selection;
    const code = editor.document.getText(selection);

    if (!code) {
      vscode.window.showWarningMessage('Please select code to fix');
      return;
    }

    await this.handleSendMessage(`Please help fix this code:\n\n${code}`, { includeCode: false });
  }

  private async handleRefactorCode(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor to refactor code from');
      return;
    }

    const selection = editor.selection;
    const code = editor.document.getText(selection);

    if (!code) {
      vscode.window.showWarningMessage('Please select code to refactor');
      return;
    }

    await this.handleSendMessage(`Please suggest improvements for this code:\n\n${code}`, { includeCode: false });
  }

  private addMessage(message: ChatMessage): void {
    this.messageHistory.push(message);
    if (this.messageHistory.length > 100) {
      this.messageHistory = this.messageHistory.slice(-100);
    }
  }

  private showThinkingIndicator(): void {
    if (!this.webview) return;

    const thinkingMsg: ChatMessage = {
      id: 'thinking',
      role: 'assistant',
      content: 'Thinking...',
      timestamp: new Date().toISOString(),
      thinking: true
    };

    this.addMessage(thinkingMsg);
    this.webview.webview.postMessage({ type: 'showThinking' });
  }

  private async removeThinkingIndicator(): Promise<void> {
    this.messageHistory = this.messageHistory.filter(m => m.id !== 'thinking');
    this.webview?.webview.postMessage({ type: 'removeThinking' });
    return new Promise(resolve => setTimeout(resolve, 50));
  }

  private updateContent(webviewView: vscode.WebviewView): void {
    const authService = AuthService.getInstance();
    const isGuest = !authService || !authService.isAuthenticated();
    const username = (authService && authService.getUser()?.username) || 'Guest User';
    const config = vscode.workspace.getConfiguration('supremeai');
    const hasApiKey = !!config.get<string>('aiApiKey');

    webviewView.webview.html = SupremeAIChatView.getHTMLContent(isGuest, username, hasApiKey, this.messageHistory);
  }

  public dispose(): void {
    this.webview = null;
    this.authListenerDisposable?.dispose();
  }

  public postMessageToChat(message: string): void {
    if (this.webview) {
      this.webview.show(true);
      this.handleSendMessage(message);
    }
  }

  public getState(): any {
    return {
      messageHistory: this.messageHistory,
      currentSession: this.currentSession
    };
  }
}

