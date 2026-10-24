/**
 * SupremeAI Activity Tree Provider - Shows recent learning activity
 */

import * as vscode from 'vscode';
import { getSupremeAIService } from '../services/SupremeAIService';

export class SupremeAIActivityProvider implements vscode.TreeDataProvider<SupremeAIActivityItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<SupremeAIActivityItem | undefined | null>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private activityItems: SupremeAIActivityItem[] = [];

  refresh(): void {
    this.loadActivity();
    this._onDidChangeTreeData.fire(undefined);
  }

  private async loadActivity(): Promise<void> {
    try {
      const service = getSupremeAIService();
      const stats = await service.getLearningStats();

      this.activityItems = [];

      if (stats?.recentActivity) {
        for (const activity of stats.recentActivity) {
          this.activityItems.push(new SupremeAIActivityItem(activity));
        }
      }

      // Add some sample items if no real data
      if (this.activityItems.length === 0) {
        this.activityItems = [
          new SupremeAIActivityItem({
            type: 'INFO',
            message: 'SupremeAI is running and learning in the background',
            timestamp: new Date().toISOString()
          })
        ];
      }
    } catch (error) {
      console.error('[SupremeAI] Failed to load activity:', error);
    }
  }

  getTreeItem(element: SupremeAIActivityItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: SupremeAIActivityItem): Promise<SupremeAIActivityItem[]> {
    if (!element) {
      // Root level - return activity items
      return this.activityItems;
    }
    return [];
  }
}

export class SupremeAIActivityItem extends vscode.TreeItem {
  constructor(
    public readonly activity: {
      type: string;
      message: string;
      timestamp: string;
    }
  ) {
    super(activity.message, vscode.TreeItemCollapsibleState.None);

    this.description = this.formatTime(activity.timestamp);
    this.iconPath = this.getIcon(activity.type);
    this.tooltip = `${activity.type}: ${activity.message}`;
    this.contextValue = 'supremeai.activityItem';
  }

  private formatTime(timestamp: string): string {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);

    if (minutes < 1) return 'now';
    if (minutes < 60) return `${minutes}m`;
    if (hours < 24) return `${hours}h`;
    return date.toLocaleDateString();
  }

  private getIcon(type: string): string {
    switch (type) {
      case 'CODE_EDIT':
        return '$(edit)';
      case 'ERROR_REPORT':
        return '$(error)';
      case 'SUGGESTION_FEEDBACK':
        return '$(thumbsup)';
      default:
        return '$(info)';
    }
  }
}

