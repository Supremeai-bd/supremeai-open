/**
 * SecurityScanner — Platform-Agnostic AI-powered code security scanning.
 * ভিতরের AI কল SupremeAIService-এর chat বা evolution endpoint দিয়ে হয়।
 */

import type { SupremeAIService } from './SupremeAIService';
import type { PlatformTextDocument } from '../platform';

export interface SecurityIssueV2 {
  severity: 'critical' | 'high' | 'medium' | 'low';
  type: string;
  file?: string;
  line?: number;
  description: string;
  recommendation: string;
}

export class SecurityScanner {
  private supremeAIService: SupremeAIService;

  constructor(service: SupremeAIService) {
    this.supremeAIService = service;
  }

  /** একক ফাইলের সম্পূর্ণ টেক্সট AI দিয়ে স্ক্যান করে। */
  public async scanCode(code: string, language: string, filePath?: string): Promise<SecurityIssueV2[]> {
    const response = await this.supremeAIService.sendChatMessage({
      message: `Perform a security scan on the following ${language} code and identify potential vulnerabilities. Return a concise list of issues with severity (critical/high/medium/low), vulnerability type, and a fix recommendation:\n\n\`\`\`${language}\n${code}\n\`\`\``,
      sessionId: this.supremeAIService.getSessionId(),
      context: {
        source: 'desktop',
        language,
        filePath,
        codeSnippet: code.length > 8000 ? code.slice(0, 8000) : code,
        timestamp: new Date().toISOString(),
      },
    });

    const issues = this.parseSecurityIssues(response.response);
    return filePath ? issues.map((i) => ({ ...i, file: filePath })) : issues;
  }

  /** একটি প্ল্যাটফর্ম ডকুমেন্টকে স্ক্যান করার সুবিধা। */
  public async scanDocument(document: PlatformTextDocument): Promise<SecurityIssueV2[]> {
    const code = document.getText();
    const language = document.languageId;
    return this.scanCode(code, language, document.filePath);
  }

  /** একাধিক ডকুমেন্ট স্ক্যান করে (সমান্তরাল desktop ব্যবহারের জন্য)। */
  public async scanDocuments(documents: PlatformTextDocument[]): Promise<SecurityIssueV2[]> {
    const results: SecurityIssueV2[] = [];
    for (const doc of documents) {
      const issues = await this.scanDocument(doc);
      results.push(...issues);
    }
    return results;
  }

  private parseSecurityIssues(response: string): SecurityIssueV2[] {
    const issues: SecurityIssueV2[] = [];
    if (!response) return issues;

    const lines = response.split('\n');
    for (const line of lines) {
      const lower = line.toLowerCase();
      if (
        lower.includes('vulnerability') ||
        lower.includes('security') ||
        lower.includes('injection') ||
        lower.includes('xss') ||
        lower.includes('csrf') ||
        lower.includes('hardcoded') ||
        lower.includes('secret')
      ) {
        issues.push({
          severity: lower.includes('critical') ? 'critical' : 'medium',
          type: lower.includes('hardcoded') ? 'hardcoded_secret' : lower.includes('xss') ? 'xss' : 'potential_security_risk',
          description: line,
          recommendation: 'Review and validate inputs; fix the identified pattern.',
        });
      }
    }
    return issues;
  }
}