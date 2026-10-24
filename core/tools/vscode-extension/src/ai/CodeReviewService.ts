import { getAIService, CodeSuggestion } from './AIService';
import { getSupremeAIService } from '../services/SupremeAIService';
import * as vscode from 'vscode';

export interface CodeReviewIssue {
  line: number;
  severity: 'error' | 'warning' | 'info';
  message: string;
  suggestion: string;
  code?: string;
}

export class CodeReviewService {
  private aiService = getAIService();
  private backendService = getSupremeAIService();

  async reviewCode(
    code: string,
    language: string,
    filePath: string
  ): Promise<CodeReviewIssue[]> {
    if (!this.aiService.isAIEnabled()) {
      return this.getBasicReview(code, language);
    }

    const suggestion = await this.aiService.generateCodeCompletion(
      `Review this ${language} code for issues:\n${code}\n\nReturn JSON: {issues: [{line, severity, message, suggestion}]}`,
      language
    );

    if (suggestion) {
      try {
        const parsed = JSON.parse(suggestion.code);
        return parsed.issues || [];
      } catch {
        return this.getBasicReview(code, language);
      }
    }

    return this.getBasicReview(code, language);
  }

  async reviewSelection(code: string, language: string): Promise<CodeSuggestion | null> {
    const prompt = `Review and improve this selected ${language} code:\n${code}`;
    try {
      const response = await this.backendService.sendChatMessage({
        message: prompt,
        sessionId: this.backendService.getSessionId(),
        messages: [],
        context: { source: 'vscode', timestamp: new Date().toISOString() },
      });
      return {
        id: `vscode_review_${Date.now()}`,
        type: 'refactor',
        title: 'Code Review',
        description: 'AI-powered review from backend',
        code: response.response || response.message || code,
        explanation: 'AI reviewed code from backend',
        confidence: 0.9,
        language,
        context: null,
      } as CodeSuggestion;
    } catch (error: any) {
      console.error(`[SupremeAI] Backend review failed: ${error.message}`);
      return this.aiService.generateCodeCompletion(prompt, language);
    }
  }

  private getBasicReview(code: string, language: string): CodeReviewIssue[] {
    const issues: CodeReviewIssue[] = [];
    code.split('\n').forEach((line: string, index: number) => {
      if (line.includes('console.log') && language !== 'javascript') {
        issues.push({
          line: index + 1,
          severity: 'warning',
          message: 'Debug statement found',
          suggestion: 'Remove console.log before production',
        });
      }
      if ((line.trim() || '').startsWith('TODO') || (line.trim() || '').startsWith('FIXME')) {
        issues.push({
          line: index + 1,
          severity: 'info',
          message: 'Todo/Fixme comment found',
          suggestion: 'Address this item',
        });
      }
    });
    return issues;
  }
}

let codeReviewInstance: CodeReviewService | null = null;

export function getCodeReviewService(): CodeReviewService {
  if (!codeReviewInstance) {
    codeReviewInstance = new CodeReviewService();
  }
  return codeReviewInstance;
}

export function setCodeReviewService(service: CodeReviewService): void {
  codeReviewInstance = service;
}
