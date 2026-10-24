/**
 * PerformanceMonitor — Platform-Agnostic AI performance analysis.
 */

import type { SupremeAIService } from './SupremeAIService';
import type { PlatformTextDocument } from '../platform';

export interface PerformanceInsight {
  bottlenecks: string[];
  recommendations: string[];
  complexity_score: number;
  estimated_impact: 'low' | 'medium' | 'high';
  file?: string;
}

export class PerformanceMonitor {
  private supremeAIService: SupremeAIService;

  constructor(service: SupremeAIService) {
    this.supremeAIService = service;
  }

  public async analyzePerformance(code: string, language: string, filePath?: string): Promise<PerformanceInsight> {
    const response = await this.supremeAIService.sendChatMessage({
      message: `Analyze the performance of the following ${language} code and identify bottlenecks and optimization recommendations:\n\n\`\`\`${language}\n${code}\n\`\`\``,
      sessionId: this.supremeAIService.getSessionId(),
      context: {
        source: 'desktop',
        language,
        filePath,
        codeSnippet: code.length > 8000 ? code.slice(0, 8000) : code,
        timestamp: new Date().toISOString(),
      },
    });

    const insight = this.parsePerformanceInsights(response.response);
    return filePath ? { ...insight, file: filePath } : insight;
  }

  public async analyzeDocument(document: PlatformTextDocument): Promise<PerformanceInsight> {
    const code = document.getText();
    const language = document.languageId;
    return this.analyzePerformance(code, language, document.filePath);
  }

  private parsePerformanceInsights(response: string): PerformanceInsight {
    const lines = response ? response.split('\n') : [];
    const bottlenecks = lines.filter((l) => l.toLowerCase().includes('bottleneck'));
    const recommendations = lines.filter((l) => l.toLowerCase().includes('optimize') || l.toLowerCase().includes('recommend'));
    const complexityTokens = (response || '').match(/\b(if|for|while|switch|catch|map|reduce|filter)\b/g) || [];
    return {
      bottlenecks: bottlenecks.length ? bottlenecks : ['Potential bottleneck identified'],
      recommendations: recommendations.length ? recommendations : ['Consider optimizing hot paths'],
      complexity_score: Math.min(100, complexityTokens.length * 5 + 50),
      estimated_impact: bottlenecks.length > 0 ? 'high' : 'medium',
    };
  }
}