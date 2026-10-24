import * as vscode from 'vscode';
import { getSupremeAIService } from '../services/SupremeAIService';
import { ChatRequest } from '../types';

export class StreamingChatProvider {
  private static instance: StreamingChatProvider | undefined;
  private disposables: vscode.Disposable[] = [];

  static getInstance(): StreamingChatProvider {
    if (!StreamingChatProvider.instance) {
      StreamingChatProvider.instance = new StreamingChatProvider();
    }
    return StreamingChatProvider.instance;
  }

  register(context: vscode.ExtensionContext): void {
    context.subscriptions.push(new vscode.Disposable(() => this.dispose()));
    vscode.commands.executeCommand('setContext', 'supremeai.streamingEnabled', true);
  }

  async sendMessageStream(message: string, onToken?: (token: string) => void): Promise<string> {
    const service = getSupremeAIService();
    const request: ChatRequest = {
      message,
      sessionId: service.getSessionId(),
      context: { source: 'vscode', timestamp: new Date().toISOString() },
    };
    const res = await service.sendChatMessage(request);
    onToken?.(res.response);
    return res.response;
  }

  dispose(): void {
    this.disposables.forEach(d => d.dispose());
    this.disposables = [];
  }
}

