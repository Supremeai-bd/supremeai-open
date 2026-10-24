import * as vscode from 'vscode';
import { SupremeAIService } from '../services/SupremeAIService';

export class PerformanceMonitor {
  private supremeAIService: SupremeAIService;

  constructor(service: SupremeAIService) {
    this.supremeAIService = service;
  }

  public async analyzePerformance(code: string, language: string): Promise<any> {
    const response = await this.supremeAIService.sendChatMessage({
      message: `Analyze the performance of the following ${language} code and identify bottlenecks:\n\n\`\`\`${language}\n${code}\n\`\`\``,
      sessionId: this.supremeAIService.getSessionId()
    });

    return this.parsePerformanceInsights(response.response);
  }

  public async analyzeProjectPerformance(): Promise<any[]> {
    // প্রজেক্ট জুড়ে পারফরমেন্স বিশ্লেষণ করার লজিক
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
      return [];
    }

    const performanceInsights: any[] = [];
    
    // প্রতিটি ফাইল বিশ্লেষণ করা
    const files = await vscode.workspace.findFiles('**/*.{js,ts,jsx,tsx,py,java}', '**/node_modules/**');
    
    for (const file of files) {
      const document = await vscode.workspace.openTextDocument(file);
      const code = document.getText();
      const language = document.languageId;
      
      if (code.length > 100) { // Only analyze files with substantial content
        const insights = await this.analyzePerformance(code, language);
        performanceInsights.push({
          ...insights,
          file: file.path
        });
      }
    }

    return performanceInsights;
  }

  private parsePerformanceInsights(response: string): any {
    // পারফরমেন্স ইনসাইট পার্স করার লজিক
    return {
      bottlenecks: response.includes('bottleneck') ? ['Potential bottleneck identified'] : [],
      recommendations: response.includes('optimize') ? ['Consider optimizing algorithm'] : [],
      complexity_score: 75, // Example score
      estimated_impact: 'medium'
    };
  }
}