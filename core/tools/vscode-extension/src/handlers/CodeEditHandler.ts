/**
 * Code Edit Handler - Captures code changes for learning
 * Listens to text document changes and debounces them
 */

import * as vscode from 'vscode';
import { getSupremeAIService } from '../services/SupremeAIService';
import { CodeEdit } from '../types';

export class CodeEditHandler {
  private context: vscode.ExtensionContext;
  private debounceTimer: NodeJS.Timeout | null = null;
  private debounceDelay: number = 10000; // 10 seconds (ultra-lightweight typing optimization)
  private lastSentCode: Map<string, string> = new Map();
  private readonly MAX_CACHE_SIZE = 50; // আর্কিটেকচারাল ফিক্স: মেমোরি লিক রোধে ক্যাশের আকার সীমিত করা হলো

  constructor(context: vscode.ExtensionContext) {
    this.context = context;
  }

  /**
   * Register listeners for document changes
   */
  register(): void {
    // Listen to text document changes
    vscode.workspace.onDidChangeTextDocument(this.onDocumentChanged, this);

    // Also listen to document open/close for session tracking
    vscode.workspace.onDidOpenTextDocument(this.onDocumentOpened, this);
    vscode.workspace.onDidCloseTextDocument(this.onDocumentClosed, this);

    console.log('[SupremeAI] CodeEditHandler registered');
  }

  private onDocumentChanged(event: vscode.TextDocumentChangeEvent): void {
    const document = event.document;
    const languageId = document.languageId;
    const filePath = document.uri.fsPath;

    // Only analyze code files (ignore markdown, plain text, etc.)
    if (!this.isCodeFile(languageId)) {
      return;
    }

    // Clear previous timer
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }

    // Debounce: wait for user to stop typing
    this.debounceTimer = setTimeout(async () => {
      await this.processDocumentChange(document, filePath);
    }, this.debounceDelay);
  }

  private async processDocumentChange(document: vscode.TextDocument, filePath: string): Promise<void> {
    try {
      const code = document.getText();

      // Check if code actually changed (avoid sending identical content)
      const lastCode = this.lastSentCode.get(filePath);
      if (lastCode === code) {
        return;
      }

      // Get original code (could be stored in workspace state or from git diff)
      const originalCode = await this.getOriginalCode(filePath, document);

      if (originalCode !== null && originalCode !== code) {
        const edit: CodeEdit = {
          taskId: this.generateTaskId(filePath),
          originalCode,
          editedCode: code,
          context: `File: ${filePath}, Language: ${document.languageId}`,
          language: document.languageId,
          timestamp: new Date().toISOString(),
          filePath,
        };

        const service = getSupremeAIService();
        const result = await service.sendCodeEdit(edit);

        if (result.success) {
          console.log(`[SupremeAI] Learned from edit in ${filePath}`);
          this.lastSentCode.set(filePath, code);
          this._manageCacheSize(); // ক্যাশের আকার ম্যানেজ করার জন্য নতুন মেথড কল
        }
      }
    } catch (error: any) {
      console.error(`[SupremeAI] Error processing document change: ${error.message}`);
    }
  }

  private async getOriginalCode(filePath: string, document: vscode.TextDocument): Promise<string | null> {
    // Try to get original from:
    // 1. Undo stack (if available)
    // 2. Git diff (if file is tracked)
    // 3. Saved version from workspace state

    // For now, use workspace state to store baseline on file open
    const stateKey = `original_code_${filePath}`;
    const saved = this.context.globalState.get<string>(stateKey);

    if (saved) {
      return saved;
    }

    // If no saved original, store current as baseline
    if (!document.isDirty) {
      this.context.globalState.update(stateKey, document.getText());
    }

    return null; // Will skip learning until we have a baseline
  }

  private onDocumentOpened(document: vscode.TextDocument): void {
    const filePath = document.uri.fsPath;

    // Store initial version as baseline after 1 second (ensure file is settled)
    setTimeout(() => {
      if (!document.isDirty) {
        const stateKey = `original_code_${filePath}`;
        this.context.globalState.update(stateKey, document.getText());
        console.log(`[SupremeAI] Baseline stored for ${filePath}`);
      }
    }, 1000);
  }

  private onDocumentClosed(document: vscode.TextDocument): void {
    const filePath = document.uri.fsPath;
    this.lastSentCode.delete(filePath);
  }

  /**
   * মেমোরি লিক রোধ করার জন্য lastSentCode ম্যাপের আকার ম্যানেজ করে।
   * যদি ম্যাপের আকার MAX_CACHE_SIZE অতিক্রম করে, তবে সবচেয়ে পুরোনো এন্ট্রি মুছে দেয়।
   */
  private _manageCacheSize(): void {
    if (this.lastSentCode.size > this.MAX_CACHE_SIZE) {
      const oldestKey = this.lastSentCode.keys().next().value;
      if (oldestKey !== undefined) {
        this.lastSentCode.delete(oldestKey);
        console.log(`[SupremeAI] Cache limit reached. Evicted oldest entry: ${oldestKey}`);
      }
    }
  }

  private isCodeFile(languageId: string): boolean {
    const codeLanguages = [
      'typescript', 'javascript', 'python', 'java', 'cpp', 'c', 'csharp',
      'go', 'rust', 'kotlin', 'scala', 'swift', 'php', 'ruby', 'perl',
      'lua', 'r', 'matlab', 'sql', 'html', 'css', 'scss', 'less',
      'json', 'yaml', 'xml', 'shell', 'bash', 'powershell', 'dockerfile'
    ];
    return codeLanguages.includes(languageId);
  }

  private generateTaskId(filePath: string): string {
    const hash = this.simpleHash(filePath);
    return `task_${Date.now()}_${hash}`;
  }

  private simpleHash(str: string): number {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash);
  }
}
