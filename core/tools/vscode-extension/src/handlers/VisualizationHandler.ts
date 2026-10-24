import * as vscode from 'vscode';
import { SupremeAIService } from '../services/SupremeAIService';

export class VisualizationHandler {
  private context: vscode.ExtensionContext;
  private supremeAIService: SupremeAIService;

  constructor(context: vscode.ExtensionContext, service: SupremeAIService) {
    this.context = context;
    this.supremeAIService = service;
  }

  public register() {
    // ডিপেন্ডেন্সি গ্রাফ কমান্ড রেজিস্টার
    const dependencyGraphCommand = vscode.commands.registerCommand('supremeai.showDependencyGraph', async () => {
      await vscode.commands.executeCommand('supremeai.dependencyGraph.focus');
    });

    // আর্কিটেকচার ম্যাপ কমান্ড রেজিস্টার
    const architectureMapCommand = vscode.commands.registerCommand('supremeai.showArchitectureMap', async () => {
      vscode.window.showInformationMessage('Architecture Map feature coming soon!');
    });

    // ফ্লো চার্ট কমান্ড রেজিস্টার
    const flowChartCommand = vscode.commands.registerCommand('supremeai.showFlowChart', async () => {
      vscode.window.showInformationMessage('Flow Chart feature coming soon!');
    });

    // পারফরমেন্স ইনসাইট কমান্ড রেজিস্টার
    const performanceInsightCommand = vscode.commands.registerCommand('supremeai.showPerformanceInsights', async () => {
      vscode.window.showInformationMessage('Performance Insights feature coming soon!');
    });

    this.context.subscriptions.push(
      dependencyGraphCommand,
      architectureMapCommand,
      flowChartCommand,
      performanceInsightCommand
    );
  }
}